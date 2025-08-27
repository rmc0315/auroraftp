"""Site manager dialog for managing saved connections."""

import asyncio
import json
import logging
import subprocess
import tempfile
from typing import Dict, List, Optional
from uuid import UUID

from PyQt6.QtCore import Qt, QProcess, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.config import get_config_manager
from ..core.models import AuthMethod, Credential, ProtocolType, Site
from ..protocols import ProtocolFactory, URLParser

logger = logging.getLogger(__name__)


class ConnectionTestProcess(QProcess):
    """Process-based connection tester to avoid GUI blocking."""
    
    test_completed = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, site: Site, parent=None):
        super().__init__(parent)
        self.site = site
        self.temp_file = None
        
        # Connect process signals
        self.finished.connect(self.on_process_finished)
        self.errorOccurred.connect(self.on_process_error)
    
    def start_test(self) -> None:
        """Start the connection test in a separate process."""
        try:
            # Create temporary file with site data
            self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            
            # Serialize site data
            site_data = {
                'name': self.site.name,
                'protocol': self.site.protocol.value,
                'hostname': self.site.hostname,
                'port': self.site.port,
                'username': self.site.credential.username,
                'password': self.site.credential.password or '',
                'auth_method': self.site.credential.auth_method.value,
                'passive_mode': self.site.passive_mode,
                'timeout': self.site.timeout,
                'tls_explicit': self.site.tls_explicit,
                'tls_implicit': self.site.tls_implicit,
                'verify_cert': self.site.verify_cert,
                'remote_path': self.site.remote_path or '/'
            }
            
            json.dump(site_data, self.temp_file)
            self.temp_file.close()
            
            # Start the test process
            import sys
            python_executable = sys.executable
            script_path = self.create_test_script()
            
            self.start(python_executable, [script_path, self.temp_file.name])
            
        except Exception as e:
            self.test_completed.emit(False, f"Failed to start test: {e}")
    
    def create_test_script(self) -> str:
        """Create a standalone test script."""
        script_content = '''#!/usr/bin/env python3
import sys
import json
import asyncio
import tempfile
import os

async def test_ftp_connection(site_data):
    """Test FTP connection."""
    try:
        import aioftp
        
        # Create client with passive mode setting
        client_kwargs = {}
        if not site_data.get('passive_mode', True):
            client_kwargs['passive_commands'] = ()
        
        client = aioftp.Client(**client_kwargs)
        
        # Connect with timeout
        await asyncio.wait_for(client.connect(
            host=site_data['hostname'],
            port=site_data['port']
        ), timeout=30.0)
        
        # Login with timeout
        await asyncio.wait_for(client.login(
            user=site_data['username'],
            password=site_data['password']
        ), timeout=15.0)
        
        # Test basic operation
        await asyncio.wait_for(client.get_current_directory(), timeout=10.0)
        
        # Disconnect
        await asyncio.wait_for(client.quit(), timeout=10.0)
        
        return True, f"Successfully connected to {site_data['hostname']}"
        
    except Exception as e:
        return False, str(e)

async def test_sftp_connection(site_data):
    """Test SFTP connection."""
    try:
        import asyncssh
        
        # Connect with timeout
        conn = await asyncio.wait_for(asyncssh.connect(
            host=site_data['hostname'],
            port=site_data['port'],
            username=site_data['username'],
            password=site_data['password'],
            known_hosts=None  # Skip host key verification for test
        ), timeout=30.0)
        
        # Test basic operation
        async with conn:
            sftp = await conn.start_sftp_client()
            await asyncio.wait_for(sftp.getcwd(), timeout=10.0)
        
        return True, f"Successfully connected to {site_data['hostname']}"
        
    except Exception as e:
        return False, str(e)

async def main():
    if len(sys.argv) != 2:
        print("RESULT:false:Missing site data file")
        return
    
    try:
        with open(sys.argv[1], 'r') as f:
            site_data = json.load(f)
        
        protocol = site_data.get('protocol', 'ftp').lower()
        
        if protocol in ['ftp', 'ftps']:
            success, message = await test_ftp_connection(site_data)
        elif protocol in ['sftp', 'scp']:
            success, message = await test_sftp_connection(site_data)
        else:
            success, message = False, f"Unsupported protocol: {protocol}"
        
        result = "true" if success else "false"
        print(f"RESULT:{result}:{message}")
        
    except Exception as e:
        print(f"RESULT:false:Test script error: {e}")
    finally:
        # Clean up temp file
        try:
            os.unlink(sys.argv[1])
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
'''
        
        # Write script to temporary file
        script_file = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        script_file.write(script_content)
        script_file.close()
        return script_file.name
    
    def on_process_finished(self, exit_code, exit_status):
        """Handle process completion."""
        try:
            output = self.readAllStandardOutput().data().decode('utf-8').strip()
            
            # Parse result
            if output.startswith('RESULT:'):
                parts = output[7:].split(':', 2)
                if len(parts) >= 2:
                    success = parts[0] == 'true'
                    message = parts[1] if len(parts) == 2 else parts[2]
                    self.test_completed.emit(success, message)
                else:
                    self.test_completed.emit(False, "Invalid test result format")
            else:
                self.test_completed.emit(False, f"Unexpected output: {output}")
                
        except Exception as e:
            self.test_completed.emit(False, f"Failed to parse test result: {e}")
    
    def on_process_error(self, error):
        """Handle process error."""
        self.test_completed.emit(False, f"Process error: {error}")


