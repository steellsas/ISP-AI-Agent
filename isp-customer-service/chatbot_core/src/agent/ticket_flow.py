"""
Ticket-confirmation dialogue flow — the scripted contact ladder before EVERY
registration (2026-08-04): the contact number is ALWAYS asked, then the
convenient hours; _register_ticket_from_state creates the ticket
deterministically from STATE.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of
ReactAgent. Both engines use it — the legacy ReactAgent through thin delegate
methods, the v2 ticket/executor nodes directly. The stage value lives on
AgentState.ticket_stage (promoted); the dialogue CONTEXT (engine._ticket_ctx)
still holds a live resolution Step reference, so it stays engine-local until
steps are addressable by id.
"""

from __future__ import annotations

import re
from typing import Any

# A ticket refusal that CARRIES solving content — the caller is refusing the
# REGISTRATION, not the help.
CONTINUE_SOLVING_MARKS = (
    "jung",  # jungiu / pajunkim / prijunkite
    "kompiuter",
    "kabel",
    "bandom",
    "bandyk",
    "pabandy",
    "tikrin",
    "tęs",
    "tes ",
    "teskim",
    "toliau",
    "darom",
    "spręs",
    "spres",
)


def begin_ticket_dialogue(engine: Any, step) -> None:
    """Start the ticket-confirmation dialogue: before ANY registration the agent
    collects the contact number (ALWAYS asked — the caller may be on a
    company/other phone, or the DB number stale) and when it is convenient to
    call. The scripted ladder asks; once complete, finish_ticket_dialogue
    registers with the contacts on the ticket."""
    if engine.state.ticket_id or engine._ticket_stage:
        return  # already registered / already collecting
    engine._ticket_ctx = {"step": step}
    engine._ticket_stage = "phone"
    engine.tracer.emit("decision", intent="ticket_dialogue", action="start")


def ticket_need(engine: Any) -> str:
    """Human wording of WHY the ticket is needed ("reikalingas naujas
    maršrutizatorius"), for the intro announce and the ticket itself — never
    the raw verdict key."""
    from .evidence import fault_need
    from .glossary import DIAGNOSIS_LT, TICKET_NEED_LT

    s = engine.state
    cause = (s.hypothesis or {}).get("cause") or (s.resolution or {}).get("verdict") or ""
    need = fault_need(cause) or TICKET_NEED_LT.get(cause)  # file first, code fallback
    if need:
        return need
    # No verdict at all — an in-scope fault the agent's knowledge cannot
    # resolve. HONEST ticket type (Andrius 2026-09-02): "neaiškus gedimas" —
    # feeds the analysis/improvement loop instead of an improvised cause.
    if not cause:
        return "gedimo tipas neaiškus — priežastis telefonu nenustatyta, perduota analizei"
    return DIAGNOSIS_LT.get(cause, cause)


def wants_to_keep_solving(engine: Any, user_input: str | None) -> bool:
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
        if any(m in word for m in CONTINUE_SOLVING_MARKS) and not word.startswith(("ne", "nebe")):
            return True
    return False


def abort_ticket_to_solving(engine: Any) -> None:
    """Drop the ticket dialogue WITHOUT closing the call and hand the turn
    back to solving — the narrator says so and re-anchors the last
    instruction (directive consumed in the facts block)."""
    engine._ticket_stage = None
    engine._ticket_ctx = None
    engine._resume_fix_note = True
    engine._resync_note = True  # C: re-anchor from the ledger, no improvising
    engine.tracer.emit("decision", intent="ticket_dialogue", action="cancel_to_solving")


def ticket_stage_reply(engine: Any) -> str:
    """The scripted reply for the CURRENT dialogue stage. The first phone ask
    carries the intro (phone solving is over -> registering, and WHY), so the
    caller hears the transition before the contact questions. Marks the stage
    question as ASKED — only then does the capture accept an answer — and
    speaks the retry phrasing after an unclear answer."""
    from .identification import phrase

    ctx = engine._ticket_ctx if engine._ticket_ctx is not None else {}
    if ctx.pop("ask_cancel_confirm", None):
        ctx["cancel_confirm_out"] = True
        ctx["last_kind"] = "cancel_confirm"
        return phrase("ticket_cancel_confirm")
    retry = ctx.pop("ask_retry", None)
    if retry == "phone":
        ctx["last_kind"] = "retry_phone"
        return phrase("ticket_phone_retry")
    if retry == "hours":
        ctx["last_kind"] = "retry_hours"
        return phrase("ticket_hours_retry")
    if engine._ticket_stage == "hours":
        ctx["hours_asked"] = True
        ctx["last_kind"] = "hours"
        return phrase("ticket_hours")
    parts = []
    if not ctx.get("intro_done"):
        ctx["intro_done"] = True
        ctx["last_kind"] = "phone_intro"
        # After a WORKING bridge "telefonu išspręsti nepavyks" is jarring —
        # the internet just came back (live 2026-08-12). The intro then
        # states the success and registers the ROUTER replacement.
        if getattr(engine, "_bridge_bound", False):
            parts.append(phrase("ticket_intro_bridge"))
        else:
            parts.append(phrase("ticket_intro", priezastis=ticket_need(engine)))
    else:
        ctx["last_kind"] = "phone"
    ctx["phone_asked"] = True
    parts.append(phrase("ticket_phone"))
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


