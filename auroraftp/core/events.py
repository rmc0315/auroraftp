"""Event system for inter-component communication."""

from typing import Any, Callable, Dict, List
from uuid import UUID

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """Central event bus for application-wide communication."""
    
    # Connection events
    connection_started = pyqtSignal(UUID)  # site_id
    connection_established = pyqtSignal(UUID, str)  # site_id, server_info
    connection_failed = pyqtSignal(UUID, str)  # site_id, error_message
    connection_closed = pyqtSignal(UUID)  # site_id
    
    # Directory events
    directory_changed = pyqtSignal(UUID, str)  # site_id, new_path
    directory_listing_updated = pyqtSignal(UUID, str, list)  # site_id, path, files
    directory_listing_failed = pyqtSignal(UUID, str, str)  # site_id, path, error
    
    # Transfer events
    transfer_added = pyqtSignal(UUID)  # transfer_id
    transfer_started = pyqtSignal(UUID)  # transfer_id
    transfer_progress = pyqtSignal(UUID, int, int)  # transfer_id, transferred, total
    transfer_completed = pyqtSignal(UUID)  # transfer_id
    transfer_failed = pyqtSignal(UUID, str)  # transfer_id, error_message
    transfer_paused = pyqtSignal(UUID)  # transfer_id
    transfer_resumed = pyqtSignal(UUID)  # transfer_id
    transfer_cancelled = pyqtSignal(UUID)  # transfer_id
    
    # Queue events
    queue_started = pyqtSignal()
    queue_paused = pyqtSignal()
    queue_completed = pyqtSignal()
    queue_cleared = pyqtSignal()
    
    # File operation events
    file_created = pyqtSignal(UUID, str, str)  # site_id, parent_path, name
    file_deleted = pyqtSignal(UUID, str)  # site_id, path
    file_renamed = pyqtSignal(UUID, str, str)  # site_id, old_path, new_path
    file_permissions_changed = pyqtSignal(UUID, str, str)  # site_id, path, permissions
    
    # Sync events
    sync_started = pyqtSignal(UUID)  # profile_id
    sync_progress = pyqtSignal(UUID, int, int)  # profile_id, current, total
    sync_completed = pyqtSignal(UUID, dict)  # profile_id, results
    sync_failed = pyqtSignal(UUID, str)  # profile_id, error_message
    
    # Configuration events
    site_added = pyqtSignal(UUID)  # site_id
    site_updated = pyqtSignal(UUID)  # site_id
    site_deleted = pyqtSignal(UUID)  # site_id
    config_updated = pyqtSignal(str)  # setting_name
    
    # Log events
    log_message = pyqtSignal(str, str, str)  # level, message, details
    
    # UI events
    status_message = pyqtSignal(str, int)  # message, timeout_ms
    error_message = pyqtSignal(str, str)  # title, message
    
    def __init__(self):
        super().__init__()
        self._handlers: Dict[str, List[Callable]] = {}
    
    def emit_status(self, message: str, timeout: int = 5000) -> None:
        """Emit status bar message."""
        self.status_message.emit(message, timeout)
    
    def emit_error(self, title: str, message: str) -> None:
        """Emit error message."""
        self.error_message.emit(title, message)
    
    def emit_log(self, level: str, message: str, details: str = "") -> None:
        """Emit log message."""
        self.log_message.emit(level, message, details)


# Global event bus instance
event_bus = EventBus()