class SiteEditDialog(QDialog):
    """Dialog for editing site configuration."""
    
    def __init__(self, site: Optional[Site] = None, parent=None):
        super().__init__(parent)
        self.site = site
        self.test_process: Optional[ConnectionTestProcess] = None
        self.setup_ui()
        
        if site:
            self.load_site_data(site)
        else:
            self.set_defaults()
    
    def setup_ui(self) -> None:
        """Setup UI layout."""
        self.setWindowTitle("Site Configuration")
        self.setModal(True)
        self.resize(500, 600)
        
        layout = QVBoxLayout(self)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # General tab
        self.setup_general_tab()
        
        # Advanced tab
        self.setup_advanced_tab()
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Test connection button
        test_button = QPushButton("Test Connection")
        test_button.clicked.connect(self.test_connection)
        buttons.addButton(test_button, QDialogButtonBox.ButtonRole.ActionRole)
    
    def setup_general_tab(self) -> None:
        """Setup general settings tab."""
        widget = QWidget()
        self.tab_widget.addTab(widget, "General")
        
        layout = QFormLayout(widget)
        
        # Basic settings
        self.name_edit = QLineEdit()
        layout.addRow("Name:", self.name_edit)
        
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems([p.value.upper() for p in ProtocolType])
        self.protocol_combo.currentTextChanged.connect(self.on_protocol_changed)
        layout.addRow("Protocol:", self.protocol_combo)
        
        # Add protocol help text
        protocol_help = QLabel("• FTP/FTPS: Traditional FTP (port 21) - use for most web hosting\n"
                              "• SFTP/SCP: SSH-based (port 22) - use for VPS/dedicated servers")
        protocol_help.setStyleSheet("QLabel { color: #666; font-size: 10px; }")
        protocol_help.setWordWrap(True)
        layout.addRow("", protocol_help)
        
        self.hostname_edit = QLineEdit()
        self.hostname_edit.setPlaceholderText("e.g., ftp.yourhost.com or 192.168.1.100")
        layout.addRow("Hostname:", self.hostname_edit)
        
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        layout.addRow("Port:", self.port_spin)
        
        # Authentication
        auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout(auth_group)
        
        # Make username and password more prominent for FTP connections
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Required: Enter your FTP/SFTP username")
        self.username_edit.setStyleSheet("QLineEdit { border: 2px solid #4CAF50; }")
        auth_layout.addRow("Username*:", self.username_edit)
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Required: Enter your FTP/SFTP password")
        self.password_edit.setStyleSheet("QLineEdit { border: 2px solid #4CAF50; }")
        auth_layout.addRow("Password*:", self.password_edit)
        
        self.auth_method_combo = QComboBox()
        self.auth_method_combo.addItems([m.value.replace('_', ' ').title() for m in AuthMethod])
        self.auth_method_combo.currentTextChanged.connect(self.on_auth_method_changed)
        auth_layout.addRow("Auth Method:", self.auth_method_combo)
        
        self.key_file_edit = QLineEdit()
        auth_layout.addRow("Key File:", self.key_file_edit)
        
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        auth_layout.addRow("Passphrase:", self.passphrase_edit)
        
        self.use_agent_check = QCheckBox("Use SSH Agent")
        auth_layout.addRow("", self.use_agent_check)
        
        layout.addRow(auth_group)
        
        # Paths
        paths_group = QGroupBox("Default Paths")
        paths_layout = QFormLayout(paths_group)
        
        self.local_path_edit = QLineEdit()
        paths_layout.addRow("Local Path:", self.local_path_edit)
        
        self.remote_path_edit = QLineEdit()
        paths_layout.addRow("Remote Path:", self.remote_path_edit)
        
        layout.addRow(paths_group)
    
    def setup_advanced_tab(self) -> None:
        """Setup advanced settings tab."""
        widget = QWidget()
        self.tab_widget.addTab(widget, "Advanced")
        
        layout = QFormLayout(widget)
        
        # Connection settings
        conn_group = QGroupBox("Connection")
        conn_layout = QFormLayout(conn_group)
        
        self.passive_mode_check = QCheckBox("Use Passive Mode")
        self.passive_mode_check.setChecked(True)
        conn_layout.addRow("", self.passive_mode_check)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" seconds")
        conn_layout.addRow("Timeout:", self.timeout_spin)
        
        self.keepalive_spin = QSpinBox()
        self.keepalive_spin.setRange(0, 600)
        self.keepalive_spin.setValue(60)
        self.keepalive_spin.setSuffix(" seconds")
        conn_layout.addRow("Keep Alive:", self.keepalive_spin)
        
        layout.addRow(conn_group)
        
        # TLS/SSL settings
        tls_group = QGroupBox("TLS/SSL")
        tls_layout = QFormLayout(tls_group)
        
        self.tls_explicit_check = QCheckBox("Explicit TLS")
        self.tls_explicit_check.setChecked(True)
        tls_layout.addRow("", self.tls_explicit_check)
        
        self.tls_implicit_check = QCheckBox("Implicit TLS")
        tls_layout.addRow("", self.tls_implicit_check)
        
        self.verify_cert_check = QCheckBox("Verify Certificate")
        self.verify_cert_check.setChecked(True)
        tls_layout.addRow("", self.verify_cert_check)
        
        layout.addRow(tls_group)
        
        # Organization
        org_group = QGroupBox("Organization")
        org_layout = QFormLayout(org_group)
        
        self.folder_edit = QLineEdit()
        org_layout.addRow("Folder:", self.folder_edit)
        
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("tag1, tag2, tag3")
        org_layout.addRow("Tags:", self.tags_edit)
        
        self.color_edit = QLineEdit()
        org_layout.addRow("Color:", self.color_edit)
        
        self.notes_edit = QLineEdit()
        org_layout.addRow("Notes:", self.notes_edit)
        
        layout.addRow(org_group)
    
    def set_defaults(self) -> None:
        """Set default values."""
        self.name_edit.setText("New Site")
        self.protocol_combo.setCurrentText("FTP")
        self.port_spin.setValue(21)
        self.auth_method_combo.setCurrentText("Password")
        self.on_auth_method_changed("Password")
    
    def load_site_data(self, site: Site) -> None:
        """Load site data into form."""
        self.name_edit.setText(site.name)
        self.protocol_combo.setCurrentText(site.protocol.value.upper())
        self.hostname_edit.setText(site.hostname)
        self.port_spin.setValue(site.port)
        
        # Authentication
        self.username_edit.setText(site.credential.username)
        self.auth_method_combo.setCurrentText(
            site.credential.auth_method.value.replace('_', ' ').title()
        )
        
        if site.credential.password:
            self.password_edit.setText(site.credential.password)
        
        if site.credential.key_file:
            self.key_file_edit.setText(str(site.credential.key_file))
        
        if site.credential.passphrase:
            self.passphrase_edit.setText(site.credential.passphrase)
        
        self.use_agent_check.setChecked(site.credential.use_agent)
        
        # Paths
        if site.local_path:
            self.local_path_edit.setText(str(site.local_path))
        if site.remote_path:
            self.remote_path_edit.setText(site.remote_path)
        
        # Advanced
        self.passive_mode_check.setChecked(site.passive_mode)
        self.timeout_spin.setValue(site.timeout)
        self.keepalive_spin.setValue(site.keepalive_interval)
        
        self.tls_explicit_check.setChecked(site.tls_explicit)
        self.tls_implicit_check.setChecked(site.tls_implicit)
        self.verify_cert_check.setChecked(site.verify_cert)
        
        # Organization
        if site.folder:
            self.folder_edit.setText(site.folder)
        if site.tags:
            self.tags_edit.setText(", ".join(site.tags))
        if site.color:
            self.color_edit.setText(site.color)
        if site.notes:
            self.notes_edit.setText(site.notes)
        
        self.on_auth_method_changed(self.auth_method_combo.currentText())
    
    @pyqtSlot(str)
    def on_protocol_changed(self, protocol: str) -> None:
        """Handle protocol change."""
        if protocol == "FTP":
            self.port_spin.setValue(21)
        elif protocol == "FTPS":
            self.port_spin.setValue(21)
        elif protocol in ["SFTP", "SSH"]:
            self.port_spin.setValue(22)
    
    @pyqtSlot(str)
    def on_auth_method_changed(self, method: str) -> None:
        """Handle auth method change."""
        method = method.lower().replace(' ', '_')
        
        self.password_edit.setEnabled(method == "password")
        self.key_file_edit.setEnabled(method == "key_file")
        self.passphrase_edit.setEnabled(method == "key_file")
        self.use_agent_check.setEnabled(method in ["ssh_agent", "key_file"])
    
    def test_connection(self) -> None:
        """Test connection with current settings."""
        try:
            site = self.get_site_data()
            
            # Check if test is already running
            if self.test_process and self.test_process.state() != QProcess.ProcessState.NotRunning:
                QMessageBox.information(self, "Test in Progress", "Connection test is already running.")
                return
            
            # Start connection test process
            self.test_process = ConnectionTestProcess(site, self)
            self.test_process.test_completed.connect(self.on_test_completed)
            self.test_process.start_test()
            
            # Show progress dialog
            self.progress_dialog = QProgressDialog("Testing connection...", "Cancel", 0, 0, self)
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.canceled.connect(self.cancel_test)
            
            # Set a maximum timeout of 30 seconds (shorter for better UX)
            self.test_timeout_timer = QTimer()
            self.test_timeout_timer.setSingleShot(True)
            self.test_timeout_timer.timeout.connect(self.on_test_timeout)
            self.test_timeout_timer.start(30000)  # 30 seconds
            
            self.progress_dialog.show()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Invalid configuration: {e}")
    
    def cancel_test(self) -> None:
        """Cancel connection test."""
        if self.test_process and self.test_process.state() != QProcess.ProcessState.NotRunning:
            self.test_process.kill()
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        if hasattr(self, 'test_timeout_timer'):
            self.test_timeout_timer.stop()
    
    def on_test_timeout(self) -> None:
        """Handle test timeout."""
        if self.test_process:
            self.test_process.kill()
        self.on_test_completed(False, "Test timed out after 30 seconds")
    
    @pyqtSlot(bool, str)
    def on_test_completed(self, success: bool, message: str) -> None:
        """Handle test completion."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        if hasattr(self, 'test_timeout_timer'):
            self.test_timeout_timer.stop()
        
        if success:
            QMessageBox.information(self, "Connection Test", f"✓ {message}")
        else:
            # Provide helpful error messages
            error_message = message
            if "ssh_compression" in message.lower():
                error_message = "SSH compression error. Try using FTP instead of SFTP for web hosting."
            elif "connection refused" in message.lower():
                error_message = "Connection refused. Check hostname and port. For FTP use port 21, for SFTP use port 22."
            elif "authentication" in message.lower() or "login" in message.lower():
                error_message = "Authentication failed. Please check your username and password."
            elif "timeout" in message.lower():
                error_message = "Connection timeout. Check your network and firewall settings."
            
            QMessageBox.critical(self, "Connection Test Failed", f"✗ {error_message}\n\nDetails: {message}")
    
    def get_site_data(self) -> Site:
        """Get site data from form."""
        from pathlib import Path
        
        # Parse protocol
        protocol_str = self.protocol_combo.currentText().lower()
        protocol = ProtocolType(protocol_str)
        
        # Parse auth method
        auth_method_str = self.auth_method_combo.currentText().lower().replace(' ', '_')
        auth_method = AuthMethod(auth_method_str)
        
        # Create credential
        credential = Credential(
            username=self.username_edit.text(),
            auth_method=auth_method,
            password=self.password_edit.text() or None,
            key_file=Path(self.key_file_edit.text()) if self.key_file_edit.text() else None,
            passphrase=self.passphrase_edit.text() or None,
            use_agent=self.use_agent_check.isChecked(),
        )
        
        # Parse tags
        tags = []
        if self.tags_edit.text():
            tags = [tag.strip() for tag in self.tags_edit.text().split(",")]
        
        # Create site
        site_data = {
            "name": self.name_edit.text(),
            "protocol": protocol,
            "hostname": self.hostname_edit.text(),
            "port": self.port_spin.value(),
            "credential": credential,
            "passive_mode": self.passive_mode_check.isChecked(),
            "timeout": self.timeout_spin.value(),
            "keepalive_interval": self.keepalive_spin.value(),
            "tls_explicit": self.tls_explicit_check.isChecked(),
            "tls_implicit": self.tls_implicit_check.isChecked(),
            "verify_cert": self.verify_cert_check.isChecked(),
            "folder": self.folder_edit.text() or None,
            "tags": tags,
            "color": self.color_edit.text() or None,
            "notes": self.notes_edit.text() or None,
        }
        
        if self.local_path_edit.text():
            site_data["local_path"] = Path(self.local_path_edit.text())
        
        if self.remote_path_edit.text():
            site_data["remote_path"] = self.remote_path_edit.text()
        
        if self.site:
            site_data["id"] = self.site.id
        
        return Site(**site_data)


class SiteManagerDialog(QDialog):
    """Site manager main dialog."""
    
    # Signal emitted when user wants to connect to a site
    connect_to_site_requested = pyqtSignal(object)  # Site object
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = get_config_manager()
        self.sites: Dict[str, Site] = {}
        
        self.setup_ui()
        self.load_sites()
    
    def setup_ui(self) -> None:
        """Setup UI layout."""
        self.setWindowTitle("Site Manager")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.new_button = QPushButton("New")
        self.new_button.clicked.connect(self.new_site)
        toolbar_layout.addWidget(self.new_button)
        
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_site)
        self.edit_button.setEnabled(False)
        toolbar_layout.addWidget(self.edit_button)
        
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.clicked.connect(self.duplicate_site)
        self.duplicate_button.setEnabled(False)
        toolbar_layout.addWidget(self.duplicate_button)
        
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_site)
        self.delete_button.setEnabled(False)
        toolbar_layout.addWidget(self.delete_button)
        
        toolbar_layout.addStretch()
        
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self.import_sites)
        toolbar_layout.addWidget(self.import_button)
        
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.export_sites)
        toolbar_layout.addWidget(self.export_button)
        
        layout.addLayout(toolbar_layout)
        
        # Site list
        self.site_tree = QTreeWidget()
        self.site_tree.setHeaderLabels(["Name", "Protocol", "Hostname", "Port", "Username"])
        self.site_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.site_tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.site_tree.itemDoubleClicked.connect(self.edit_site)
        
        # Configure headers
        header = self.site_tree.header()
        header.setStretchLastSection(True)
        header.resizeSection(0, 200)  # Name
        header.resizeSection(1, 80)   # Protocol
        header.resizeSection(2, 150)  # Hostname
        header.resizeSection(3, 60)   # Port
        
        layout.addWidget(self.site_tree)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Connect button
        connect_button = QPushButton("Connect")
        connect_button.clicked.connect(self.connect_to_site)
        buttons.addButton(connect_button, QDialogButtonBox.ButtonRole.ActionRole)
    
    def load_sites(self) -> None:
        """Load sites into tree."""
        self.sites = self.config_manager.load_sites()
        self.refresh_tree()
    
    def refresh_tree(self) -> None:
        """Refresh site tree."""
        self.site_tree.clear()
        
        # Group sites by folder
        folders: Dict[str, List[Site]] = {}
        for site in self.sites.values():
            folder = site.folder or "Default"
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(site)
        
        # Add folder items
        for folder_name, folder_sites in folders.items():
            folder_item = QTreeWidgetItem([folder_name])
            folder_item.setData(0, Qt.ItemDataRole.UserRole, "folder")
            self.site_tree.addTopLevelItem(folder_item)
            
            # Add sites
            for site in folder_sites:
                site_item = QTreeWidgetItem([
                    site.name,
                    site.protocol.value.upper(),
                    site.hostname,
                    str(site.port),
                    site.credential.username,
                ])
                site_item.setData(0, Qt.ItemDataRole.UserRole, str(site.id))
                folder_item.addChild(site_item)
            
            folder_item.setExpanded(True)
    
    @pyqtSlot()
    def on_selection_changed(self) -> None:
        """Handle selection change."""
        current = self.site_tree.currentItem()
        is_site = current and current.data(0, Qt.ItemDataRole.UserRole) != "folder"
        
        self.edit_button.setEnabled(is_site)
        self.duplicate_button.setEnabled(is_site)
        self.delete_button.setEnabled(is_site)
    
    def get_selected_site(self) -> Optional[Site]:
        """Get currently selected site."""
        current = self.site_tree.currentItem()
        if not current:
            return None
        
        site_id = current.data(0, Qt.ItemDataRole.UserRole)
        if site_id == "folder":
            return None
        
        return self.sites.get(site_id)
    
    def new_site(self) -> None:
        """Create new site."""
        dialog = SiteEditDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            site = dialog.get_site_data()
            self.config_manager.add_site(site)
            self.load_sites()
    
    def edit_site(self) -> None:
        """Edit selected site."""
        site = self.get_selected_site()
        if not site:
            return
        
        dialog = SiteEditDialog(site, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_site = dialog.get_site_data()
            self.config_manager.update_site(updated_site)
            self.load_sites()
    
    def duplicate_site(self) -> None:
        """Duplicate selected site."""
        site = self.get_selected_site()
        if not site:
            return
        
        # Create copy with new ID
        import copy
        new_site = copy.deepcopy(site)
        new_site.name = f"{site.name} (Copy)"
        new_site.id = UUID()
        
        dialog = SiteEditDialog(new_site, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            final_site = dialog.get_site_data()
            self.config_manager.add_site(final_site)
            self.load_sites()
    
    def delete_site(self) -> None:
        """Delete selected site."""
        site = self.get_selected_site()
        if not site:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete site '{site.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.delete_site(site.id)
            self.load_sites()
    
    def connect_to_site(self) -> None:
        """Connect to selected site."""
        site = self.get_selected_site()
        if site:
            # Emit signal to main window to connect to this site
            self.connect_to_site_requested.emit(site)
            self.accept()
    
    def import_sites(self) -> None:
        """Import sites from file."""
        from PyQt6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sites",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                from pathlib import Path
                count = self.config_manager.import_sites(Path(file_path))
                QMessageBox.information(
                    self,
                    "Import Complete",
                    f"Imported {count} sites successfully."
                )
                self.load_sites()
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import sites: {e}")
    
    def export_sites(self) -> None:
        """Export sites to file."""
        from PyQt6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sites",
            "auroraftp_sites.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            try:
                from pathlib import Path
                self.config_manager.export_sites(Path(file_path), include_credentials=False)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    "Sites exported successfully.\n\nNote: Passwords are not included for security."
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export sites: {e}")