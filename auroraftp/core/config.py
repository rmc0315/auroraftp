"""Configuration management and secure credential storage."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

import keyring
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from platformdirs import user_config_dir, user_data_dir, user_log_dir
from pydantic import ValidationError

from .models import AppConfig, Site, SyncProfile

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Configuration related errors."""
    pass


class CredentialStore:
    """Secure credential storage using keyring with encrypted fallback."""
    
    SERVICE_NAME = "AuroraFTP"
    
    def __init__(self, use_keyring: bool = True):
        self.use_keyring = use_keyring
        self._encryption_key: Optional[bytes] = None
        self._master_password: Optional[str] = None
    
    def _get_encryption_key(self, password: str) -> bytes:
        """Derive encryption key from master password."""
        salt = b"auroraftp_salt_v1"  # In production, use random salt per user
        kdf = Scrypt(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )
        return kdf.derive(password.encode())
    
    def set_master_password(self, password: str) -> None:
        """Set master password for encrypted storage."""
        self._master_password = password
        self._encryption_key = self._get_encryption_key(password)
    
    def store_credential(self, site_id: str, credential_data: Dict[str, Any]) -> bool:
        """Store credential securely."""
        try:
            if self.use_keyring:
                credential_json = json.dumps(credential_data)
                keyring.set_password(self.SERVICE_NAME, site_id, credential_json)
                return True
            else:
                # Fallback to encrypted file storage
                if not self._encryption_key:
                    raise ConfigError("Master password required for encrypted storage")
                
                encrypted_data = self._encrypt_data(credential_data)
                config_manager = ConfigManager()
                credentials_file = config_manager.config_dir / "credentials.enc"
                
                # Load existing credentials
                all_credentials = {}
                if credentials_file.exists():
                    all_credentials = self._load_encrypted_file(credentials_file)
                
                all_credentials[site_id] = encrypted_data
                self._save_encrypted_file(credentials_file, all_credentials)
                return True
                
        except Exception as e:
            logger.error(f"Failed to store credential for {site_id}: {e}")
            return False
    
    def get_credential(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve credential securely."""
        try:
            if self.use_keyring:
                credential_json = keyring.get_password(self.SERVICE_NAME, site_id)
                if credential_json:
                    return json.loads(credential_json)
            else:
                # Fallback to encrypted file storage
                if not self._encryption_key:
                    raise ConfigError("Master password required for encrypted storage")
                
                config_manager = ConfigManager()
                credentials_file = config_manager.config_dir / "credentials.enc"
                
                if credentials_file.exists():
                    all_credentials = self._load_encrypted_file(credentials_file)
                    if site_id in all_credentials:
                        return self._decrypt_data(all_credentials[site_id])
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve credential for {site_id}: {e}")
            return None
    
    def delete_credential(self, site_id: str) -> bool:
        """Delete stored credential."""
        try:
            if self.use_keyring:
                keyring.delete_password(self.SERVICE_NAME, site_id)
            else:
                config_manager = ConfigManager()
                credentials_file = config_manager.config_dir / "credentials.enc"
                
                if credentials_file.exists():
                    all_credentials = self._load_encrypted_file(credentials_file)
                    if site_id in all_credentials:
                        del all_credentials[site_id]
                        self._save_encrypted_file(credentials_file, all_credentials)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete credential for {site_id}: {e}")
            return False
    
    def _encrypt_data(self, data: Dict[str, Any]) -> str:
        """Encrypt data using Fernet."""
        if not self._encryption_key:
            raise ConfigError("Encryption key not set")
        
        fernet = Fernet(Fernet.generate_key())
        encrypted = fernet.encrypt(json.dumps(data).encode())
        return encrypted.decode()
    
    def _decrypt_data(self, encrypted_data: str) -> Dict[str, Any]:
        """Decrypt data using Fernet."""
        if not self._encryption_key:
            raise ConfigError("Encryption key not set")
        
        fernet = Fernet(self._encryption_key)
        decrypted = fernet.decrypt(encrypted_data.encode())
        return json.loads(decrypted.decode())
    
    def _load_encrypted_file(self, file_path: Path) -> Dict[str, Any]:
        """Load encrypted credentials file."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_encrypted_file(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Save encrypted credentials file."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(data, f)


class ConfigManager:
    """Application configuration manager."""
    
    def __init__(self):
        self.app_name = "auroraftp"
        self.config_dir = Path(user_config_dir(self.app_name))
        self.data_dir = Path(user_data_dir(self.app_name))
        self.log_dir = Path(user_log_dir(self.app_name))
        
        # Create directories
        for directory in [self.config_dir, self.data_dir, self.log_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        self.config_file = self.config_dir / "config.json"
        self.sites_file = self.config_dir / "sites.json"
        self.sync_profiles_file = self.config_dir / "sync_profiles.json"
        
        self._config: Optional[AppConfig] = None
        self._sites: Dict[str, Site] = {}
        self._sync_profiles: Dict[str, SyncProfile] = {}
        self._credential_store = CredentialStore()
    
    @property
    def credential_store(self) -> CredentialStore:
        """Get credential store instance."""
        return self._credential_store
    
    def load_config(self) -> AppConfig:
        """Load application configuration."""
        if self._config is not None:
            return self._config
        
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                self._config = AppConfig(**config_data)
            else:
                self._config = AppConfig()
                self.save_config()
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning(f"Invalid config file, using defaults: {e}")
            self._config = AppConfig()
        
        return self._config
    
    def save_config(self) -> None:
        """Save application configuration."""
        if self._config is None:
            return
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._config.dict(), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise ConfigError(f"Failed to save configuration: {e}")
    
    def load_sites(self) -> Dict[str, Site]:
        """Load saved sites."""
        if self._sites:
            return self._sites
        
        try:
            if self.sites_file.exists():
                with open(self.sites_file, 'r') as f:
                    sites_data = json.load(f)
                
                for site_id, site_data in sites_data.items():
                    try:
                        # Load credential from secure storage
                        credential_data = self._credential_store.get_credential(site_id)
                        if credential_data:
                            site_data['credential'] = credential_data
                        
                        site = Site(**site_data)
                        self._sites[site_id] = site
                    except ValidationError as e:
                        logger.warning(f"Invalid site data for {site_id}: {e}")
            
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load sites: {e}")
        
        return self._sites
    
    def save_sites(self) -> None:
        """Save sites configuration."""
        try:
            sites_data = {}
            
            for site_id, site in self._sites.items():
                site_dict = site.dict()
                
                # Store credential separately
                credential = site_dict.pop('credential', None)
                if credential:
                    self._credential_store.store_credential(site_id, credential)
                
                sites_data[site_id] = site_dict
            
            with open(self.sites_file, 'w') as f:
                json.dump(sites_data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save sites: {e}")
            raise ConfigError(f"Failed to save sites: {e}")
    
    def add_site(self, site: Site) -> None:
        """Add a new site."""
        site_id = str(site.id)
        self._sites[site_id] = site
        self.save_sites()
    
    def update_site(self, site: Site) -> None:
        """Update existing site."""
        site_id = str(site.id)
        if site_id in self._sites:
            self._sites[site_id] = site
            self.save_sites()
        else:
            raise ConfigError(f"Site {site_id} not found")
    
    def delete_site(self, site_id: Union[str, UUID]) -> None:
        """Delete a site."""
        site_id_str = str(site_id)
        if site_id_str in self._sites:
            del self._sites[site_id_str]
            self._credential_store.delete_credential(site_id_str)
            self.save_sites()
        else:
            raise ConfigError(f"Site {site_id_str} not found")
    
    def get_site(self, site_id: Union[str, UUID]) -> Optional[Site]:
        """Get site by ID."""
        return self._sites.get(str(site_id))
    
    def get_sites_by_folder(self, folder: Optional[str] = None) -> List[Site]:
        """Get sites by folder."""
        return [
            site for site in self._sites.values()
            if site.folder == folder
        ]
    
    def load_sync_profiles(self) -> Dict[str, SyncProfile]:
        """Load sync profiles."""
        if self._sync_profiles:
            return self._sync_profiles
        
        try:
            if self.sync_profiles_file.exists():
                with open(self.sync_profiles_file, 'r') as f:
                    profiles_data = json.load(f)
                
                for profile_id, profile_data in profiles_data.items():
                    try:
                        profile = SyncProfile(**profile_data)
                        self._sync_profiles[profile_id] = profile
                    except ValidationError as e:
                        logger.warning(f"Invalid sync profile {profile_id}: {e}")
            
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load sync profiles: {e}")
        
        return self._sync_profiles
    
    def save_sync_profiles(self) -> None:
        """Save sync profiles."""
        try:
            profiles_data = {
                profile_id: profile.dict()
                for profile_id, profile in self._sync_profiles.items()
            }
            
            with open(self.sync_profiles_file, 'w') as f:
                json.dump(profiles_data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save sync profiles: {e}")
            raise ConfigError(f"Failed to save sync profiles: {e}")
    
    def add_sync_profile(self, profile: SyncProfile) -> None:
        """Add sync profile."""
        profile_id = str(profile.id)
        self._sync_profiles[profile_id] = profile
        self.save_sync_profiles()
    
    def delete_sync_profile(self, profile_id: Union[str, UUID]) -> None:
        """Delete sync profile."""
        profile_id_str = str(profile_id)
        if profile_id_str in self._sync_profiles:
            del self._sync_profiles[profile_id_str]
            self.save_sync_profiles()
    
    def export_sites(self, file_path: Path, include_credentials: bool = False) -> None:
        """Export sites to JSON file."""
        sites_data = {}
        
        for site_id, site in self._sites.items():
            site_dict = site.dict()
            
            if not include_credentials:
                # Remove sensitive credential data
                if 'credential' in site_dict:
                    cred = site_dict['credential']
                    site_dict['credential'] = {
                        'username': cred.get('username'),
                        'auth_method': cred.get('auth_method'),
                        'use_agent': cred.get('use_agent', False)
                    }
            
            sites_data[site_id] = site_dict
        
        with open(file_path, 'w') as f:
            json.dump(sites_data, f, indent=2, default=str)
    
    def import_sites(self, file_path: Path) -> int:
        """Import sites from JSON file. Returns number of imported sites."""
        try:
            with open(file_path, 'r') as f:
                sites_data = json.load(f)
            
            imported_count = 0
            
            for site_data in sites_data.values():
                try:
                    site = Site(**site_data)
                    self.add_site(site)
                    imported_count += 1
                except ValidationError as e:
                    logger.warning(f"Skipped invalid site: {e}")
            
            return imported_count
            
        except Exception as e:
            logger.error(f"Failed to import sites: {e}")
            raise ConfigError(f"Failed to import sites: {e}")


# Global configuration instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager