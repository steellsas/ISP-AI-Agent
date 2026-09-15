"""
Ticket-confirmation dialogue flow — the scripted contact ladder before EVERY
registration (2026-08-04): the contact number is ALWAYS asked, then the
convenient hours; _register_ticket_from_state creates the ticket
deterministically from STATE.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent. The stage value lives on
GraphState.ticket.stage (promoted); the dialogue CONTEXT is GraphState.ticket.context
(a TicketContext model — the escalate step is kept by id).
"""

from __future__ import annotations

import re
from typing import Any

from .contract.locale import phrase_or, vocab


def begin_ticket_dialogue(state: Any, rt: Any, step) -> None:
    """Start the ticket-confirmation dialogue: before ANY registration the agent
    collects the contact number (ALWAYS asked — the caller may be on a
    company/other phone, or the DB number stale) and when it is convenient to
    call. The scripted ladder asks; once complete, finish_ticket_dialogue
    registers with the contacts on the ticket."""
    if state.ticket.ticket_id or state.ticket.stage:
        return  # already registered / already collecting
    from .graph_v2.state import TicketContext

    state.ticket.context = TicketContext(step_id=step.id if step is not None else None)
    state.ticket.stage = "phone"
    rt.tracer.emit("decision", intent="ticket_dialogue", action="start")


# Escalate reasons after which nothing was done at the device: the ticket must
# not claim the pack's post-action wording.
NOTHING_DONE_REASONS = frozenset({"caller_refused", "cannot_now", "cannot_now_asks_ticket"})


def ticket_need(state: Any, rt: Any) -> str:
    """Human wording of WHY the ticket is needed ("reikalingas naujas
    maršrutizatorius"), for the intro announce and the ticket itself — never
    the raw verdict key."""
    from .contract.locale import phrase
    from .evidence import fault_need

    s = state
    cause = (
        (s.diagnosis.hypothesis or {}).get("cause")
        or (s.resolution.procedure or {}).get("verdict")
        or ""
    )
    # P-E (live 2026-09-08): escalating WITHOUT the step's action done must
    # not claim it happened — "routeris perkrautas, bet ryšys neatsistatė"
    # went out when the caller never rebooted (not at home). A refusal /
    # cannot-now escalation speaks the honest state instead of the fault
    # file's post-action wording.
    reason = (s.resolution.procedure or {}).get("escalate_reason")
    if reason in NOTHING_DONE_REASONS:
        gloss = phrase_or(f"verdict.{cause}.gloss", None)
        prefix = phrase("ticket.need_suspected", gloss=gloss) if gloss else ""
        return prefix + phrase("ticket.need_not_checked")
    need = fault_need(cause) or phrase_or(
        f"verdict.{cause}.ticket_need", None
    )  # file first, code fallback
    if need:
        return need
    # No verdict at all — an in-scope fault the agent's knowledge cannot
    # resolve. HONEST ticket type (Andrius 2026-09-02): "neaiškus gedimas" —
    # feeds the analysis/improvement loop instead of an improvised cause.
    if not cause:
        return phrase("ticket.need_unclear")
    return phrase_or(f"verdict.{cause}.gloss", cause)


def wants_to_keep_solving(state: Any, rt: Any, user_input: str | None) -> bool:
    """A ticket refusal that CARRIES solving content ("Ne, tai mes pajunkim
    tą kompiuterį…") — the caller is refusing the REGISTRATION, not the
    help. Live 2026-08-11: this was read as plain refusal, the dialogue
    resumed the phone question and the call closed registered while the
    caller was still asking for the bridge."""
    from .evidence import extract_client_facts
    from .resolution import detect_refuse_or_ticket

    # An explicit registration DEMAND is never a keep-solving signal, no matter
    # what other words ride along ("nenoriu tikrinti toliau, UŽREGISTRUOKIT" —
    # live 2026-08-13: 'tikrin'/'toliau' marks cancelled the demanded dialogue).
    if detect_refuse_or_ticket(user_input) == "demand":
        return False

    low = (user_input or "").lower()
    if bool(extract_client_facts(user_input)):
        return True
    # Polarity guard (live 2026-08-13): "nebeSPRENDžiam" matched the 'sprend'
    # mark and cancelled the ticket dialogue the caller had just DEMANDED. A
    # mark only counts when the word carrying it is not itself negated.
    for token in low.split():
        word = token.strip(".,!?…")
        if any(m in word for m in vocab("continue_solving_marks")) and not word.startswith(
            vocab("negation_prefixes")
        ):
            return True
    return False


def abort_ticket_to_solving(state: Any, rt: Any) -> None:
    """Drop the ticket dialogue WITHOUT closing the call and hand the turn
    back to solving — the narrator says so and re-anchors the last
    instruction (directive consumed in the facts block)."""
    state.ticket.stage = None
    state.ticket.context = None
    state.ticket.resume_fix_note = True
    state.dialog.resync_note = True  # C: re-anchor from the ledger, no improvising
    from .dialog_registry import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ticket")
    rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_to_solving")


