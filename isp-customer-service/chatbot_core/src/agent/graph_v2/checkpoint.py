"""
Checkpointer factory — the call state between turns (+ time-travel history).

The API service creates ONE SqliteSaver per process on one database file (one
thread per call, thread_id = session_id) and closes it on shutdown.
check_same_thread=False because voice turns run in worker threads
(asyncio.to_thread); SqliteSaver serializes access with its own internal lock.
Tests and eval use the in-memory saver. Kept in its own file so the storage
choice (sqlite -> postgres later) is a one-file swap.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

# <repo>/logs/graph_checkpoints.sqlite — absolute, independent of the working directory.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[4] / "logs" / "graph_checkpoints.sqlite"

# Custom types the checkpoint serializer may (de)serialize — without this the
# read path warned "Deserializing unregistered type … will be blocked in a
# future version" and returned plain dicts instead of models. Both import
# roots are listed because the project is loadable as `agent.*` and
# `src.agent.*` (known debt — see roadmap).
_STATE_TYPES: list[tuple[str, str]] = [
    ("slots", "Slot"),
    ("slots", "SlotStatus"),
    ("slots", "ClientProfileState"),
    ("graph_v2.state", "GraphState"),
    ("graph_v2.state", "IdentityState"),
    ("graph_v2.state", "IntakeState"),
    ("graph_v2.state", "DiagnosisState"),
    ("graph_v2.state", "ResolutionState"),
    ("graph_v2.state", "TicketContext"),
    ("graph_v2.state", "TicketState"),
    ("graph_v2.state", "DialogState"),
    ("graph_v2.state", "ClosingState"),
    ("graph_v2.state", "VoiceState"),
    ("graph_v2.state", "ToolsState"),
    ("graph_v2.state", "CaseState"),
    ("graph_v2.state", "TurnDirectives"),
    ("graph_v2.state", "TurnScratch"),
    ("graph_v2.state", "ActiveQuestion"),
    ("evidence", "Contradiction"),
]
_ALLOWED: list[tuple[str, str]] = [
    (f"{root}.{module}", name) for root in ("agent", "src.agent") for module, name in _STATE_TYPES
]


def make_checkpointer(path: Path | None = None) -> BaseCheckpointSaver:
    """A SqliteSaver on `path` (made absolute), or an in-memory saver when None."""
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED)
    if path is None:
        return InMemorySaver(serde=serde)
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn, serde=serde)


def close_checkpointer(saver: BaseCheckpointSaver | None) -> None:
    """Release the saver's database connection (no-op for the in-memory saver)."""
    conn = getattr(saver, "conn", None)
    if conn is not None:
        conn.close()
