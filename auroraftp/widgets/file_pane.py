"""File pane widgets for local and remote file browsing."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QFileSystemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import RemoteFile
from ..protocols import ProtocolSession

logger = logging.getLogger(__name__)


class RemoteFileModel:
    """Simple model for remote files."""
    
    def __init__(self):
        self.files: List[RemoteFile] = []
        self.current_path = "/"
    
    def set_files(self, files: List[RemoteFile]) -> None:
        """Set file list."""
        self.files = files
    
    def get_files(self) -> List[RemoteFile]:
        """Get file list."""
        return self.files





class FilePane(QWidget):
    """Base file pane widget."""
    
    transfer_requested = pyqtSignal(str, str, str)  # direction, local_path, remote_path
    file_dropped = pyqtSignal(object)  # drop data
    
    def __init__(self):
        super().__init__()
        self.show_hidden = False
        self.current_path = Path.cwd()
        
        self.setup_ui()
    
    def setup_ui(self) -> None:
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        
        # Path bar
        path_layout = QHBoxLayout()
        
        self.path_label = QLabel("Path:")
        path_layout.addWidget(self.path_label)
        
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self.on_path_entered)
        path_layout.addWidget(self.path_edit)
        
        self.up_button = QPushButton("Up")
        self.up_button.clicked.connect(self.go_up)
        path_layout.addWidget(self.up_button)
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        path_layout.addWidget(self.refresh_button)
        
        layout.addLayout(path_layout)
        
        # File tree
        self.tree_view = QTreeWidget()
        self.tree_view.setHeaderLabels(["Name", "Size", "Modified", "Type"])
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_view.itemDoubleClicked.connect(self.on_item_double_click)
        
        layout.addWidget(self.tree_view)
    
    def navigate_to(self, path) -> None:
        """Navigate to path."""
        raise NotImplementedError
    
    def refresh(self) -> None:
        """Refresh file list."""
        raise NotImplementedError
    
    def go_up(self) -> None:
        """Go up one directory."""
        raise NotImplementedError
    
    def on_path_entered(self) -> None:
        """Handle path entered in edit."""
        path = self.path_edit.text()
        self.navigate_to(path)
    
    def on_double_click(self, index) -> None:
        """Handle double click on item."""
        raise NotImplementedError
    
    def on_item_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double click on tree widget item."""
        self.on_double_click(None)  # For compatibility
    
    def show_context_menu(self, position) -> None:
        """Show context menu."""
        raise NotImplementedError
    
    def set_show_hidden(self, show: bool) -> None:
        """Set hidden files visibility."""
        self.show_hidden = show
        self.refresh()


