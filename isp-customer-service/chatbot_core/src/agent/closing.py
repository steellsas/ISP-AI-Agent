"""Ending a call — the ONE place the closing flags are written (wave 1b).

Every path that ends a case (the walker's terminals, the identification and ticket
policies, the inform wrap-up, the stuck ladder, the hang-up safety net, and every plan
carrying `Action(type="close")`) comes through `close_call`, so the reason is recorded
once, traced once, and cannot be half-set. Before this, twenty places wrote
`closing.case_closed = True` by hand and one of them could silently overwrite another's
reason (live: a farewell turned a resolved call into "registered").

`reason` is one of gate.CLOSE_REASONS. "keep" ends the CALL without re-deciding why it
ended (a farewell for an already closed case). "stuck" is the backstop's close: it keeps
the registration an identified caller was promised (F-5).
"""

from __future__ import annotations

from typing import Any


def close_call(state: Any, rt: Any, reason: str, complete: bool = False) -> None:
    """Close the case for `reason`; `complete` also hangs up (the words that go out with
    it ARE the goodbye)."""
    s = state
    if reason == "stuck":
        _close_stuck(state, rt)
    elif reason == "keep":
        s.closing.case_closed = True
    else:
        s.closing.case_closed = True
        s.closing.closed_reason = reason
    if complete:
        s.closing.is_complete = True
    rt.tracer.emit(
        "decision",
        intent="close",
        action=s.closing.closed_reason,
        value="complete" if s.closing.is_complete else "open",
    )


def hang_up(state: Any, rt: Any) -> None:
    """End the CALL on an already closed case (the transport hangs up)."""
    close_call(state, rt, "keep", complete=True)


def _close_stuck(state: Any, rt: Any) -> None:
    """The stuck ladder's close: an identified caller gets the fault registered (it was
    promised), an unidentified one is recorded as stuck."""
    from .executor_flow import register_ticket_from_state

    s = state
    s.closing.case_closed = True
    if not s.identity.customer_id:
        s.closing.closed_reason = "declined"
        s.closing.unidentified_reason = "stuck"
        return
    if s.resolution.procedure is not None:
        s.resolution.procedure["escalate_reason"] = "stuck"
    register_ticket_from_state(s, rt, None)
    s.closing.closed_reason = "registered" if s.ticket.ticket_id else "declined"
