"""
Checkpointer factory — SqliteSaver for state between calls + time-travel.

One shared database file, one thread per call (thread_id = session_id, the
existing convention in session.py). check_same_thread=False because voice
turns run in worker threads (asyncio.to_thread); SqliteSaver serializes
access with its own internal lock. Kept in its own file so the storage choice
(sqlite -> postgres later) is a one-file swap.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_DB_PATH = "logs/graph_checkpoints.sqlite"

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
    ("graph_v2.state", "TurnScratch"),
    ("dialog_registry", "ActiveQuestion"),
    ("evidence", "EvidenceConflict"),
    ("evidence", "FactConfirm"),
]
_ALLOWED: list[tuple[str, str]] = [
    (f"{root}.{module}", name) for root in ("agent", "src.agent") for module, name in _STATE_TYPES
]


def make_checkpointer(db_path: str | Path = DEFAULT_DB_PATH) -> SqliteSaver:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn, serde=JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED))
