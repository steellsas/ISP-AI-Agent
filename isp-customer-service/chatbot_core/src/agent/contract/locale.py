"""
Locale — everything language-specific, per language (`agent/locales/<lang>/`).

`phrases.yaml` is a nested map of sentences; code and knowledge files refer to a
sentence by its dotted key (`identification.ask_problem`,
`pack.router_hung.fail_scope.question`). `phrase(key, **vars)` renders one for the
active language. A language is loaded whole and checked at load: a missing
file or a non-text entry fails there, and an unknown key fails loudly instead of
speaking an empty line.

`vocabulary.yaml` holds the named word lists and patterns the deterministic
readers match the caller's words against (`vocab("farewell")`,
`vocab_re("tv_re")`); `lang.py` holds language algorithms (folding, date and
amount wording, speech normalisation), reached through `lang()`.

The active language is process-wide and set from AgentConfig.language.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
DEFAULT_LANGUAGE = "lt"


class LocaleError(Exception):
    """A locale that cannot be loaded or a key it does not have."""


@dataclass(frozen=True)
class Locale:
    language: str
    phrases: dict[str, str]  # dotted key -> sentence
    vocabulary: dict[str, Any] = field(default_factory=dict)  # name -> list / text / map

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

    def vocab_entry(self, name: str) -> Any:
        try:
            return self.vocabulary[name]
        except KeyError:
            raise LocaleError(
                f"vocabulary '{name}' is missing in locale '{self.language}'"
            ) from None


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


def _freeze(node: Any) -> Any:
    if isinstance(node, list):
        return tuple(_freeze(x) for x in node)
    if isinstance(node, dict):
        return {k: _freeze(v) for k, v in node.items()}
    return node


def _read_yaml(language: str, path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise LocaleError(f"locale '{language}': cannot read {path} ({e})") from e


@lru_cache(maxsize=8)
def load_locale(language: str, root: Path = LOCALES_DIR) -> Locale:
    folder = root / language
    phrases: dict[str, str] = {}
    errors: list[str] = []
    _flatten(_read_yaml(language, folder / "phrases.yaml"), "", phrases, errors)
    if errors:
        raise LocaleError(f"locale '{language}' phrases.yaml:\n  " + "\n  ".join(errors))
    vocabulary: dict[str, Any] = {}
    if (folder / "vocabulary.yaml").is_file():
        data = _read_yaml(language, folder / "vocabulary.yaml")
        if not isinstance(data, dict) or any(not isinstance(k, str) for k in data):
            raise LocaleError(f"locale '{language}' vocabulary.yaml: expected named entries")
        vocabulary = {name: _freeze(value) for name, value in data.items()}
    return Locale(language, phrases, vocabulary)


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


# --- phrases ----------------------------------------------------------------------


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


# --- vocabulary ---------------------------------------------------------------------


def vocab(name: str) -> tuple[str, ...]:
    """A named word list (substring markers, stems, whole words)."""
    entry = current().vocab_entry(name)
    if not isinstance(entry, tuple):
        raise LocaleError(f"vocabulary '{name}' is not a list")
    return entry


def vocab_set(name: str) -> frozenset[str]:
    return _vocab_set(_active_language, name)


@lru_cache(maxsize=256)
def _vocab_set(language: str, name: str) -> frozenset[str]:
    return frozenset(vocab(name))


def vocab_text(name: str) -> str:
    """A named text entry (a regex fragment)."""
    entry = current().vocab_entry(name)
    if not isinstance(entry, str):
        raise LocaleError(f"vocabulary '{name}' is not text")
    return entry


def vocab_re(name: str, flags: int = 0) -> re.Pattern[str]:
    """A named regex, compiled once per language."""
    return _vocab_re(_active_language, name, flags)


@lru_cache(maxsize=512)
def _vocab_re(language: str, name: str, flags: int) -> re.Pattern[str]:
    return re.compile(vocab_text(name), flags)


def vocab_map(name: str) -> Any:
    """A named structured entry (label -> markers tables)."""
    return current().vocab_entry(name)


def lang() -> ModuleType:
    """The active language's algorithms module (`agent.locales.<lang>.lang`)."""
    return _lang_module(_active_language)


@lru_cache(maxsize=8)
def _lang_module(language: str) -> ModuleType:
    return importlib.import_module(f"..locales.{language}.lang", __package__)


def reload() -> None:
    load_locale.cache_clear()
    _vocab_set.cache_clear()
    _vocab_re.cache_clear()
