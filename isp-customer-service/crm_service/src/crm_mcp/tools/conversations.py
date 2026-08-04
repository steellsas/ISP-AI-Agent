"""
Conversation record tools.

Persist the OUTCOME of a call to the `conversations` table (Phase 3.10): one row
per call with the structured summary + the transcript, for client history, reports,
and faster repeat-fault diagnosis. Written DETERMINISTICALLY by the engine at
session end from STATE — no LLM, no new reasoning here.
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Add shared to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "src"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from utils import get_logger

from database import DatabaseConnection

logger = get_logger(__name__)


def generate_conversation_id() -> str:
    """Generate a unique conversation id."""
    return f"CONV{uuid.uuid4().hex[:8].upper()}"


def save_conversation(db: DatabaseConnection, args: dict[str, Any]) -> dict[str, Any]:
    """
    Persist one call record.

    Args (all from engine STATE / trace, already structured):
        session_id:        trace/session id (required).
        customer_id:       confirmed customer id, or None for an unidentified caller.
        messages:          the transcript — a list of {role, content} dicts (stored as JSON).
        outcome:           short disposition string (resolved / outage / escalated / ...).
        summary:           the structured call summary dict (stored as JSON).
        ticket_id:         ticket filed this call, or None.
        duration_seconds:  call length if known, else None.

    Returns an envelope {success, conversation_id?} — never raises; a DB failure is
    logged and reported so it cannot interrupt call teardown.
    """
    session_id = args.get("session_id")
    customer_id = args.get("customer_id")
    messages = args.get("messages") or []
    outcome = args.get("outcome")
    summary = args.get("summary")
    ticket_id = args.get("ticket_id")
    duration_seconds = args.get("duration_seconds")

    if not session_id:
        return {"success": False, "error": "missing_session_id"}

    # A dangling customer/ticket FK (e.g. an unidentified caller) must not lose the
    # record: the columns are nullable + ON DELETE SET NULL, so drop a reference that
    # does not resolve rather than failing the whole insert.
    if customer_id and not _row_exists(db, "customers", "customer_id", customer_id):
        logger.warning(f"conversation {session_id}: customer {customer_id} not found; storing NULL")
        customer_id = None
    if ticket_id and not _row_exists(db, "tickets", "ticket_id", ticket_id):
        logger.warning(f"conversation {session_id}: ticket {ticket_id} not found; storing NULL")
        ticket_id = None

    conversation_id = generate_conversation_id()
    now = datetime.now().isoformat()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversations (
                    conversation_id,
                    customer_id,
                    session_id,
                    timestamp,
                    messages,
                    outcome,
                    summary,
                    ticket_id,
                    duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    customer_id,
                    session_id,
                    now,
                    json.dumps(messages, ensure_ascii=False),
                    outcome,
                    json.dumps(summary, ensure_ascii=False) if summary is not None else None,
                    ticket_id,
                    duration_seconds,
                ),
            )
        logger.info(f"Saved conversation {conversation_id} (session {session_id})")
        return {"success": True, "conversation_id": conversation_id}
    except Exception as e:
        logger.error(f"Error in save_conversation: {e}", exc_info=True)
        return {"success": False, "error": "database_error", "message": str(e)}


def _row_exists(db: DatabaseConnection, table: str, column: str, value: str) -> bool:
    """Whether a row with column==value exists (table/column are trusted literals)."""
    try:
        with db.cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (value,))
            return cursor.fetchone() is not None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"_row_exists({table}.{column}) failed: {e}")
        return False
