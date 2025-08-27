"""Connection tab widget with dual-pane file browser."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer, pyqtSlot, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from ..core.models import Site, TransferDirection, TransferItem, ProtocolType
from ..protocols import ProtocolFactory, ProtocolSession, URLParser
from ..services import TransferManager
from .file_pane import LocalFilePane, RemoteFilePane

logger = logging.getLogger(__name__)


class ConnectionTab(QWidget):
    """Connection tab with dual-pane file browser."""
    
    title_changed = pyqtSignal(str)
    
    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.site: Optional[Site] = None
        self.session: Optional[ProtocolSession] = None
        self.is_connected = False
        
        self.setup_ui()
        self.connect_signals()
        self.load_saved_sites()
    
    def setup_ui(self) -> None:
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        
        # Connection bar
        connection_layout = QHBoxLayout()
        
        # Site selector
        self.site_label = QLabel("Site:")
        connection_layout.addWidget(self.site_label)
        
        self.site_combo = QComboBox()
        self.site_combo.addItem("Select saved site...", None)
        self.site_combo.addItem("Manual connection", "manual")
        self.site_combo.addItem("Manage Sites...", "manage")
        self.site_combo.currentTextChanged.connect(self.on_site_selected)
        self.site_combo.setMinimumWidth(200)
        connection_layout.addWidget(self.site_combo)
        
        connection_layout.addSpacing(10)  # Add some space
        
        self.server_label = QLabel("Server:")
        connection_layout.addWidget(self.server_label)
        
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("hostname:port or ftp://user:pass@host:port")
        self.server_edit.setMinimumWidth(250)
        connection_layout.addWidget(self.server_edit)
        
        connection_layout.addSpacing(10)  # Add some space
        
        # Remote path input
        self.path_label = QLabel("Path:")
        connection_layout.addWidget(self.path_label)
        
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("/remote/path (optional)")
        self.path_edit.setMinimumWidth(150)
        connection_layout.addWidget(self.path_edit)
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect)
        connection_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect)
        self.disconnect_button.setEnabled(False)
        connection_layout.addWidget(self.disconnect_button)
        
        layout.addLayout(connection_layout)
        
        # File panes
        splitter = QSplitter()
        
        # Local pane
        self.local_pane = LocalFilePane()
        self.local_pane.file_dropped.connect(self.on_local_drop)
        splitter.addWidget(self.local_pane)
        
        # Remote pane
        self.remote_pane = RemoteFilePane()
        self.remote_pane.file_dropped.connect(self.on_remote_drop)
        splitter.addWidget(self.remote_pane)
        
        # Set equal sizes
        splitter.setSizes([500, 500])
        
        layout.addWidget(splitter)
        
        # Status
        self.status_label = QLabel("Not connected")
        layout.addWidget(self.status_label)
    
    def connect_signals(self) -> None:
        """Connect internal signals."""
        self.local_pane.transfer_requested.connect(self.add_transfer)
        self.remote_pane.transfer_requested.connect(self.add_transfer)
    
    def load_saved_sites(self) -> None:
        """Load saved sites into combo box."""
        from ..core.config import get_config_manager
        
        # Clear existing items except defaults
        while self.site_combo.count() > 3:
            self.site_combo.removeItem(3)
        
        # Load sites from config
        config_manager = get_config_manager()
        sites = config_manager.load_sites()
        
        # Add sites to combo box
        for site in sites.values():
            display_name = f"{site.name} ({site.protocol.value}://{site.hostname}:{site.port})"
            self.site_combo.addItem(display_name, site)
    
    @pyqtSlot(str)
    def on_site_selected(self, text: str) -> None:
        """Handle site selection from combo box."""
        current_data = self.site_combo.currentData()
        
        if current_data is None:
            # "Select saved site..." option
            self.server_edit.setEnabled(True)
            self.path_edit.setEnabled(True)
            self.server_edit.clear()
            self.path_edit.clear()
            self.site = None
        elif current_data == "manual":
            # "Manual connection" option
            self.server_edit.setEnabled(True)
            self.path_edit.setEnabled(True)
            self.server_edit.clear()
            self.path_edit.clear()
            self.site = None
        elif current_data == "manage":
            # "Manage Sites..." option
            self.open_site_manager()
            # Reset to previous selection
            self.site_combo.setCurrentIndex(0)
        else:
            # Actual site selected
            site = current_data
            self.set_site(site)
            self.server_edit.setEnabled(False)
            self.path_edit.setEnabled(True)
    
    def open_site_manager(self) -> None:
        """Open site manager dialog."""
        from .site_manager import SiteManagerDialog
        
        dialog = SiteManagerDialog(self)
        dialog.connect_to_site_requested.connect(self.on_site_manager_connect)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_saved_sites()
    
    @pyqtSlot(object)
    def on_site_manager_connect(self, site) -> None:
        """Handle connect request from site manager."""
        self.set_site(site)
        QTimer.singleShot(500, self.connect)
    
    def set_site(self, site: Site) -> None:
        """Set site configuration."""
        self.site = site
        self.server_edit.setText(f"{site.hostname}:{site.port}")
        self.title_changed.emit(site.name)
        
        if site.remote_path:
            self.path_edit.setText(site.remote_path)
        else:
            self.path_edit.setText("/")
        
        for i in range(self.site_combo.count()):
            if self.site_combo.itemData(i) == site:
                self.site_combo.setCurrentIndex(i)
                break
        
        if site.local_path:
            self.local_pane.navigate_to(site.local_path)
    
    def connect(self) -> None:
        """Connect to remote server."""
        if self.is_connected:
            return

        if not self.site:
            url = self.server_edit.text()
            if "://" not in url:
                if any(pattern in url.lower() for pattern in ['ftp.', 'bluehost', 'hostgator', 'godaddy', 'cpanel']):
                    url = f"ftp://{url}"
                else:
                    url = f"ftp://{url}"
            
            self.site = URLParser.parse_url(url)
            if not self.site:
                self.status_label.setText("Invalid server format")
                return
            
            if any(pattern in self.site.hostname.lower() for pattern in ['bluehost', 'hostgator', 'godaddy']):
                self.site.protocol = ProtocolType.FTP
                if self.site.port == 22:
                    self.site.port = 21
            
            path = self.path_edit.text().strip()
            if path:
                self.site.remote_path = path

        async def _connect_task():
            try:
                session = ProtocolFactory.create_session(self.site)
                await asyncio.wait_for(session.connect(), timeout=30.0)
                server_info = f"{self.site.protocol.value}://{self.site.hostname}:{self.site.port}"
                self.on_connected(server_info, session)
            except asyncio.TimeoutError:
                self.on_connection_failed("Connection timeout - operation took too long")
            except Exception as e:
                logger.error(f"Connection failed: {e}", exc_info=True)
                self.on_connection_failed(str(e))

        self.connect_button.setEnabled(False)
        self.status_label.setText(f"Connecting to {self.site.hostname}...")
        loop = asyncio.get_event_loop()
        loop.create_task(_connect_task())

    def on_connected(self, server_info: str, session: ProtocolSession) -> None:
        """Handle successful connection."""
        self.is_connected = True
        self.session = session
        
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.status_label.setText(f"Connected to {server_info}")
        
        self.remote_pane.set_session(self.session)
        
        initial_path = self.path_edit.text().strip() or "/"
        QTimer.singleShot(1000, lambda: self.safe_navigate_to_initial_path(initial_path))
        
        self.title_changed.emit(f"{self.site.name} [Connected]")
        logger.info(f"Connected to {self.site.hostname}")
    
    def safe_navigate_to_initial_path(self, path: str) -> None:
        """Safely navigate to initial path with error handling."""
        try:
            if self.is_connected and self.remote_pane:
                self.remote_pane.navigate_to(path)
        except Exception as e:
            logger.warning(f"Failed to navigate to initial path {path}: {e}")
    
    def on_connection_failed(self, error: str) -> None:
        """Handle connection failure."""
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        
        error_message = error
        if "ssh_compression" in error.lower():
            error_message = "SSH compression error. Try using FTP instead of SFTP."
        elif "connection refused" in error.lower():
            error_message = "Connection refused. Check hostname and port."
        elif "authentication" in error.lower() or "login" in error.lower():
            error_message = "Authentication failed. Check username and password."
        elif "timeout" in error.lower():
            error_message = "Connection timeout. Check network and firewall."
        
        self.status_label.setText(f"Connection failed: {error_message}")
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Connection Failed")
        msg.setText("Failed to connect to server")
        msg.setDetailedText(f"Hostname: {self.site.hostname if self.site else 'Unknown'}\n"
                           f"Port: {self.site.port if self.site else 'Unknown'}\n"
                           f"Protocol: {self.site.protocol.value if self.site else 'Unknown'}\n"
                           f"Username: {self.site.credential.username if self.site else 'Unknown'}\n"
                           f"Error: {error}")
        msg.exec()
        logger.error(f"Connection to {self.site.hostname if self.site else 'server'} failed: {error}")
    
    def disconnect(self) -> None:
        """Disconnect from remote server."""
        if not self.is_connected:
            return
        
        if self.session:
            try:
                loop = asyncio.get_event_loop()
                async def do_disconnect():
                    try:
                        await self.session.disconnect()
                    except Exception as e:
                        logger.warning(f"Error during disconnect: {e}")
                
                if loop.is_running():
                    loop.create_task(do_disconnect())
            except Exception as e:
                logger.warning(f"Failed to schedule disconnect: {e}")
            finally:
                self.session = None
        
        self.is_connected = False
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.status_label.setText("Disconnected")
        self.remote_pane.clear_session()
        
        if self.site:
            self.title_changed.emit(self.site.name)
        logger.info("Disconnected")
    
    def refresh(self) -> None:
        """Refresh both panes."""
        self.local_pane.refresh()
        if self.is_connected:
            self.remote_pane.refresh()
    
    def set_show_hidden(self, show: bool) -> None:
        """Set hidden files visibility."""
        self.local_pane.set_show_hidden(show)
        self.remote_pane.set_show_hidden(show)
    
    @pyqtSlot(object)
    def on_local_drop(self, drop_data) -> None:
        """Handle files dropped on local pane."""
        if hasattr(drop_data, 'remote_files'):
            for remote_file in drop_data.remote_files:
                local_path = self.local_pane.current_path / remote_file.name
                self.add_download_transfer(remote_file.path, local_path)
    
    @pyqtSlot(object) 
    def on_remote_drop(self, drop_data) -> None:
        """Handle files dropped on remote pane."""
        if hasattr(drop_data, 'local_files'):
            for local_file in drop_data.local_files:
                remote_path = f"{self.remote_pane.current_path.rstrip('/')}/{local_file.name}"
                self.add_upload_transfer(local_file, remote_path)
    
    @pyqtSlot(str, str, str)
    def add_transfer(self, direction: str, local_path: str, remote_path: str) -> None:
        """Add transfer to queue."""
        if not self.site:
            return
        
        if direction == "upload":
            # Combine the remote pane's current path with the filename
            full_remote_path = f"{self.remote_pane.current_path.rstrip('/')}/{Path(remote_path).name}"
            self.add_upload_transfer(Path(local_path), full_remote_path)
        elif direction == "download":
            # Combine the local pane's current path with the filename
            full_local_path = self.local_pane.current_path / Path(local_path).name
            self.add_download_transfer(remote_path, full_local_path)
    
    def add_upload_transfer(self, local_path: Path, remote_path: str) -> None:
        """Add upload transfer."""
        if not self.site:
            return
        
        transfer = TransferItem(
            site_id=self.site.id,
            direction=TransferDirection.UPLOAD,
            local_path=local_path,
            remote_path=remote_path,
            size=local_path.stat().st_size if local_path.exists() else 0,
        )
        self.transfer_manager.add_transfer(transfer)
        logger.info(f"Added upload: {local_path} -> {remote_path}")
    
    def add_download_transfer(self, remote_path: str, local_path: Path) -> None:
        """Add download transfer."""
        if not self.site:
            return
        
        transfer = TransferItem(
            site_id=self.site.id,
            direction=TransferDirection.DOWNLOAD,
            local_path=local_path,
            remote_path=remote_path,
        )
        self.transfer_manager.add_transfer(transfer)
        logger.info(f"Added download: {remote_path} -> {local_path}")
    
    def closeEvent(self, event) -> None:
        """Handle tab close."""
        self.disconnect()
        event.accept()
