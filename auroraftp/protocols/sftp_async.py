"""SFTP/SSH protocol implementation using asyncssh."""

import asyncio
import logging
import stat
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import asyncssh

from ..core.models import AuthMethod, FileType, RemoteFile
from .base import (
    AuthenticationError,
    ConnectionError,
    FileOperationError,
    ProtocolSession,
)

logger = logging.getLogger(__name__)


class SFTPSession(ProtocolSession):
    """SFTP session implementation using asyncssh."""
    
    def __init__(self, site):
        super().__init__(site)
        self.connection: Optional[asyncssh.SSHClientConnection] = None
        self.sftp: Optional[asyncssh.SFTPClient] = None
    
    async def connect(self) -> None:
        """Establish SFTP connection."""
        try:
            # Prepare authentication
            auth_options = {}
            
            if self.site.credential.auth_method == AuthMethod.PASSWORD:
                auth_options['password'] = self.site.credential.password
            elif self.site.credential.auth_method == AuthMethod.KEY_FILE:
                if self.site.credential.key_file:
                    auth_options['client_keys'] = [str(self.site.credential.key_file)]
                    if self.site.credential.passphrase:
                        auth_options['passphrase'] = self.site.credential.passphrase
            elif self.site.credential.auth_method == AuthMethod.SSH_AGENT:
                auth_options['agent_path'] = 'auto'
            
            # Connect to SSH server
            self.connection = await asyncssh.connect(
                host=self.site.hostname,
                port=self.site.port,
                username=self.site.credential.username,
                known_hosts=None,  # TODO: Implement known_hosts handling
                compression_algs=['zlib', 'none'] if self.site.ssh_compression else ['none'],
                **auth_options
            )
            
            # Start SFTP subsystem
            self.sftp = await self.connection.start_sftp_client()
            
            # Change to initial directory
            if self.site.remote_path:
                try:
                    await self.sftp.chdir(self.site.remote_path)
                    self._current_path = self.site.remote_path
                except Exception as e:
                    logger.warning(f"Could not change to initial directory: {e}")
            
            self._connected = True
            logger.info(f"SFTP connected to {self.site.hostname}:{self.site.port}")
            
        except asyncssh.Error as e:
            raise ConnectionError(f"SSH connection failed: {e}")
        except Exception as e:
            raise ConnectionError(f"Connection error: {e}")
    
    async def disconnect(self) -> None:
        """Close SFTP connection."""
        if self.sftp:
            self.sftp.exit()
            self.sftp = None
        
        if self.connection:
            self.connection.close()
            await self.connection.wait_closed()
            self.connection = None
        
        self._connected = False
        logger.info(f"SFTP disconnected from {self.site.hostname}")
    
    async def list_directory(self, path: str = ".") -> List[RemoteFile]:
        """List files in directory."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            files = []
            async for entry in self.sftp.scandir(path):
                attrs = entry.attrs
                
                # Determine file type
                file_type = FileType.FILE
                if stat.S_ISDIR(attrs.permissions):
                    file_type = FileType.DIRECTORY
                elif stat.S_ISLNK(attrs.permissions):
                    file_type = FileType.LINK
                
                # Convert timestamps
                modified = None
                if attrs.mtime:
                    modified = datetime.fromtimestamp(attrs.mtime)
                
                # Format permissions
                permissions = stat.filemode(attrs.permissions) if attrs.permissions else None
                
                remote_file = RemoteFile(
                    name=entry.filename,
                    path=f"{path.rstrip('/')}/{entry.filename}",
                    size=attrs.size or 0,
                    modified=modified,
                    permissions=permissions,
                    owner=str(attrs.uid) if attrs.uid else None,
                    group=str(attrs.gid) if attrs.gid else None,
                    file_type=file_type,
                    is_hidden=entry.filename.startswith('.'),
                )
                files.append(remote_file)
            
            return files
            
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to list directory: {e}")
    
    async def stat(self, path: str) -> RemoteFile:
        """Get file/directory information."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            attrs = await self.sftp.stat(path)
            
            # Determine file type
            file_type = FileType.FILE
            if stat.S_ISDIR(attrs.permissions):
                file_type = FileType.DIRECTORY
            elif stat.S_ISLNK(attrs.permissions):
                file_type = FileType.LINK
            
            # Convert timestamps
            modified = None
            if attrs.mtime:
                modified = datetime.fromtimestamp(attrs.mtime)
            
            # Format permissions
            permissions = stat.filemode(attrs.permissions) if attrs.permissions else None
            
            return RemoteFile(
                name=Path(path).name,
                path=path,
                size=attrs.size or 0,
                modified=modified,
                permissions=permissions,
                owner=str(attrs.uid) if attrs.uid else None,
                group=str(attrs.gid) if attrs.gid else None,
                file_type=file_type,
                is_hidden=Path(path).name.startswith('.'),
            )
            
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to stat {path}: {e}")
    
    async def exists(self, path: str) -> bool:
        """Check if file/directory exists."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.stat(path)
            return True
        except asyncssh.SFTPNoSuchFile:
            return False
        except asyncssh.Error:
            return False
    
    async def mkdir(self, path: str, recursive: bool = False) -> None:
        """Create directory."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            if recursive:
                await self.sftp.makedirs(path, exist_ok=True)
            else:
                await self.sftp.mkdir(path)
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to create directory {path}: {e}")
    
    async def rmdir(self, path: str) -> None:
        """Remove empty directory."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.rmdir(path)
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to remove directory {path}: {e}")
    
    async def remove(self, path: str) -> None:
        """Remove file."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.remove(path)
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to remove file {path}: {e}")
    
    async def rename(self, old_path: str, new_path: str) -> None:
        """Rename/move file or directory."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.rename(old_path, new_path)
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to rename {old_path} to {new_path}: {e}")
    
    async def download(
        self,
        remote_path: str,
        local_path: Union[str, Path],
        progress_callback: Optional[callable] = None,
    ) -> None:
        """Download file from remote to local."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Progress wrapper
            async def progress_wrapper(srcpath, dstpath, bytes_copied, total_bytes):
                if progress_callback:
                    progress_callback(bytes_copied, total_bytes)
            
            # Download with progress tracking
            await self.sftp.get(
                remote_path,
                str(local_path),
                progress_handler=progress_wrapper if progress_callback else None,
            )
            
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to download {remote_path}: {e}")
        except Exception as e:
            raise FileOperationError(f"Download error: {e}")
    
    async def upload(
        self,
        local_path: Union[str, Path],
        remote_path: str,
        progress_callback: Optional[callable] = None,
    ) -> None:
        """Upload file from local to remote."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            local_path = Path(local_path)
            if not local_path.exists():
                raise FileOperationError(f"Local file not found: {local_path}")
            
            # Progress wrapper
            async def progress_wrapper(srcpath, dstpath, bytes_copied, total_bytes):
                if progress_callback:
                    progress_callback(bytes_copied, total_bytes)
            
            # Upload with progress tracking
            await self.sftp.put(
                str(local_path),
                remote_path,
                progress_handler=progress_wrapper if progress_callback else None,
            )
            
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to upload {local_path}: {e}")
        except Exception as e:
            raise FileOperationError(f"Upload error: {e}")
    
    async def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.chmod(path, mode)
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to chmod {path}: {e}")
    
    async def chown(self, path: str, uid: int, gid: int) -> None:
        """Change file ownership."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.chown(path, uid, gid)
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to chown {path}: {e}")
    
    async def checksum(self, path: str, algorithm: str = "sha256") -> Optional[str]:
        """Calculate file checksum using SSH commands."""
        if not self._connected or not self.connection:
            raise ConnectionError("Not connected")
        
        try:
            # Map algorithm names to commands
            commands = {
                "md5": f"md5sum '{path}'",
                "sha1": f"sha1sum '{path}'",
                "sha256": f"sha256sum '{path}'",
                "sha512": f"sha512sum '{path}'",
            }
            
            if algorithm not in commands:
                return None
            
            result = await self.connection.run(commands[algorithm], check=True)
            if result.stdout:
                # Extract checksum from output (format: "checksum filename")
                return result.stdout.split()[0]
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to calculate checksum for {path}: {e}")
            return None
    
    async def change_directory(self, path: str) -> None:
        """Change current directory."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            await self.sftp.chdir(path)
            self._current_path = path
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to change directory to {path}: {e}")
    
    async def get_working_directory(self) -> str:
        """Get current working directory."""
        if not self._connected or not self.sftp:
            raise ConnectionError("Not connected")
        
        try:
            return await self.sftp.getcwd()
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to get working directory: {e}")
    
    async def execute_command(self, command: str) -> str:
        """Execute command on remote server."""
        if not self._connected or not self.connection:
            raise ConnectionError("Not connected")
        
        try:
            result = await self.connection.run(command, check=True)
            return result.stdout
        except asyncssh.Error as e:
            raise FileOperationError(f"Failed to execute command: {e}")


# Register SFTP protocols
from .base import ProtocolFactory

ProtocolFactory.register("sftp", SFTPSession)
ProtocolFactory.register("ssh", SFTPSession)  # Alias for SFTP