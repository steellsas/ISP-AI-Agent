"""The turn head — the guard families that read the caller's answer to a pending
dialogue question before anything else acts (§5 rows 4-10).

They only change state: the end-confirm pending, the reopened identity, the committed
identity from an address offer, the captured caller name. The words for the turn come
from the families below them (the scripted ladder, the procedure, the narrator). The
first family that owns the head stops the others for this turn.
"""

from __future__ import annotations

from typing import Any

from ...contract import limits
from ...contract.locale import vocab, vocab_set
from ...dialog_utils import last_agent_question
from ...execute.ticket import begin_ticket_dialogue
from ...perceive.caller import holder_name_matches
from ...perceive.detectors import detect_farewell, detect_ticket_consent
from ...perceive.slots import mentions_other_street, prefill_slots_from_text
from ...trace import trace_note
from .identification import engine_resolve_from_slots, reopen_identification
from .ticket import caller_owed, ticket_capture


def _escalate_step(s: Any) -> Any:
    """The active strategy's escalate step (the fault ticket), or None."""
    if s.resolution.procedure is None:
        return None
    from ...resolution import get_strategy

    strat = get_strategy(s.resolution.procedure.get("verdict"))
    return strat.by_role("escalate") if strat else None


def end_confirm_answer(state: Any, rt: Any, user_input: str) -> bool:
    """The answer to the end-confirm question (§5 row 4). True when it owns the rest of the turn head."""
    s = state
    # (-1) Farewell mid-process is a signal to CLARIFY, never to close (policy
    # 2026-08-03): "viso gero" heard during identification / troubleshooting /
    # before the news gets ONE confirm question; only the confirmation ends the
    # call — through the outcome (registration when a strategy is active).

    if state.dialog.end_confirm_pending and not s.closing.case_closed:
        state.dialog.end_confirm_pending = False
        if state.dialog.end_ticket_offer:
            # F-27: the answer to "register the fault?" — only a yes registers.
            state.dialog.end_ticket_offer = False
            esc = _escalate_step(s)
            if detect_ticket_consent(user_input) == "yes" and esc is not None:
                s.resolution.procedure["escalate_reason"] = "caller_ended_call"
                begin_ticket_dialogue(state, rt, esc)  # contacts, then register+close
                rt.tracer.emit("decision", intent="end_ticket_offer", action="register")
            else:
                s.closing.case_closed = True
                s.closing.closed_reason = "declined"
                rt.tracer.emit("decision", intent="end_ticket_offer", action="close")
            return True
        if detect_farewell(user_input) or detect_ticket_consent(user_input) == "yes":
            if s.resolution.procedure is not None:
                if _escalate_step(s) is not None:
                    # The end is confirmed; registering is its own question (F-27).
                    state.dialog.end_confirm_pending = True
                    state.dialog.end_ticket_offer = True
                    rt.tracer.emit("decision", intent="end_confirmed", action="offer_ticket")
                    return True
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
        return True
    return False


def reopen_confirm_answer(state: Any, rt: Any, user_input: str) -> bool:
    """The answer to the address-change confirm question (§5 row 5). True when it owns the rest of the turn head."""
    s = state
    # A-2 (live 2026-09-07: "Taip taip dėl KITO adreso" was consumed by the
    # walker, and a later side-topic turn burned the question): the SAFETY
    # question's answer is read HERE — in the deterministic turn head, BEFORE
    # the solver/walker. One-owner principle: the last question asked owns
    # the turn. An unclear answer does NOT burn the question — one re-ask,
    # only then written off as "stay with the current address".
    if state.identity.reopen_confirm_utterance is not None and state.identity.reopen_confirm_asked:
        from ...perceive.detectors import DETECTORS
        from ..question import clear as _q_clear
        from .identification import _looks_like_address

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
                # The new address was already heard: it is checked back before it
                # identifies anyone (F-6).
                from .identification import ask_heard_address

                ask_heard_address(state, rt)
            return True
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
        return True
    return False


