"""Ticket rules — the contact dialogue before a registration (§5 row 3).

The caller's answer to the number / hours question is read first (capture, one retry
each, the cancel-confirm, the callback wish); then the dialogue asks its next
question, registers once both contacts are known, or ends on a confirmed refusal.
"""

from __future__ import annotations

import re
from typing import Any

from ...contract import limits
from ...contract.locale import phrase_or, vocab
from ..plan import Action, Say, TurnPlan

STAGE = "ticket"


def caller_owed(state: Any) -> bool:
    """A ticket started right at identification (a request, a no-path fault) still owes
    the caller-name question: it comes before the contact dialogue."""
    s = state
    return bool(s.identity.customer_id and s.identity.result_pending and not s.identity.caller_name)


def plan(state: Any, rt: Any) -> TurnPlan | None:

    s = state
    user_input = s.turn.user_input
    if s.ticket.stage not in ("phone", "hours") or not user_input or s.closing.case_closed:
        return None
    if caller_owed(state):
        return None  # the answer is the caller's name — the identification ladder reads it
    ticket_capture(state, rt, user_input)
    # A first-person "I will call back" closed the dialogue — the warm goodbye.
    if s.closing.callback_goodbye_due:
        s.closing.callback_goodbye_due = False
        return _scripted("ticket.callback_close", key="identification.callback_goodbye")
    if s.ticket.stage in ("phone", "hours"):
        rule, words = ticket_question_turn(state, rt)
        if words is None:
            return TurnPlan(owner="ticket", rule=rule, say=Say(kind="directive", stage=STAGE))
        return _scripted(rule, text=words)
    if s.ticket.stage == "done":
        return TurnPlan(
            owner="ticket",
            rule="ticket.register",
            action=Action(type="register_ticket"),
            say=Say(kind="phrase", stage=STAGE),
        )
    if s.ticket.stage == "cancelled":
        from ...contract.locale import phrase

        s.ticket.stage = None
        s.ticket.context = None
        return _scripted(
            "ticket.cancelled",
            text=phrase("ticket.declined") + phrase("identification.goodbye"),
            action=Action(type="close", name="declined", args={"complete": True}),
        )
    # The caller refused the registration but wants to keep solving — the narrator
    # says so and re-anchors the last instruction.
    return TurnPlan(
        owner="ticket", rule="ticket.back_to_solving", say=Say(kind="directive", stage=STAGE)
    )


def _scripted(
    rule: str, key: str | None = None, text: str | None = None, action: Any = None
) -> TurnPlan:
    return TurnPlan(
        owner="ticket",
        rule=rule,
        action=action or Action(type="none"),
        say=Say(kind="phrase", key=key, text=text, stage=STAGE),
    )


def ticket_capture(state, rt, user_input: str) -> None:
    """Ticket-dialogue capture: the previous reply asked for the contact number /
    hours — read the answer. A question falls through to the LLM (the stage stays
    and re-asks); a farewell fast-forwards with defaults (the caller is done
    talking — register with what we have)."""

    s = state
    from ...perceive.detectors import detect_farewell, detect_ticket_consent

    state.turn.ticket_offscript_question = False
    low_q = (user_input or "").lower()
    from ...graph_v2.state import TicketContext

    ctx = state.ticket.context or TicketContext()
    # Cancel-confirm answer (2026-08-11): the previous reply asked
    # "registruoti, ar tikrai nereikia?" — read THIS turn against that
    # question only. Live, a bare "Ne." (a barge-in crumb) cancelled the
    # ticket AND closed the call in one breath; cancelling is a one-way
    # door, so it now takes a confirmed refusal.
    cancel_confirm_out, ctx.cancel_confirm_out = ctx.cancel_confirm_out, False
    if cancel_confirm_out:
        from ...perceive.detectors import is_bare_negation

        # "Ne, tai pajunkim tą kompiuterį" refuses the TICKET, not the
        # help — back to solving, never back to the phone question.
        if wants_to_keep_solving(state, rt, user_input):
            abort_ticket_to_solving(state, rt)
            return
        if is_bare_negation(user_input) or any(
            m in low_q for m in vocab("ticket_cancel_confirmed")
        ):
            state.ticket.stage = "cancelled"
            from ...decide.question import clear_owner as _q_clear_owner

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
        from ...decide.question import clear_owner as _q_clear_owner

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
    from ...perceive import understand as _und

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
                    from ...barge_in import token_overlap

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
                    from ...decide.question import clear_owner as _q_clear_owner

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
            from ...decide.question import clear_owner as _q_clear_owner

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
        from ...perceive.detectors import is_backchannel

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


