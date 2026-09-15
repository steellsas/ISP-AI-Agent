"""
Locale — everything the caller hears, per language (`agent/locales/<lang>/`).

`phrases.yaml` is a nested map of sentences; code and knowledge files refer to a
sentence by its dotted key (`identification.ask_problem`,
`pack.router_hung.fail_scope.question`). `phrase(key, **vars)` renders one for the
active language. A language is loaded whole and checked at load: a missing
file or a non-text entry fails there, and an unknown key fails loudly instead of
speaking an empty line.

The active language is process-wide and set from AgentConfig.language.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
DEFAULT_LANGUAGE = "lt"


class LocaleError(Exception):
    """A locale that cannot be loaded or a phrase key it does not have."""


@dataclass(frozen=True)
class Locale:
    language: str
    phrases: dict[str, str]  # dotted key -> sentence

    def has(self, key: str) -> bool:
        return key in self.phrases

    def template(self, key: str) -> str:
        """The sentence with its {placeholders} unfilled."""
        try:
            return self.phrases[key]
        except KeyError:
            raise LocaleError(f"phrase '{key}' is missing in locale '{self.language}'") from None

    def phrase(self, key: str, **values: Any) -> str:
        """The sentence with {placeholders} filled from `values`."""
        text = self.template(key)
        if not values:
            return text
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            logger.warning(f"phrase '{key}': placeholders not filled from {sorted(values)}")
            return text


def _flatten(node: Any, prefix: str, out: dict[str, str], errors: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                errors.append(f"{prefix or '<root>'}: key {key!r} is not a string")
                continue
            _flatten(value, f"{prefix}.{key}" if prefix else key, out, errors)
    elif isinstance(node, str):
        out[prefix] = node
    else:
        errors.append(f"{prefix}: expected text or a map, got {type(node).__name__}")


@lru_cache(maxsize=8)
def load_locale(language: str, root: Path = LOCALES_DIR) -> Locale:
    path = root / language / "phrases.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise LocaleError(f"locale '{language}': cannot read {path} ({e})") from e
    phrases: dict[str, str] = {}
    errors: list[str] = []
    _flatten(data, "", phrases, errors)
    if errors:
        raise LocaleError(f"locale '{language}' phrases.yaml:\n  " + "\n  ".join(errors))
    return Locale(language, phrases)


_active_language = DEFAULT_LANGUAGE


def set_language(language: str) -> None:
    """Make `language` the active locale (loads it now, so a bad locale fails here)."""
    global _active_language
    load_locale(language)
    _active_language = language


def active_language() -> str:
    return _active_language


def current() -> Locale:
    return load_locale(_active_language)


def phrase(key: str, **values: Any) -> str:
    return current().phrase(key, **values)


def template(key: str) -> str:
    return current().template(key)


def phrase_or(key: str, default: Any, **values: Any) -> Any:
    """phrase() when the locale has `key`, else `default` (a lookup by data,
    e.g. a verdict the locale has no gloss for)."""
    return phrase(key, **values) if current().has(key) else default


def maybe_phrase(key: str | None, **values: Any) -> str | None:
    """phrase() for an optional key (a knowledge field that may be absent)."""
    return phrase(key, **values) if key else None


def reload() -> None:
    load_locale.cache_clear()
