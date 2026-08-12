"""Runtime-editable demo settings (Phase 4 config page).

Hosted-demo thinking: most parameters must be changeable and testable WITHOUT
shell access or a restart. The page edits a WHITELIST of knobs; each change is
applied to the live process (env / agent config / adapter caches) and persisted
to a JSON overrides file that is re-applied on startup — so a hosted demo
keeps its settings across restarts, while `.env` stays the secrets file.

Scopes are honest about when a change takes effect:
- immediate      — the engine reads the env per call (flags),
- new_calls      — picked up by the next session (models, voice adapters).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PERSIST = Path(__file__).resolve().parents[2] / ".api_config.json"


def _persist_path() -> Path:
    env = os.getenv("API_CONFIG_FILE")
    return Path(env) if env else _DEFAULT_PERSIST


# The editable surface. `kind` drives how a change is applied:
#   env         — os.environ only
#   env+voice   — os.environ + rebuild the cached ASR/TTS adapters
#   agent_model — agent config (new sessions pick it up)
SCHEMA: list[dict[str, Any]] = [
    {
        "key": "agent_model",
        "label": "Agento LLM modelis",
        "options": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "scope": "new_calls",
        "kind": "agent_model",
    },
    {
        # AgentSession reads AGENT_ENGINE at construction, so the switch takes
        # effect on the NEXT call — running calls keep their engine. "graph" =
        # legacy LangGraph, "v2" = graph_v2 (docs/ROADMAP_REFACTORING.md),
        # "legacy" = direct ReactAgent loop (rollback).
        "key": "AGENT_ENGINE",
        "label": "Orkestravimo variklis (graph → v2)",
        "options": ["graph", "v2", "legacy"],
        "scope": "new_calls",
        "kind": "env",
    },
    {
        "key": "CLASSIFIER",
        "label": "LLM klasifikatorius (atsakymų skaitymas)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "SOLVER_DRIVE",
        "label": "Mąstytojas vairuoja (solver drive)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "SIMULATE_BRIDGE",
        "label": "Bridge simuliacija (demo DB)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "ASR_BACKEND",
        "label": "STT variklis",
        "options": ["groq", "local"],
        "scope": "new_calls",
        "kind": "env+voice",
    },
    {
        "key": "GROQ_MODEL",
        "label": "Groq Whisper modelis",
        "options": ["whisper-large-v3", "whisper-large-v3-turbo"],
        "scope": "new_calls",
        "kind": "env+voice",
    },
    {
        "key": "TTS_ENGINE",
        "label": "TTS variklis",
        "options": ["edge", "gtts"],
        "scope": "new_calls",
        "kind": "env+voice",
    },
    {
        "key": "TTS_VOICE",
        "label": "Balsas",
        "options": ["lt-LT-LeonasNeural", "lt-LT-OnaNeural"],
        "scope": "new_calls",
        "kind": "env+voice",
    },
    {
        "key": "API_RECORD_AUDIO",
        "label": "Įrašyti skambučių garsą",
        "options": ["1", "0"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "VOICE_STREAM",
        "label": "Srautinis kalbėjimas (sakinys po sakinio)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "UNDERSTAND",
        "label": "Supratimo pass'as (LLM atsakymų skaitymas)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
]

_BY_KEY = {item["key"]: item for item in SCHEMA}


def _get_value(item: dict[str, Any]) -> str:
    if item["kind"] == "agent_model":
        from agent.config import get_config

        return get_config().model
    default = item["options"][0]
    if item["key"] == "CLASSIFIER":
        default = os.getenv("CLASSIFIER", "on")
    return os.getenv(item["key"], default)


def current() -> list[dict[str, Any]]:
    """The whole editable surface with live values — the page renders this."""
    return [{**item, "value": _get_value(item)} for item in SCHEMA]


def apply(changes: dict[str, str]) -> list[dict[str, Any]]:
    """Validate + apply a change set; persists and returns the new state.
    Raises ValueError with a readable message on any invalid key/value."""
    for key, value in changes.items():
        item = _BY_KEY.get(key)
        if item is None:
            raise ValueError(f"nežinomas nustatymas: {key}")
        if str(value) not in item["options"]:
            raise ValueError(f"{key}: leidžiamos reikšmės {item['options']}")
    voice_touched = False
    for key, value in changes.items():
        item = _BY_KEY[key]
        value = str(value)
        if item["kind"] == "agent_model":
            from agent.config import update_config

            update_config(model=value)
        else:
            os.environ[key] = value
            if item["kind"] == "env+voice":
                voice_touched = True
        logger.info(f"config: {key} = {value}")
    if voice_touched:
        from . import voice

        voice._build_asr.cache_clear()
        voice._build_tts.cache_clear()
    _persist(changes)
    return current()


def _persist(changes: dict[str, str]) -> None:
    """Best-effort: OVERRIDES survive a restart (hosted demo). Only the keys the
    admin actually changed are written — a full-state snapshot would re-apply
    untouched defaults on startup and clobber env set elsewhere (observed: the
    test suite's CLASSIFIER=off overwritten by a restored snapshot)."""
    try:
        path = _persist_path()
        data: dict[str, str] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        data.update({k: str(v) for k, v in changes.items()})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"config persist failed: {e}")


def load_persisted() -> None:
    """Re-apply saved overrides at startup (called from the app lifespan)."""
    path = _persist_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        valid = {k: v for k, v in data.items() if k in _BY_KEY and str(v) in _BY_KEY[k]["options"]}
        if valid:
            apply(valid)
            logger.info(f"config: restored {list(valid)}")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"config restore failed: {e}")
