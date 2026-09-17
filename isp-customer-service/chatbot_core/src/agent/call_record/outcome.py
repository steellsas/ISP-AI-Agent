"""The contact record's outcome (D-14), derived from the final state — never by an LLM.

Every call ends with one record: what happened (`outcome`), why an unidentified call
stayed unidentified (`unidentified_reason`), and whether a person should look at it
(`needs_review` + `review_reason`). The conditions are checked in order; the first that
holds decides. How the transport ended (hang-up, disconnect, TTL) is kept apart from
the outcome (F-4).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Outcome:
    outcome: str
    unidentified_reason: str | None = None
    needs_review: bool = False
    review_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive(state: Any, *, technical_error: bool = False) -> Outcome:
    """The outcome row for this call (the table in M6_calls_and_records.md §4 step 5)."""
    from ..faults import verdict_flag

    s = state
    if technical_error:
        return Outcome(
            "error",
            None if s.identity.customer_id else "technical_error",
            True,
            "technical_error",
        )
    if not s.identity.customer_id:
        return _unidentified(s)
    reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
    inform = verdict_flag(reason, "inform") if reason else None
    if s.diagnosis.outage_reported or inform == "outage":
        return Outcome("informed_outage")
    # A registered ticket outranks the news it followed (a disputed debt becomes a
    # request someone must answer) — the plan's table put the debt first.
    if s.closing.appended_ticket_id:
        return Outcome("ticket_appended")
    if s.ticket.ticket_id:
        return Outcome("ticket")
    if inform == "debt" and s.diagnosis.news_delivered:
        return Outcome("informed_debt")
    if s.closing.closed_reason == "resolved":
        return Outcome("resolved")
    if not s.closing.case_closed:
        if s.diagnosis.news_delivered:
            return Outcome("informed")
        return Outcome("abandoned", None, True, "hung_up_before_close")
    if s.closing.closed_reason in ("callback", "declined"):
        return Outcome(s.closing.closed_reason)
    return Outcome("informed" if s.diagnosis.news_delivered else "closed")


def _unidentified(s: Any) -> Outcome:
    if s.closing.unidentified_reason == "stuck":
        return Outcome("unidentified", "stuck", True, "stuck")
    if s.closing.unidentified_reason == "not_a_customer":
        return Outcome("unidentified", "not_a_customer", True, "not_a_customer")
    heard_address = bool(s.identity.profile.street.value or s.identity.profile.house.value)
    if s.closing.case_closed and s.closing.closed_reason == "declined" and not heard_address:
        return Outcome("unidentified", "caller_refused")
    if heard_address:
        return Outcome("unidentified", "address_not_found", True, "address_not_found")
    if not s.closing.case_closed:
        return Outcome("abandoned", "hung_up", True, "hung_up")
    return Outcome("unidentified", None, True, "unidentified")


def outage_id(state: Any) -> str | None:
    """The mass outage this call was about (the complaint counter links to it)."""
    signals = (state.diagnosis.verdicts.get("network") or {}).get("signals") or {}
    incident = signals.get("incident") or {}
    return incident.get("outage_id") or (state.identity.held_outage or {}).get("outage_id")
