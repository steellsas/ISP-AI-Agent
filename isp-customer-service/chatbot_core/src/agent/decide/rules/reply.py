"""The scripted reply layer — the engine-composed words of a turn, in their precedence
order: the callback goodbye, the holder-name clarify, the address info, the
address-change confirm, the cannot-now ladder, the contact dialogue, the side-topic
frame, the evidence conflict clarify, the end-confirm, the escalate clarify, the bare
"ne" clarify, the identification ladder, the inform wrap-up, the caller-name question
and the inform news (§5 rows 5-15, the words of the families whose state the turn
head and the procedure set).

The narrator's turn calls it after the procedure has moved (the node calls the rule);
a phrase plan is spoken as it is, a directive plan leaves the words to the LLM.
"""

from __future__ import annotations

from typing import Any

from ...contract import limits
from ...contract.locale import phrase_or, vocab
from ...faults import verdict_flag
from ..plan import Action, Say, TurnPlan


def reply_plan(state: Any, rt: Any, user_input: str | None) -> TurnPlan | None:
    """Deterministic identification-ladder replies (2026-07-31, IDENTIFICATION
    ONLY): the mechanical turns are COMPOSED by the engine from the phrases in
    identification.yaml — the LLM repeatedly reordered or skipped them (promised
    a check without the result, relapsed into confirm rounds, skipped the caller
    question, captured 'Taip.' as a name). An off-script caller turn (a question)
    returns None so the LLM answers it; the ladder resumes next turn. Solving and
    free dialogue never come here."""
    from ...dialog_utils import anchor_text
    from ...evidence_drive import evidence_question_open, negation_clarify_reply
    from ...identification_flow import _account_code_rung, _address_move, _problem_gate_reply
    from ...ticket_flow import begin_ticket_dialogue, ticket_question_turn

    s = state
    # P-C (2026-09-08): the walker's 'callback' terminal just closed the case
    # (homework agreed) — the goodbye is scripted, warm and deterministic.
    if state.closing.callback_goodbye_due:
        state.closing.callback_goodbye_due = False
        from ...contract.locale import phrase as _cb_phrase

        return _words("dialog.callback_goodbye", _cb_phrase("identification.callback_goodbye"))
    if s.closing.case_closed:
        return _plan("closing.closed_this_turn", None, directive=True)
    from ...contract.locale import phrase
    from ...identification import caller_question
    from ...perceive.detectors import is_real_question

    # Address CHANGE confirmation (reference dialogue №3, Andrius 2026-09-03): a
    # caller's mention of another address after identification NO longer switches
    # at once — first one confirmation question; „taip" (or a clear new address)
    # reopens identification, any other answer — we stay with the current one.
    # №4 (reference dialogue 2026-09-03): the caller claims to be the holder under
    # another name — a SCRIPTED clarification (live, the narrator overrode the note
    # and confirmed „Jūs, Petrai, esate savininkas"; the privacy rule is too
    # important to improvise). The DB name is NOT in the phrase; the answer next
    # turn updates the relation (prefill).
    if state.identity.holder_clarify_open and not state.identity.holder_clarify_asked:
        state.identity.holder_clarify_asked = True
        from ...dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "holder_clarify")
        rt.tracer.emit("decision", intent="holder_name", action="clarify_ask")
        return _words(
            "identification.holder_clarify", phrase("identification.holder_mismatch_clarify")
        )
    # A-2b (Andrius 2026-09-07, live: "negaliu pasakyti, dėl kokio adreso"):
    # the caller ASKS which address the call is about — the CONFIRMED address
    # is not a secret; on the contrary, this is how the caller catches our
    # mistake. Deterministic scripted answer, never the LLM's whim; the
    # phrase itself invites a correction.
    if (
        user_input
        and any(w in user_input.lower() for w in vocab("address_topic_words"))
        and any(k in user_input.lower() for k in vocab("which_words"))
        and is_real_question(user_input)
    ):
        if s.identity.customer_id and s.identity.customer_address:
            state.identity.reopen_reask_due = False  # the info answer replaces the re-ask
            rt.tracer.emit("decision", intent="address_info", action="disclose")
            return _words(
                "identification.address_info",
                phrase("identification.current_address_info", address=s.identity.customer_address),
            )
        if not s.identity.customer_id:
            # A-2R-b follow-up (live 2026-09-07): the question arrived MID
            # identification (after reopen) — say WHAT we are clarifying:
            # the heard address (with the "dėl šio adreso" confirm core the
            # guard keys off), or that we have no address yet.
            p = s.identity.profile
            if p.street.value:
                adr = f"{p.street.value} {p.house.value or ''}".strip()
                rt.tracer.emit("decision", intent="address_info", action="progress")
                return _words(
                    "identification.address_heard",
                    phrase("identification.ident_address_heard", address=adr),
                )
            rt.tracer.emit("decision", intent="address_info", action="none_yet")
            return _words(
                "identification.address_none", phrase("identification.ident_address_none")
            )
    # This layer ASKS the address-change question; the ANSWER is read by
    # pre_turn_guards (the deterministic turn head) so the solver/walker
    # cannot consume it (live A-2 defect). Only the ask/re-ask side is here.
    pending_reopen = state.identity.reopen_confirm_utterance
    if pending_reopen is not None:
        from ...dialog_registry import register as _q_register

        adresas = s.identity.customer_address or phrase("identification.current_address_unknown")
        if not state.identity.reopen_confirm_asked:
            state.identity.reopen_confirm_asked = True
            state.identity.reopen_confirm_asks = 1
            _q_register(state, rt, "safety", "reopen_confirm", address=adresas)
            rt.tracer.emit("decision", intent="reopen_confirm", action="ask")
            return _words(
                "identification.reopen_confirm_ask",
                phrase("identification.reopen_confirm", address=adresas),
            )
        if state.identity.reopen_reask_due:
            state.identity.reopen_reask_due = False
            state.identity.reopen_confirm_asks = state.identity.reopen_confirm_asks + 1
            _q_register(state, rt, "safety", "reopen_confirm", address=adresas)
            return _words(
                "identification.reopen_confirm_reask",
                phrase("identification.repeat_ack")
                + phrase("identification.reopen_confirm", address=adresas),
            )
        return _plan(
            "identification.reopen_confirm_pending", None, directive=True
        )  # the guards already read the answer; the narrator continues

    # A-wave P1 (Andrius 2026-09-04, live #6: „Ne patogu" ignored): the
    # cannot-do-it-NOW mini-ladder in the solving phase — STOP, find out WHAT is
    # inconvenient, then offer a way (registration / call back / continue).
    cn_state = state.dialog.cannot_now_state
    if cn_state == "asked" and user_input:
        from ...dialog_registry import clear as _q_clear
        from ...dialog_registry import register as _q_register

        state.dialog.cannot_now_state = None
        _q_clear(state, rt, "cannot_now_clarify")
        low_cl = user_input.lower()
        # N2b (live 2026-09-09): "Aš Jums perskambinsiu" IN the clarify answer
        # is the whole decision — close warm right here, no offer round.
        if any(m in low_cl for m in vocab("will_call_back")):
            state.dialog.cannot_now_done = True
            s.closing.case_closed = True
            s.closing.closed_reason = "callback"
            rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return _words("dialog.cannot_now_callback", phrase("identification.callback_goodbye"))
        # N2 (live 2026-09-09: "Negaliu, nes esu nenuose" got RESUME and the
        # walker pushed another check): the caller was just asked "ar negalite
        # dabar patikrinti?" — a rambling answer about being away IS a yes.
        # RESUME only on a clear back-to-solving signal; everything else
        # offers the way out.
        resumed = any(m in low_cl for m in vocab("resume_solving")) and not any(
            m in low_cl for m in vocab("resume_solving_denied")
        )
        if not resumed:
            state.dialog.cannot_now_state = "offered"
            _q_register(state, rt, "safety", "cannot_now_offer")
            rt.tracer.emit("decision", intent="cannot_now", action="offer")
            return _words("dialog.cannot_now_offer", phrase("identification.cannot_now_offer"))
        rt.tracer.emit("decision", intent="cannot_now", action="resume")
        return _plan(
            "dialog.cannot_now_resume", None, directive=True
        )  # explained otherwise — continue the path (content already ingested)
    if cn_state == "offered" and user_input:
        from ...dialog_registry import clear as _q_clear

        state.dialog.cannot_now_state = None
        state.dialog.cannot_now_done = True
        _q_clear(state, rt, "cannot_now_offer")
        low_cn = user_input.lower()
        if any(m in low_cn for m in (*vocab("will_call_back"), *vocab("later_words"))):
            s.closing.case_closed = True
            s.closing.closed_reason = "callback"
            rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return _words("dialog.cannot_now_callback", phrase("identification.callback_goodbye"))
        from ...perceive.detectors import DETECTORS as _DET_CN2
        from ...perceive.detectors import detect_refuse_or_ticket

        if (
            detect_refuse_or_ticket(user_input) == "demand"
            or _DET_CN2["yes_no"](user_input) == "yes"
            or any(m in low_cn for m in vocab("ticket_words"))
        ):
            from ...faults import step_by_role

            # P-E: the ticket intro must speak the honest state — the caller
            # could not act NOW; nothing was performed.
            if s.resolution.procedure is not None:
                s.resolution.procedure["escalate_reason"] = "cannot_now"
            rt.tracer.emit("decision", intent="cannot_now", action="ticket")
            begin_ticket_dialogue(state, rt, step_by_role("unclear_fault", "escalate"))
            return _plan(
                "dialog.cannot_now_ticket", None, directive=True
            )  # ticket dialogue intro — the next step
        return _plan("dialog.cannot_now_declined", None, directive=True)
    if (
        cn_state is None
        and not state.dialog.cannot_now_done
        and s.resolution.procedure
        and s.identity.customer_id
        and not state.ticket.stage
        and user_input
    ):
        from ...dialog_registry import pack_owns_cannot_now as _pack_cn
        from ...perceive.detectors import detect_cannot_now as _dcn

        if _dcn(user_input) and not _pack_cn(state, rt):
            from ...dialog_registry import register as _q_register

            state.dialog.cannot_now_state = "asked"
            _q_register(state, rt, "safety", "cannot_now_clarify")
            rt.tracer.emit("decision", intent="cannot_now", action="clarify_ask")
            return _words("dialog.cannot_now_clarify", phrase("identification.cannot_now_clarify"))

    # Ticket-confirmation dialogue: contacts before every registration. An
    # off-script question falls to the ticket node's LLM (facts carry the
    # pending stage question to re-ask); the mechanical turns stay scripted.
    if state.ticket.stage in ("phone", "hours"):
        return _words(*ticket_question_turn(state, rt))
    if state.ticket.stage == "done":
        return _plan("ticket.register", None, action=Action(type="register_ticket"))
    if state.ticket.stage == "cancelled":
        state.ticket.stage = None
        state.ticket.context = None
        s.closing.case_closed = True
        s.closing.closed_reason = "declined"
        s.closing.is_complete = True
        return _words(
            "ticket.cancelled", phrase("ticket.declined") + phrase("identification.goodbye")
        )
    # Side-topic FRAME (3rd consecutive deviation): the LLM answered twice
    # and the caller keeps drifting — the return is scripted now. With a
    # CONFIRMED hypothesis the frame is the solve-together-or-technician
    # choice (Andrius 2026-08-07: maximise solving by phone).
    if state.turn.side_topic_active and state.dialog.side_topic_streak >= limits.get(
        "side_topic_streak_max"
    ):
        state.dialog.side_topic_streak = 0
        from ...evidence import hypothesis_status, spec_for

        spec = spec_for((s.resolution.procedure or {}).get("verdict"))
        if spec is not None and hypothesis_status(s.diagnosis.evidence, spec) == "confirmed":
            return _words(
                "side_topic.frame_solve_or_ticket", phrase("identification.solve_or_ticket")
            )
        return _words(
            "side_topic.frame_back_to_issue",
            phrase("identification.back_to_issue", anchor=anchor_text(state, rt)),
        )
    # Ledger conflict clarify (ONE question, engine-composed): "sakėte X,
    # dabar Y — kaip yra iš tiesų?" — the next answer settles the fact.
    from .. import hypothesis

    change = hypothesis.ask(state, rt, "verdict")
    if change is not None:
        return _words("diagnosis.hypothesis_confirm", hypothesis.change_question(change))
    conflict = hypothesis.ask(state, rt, "conflict")
    if conflict is not None:
        from ...evidence import gloss_label, gloss_value

        key, old, new = conflict.fact_key, conflict.before_value, conflict.now_value
        return _words(
            "diagnosis.evidence_conflict_clarify",
            phrase(
                "identification.evidence_conflict",
                topic=gloss_label(key),
                a=gloss_value(old, key),
                b=gloss_value(new, key),
            ),
        )
    # Farewell-mid-process clarify (any stage): ONE deterministic confirm question.
    if state.dialog.end_confirm_pending:
        return _words("dialog.confirm_end", phrase("identification.confirm_end"))
    # Uncorroborated bare "ne" tried to route the walker into ESCALATE — ask
    # the solve-or-register choice instead of crossing the one-way door
    # (2026-08-11). The next turn routes normally: a repeated no escalates.
    if state.resolution.escalate_clarify_due:
        state.resolution.escalate_clarify_due = False
        return _words("diagnosis.escalate_clarify", phrase("identification.escalate_clarify"))
    # Bare "ne" while the evidence drive's question is open, on the WALKER
    # path (farewell/refuse-shaped turns land here; the drive words its own
    # clarify): say what the "ne" could mean instead of acting on it.
    from ...perceive.detectors import is_bare_negation

    open_key = evidence_question_open(state, rt)
    if open_key and is_bare_negation(user_input):
        clarify = negation_clarify_reply(state, rt, open_key)
        if clarify:
            return _words("diagnosis.negation_clarify", clarify)
    if (
        user_input
        and is_real_question(user_input)
        and (s.intake.problem_type or s.identity.customer_id)
        # A code-phase question („o kur jį rasti?") goes to the rung — the retry
        # phrase with a HINT where to look IS the answer (reference dialogue №2).
        and not state.identity.account_code_mode
        # NLU wave block 4: "V KAIP Vilnius" is the spelling answer, not a
        # question — the rung's spell reader owns the armed turn; two "kaip"
        # pairs are spelling-shaped even without the mode (client-initiated).
        and not state.identity.spell_mode
        and user_input.lower().count(" kaip ") < 2
    ):
        return _plan(
            "dialog.question_passthrough", None, directive=True
        )  # off-script — the LLM answers; guards kept the ladder state
        # (pre-problem questions fall through to the problem GATE below)
    # INTAKE (not yet identified): the anamnesis question and the address
    # offer/ask are mechanical too — the LLM repeated the anamnesis and slid the
    # whole ladder by a turn (observed in eval).
    if not s.identity.customer_id:
        # Small talk BEFORE any problem is stated gets a scripted greeting-back
        # — never the LLM (which jumped to the address offer on "Labadiena!",
        # duplicating the ladder's own later offer; live 2026-08-06).
        if not s.intake.problem_type and user_input:
            from ...perceive.detectors import is_greeting

            if is_greeting(user_input):
                return _words("identification.ask_problem", phrase("identification.ask_problem"))
            # Live 2026-08-21: a garbled opener ("Atsikai, daro") fell to the
            # LLM, which offered the address before any problem was stated.
            # 2026-09-02: the gate grew the L2 classification ladder — see
            # _problem_gate_reply. A commit there (LLM guess accepted) falls
            # THROUGH to the intake ladder the same turn: reaching a problem
            # never ends the call, only never reaching one does.
            _has_addr0 = bool(s.identity.profile.street.value or s.identity.profile.house.value)
            if not _has_addr0:
                reply = _problem_gate_reply(state, rt, s, user_input)
                if s.intake.problem_type is None:
                    return _words("identification.problem_gate", reply)
                # gate commit — continue to anamnesis/address this turn
        p = s.identity.profile
        has_addr = bool(p.street.value or p.house.value)
        # №2/№5 (reference dialogue 2026-09-03): the subscriber-code rung — when
        # the address does not clear up, the method changes; the code-waiting phase
        # reads the answer. The phone-candidate offer flow is not counted (it has
        # its own confirmation mechanics).
        if state.identity.account_code_mode or not s.identity.phone_candidate:
            handled, reply = _account_code_rung(state, rt, s, user_input)
            if handled:
                return _words("identification.account_code", reply)
        if (
            s.intake.problem_type
            and not s.intake.anamnesis_asked
            and not s.identity.preflight_outage
            and not has_addr
        ):
            # DIALOGO_ETALONAS #2 (Andrius 2026-09-01/03): the OPENING
            # anamnesis QUESTION is gone — capture-first keeps whatever the
            # caller already said ("vakar dingo, po audros"), and the targeted
            # anamnesis lives in the PACKS, asked with telemetry context only
            # when the verdict needs it. A blind "kada dingo? gal po audros?"
            # wasted a turn on every fast-path call (live 2026-09-03: the
            # answer "kaimynai remontą darys" fed nothing — the verdict was a
            # billing block). anamnesis_asked stays as the ladder-live marker
            # (the deterministic address-resolve gate keys off it).
            s.intake.anamnesis_asked = True
            if user_input:
                from ...perceive.nlu import extract_anamnesis

                read = extract_anamnesis(user_input)
                if read.get("when") not in (None, "unknown") or read.get("trigger"):
                    s.intake.anamnesis_raw = user_input.strip()[:200]
                    s.intake.anamnesis_when = read.get("when")
                    s.intake.anamnesis_trigger = read.get("trigger")
                    rt.tracer.emit(
                        "anamnesis",
                        text=s.intake.anamnesis_raw,
                        when=s.intake.anamnesis_when,
                        trigger=s.intake.anamnesis_trigger,
                        from_opening=True,
                    )
                    state.intake.opening_heard_note = True
            return _words("identification.address_move", _address_move(state, rt, s))
        return None
    # WRAP-UP after the news (inform mode): the business is DONE — any further
    # turn that is not a question/wants-more wraps up DETERMINISTICALLY. Garbled
    # goodbyes ("Nusigaro" = "viso gero") had the model loop "nesupratau,
    # pakartokite" after a delivered debt notice (observed live: the caller could
    # not end the call).
    if (
        s.resolution.procedure is None
        and (state.diagnosis.news_delivered or s.diagnosis.outage_reported)
        and not state.identity.result_pending
    ):
        low = (user_input or "").lower()
        wants_more = is_real_question(user_input) or any(
            m in low for m in vocab("inform_wants_more")
        )
        if wants_more:
            return _plan(
                "inform.wants_more", None, directive=True
            )  # a question / wants something — the LLM handles it
        # Closing wave block 2 (live 2026-09-08: "Vilma" — the caller's NAME —
        # got a deaf goodbye): a content-bearing turn is NOT a goodbye. Up to
        # two such turns get an LLM reaction (with a directive to react and
        # re-offer the close); the cap keeps garbled goodbyes ("Nusigaro")
        # from looping the wrap-up forever.
        from ...perceive.detectors import detect_farewell as _df
        from ...perceive.detectors import is_backchannel as _bc

        content = bool(user_input) and not _df(user_input) and not _bc(user_input)
        n = state.closing.wrap_content_turns
        if content and n < limits.get("wrap_content_turns_max"):
            state.closing.wrap_content_turns = n + 1
            state.closing.wrap_react_note = True
            rt.tracer.emit("decision", intent="wrap_up", action="react", turns=n + 1)
            return _plan(
                "inform.wrap_react", None, directive=True
            )  # the narrator reacts to WHAT was said, then re-offers
        s.closing.case_closed = True
        s.closing.closed_reason = "outage" if s.diagnosis.outage_reported else "inform"
        s.closing.is_complete = True
        # clarity requirements (declared in inform.yaml): the inform template
        # spoke all its elements before this close — trace it for the audits.
        from ...inform import clarity_declaration

        _reason = (s.diagnosis.verdicts.get("network") or {}).get("reason")
        _required = clarity_declaration(_reason)
        if _required:
            rt.tracer.emit(
                "clarity",
                reason=_reason,
                required=_required,
                told=state.diagnosis.news_delivered,
            )
        rt.tracer.emit("decision", intent="wrap_up", action="close", to=s.closing.closed_reason)
        return _words("inform.wrap_close", phrase("identification.goodbye"))
    if not state.identity.result_pending:
        return None
    if not s.identity.caller_name:
        # The caller-intro question turn (with the address echo on a fresh
        # commit) + the CHECKING cue — the engine resolves/diagnoses silently
        # here, and without the cue the caller thinks nothing started
        # (live 2026-08-07: "nepasako, kad patikrins").
        parts = []
        if state.identity.just_identified and s.identity.customer_address:
            parts.append(phrase("identification.echo_address", address=s.identity.customer_address))
            parts.append(phrase("identification.checking_note"))
        state.identity.just_identified = False
        from ...dialog_registry import register as _q_register

        _q_register(state, rt, "ident", "caller_name")
        parts.append(caller_question())
        return _words("identification.caller_name", " ".join(p for p in parts if p))
    # The caller introduced themselves — deliver the deferred result. INFORM
    # verdicts are fully mechanical; a strategy result (finding + step question)
    # stays with the LLM (returns None; the REZULTATO facts directive drives it).
    if s.resolution.procedure is not None:
        return _plan("identification.result_to_procedure", None, directive=True)

    d = s.diagnosis.verdicts.get("network") or {}
    reason = d.get("reason")
    # Closing wave (2026-09-08): the inform SPEECH lives in
    # knowledge/inform.yaml — the template carries the details (debt
    # amount, months, last payment; outage place and ETA) and its own
    # "Patikrinau…" opening, so check_result/billing_extra are not repeated.
    from ...inform import inform_text

    inf = inform_text(state, rt, reason)
    if inf:
        # B3 inform verdicts (node/switch fault, Andrius 2026-09-11): the
        # template PROMISES "meistrai jau užregistruoti" — the engine makes it
        # true by registering the ticket itself before the words go out.
        inform_action = (
            Action(type="register_ticket", name="auto")
            if verdict_flag(reason, "auto_ticket") and not s.ticket.ticket_id
            else Action(type="none")
        )
        state.identity.result_pending = False
        state.diagnosis.news_delivered = True
        rt.tracer.emit("decision", intent="inform", action="template", reason=reason)
        return _plan(
            "inform.template",
            " ".join(
                [phrase("identification.thanks"), inf, phrase("identification.anything_else")]
            ),
            action=inform_action,
        )
    zinia = phrase_or(f"verdict.{reason}.gloss", reason or "")
    if not zinia:
        return None
    zinia = zinia[0].upper() + zinia[1:]  # sentence-cased after "…iki jūsų buto."
    bits = [
        phrase("identification.thanks"),
        phrase("identification.check_result", news=zinia + "."),
    ]
    if verdict_flag(reason, "inform") == "debt":
        bits.append(phrase("identification.billing_extra"))
    # Outage news carries the ETA when the preflight knows it.
    if verdict_flag(reason, "inform") == "outage" and (s.identity.preflight_outage or {}).get(
        "eta"
    ):
        bits.append(phrase("identification.outage_eta", eta=s.identity.preflight_outage["eta"]))
    bits.append(phrase("identification.anything_else"))
    state.identity.result_pending = False
    state.diagnosis.news_delivered = True
    return _words("inform.verdict_gloss", " ".join(b for b in bits if b))


