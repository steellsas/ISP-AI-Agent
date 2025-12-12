"""
Logging Configuration
Centralized logging setup for all services

Features:
- Service-specific loggers (CRM, Network, Chatbot)
- MCP stdio server support (stderr for JSON-RPC compatibility)
- Sensitive data filtering (API keys, phone numbers)
- Rotating file handler
- Convenience functions for structured logging
"""

import os
import sys
import re
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from datetime import datetime


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default log directory (relative to project root)
DEFAULT_LOG_DIR = Path("logs")

# File rotation settings
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

# Default format
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# =============================================================================
# SENSITIVE DATA FILTER
# =============================================================================

class SensitiveDataFilter(logging.Filter):
    """Filter out sensitive data from logs."""
    
    SENSITIVE_PATTERNS = [
        # API keys (partial match)
        ("sk-", "[API_KEY]"),
        ("api_key", "[API_KEY]"),
        ("OPENAI_API_KEY", "[API_KEY]"),
        ("ANTHROPIC_API_KEY", "[API_KEY]"),
        ("GOOGLE_API_KEY", "[API_KEY]"),
    ]
    
    def filter(self, record):
        """Mask sensitive data in log messages."""
        if isinstance(record.msg, str):
            msg = record.msg
            
            # Mask API keys
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                if pattern.lower() in msg.lower():
                    msg = self._mask_key_value(msg, pattern)
            
            # Mask phone numbers (keep last 4 digits)
            msg = self._mask_phone_numbers(msg)
            
            record.msg = msg
        
        return True
    
    def _mask_key_value(self, msg: str, pattern: str) -> str:
        """Mask API key values."""
        # Match patterns like sk-xxx or key=xxx
        key_pattern = rf'({pattern}["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_-]+)(["\']?)'
        return re.sub(key_pattern, r'\1[REDACTED]\3', msg, flags=re.IGNORECASE)
    
    def _mask_phone_numbers(self, msg: str) -> str:
        """Mask phone numbers, keeping last 4 digits."""
        # Lithuanian phone format: +370xxxxxxxx
        phone_pattern = r'(\+370)(\d{4})(\d{4})'
        return re.sub(phone_pattern, r'\1****\3', msg)


# =============================================================================
# CORE LOGGER SETUP
# =============================================================================