def cannot_now_shield(state: Any, rt: Any, user_input: str) -> bool:
    """A cannot-do-it-now signal shields the turn for the ladder (§5 row 6). True when it owns the rest of the turn head."""
    s = state
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
        from ...perceive.detectors import detect_cannot_now as _dcn_head
        from ..question import pack_owns_cannot_now

        # P-C: an ability_check/locate_device/homework step's question IS the pack's
        # own cannot-now handling — the shield stands down, the walker routes.
        if _dcn_head(user_input) and not pack_owns_cannot_now(state, rt):
            from ..question import register as _q_register

            _q_register(state, rt, "safety", "cannot_now")  # priority shield this turn
            rt.tracer.emit("decision", intent="cannot_now", action="shield")
    return False


def farewell_mid_process(state: Any, rt: Any, user_input: str) -> bool:
    """A goodbye mid-process asks the end-confirm, never closes (§5 row 7). True when it owns the rest of the turn head."""
    s = state
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
        from ..question import active as _q_act

        _qa = _q_act(state, rt)
        from ...faults import role_of

        _qa_role = (
            role_of((s.resolution.procedure or {}).get("verdict"), _qa.key.removeprefix("step:"))
            if _qa is not None and _qa.key.startswith("step:")
            else None
        )
        if _qa_role != "homework":
            state.dialog.end_confirm_pending = True
            rt.tracer.emit("decision", intent="farewell_mid_process", action="confirm_end")
            return True
    return False


def caller_intro(state: Any, rt: Any, user_input: str) -> bool:
    """The caller's answer to who is calling; the holder-name check (§5 row 8). True when it owns the rest of the turn head."""
    s = state
    # (0) Caller-intro capture: the previous reply asked WHO is calling (the
    # identification ladder's last rung) — record the answer verbatim (for the
    # RECORD, 5d rule) + a keyword relation read. The deferred check result goes
    # out in THIS turn's reply (see the RESULT facts directive).
    if s.identity.customer_id and state.identity.result_pending and not s.identity.caller_name:
        from ...perceive.caller import detect_caller_relation
        from ...perceive.detectors import detect_farewell, is_real_question

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
                from ...perceive.caller import extract_caller_name

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
            from ..question import clear as _q_clear

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
        return True
    return False


