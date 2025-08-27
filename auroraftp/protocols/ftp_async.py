"""FTP/FTPS protocol implementation using aioftp."""

import asyncio
import logging
import ssl
from pathlib import Path
from typing import List, Optional, Union

import aioftp

from ..core.models import AuthMethod, FileType, ProtocolType, RemoteFile
from .base import (
    AuthenticationError,
    ConnectionError,
    FileOperationError,
    ProtocolSession,
)

logger = logging.getLogger(__name__)


class FTPSession(ProtocolSession):
    """FTP/FTPS session implementation."""
    
    def __init__(self, site):
        super().__init__(site)
        self.client: Optional[aioftp.Client] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for FTPS."""
        if self.site.protocol != ProtocolType.FTPS:
            return None
        
        context = ssl.create_default_context()
        
        if not self.site.verify_cert:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        return context
    
    async def connect(self) -> None:
        """Establish FTP/FTPS connection."""
        try:
            if self.site.protocol == ProtocolType.FTPS:
                self._ssl_context = self._create_ssl_context()
            
            # Create client with passive mode setting
            client_kwargs = {}
            if not self.site.passive_mode:
                # For active mode, disable passive commands
                client_kwargs['passive_commands'] = ()
            
            self.client = aioftp.Client(**client_kwargs)
            
            # Configure SSL for FTPS
            if self.site.protocol == ProtocolType.FTPS:
                if self.site.tls_implicit:
                    # Implicit FTPS
                    await self.client.connect(
                        host=self.site.hostname,
                        port=self.site.port,
                        ssl=self._ssl_context,
                    )
                else:
                    # Explicit FTPS
                    await self.client.connect(
                        host=self.site.hostname,
                        port=self.site.port,
                    )
                    await self.client.auth(ssl=self._ssl_context)
            else:
                # Plain FTP
                await self.client.connect(
                    host=self.site.hostname,
                    port=self.site.port,
                )
            
            # Authenticate
            if self.site.credential.auth_method == AuthMethod.PASSWORD:
                await self.client.login(
                    user=self.site.credential.username,
                    password=self.site.credential.password or "",
                )
            else:
                raise AuthenticationError(
                    f"Unsupported auth method: {self.site.credential.auth_method}"
                )
            
            # Passive mode is handled during client creation
            
            # Change to initial directory
            if self.site.remote_path:
                try:
                    await self.client.change_directory(self.site.remote_path)
                    self._current_path = self.site.remote_path
                except Exception as e:
                    logger.warning(f"Could not change to initial directory: {e}")
            
            self._connected = True
            logger.info(f"Connected to {self.site.hostname}:{self.site.port}")
            
        except aioftp.AIOFTPException as e:
            raise ConnectionError(f"FTP connection failed: {e}")
        except Exception as e:
            raise ConnectionError(f"Connection error: {e}")
    
    async def disconnect(self) -> None:
        """Close FTP connection."""
        if self.client and self._connected:
            try:
                await self.client.quit()
            except Exception:
                pass  # Ignore errors during disconnect
            finally:
                self.client = None
                self._connected = False
                logger.info(f"Disconnected from {self.site.hostname}")
    
    async def list_directory(self, path: str = ".") -> List[RemoteFile]:
        """List files in directory."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            files = []
            logger.info(f"Starting directory listing for path: {path}")
            
            # Use a more robust approach with better error handling
            try:
                try:
                    list_iterator = self.client.list(path, recursive=False)
                except Exception as e:
                    logger.error(f"Error calling self.client.list for path '{path}': {e}")
                    return []

                file_count = 0
                async for path_info, stat_info in list_iterator:
                    file_count += 1
                    logger.info(f"Raw path_info: {path_info}, Raw stat_info: {stat_info}")
                    try:
                        # Handle dict-based stat_info from some FTP servers (e.g., Bluehost)
                        if isinstance(stat_info, dict):
                            stat_type = stat_info.get('type', '').lower()
                            if 'dir' in stat_type:
                                file_type = FileType.DIRECTORY
                            elif 'file' in stat_type:
                                file_type = FileType.FILE
                            elif 'slink' in stat_type:
                                file_type = FileType.LINK
                            else:
                                file_type = FileType.UNKNOWN

                            size_str = stat_info.get('size') or stat_info.get('sizd', '0')
                            size = int(size_str)

                            modified_str = stat_info.get('modify')
                            modified = None
                            if modified_str:
                                try:
                                    from datetime import datetime
                                    modified = datetime.strptime(modified_str, '%Y%m%d%H%M%S')
                                except (ValueError, TypeError):
                                    modified = None
                            
                            permissions = stat_info.get('unix.mode') or ''

                        # Handle object-based stat_info from other servers
                        else:
                            file_type = FileType.DIRECTORY if stat_info.is_dir() else FileType.FILE
                            size = getattr(stat_info, 'st_size', 0)
                            modified = None
                            if hasattr(stat_info, 'st_mtime'):
                                try:
                                    from datetime import datetime
                                    modified = datetime.fromtimestamp(stat_info.st_mtime)
                                except (OSError, ValueError):
                                    modified = None
                            
                            permissions = None
                            if hasattr(stat_info, 'st_mode'):
                                try:
                                    import stat
                                    permissions = stat.filemode(stat_info.st_mode)
                                except (OSError, ValueError):
                                    permissions = None

                        # Create remote file object
                        remote_file = RemoteFile(
                            name=path_info.name if path_info else "unknown",
                            path=str(path_info) if path_info else path,
                            size=size,
                            modified=modified,
                            permissions=permissions,
                            file_type=file_type,
                            is_hidden=path_info.name.startswith('.') if path_info else False,
                        )
                        files.append(remote_file)
                        logger.debug(f"Added file: {remote_file.name} ({remote_file.file_type})")

                    except Exception as e:
                        logger.warning(f"Error processing file entry {file_count}: {e}", exc_info=True)
                        # Skip this file but continue with others
                        continue
                
                logger.info(f"Processed {file_count} raw entries, created {len(files)} file objects")
                        
            except Exception as e:
                logger.error(f"Error during directory listing iteration: {e}")
                # If we can't list, return empty list rather than crash
                return []
            
            logger.info(f"Returning {len(files)} files from directory listing")
            return files
            
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to list directory: {e}")
    
    async def stat(self, path: str) -> RemoteFile:
        """Get file/directory information."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            stat_info = await self.client.stat(path)

            # Handle dict-based stat_info from some FTP servers
            if isinstance(stat_info, dict):
                stat_type = stat_info.get('type', '').lower()
                if 'dir' in stat_type:
                    file_type = FileType.DIRECTORY
                elif 'file' in stat_type:
                    file_type = FileType.FILE
                elif 'slink' in stat_type:
                    file_type = FileType.LINK
                else:
                    file_type = FileType.UNKNOWN

                size_str = stat_info.get('size') or stat_info.get('sizd', '0')
                size = int(size_str)

                modified_str = stat_info.get('modify')
                modified = None
                if modified_str:
                    try:
                        from datetime import datetime
                        modified = datetime.strptime(modified_str, '%Y%m%d%H%M%S')
                    except (ValueError, TypeError):
                        modified = None
                
                permissions = stat_info.get('unix.mode') or ''

            # Handle object-based stat_info from other servers
            else:
                file_type = FileType.DIRECTORY if stat_info.is_dir() else FileType.FILE
                size = getattr(stat_info, 'st_size', 0)
                modified = None
                if hasattr(stat_info, 'st_mtime'):
                    try:
                        from datetime import datetime
                        modified = datetime.fromtimestamp(stat_info.st_mtime)
                    except (OSError, ValueError):
                        modified = None
                
                permissions = None
                if hasattr(stat_info, 'st_mode'):
                    try:
                        import stat
                        permissions = stat.filemode(stat_info.st_mode)
                    except (OSError, ValueError):
                        permissions = None

            return RemoteFile(
                name=Path(path).name,
                path=path,
                size=size,
                modified=modified,
                permissions=permissions,
                file_type=file_type,
                is_hidden=Path(path).name.startswith('.'),
            )
            
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to stat {path}: {e}")
    
    async def exists(self, path: str) -> bool:
        """Check if file/directory exists."""
        try:
            await self.stat(path)
            return True
        except FileOperationError:
            return False
    
    async def mkdir(self, path: str, recursive: bool = False) -> None:
        """Create directory."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            if recursive:
                # Create parent directories if needed
                parts = Path(path).parts
                current = ""
                for part in parts:
                    current = current + "/" + part if current else part
                    if not await self.exists(current):
                        await self.client.make_directory(current)
            else:
                await self.client.make_directory(path)
                
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to create directory {path}: {e}")
    
    async def rmdir(self, path: str) -> None:
        """Remove empty directory."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            await self.client.remove_directory(path)
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to remove directory {path}: {e}")
    
    async def remove(self, path: str) -> None:
        """Remove file."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            await self.client.remove_file(path)
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to remove file {path}: {e}")
    
    async def rename(self, old_path: str, new_path: str) -> None:
        """Rename/move file or directory."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            await self.client.rename(old_path, new_path)
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to rename {old_path} to {new_path}: {e}")
    
    async def download(
        self,
        remote_path: str,
        local_path: Union[str, Path],
        progress_callback: Optional[callable] = None,
    ) -> None:
        """Download file from remote to local."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get file size for progress tracking
            stat_info = await self.stat(remote_path)
            total_size = stat_info.size
            transferred = 0
            
            async with self.client.download_stream(remote_path) as stream:
                with open(local_path, 'wb') as f:
                    while True:
                        chunk = await stream.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        transferred += len(chunk)
                        
                        if progress_callback:
                            progress_callback(transferred, total_size)
            
        except aioftp.AIOFTPException as e:
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
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            local_path = Path(local_path)
            if not local_path.exists():
                raise FileOperationError(f"Local file not found: {local_path}")
            
            total_size = local_path.stat().st_size
            transferred = 0
            
            async with self.client.upload_stream(remote_path) as stream:
                with open(local_path, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        
                        await stream.write(chunk)
                        transferred += len(chunk)
                        
                        if progress_callback:
                            progress_callback(transferred, total_size)
            
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to upload {local_path}: {e}")
        except Exception as e:
            raise FileOperationError(f"Upload error: {e}")
    
    async def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            # FTP doesn't have a standard chmod, try SITE CHMOD
            await self.client.command(f"SITE CHMOD {oct(mode)[2:]} {path}")
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to chmod {path}: {e}")
    
    async def change_directory(self, path: str) -> None:
        """Change current directory."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            await self.client.change_directory(path)
            self._current_path = path
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to change directory to {path}: {e}")
    
    async def get_working_directory(self) -> str:
        """Get current working directory."""
        if not self._connected or not self.client:
            raise ConnectionError("Not connected")
        
        try:
            return await self.client.get_current_directory()
        except aioftp.AIOFTPException as e:
            raise FileOperationError(f"Failed to get working directory: {e}")


# Register FTP protocols
from .base import ProtocolFactory

ProtocolFactory.register("ftp", FTPSession)
ProtocolFactory.register("ftps", FTPSession)