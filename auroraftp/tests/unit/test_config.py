"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from auroraftp.core.config import ConfigManager, CredentialStore
from auroraftp.core.models import AuthMethod, Credential, ProtocolType, Site


class TestCredentialStore:
    """Test credential storage."""
    
    def test_encrypted_storage(self):
        """Test encrypted credential storage."""
        store = CredentialStore(use_keyring=False)
        store.set_master_password("test_password")
        
        # Test data
        site_id = "test_site"
        credential_data = {
            "username": "testuser",
            "password": "secret123",
            "auth_method": "password"
        }
        
        # Store credential
        success = store.store_credential(site_id, credential_data)
        assert success
        
        # Retrieve credential
        retrieved = store.get_credential(site_id)
        assert retrieved == credential_data
        
        # Delete credential
        success = store.delete_credential(site_id)
        assert success
        
        # Verify deletion
        retrieved = store.get_credential(site_id)
        assert retrieved is None
    
    @patch('keyring.set_password')
    @patch('keyring.get_password')
    @patch('keyring.delete_password')
    def test_keyring_storage(self, mock_delete, mock_get, mock_set):
        """Test keyring credential storage."""
        store = CredentialStore(use_keyring=True)
        
        # Mock keyring responses
        mock_set.return_value = None
        mock_get.return_value = '{"username": "testuser", "password": "secret123"}'
        mock_delete.return_value = None
        
        site_id = "test_site"
        credential_data = {"username": "testuser", "password": "secret123"}
        
        # Store credential
        success = store.store_credential(site_id, credential_data)
        assert success
        mock_set.assert_called_once()
        
        # Retrieve credential
        retrieved = store.get_credential(site_id)
        assert retrieved == credential_data
        mock_get.assert_called_once()
        
        # Delete credential
        success = store.delete_credential(site_id)
        assert success
        mock_delete.assert_called_once()


class TestConfigManager:
    """Test configuration manager."""
    
    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager()
        
        # Override directories to use temp dir
        self.config_manager.config_dir = Path(self.temp_dir) / "config"
        self.config_manager.data_dir = Path(self.temp_dir) / "data"
        self.config_manager.log_dir = Path(self.temp_dir) / "logs"
        
        # Create directories
        for directory in [self.config_manager.config_dir, 
                         self.config_manager.data_dir, 
                         self.config_manager.log_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Update file paths
        self.config_manager.config_file = self.config_manager.config_dir / "config.json"
        self.config_manager.sites_file = self.config_manager.config_dir / "sites.json"
        self.config_manager.sync_profiles_file = self.config_manager.config_dir / "sync_profiles.json"
    
    def teardown_method(self):
        """Cleanup test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_load_default_config(self):
        """Test loading default configuration."""
        config = self.config_manager.load_config()
        
        assert config.theme == "system"
        assert config.max_concurrent_transfers == 3
        assert config.log_level == "INFO"
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        # Load and modify config
        config = self.config_manager.load_config()
        config.theme = "dark"
        config.max_concurrent_transfers = 5
        
        # Save config
        self.config_manager.save_config()
        
        # Create new manager and load
        new_manager = ConfigManager()
        new_manager.config_dir = self.config_manager.config_dir
        new_manager.config_file = self.config_manager.config_file
        
        loaded_config = new_manager.load_config()
        assert loaded_config.theme == "dark"
        assert loaded_config.max_concurrent_transfers == 5
    
    def test_add_and_load_site(self):
        """Test adding and loading sites."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="secret123"
        )
        
        site = Site(
            name="Test Server",
            protocol=ProtocolType.SFTP,
            hostname="test.example.com",
            port=22,
            credential=credential
        )
        
        # Add site
        self.config_manager.add_site(site)
        
        # Load sites
        sites = self.config_manager.load_sites()
        
        assert len(sites) == 1
        site_id = str(site.id)
        assert site_id in sites
        
        loaded_site = sites[site_id]
        assert loaded_site.name == "Test Server"
        assert loaded_site.hostname == "test.example.com"
        assert loaded_site.credential.username == "testuser"
    
    def test_update_site(self):
        """Test updating a site."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="secret123"
        )
        
        site = Site(
            name="Test Server",
            protocol=ProtocolType.SFTP,
            hostname="test.example.com",
            credential=credential
        )
        
        # Add site
        self.config_manager.add_site(site)
        
        # Update site
        site.name = "Updated Server"
        site.hostname = "updated.example.com"
        self.config_manager.update_site(site)
        
        # Load and verify
        sites = self.config_manager.load_sites()
        loaded_site = sites[str(site.id)]
        assert loaded_site.name == "Updated Server"
        assert loaded_site.hostname == "updated.example.com"
    
    def test_delete_site(self):
        """Test deleting a site."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="secret123"
        )
        
        site = Site(
            name="Test Server",
            protocol=ProtocolType.SFTP,
            hostname="test.example.com",
            credential=credential
        )
        
        # Add site
        self.config_manager.add_site(site)
        
        # Verify it exists
        sites = self.config_manager.load_sites()
        assert len(sites) == 1
        
        # Delete site
        self.config_manager.delete_site(site.id)
        
        # Verify deletion
        sites = self.config_manager.load_sites()
        assert len(sites) == 0
    
    def test_get_sites_by_folder(self):
        """Test getting sites by folder."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="secret123"
        )
        
        # Create sites in different folders
        site1 = Site(
            name="Site 1",
            protocol=ProtocolType.SFTP,
            hostname="site1.com",
            credential=credential,
            folder="work"
        )
        
        site2 = Site(
            name="Site 2",
            protocol=ProtocolType.SFTP,
            hostname="site2.com",
            credential=credential,
            folder="work"
        )
        
        site3 = Site(
            name="Site 3",
            protocol=ProtocolType.SFTP,
            hostname="site3.com",
            credential=credential,
            folder="personal"
        )
        
        # Add sites
        for site in [site1, site2, site3]:
            self.config_manager.add_site(site)
        
        # Test folder filtering
        work_sites = self.config_manager.get_sites_by_folder("work")
        assert len(work_sites) == 2
        
        personal_sites = self.config_manager.get_sites_by_folder("personal")
        assert len(personal_sites) == 1
        
        none_sites = self.config_manager.get_sites_by_folder(None)
        assert len(none_sites) == 0
    
    def test_export_import_sites(self):
        """Test exporting and importing sites."""
        credential = Credential(
            username="testuser",
            auth_method=AuthMethod.PASSWORD,
            password="secret123"
        )
        
        site = Site(
            name="Test Server",
            protocol=ProtocolType.SFTP,
            hostname="test.example.com",
            credential=credential
        )
        
        # Add site
        self.config_manager.add_site(site)
        
        # Export sites
        export_file = Path(self.temp_dir) / "exported_sites.json"
        self.config_manager.export_sites(export_file, include_credentials=False)
        
        assert export_file.exists()
        
        # Clear sites
        self.config_manager.delete_site(site.id)
        sites = self.config_manager.load_sites()
        assert len(sites) == 0
        
        # Import sites
        imported_count = self.config_manager.import_sites(export_file)
        assert imported_count == 1
        
        # Verify import
        sites = self.config_manager.load_sites()
        assert len(sites) == 1