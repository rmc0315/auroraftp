"""Folder synchronization engine."""

import asyncio
import fnmatch
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..core.events import event_bus
from ..core.models import RemoteFile, SyncMode, SyncProfile, TransferDirection, TransferItem
from ..protocols import ProtocolSession

logger = logging.getLogger(__name__)


class SyncAction:
    """Represents a sync action to be performed."""
    
    def __init__(
        self,
        action: str,  # upload, download, delete_local, delete_remote, mkdir_local, mkdir_remote
        local_path: Optional[Path] = None,
        remote_path: Optional[str] = None,
        size: int = 0,
        reason: str = "",
    ):
        self.action = action
        self.local_path = local_path
        self.remote_path = remote_path
        self.size = size
        self.reason = reason
    
    def __str__(self) -> str:
        if self.action == "upload":
            return f"Upload {self.local_path} -> {self.remote_path} ({self.reason})"
        elif self.action == "download":
            return f"Download {self.remote_path} -> {self.local_path} ({self.reason})"
        elif self.action == "delete_local":
            return f"Delete local {self.local_path} ({self.reason})"
        elif self.action == "delete_remote":
            return f"Delete remote {self.remote_path} ({self.reason})"
        elif self.action == "mkdir_local":
            return f"Create local directory {self.local_path}"
        elif self.action == "mkdir_remote":
            return f"Create remote directory {self.remote_path}"
        else:
            return f"{self.action}: {self.local_path} <-> {self.remote_path}"


