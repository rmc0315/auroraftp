"""URL parsing and protocol auto-detection."""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from ..core.models import AuthMethod, Credential, ProtocolType, Site


class URLParser:
    """Parser for FTP/SFTP URLs."""
    
    @staticmethod
    def parse_url(url: str) -> Optional[Site]:
        """Parse URL and create Site configuration."""
        try:
            parsed = urlparse(url)
            
            # Determine protocol
            protocol_map = {
                'ftp': ProtocolType.FTP,
                'ftps': ProtocolType.FTPS,
                'sftp': ProtocolType.SFTP,
                'ssh': ProtocolType.SFTP,
            }
            
            if parsed.scheme.lower() not in protocol_map:
                return None
            
            protocol = protocol_map[parsed.scheme.lower()]
            
            # Extract connection details
            hostname = parsed.hostname
            if not hostname:
                return None
            
            port = parsed.port
            if not port:
                # Use default ports
                default_ports = {
                    ProtocolType.FTP: 21,
                    ProtocolType.FTPS: 21,
                    ProtocolType.SFTP: 22,
                }
                port = default_ports.get(protocol, 21)
            
            # Extract credentials
            username = parsed.username or "anonymous"
            password = parsed.password
            
            # Determine auth method
            if protocol in [ProtocolType.SFTP]:
                auth_method = AuthMethod.SSH_AGENT if not password else AuthMethod.PASSWORD
            else:
                auth_method = AuthMethod.PASSWORD
            
            credential = Credential(
                username=username,
                password=password,
                auth_method=auth_method,
            )
            
            # Create site
            site = Site(
                name=f"{hostname}:{port}",
                protocol=protocol,
                hostname=hostname,
                port=port,
                credential=credential,
                remote_path=parsed.path or "/",
            )
            
            return site
            
        except Exception:
            return None
    
    @staticmethod
    def validate_hostname(hostname: str) -> bool:
        """Validate hostname format."""
        if not hostname:
            return False
        
        # Basic hostname validation
        pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        return bool(re.match(pattern, hostname))
    
    @staticmethod
    def validate_port(port: int) -> bool:
        """Validate port number."""
        return 1 <= port <= 65535
    
    @staticmethod
    def suggest_connection_name(hostname: str, username: str, protocol: ProtocolType) -> str:
        """Suggest a connection name."""
        protocol_name = protocol.value.upper()
        if username and username != "anonymous":
            return f"{username}@{hostname} ({protocol_name})"
        else:
            return f"{hostname} ({protocol_name})"
    
    @staticmethod
    def format_url(site: Site, include_credentials: bool = False) -> str:
        """Format site as URL."""
        scheme = site.protocol.value
        
        # Build URL components
        netloc = site.hostname
        if site.port != site.default_port:
            netloc = f"{netloc}:{site.port}"
        
        if include_credentials and site.credential.username:
            if site.credential.password and site.credential.auth_method == AuthMethod.PASSWORD:
                netloc = f"{site.credential.username}:{site.credential.password}@{netloc}"
            else:
                netloc = f"{site.credential.username}@{netloc}"
        
        path = site.remote_path or "/"
        
        return f"{scheme}://{netloc}{path}"


def detect_protocol_from_port(port: int) -> Optional[ProtocolType]:
    """Detect likely protocol from port number."""
    port_map = {
        21: ProtocolType.FTP,
        22: ProtocolType.SFTP,
        990: ProtocolType.FTPS,  # Implicit FTPS
    }
    return port_map.get(port)


def parse_connection_string(connection_string: str) -> Optional[Tuple[str, int, Optional[str]]]:
    """Parse connection string formats like 'host:port' or 'user@host:port'."""
    try:
        # Handle user@host:port format
        if '@' in connection_string:
            user_host, port_part = connection_string.rsplit(':', 1) if ':' in connection_string else (connection_string, None)
            username, hostname = user_host.split('@', 1)
        else:
            # Handle host:port format
            if ':' in connection_string:
                hostname, port_part = connection_string.rsplit(':', 1)
                username = None
            else:
                hostname = connection_string
                port_part = None
                username = None
        
        # Parse port
        port = int(port_part) if port_part else None
        
        return hostname, port, username
        
    except (ValueError, IndexError):
        return None