def _owner(state: Any, rule: str) -> str:
    family = rule.split(".", 1)[0]
    if family in ("identification", "inform", "side_topic", "diagnosis", "ticket", "closing"):
        return family
    if state.closing.case_closed:
        return "closing"
    return "diagnosis" if state.identity.customer_id else "identification"


_STATE: dict[str, Any] = {}


def _plan(
    rule: str, words: str | None, action: Action | None = None, directive: bool = False
) -> TurnPlan:
    owner = _owner(_STATE["state"], rule)
    if directive:
        say = Say(kind="directive")
    else:
        say = Say(kind="phrase", text=words)
    return TurnPlan(owner=owner, rule=rule, action=action or Action(type="none"), say=say)


def _words(rule: str, words: str | None) -> TurnPlan:
    """Engine words — or, when the rule composed none, the narrator speaks."""
    return _plan(rule, words, directive=not words)


def scripted_words(state: Any, rt: Any, user_input: str | None) -> str | None:
    """The scripted reply's words for this turn (running its action), or None when the
    narrator speaks — the reply layer as one call."""
    plan = plan_reply(state, rt, user_input)
    if plan is None or plan.say.kind != "phrase":
        return None
    from ...execute.actions import run_action

    action_text = run_action(state, rt, plan)
    return plan.say.text or action_text


def plan_reply(state: Any, rt: Any, user_input: str | None) -> TurnPlan | None:
    _STATE["state"] = state
    return reply_plan(state, rt, user_input)