def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
    use_stderr: bool = False,
    use_rotation: bool = True,
    filter_sensitive: bool = True,
) -> logging.Logger:
    """
    Setup logger with consistent configuration.

    Args:
        name: Logger name (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging
        format_string: Optional custom format string
        use_stderr: Use stderr instead of stdout (required for MCP stdio servers)
        use_rotation: Use rotating file handler (default True)
        filter_sensitive: Filter sensitive data like API keys (default True)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Format
    if format_string is None:
        format_string = DEFAULT_FORMAT

    formatter = logging.Formatter(format_string, DEFAULT_DATE_FORMAT)

    # Sensitive data filter
    sensitive_filter = SensitiveDataFilter() if filter_sensitive else None

    # Console handler - stdout OR stderr
    stream = sys.stderr if use_stderr else sys.stdout
    console_handler = logging.StreamHandler(stream)
    console_handler.setFormatter(formatter)
    if sensitive_filter:
        console_handler.addFilter(sensitive_filter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        if use_rotation:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=MAX_FILE_SIZE,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
        else:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
        
        file_handler.setFormatter(formatter)
        if sensitive_filter:
            file_handler.addFilter(sensitive_filter)
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


# =============================================================================
# GLOBAL LOGGING SETUP (for Streamlit app)
# =============================================================================

_global_logging_initialized = False


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    log_file: str = "app.log",
):
    """
    Initialize global logging system (singleton).
    
    Call once at application startup. Sets up:
    - Console handler (INFO level)
    - Rotating file handler (all logs)
    - Quiets noisy libraries
    
    Args:
        level: Log level (DEBUG, INFO, etc.)
        log_dir: Log directory (default: logs/)
        log_file: Log filename (default: app.log)
    """
    global _global_logging_initialized
    
    if _global_logging_initialized:
        return
    
    log_dir = log_dir or DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    
    formatter = logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT)
    sensitive_filter = SensitiveDataFilter()
    
    # Console handler
    console_level = logging.DEBUG if os.getenv("DEBUG", "").lower() == "true" else logging.INFO
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)
    
    # File handler (rotating)
    file_path = log_dir / log_file
    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)
    root_logger.addHandler(file_handler)
    
    # Quiet noisy libraries
    for lib in ["httpx", "httpcore", "urllib3", "openai", "anthropic", "litellm"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
    
    _global_logging_initialized = True
    
    # Log startup
    logger = logging.getLogger("utils.logger")
    logger.info("=" * 60)
    logger.info(f"Logging initialized at {datetime.now().isoformat()}")
    logger.info(f"Log file: {file_path}")
    logger.info("=" * 60)


# =============================================================================
# SERVICE-SPECIFIC LOGGER SETUP
# =============================================================================

def setup_crm_logger(level: str = "INFO", use_stderr: bool = True) -> logging.Logger:
    """
    Setup logger for CRM service.

    Args:
        level: Log level
        use_stderr: Use stderr (True for MCP stdio, False for standalone)
    """
    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(exist_ok=True)

    return setup_logger(
        "crm_service",
        level=level,
        log_file=log_dir / f"crm_{datetime.now().strftime('%Y%m%d')}.log",
        use_stderr=use_stderr,
    )


def setup_network_logger(level: str = "INFO", use_stderr: bool = True) -> logging.Logger:
    """
    Setup logger for Network Diagnostic service.

    Args:
        level: Log level
        use_stderr: Use stderr (True for MCP stdio, False for standalone)
    """
    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(exist_ok=True)

    return setup_logger(
        "network_service",
        level=level,
        log_file=log_dir / f"network_{datetime.now().strftime('%Y%m%d')}.log",
        use_stderr=use_stderr,
    )


def setup_chatbot_logger(level: str = "INFO") -> logging.Logger:
    """
    Setup logger for Chatbot Core.

    Args:
        level: Log level
    """
    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(exist_ok=True)

    return setup_logger(
        "chatbot_core",
        level=level,
        log_file=log_dir / f"chatbot_{datetime.now().strftime('%Y%m%d')}.log",
        use_stderr=False,
    )


def setup_mcp_server_logger(
    name: str, level: str = "INFO", log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Setup logger specifically for MCP stdio servers.

    IMPORTANT: MCP servers MUST use stderr for logging, not stdout!
    stdout is reserved for JSON-RPC protocol messages.

    Args:
        name: Logger name
        level: Log level
        log_file: Optional log file path

    Returns:
        Configured logger with stderr output
    """
    return setup_logger(
        name=name,
        level=level,
        log_file=log_file,
        use_stderr=True,
    )


# =============================================================================
# CONVENIENCE LOGGING FUNCTIONS
# =============================================================================

def log_agent_action(action: str, details: dict = None):
    """Log agent action with structured data."""
    logger = get_logger("agent.action")
    
    msg = f"ACTION: {action}"
    if details:
        details_str = " | ".join(f"{k}={v}" for k, v in details.items())
        msg += f" | {details_str}"
    
    logger.info(msg)


def log_tool_call(tool_name: str, params: dict, result: dict):
    """Log tool execution."""
    logger = get_logger("agent.tools")
    
    success = result.get("success", True)
    level = logging.INFO if success else logging.WARNING
    
    logger.log(level, f"TOOL: {tool_name} | params={params} | success={success}")


def log_llm_call(model: str, tokens: int, cost: float, latency_ms: float):
    """Log LLM API call."""
    logger = get_logger("agent.llm")
    
    logger.info(f"LLM: {model} | tokens={tokens} | cost=${cost:.4f} | latency={latency_ms:.0f}ms")


def log_error(error: Exception, context: str = None):
    """Log error with full traceback."""
    logger = get_logger("agent.error")
    
    msg = f"ERROR: {type(error).__name__}: {error}"
    if context:
        msg = f"{context} | {msg}"
    
    logger.error(msg, exc_info=True)