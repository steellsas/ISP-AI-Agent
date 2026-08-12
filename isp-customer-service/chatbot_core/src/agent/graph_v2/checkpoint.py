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

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_DB_PATH = "logs/graph_checkpoints.sqlite"


def make_checkpointer(db_path: str | Path = DEFAULT_DB_PATH) -> SqliteSaver:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)
