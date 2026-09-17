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


# The contact-record columns (D-14), written as given (trusted literal column names).
RECORD_FIELDS = (
    "transport_end",
    "unidentified_reason",
    "needs_review",
    "review_reason",
    "intent",
    "verdict",
    "address_confirmed",
    "outage_id",
    "audio_retention_until",
)


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
        transport_end … audio_retention_until: the contact record (RECORD_FIELDS, D-14).

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

    record = {k: args.get(k) for k in RECORD_FIELDS}
    record["needs_review"] = 1 if record.get("needs_review") else 0
    record["address_confirmed"] = 1 if record.get("address_confirmed") else 0
    now = datetime.now().isoformat()
    values = {
        "customer_id": customer_id,
        "timestamp": now,
        "messages": json.dumps(messages, ensure_ascii=False),
        "outcome": outcome,
        "summary": json.dumps(summary, ensure_ascii=False) if summary is not None else None,
        "ticket_id": ticket_id,
        "duration_seconds": duration_seconds,
        **record,
    }
    try:
        with db.cursor() as cursor:
            # One record per call: a second finalize of the same session updates it.
            cursor.execute(
                "SELECT conversation_id FROM conversations WHERE session_id = ?", (session_id,)
            )
            row = cursor.fetchone()
            if row:
                conversation_id = dict(row)["conversation_id"]
                values.pop("timestamp")
                sets = ", ".join(f"{k} = ?" for k in values)
                cursor.execute(
                    f"UPDATE conversations SET {sets} WHERE conversation_id = ?",
                    (*values.values(), conversation_id),
                )
            else:
                conversation_id = generate_conversation_id()
                cols = ["conversation_id", "session_id", *values]
                cursor.execute(
                    f"INSERT INTO conversations ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' for _ in cols)})",
                    (conversation_id, session_id, *values.values()),
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
