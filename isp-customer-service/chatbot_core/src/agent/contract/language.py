"""The model's known language mistakes and their corrections (v3 6d, `locales/<lang>/kalba.yaml`).

Three uses of one file, so a new word is one line and never a prompt edit:

- `fix_words(sentence)` — the reply guard corrects a known wrong word before it is spoken;
- `prompt_lines()` — the few most frequent ones go into the speaking prompt as „never → say";
- `known_correct()` — words the lexicon lacks, so measuring does not flag them.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import yaml

from .locale import LOCALES_DIR, active_language

_WORD = re.compile(r"[A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž]+")


@lru_cache(maxsize=8)
def _load(language: str) -> dict[str, Any]:
    path = LOCALES_DIR / language / "kalba.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def fixes() -> dict[str, str]:
    """Wrong word (lower case) → the right one."""
    raw = _load(active_language()).get("taisymai") or {}
    return {str(k).lower(): str(v) for k, v in raw.items()}


def known_correct() -> set[str]:
    return {str(w).lower() for w in (_load(active_language()).get("teisingi") or [])}


def prompt_lines() -> str:
    """„wrong" → „right" for the most frequent mistakes (the prompt keeps it short)."""
    table = fixes()
    chosen = [str(w).lower() for w in (_load(active_language()).get("i_prompta") or [])]
    return "; ".join(f"„{w}“ → „{table[w]}“" for w in chosen if w in table)


def fix_words(sentence: str) -> tuple[str, list[tuple[str, str]]]:
    """The sentence with known wrong words replaced (whole words, capital kept)."""
    table = fixes()
    if not table or not sentence:
        return sentence, []
    applied: list[tuple[str, str]] = []

    def _swap(match: re.Match) -> str:
        word = match.group(0)
        right = table.get(word.lower())
        if right is None:
            return word
        applied.append((word, right))
        return right[:1].upper() + right[1:] if word[:1].isupper() else right

    return _WORD.sub(_swap, sentence), applied


def reload() -> None:
    _load.cache_clear()
