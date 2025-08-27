"""Core data models for AuroraFTP."""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


class ProtocolType(str, Enum):
    """Supported protocol types."""
    FTP = "ftp"
    FTPS = "ftps"
    SFTP = "sftp"


class AuthMethod(str, Enum):
    """Authentication methods."""
    PASSWORD = "password"
    KEY_FILE = "key_file"
    SSH_AGENT = "ssh_agent"
    INTERACTIVE = "interactive"


class TransferDirection(str, Enum):
    """Transfer direction."""
    UPLOAD = "upload"
    DOWNLOAD = "download"


class TransferStatus(str, Enum):
    """Transfer status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncMode(str, Enum):
    """Synchronization modes."""
    MIRROR = "mirror"  # One-way sync
    BIDIRECTIONAL = "bidirectional"  # Two-way sync
    UPLOAD_ONLY = "upload_only"
    DOWNLOAD_ONLY = "download_only"


class FileType(str, Enum):
    """File types."""
    FILE = "file"
    DIRECTORY = "directory"
    LINK = "link"
    UNKNOWN = "unknown"


class Credential(BaseModel):
    """Authentication credentials."""
    username: str
    auth_method: AuthMethod = AuthMethod.PASSWORD
    password: Optional[str] = None
    key_file: Optional[Path] = None
    passphrase: Optional[str] = None
    use_agent: bool = False

    class Config:
        arbitrary_types_allowed = True


class Site(BaseModel):
    """Site configuration."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    protocol: ProtocolType
    hostname: str
    port: int = Field(default=21)
    credential: Credential
    
    # Connection settings
    passive_mode: bool = True
    timeout: int = 30
    keepalive_interval: int = 60
    max_connections: int = 5
    
    # Default paths
    local_path: Optional[Path] = None
    remote_path: Optional[str] = None
    
    # Organization
    folder: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    color: Optional[str] = None
    notes: Optional[str] = None
    
    # TLS/SSL settings
    tls_explicit: bool = True
    tls_implicit: bool = False
    verify_cert: bool = True
    
    # SSH settings
    ssh_compression: bool = True
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_connected: Optional[datetime] = None
    last_local_path: Optional[Path] = None
    last_remote_path: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @validator('port')
    def validate_port(cls, v: int, values: Dict[str, Any]) -> int:
        """Validate port number."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @property
    def default_port(self) -> int:
        """Get default port for protocol."""
        defaults = {
            ProtocolType.FTP: 21,
            ProtocolType.FTPS: 21,
            ProtocolType.SFTP: 22,
        }
        return defaults.get(self.protocol, 21)


class RemoteFile(BaseModel):
    """Remote file information."""
    name: str
    path: str
    size: int = 0
    modified: Optional[datetime] = None
    permissions: Optional[str] = None
    owner: Optional[str] = None
    group: Optional[str] = None
    file_type: FileType = FileType.FILE
    is_hidden: bool = False

    @property
    def is_directory(self) -> bool:
        """Check if this is a directory."""
        return self.file_type == FileType.DIRECTORY

    @property
    def extension(self) -> str:
        """Get file extension."""
        return Path(self.name).suffix.lower()


class TransferItem(BaseModel):
    """Transfer queue item."""
    id: UUID = Field(default_factory=uuid4)
    site_id: UUID
    direction: TransferDirection
    local_path: Path
    remote_path: str
    size: int = 0
    transferred: int = 0
    status: TransferStatus = TransferStatus.PENDING
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # Transfer options
    overwrite_mode: str = "ask"  # ask, overwrite, skip, rename
    verify_checksum: bool = True
    preserve_timestamp: bool = True
    create_directories: bool = True

    class Config:
        arbitrary_types_allowed = True

    @property
    def progress(self) -> float:
        """Calculate transfer progress (0.0 to 1.0)."""
        if self.size == 0:
            return 0.0
        return min(self.transferred / self.size, 1.0)

    @property
    def is_complete(self) -> bool:
        """Check if transfer is complete."""
        return self.status == TransferStatus.COMPLETED

    @property
    def can_retry(self) -> bool:
        """Check if transfer can be retried."""
        return (
            self.status == TransferStatus.FAILED
            and self.retry_count < self.max_retries
        )


class SyncProfile(BaseModel):
    """Folder synchronization profile."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    site_id: UUID
    local_path: Path
    remote_path: str
    mode: SyncMode = SyncMode.MIRROR
    
    # Filters
    include_patterns: List[str] = Field(default_factory=list)
    exclude_patterns: List[str] = Field(default_factory=list)
    
    # Options
    delete_extra: bool = False
    preserve_timestamps: bool = True
    follow_symlinks: bool = False
    verify_checksums: bool = True
    dry_run: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_sync: Optional[datetime] = None

    class Config:
        arbitrary_types_allowed = True


class SessionInfo(BaseModel):
    """Active session information."""
    site_id: UUID
    site: Site
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    current_remote_path: str = "/"
    current_local_path: Path = Field(default_factory=Path.cwd)
    is_connected: bool = False
    server_info: Optional[str] = None
    protocol_version: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


class LogEntry(BaseModel):
    """Log entry model."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str
    site_id: Optional[UUID] = None
    message: str
    details: Optional[Dict[str, Any]] = None

    class Config:
        arbitrary_types_allowed = True


class AppConfig(BaseModel):
    """Application configuration."""
    # UI settings
    theme: str = "system"  # light, dark, system
    language: str = "en"
    window_geometry: Optional[Dict[str, int]] = None
    
    # Transfer settings
    default_transfer_mode: str = "binary"
    max_concurrent_transfers: int = 3
    chunk_size: int = 65536  # 64KB
    retry_delay: int = 5  # seconds
    bandwidth_limit: Optional[int] = None  # bytes/sec
    
    # Security settings
    store_passwords: bool = True
    verify_ssl_certs: bool = True
    ssh_compression: bool = True
    
    # Logging
    log_level: str = "INFO"
    log_file_size: int = 10 * 1024 * 1024  # 10MB
    log_file_count: int = 5
    
    # Advanced
    timeout_connect: int = 30
    timeout_data: int = 60
    keepalive_interval: int = 60
    temp_directory: Optional[Path] = None

    class Config:
        arbitrary_types_allowed = True