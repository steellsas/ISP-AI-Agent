"""
Logging Configuration
Centralized logging setup for all services
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Setup logger with consistent configuration.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging
        format_string: Optional custom format string
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Default format
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        )
    
    formatter = logging.Formatter(format_string)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance with default configuration.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Service-specific logger setup functions

def setup_crm_logger(level: str = "INFO") -> logging.Logger:
    """Setup logger for CRM service."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    return setup_logger(
        "crm_service",
        level=level,
        log_file=log_dir / f"crm_{datetime.now().strftime('%Y%m%d')}.log"
    )


def setup_network_logger(level: str = "INFO") -> logging.Logger:
    """Setup logger for Network Diagnostic service."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    return setup_logger(
        "network_service",
        level=level,
        log_file=log_dir / f"network_{datetime.now().strftime('%Y%m%d')}.log"
    )


def setup_chatbot_logger(level: str = "INFO") -> logging.Logger:
    """Setup logger for Chatbot Core."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    return setup_logger(
        "chatbot_core",
        level=level,
        log_file=log_dir / f"chatbot_{datetime.now().strftime('%Y%m%d')}.log"
    )