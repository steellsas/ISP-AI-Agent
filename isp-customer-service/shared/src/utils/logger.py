"""
Logging Configuration
Centralized logging setup for all services
"""

import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------
# Customer phone numbers are direct personal identifiers (GDPR). They must not
# land in plain text in log files. We mask them centrally so the protection is
# automatic everywhere and survives refactors — see PiiRedactionFilter below.
#
# Traceability is preserved two ways:
#   1. The last 4 digits are kept (+37060012345 -> ***2345), enough to confirm
#      "is this the number ending 2345 the customer gave?" or spot a wrong one.
#   2. Redaction is gated by the REDACT_PII env flag (default on). During local
#      testing set REDACT_PII=false to see full numbers — clear text never
#      leaves your machine, deployed environments stay masked by default.

# Lithuanian phone shapes: +370 + 8 digits, or local 8 + 8 digits, tolerating
# spaces / dashes as separators. Dots (IP addresses) and colons (MAC) are NOT
# accepted as separators, and the leading +370/8 anchor keeps CUST-IDs, ticket
# IDs and IPs from matching.
_PHONE_RE = re.compile(r"(?:\+370|8)(?:[\s-]?\d){8}")

_PII_DISABLED_VALUES = {"0", "false", "no", "off"}


def _redaction_enabled() -> bool:
    """True unless REDACT_PII is explicitly turned off (read live, so tests and
    local runs can toggle it without re-importing)."""
    return os.getenv("REDACT_PII", "true").strip().lower() not in _PII_DISABLED_VALUES


def redact_phone(text: str, *, enabled: bool | None = None) -> str:
    """Mask Lithuanian phone numbers in ``text``, keeping the last 4 digits.

    Use this for any string that may be surfaced outside the central log filter
    (e.g. an error message returned to the caller). ``enabled=None`` defers to
    the REDACT_PII env flag; pass an explicit bool to force behaviour.
    """
    if enabled is None:
        enabled = _redaction_enabled()
    if not enabled or not text:
        return text

    def _mask(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return "***" + digits[-4:]

    return _PHONE_RE.sub(_mask, text)


class PiiRedactionFilter(logging.Filter):
    """Logging filter that redacts phone numbers from every record.

    Attached to *handlers* (not loggers) so it also covers records that
    propagate up from child module loggers such as ``agent.tools``. It formats
    the record once and clears ``args`` so the downstream formatter does not
    re-expand the unredacted arguments.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not _redaction_enabled():
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True
        record.msg = redact_phone(message, enabled=True)
        record.args = ()
        return True


def _attach_pii_filter(handler: logging.Handler) -> None:
    """Idempotently add a PiiRedactionFilter to a handler."""
    if not any(isinstance(f, PiiRedactionFilter) for f in handler.filters):
        handler.addFilter(PiiRedactionFilter())


def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Path | None = None,
    format_string: str | None = None,
    use_stderr: bool = False,  # ← NEW: For MCP servers
) -> logging.Logger:
    """
    Setup logger with consistent configuration.

    Args:
        name: Logger name (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for logging
        format_string: Optional custom format string
        use_stderr: Use stderr instead of stdout (required for MCP stdio servers)

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
            "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
        )

    formatter = logging.Formatter(format_string)

    # Console handler - stdout OR stderr
    stream = sys.stderr if use_stderr else sys.stdout
    console_handler = logging.StreamHandler(stream)
    console_handler.setFormatter(formatter)
    _attach_pii_filter(console_handler)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        _attach_pii_filter(file_handler)
        logger.addHandler(file_handler)

    # Also guard any handlers already on the root logger (e.g. installed by an
    # earlier logging.basicConfig). Child module loggers like ``agent.tools``
    # propagate their records to root, so the redaction must live there too.
    for root_handler in logging.getLogger().handlers:
        _attach_pii_filter(root_handler)

    return logger


_original_record_factory = logging.getLogRecordFactory()
_factory_installed = False


def _pii_record_factory(*args, **kwargs) -> logging.LogRecord:
    """LogRecord factory wrapper that redacts phone numbers at record creation.

    The codebase logs with f-strings, so PII is already baked into ``record.msg``
    when the record is built (``record.args`` is empty). Redacting here therefore
    covers *every* logger in the process — including module loggers that only
    propagate to a root handler configured by Streamlit or basicConfig, which a
    handler-level filter alone would miss.
    """
    record = _original_record_factory(*args, **kwargs)
    if not _redaction_enabled():
        return record
    try:
        if record.args:
            # %-style log: merge args first, then redact and clear them.
            record.msg = redact_phone(record.getMessage(), enabled=True)
            record.args = ()
        elif isinstance(record.msg, str):
            record.msg = redact_phone(record.msg, enabled=True)
    except Exception:
        pass
    return record


def install_pii_redaction() -> None:
    """Install process-wide phone-number redaction for logging.

    Sets a LogRecord factory (covers every logger, regardless of how its
    handlers were configured) and also attaches the filter to any existing
    root-logger handlers. Idempotent — safe to call from multiple entry points
    (Streamlit app startup, CLI ``__main__`` blocks, tests).
    """
    global _factory_installed
    if not _factory_installed:
        logging.setLogRecordFactory(_pii_record_factory)
        _factory_installed = True
    for root_handler in logging.getLogger().handlers:
        _attach_pii_filter(root_handler)


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


def setup_crm_logger(level: str = "INFO", use_stderr: bool = True) -> logging.Logger:
    """
    Setup logger for CRM service.

    Args:
        level: Log level
        use_stderr: Use stderr (True for MCP stdio, False for standalone)
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    return setup_logger(
        "crm_service",
        level=level,
        log_file=log_dir / f"crm_{datetime.now().strftime('%Y%m%d')}.log",
        use_stderr=use_stderr,  # ← MCP requires stderr!
    )


def setup_network_logger(level: str = "INFO", use_stderr: bool = True) -> logging.Logger:
    """
    Setup logger for Network Diagnostic service.

    Args:
        level: Log level
        use_stderr: Use stderr (True for MCP stdio, False for standalone)
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    return setup_logger(
        "network_service",
        level=level,
        log_file=log_dir / f"network_{datetime.now().strftime('%Y%m%d')}.log",
        use_stderr=use_stderr,  # ← MCP requires stderr!
    )


def setup_chatbot_logger(level: str = "INFO") -> logging.Logger:
    """
    Setup logger for Chatbot Core.

    Args:
        level: Log level
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    return setup_logger(
        "chatbot_core",
        level=level,
        log_file=log_dir / f"chatbot_{datetime.now().strftime('%Y%m%d')}.log",
        use_stderr=False,  # Chatbot can use stdout
    )


def setup_mcp_server_logger(
    name: str, level: str = "INFO", log_file: Path | None = None
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
        use_stderr=True,  # ← CRITICAL for MCP!
    )
