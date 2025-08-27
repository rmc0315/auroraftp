"""Abstract base protocol interface."""

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, List, Optional, Union

from ..core.models import RemoteFile, Site


class ProtocolError(Exception):
    """Base protocol error."""
    pass


class ConnectionError(ProtocolError):
    """Connection related errors."""
    pass


class AuthenticationError(ProtocolError):
    """Authentication related errors."""
    pass


class FileOperationError(ProtocolError):
    """File operation related errors."""
    pass


class ProtocolSession(ABC):
    """Abstract protocol session interface."""
    
    def __init__(self, site: Site):
        self.site = site
        self._connected = False
        self._current_path = "/"
    
    @property
    def is_connected(self) -> bool:
        """Check if session is connected."""
        return self._connected
    
    @property
    def current_path(self) -> str:
        """Get current remote path."""
        return self._current_path
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to remote server."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to remote server."""
        pass
    
    @abstractmethod
    async def list_directory(self, path: str = ".") -> List[RemoteFile]:
        """List files in directory."""
        pass
    
    @abstractmethod
    async def stat(self, path: str) -> RemoteFile:
        """Get file/directory information."""
        pass
    
    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if file/directory exists."""
        pass
    
    @abstractmethod
    async def mkdir(self, path: str, recursive: bool = False) -> None:
        """Create directory."""
        pass
    
    @abstractmethod
    async def rmdir(self, path: str) -> None:
        """Remove empty directory."""
        pass
    
    @abstractmethod
    async def remove(self, path: str) -> None:
        """Remove file."""
        pass
    
    @abstractmethod
    async def rename(self, old_path: str, new_path: str) -> None:
        """Rename/move file or directory."""
        pass
    
    @abstractmethod
    async def download(
        self,
        remote_path: str,
        local_path: Union[str, Path],
        progress_callback: Optional[callable] = None,
    ) -> None:
        """Download file from remote to local."""
        pass
    
    @abstractmethod
    async def upload(
        self,
        local_path: Union[str, Path],
        remote_path: str,
        progress_callback: Optional[callable] = None,
    ) -> None:
        """Upload file from local to remote."""
        pass
    
    @abstractmethod
    async def chmod(self, path: str, mode: int) -> None:
        """Change file permissions."""
        pass
    
    async def chown(self, path: str, uid: int, gid: int) -> None:
        """Change file ownership. Default implementation raises NotImplementedError."""
        raise NotImplementedError("chown not supported by this protocol")
    
    async def checksum(self, path: str, algorithm: str = "md5") -> Optional[str]:
        """Calculate file checksum. Default implementation returns None."""
        return None
    
    async def change_directory(self, path: str) -> None:
        """Change current directory."""
        # Validate path exists and is directory
        file_info = await self.stat(path)
        if not file_info.is_directory:
            raise FileOperationError(f"Not a directory: {path}")
        
        self._current_path = path
    
    async def get_working_directory(self) -> str:
        """Get current working directory."""
        return self._current_path
    
    @asynccontextmanager
    async def session(self) -> AsyncIterator["ProtocolSession"]:
        """Async context manager for session lifecycle."""
        try:
            await self.connect()
            yield self
        finally:
            if self._connected:
                await self.disconnect()


class ProtocolFactory:
    """Factory for creating protocol sessions."""
    
    _protocols = {}
    
    @classmethod
    def register(cls, protocol_type: str, session_class: type) -> None:
        """Register a protocol implementation."""
        cls._protocols[protocol_type.lower()] = session_class
    
    @classmethod
    def create_session(cls, site: Site) -> ProtocolSession:
        """Create a protocol session for the given site."""
        protocol_type = site.protocol.value.lower()
        
        if protocol_type not in cls._protocols:
            raise ProtocolError(f"Unsupported protocol: {protocol_type}")
        
        session_class = cls._protocols[protocol_type]
        return session_class(site)
    
    @classmethod
    def get_supported_protocols(cls) -> List[str]:
        """Get list of supported protocols."""
        return list(cls._protocols.keys())