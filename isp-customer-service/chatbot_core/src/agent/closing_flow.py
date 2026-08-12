"""
Closing-stage flow — the deterministic "when does the call end" rules.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent so the closing rules live in one importable module. Both engines
use it — the legacy ReactAgent through thin delegate methods, the v2 graph
nodes directly. Functions take the engine explicitly (state + per-call flags);
no module state.
"""

from __future__ import annotations

from typing import Any

# When the agent's reply contains one of these, the call is over — end it (hang up)
# no matter which path produced the goodbye. Kept to clear terminal farewells so a
# mid-conversation "gero" never trips it.
GOODBYE_MARKERS = (
    "geros dienos",
    "geros jums dienos",
    "gražios dienos",
    "gero vakaro",
    "gražaus vakaro",
    "viso gero",
    "viso labo",
)


def maybe_finish(engine: Any, user_input: str | None) -> None:
    """In the closing stage, decide whether to end the call. The case is already
    closed; the agent offered "ar dar kuo nors padėti?". If the caller says a
    goodbye / "no", or we have lingered a second closing turn, set is_complete so
    the transport hangs up — no endless goodbyes."""
    s = engine.state
    if not s.case_closed or s.is_complete:
        return
    s.closing_turns += 1
    from .resolution import detect_farewell

    if detect_farewell(user_input) or s.closing_turns >= 2:
        s.is_complete = True


def maybe_close_inform(engine: Any, user_input: str | None) -> None:
    """Deterministic close for INFORM mode (mass outage, billing, or any verdict with
    NO troubleshooting strategy to walk). Once the caller has been informed and
    signals they are done — a goodbye or a plain 'no more questions' — the engine
    closes the call ITSELF and ends it on one farewell.

    Without this, closing depended on the model calling close_case, which it did not:
    the caller said goodbye repeatedly, the call stayed open, and the diagnosis node
    re-narrated the outage every turn (observed: 'kartoja gedimą')."""
    s = engine.state
    if s.case_closed or not s.customer_id:
        return
    # Farewell may close the INFORM call only after the BUSINESS is done: the
    # identification ladder finished AND the news actually delivered. A garbled
    # mid-ladder "Ne, mano vardas Tomas…" matched the loose farewell heuristic and
    # HUNG UP on the caller before they ever heard the debt (observed live).
    # An OUTAGE report counts as the news told — it is delivered the moment
    # outage_reported flips (a different path than the billing script).
    if (
        engine._result_pending
        or engine._ticket_stage
        or not (engine._news_told or s.outage_reported)
    ):
        return
    reason = (s.diagnosis.get("network") or {}).get("reason")
    # INFORM mode: an outage was flagged, OR we identified + diagnosed but there is no
    # resolution strategy to walk (active_outage, billing_suspended, generic inform).
    # A live strategy (foreign_mac, dead-router, client_side) keeps s.resolution set
    # and is handled by the walker instead — never closed here.
    inform_mode = s.outage_reported or (s.resolution is None and bool(s.diagnosis))
    if not inform_mode:
        return
    from .resolution import detect_farewell

    if detect_farewell(user_input):
        s.case_closed = True
        s.closed_reason = "outage" if (s.outage_reported or reason == "active_outage") else "inform"
        s.is_complete = True  # caller already said goodbye — end on ONE farewell
        # Observability: the close moment was invisible in the trace (this made a
        # stuck-close analysis needlessly hard) — record it.
        engine.tracer.emit("decision", intent="inform_close", action="close", to=s.closed_reason)


def maybe_end_on_goodbye(engine: Any, text: str) -> None:
    """Catch-all hang-up: if the agent JUST said a terminal goodbye — on ANY path
    (resolved, registered, declined, or the stuck backstop) — end the call so the
    transport stops instead of looping the goodbye. Covers the cases the
    case_closed/closing flow misses (e.g. the model says 'geros dienos' on a stuck
    turn without close_case ever firing)."""
    if engine.state.is_complete or not text:
        return
    low = text.lower()
    if any(m in low for m in GOODBYE_MARKERS):
        engine.state.is_complete = True