def unidentified_address(state: Any, rt: Any, user_input: str) -> bool:
    """The reply to the address offer / a dictated address commits the identity (§5 row 9). True when it owns the rest of the turn head."""
    s = state
    if not s.identity.customer_id:
        from .identification import (
            ask_heard_address,
            forget_heard_numbers,
            heard_confirm_open,
        )

        q = (last_agent_question(state) or "").lower()
        heard_open = heard_confirm_open(state)
        if heard_open or any(m in q for m in vocab("address_offer_question")):
            from ...perceive.detectors import detect_address_confirm

            verdict = detect_address_confirm(user_input)
            if heard_open and verdict != "yes":
                forget_heard_numbers(state, rt)
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
                from ...slots import SlotStatus

                p.street.propose(c["street"], 1.0, SlotStatus.HEARD)
                p.house.propose(str(c.get("house") or ""), 1.0, SlotStatus.HEARD)
                if c.get("apartment"):
                    p.apartment.propose(str(c["apartment"]), 1.0, SlotStatus.HEARD)
                if c.get("city"):
                    p.city.propose(str(c["city"]), 1.0, SlotStatus.HEARD)
                if engine_resolve_from_slots(state, rt):
                    # An explicit yes to "Ar skambinate dėl…" — the address is confirmed.
                    state.identity.address_confirmed = True
                    rt.tracer.emit("decision", intent="address_confirm", action="offer_confirmed")
                    state.identity.just_identified = True
                    from ...identification import ask_caller

                    if ask_caller() and not s.identity.caller_name:
                        state.identity.result_pending = True
                return True
            if verdict == "yes":
                # A-2R-b (2026-09-07): a "taip" to an address confirm WITHOUT
                # a phone candidate (e.g. after reopen, address heard in the
                # slots) — the engine commits from the slots; a block of
                # flats leaves the apartment note.
                p_y = s.identity.profile
                if p_y.street.value and p_y.house.value:
                    rt.tracer.emit("decision", intent="address_confirm", action="heard_confirmed")
                    if engine_resolve_from_slots(state, rt):
                        state.identity.address_confirmed = True
                        state.identity.just_identified = True
                        from ...identification import ask_caller

                        if ask_caller() and not s.identity.caller_name:
                            state.identity.result_pending = True
                    return True
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
                    from ...slots import SlotStatus

                    if s.identity.phone_candidate.get("street"):
                        p.street.propose(
                            s.identity.phone_candidate["street"], 0.9, SlotStatus.HEARD
                        )
                    if not p.city.value and s.identity.phone_candidate.get("city"):
                        p.city.propose(
                            str(s.identity.phone_candidate["city"]), 0.9, SlotStatus.HEARD
                        )
                if p.street.value and p.house.value:
                    if not ask_heard_address(state, rt):
                        state.turn.address_confirm_note = (
                            "- KLIENTAS PASAKĖ KITĄ ADRESĄ, bet jo patikrinti "
                            "nepavyko (žr. HEARD ADDRESS) — patikslink trūkstamą "
                            "dalį arba paprašyk pakartoti."
                        )
                else:
                    state.turn.address_confirm_note = (
                        "- ADRESAS NEPATVIRTINTAS: kliento atsakymas AIŠKIAI "
                        "nepatvirtino pasiūlyto adreso (girdisi neigimas ar "
                        "neaiškumas). NEpatvirtink pasiūlyto adreso. "
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
                if ask_heard_address(state, rt):
                    return True
        return True
    return False


def address_correction(state: Any, rt: Any, user_input: str) -> bool:
    """An identified caller names another address -> the confirm question (§5 row 10). True when it owns the rest of the turn head."""
    s = state
    if s.identity.customer_id and not s.closing.case_closed:
        from ...perceive.detectors import detect_address_correction

        if (
            detect_address_correction(user_input) or mentions_other_street(state, rt, user_input)
        ) and not state.identity.reopen_confirm_utterance:
            # Reference dialogue №3 (2026-09-03): FIRST a confirmation question, only
            # then identification reopens — an STT garble no longer throws the call
            # onto another address without the caller's „taip".
            state.identity.reopen_confirm_utterance = user_input
            state.identity.reopen_confirm_asked = False
            rt.tracer.emit("decision", intent="reopen_confirm", action="pending")
    return False


# The head families in §5 order.
GROUPS = (
    end_confirm_answer,
    reopen_confirm_answer,
    cannot_now_shield,
    farewell_mid_process,
    caller_intro,
    unidentified_address,
    address_correction,
)


def head_rule(group):
    """A policy rule for one head family: it runs on a caller turn nobody owns yet and
    never plans the turn itself."""

    def rule(state: Any, rt: Any) -> None:
        user_input = state.turn.user_input
        if not user_input or state.turn.head_owner:
            return None
        if state.ticket.stage in ("phone", "hours") and not caller_owed(state):
            return None
        if group(state, rt, user_input):
            state.turn.head_owner = group.__name__
        return None

    rule.__name__ = group.__name__
    return rule


def turn_head(state: Any, rt: Any, user_input: str) -> None:
    """The whole head in one call: the contact-dialogue capture, or the head families
    in order until one owns the turn."""
    if not user_input:
        return
    if state.ticket.stage in ("phone", "hours") and not caller_owed(state):
        ticket_capture(state, rt, user_input)
        return
    for group in GROUPS:
        if group(state, rt, user_input):
            return
