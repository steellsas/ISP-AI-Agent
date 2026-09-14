"""
Closing-stage flow — the deterministic "when does the call end" rules.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent so
the closing rules live in one importable module. Functions
take (state, rt) — the call state and the AgentRuntime; no module state.
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


def maybe_finish(state: Any, rt: Any, user_input: str | None) -> None:
    """In the closing stage, decide whether to end the call. The case is already
    closed; the agent offered "ar dar kuo nors padėti?". If the caller says a
    goodbye / "no", or we have lingered a second closing turn, set is_complete so
    the transport hangs up — no endless goodbyes."""
    s = state
    if not s.closing.case_closed or s.closing.is_complete:
        return
    s.closing.closing_turns += 1
    from .resolution import detect_farewell

    if detect_farewell(user_input) or s.closing.closing_turns >= 2:
        s.closing.is_complete = True


def maybe_close_inform(state: Any, rt: Any, user_input: str | None) -> None:
    """Deterministic close for INFORM mode (mass outage, billing, or any verdict with
    NO troubleshooting strategy to walk). Once the caller has been informed and
    signals they are done — a goodbye or a plain 'no more questions' — the engine
    closes the call ITSELF and ends it on one farewell.

    Without this, closing depended on the model calling close_case, which it did not:
    the caller said goodbye repeatedly, the call stayed open, and the diagnosis node
    re-narrated the outage every turn (observed: 'kartoja gedimą')."""
    s = state
    if s.closing.case_closed or not s.identity.customer_id:
        return
    # Farewell may close the INFORM call only after the BUSINESS is done: the
    # identification ladder finished AND the news actually delivered. A garbled
    # mid-ladder "Ne, mano vardas Tomas…" matched the loose farewell heuristic and
    # HUNG UP on the caller before they ever heard the debt (observed live).
    # An OUTAGE report counts as the news told — it is delivered the moment
    # outage_reported flips (a different path than the billing script).
    if (
        state.identity.result_pending
        or state.ticket.stage
        or not (state.diagnosis.news_delivered or s.diagnosis.outage_reported)
    ):
        return
    reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
    # INFORM mode: an outage was flagged, OR we identified + diagnosed but there is no
    # resolution strategy to walk (active_outage, billing_suspended, generic inform).
    # A live strategy (foreign_mac, dead-router, client_side) keeps s.resolution set
    # and is handled by the walker instead — never closed here.
    inform_mode = s.diagnosis.outage_reported or (
        s.resolution.procedure is None and bool(s.diagnosis.verdicts)
    )
    if not inform_mode:
        return
    from .resolution import detect_farewell

    if detect_farewell(user_input):
        s.closing.case_closed = True
        s.closing.closed_reason = (
            "outage" if (s.diagnosis.outage_reported or reason == "active_outage") else "inform"
        )
        s.closing.is_complete = True  # caller already said goodbye — end on ONE farewell
        # Observability: the close moment was invisible in the trace (this made a
        # stuck-close analysis needlessly hard) — record it.
        rt.tracer.emit(
            "decision", intent="inform_close", action="close", to=s.closing.closed_reason
        )


def maybe_end_on_goodbye(state: Any, rt: Any, text: str) -> None:
    """Catch-all hang-up: if the agent JUST said a terminal goodbye — on ANY path
    (resolved, registered, declined, or the stuck backstop) — end the call so the
    transport stops instead of looping the goodbye. Covers the cases the
    case_closed/closing flow misses (e.g. the model says 'geros dienos' on a stuck
    turn without close_case ever firing)."""
    if state.closing.is_complete or not text:
        return
    low = text.lower()
    if any(m in low for m in GOODBYE_MARKERS):
        state.closing.is_complete = True
