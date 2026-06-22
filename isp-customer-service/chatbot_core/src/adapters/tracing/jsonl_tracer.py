"""JSONL conversation-trace sink (+ a no-op tracer + factory).

One file per session: ``<trace_dir>/<session_id>.jsonl``, one event per line:

    {"v":1,"ts":"2026-06-13T16:08:05.123","session_id":"...","type":"tool_call",...}

Design (chatbot_core/docs/stebejimo_dizainas.md): the producer is the single
AgentSession seam, so the trace is identical across CLI / voice / UI. The SINK
is swappable behind the ConversationTracer port — file now, aggregator/UI feed
later. Phone numbers are redacted via the shared REDACT_PII flag. Best-effort:
a sink failure logs a warning and NEVER interrupts the conversation.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Reuse the shared PII redaction (same flag as the central log filter).
_SHARED_SRC = Path(__file__).resolve().parents[4] / "shared" / "src"
if str(_SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(_SHARED_SRC))

try:
    from utils import redact_phone
except ImportError:  # pragma: no cover - defensive

    def redact_phone(text: str, *, enabled: bool | None = None) -> str:
        return text


logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_DISABLED_VALUES = {"0", "false", "no", "off"}
# Structural fields are never redacted — their digit runs (session_id, ts) can
# coincidentally match the phone regex and would otherwise be corrupted.
_STRUCTURAL_KEYS = {"v", "ts", "session_id", "type"}

# Per-process counter disambiguates ids created in the same microsecond
# (e.g. concurrent voice sessions or back-to-back starts).
_seq = itertools.count(1)


def new_session_id() -> str:
    """A sortable, collision-safe session id (timestamp + sequence, not a UUID)."""
    return f"{datetime.now():%Y%m%d-%H%M%S-%f}-{next(_seq):04d}"


def _default_trace_dir() -> Path:
    # adapters/tracing/jsonl_tracer.py -> tracing -> adapters -> src -> chatbot_core -> <project root>
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "logs" / "sessions"


class NullTracer:
    """No-op tracer (tracing disabled). Keeps call sites unconditional."""

    def emit(self, event_type: str, **fields: Any) -> None:
        return None


class JsonlFileTracer:
    """Append-only JSONL sink, one file per conversation."""

    def __init__(
        self,
        session_id: str,
        trace_dir: Path | None = None,
        redact: bool | None = None,
    ):
        self.session_id = session_id
        self._redact = redact  # None -> defer to REDACT_PII env flag
        directory = trace_dir or _default_trace_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._path: Path | None = directory / f"{session_id}.jsonl"
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Conversation trace disabled (cannot use {directory}): {e}")
            self._path = None

    @property
    def path(self) -> Path | None:
        return self._path

    def emit(self, event_type: str, **fields: Any) -> None:
        if self._path is None:
            return
        event = {
            "v": SCHEMA_VERSION,
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "session_id": self.session_id,
            "type": event_type,
            **fields,
        }
        try:
            # Redact phone numbers in VALUES (text, nested args/summary), but
            # never in structural keys whose digit runs could false-match.
            scrubbed = {
                k: (v if k in _STRUCTURAL_KEYS else self._scrub(v)) for k, v in event.items()
            }
            line = json.dumps(scrubbed, ensure_ascii=False, default=str)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Conversation trace write failed: {e}")

    def _scrub(self, value: Any) -> Any:
        """Recursively redact phone numbers in string values."""
        if isinstance(value, str):
            return redact_phone(value, enabled=self._redact)
        if isinstance(value, dict):
            return {k: self._scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._scrub(v) for v in value]
        return value

    def export_txt(self) -> Path | None:
        """Write a human-readable transcript (<id>.txt) next to the JSONL.

        Quick-read view of the call: USER / AGENT turns with compact tool,
        verdict and latency annotations. Best-effort; never raises.
        """
        if self._path is None or not self._path.exists():
            return None
        txt_path = self._path.with_suffix(".txt")
        try:
            lines: list[str] = []
            with open(self._path, encoding="utf-8") as f:
                for raw in f:
                    if not raw.strip():
                        continue
                    e = json.loads(raw)
                    t = e.get("type")
                    if t == "session_start":
                        lines.append(
                            f"[{e.get('session_id')}] phone={e.get('caller_phone')} "
                            f"model={e.get('model')}"
                        )
                    elif t == "asr":
                        if e.get("raw") != e.get("transcript"):
                            lines.append(f"   (heard: {e.get('raw')!r})")
                    elif t == "user_turn":
                        lines.append(f"USER : {e.get('text')}")
                    elif t == "agent_reply":
                        lines.append(f"AGENT: {e.get('text')}")
                    elif t == "nlu":
                        lines.append(
                            f"   . nlu problem={e.get('problem')} street={e.get('street')} "
                            f"house={e.get('house')} apt={e.get('apartment')} "
                            f"city={e.get('city')} conf={e.get('confidence')}"
                        )
                    elif t == "tool_call":
                        lines.append(f"   . tool {e.get('name')} {e.get('args')}")
                    elif t == "tool_result":
                        lines.append(
                            f"   . -> ok={e.get('ok')} {e.get('summary') or ''} ({e.get('ms')}ms)"
                        )
                    elif t == "verdict":
                        lines.append(
                            f"   . VERDICT {e.get('group')} {e.get('action')} {e.get('reason')}"
                        )
                    elif t == "voice_latency":
                        lines.append(
                            f"   ~ asr={e.get('asr_ms')} agent={e.get('agent_ms')} "
                            f"tts={e.get('tts_ms')} total={e.get('total_ms')}ms"
                        )
                    elif t == "session_end":
                        lines.append(
                            f"--- end: {e.get('outcome')} customer={e.get('customer_id')} "
                            f"ticket={e.get('ticket_id')} "
                            f"llm_calls={e.get('llm_calls')} tokens={e.get('total_tokens')}"
                        )
            # The JSONL values are already redacted per-field, so just join them
            # (re-redacting the whole text would mask the numeric session id).
            txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return txt_path
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Transcript export failed: {e}")
            return None


def _enabled_from_env() -> bool:
    return os.getenv("TRACE_ENABLED", "true").strip().lower() not in _DISABLED_VALUES


def get_tracer(
    session_id: str,
    *,
    enabled: bool | None = None,
    trace_dir: str | Path | None = None,
):
    """Return a tracer for one session: JsonlFileTracer when enabled, else NullTracer.

    Enabled defaults to the TRACE_ENABLED env flag (on). trace_dir defaults to
    the TRACE_DIR env var, else <project_root>/logs/sessions.
    """
    if enabled is None:
        enabled = _enabled_from_env()
    if not enabled:
        return NullTracer()
    directory = trace_dir or os.getenv("TRACE_DIR")
    return JsonlFileTracer(session_id, Path(directory) if directory else None)
