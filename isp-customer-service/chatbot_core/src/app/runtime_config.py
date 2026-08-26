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
        # R4c tiering: the solver (mąstytojas) may run on a stronger model than
        # the fast narrator/perception calls. "(kaip agento)" = same model.
        "key": "solver_model",
        "label": "Solverio LLM modelis (mąstytojas)",
        "options": ["(kaip agento)", "gpt-4o", "gpt-4.1-mini", "gpt-4o-mini"],
        "scope": "new_calls",
        "kind": "solver_model",
    },
    {
        # Tempo wave (VOICE_PLAN): the perception family (understand pass +
        # step classifier) on a FASTER model — Groq inference cuts the
        # between-questions gap. Enum validation keeps weaker models safe.
        "key": "PERCEPTION_MODEL",
        "label": "Percepcijos LLM modelis (supratimas)",
        "options": [
            "default",
            "groq/openai/gpt-oss-120b",
            "groq/openai/gpt-oss-20b",
            "groq/qwen/qwen3.6-27b",
            "gpt-4o-mini",
        ],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # AgentSession reads AGENT_ENGINE at construction, so the switch takes
        # effect on the NEXT call — running calls keep their engine. "graph" =
        # legacy LangGraph, "v2" = graph_v2 (docs/ROADMAP_REFACTORING.md),
        # "legacy" = direct ReactAgent loop (rollback).
        "key": "AGENT_ENGINE",
        "label": "Orkestravimo variklis (v2 = numatytasis)",
        "options": ["v2", "graph", "legacy"],
        "scope": "new_calls",
        "kind": "env",
    },
    {
        # Persona (R5c): evidence questions worded by the NARRATOR from the
        # pack's goal (reikia) vs read verbatim from the script. off = rollback.
        "key": "NARRATOR_QUESTIONS",
        "label": "Naratoriaus formuluotės (klausimai iš tikslo)",
        "options": ["on", "off"],
        "scope": "immediate",
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
        # VOICE_PLAN V1: fragments shorter than this never reach Whisper (it
        # hallucinates words from sub-word blips). 0 disables the guard.
        "key": "ASR_MIN_AUDIO_S",
        "label": "Trumpo garso sargas, s (0 = išjungta)",
        "options": ["0.2", "0.3", "0.4", "0.5", "0"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # Latency mask: the cached "Sekundėlę, tikrinu." cue when the LLM is
        # still thinking past the delay below.
        "key": "VOICE_FILLER",
        "label": "Užpildas „Sekundėlę, tikrinu“",
        "options": ["off", "on"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # Kalbėjimo greitis: '+10%' — informacija teka greičiau, tonas
        # dalykiškesnis (Andrius 2026-08-20).
        "key": "TTS_RATE",
        "label": "Kalbėjimo greitis",
        "options": ["+0%", "+10%", "+15%", "+20%", "-10%"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # Balso tonas: žemesnis (-10Hz) skamba dalykiškiau/techniškiau,
        # aukštesnis — energingiau. Tik edge varikliui.
        "key": "TTS_PITCH",
        "label": "Balso tonas (žemesnis = techniškesnis)",
        "options": ["+0Hz", "-10Hz", "-20Hz", "+10Hz"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # S1 (2026-08-24): šakų paruošimas kol klientas atsakinėja — atsakymas
        # iš kešo ~0 s, kai atsakymas telpa į numatytą šaką.
        "key": "SPECULATION",
        "label": "Spekuliatyvus paruošimas (šakos iš anksto)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "VOICE_FILLER_AFTER_S",
        "label": "Užpildo vėlinimas, s",
        "options": ["1.2", "0.8", "1.6", "2.0"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # G3: the agent speaks first after a long caller silence while a task
        # is standing — "Kaip sekasi, ar pavyksta?" (once per turn).
        "key": "VOICE_CHECKIN",
        "label": "Pasiteiravimas po tylos („Kaip sekasi?“)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "VOICE_CHECKIN_AFTER_S",
        "label": "Pasiteiravimo vėlinimas, s",
        "options": ["35", "20", "50", "70"],
        "scope": "immediate",
        "kind": "env",
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
        # L4 duplex E1 (2026-08-24): klientas siunčia frazės momentines kopijas
        # dar KALBANT — serveris veda slenkantį dalinį transkriptą (E1: tik
        # trace + ekranas; E2 ant jo statys semantinį turn-taking'ą).
        "key": "DUPLEX",
        "label": "Duplex (daliniai transkriptai kalbant)",
        "options": ["off", "on"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        "key": "PARTIAL_INTERVAL_S",
        "label": "Dalinių intervalas, s",
        "options": ["1.0", "0.8", "1.5", "2.0"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # E2: pilnas laukiamas atsakymas dalinyje -> kerpam turn'ą po tiek
        # tylos (vietoj kliento micSil ~900 ms).
        "key": "ENDPOINT_FAST_MS",
        "label": "Greitas kirpimas (pilnas atsakymas), ms",
        "options": ["350", "250", "450", "600"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # E2: nebaigta mintis (jungtukas/kablelis gale) -> laukiam tiek tylos.
        "key": "ENDPOINT_SLOW_MS",
        "label": "Ilgas laukimas (nebaigta mintis), ms",
        "options": ["1400", "1200", "1800", "2200"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # D2: serverio VAD slenkstis (kliento mikrofonai skiriasi — derinti
        # pirmo balso testo metu, jei kalba nesigirdi arba triukšmas kerta).
        "key": "SERVER_VAD_THR",
        "label": "Serverio VAD slenkstis",
        "options": ["0.010", "0.006", "0.015", "0.020"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # D2: numatytasis tylos langas serverio kirpimui (be E2 užuominos).
        "key": "SERVER_SIL_MS",
        "label": "Serverio tylos langas, ms",
        "options": ["900", "700", "1100", "1400"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # W2 (2026-08-25): tylusis analitikas — fone skaito visą pokalbį ir
        # duoda naratoriui patariamųjų pastabų (faktų ir eigos nekeičia).
        "key": "ANALYST",
        "label": "Tylusis analitikas (fone, patariamasis)",
        "options": ["on", "off"],
        "scope": "immediate",
        "kind": "env",
    },
    {
        # P1b (2026-08-26): po pertraukimo — trumpas „Aha, girdžiu" iš kešo,
        # jei tikras atsakas neatėjo per INTERRUPT_ACK_AFTER_S.
        "key": "INTERRUPT_ACK",
        "label": "Ack po pertraukimo („Aha, girdžiu“)",
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
    if item["kind"] == "solver_model":
        from agent.config import get_config

        return get_config().solver_model or "(kaip agento)"
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
        elif item["kind"] == "solver_model":
            from agent.config import update_config

            update_config(solver_model=None if value == "(kaip agento)" else value)
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
