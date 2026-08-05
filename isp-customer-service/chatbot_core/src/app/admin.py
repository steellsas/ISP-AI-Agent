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

_ROOT = Path(__file__).resolve().parents[3]
_DB = _ROOT / "database" / "isp_database.db"
_SCHEMAS = ("crm_schema", "network_schema")
_SEEDS = ("customers", "addresses", "service_plans", "equipment", "network", "demo_internet")


def reset_db() -> dict:
    """Drop every table and re-run the schema + seed scripts. Sync — callers
    run it in a worker thread. Raises on failure (the route maps it to 500)."""
    conn = sqlite3.connect(_DB)
    try:
        conn.execute("PRAGMA foreign_keys=off")
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
        customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        tickets = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        logger.info(f"DB reset: {customers} customers, {tickets} tickets")
        return {"reset": True, "customers": customers, "tickets": tickets}
    finally:
        conn.close()
