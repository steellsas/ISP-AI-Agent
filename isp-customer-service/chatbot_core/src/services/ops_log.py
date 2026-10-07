"""Operations log: WHY the agent did not work, apart from WHAT was said.

The conversation lives in `logs/sessions/<id>.jsonl` (the trace). This file is the
other question — a provider that refused, a model that fell back, a socket that
dropped, an ASR/TTS call that failed — so an incident is found without reading
dialogues, and a dialogue is read without wading through connection noise.

    logs/ops/ops.log      rotated at midnight, 14 days kept

Two kinds of lines land here:
  1. explicit events: `ops_log.event("llm", "fallback", model=..., error=...)`
  2. every WARNING+ record of any logger (the adapters already log their failures
     as warnings/exceptions — they reach this file without being touched).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

logger = logging.getLogger("ops")

_ROOT = Path(__file__).resolve().parents[3]
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def _log_dir() -> Path:
    env = os.getenv("OPS_LOG_DIR")
    return Path(env) if env else _ROOT / "logs" / "ops"


def _short(value: object, limit: int = 300) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def event(component: str, what: str, level: int = logging.WARNING, **fields: object) -> None:
    """One operations event: `[llm] fallback model=… to=… error=…`."""
    details = " ".join(f"{k}={_short(v)}" for k, v in fields.items() if v is not None)
    logger.log(level, f"[{component}] {what} {details}".rstrip())


class _OpsFilter(logging.Filter):
    """The ops logger at any level; everything else only from WARNING up."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "ops" or record.levelno >= logging.WARNING


_installed = False


def install() -> Path | None:
    """Attach the ops file to the root logger (idempotent). Returns its path."""
    global _installed
    if _installed:
        return _log_dir() / "ops.log"
    try:
        path = _log_dir() / "ops.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(path, when="midnight", backupCount=14, encoding="utf-8")
    except OSError as e:  # pragma: no cover - a read-only disk must not stop the app
        logging.getLogger(__name__).warning(f"ops log unavailable: {e}")
        return None
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(_OpsFilter())
    try:  # phone numbers are masked in this file like in every other (GDPR)
        from utils.logger import _attach_pii_filter

        _attach_pii_filter(handler)
    except ImportError:  # pragma: no cover - shared/ not on the path
        pass
    root = logging.getLogger()
    if not root.handlers:
        # With no root handler Python printed warnings via its last-resort stderr
        # handler; adding the file alone would silence the console. Keep it.
        console = logging.StreamHandler()
        console.setLevel(logging.WARNING)
        console.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(console)
    root.addHandler(handler)
    logger.setLevel(logging.INFO)
    _installed = True
    return path