# Escalate reasons after which nothing was done at the device: the ticket must
# not claim the pack's post-action wording.
NOTHING_DONE_REASONS = frozenset({"caller_refused", "cannot_now", "cannot_now_asks_ticket"})


def ticket_need(state: Any, rt: Any) -> str:
    """Human wording of WHY the ticket is needed ("reikalingas naujas
    maršrutizatorius"), for the intro announce and the ticket itself — never
    the raw verdict key."""
    from ...contract.locale import phrase
    from ...evidence import fault_need

    s = state
    if s.ticket.request_type:
        return phrase("ticket.need_request")
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
    # The unclear fault names no cause to the caller (no telemetry jargon).
    if (s.resolution.procedure or {}).get("verdict") == "unclear_fault":
        return phrase("ticket.need_unclear")
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
    from ...evidence import extract_client_facts
    from ...perceive.detectors import detect_refuse_or_ticket

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
    from ...decide.question import clear_owner as _q_clear_owner

    _q_clear_owner(state, rt, "ticket")
    rt.tracer.emit("decision", intent="ticket_dialogue", action="cancel_to_solving")


def ticket_stage_reply(state: Any, rt: Any) -> str:
    """The scripted reply for the CURRENT dialogue stage. The first phone ask
    carries the intro (phone solving is over -> registering, and WHY), so the
    caller hears the transition before the contact questions. Marks the stage
    question as ASKED — only then does the capture accept an answer — and
    speaks the retry phrasing after an unclear answer."""
    from ...contract.locale import phrase
    from ...decide.question import register as _q_register
    from ...graph_v2.state import TicketContext

    ctx = state.ticket.context or TicketContext()
    if ctx.ask_cancel_confirm:
        ctx.ask_cancel_confirm = False
        ctx.cancel_confirm_out = True
        ctx.last_kind = "cancel_confirm"
        _q_register(state, rt, "ticket", "ticket_cancel")
        if state.ticket.request_type:
            return phrase("identification.ticket_cancel_confirm_request")
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
        if state.ticket.request_type:
            parts.append(phrase("identification.ticket_intro_request"))
        elif state.resolution.bridge_bound:
            parts.append(phrase("identification.ticket_intro_bridge"))
        else:
            parts.append(phrase("identification.ticket_intro", reason=ticket_need(state, rt)))
    else:
        ctx.last_kind = "phone"
    ctx.phone_asked = True
    _q_register(state, rt, "ticket", "ticket_phone")
    parts.append(phrase("identification.ticket_phone"))
    return " ".join(parts)


def ticket_question_turn(state: Any, rt: Any) -> tuple[str, str | None]:
    """The contact question of this turn (stage phone/hours): (rule id, words). No
    words = the narrator speaks: an off-script question, or — Zone 1 (scripts ->
    directives, Andrius 2026-08-20) — a QUESTION moment worded into the flow of the
    conversation (the directive carries the scripted fallback); retries and the
    cancel-confirm stay scripted (precision beats style on a repeat)."""
    import os

    if state.turn.ticket_offscript_question:
        return "ticket.offscript_question", None
    scripted = ticket_stage_reply(state, rt)
    ctx = state.ticket.context
    kind = ctx.last_kind if ctx else None
    if os.getenv("NARRATOR_QUESTIONS", "on").lower() == "on" and kind in (
        "phone_intro",
        "phone",
        "hours",
    ):
        state.turn.directives.ticket = {"kind": kind, "fallback": scripted}
        return f"ticket.ask_{kind}", None
    return f"ticket.{kind}", scripted
