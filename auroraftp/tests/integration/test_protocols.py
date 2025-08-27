"""Integration tests for protocol implementations."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from auroraftp.core.models import AuthMethod, Credential, ProtocolType, Site
from auroraftp.protocols import ProtocolFactory, ProtocolSession
from auroraftp.protocols.base import ConnectionError, FileOperationError


class TestSFTPIntegration:
    """Integration tests for SFTP protocol."""
    
    @pytest.fixture
    def sftp_site(self):
        """Create SFTP test site."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="testpass"
        )
        
        return Site(
            name="Test SFTP",
            protocol=ProtocolType.SFTP,
            hostname="localhost",
            port=2222,  # Docker SFTP port
            credential=credential
        )
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sftp_connection(self, sftp_site):
        """Test SFTP connection."""
        session = ProtocolFactory.create_session(sftp_site)
        
        async with session.session():
            assert session.is_connected
            
            # Test basic directory listing
            files = await session.list_directory("/")
            assert isinstance(files, list)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sftp_file_operations(self, sftp_site):
        """Test SFTP file operations."""
        session = ProtocolFactory.create_session(sftp_site)
        
        async with session.session():
            # Test directory creation
            test_dir = "/test_directory"
            await session.mkdir(test_dir)
            
            # Verify directory exists
            assert await session.exists(test_dir)
            
            # Test file upload
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write("Hello, SFTP!")
                local_file = Path(f.name)
            
            try:
                remote_file = f"{test_dir}/test_file.txt"
                await session.upload(local_file, remote_file)
                
                # Verify file exists
                assert await session.exists(remote_file)
                
                # Test file download
                download_file = local_file.with_suffix('.downloaded')
                await session.download(remote_file, download_file)
                
                # Verify content
                assert download_file.read_text() == "Hello, SFTP!"
                
                # Test file removal
                await session.remove(remote_file)
                assert not await session.exists(remote_file)
                
                # Test directory removal
                await session.rmdir(test_dir)
                assert not await session.exists(test_dir)
                
            finally:
                # Cleanup
                local_file.unlink(missing_ok=True)
                download_file.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sftp_directory_navigation(self, sftp_site):
        """Test SFTP directory navigation."""
        session = ProtocolFactory.create_session(sftp_site)
        
        async with session.session():
            # Get initial directory
            initial_dir = await session.get_working_directory()
            
            # Create test directory
            test_dir = "/nav_test"
            await session.mkdir(test_dir)
            
            try:
                # Change to test directory
                await session.change_directory(test_dir)
                current_dir = await session.get_working_directory()
                assert current_dir == test_dir
                
                # Change back
                await session.change_directory(initial_dir)
                current_dir = await session.get_working_directory()
                assert current_dir == initial_dir
                
            finally:
                # Cleanup
                await session.rmdir(test_dir)


class TestFTPIntegration:
    """Integration tests for FTP protocol."""
    
    @pytest.fixture
    def ftp_site(self):
        """Create FTP test site."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="testpass"
        )
        
        return Site(
            name="Test FTP",
            protocol=ProtocolType.FTP,
            hostname="localhost",
            port=2121,  # Docker FTP port
            credential=credential
        )
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ftp_connection(self, ftp_site):
        """Test FTP connection."""
        session = ProtocolFactory.create_session(ftp_site)
        
        async with session.session():
            assert session.is_connected
            
            # Test basic directory listing
            files = await session.list_directory("/")
            assert isinstance(files, list)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ftp_file_operations(self, ftp_site):
        """Test FTP file operations."""
        session = ProtocolFactory.create_session(ftp_site)
        
        async with session.session():
            # Test file upload
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write("Hello, FTP!")
                local_file = Path(f.name)
            
            try:
                remote_file = "/test_file_ftp.txt"
                await session.upload(local_file, remote_file)
                
                # Verify file exists
                assert await session.exists(remote_file)
                
                # Test file download
                download_file = local_file.with_suffix('.downloaded')
                await session.download(remote_file, download_file)
                
                # Verify content
                assert download_file.read_text() == "Hello, FTP!"
                
                # Test file removal
                await session.remove(remote_file)
                assert not await session.exists(remote_file)
                
            finally:
                # Cleanup
                local_file.unlink(missing_ok=True)
                download_file.unlink(missing_ok=True)


class TestProtocolFactory:
    """Test protocol factory."""
    
    def test_supported_protocols(self):
        """Test getting supported protocols."""
        protocols = ProtocolFactory.get_supported_protocols()
        
        assert "ftp" in protocols
        assert "ftps" in protocols
        assert "sftp" in protocols
    
    def test_create_sftp_session(self):
        """Test creating SFTP session."""
        credential = Credential(
            username="test",
            auth_method=AuthMethod.PASSWORD,
            password="test"
        )
        
        site = Site(
            name="Test",
            protocol=ProtocolType.SFTP,
            hostname="localhost",
            credential=credential
        )
        
        session = ProtocolFactory.create_session(site)
        assert isinstance(session, ProtocolSession)
        assert session.site == site
    
    def test_create_ftp_session(self):
        """Test creating FTP session."""
        credential = Credential(
            username="test",
            auth_method=AuthMethod.PASSWORD,
            password="test"
        )
        
        site = Site(
            name="Test",
            protocol=ProtocolType.FTP,
            hostname="localhost",
            credential=credential
        )
        
        session = ProtocolFactory.create_session(site)
        assert isinstance(session, ProtocolSession)
        assert session.site == site
    
    def test_unsupported_protocol(self):
        """Test unsupported protocol."""
        from auroraftp.protocols.base import ProtocolError
        
        credential = Credential(
            username="test",
            auth_method=AuthMethod.PASSWORD,
            password="test"
        )
        
        # Mock an unsupported protocol
        class UnsupportedProtocol:
            value = "unsupported"
        
        site = Site(
            name="Test",
            protocol=UnsupportedProtocol(),
            hostname="localhost",
            credential=credential
        )
        
        with pytest.raises(ProtocolError, match="Unsupported protocol"):
            ProtocolFactory.create_session(site)


@pytest.mark.integration
class TestProtocolErrorHandling:
    """Test protocol error handling."""
    
    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """Test connection failure handling."""
        credential = Credential(
            username="baduser",
            auth_method=AuthMethod.PASSWORD,
            password="badpass"
        )
        
        site = Site(
            name="Bad Site",
            protocol=ProtocolType.SFTP,
            hostname="nonexistent.example.com",
            port=22,
            credential=credential
        )
        
        session = ProtocolFactory.create_session(site)
        
        with pytest.raises(ConnectionError):
            async with session.session():
                pass
    
    @pytest.mark.asyncio
    async def test_file_not_found(self, sftp_site):
        """Test file not found error."""
        session = ProtocolFactory.create_session(sftp_site)
        
        async with session.session():
            with pytest.raises(FileOperationError):
                await session.stat("/nonexistent_file.txt")
    
    @pytest.mark.asyncio
    async def test_permission_denied(self, sftp_site):
        """Test permission denied error."""
        session = ProtocolFactory.create_session(sftp_site)
        
        async with session.session():
            # Try to create directory in root (should fail)
            with pytest.raises(FileOperationError):
                await session.mkdir("/root/test_dir")