def ticket_stage_reply(state: Any, rt: Any) -> str:
    """The scripted reply for the CURRENT dialogue stage. The first phone ask
    carries the intro (phone solving is over -> registering, and WHY), so the
    caller hears the transition before the contact questions. Marks the stage
    question as ASKED — only then does the capture accept an answer — and
    speaks the retry phrasing after an unclear answer."""
    from .contract.locale import phrase
    from .dialog_registry import register as _q_register
    from .graph_v2.state import TicketContext

    ctx = state.ticket.context or TicketContext()
    if ctx.ask_cancel_confirm:
        ctx.ask_cancel_confirm = False
        ctx.cancel_confirm_out = True
        ctx.last_kind = "cancel_confirm"
        _q_register(state, rt, "ticket", "ticket_cancel")
        return phrase("identification.ticket_cancel_confirm")
    retry, ctx.ask_retry = ctx.ask_retry, None
    if retry == "phone":
        ctx.last_kind = "retry_phone"
        _q_register(state, rt, "ticket", "ticket_phone")
        return phrase("identification.ticket_phone_retry")
    if retry == "hours":
        ctx.last_kind = "retry_hours"
        _q_register(state, rt, "ticket", "ticket_hours")
        return phrase("identification.ticket_hours_retry")
    if state.ticket.stage == "hours":
        ctx.hours_asked = True
        ctx.last_kind = "hours"
        _q_register(state, rt, "ticket", "ticket_hours")
        return phrase("identification.ticket_hours")
    parts = []
    if not ctx.intro_done:
        ctx.intro_done = True
        ctx.last_kind = "phone_intro"
        # After a WORKING bridge "telefonu išspręsti nepavyks" is jarring —
        # the internet just came back (live 2026-08-12). The intro then
        # states the success and registers the ROUTER replacement.
        if state.resolution.bridge_bound:
            parts.append(phrase("identification.ticket_intro_bridge"))
        else:
            parts.append(phrase("identification.ticket_intro", priezastis=ticket_need(state, rt)))
    else:
        ctx.last_kind = "phone"
    ctx.phone_asked = True
    _q_register(state, rt, "ticket", "ticket_phone")
    parts.append(phrase("identification.ticket_phone"))
    return " ".join(parts)


def fmt_phone(nr: str | None) -> str:
    """Group a dialable number for TTS ("+370 600 12353"); free text passes through."""
    raw = (nr or "").strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if len(re.sub(r"\D", "", digits)) < 6 or digits != raw:
        return raw
    if digits.startswith("+370") and len(digits) == 12:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    return digits


def amend_ticket_note(state: Any, rt: Any, note: str) -> bool:
    """Post-registration correction (live 2026-08-25: the caller gave a NEW
    call-back number after 'Užregistravau' and it vanished into the goodbye).
    Appends the note to the registered ticket's details so the worker sees it.
    Best-effort: False on any hiccup — the spoken acknowledgement then still
    happens, but the trace records note_failed."""
    tid = state.ticket.ticket_id
    if not tid or not note:
        return False
    try:
        result = rt.tools.run(
            state,
            rt,
            "append_ticket_note",
            {"ticket_id": tid, "note": note},
            reason="ticket_amend",
            apply=False,
        )
        return bool(result.data.get("success"))
    except Exception:  # a failed note must never break the goodbye
        import logging

        logging.getLogger(__name__).warning("ticket note amend failed", exc_info=True)
        return False


def finish_ticket_dialogue(state: Any, rt: Any) -> str:
    """All contacts collected (or defaulted) — register, close, announce. The
    announce repeats the number and hours back, so "kokiu numeriu?" never needs
    asking (observed live: the caller asked twice and got a goodbye)."""
    from .contract.locale import phrase
    from .executor_flow import register_ticket_from_state

    s = state
    if not s.ticket.contact_phone:
        s.ticket.contact_phone = s.identity.caller_phone  # default: the number they call from
    if not s.ticket.contact_hours:
        s.ticket.contact_hours = phrase("ticket.default_hours")
    ctx = state.ticket.context
    step_id = ctx.step_id if ctx else None
    note = (ctx.note if ctx else None) or ""
    state.ticket.stage = None
    state.ticket.context = None
    from .dialog_registry import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ticket")  # contacts collected — the dialogue is over
    register_ticket_from_state(state, rt, step_id)
    s.closing.case_closed = True
    s.closing.closed_reason = "registered" if s.ticket.ticket_id else "declined"
    val = s.ticket.contact_hours
    val = val[:1].lower() + val[1:]  # mid-sentence: "skambinti galima bet kada"
    return (
        phrase("identification.ticket_done", nr=fmt_phone(s.ticket.contact_phone), val=val) + note
    )


def registration_claim_guard(state: Any, rt: Any, content: str) -> str | None:
    """The LLM narrator CLAIMED a registration that never happened (observed
    live 2026-08-05: "Užregistravau gedimą…" at dr_recheck, ticket_id None,
    the caller hung up trusting it). Words may not outrun the engine: when a
    claim is detected with no ticket and no dialogue running, the contact
    dialogue begins NOW and its phone question is APPENDED to the reply —
    the promise becomes the process. Returns the appended text or None."""
    s = state
    low = (content or "").lower()
    if not any(m in low for m in vocab("registration_claim")):
        return None
    # A DEVICE registration ("užregistravau jūsų naują routerį prie linijos" —
    # the MAC bind, live eval 2026-08-21) is not a fault-ticket claim: the
    # guard fires only when the sentence is about the ticket/technician.
    if not any(m in low for m in vocab("registration_claim_subject")):
        return None
    if (
        s.ticket.ticket_id
        or state.ticket.stage
        or s.closing.case_closed
        or not s.identity.customer_id
    ):
        return None
    if s.resolution.procedure is None:
        return None
    from .contract.locale import phrase
    from .resolution import get_strategy

    strat = get_strategy(s.resolution.procedure.get("verdict"))
    esc = strat.by_role("escalate") if strat else None
    s.resolution.procedure.setdefault("escalate_reason", "phone_fix_failed")
    begin_ticket_dialogue(state, rt, esc)
    if state.ticket.stage != "phone":
        return None  # could not start (defensive) — nothing to append
    rt.tracer.emit("decision", intent="ticket_dialogue", action="claim_guard")
    if state.ticket.context is not None:
        state.ticket.context.intro_done = True  # the claim already announced it
        state.ticket.context.phone_asked = True  # appended below — answers count
    return " " + phrase("identification.ticket_phone")
