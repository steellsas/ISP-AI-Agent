"""Demo admin actions — DB reset to the seeded state.

Between test calls the demo DB drifts (tickets pile up, the bridge test binds
the caller's MAC, statuses change). The reset drops and re-seeds IN PLACE —
same SQL files as scripts/setup_db.py + seed_data.py — without deleting the
file, so it works even while the API process holds SQLite connections
(unlinking a held file is WinError 32 on Windows; observed with voice_demo).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

from agent.db_path import database_path

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMAS = ("crm_schema", "network_schema")
_SEEDS = (
    "customers",
    "addresses",
    "service_plans",
    "equipment",
    "network",
    "demo_internet",
    "invoices",
    "similar_streets",
    "network_faults",
)


# Kept across a reset: the archive lists past calls from this table, and a scenario's ▶ resets
# the DB before every call — without this each call wiped the previous one from the archive
# (Andrius, 2026-10-27). The demo lines, tickets and statuses are what a reset is for.
_KEPT = ("conversations",)


def reset_db() -> dict:
    """Drop every table and re-run the schema + seed scripts, keeping the call records
    (`_KEPT`). Sync — callers run it in a worker thread. Raises on failure (the route maps
    it to 500)."""
    conn = sqlite3.connect(database_path())
    try:
        conn.execute("PRAGMA foreign_keys=off")
        kept = {name: _rows(conn, name) for name in _KEPT}
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith("sqlite_")
        ]
        for t in tables:
            conn.execute(f'DROP TABLE IF EXISTS "{t}"')
        conn.commit()
        for name in _SCHEMAS:
            sql = (_ROOT / "database" / "schema" / f"{name}.sql").read_text(encoding="utf-8")
            conn.executescript(sql)
        for name in _SEEDS:
            sql = (_ROOT / "database" / "seeds" / f"{name}.sql").read_text(encoding="utf-8")
            conn.executescript(sql)
        conn.commit()
        # The schema scripts turn the checks back on; a kept call may name a ticket the reset
        # just removed, and that is still the call's history.
        conn.execute("PRAGMA foreign_keys=off")
        for name, rows in kept.items():
            _restore(conn, name, rows)
        conn.commit()
        customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        tickets = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        logger.info(f"DB reset: {customers} customers, {tickets} tickets")
        return {"reset": True, "customers": customers, "tickets": tickets}
    finally:
        conn.close()


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Every row of `table` (none if it does not exist yet)."""
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.row_factory = None


def _restore(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    """Put the kept rows back — only the columns the fresh schema still has."""
    if not rows:
        return
    columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    names = [c for c in columns if c in rows[0]]
    marks = ", ".join("?" for _ in names)
    quoted = ", ".join(f'"{c}"' for c in names)
    conn.executemany(
        f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({marks})',
        [tuple(r.get(c) for c in names) for r in rows],
    )
