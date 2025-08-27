"""Transfer queue widget."""

import logging
from typing import Dict, Optional

from PyQt6.QtCore import QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.events import event_bus
from ..core.models import TransferItem, TransferStatus
from ..services import TransferManager

logger = logging.getLogger(__name__)


class TransferQueueWidget(QWidget):
    """Transfer queue widget with progress display."""
    
    def __init__(self, transfer_manager: TransferManager):
        super().__init__()
        self.transfer_manager = transfer_manager
        self.transfer_items: Dict[str, QTreeWidgetItem] = {}
        
        self.setup_ui()
        self.connect_signals()
        
        # Setup refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_transfers)
        self.refresh_timer.start(1000)  # Refresh every second
    
    def setup_ui(self) -> None:
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Transfer tree
        self.transfer_tree = QTreeWidget()
        self.transfer_tree.setHeaderLabels([
            "Name", "Status", "Progress", "Size", "Speed", "ETA", "Local Path", "Remote Path"
        ])
        self.transfer_tree.setRootIsDecorated(False)
        self.transfer_tree.setAlternatingRowColors(True)
        self.transfer_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.transfer_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.transfer_tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # Configure headers
        header = self.transfer_tree.header()
        header.setStretchLastSection(True)
        header.resizeSection(0, 200)  # Name
        header.resizeSection(1, 80)   # Status
        header.resizeSection(2, 100)  # Progress
        header.resizeSection(3, 80)   # Size
        header.resizeSection(4, 80)   # Speed
        header.resizeSection(5, 80)   # ETA
        
        layout.addWidget(self.transfer_tree)
    
    def connect_signals(self) -> None:
        """Connect event bus signals."""
        event_bus.transfer_added.connect(self.on_transfer_added)
        event_bus.transfer_started.connect(self.on_transfer_started)
        event_bus.transfer_progress.connect(self.on_transfer_progress)
        event_bus.transfer_completed.connect(self.on_transfer_completed)
        event_bus.transfer_failed.connect(self.on_transfer_failed)
        event_bus.transfer_paused.connect(self.on_transfer_paused)
        event_bus.transfer_resumed.connect(self.on_transfer_resumed)
        event_bus.transfer_cancelled.connect(self.on_transfer_cancelled)
    
    @pyqtSlot()
    def refresh_transfers(self) -> None:
        """Refresh transfer display."""
        transfers = self.transfer_manager.get_all_transfers()
        
        # Remove completed/cancelled transfers older than 5 minutes
        current_items = list(self.transfer_items.keys())
        for transfer_id in current_items:
            if transfer_id not in {str(t.id) for t in transfers}:
                item = self.transfer_items.pop(transfer_id)
                index = self.transfer_tree.indexOfTopLevelItem(item)
                if index >= 0:
                    self.transfer_tree.takeTopLevelItem(index)
        
        # Update existing transfers
        for transfer in transfers:
            self.update_transfer_item(transfer)
    
    def update_transfer_item(self, transfer: TransferItem) -> None:
        """Update or create transfer item."""
        transfer_id = str(transfer.id)
        
        if transfer_id not in self.transfer_items:
            # Create new item
            item = QTreeWidgetItem()
            self.transfer_items[transfer_id] = item
            self.transfer_tree.addTopLevelItem(item)
        else:
            item = self.transfer_items[transfer_id]
        
        # Update item data
        item.setText(0, transfer.local_path.name)  # Name
        item.setText(1, transfer.status.value.title())  # Status
        
        # Progress
        if transfer.size > 0:
            progress = int(transfer.progress * 100)
            item.setText(2, f"{progress}%")
        else:
            item.setText(2, "")
        
        # Size
        item.setText(3, self.format_size(transfer.size))
        
        # Speed (placeholder)
        item.setText(4, "")
        
        # ETA (placeholder)
        item.setText(5, "")
        
        # Paths
        item.setText(6, str(transfer.local_path))
        item.setText(7, transfer.remote_path)
        
        # Set item color based on status
        if transfer.status == TransferStatus.COMPLETED:
            item.setBackground(0, Qt.GlobalColor.green)
        elif transfer.status == TransferStatus.FAILED:
            item.setBackground(0, Qt.GlobalColor.red)
        elif transfer.status == TransferStatus.RUNNING:
            item.setBackground(0, Qt.GlobalColor.yellow)
        else:
            item.setBackground(0, Qt.GlobalColor.transparent)
    
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
    
    def show_context_menu(self, position) -> None:
        """Show context menu for transfers."""
        item = self.transfer_tree.itemAt(position)
        if not item:
            return
        
        # Find transfer
        transfer_id = None
        for tid, titem in self.transfer_items.items():
            if titem == item:
                transfer_id = tid
                break
        
        if not transfer_id:
            return
        
        transfer = self.transfer_manager.get_transfer(transfer_id)
        if not transfer:
            return
        
        menu = QMenu(self)
        
        # Pause/Resume
        if transfer.status == TransferStatus.RUNNING:
            pause_action = QAction("Pause", self)
            pause_action.triggered.connect(lambda: self.transfer_manager.pause_transfer(transfer.id))
            menu.addAction(pause_action)
        elif transfer.status in [TransferStatus.PENDING, TransferStatus.PAUSED]:
            resume_action = QAction("Resume", self)
            resume_action.triggered.connect(lambda: self.transfer_manager.resume_transfer(transfer.id))
            menu.addAction(resume_action)
        
        # Retry
        if transfer.status == TransferStatus.FAILED and transfer.can_retry:
            retry_action = QAction("Retry", self)
            retry_action.triggered.connect(lambda: self.transfer_manager.retry_transfer(transfer.id))
            menu.addAction(retry_action)
        
        # Remove
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self.transfer_manager.remove_transfer(transfer.id))
        menu.addAction(remove_action)
        
        menu.addSeparator()
        
        # Clear completed
        clear_action = QAction("Clear Completed", self)
        clear_action.triggered.connect(self.transfer_manager.clear_completed)
        menu.addAction(clear_action)
        
        menu.exec(self.transfer_tree.mapToGlobal(position))
    
    @pyqtSlot(object)
    def on_transfer_added(self, transfer_id) -> None:
        """Handle transfer added."""
        # Refresh will pick up new transfers
        pass
    
    @pyqtSlot(object)
    def on_transfer_started(self, transfer_id) -> None:
        """Handle transfer started."""
        # Refresh will update status
        pass
    
    @pyqtSlot(object, int, int)
    def on_transfer_progress(self, transfer_id, transferred, total) -> None:
        """Handle transfer progress."""
        # Refresh will update progress
        pass
    
    @pyqtSlot(object)
    def on_transfer_completed(self, transfer_id) -> None:
        """Handle transfer completed."""
        # Refresh will update status
        pass
    
    @pyqtSlot(object, str)
    def on_transfer_failed(self, transfer_id, error) -> None:
        """Handle transfer failed."""
        # Refresh will update status
        pass
    
    @pyqtSlot(object)
    def on_transfer_paused(self, transfer_id) -> None:
        """Handle transfer paused."""
        # Refresh will update status
        pass
    
    @pyqtSlot(object)
    def on_transfer_resumed(self, transfer_id) -> None:
        """Handle transfer resumed."""
        # Refresh will update status
        pass
    
    @pyqtSlot(object)
    def on_transfer_cancelled(self, transfer_id) -> None:
        """Handle transfer cancelled."""
        # Refresh will update status
        pass