def amend_ticket_note(engine: Any, note: str) -> bool:
    """Post-registration correction (live 2026-08-25: the caller gave a NEW
    call-back number after 'Užregistravau' and it vanished into the goodbye).
    Appends the note to the registered ticket's details so the worker sees it.
    Best-effort: False on any hiccup — the spoken acknowledgement then still
    happens, but the trace records note_failed."""
    tid = engine.state.ticket_id
    if not tid or not note:
        return False
    try:
        from .tools import get_db

        db = get_db()
        with db.cursor() as cursor:
            cursor.execute("SELECT details FROM tickets WHERE ticket_id = ?", (tid,))
            row = cursor.fetchone()
            if not row:
                return False
            details = (dict(row).get("details") or "").rstrip()
            cursor.execute(
                "UPDATE tickets SET details = ? WHERE ticket_id = ?",
                (f"{details}\n[PATIKSLINTA] {note}".strip(), tid),
            )
        return True
    except Exception:  # a failed note must never break the goodbye
        import logging

        logging.getLogger(__name__).warning("ticket note amend failed", exc_info=True)
        return False


def finish_ticket_dialogue(engine: Any) -> str:
    """All contacts collected (or defaulted) — register, close, announce. The
    announce repeats the number and hours back, so "kokiu numeriu?" never needs
    asking (observed live: the caller asked twice and got a goodbye)."""
    from .identification import phrase

    s = engine.state
    if not s.contact_phone:
        s.contact_phone = s.caller_phone  # default: the number they call from
    if not s.contact_hours:
        s.contact_hours = "bet kada"
    step = (engine._ticket_ctx or {}).get("step")
    note = (engine._ticket_ctx or {}).get("note") or ""
    engine._ticket_stage = None
    engine._ticket_ctx = None
    engine._register_ticket_from_state(step)
    s.case_closed = True
    s.closed_reason = "registered" if s.ticket_id else "declined"
    val = s.contact_hours
    val = val[:1].lower() + val[1:]  # mid-sentence: "skambinti galima bet kada"
    return phrase("ticket_done", nr=fmt_phone(s.contact_phone), val=val) + note


def registration_claim_guard(engine: Any, content: str) -> str | None:
    """The LLM narrator CLAIMED a registration that never happened (observed
    live 2026-08-05: "Užregistravau gedimą…" at dr_recheck, ticket_id None,
    the caller hung up trusting it). Words may not outrun the engine: when a
    claim is detected with no ticket and no dialogue running, the contact
    dialogue begins NOW and its phone question is APPENDED to the reply —
    the promise becomes the process. Returns the appended text or None."""
    s = engine.state
    low = (content or "").lower()
    if not any(m in low for m in ("užregistrav", "uzregistrav", "registruoju gedim")):
        return None
    # A DEVICE registration ("užregistravau jūsų naują routerį prie linijos" —
    # the MAC bind, live eval 2026-08-21) is not a fault-ticket claim: the
    # guard fires only when the sentence is about the ticket/technician.
    if not any(m in low for m in ("gedim", "meistr", "tiket", "koleg", "technik")):
        return None
    if s.ticket_id or engine._ticket_stage or s.case_closed or not s.customer_id:
        return None
    if s.resolution is None:
        return None
    from .identification import phrase
    from .resolution import get_strategy

    strat = get_strategy(s.resolution.get("verdict"))
    esc = strat.step("escalate") if strat else None
    s.resolution.setdefault("escalate_reason", "Sprendimas telefonu nepavyko.")
    begin_ticket_dialogue(engine, esc)
    if engine._ticket_stage != "phone":
        return None  # could not start (defensive) — nothing to append
    engine.tracer.emit("decision", intent="ticket_dialogue", action="claim_guard")
    if engine._ticket_ctx is not None:
        engine._ticket_ctx["intro_done"] = True  # the claim already announced it
        engine._ticket_ctx["phone_asked"] = True  # appended below — answers count
    return " " + phrase("ticket_phone")
