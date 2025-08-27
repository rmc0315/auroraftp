"""Structured logging configuration."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

from ..core.config import get_config_manager


class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts sensitive information."""
    
    SENSITIVE_PATTERNS = [
        "password",
        "passwd", 
        "secret",
        "token",
        "key",
        "auth",
        "credential",
    ]
    
    def format(self, record: logging.LogRecord) -> str:
        # Create a copy of the record to avoid modifying the original
        record_copy = logging.makeLogRecord(record.__dict__)
        
        # Redact sensitive information from message
        message = record_copy.getMessage()
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in message.lower():
                # Simple redaction - replace with [REDACTED]
                import re
                message = re.sub(
                    rf'({pattern}["\s]*[:=]["\s]*)([^"\s,\}}\]]+)',
                    r'\1[REDACTED]',
                    message,
                    flags=re.IGNORECASE
                )
        
        record_copy.msg = message
        record_copy.args = ()
        
        return super().format(record_copy)


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    console_output: bool = True,
    file_output: bool = True,
) -> None:
    """Setup application logging."""
    
    # Get log directory
    if log_dir is None:
        config_manager = get_config_manager()
        log_dir = config_manager.log_dir
    
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create root logger
    root_logger = logging.getLogger("auroraftp")
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with Rich
    if console_output:
        console = Console(stderr=True)
        console_handler = RichHandler(
            console=console,
            show_time=True,
            show_level=True,
            show_path=False,
            markup=True,
            rich_tracebacks=True,
        )
        console_handler.setLevel(getattr(logging, level.upper()))
        
        console_formatter = SensitiveFormatter(
            "%(message)s"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if file_output:
        log_file = log_dir / "auroraftp.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)
        
        file_formatter = SensitiveFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Set levels for external libraries
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    logging.getLogger("aioftp").setLevel(logging.WARNING)
    logging.getLogger("PyQt6").setLevel(logging.WARNING)
    
    root_logger.info(f"Logging configured - Level: {level}, File: {file_output}, Console: {console_output}")


class SessionLogger:
    """Per-session logger for protocol operations."""
    
    def __init__(self, site_name: str, site_id: str):
        self.site_name = site_name
        self.site_id = site_id
        self.logger = logging.getLogger(f"auroraftp.session.{site_name}")
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(f"[{self.site_name}] {message}", extra={"site_id": self.site_id, **kwargs})
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(f"[{self.site_name}] {message}", extra={"site_id": self.site_id, **kwargs})
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(f"[{self.site_name}] {message}", extra={"site_id": self.site_id, **kwargs})
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(f"[{self.site_name}] {message}", extra={"site_id": self.site_id, **kwargs})


class TransferLogger:
    """Logger for transfer operations."""
    
    def __init__(self, transfer_id: str):
        self.transfer_id = transfer_id
        self.logger = logging.getLogger("auroraftp.transfer")
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(f"[Transfer {self.transfer_id[:8]}] {message}", 
                        extra={"transfer_id": self.transfer_id, **kwargs})
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(f"[Transfer {self.transfer_id[:8]}] {message}", 
                           extra={"transfer_id": self.transfer_id, **kwargs})
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(f"[Transfer {self.transfer_id[:8]}] {message}", 
                         extra={"transfer_id": self.transfer_id, **kwargs})
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(f"[Transfer {self.transfer_id[:8]}] {message}", 
                         extra={"transfer_id": self.transfer_id, **kwargs})


def get_session_logger(site_name: str, site_id: str) -> SessionLogger:
    """Get session logger for a site."""
    return SessionLogger(site_name, site_id)


def get_transfer_logger(transfer_id: str) -> TransferLogger:
    """Get transfer logger for a transfer."""
    return TransferLogger(transfer_id)