"""Main application window."""

import asyncio
import logging
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.config import get_config_manager
from ..core.events import event_bus
from ..core.models import Site
from ..protocols import URLParser
from ..services import TransferManager
from .connection_tab import ConnectionTab
from .log_panel import LogPanel
from .site_manager import SiteManagerDialog
from .transfer_queue import TransferQueueWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.config_manager = get_config_manager()
        self.transfer_manager = TransferManager()
        self.connection_tabs: Dict[str, ConnectionTab] = {}
        
        self.setup_ui()
        self.setup_menus()
        self.setup_toolbars()
        self.setup_status_bar()
        self.setup_docks()
        self.connect_signals()
        
        # Start transfer manager
        QTimer.singleShot(100, self.start_transfer_manager)
    
    def setup_ui(self) -> None:
        """Setup main UI layout."""
        self.setWindowTitle("AuroraFTP")
        self.setMinimumSize(1200, 800)
        
        # Central widget with tab area
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab widget for connections
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        # Add "+" button for new connection
        self.tab_widget.addTab(QWidget(), "+")
        self.tab_widget.tabBarClicked.connect(self.on_tab_clicked)
        
        layout.addWidget(self.tab_widget)
    
    def setup_menus(self) -> None:
        """Setup menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        new_connection_action = QAction("&New Connection", self)
        new_connection_action.setShortcut(QKeySequence("Ctrl+N"))
        new_connection_action.triggered.connect(self.new_connection)
        file_menu.addAction(new_connection_action)
        
        file_menu.addSeparator()
        
        site_manager_action = QAction("&Site Manager", self)
        site_manager_action.setShortcut(QKeySequence("Ctrl+M"))
        site_manager_action.triggered.connect(self.show_site_manager)
        file_menu.addAction(site_manager_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Connection menu
        connection_menu = menubar.addMenu("&Connection")
        
        connect_action = QAction("&Connect", self)
        connect_action.setShortcut(QKeySequence("Ctrl+Return"))
        connect_action.triggered.connect(self.connect_current_tab)
        connection_menu.addAction(connect_action)
        
        disconnect_action = QAction("&Disconnect", self)
        disconnect_action.setShortcut(QKeySequence("Ctrl+D"))
        disconnect_action.triggered.connect(self.disconnect_current_tab)
        connection_menu.addAction(disconnect_action)
        
        # Transfer menu
        transfer_menu = menubar.addMenu("&Transfer")
        
        pause_all_action = QAction("&Pause All", self)
        pause_all_action.triggered.connect(self.pause_all_transfers)
        transfer_menu.addAction(pause_all_action)
        
        resume_all_action = QAction("&Resume All", self)
        resume_all_action.triggered.connect(self.resume_all_transfers)
        transfer_menu.addAction(resume_all_action)
        
        clear_completed_action = QAction("&Clear Completed", self)
        clear_completed_action.setShortcut(QKeySequence("Ctrl+K"))
        clear_completed_action.triggered.connect(self.clear_completed_transfers)
        transfer_menu.addAction(clear_completed_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        
        show_hidden_action = QAction("Show &Hidden Files", self)
        show_hidden_action.setShortcut(QKeySequence("Ctrl+H"))
        show_hidden_action.setCheckable(True)
        show_hidden_action.triggered.connect(self.toggle_hidden_files)
        view_menu.addAction(show_hidden_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_toolbars(self) -> None:
        """Setup toolbars."""
        main_toolbar = QToolBar("Main")
        self.addToolBar(main_toolbar)
        
        # New connection
        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence("Ctrl+T"))
        new_action.triggered.connect(self.new_connection)
        main_toolbar.addAction(new_action)
        
        main_toolbar.addSeparator()
        
        # Connect/Disconnect
        connect_action = QAction("Connect", self)
        connect_action.triggered.connect(self.connect_current_tab)
        main_toolbar.addAction(connect_action)
        
        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect_current_tab)
        main_toolbar.addAction(disconnect_action)
        
        main_toolbar.addSeparator()
        
        # Refresh
        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.refresh_current_tab)
        main_toolbar.addAction(refresh_action)
    
    def setup_status_bar(self) -> None:
        """Setup status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Connect to event bus for status messages
        event_bus.status_message.connect(self.show_status_message)
        
        self.show_status_message("Ready", 0)
    
    def setup_docks(self) -> None:
        """Setup dock widgets."""
        # Transfer queue dock
        self.transfer_dock = QDockWidget("Transfer Queue", self)
        self.transfer_queue_widget = TransferQueueWidget(self.transfer_manager)
        self.transfer_dock.setWidget(self.transfer_queue_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.transfer_dock)
        
        # Log panel dock
        self.log_dock = QDockWidget("Logs", self)
        self.log_panel = LogPanel()
        self.log_dock.setWidget(self.log_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.log_dock)
        
        # Hide docks initially
        self.transfer_dock.hide()
        self.log_dock.hide()
    
    def connect_signals(self) -> None:
        """Connect event bus signals."""
        event_bus.error_message.connect(self.show_error_message)
        event_bus.connection_established.connect(self.on_connection_established)
        event_bus.connection_failed.connect(self.on_connection_failed)
        event_bus.transfer_added.connect(self.on_transfer_added)
    
    def start_transfer_manager(self) -> None:
        """Start the transfer manager."""
        # Use QTimer to defer the async operation to avoid blocking GUI
        QTimer.singleShot(0, self._do_start_transfer_manager)
    
    def _do_start_transfer_manager(self) -> None:
        """Actually start the transfer manager."""
        try:
            # Get the current event loop (should be the qasync loop)
            loop = asyncio.get_event_loop()
            loop.create_task(self.transfer_manager.start())
        except Exception as e:
            logger.error(f"Failed to start transfer manager: {e}")
    
    @pyqtSlot(int)
    def on_tab_clicked(self, index: int) -> None:
        """Handle tab clicks."""
        if index == self.tab_widget.count() - 1:  # "+" tab
            self.new_connection()
    
    def new_connection(self) -> None:
        """Create new connection tab."""
        tab = ConnectionTab(self.transfer_manager)
        tab_index = self.tab_widget.count() - 1  # Insert before "+" tab
        self.tab_widget.insertTab(tab_index, tab, "New Connection")
        self.tab_widget.setCurrentIndex(tab_index)
        
        # Store tab reference
        tab_id = f"tab_{tab_index}"
        self.connection_tabs[tab_id] = tab
        
        # Connect tab signals
        tab.title_changed.connect(lambda title: self.update_tab_title(tab, title))
    
    @pyqtSlot(int)
    def close_tab(self, index: int) -> None:
        """Close connection tab."""
        if index < self.tab_widget.count() - 1:  # Don't close "+" tab
            tab = self.tab_widget.widget(index)
            
            # Disconnect if connected
            if hasattr(tab, 'disconnect'):
                tab.disconnect()
            
            # Remove from tabs dict
            for tab_id, stored_tab in list(self.connection_tabs.items()):
                if stored_tab == tab:
                    del self.connection_tabs[tab_id]
                    break
            
            self.tab_widget.removeTab(index)
    
    def update_tab_title(self, tab: ConnectionTab, title: str) -> None:
        """Update tab title."""
        for i in range(self.tab_widget.count() - 1):
            if self.tab_widget.widget(i) == tab:
                self.tab_widget.setTabText(i, title)
                break
    
    def get_current_tab(self) -> Optional[ConnectionTab]:
        """Get current connection tab."""
        current_index = self.tab_widget.currentIndex()
        if current_index < self.tab_widget.count() - 1:
            return self.tab_widget.widget(current_index)
        return None
    
    def connect_current_tab(self) -> None:
        """Connect current tab."""
        tab = self.get_current_tab()
        if tab:
            tab.connect()
    
    def disconnect_current_tab(self) -> None:
        """Disconnect current tab."""
        tab = self.get_current_tab()
        if tab:
            tab.disconnect()
    
    def refresh_current_tab(self) -> None:
        """Refresh current tab."""
        tab = self.get_current_tab()
        if tab:
            tab.refresh()
    
    def show_site_manager(self) -> None:
        """Show site manager dialog."""
        dialog = SiteManagerDialog(self)
        dialog.connect_to_site_requested.connect(self.connect_to_site_from_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh connections if needed
            pass
    
    @pyqtSlot(object)
    def connect_to_site_from_manager(self, site) -> None:
        """Connect to site selected from site manager."""
        # Create new tab with the selected site
        tab = ConnectionTab(self.transfer_manager)
        tab.set_site(site)
        
        tab_index = self.tab_widget.count() - 1  # Insert before "+" tab
        self.tab_widget.insertTab(tab_index, tab, site.name)
        self.tab_widget.setCurrentIndex(tab_index)
        
        # Store tab reference
        tab_id = f"tab_{tab_index}"
        self.connection_tabs[tab_id] = tab
        
        # Connect tab signals
        tab.title_changed.connect(lambda title: self.update_tab_title(tab, title))
        
        # Auto-connect after a short delay
        QTimer.singleShot(500, tab.connect)
    
    def toggle_hidden_files(self, checked: bool) -> None:
        """Toggle hidden files visibility."""
        for tab in self.connection_tabs.values():
            if hasattr(tab, 'set_show_hidden'):
                tab.set_show_hidden(checked)
    
    def pause_all_transfers(self) -> None:
        """Pause all transfers."""
        # Implementation depends on transfer manager
        pass
    
    def resume_all_transfers(self) -> None:
        """Resume all transfers."""
        # Implementation depends on transfer manager
        pass
    
    def clear_completed_transfers(self) -> None:
        """Clear completed transfers."""
        self.transfer_manager.clear_completed()
    
    def auto_connect(self, url: str, password_env: str = None) -> None:
        """Auto-connect to URL."""
        site = URLParser.parse_url(url)
        if not site:
            self.show_error_message("Invalid URL", f"Could not parse URL: {url}")
            return
        
        # Set password from environment if specified
        if password_env:
            import os
            password = os.getenv(password_env)
            if password:
                site.credential.password = password
        
        # Create new tab and connect
        tab = ConnectionTab(self.transfer_manager)
        tab.set_site(site)
        
        tab_index = self.tab_widget.count() - 1
        self.tab_widget.insertTab(tab_index, tab, site.name)
        self.tab_widget.setCurrentIndex(tab_index)
        
        # Connect
        QTimer.singleShot(500, tab.connect)
    
    @pyqtSlot(str, int)
    def show_status_message(self, message: str, timeout: int) -> None:
        """Show status bar message."""
        if timeout > 0:
            self.status_bar.showMessage(message, timeout)
        else:
            self.status_bar.showMessage(message)
    
    @pyqtSlot(str, str)
    def show_error_message(self, title: str, message: str) -> None:
        """Show error message dialog."""
        QMessageBox.critical(self, title, message)
    
    @pyqtSlot()
    def on_connection_established(self) -> None:
        """Handle connection established."""
        self.show_status_message("Connected", 3000)
    
    @pyqtSlot(object, str)
    def on_connection_failed(self, site_id, error: str) -> None:
        """Handle connection failed."""
        self.show_status_message(f"Connection failed: {error}", 5000)
    
    @pyqtSlot(object)
    def on_transfer_added(self, transfer_id) -> None:
        """Handle transfer added."""
        # Show transfer dock if hidden
        if self.transfer_dock.isHidden():
            self.transfer_dock.show()
    
    def show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About AuroraFTP",
            "<h3>AuroraFTP 0.1.0</h3>"
            "<p>Modern FTP/SFTP client for Linux</p>"
            "<p>Built with Python and PyQt6</p>"
            "<p>Copyright © 2024 AuroraFTP Team</p>"
        )
    
    def closeEvent(self, event) -> None:
        """Handle window close event."""
        # Disconnect all tabs first (this is synchronous from UI perspective)
        for tab in self.connection_tabs.values():
            if hasattr(tab, 'disconnect'):
                tab.disconnect()
        
        # Schedule async cleanup but don't wait for it
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                async def cleanup():
                    try:
                        await self.transfer_manager.stop()
                    except Exception as e:
                        logger.warning(f"Error stopping transfer manager: {e}")
                
                loop.create_task(cleanup())
        except Exception as e:
            logger.warning(f"Failed to schedule cleanup: {e}")
        
        # Accept immediately to avoid hanging on close
        event.accept()