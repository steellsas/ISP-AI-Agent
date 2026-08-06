"""Archive zone (Phase 4 PR3) — read-only access to past calls.

Sources, in one place:
- conversations table (Phase 3.10 call records): who/when/outcome/ticket +
  the structured summary + full message transcript,
- logs/sessions/<id>.jsonl traces: the event stream (brain panel, replayed)
  and the llm events the cost/token totals are computed from,
- logs/sessions/<id>/turn_NN_*.{wav,mp3}: per-turn audio recordings.

Everything is best-effort: a missing trace or audio folder degrades to an
empty list, never an error — old calls predate some of these artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_DB = _ROOT / "database" / "isp_database.db"


def _trace_dir() -> Path:
    env = os.getenv("TRACE_DIR")
    return Path(env) if env else _ROOT / "logs" / "sessions"


def _record_root() -> Path:
    env = os.getenv("API_RECORD_DIR")
    return Path(env) if env else _ROOT / "logs" / "sessions"


def _safe_session_id(session_id: str) -> bool:
    """Path-safety: session ids are engine-minted (timestamp-seq); reject
    anything that could traverse."""
    return bool(session_id) and all(c.isalnum() or c in "-_" for c in session_id)


def list_calls(limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first call records for the archive table."""
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT session_id, customer_id, timestamp, outcome, ticket_id, "
            "duration_seconds, summary FROM conversations "
            "ORDER BY timestamp DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    finally:
        conn.close()
    calls = []
    for r in rows:
        try:
            summary = json.loads(r["summary"]) if r["summary"] else {}
        except Exception:
            summary = {}
        calls.append(
            {
                "session_id": r["session_id"],
                "customer_id": r["customer_id"],
                "timestamp": r["timestamp"],
                "outcome": r["outcome"],
                "ticket_id": r["ticket_id"],
                "duration_seconds": r["duration_seconds"],
                "purpose": summary.get("purpose"),
                "cause": summary.get("cause"),
                "resolved": summary.get("resolved"),
                "caller_name": summary.get("caller_name"),
            }
        )
    return calls


def _load_events(session_id: str) -> list[dict[str, Any]]:
    path = _trace_dir() / f"{session_id}.jsonl"
    if not path.exists():
        return []
    events = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"trace read failed for {session_id}: {e}")
    return events


def _audio_files(session_id: str) -> list[str]:
    d = _record_root() / session_id
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.suffix in (".wav", ".mp3"))


def _stats_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Token/cost/latency totals — computed from the archived llm/voice events
    with the same price table the live panel uses."""
    from .config import cost_usd

    llm_calls = input_tokens = output_tokens = 0
    cost = 0.0
    voice_totals: list[int] = []
    for e in events:
        if e.get("type") == "llm":
            llm_calls += 1
            input_tokens += int(e.get("input_tokens") or 0)
            output_tokens += int(e.get("output_tokens") or 0)
            cost += cost_usd(
                e.get("model"), int(e.get("input_tokens") or 0), int(e.get("output_tokens") or 0)
            )
        elif e.get("type") == "voice_latency" and e.get("total_ms") is not None:
            voice_totals.append(int(e["total_ms"]))
    return {
        "llm_calls": llm_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "voice_turns": len(voice_totals),
        "avg_voice_latency_ms": (sum(voice_totals) // len(voice_totals)) if voice_totals else None,
    }


def call_detail(session_id: str) -> dict[str, Any] | None:
    """Everything the archive detail view needs for ONE call. None = unknown id."""
    if not _safe_session_id(session_id):
        return None
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM conversations WHERE session_id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    events = _load_events(session_id)
    if row is None and not events:
        return None
    try:
        messages = json.loads(row["messages"]) if row and row["messages"] else []
    except Exception:
        messages = []
    try:
        summary = json.loads(row["summary"]) if row and row["summary"] else {}
    except Exception:
        summary = {}
    # The transcript comes from the TRACE (user_turn/agent_reply events) — the
    # message history misses caller lines on scripted turns (the engine only
    # appends them on the LLM path), so events are the complete record. The
    # history is the fallback for pre-trace calls.
    transcript = [
        {"role": "user" if e["type"] == "user_turn" else "assistant", "text": e.get("text")}
        for e in events
        if e.get("type") in ("user_turn", "agent_reply") and (e.get("text") or "").strip()
    ]
    if not transcript:
        transcript = [
            {"role": m.get("role"), "text": m.get("content")}
            for m in messages
            if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()
        ]
    return {
        "session_id": session_id,
        "customer_id": row["customer_id"] if row else None,
        "timestamp": row["timestamp"] if row else None,
        "outcome": row["outcome"] if row else None,
        "ticket_id": row["ticket_id"] if row else None,
        "summary": summary,
        "transcript": transcript,
        "events": events,
        "audio": _audio_files(session_id),
        "stats": _stats_from_events(events),
    }


def audio_path(session_id: str, filename: str) -> Path | None:
    """Filesystem path for one recording — validated, inside the call's folder."""
    if not _safe_session_id(session_id):
        return None
    name = Path(filename).name  # strip any path components
    if Path(filename).suffix not in (".wav", ".mp3") or name != filename:
        return None
    path = _record_root() / session_id / name
    return path if path.is_file() else None