class LocalFilePane(FilePane):
    """Local file system pane."""
    
    def __init__(self):
        super().__init__()
        self.current_path = Path.cwd()
        
        # Update path display and refresh
        self.update_path_display()
        self.refresh()
    
    def navigate_to(self, path) -> None:
        """Navigate to local path."""
        try:
            if isinstance(path, str):
                path = Path(path)
            
            if path.exists() and path.is_dir():
                self.current_path = path
                self.update_path_display()
                self.refresh()
            else:
                QMessageBox.warning(self, "Invalid Path", f"Path does not exist: {path}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to navigate: {e}")
    
    def refresh(self) -> None:
        """Refresh local file list."""
        self.tree_view.clear()
        
        try:
            # Add parent directory entry
            if self.current_path.parent != self.current_path:
                parent_item = QTreeWidgetItem([".. (Parent Directory)", "", "", "Directory"])
                parent_item.setData(0, Qt.ItemDataRole.UserRole, str(self.current_path.parent))
                self.tree_view.addTopLevelItem(parent_item)
            
            # List directory contents
            for item in self.current_path.iterdir():
                # Skip hidden files if not showing them
                if not self.show_hidden and item.name.startswith('.'):
                    continue
                
                try:
                    size_str = ""
                    if item.is_file():
                        size = item.stat().st_size
                        size_str = self.format_size(size)
                    
                    modified_str = ""
                    try:
                        import datetime
                        modified = datetime.datetime.fromtimestamp(item.stat().st_mtime)
                        modified_str = modified.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                    
                    type_str = "Directory" if item.is_dir() else "File"
                    
                    tree_item = QTreeWidgetItem([item.name, size_str, modified_str, type_str])
                    tree_item.setData(0, Qt.ItemDataRole.UserRole, str(item))
                    self.tree_view.addTopLevelItem(tree_item)
                    
                except (PermissionError, OSError):
                    # Skip items we can't access
                    continue
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to list directory: {e}")
    
    def format_size(self, size: int) -> str:
        """Format file size for display."""
        if size == 0:
            return "0 B"
        
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size_float = float(size)
        
        while size_float >= 1024 and unit_index < len(units) - 1:
            size_float /= 1024
            unit_index += 1
        
        return f"{size_float:.1f} {units[unit_index]}"
    
    def go_up(self) -> None:
        """Go up one directory."""
        parent = self.current_path.parent
        if parent != self.current_path:
            self.navigate_to(parent)
    
    def update_path_display(self) -> None:
        """Update path display."""
        self.path_edit.setText(str(self.current_path))
    
    def on_double_click(self, index) -> None:
        """Handle double click on local item."""
        current_item = self.tree_view.currentItem()
        if not current_item:
            return
        
        path_str = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        
        path = Path(path_str)
        type_str = current_item.text(3)
        
        if type_str == "Directory":
            self.navigate_to(path)
        else:
            # Open file with default application
            import subprocess
            import sys
            
            if sys.platform.startswith('linux'):
                subprocess.run(['xdg-open', str(path)])
    
    def on_item_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double click on tree widget item."""
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        
        path = Path(path_str)
        type_str = item.text(3)
        
        if type_str == "Directory":
            self.navigate_to(path)
        else:
            # Open file with default application
            import subprocess
            import sys
            
            if sys.platform.startswith('linux'):
                subprocess.run(['xdg-open', str(path)])
    
    def show_context_menu(self, position) -> None:
        """Show context menu for local files."""
        item = self.tree_view.itemAt(position)
        if not item:
            return
        
        path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not path_str:
            return
        
        file_path = Path(path_str)
        
        menu = QMenu(self)
        
        # Upload action
        upload_action = QAction("Upload", self)
        upload_action.triggered.connect(lambda: self.request_upload(file_path))
        menu.addAction(upload_action)
        
        menu.addSeparator()
        
        # New folder action
        new_folder_action = QAction("New Folder", self)
        new_folder_action.triggered.connect(self.create_new_folder)
        menu.addAction(new_folder_action)
        
        # Delete action
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self.delete_file(file_path))
        menu.addAction(delete_action)
        
        # Rename action
        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(lambda: self.rename_file(file_path))
        menu.addAction(rename_action)
        
        menu.exec(self.tree_view.mapToGlobal(position))
    
    def request_upload(self, local_path: Path) -> None:
        """Request upload of local file."""
        # Emit signal to request upload
        remote_path = local_path.name  # Default to same name
        self.transfer_requested.emit("upload", str(local_path), remote_path)
    
    def create_new_folder(self) -> None:
        """Create new folder."""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            try:
                new_path = self.current_path / name
                new_path.mkdir()
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create folder: {e}")
    
    def delete_file(self, file_path: Path) -> None:
        """Delete file or folder."""
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{file_path.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if file_path.is_dir():
                    file_path.rmdir()
                else:
                    file_path.unlink()
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")
    
    def rename_file(self, file_path: Path) -> None:
        """Rename file or folder."""
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=file_path.name
        )
        if ok and new_name and new_name != file_path.name:
            try:
                new_path = file_path.parent / new_name
                file_path.rename(new_path)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to rename: {e}")


class RemoteFilePane(FilePane):
    """Remote file system pane."""
    
    def __init__(self):
        super().__init__()
        self.session: Optional[ProtocolSession] = None
        self.model = RemoteFileModel()
        self.current_path = "/"
        
        # Setup tree widget headers  
        header = self.tree_view.header()
        header.setStretchLastSection(True)
        header.resizeSection(0, 200)  # Name
        header.resizeSection(1, 100)  # Size  
        header.resizeSection(2, 150)  # Modified
        header.resizeSection(3, 80)   # Type
        
        self.update_path_display()
    
    def set_session(self, session: ProtocolSession) -> None:
        """Set protocol session."""
        self.session = session
        # Delay the initial refresh to avoid immediate crash
        QTimer.singleShot(500, self.safe_refresh)
    
    def safe_refresh(self) -> None:
        """Safely refresh with error handling."""
        try:
            if self.session:
                self.refresh()
        except Exception as e:
            logger.error(f"Failed to perform initial refresh: {e}")
            # Show a message to the user but don't crash
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Warning", f"Could not list remote directory: {e}")
    
    def clear_session(self) -> None:
        """Clear protocol session."""
        self.session = None
        self.model.set_files([])
        self.update_display()
    
    def navigate_to(self, path: str) -> None:
        """Navigate to remote path."""
        if not self.session:
            return
        
        self.current_path = path
        self.update_path_display()
        self.refresh()
    
    def refresh(self) -> None:
        """Refresh remote file list."""
        if not self.session:
            return

        async def _refresh():
            try:
                logger.info(f"Starting async directory listing for {self.current_path}")
                files = await asyncio.wait_for(
                    self.session.list_directory(self.current_path),
                    timeout=15.0
                )
                self.on_files_loaded(files)
            except asyncio.TimeoutError:
                logger.error(f"Timeout listing directory {self.current_path}")
                self.on_list_error(f"Timeout listing directory {self.current_path}")
            except Exception as e:
                logger.error(f"Failed to list directory {self.current_path}: {e}", exc_info=True)
                self.on_list_error(str(e))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_refresh())
            else:
                logger.warning("Event loop not running, cannot refresh remote file pane.")
        except Exception as e:
            logger.error(f"Error scheduling refresh task: {e}", exc_info=True)
    
    def go_up(self) -> None:
        """Go up one directory."""
        if self.current_path != "/":
            parent = str(Path(self.current_path).parent)
            if parent == ".":
                parent = "/"
            self.navigate_to(parent)
    
    def update_path_display(self) -> None:
        """Update path display."""
        self.path_edit.setText(self.current_path)
    
    @pyqtSlot(list)
    def on_files_loaded(self, files: List[RemoteFile]) -> None:
        """Handle files loaded."""
        try:
            # Filter hidden files if needed
            if not self.show_hidden:
                files = [f for f in files if not f.is_hidden]
            
            self.model.set_files(files)
            self.update_display()
        except Exception as e:
            logger.error(f"Error handling loaded files: {e}")
            # Don't crash, just show an error message
            self.on_list_error(f"Error displaying files: {e}")
    
    @pyqtSlot(str)
    def on_list_error(self, error: str) -> None:
        """Handle list error."""
        QMessageBox.critical(self, "Error", f"Failed to list directory: {error}")
    
    def update_display(self) -> None:
        """Update tree view display."""
        try:
            self.tree_view.clear()
            
            # Add parent directory entry
            if self.current_path != "/":
                parent_item = QTreeWidgetItem([".. (Parent Directory)", "", "", "Directory"])
                parent_item.setData(0, Qt.ItemDataRole.UserRole, "..")
                self.tree_view.addTopLevelItem(parent_item)
            
            # Add files
            for file in self.model.get_files():
                try:
                    size_str = self.format_size(file.size) if file.size > 0 else ""
                    modified_str = ""
                    if file.modified:
                        try:
                            modified_str = file.modified.strftime("%Y-%m-%d %H:%M")
                        except (ValueError, AttributeError):
                            modified_str = ""
                    
                    type_str = "Directory" if file.is_directory else "File"
                    
                    item = QTreeWidgetItem([file.name or "unknown", size_str, modified_str, type_str])
                    item.setData(0, Qt.ItemDataRole.UserRole, file) # Store the whole RemoteFile object
                    
                    # Set icon based on type
                    if file.is_directory:
                        # You could set a folder icon here
                        pass
                    
                    self.tree_view.addTopLevelItem(item)
                    
                except Exception as e:
                    logger.warning(f"Error adding file {file.name if file else 'unknown'} to display: {e}")
                    # Skip this file but continue with others
                    continue
                    
        except Exception as e:
            logger.error(f"Error updating file display: {e}")
            # Clear the display and show error message
            self.tree_view.clear()
            error_item = QTreeWidgetItem(["Error loading files", "", "", ""])
            self.tree_view.addTopLevelItem(error_item)
    
    def format_size(self, size: int) -> str:
        """Format file size for display."""
        if size == 0:
            return ""
        
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        size_float = float(size)
        
        while size_float >= 1024 and unit_index < len(units) - 1:
            size_float /= 1024
            unit_index += 1
        
        return f"{size_float:.1f} {units[unit_index]}"
    
    def on_double_click(self, index) -> None:
        """Handle double click on remote item."""
        current_item = self.tree_view.currentItem()
        if not current_item:
            return
        
        item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data:
            return
        
        if item_data == "..":
            self.go_up()
        elif isinstance(item_data, RemoteFile) and item_data.is_directory:
            self.navigate_to(item_data.path)
    
    def on_item_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double click on tree widget item."""
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data:
            return
        
        if item_data == "..":
            self.go_up()
        elif isinstance(item_data, RemoteFile) and item_data.is_directory:
            self.navigate_to(item_data.path)
    
    def show_context_menu(self, position) -> None:
        """Show context menu for remote files."""
        item = self.tree_view.itemAt(position)
        if not item:
            return

        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, RemoteFile):
            return

        remote_file = item_data
        menu = QMenu(self)
        
        download_action = QAction("Download", self)
        download_action.triggered.connect(lambda: self.request_download(remote_file))
        menu.addAction(download_action)
        
        menu.addSeparator()
        
        new_folder_action = QAction("New Folder", self)
        new_folder_action.triggered.connect(self.create_remote_folder)
        menu.addAction(new_folder_action)
        
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(lambda: self.delete_remote_file(remote_file))
        menu.addAction(delete_action)
        
        rename_action = QAction("Rename", self)
        rename_action.triggered.connect(lambda: self.rename_remote_file(remote_file))
        menu.addAction(rename_action)
        
        menu.exec(self.tree_view.mapToGlobal(position))

    def request_download(self, remote_file: RemoteFile) -> None:
        """Request download of a remote file."""
        # The local path is just the filename; the ConnectionTab will build the full path
        self.transfer_requested.emit("download", remote_file.name, remote_file.path)

    def delete_remote_file(self, file_to_delete: RemoteFile) -> None:
        """Delete a remote file or directory."""
        if not self.session:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{file_to_delete.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        async def _delete():
            try:
                if file_to_delete.is_directory:
                    await self.session.rmdir(file_to_delete.path)
                else:
                    await self.session.remove(file_to_delete.path)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

        loop = asyncio.get_event_loop()
        loop.create_task(_delete())

    def rename_remote_file(self, file_to_rename: RemoteFile) -> None:
        """Rename a remote file or directory."""
        if not self.session:
            return

        old_name = file_to_rename.name
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)

        if ok and new_name and new_name != old_name:
            old_path = file_to_rename.path
            new_path = str(Path(old_path).parent / new_name)

            async def _rename():
                try:
                    await self.session.rename(old_path, new_path)
                    self.refresh()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to rename: {e}")

            loop = asyncio.get_event_loop()
            loop.create_task(_rename())
    
    def create_remote_folder(self) -> None:
        """Create remote folder."""
        if not self.session:
            return
        
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            try:
                # Use the current event loop
                loop = asyncio.get_event_loop()
                
                async def create_folder():
                    try:
                        remote_path = f"{self.current_path.rstrip('/')}/{name}"
                        await asyncio.wait_for(self.session.mkdir(remote_path), timeout=10.0)
                        # Refresh after creation
                        QTimer.singleShot(100, self.refresh)
                    except asyncio.TimeoutError:
                        QMessageBox.critical(self, "Error", "Timeout creating folder")
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to create folder: {e}")
                
                loop.create_task(create_folder())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to schedule folder creation: {e}")