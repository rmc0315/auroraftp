"""Tests for core models."""

import pytest
from datetime import datetime
from pathlib import Path
from uuid import UUID

from auroraftp.core.models import (
    AuthMethod,
    Credential,
    ProtocolType,
    Site,
    TransferDirection,
    TransferItem,
    TransferStatus,
)


class TestCredential:
    """Test Credential model."""
    
    def test_password_credential(self):
        """Test password-based credential."""
        cred = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="secret123"
        )
        
        assert cred.username == "testuser"
        assert cred.auth_method == AuthMethod.PASSWORD
        assert cred.password == "secret123"
        assert cred.key_file is None
        assert not cred.use_agent
    
    def test_key_file_credential(self):
        """Test key file-based credential."""
        key_path = Path("/home/user/.ssh/id_rsa")
        
        cred = Credential(
            username="testuser",
            auth_method=AuthMethod.KEY_FILE,
            key_file=key_path,
            passphrase="keypassword"
        )
        
        assert cred.username == "testuser"
        assert cred.auth_method == AuthMethod.KEY_FILE
        assert cred.key_file == key_path
        assert cred.passphrase == "keypassword"
        assert cred.password is None
    
    def test_ssh_agent_credential(self):
        """Test SSH agent credential."""
        cred = Credential(
            username="testuser",
            auth_method=AuthMethod.SSH_AGENT,
            use_agent=True
        )
        
        assert cred.username == "testuser"
        assert cred.auth_method == AuthMethod.SSH_AGENT
        assert cred.use_agent
        assert cred.password is None
        assert cred.key_file is None


class TestSite:
    """Test Site model."""
    
    def test_basic_site(self):
        """Test basic site configuration."""
        credential = Credential(
            username="user",
            auth_method=AuthMethod.PASSWORD,
            password="pass"
        )
        
        site = Site(
            name="Test Server",
            protocol=ProtocolType.SFTP,
            hostname="example.com",
            port=22,
            credential=credential
        )
        
        assert site.name == "Test Server"
        assert site.protocol == ProtocolType.SFTP
        assert site.hostname == "example.com"
        assert site.port == 22
        assert isinstance(site.id, UUID)
        assert isinstance(site.created_at, datetime)
    
    def test_default_port(self):
        """Test default port property."""
        credential = Credential(username="user", auth_method=AuthMethod.PASSWORD)
        
        ftp_site = Site(
            name="FTP",
            protocol=ProtocolType.FTP,
            hostname="ftp.example.com",
            credential=credential
        )
        assert ftp_site.default_port == 21
        
        sftp_site = Site(
            name="SFTP", 
            protocol=ProtocolType.SFTP,
            hostname="sftp.example.com",
            credential=credential
        )
        assert sftp_site.default_port == 22
    
    def test_port_validation(self):
        """Test port number validation."""
        credential = Credential(username="user", auth_method=AuthMethod.PASSWORD)
        
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            Site(
                name="Invalid Port",
                protocol=ProtocolType.SFTP,
                hostname="example.com",
                port=0,
                credential=credential
            )
        
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            Site(
                name="Invalid Port",
                protocol=ProtocolType.SFTP,
                hostname="example.com", 
                port=65536,
                credential=credential
            )
    
    def test_site_with_paths(self):
        """Test site with local and remote paths."""
        credential = Credential(username="user", auth_method=AuthMethod.PASSWORD)
        
        site = Site(
            name="Test",
            protocol=ProtocolType.SFTP,
            hostname="example.com",
            credential=credential,
            local_path=Path("/home/user/downloads"),
            remote_path="/var/www/html"
        )
        
        assert site.local_path == Path("/home/user/downloads")
        assert site.remote_path == "/var/www/html"


class TestTransferItem:
    """Test TransferItem model."""
    
    def test_upload_transfer(self):
        """Test upload transfer item."""
        from uuid import uuid4
        site_id = uuid4()
        local_path = Path("/home/user/file.txt")
        
        transfer = TransferItem(
            site_id=site_id,
            direction=TransferDirection.UPLOAD,
            local_path=local_path,
            remote_path="/remote/file.txt",
            size=1024
        )
        
        assert transfer.site_id == site_id
        assert transfer.direction == TransferDirection.UPLOAD
        assert transfer.local_path == local_path
        assert transfer.remote_path == "/remote/file.txt"
        assert transfer.size == 1024
        assert transfer.status == TransferStatus.PENDING
        assert isinstance(transfer.id, UUID)
        assert isinstance(transfer.created_at, datetime)
    
    def test_download_transfer(self):
        """Test download transfer item."""
        from uuid import uuid4
        site_id = uuid4()
        local_path = Path("/home/user/downloaded.txt")
        
        transfer = TransferItem(
            site_id=site_id,
            direction=TransferDirection.DOWNLOAD,
            local_path=local_path,
            remote_path="/remote/source.txt",
            size=2048
        )
        
        assert transfer.direction == TransferDirection.DOWNLOAD
        assert transfer.size == 2048
    
    def test_progress_calculation(self):
        """Test progress calculation."""
        from uuid import uuid4
        transfer = TransferItem(
            site_id=uuid4(),
            direction=TransferDirection.UPLOAD,
            local_path=Path("file.txt"),
            remote_path="file.txt",
            size=1000,
            transferred=250
        )
        
        assert transfer.progress == 0.25
        
        # Test edge cases
        transfer.size = 0
        assert transfer.progress == 0.0
        
        transfer.size = 1000
        transfer.transferred = 1500  # More than size
        assert transfer.progress == 1.0
    
    def test_transfer_status_properties(self):
        """Test transfer status properties."""
        from uuid import uuid4
        transfer = TransferItem(
            site_id=uuid4(),
            direction=TransferDirection.UPLOAD,
            local_path=Path("file.txt"),
            remote_path="file.txt"
        )
        
        # Test completion status
        assert not transfer.is_complete
        transfer.status = TransferStatus.COMPLETED
        assert transfer.is_complete
        
        # Test retry capability
        transfer.status = TransferStatus.FAILED
        transfer.retry_count = 0
        transfer.max_retries = 3
        assert transfer.can_retry
        
        transfer.retry_count = 3
        assert not transfer.can_retry