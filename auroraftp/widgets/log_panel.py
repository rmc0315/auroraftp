"""Log panel widget for displaying application logs."""

import logging
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.events import event_bus


class LogHandler(logging.Handler):
    """Custom log handler that emits signals."""
    
    def __init__(self, log_panel):
        super().__init__()
        self.log_panel = log_panel
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record."""
        try:
            msg = self.format(record)
            self.log_panel.add_log_message(record.levelname, msg)
        except Exception:
            self.handleError(record)


class LogPanel(QWidget):
    """Log panel widget."""
    
    def __init__(self):
        super().__init__()
        self.max_lines = 1000
        self.current_level = "INFO"
        
        self.setup_ui()
        self.setup_logging()
        self.connect_signals()
    
    def setup_ui(self) -> None:
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        # Log level filter
        toolbar_layout.addWidget(QLabel("Level:"))
        
        self.level_combo = QComboBox()
        self.level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_combo.setCurrentText("INFO")
        self.level_combo.currentTextChanged.connect(self.on_level_changed)
        toolbar_layout.addWidget(self.level_combo)
        
        toolbar_layout.addStretch()
        
        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_logs)
        toolbar_layout.addWidget(self.clear_button)
        
        # Copy button
        self.copy_button = QPushButton("Copy All")
        self.copy_button.clicked.connect(self.copy_logs)
        toolbar_layout.addWidget(self.copy_button)
        
        layout.addLayout(toolbar_layout)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_text.customContextMenuRequested.connect(self.show_context_menu)
        
        # Use monospace font
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_text.setFont(font)
        
        layout.addWidget(self.log_text)
    
    def setup_logging(self) -> None:
        """Setup logging handler."""
        # Create custom handler
        self.log_handler = LogHandler(self)
        self.log_handler.setLevel(logging.DEBUG)
        
        # Format logs
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        self.log_handler.setFormatter(formatter)
        
        # Add to root logger
        root_logger = logging.getLogger("auroraftp")
        root_logger.addHandler(self.log_handler)
    
    def connect_signals(self) -> None:
        """Connect event bus signals."""
        event_bus.log_message.connect(self.on_log_message)
    
    @pyqtSlot(str)
    def on_level_changed(self, level: str) -> None:
        """Handle log level change."""
        self.current_level = level
        # Could implement filtering here
    
    @pyqtSlot(str, str, str)
    def on_log_message(self, level: str, message: str, details: str) -> None:
        """Handle log message from event bus."""
        self.add_log_message(level, message, details)
    
    def add_log_message(self, level: str, message: str, details: str = "") -> None:
        """Add log message to display."""
        # Check if level should be displayed
        level_priority = {
            "DEBUG": 0,
            "INFO": 1,
            "WARNING": 2,
            "ERROR": 3,
            "CRITICAL": 4,
        }
        
        current_priority = level_priority.get(self.current_level, 1)
        message_priority = level_priority.get(level, 1)
        
        if message_priority < current_priority:
            return
        
        # Format message
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {level}: {message}"
        
        if details:
            formatted_message += f" - {details}"
        
        # Add to text widget
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Set color based on level
        if level == "ERROR" or level == "CRITICAL":
            self.log_text.setTextColor(Qt.GlobalColor.red)
        elif level == "WARNING":
            self.log_text.setTextColor(Qt.GlobalColor.darkYellow)
        elif level == "DEBUG":
            self.log_text.setTextColor(Qt.GlobalColor.gray)
        else:
            self.log_text.setTextColor(Qt.GlobalColor.black)
        
        cursor.insertText(formatted_message + "\n")
        
        # Reset color
        self.log_text.setTextColor(Qt.GlobalColor.black)
        
        # Scroll to bottom
        self.log_text.ensureCursorVisible()
        
        # Limit number of lines
        self.limit_lines()
    
    def limit_lines(self) -> None:
        """Limit number of lines in log display."""
        document = self.log_text.document()
        if document.lineCount() > self.max_lines:
            # Remove lines from beginning
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            
            # Select lines to remove
            lines_to_remove = document.lineCount() - self.max_lines + 100  # Remove extra
            for _ in range(lines_to_remove):
                cursor.select(QTextCursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()  # Remove newline
    
    def clear_logs(self) -> None:
        """Clear all log messages."""
        self.log_text.clear()
    
    def copy_logs(self) -> None:
        """Copy all logs to clipboard."""
        from PyQt6.QtGui import QGuiApplication
        
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self.log_text.toPlainText())
    
    def show_context_menu(self, position) -> None:
        """Show context menu."""
        menu = QMenu(self)
        
        # Copy selection
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.log_text.copy)
        copy_action.setEnabled(self.log_text.textCursor().hasSelection())
        menu.addAction(copy_action)
        
        # Copy all
        copy_all_action = QAction("Copy All", self)
        copy_all_action.triggered.connect(self.copy_logs)
        menu.addAction(copy_all_action)
        
        menu.addSeparator()
        
        # Clear
        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear_logs)
        menu.addAction(clear_action)
        
        menu.exec(self.log_text.mapToGlobal(position))