"""FAQ loader — the KNOWN ANSWERS for side-topic questions (2026-08-07).

The side_topic node may only answer off-fault questions from THIS file: a
matched entry's `atsakymas` is the whole permitted content; no match means
"ne mano sritis" + the return anchor. Fail-soft like every knowledge loader.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATH = Path(__file__).resolve().parent / "knowledge" / "faq.yaml"


@lru_cache(maxsize=1)
def _entries() -> list[dict[str, Any]]:
    try:
        import yaml

        data = yaml.safe_load(_PATH.read_text(encoding="utf-8")) or {}
        items = data.get("faq") if isinstance(data, dict) else None
        return [i for i in (items or []) if isinstance(i, dict) and i.get("atsakymas")]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"faq.yaml not loaded ({e})")
        return []


def reload() -> None:
    _entries.cache_clear()


def match(text: str | None) -> list[dict[str, Any]]:
    """FAQ entries whose keywords appear in the utterance (usually 0 or 1)."""
    if not text:
        return []
    low = text.lower()
    return [
        e for e in _entries() if any(str(k).lower() in low for k in (e.get("raktazodziai") or []))
    ]
