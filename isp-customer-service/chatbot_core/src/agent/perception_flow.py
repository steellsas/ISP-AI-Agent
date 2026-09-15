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
from .contract.locale import vocab, vocab_set
from .dialog_utils import last_agent_question
from .perceive.caller import holder_name_matches
from .perceive.slots import mentions_other_street
from .trace import trace_note

logger = logging.getLogger(__name__)


def pre_turn_guards(state, rt, user_input: str) -> None:
    """Deterministic per-turn guards, run BEFORE the LLM sees the turn.

    (1) Address-offer reply guard: a reply to "Ar skambinate dėl X?" commits the
        account ONLY on a CLEAN yes — a garbled/mixed reply ("Taip, nebija" = STT
        mangle of a denial) vetoes the commit and the agent re-asks (observed live:
        wrong apartment's debt read to the caller).
    (2) Reopen identification: an already-identified caller says they are calling
        about a DIFFERENT address -> drop the identity and ask for the address
        again instead of carrying on about the wrong account."""
    from .identification_flow import reopen_identification
    from .perceive.slots import prefill_slots_from_text
    from .ticket_flow import begin_ticket_dialogue

    s = state
    state.turn.address_confirm_note = None
    state.turn.address_lookup_note = None  # F2: fresh lookup diagnosis per turn
    state.turn.directives.ident = None  # zone 2: ingest may not run pre-identification
    state.turn.reopen_note = False
    if not user_input:
        return
    # (-2) The ticket dialogue's answers are read by the ticket rules (decide).
    if state.ticket.stage in ("phone", "hours"):
        ticket_capture(state, rt, user_input)
        return
    # (-1) Farewell mid-process is a signal to CLARIFY, never to close (policy
    # 2026-08-03): "viso gero" heard during identification / troubleshooting /
    # before the news gets ONE confirm question; only the confirmation ends the
    # call — through the outcome (registration when a strategy is active).
    from .perceive.detectors import detect_farewell, detect_ticket_consent

    if state.dialog.end_confirm_pending and not s.closing.case_closed:
        state.dialog.end_confirm_pending = False
        if detect_farewell(user_input) or detect_ticket_consent(user_input) == "yes":
            if s.resolution.procedure is not None:
                from .resolution import get_strategy

                strat = get_strategy(s.resolution.procedure.get("verdict"))
                esc = strat.by_role("escalate") if strat else None
                s.resolution.procedure["escalate_reason"] = "caller_ended_call"
                if esc is not None:
                    begin_ticket_dialogue(state, rt, esc)  # contacts, then register+close
                else:
                    s.closing.case_closed = True
                    s.closing.closed_reason = "declined"
            else:
                s.closing.case_closed = True
                s.closing.closed_reason = "declined"
            rt.tracer.emit("decision", intent="end_confirmed", action="close")
        else:
            # Changed their mind — hold the walker THIS turn so a "ne, tęskime"
            # is not misrouted as a step answer; resume next turn.
            state.dialog.resume_hold_due = True
            state.dialog.resync_note = True  # C: re-anchor from the ledger, no improvising
            rt.tracer.emit("decision", intent="end_declined", action="resume")
        return
    # A-2 (live 2026-09-07: "Taip taip dėl KITO adreso" was consumed by the
    # walker, and a later side-topic turn burned the question): the SAFETY
    # question's answer is read HERE — in the deterministic turn head, BEFORE
    # the solver/walker. One-owner principle: the last question asked owns
    # the turn. An unclear answer does NOT burn the question — one re-ask,
    # only then written off as "stay with the current address".
    if state.identity.reopen_confirm_utterance is not None and state.identity.reopen_confirm_asked:
        from .dialog_registry import clear as _q_clear
        from .identification_flow import _looks_like_address
        from .perceive.detectors import DETECTORS

        pending = state.identity.reopen_confirm_utterance
        verdict = DETECTORS["yes_no"](user_input)
        if verdict == "yes" or _looks_like_address(user_input):
            state.identity.reopen_confirm_utterance = None
            state.identity.reopen_confirm_asked = False
            _q_clear(state, rt, "reopen_confirm")
            rt.tracer.emit("decision", intent="reopen_confirm", action="confirmed")
            reopen_identification(state, rt, pending)
            # P1 (live 2026-09-07): the pending phrase often already yielded a
            # good address (conf 1.0) — the answer's STT garble ("Tildziai
            # 660-3") must not stomp it; the answer is read only when the
            # address is still missing.
            p = s.identity.profile
            if _looks_like_address(user_input) and not (p.street.value and p.house.value):
                prefill_slots_from_text(state, rt, user_input)  # the answer names it
            # A-2R (live 2026-09-07): the new address was usually ALREADY
            # heard (in the pending phrase "mano adresas Tilžės 60") —
            # identification continues RIGHT NOW: the engine tries resolve;
            # success = new customer, failure leaves the diagnosis note
            # (e.g. "which apartment?"), and the next question belongs to
            # identification, not the old analysis.
            if p.street.value and p.house.value:
                trace_note(
                    rt.tracer,
                    state,
                    "reopen_identity",
                    "new address already heard; engine resolve",
                )
                if engine_resolve_from_slots(state, rt):
                    state.identity.just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
            return
        state.dialog.resume_hold_due = True  # the answer belongs to THIS question, not the walker
        if verdict == "no":
            state.identity.reopen_confirm_utterance = None
            state.identity.reopen_confirm_asked = False
            _q_clear(state, rt, "reopen_confirm")
            rt.tracer.emit("decision", intent="reopen_confirm", action="declined")
        elif state.identity.reopen_confirm_asks < limits.get("reopen_confirm_max_asks"):
            state.identity.reopen_reask_due = True  # the scripted layer re-asks the question
            rt.tracer.emit("decision", intent="reopen_confirm", action="reask")
        else:
            state.identity.reopen_confirm_utterance = None
            state.identity.reopen_confirm_asked = False
            _q_clear(state, rt, "reopen_confirm")
            rt.tracer.emit("decision", intent="reopen_confirm", action="declined_unclear")
        return
    # P-D (live 2026-09-08: "nepatogu, nesu namuose" — the walker's refuse
    # guard escalated into a TICKET in the same turn, and the cannot-now
    # ladder never got its chance because ticket_stage was already set): a
    # cannot-now signal registers a SAFETY question in the turn head, so the
    # registry priority guard holds the walker/solver and the scripted ladder
    # asks its clarify this very turn.
    if (
        s.identity.customer_id
        and s.resolution.procedure
        and not state.ticket.stage
        and not s.closing.case_closed
        and state.dialog.cannot_now_state is None
        and not state.dialog.cannot_now_done
    ):
        from .dialog_registry import pack_owns_cannot_now
        from .perceive.detectors import detect_cannot_now as _dcn_head

        # P-C: an ability_check/locate_device/homework step's question IS the pack's
        # own cannot-now handling — the shield stands down, the walker routes.
        if _dcn_head(user_input) and not pack_owns_cannot_now(state, rt):
            from .dialog_registry import register as _q_register

            _q_register(state, rt, "safety", "cannot_now")  # priority shield this turn
            rt.tracer.emit("decision", intent="cannot_now", action="shield")
    mid_process = not s.closing.case_closed and (
        not s.identity.customer_id
        or s.resolution.procedure is not None
        or state.identity.result_pending
        or (
            bool(s.diagnosis.verdicts)
            and not (state.diagnosis.news_delivered or s.diagnosis.outage_reported)
        )
    )
    if mid_process and detect_farewell(user_input):
        # F1 (live 2026-09-09: "Gerai, sutariam, viso gero" answering the
        # HOMEWORK consent got "Ar tikrai norite baigti?" twice): on the
        # homework step a farewell IS the consent — the walker routes it
        # to the callback terminal; the end-confirm must not intercept.
        from .dialog_registry import active as _q_act

        _qa = _q_act(state, rt)
        from .faults import role_of

        _qa_role = (
            role_of((s.resolution.procedure or {}).get("verdict"), _qa.key.removeprefix("step:"))
            if _qa is not None and _qa.key.startswith("step:")
            else None
        )
        if _qa_role != "homework":
            state.dialog.end_confirm_pending = True
            rt.tracer.emit("decision", intent="farewell_mid_process", action="confirm_end")
            return
    # (0) Caller-intro capture: the previous reply asked WHO is calling (the
    # identification ladder's last rung) — record the answer verbatim (for the
    # RECORD, 5d rule) + a keyword relation read. The deferred check result goes
    # out in THIS turn's reply (see the RESULT facts directive).
    if s.identity.customer_id and state.identity.result_pending and not s.identity.caller_name:
        from .perceive.caller import detect_caller_relation
        from .perceive.detectors import detect_farewell, is_real_question

        # Question by WORDS only — STT sticks "?" onto rising intonation
        # ("Tomas? Ne, mano vardas Tomas…" is the ANSWER, not a question).
        if is_real_question(user_input):
            return  # off-script — the LLM answers; the ladder re-asks next turn
        if not detect_farewell(user_input):
            # Wait/consent-only replies are NOT a name ("Taip.", "Laukiu, laukiu"
            # were captured as names live) — record "nenurodyta" and move on.
            tokens = [t.strip(".,!?") for t in user_input.lower().split()]
            if tokens and all(t in vocab_set("not_a_name") for t in tokens if t):
                s.identity.caller_name = "nenurodyta"
                s.identity.caller_relation = "unknown"
            else:
                # The bare NAME, not the sentence — "Taip. Mano vardas Andrius.
                # Taip, aš sutartį sudaręs asmuo." went on the ticket verbatim.
                from .perceive.caller import extract_caller_name

                s.identity.caller_name = extract_caller_name(user_input) or user_input.strip()[:120]
                s.identity.caller_relation = detect_caller_relation(user_input)
                # Phrasebook (reference dialogue, 2026-09-03): the caller JUST introduced
                # themselves — the next reply opens with a warm acceptance
                # („Malonu, Tomai") instead of a dry „Supratau — X". One-shot.
                state.identity.caller_name_heard = True
            rt.tracer.emit(
                "caller_intro", name=s.identity.caller_name, relation=s.identity.caller_relation
            )
            # B-wave registry: the caller-name question just got its answer.
            from .dialog_registry import clear as _q_clear

            _q_clear(state, rt, "caller_name")
            # №4 (reference dialogue 2026-09-03): the caller claims to be the HOLDER,
            # but the name does not match the DB contract name — one polite
            # clarification WITHOUT saying the DB name (privacy boundary). Fuzzy: for
            # STT garbling („Andrijus" ~ „Andrius") a 4-letter prefix match is enough.
            if s.identity.caller_relation == "holder" and s.identity.caller_name not in (
                None,
                "nenurodyta",
            ):
                if not holder_name_matches(state, rt, s.identity.caller_name):
                    state.identity.holder_clarify_open = True
                    state.identity.holder_clarify_asked = False
                    rt.tracer.emit("decision", intent="holder_name", action="mismatch_clarify")
        return
    if not s.identity.customer_id:
        q = (last_agent_question(state) or "").lower()
        if any(m in q for m in vocab("address_offer_question")):
            from .perceive.detectors import detect_address_confirm

            verdict = detect_address_confirm(user_input)
            if (
                verdict == "yes"
                and s.identity.phone_candidate
                and s.identity.phone_candidate.get("street")
            ):
                # Clean YES to the phone-address OFFER: the ENGINE commits the
                # identity from the candidate parts right now (the model's own
                # resolve-then-narrate path kept relapsing into confirm rounds
                # and skipping the caller question — observed live). The scripted
                # ladder reply asks WHO is calling next.
                c = s.identity.phone_candidate
                p = s.identity.profile
                from .slots import SlotStatus

                p.street.propose(c["street"], 1.0, SlotStatus.HEARD)
                p.house.propose(str(c.get("house") or ""), 1.0, SlotStatus.HEARD)
                if c.get("apartment"):
                    p.apartment.propose(str(c["apartment"]), 1.0, SlotStatus.HEARD)
                if c.get("city"):
                    p.city.propose(str(c["city"]), 1.0, SlotStatus.HEARD)
                if engine_resolve_from_slots(state, rt):
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        "offer confirmed; engine resolve",
                    )
                    state.identity.just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
                return
            if verdict == "yes":
                # A-2R-b (2026-09-07): a "taip" to an address confirm WITHOUT
                # a phone candidate (e.g. after reopen, address heard in the
                # slots) — the engine commits from the slots; a block of
                # flats leaves the apartment note.
                p_y = s.identity.profile
                if p_y.street.value and p_y.house.value:
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        "slots confirmed; engine resolve",
                    )
                    if engine_resolve_from_slots(state, rt):
                        state.identity.just_identified = True
                        from .identification import ask_caller

                        if ask_caller() and not s.identity.caller_name:
                            state.identity.result_pending = True
                    return
            if verdict != "yes":
                # Direct accept (arc v3.1): the caller DICTATED a full other address
                # in this very turn (NLU heard street+house clearly) — the ENGINE
                # resolves + diagnoses it RIGHT NOW (asking the model to call the
                # tool proved unreliable: it narrated "patikrinsiu" without acting,
                # then relapsed into a redundant confirm round). The reply then
                # echoes the address and continues per the identification ladder.
                p = state.identity.profile
                # Street/city inherit from the OFFERED address when the correction
                # names only the house/flat ("Ne, dėl 60 buto 3" — same street;
                # observed live: the engine path did not fire without this).
                if not p.street.value and p.house.value and s.identity.phone_candidate:
                    from .slots import SlotStatus

                    if s.identity.phone_candidate.get("street"):
                        p.street.propose(
                            s.identity.phone_candidate["street"], 0.9, SlotStatus.HEARD
                        )
                    if not p.city.value and s.identity.phone_candidate.get("city"):
                        p.city.propose(
                            str(s.identity.phone_candidate["city"]), 0.9, SlotStatus.HEARD
                        )
                if p.street.value and p.house.value:
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        "offer corrected with a full dictated address; engine resolve",
                    )
                    if engine_resolve_from_slots(state, rt):
                        state.identity.just_identified = True
                        from .identification import ask_caller

                        if ask_caller() and not s.identity.caller_name:
                            state.identity.result_pending = True
                        state.turn.address_confirm_note = (
                            "- IDENTIFIKUOTA (variklis jau atliko patikrą): "
                            f"adresas {s.identity.customer_address}. Atsakymo pradžioje "
                            "pakartok adresą („Supratau — <adresas>.“) ir tęsk "
                            "pagal žemiau esančią kryptį."
                        )
                    else:
                        state.turn.address_confirm_note = (
                            "- KLIENTAS PASAKĖ KITĄ ADRESĄ, bet jo patikrinti "
                            "nepavyko (žr. HEARD ADDRESS) — patikslink trūkstamą "
                            "dalį arba paprašyk pakartoti."
                        )
                else:
                    state.turn.address_confirm_note = (
                        "- ADRESAS NEPATVIRTINTAS: kliento atsakymas AIŠKIAI "
                        "nepatvirtino pasiūlyto adreso (girdisi neigimas ar "
                        "neaiškumas). NEkviesk resolve_address su pasiūlytu adresu. "
                        "Jei klientas įvardijo KITĄ adresą (žr. HEARD ADDRESS) — "
                        "naudok TĄ. Kitu atveju mandagiai perklausk: „Atsiprašau, "
                        "nesupratau — dėl kokio adreso skambinate?“"
                    )
                    trace_note(
                        rt.tracer,
                        state,
                        "address_confirm",
                        f"offer not confirmed (verdict={verdict}); veto commit",
                        level="warn",
                    )
        else:
            # arc v3.2 (eval I2 2026-08-27, after the prompt-prefix rework): the
            # caller dictated or CORRECTED the address ("Ai, atsiprašau — 29
            # namas") and the model either answered "Radau…" for a NONEXISTENT
            # house without calling the tool, or relapsed into a confirm round.
            # Same rule as the offer path: clearly heard street+house AND a
            # digit in THIS utterance (an address part was just said) -> the
            # ENGINE resolves right now; a failed resolve leaves the per-level
            # diagnosis note (namo 39 nerandu, yra 29/31) for the narrator.
            import re as _re

            p = s.identity.profile
            if (
                s.intake.anamnesis_asked  # the address ladder is live (not the opener)
                and p.street.value
                and p.house.value
                and _re.search(r"\d", user_input or "")
            ):
                trace_note(rt.tracer, state, "address_ask", "dictated address; engine resolve")
                if engine_resolve_from_slots(state, rt):
                    state.identity.just_identified = True
                    from .identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
                    state.turn.address_confirm_note = (
                        "- IDENTIFIKUOTA (variklis jau atliko patikrą): "
                        f"adresas {s.identity.customer_address}. Atsakymo pradžioje "
                        "pakartok adresą („Supratau — <adresas>.“) ir tęsk "
                        "pagal žemiau esančią kryptį."
                    )
    elif not s.closing.case_closed:
        from .perceive.detectors import detect_address_correction

        if (
            detect_address_correction(user_input) or mentions_other_street(state, rt, user_input)
        ) and not state.identity.reopen_confirm_utterance:
            # Reference dialogue №3 (2026-09-03): FIRST a confirmation question, only
            # then identification reopens — an STT garble no longer throws the call
            # onto another address without the caller's „taip".
            state.identity.reopen_confirm_utterance = user_input
            state.identity.reopen_confirm_asked = False
            rt.tracer.emit("decision", intent="reopen_confirm", action="pending")


def engine_resolve_from_slots(state, rt) -> bool:
    """Deterministic identification commit from clearly-heard slots: the ENGINE
    calls resolve_address (+ the silent diagnose) itself — no LLM tool-call
    hesitancy, no confirm-round relapse. True when a customer committed."""
    from .walker_flow import ensure_diagnosed

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
    from .dialog_registry import clear_owner as _q_clear_owner

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
            from .dialog_registry import clear_owner as _q_clear_owner

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
        from .dialog_registry import clear_owner as _q_clear_owner

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
                    from .dialog_registry import clear_owner as _q_clear_owner

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
            from .dialog_registry import clear_owner as _q_clear_owner

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
