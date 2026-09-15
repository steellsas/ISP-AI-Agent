"""
Perception flow — reading the caller's turn before anyone acts on it: the
evidence ingest (understanding pass + keyword extractor), side-topic
classification, the anchor question, and the pre-turn guard sweep.

R3 extraction (docs/ROADMAP_REFACTORING.md §4): moved verbatim out of ReactAgent; R4
merges the understand/intent/classifier calls into ONE fast LLM call here. Functions
take (state, rt) — the call state and the AgentRuntime; flows call each other
directly; tools run through rt.tools (the gateway).
"""

from __future__ import annotations

import logging
import re

from .contract import limits
from .contract.locale import vocab
from .trace import trace_note

logger = logging.getLogger(__name__)


def engine_resolve_from_slots(state, rt) -> bool:
    """Deterministic identification commit from clearly-heard slots: the ENGINE
    calls resolve_address (+ the silent diagnose) itself — no LLM tool-call
    hesitancy, no confirm-round relapse. True when a customer committed."""
    from .execute.diagnosis import ensure_diagnosed

    p = state.identity.profile
    args: dict[str, str] = {
        "street": str(p.street.value),
        "house_number": str(p.house.value),
    }
    if p.apartment.value:
        args["apartment_number"] = str(p.apartment.value)
    if p.city.value:
        args["city"] = str(p.city.value)
    try:
        rt.tools.run(state, rt, "resolve_address", args, reason="resolve_from_slots")
    except Exception as e:  # pragma: no cover - best-effort
        trace_note(rt.tracer, state, "engine_resolve", str(e), level="error")
        return False
    if not state.identity.customer_id:
        return False
    # B-wave registry: the identification question (address/code) got its
    # answer — a contract committed; the next question (the name) is
    # registered by its own owner.
    from .decide.question import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ident")
    ensure_diagnosed(state, rt)
    return True