class SyncResult:
    """Results of a sync operation."""
    
    def __init__(self):
        self.actions_planned: List[SyncAction] = []
        self.actions_executed: List[SyncAction] = []
        self.errors: List[Tuple[SyncAction, str]] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.dry_run: bool = False
    
    @property
    def duration(self) -> Optional[float]:
        """Get sync duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def success_count(self) -> int:
        """Number of successful actions."""
        return len(self.actions_executed)
    
    @property
    def error_count(self) -> int:
        """Number of failed actions."""
        return len(self.errors)
    
    @property
    def total_size(self) -> int:
        """Total size of transferred data."""
        return sum(action.size for action in self.actions_executed)


class SyncEngine:
    """Folder synchronization engine."""
    
    def __init__(self):
        self._current_sync: Optional[SyncProfile] = None
        self._cancelled = False
    
    async def compare_folders(
        self,
        profile: SyncProfile,
        session: ProtocolSession,
    ) -> List[SyncAction]:
        """Compare local and remote folders and plan sync actions."""
        self._current_sync = profile
        self._cancelled = False
        
        actions = []
        
        try:
            # Get local and remote file lists
            local_files = await self._scan_local_folder(profile.local_path, profile)
            remote_files = await self._scan_remote_folder(profile.remote_path, session, profile)
            
            # Compare and generate actions
            if profile.mode == SyncMode.MIRROR:
                actions = self._plan_mirror_sync(local_files, remote_files, profile)
            elif profile.mode == SyncMode.BIDIRECTIONAL:
                actions = self._plan_bidirectional_sync(local_files, remote_files, profile)
            elif profile.mode == SyncMode.UPLOAD_ONLY:
                actions = self._plan_upload_sync(local_files, remote_files, profile)
            elif profile.mode == SyncMode.DOWNLOAD_ONLY:
                actions = self._plan_download_sync(local_files, remote_files, profile)
            
            return actions
            
        except Exception as e:
            logger.error(f"Failed to compare folders: {e}")
            raise
    
    async def execute_sync(
        self,
        profile: SyncProfile,
        session: ProtocolSession,
        actions: Optional[List[SyncAction]] = None,
    ) -> SyncResult:
        """Execute synchronization."""
        result = SyncResult()
        result.start_time = datetime.utcnow()
        result.dry_run = profile.dry_run
        
        try:
            # Plan actions if not provided
            if actions is None:
                actions = await self.compare_folders(profile, session)
            
            result.actions_planned = actions
            
            if profile.dry_run:
                # Dry run - just return planned actions
                result.actions_executed = []
            else:
                # Execute actions
                await self._execute_actions(actions, session, result)
            
        except Exception as e:
            logger.error(f"Sync execution failed: {e}")
            raise
        finally:
            result.end_time = datetime.utcnow()
            self._current_sync = None
        
        return result
    
    async def _scan_local_folder(
        self,
        local_path: Path,
        profile: SyncProfile,
    ) -> Dict[str, Path]:
        """Scan local folder and return file mapping."""
        files = {}
        
        if not local_path.exists():
            return files
        
        def scan_recursive(path: Path, relative_base: Path) -> None:
            try:
                for item in path.iterdir():
                    if self._cancelled:
                        break
                    
                    relative_path = item.relative_to(relative_base)
                    relative_str = str(relative_path).replace("\\", "/")
                    
                    # Apply filters
                    if not self._should_include_file(relative_str, profile):
                        continue
                    
                    files[relative_str] = item
                    
                    if item.is_dir() and profile.follow_symlinks or not item.is_symlink():
                        scan_recursive(item, relative_base)
                        
            except PermissionError:
                logger.warning(f"Permission denied accessing {path}")
            except Exception as e:
                logger.warning(f"Error scanning {path}: {e}")
        
        await asyncio.get_event_loop().run_in_executor(
            None, scan_recursive, local_path, local_path
        )
        
        return files
    
    async def _scan_remote_folder(
        self,
        remote_path: str,
        session: ProtocolSession,
        profile: SyncProfile,
    ) -> Dict[str, RemoteFile]:
        """Scan remote folder and return file mapping."""
        files = {}
        
        async def scan_recursive(path: str, base_path: str) -> None:
            if self._cancelled:
                return
            
            try:
                items = await session.list_directory(path)
                
                for item in items:
                    if self._cancelled:
                        break
                    
                    # Calculate relative path
                    if path == base_path:
                        relative_path = item.name
                    else:
                        relative_path = f"{path[len(base_path):].lstrip('/')}/{item.name}"
                    
                    # Apply filters
                    if not self._should_include_file(relative_path, profile):
                        continue
                    
                    files[relative_path] = item
                    
                    # Recurse into directories
                    if item.is_directory:
                        await scan_recursive(item.path, base_path)
                        
            except Exception as e:
                logger.warning(f"Error scanning remote {path}: {e}")
        
        await scan_recursive(remote_path, remote_path)
        return files
    
    def _should_include_file(self, relative_path: str, profile: SyncProfile) -> bool:
        """Check if file should be included based on filters."""
        # Check include patterns
        if profile.include_patterns:
            included = False
            for pattern in profile.include_patterns:
                if fnmatch.fnmatch(relative_path, pattern):
                    included = True
                    break
            if not included:
                return False
        
        # Check exclude patterns
        for pattern in profile.exclude_patterns:
            if fnmatch.fnmatch(relative_path, pattern):
                return False
        
        return True
    
    def _plan_mirror_sync(
        self,
        local_files: Dict[str, Path],
        remote_files: Dict[str, RemoteFile],
        profile: SyncProfile,
    ) -> List[SyncAction]:
        """Plan mirror sync (local -> remote)."""
        actions = []
        
        # Upload new/modified local files
        for rel_path, local_path in local_files.items():
            if rel_path not in remote_files:
                # New file
                if local_path.is_dir():
                    actions.append(SyncAction(
                        "mkdir_remote",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        reason="new directory"
                    ))
                else:
                    actions.append(SyncAction(
                        "upload",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        size=local_path.stat().st_size,
                        reason="new file"
                    ))
            else:
                # Check if modified
                remote_file = remote_files[rel_path]
                if not local_path.is_dir() and self._is_file_modified(local_path, remote_file, profile):
                    actions.append(SyncAction(
                        "upload",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        size=local_path.stat().st_size,
                        reason="modified"
                    ))
        
        # Delete extra remote files
        if profile.delete_extra:
            for rel_path, remote_file in remote_files.items():
                if rel_path not in local_files:
                    if remote_file.is_directory:
                        actions.append(SyncAction(
                            "delete_remote",
                            remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                            reason="extra directory"
                        ))
                    else:
                        actions.append(SyncAction(
                            "delete_remote",
                            remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                            reason="extra file"
                        ))
        
        return actions
    
    def _plan_bidirectional_sync(
        self,
        local_files: Dict[str, Path],
        remote_files: Dict[str, RemoteFile],
        profile: SyncProfile,
    ) -> List[SyncAction]:
        """Plan bidirectional sync."""
        actions = []
        
        all_paths = set(local_files.keys()) | set(remote_files.keys())
        
        for rel_path in all_paths:
            local_path = local_files.get(rel_path)
            remote_file = remote_files.get(rel_path)
            
            if local_path and remote_file:
                # File exists in both - check which is newer
                if not local_path.is_dir() and not remote_file.is_directory:
                    local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime)
                    remote_mtime = remote_file.modified or datetime.min
                    
                    if local_mtime > remote_mtime:
                        actions.append(SyncAction(
                            "upload",
                            local_path=local_path,
                            remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                            size=local_path.stat().st_size,
                            reason="local newer"
                        ))
                    elif remote_mtime > local_mtime:
                        actions.append(SyncAction(
                            "download",
                            local_path=profile.local_path / rel_path,
                            remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                            size=remote_file.size,
                            reason="remote newer"
                        ))
            
            elif local_path:
                # Only exists locally - upload
                if local_path.is_dir():
                    actions.append(SyncAction(
                        "mkdir_remote",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        reason="local only"
                    ))
                else:
                    actions.append(SyncAction(
                        "upload",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        size=local_path.stat().st_size,
                        reason="local only"
                    ))
            
            elif remote_file:
                # Only exists remotely - download
                if remote_file.is_directory:
                    actions.append(SyncAction(
                        "mkdir_local",
                        local_path=profile.local_path / rel_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        reason="remote only"
                    ))
                else:
                    actions.append(SyncAction(
                        "download",
                        local_path=profile.local_path / rel_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        size=remote_file.size,
                        reason="remote only"
                    ))
        
        return actions
    
    def _plan_upload_sync(
        self,
        local_files: Dict[str, Path],
        remote_files: Dict[str, RemoteFile],
        profile: SyncProfile,
    ) -> List[SyncAction]:
        """Plan upload-only sync."""
        actions = []
        
        for rel_path, local_path in local_files.items():
            if rel_path not in remote_files or self._is_file_modified(
                local_path, remote_files.get(rel_path), profile
            ):
                if local_path.is_dir():
                    actions.append(SyncAction(
                        "mkdir_remote",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        reason="upload only"
                    ))
                else:
                    actions.append(SyncAction(
                        "upload",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        size=local_path.stat().st_size,
                        reason="upload only"
                    ))
        
        return actions
    
    def _plan_download_sync(
        self,
        local_files: Dict[str, Path],
        remote_files: Dict[str, RemoteFile],
        profile: SyncProfile,
    ) -> List[SyncAction]:
        """Plan download-only sync."""
        actions = []
        
        for rel_path, remote_file in remote_files.items():
            local_path = profile.local_path / rel_path
            
            if rel_path not in local_files or self._is_file_modified(
                local_files.get(rel_path), remote_file, profile
            ):
                if remote_file.is_directory:
                    actions.append(SyncAction(
                        "mkdir_local",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        reason="download only"
                    ))
                else:
                    actions.append(SyncAction(
                        "download",
                        local_path=local_path,
                        remote_path=f"{profile.remote_path.rstrip('/')}/{rel_path}",
                        size=remote_file.size,
                        reason="download only"
                    ))
        
        return actions
    
    def _is_file_modified(
        self,
        local_path: Optional[Path],
        remote_file: Optional[RemoteFile],
        profile: SyncProfile,
    ) -> bool:
        """Check if file is modified."""
        if not local_path or not remote_file:
            return True
        
        if local_path.is_dir() or remote_file.is_directory:
            return False
        
        if not local_path.exists():
            return True
        
        local_stat = local_path.stat()
        
        # Compare size
        if local_stat.st_size != remote_file.size:
            return True
        
        # Compare timestamp if available
        if profile.preserve_timestamps and remote_file.modified:
            local_mtime = datetime.fromtimestamp(local_stat.st_mtime)
            if abs((local_mtime - remote_file.modified).total_seconds()) > 2:
                return True
        
        return False
    
    async def _execute_actions(
        self,
        actions: List[SyncAction],
        session: ProtocolSession,
        result: SyncResult,
    ) -> None:
        """Execute sync actions."""
        total_actions = len(actions)
        
        for i, action in enumerate(actions):
            if self._cancelled:
                break
            
            try:
                await self._execute_action(action, session)
                result.actions_executed.append(action)
                
                # Emit progress
                if self._current_sync:
                    event_bus.sync_progress.emit(self._current_sync.id, i + 1, total_actions)
                
            except Exception as e:
                logger.error(f"Failed to execute action {action}: {e}")
                result.errors.append((action, str(e)))
    
    async def _execute_action(self, action: SyncAction, session: ProtocolSession) -> None:
        """Execute a single sync action."""
        if action.action == "upload":
            await session.upload(action.local_path, action.remote_path)
        
        elif action.action == "download":
            action.local_path.parent.mkdir(parents=True, exist_ok=True)
            await session.download(action.remote_path, action.local_path)
        
        elif action.action == "delete_local":
            if action.local_path.is_dir():
                action.local_path.rmdir()
            else:
                action.local_path.unlink()
        
        elif action.action == "delete_remote":
            remote_file = await session.stat(action.remote_path)
            if remote_file.is_directory:
                await session.rmdir(action.remote_path)
            else:
                await session.remove(action.remote_path)
        
        elif action.action == "mkdir_local":
            action.local_path.mkdir(parents=True, exist_ok=True)
        
        elif action.action == "mkdir_remote":
            await session.mkdir(action.remote_path, recursive=True)
    
    def cancel_sync(self) -> None:
        """Cancel current sync operation."""
        self._cancelled = True