def ticket_capture(state, rt, user_input: str) -> None:
    """Ticket-dialogue capture: the previous reply asked for the contact number /
    hours — read the answer. A question falls through to the LLM (the stage stays
    and re-asks); a farewell fast-forwards with defaults (the caller is done
    talking — register with what we have)."""
    from .ticket_flow import abort_ticket_to_solving, wants_to_keep_solving

    s = state
    from .perceive.detectors import detect_farewell, detect_ticket_consent

    state.turn.ticket_offscript_question = False
    low_q = (user_input or "").lower()
    from .graph_v2.state import TicketContext

    ctx = state.ticket.context or TicketContext()
    # Cancel-confirm answer (2026-08-11): the previous reply asked
    # "registruoti, ar tikrai nereikia?" — read THIS turn against that
    # question only. Live, a bare "Ne." (a barge-in crumb) cancelled the
    # ticket AND closed the call in one breath; cancelling is a one-way
    # door, so it now takes a confirmed refusal.
    cancel_confirm_out, ctx.cancel_confirm_out = ctx.cancel_confirm_out, False
    if cancel_confirm_out:
        from .perceive.detectors import is_bare_negation

        # "Ne, tai pajunkim tą kompiuterį" refuses the TICKET, not the
        # help — back to solving, never back to the phone question.
        if wants_to_keep_solving(state, rt, user_input):
            abort_ticket_to_solving(state, rt)
            return
        if is_bare_negation(user_input) or any(
            m in low_q for m in vocab("ticket_cancel_confirmed")
        ):
            state.ticket.stage = "cancelled"
            from .decide.question import clear_owner as _q_clear_owner

            _q_clear_owner(state, rt, "ticket")
            rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
            return
        # Anything else resumes the registration — the stage re-asks.
        rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm_resumed")
        return
    # Understanding pass first (2026-08-10, Andrius): caller phrasing
    # cannot be predicted — "Bet kada galima per pietus iš ryto" IS an
    # P5 (closing wave, live 2026-09-07: "Gerai, aš paskambinsiu vėliau"
    # mid-ticket-dialogue got "ar tiks numeris?"): a first-person "I will
    # call back" IS a callback wish, not a contact answer — the caller
    # does not want the registration now. Same warm close as the
    # cannot-now ladder: no ticket, callback goodbye.
    if any(m in low_q for m in vocab("will_call_back_first_person")):
        state.ticket.stage = None
        state.ticket.context = None
        from .decide.question import clear_owner as _q_clear_owner

        _q_clear_owner(state, rt, "ticket")
        s.closing.case_closed = True
        s.closing.closed_reason = "callback"
        state.closing.callback_goodbye_due = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="callback_close")
        return
    # hours answer, but "galima" sat on the keyword question list and
    # diverted it. The model reads the answer against THIS question;
    # keyword logic below stays as the fallback when it is unavailable.
    und_handled = False
    from .perceive import understand as _und

    if _und.enabled():
        ut = _und.understand_ticket(
            user_input,
            stage=state.ticket.stage,
            anchor=(s.dialog.last_question or ""),
            model=rt.config.model,
        )
        if ut is not None:
            und_handled = True
            rt.tracer.emit(
                "understand_ticket",
                stage=state.ticket.stage,
                type=ut["type"],
                value=ut.get("value"),
            )
            if ut["type"] == "question":
                # Echo of our own offer (D, live 2026-08-20): "Ar tiks tas,
                # iš kurio skambinu?" repeated back with rising intonation
                # is CONSENT — answering it and re-asking doubled the
                # question. Fuzzy overlap with what we just asked decides.
                if state.ticket.stage == "phone":
                    from .barge_in import token_overlap

                    if token_overlap(user_input, s.dialog.last_question or "") >= limits.get(
                        "echo_overlap_threshold"
                    ):
                        s.ticket.contact_phone = s.identity.caller_phone
                        state.ticket.stage = "hours"
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="phone_echo_consent"
                        )
                        return
                state.turn.ticket_offscript_question = True
                rt.tracer.emit("decision", intent="ticket_dialogue", action="question")
                return
            if ut["type"] == "refusal":
                # Refusal WITH solving content skips the confirm — the
                # caller told us what they want: keep fixing.
                if wants_to_keep_solving(state, rt, user_input):
                    abort_ticket_to_solving(state, rt)
                    return
                # One confirm round before the one-way door (2026-08-11):
                # "Ne." to "ar tiks šis numeris?" may mean "kitu numeriu",
                # not "neregistruokite" — clarify before dropping the
                # ticket the caller was just promised.
                if ctx.cancel_confirm_asked:
                    state.ticket.stage = "cancelled"
                    from .decide.question import clear_owner as _q_clear_owner

                    _q_clear_owner(state, rt, "ticket")
                    rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
                    return
                ctx.cancel_confirm_asked = True
                ctx.ask_cancel_confirm = True
                rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm")
                return
            if not getattr(ctx, f"{state.ticket.stage}_asked", False):
                return  # trigger-swallow guard (question not asked yet)
            value = ut.get("value")
            if value:
                if state.ticket.stage == "phone":
                    digits = re.sub(r"\D", "", value)
                    if value == "same_number":
                        s.ticket.contact_phone = s.identity.caller_phone
                    elif len(digits) >= 6:
                        s.ticket.contact_phone = re.sub(r"[^\d+]", "", value)[:20]
                    else:
                        value = None  # not a usable number — keyword/retry path
                    if value is not None:
                        rt.tracer.emit(
                            "decision", intent="ticket_dialogue", action="phone_captured"
                        )
                        state.ticket.stage = "hours"
                        return
                else:
                    s.ticket.contact_hours = re.sub(r"[?!]", " ", value).strip(" .,")[:80]
                    rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_captured")
                    state.ticket.stage = "done"
                    return
            # No value — fall through to the keyword/retry machinery.
    # W0-C (live 2026-08-25): STT turned "patogiausia" into "KODĖL
    # tokiausia skambinti nuo 17-18 val." — the question keyword diverted
    # a perfectly good answer to the LLM and the capture never saw it.
    # CONTENT BEATS FORM: an utterance carrying a plausible answer for the
    # CURRENT stage is read by the capture machinery, question-shaped or not.
    # Digits only — "Bet kada galima skambinti?" is the caller ASKING and
    # must still divert; a garbled question-word around "nuo 17-18" is not.
    if state.ticket.stage == "phone":
        _answer_content = len(re.sub(r"\D", "", user_input or "")) >= 6
    else:
        _answer_content = bool(re.search(r"\d", user_input or ""))
    if (
        not und_handled
        and not _answer_content
        and any(m in low_q for m in vocab("ticket_offscript_question"))
    ):
        # Keyword question-divert (fallback only): the pass, when it ran,
        # already said this is NOT a question.
        state.turn.ticket_offscript_question = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="question")
        return
    # Explicit "do not register" cancels the dialogue (their call, their
    # choice) — after ONE confirm round; the scripted reply closes with a
    # goodbye only on the confirmed refusal.
    if not und_handled and any(m in low_q for m in vocab("ticket_cancel")):
        if wants_to_keep_solving(state, rt, user_input):
            abort_ticket_to_solving(state, rt)
            return
        if ctx.cancel_confirm_asked:
            state.ticket.stage = "cancelled"
            from .decide.question import clear_owner as _q_clear_owner

            _q_clear_owner(state, rt, "ticket")
            rt.tracer.emit("decision", intent="ticket_dialogue", action="cancelled")
            return
        ctx.cancel_confirm_asked = True
        ctx.ask_cancel_confirm = True
        rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_confirm")
        return
    if detect_farewell(user_input):
        state.ticket.stage = "done"
        return
    # An answer counts ONLY after its question was actually ASKED. The
    # dialogue can begin mid-turn (escalate fires while processing the
    # caller's utterance) — live 2026-08-05 the TRIGGER phrase "Neturi
    # kompiutera" was swallowed as the phone number.
    if not getattr(ctx, f"{state.ticket.stage}_asked", False):
        return
    clean = user_input.strip().strip(" .?!,")
    if state.ticket.stage == "phone":
        from .perceive.detectors import is_backchannel

        digits = re.sub(r"[^\d+]", "", user_input)
        if len(re.sub(r"\D", "", digits)) >= 6:
            s.ticket.contact_phone = digits[:20]
        elif detect_ticket_consent(user_input) == "yes" or is_backchannel(user_input):
            # "tiks šis" / a garbled yes ("T." — STT of "Taip", observed
            # live as tel. on the ticket) — the number they call from.
            s.ticket.contact_phone = s.identity.caller_phone
        elif ctx.phone_retry:
            # Second unclear answer — default to the caller-ID and move on.
            s.ticket.contact_phone = s.identity.caller_phone
        else:
            # Not a number, not a yes — the agent SAYS what it needs and
            # re-asks ONCE ("understand the answer, re-ask when it is not
            # one" — 2026-08-05); garbage never lands on the ticket.
            ctx.phone_retry = True
            ctx.ask_retry = "phone"
            rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_retry")
            return
        rt.tracer.emit("decision", intent="ticket_dialogue", action="phone_captured")
        state.ticket.stage = "hours"
    else:
        # STT sticks "?" mid-string too ("Bet kada? Bet kurio laiko?") —
        # scrub ALL question/exclamation marks before the ticket/announce.
        clean = re.sub(r"\s+", " ", re.sub(r"[?!]", " ", clean)).strip(" .,")
        low_h = clean.lower()
        plausible = bool(re.search(r"\d", low_h)) or any(
            m in low_h for m in vocab("contact_hours_marks")
        )
        if not plausible and not ctx.hours_retry:
            ctx.hours_retry = True
            ctx.ask_retry = "hours"
            rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_retry")
            return
        # Strip trailing STT punctuation — "Bet kada?" landed on the ticket
        # (and in the announce) with the question mark. Second unclear
        # answer defaults to "bet kada" (spoken back in the announce).
        s.ticket.contact_hours = clean[:80] if plausible else "bet kada"
        rt.tracer.emit("decision", intent="ticket_dialogue", action="hours_captured")
        state.ticket.stage = "done"
    return
