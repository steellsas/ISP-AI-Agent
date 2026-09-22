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
    from ...execute.ticket import begin_ticket_dialogue
    from .identification import _account_code_rung, _address_move, _problem_gate_reply
    from .ticket import ticket_question_turn

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
        from ..question import register as _q_register

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
        from ..question import register as _q_register

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
        from ..question import clear as _q_clear
        from ..question import register as _q_register

        state.dialog.cannot_now_state = None
        _q_clear(state, rt, "cannot_now_clarify")
        low_cl = user_input.lower()
        # N2b (live 2026-09-09): "Aš Jums perskambinsiu" IN the clarify answer
        # is the whole decision — close warm right here, no offer round.
        if any(m in low_cl for m in vocab("will_call_back")):
            state.dialog.cannot_now_done = True
            rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return _plan(
                "dialog.cannot_now_callback",
                phrase("identification.callback_goodbye"),
                action=Action(type="close", name="callback"),
            )
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
        from ..question import clear as _q_clear

        state.dialog.cannot_now_state = None
        state.dialog.cannot_now_done = True
        _q_clear(state, rt, "cannot_now_offer")
        low_cn = user_input.lower()
        if any(m in low_cn for m in (*vocab("will_call_back"), *vocab("later_words"))):
            rt.tracer.emit("decision", intent="cannot_now", action="callback_close")
            return _plan(
                "dialog.cannot_now_callback",
                phrase("identification.callback_goodbye"),
                action=Action(type="close", name="callback"),
            )
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
        from ...perceive.detectors import detect_cannot_now as _dcn
        from ..question import pack_owns_cannot_now as _pack_cn

        if _dcn(user_input) and not _pack_cn(state, rt):
            from ..question import register as _q_register

            state.dialog.cannot_now_state = "asked"
            _q_register(state, rt, "safety", "cannot_now_clarify")
            rt.tracer.emit("decision", intent="cannot_now", action="clarify_ask")
            return _words("dialog.cannot_now_clarify", phrase("identification.cannot_now_clarify"))

    # Ticket-confirmation dialogue: contacts before every registration. An
    # off-script question falls to the ticket node's LLM (facts carry the
    # pending stage question to re-ask); the mechanical turns stay scripted.
    from .ticket import caller_owed

    if state.ticket.stage in ("phone", "hours") and not caller_owed(state):
        # The ticket intro is this call's result: nothing is left pending.
        state.identity.result_pending = False
        return _words(*ticket_question_turn(state, rt))
    if state.ticket.stage == "done":
        return _plan("ticket.register", None, action=Action(type="register_ticket"))
    if state.ticket.stage == "cancelled":
        state.ticket.stage = None
        state.ticket.context = None
        return _plan(
            "ticket.cancelled",
            phrase("ticket.declined") + phrase("identification.goodbye"),
            action=Action(type="close", name="declined", args={"complete": True}),
        )
    # Side-topic FRAME (3rd consecutive deviation): the LLM answered twice
    # and the caller keeps drifting — the return is scripted now. With a
    # CONFIRMED hypothesis the frame is the solve-together-or-technician
    # choice (Andrius 2026-08-07: maximise solving by phone).
    if state.turn.side_topic_active and state.dialog.side_topic_streak >= limits.get(
        "side_topic_streak_max"
    ):
        state.dialog.side_topic_streak = 0
        # A settled fault means the frame is the solve-together-or-technician choice; before
        # that, bring them back to the question (wave 3: "settled" is the Case's fault).
        if state.case.fault is not None:
            return _words(
                "side_topic.frame_solve_or_ticket", phrase("identification.solve_or_ticket")
            )
        return _words(
            "side_topic.frame_back_to_issue",
            phrase("identification.back_to_issue", anchor=anchor_text(state, rt)),
        )
    # Ledger conflict clarify (ONE question, engine-composed): "sakėte X,
    # dabar Y — kaip yra iš tiesų?" — the next answer settles the fact.
    # A telemetry recheck that names another cause is no longer a "belief change": the
    # facts changed, and the Case re-judges its candidates over them (wave 3). What stays is
    # the CALLER contradicting what they said before — that is still one question.
    from .. import hypothesis

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
        if state.dialog.end_ticket_offer:
            return _words("dialog.end_offer_ticket", phrase("identification.end_offer_ticket"))
        return _words("dialog.confirm_end", phrase("identification.confirm_end"))
    # Uncorroborated bare "ne" tried to route the walker into ESCALATE — ask
    # the solve-or-register choice instead of crossing the one-way door
    # (2026-08-11). The next turn routes normally: a repeated no escalates.
    if state.resolution.escalate_clarify_due:
        state.resolution.escalate_clarify_due = False
        return _words("diagnosis.escalate_clarify", phrase("identification.escalate_clarify"))
    # A bare "ne" to the question the Case has out: say what the "ne" could mean instead of
    # acting on it (wave 3 — the wording is the card's `needs.<fact>.clarify`).
    from ...case import clarify_for
    from ...perceive.detectors import is_bare_negation

    open_fact = state.case.awaiting
    if open_fact and is_bare_negation(user_input):
        clarify = clarify_for(state.case.fault, open_fact)
        if clarify:
            return _words("diagnosis.negation_clarify", clarify)
    # A disputed debt is offered to the responsible person, never explained (D-11) —
    # „Kaip tai skola?" is an answer to our news, not an off-script question.
    if s.identity.customer_id and not state.ticket.request_type and not s.closing.case_closed:
        from .requests import debt_offer_turn

        offer = debt_offer_turn(state, rt, user_input)
        if offer == "ask":
            return _words("inform.debt_offer", phrase("identification.debt_dispute_offer"))
        if offer == "start":
            return _words(*ticket_question_turn(state, rt))
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
        if s.intake.problem_type and not s.intake.anamnesis_asked and not has_addr:
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
    from ...inform import is_news as _is_news

    if (
        # Only a NEWS call wraps up like this. A fault is worked on: the Case decides those
        # turns, and this guard used to be the walker's pointer (`resolution.procedure`) —
        # when it went away, every fault call wrapped up after the first reaction and closed
        # with the caller's internet still down (full eval: nine scenarios).
        _is_news((s.diagnosis.verdicts.get("network") or {}).get("reason"))
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
        close_reason = "outage" if s.diagnosis.outage_reported else "inform"
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
        rt.tracer.emit("decision", intent="wrap_up", action="close", to=close_reason)
        return _plan(
            "inform.wrap_close",
            phrase("identification.goodbye"),
            action=Action(type="close", name=close_reason, args={"complete": True}),
        )
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
            if not s.ticket.request_type:  # a request is registered, not checked
                parts.append(phrase("identification.checking_note"))
        state.identity.just_identified = False
        from ..question import register as _q_register

        _q_register(state, rt, "ident", "caller_name")
        parts.append(caller_question())
        return _words("identification.caller_name", " ".join(p for p in parts if p))
    # The caller introduced themselves — deliver the deferred result. INFORM
    # verdicts are fully mechanical; a strategy result (finding + step question)
    # stays with the LLM (returns None; the REZULTATO facts directive drives it).
    d = s.diagnosis.verdicts.get("network") or {}
    reason = d.get("reason")
    # A fault is the CASE's to work on; only news is delivered here. This used to be decided
    # by the walker's pointer (`resolution.procedure`), and when that went away every fault
    # was announced as news and the call wrapped up (full eval: nine scenarios closed as
    # "open" with the caller's internet still down).
    from ...inform import is_news

    if reason and not is_news(reason):
        return _plan("identification.result_to_procedure", None, directive=True)
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
    # Outage news carries the ETA the held check found (released for this customer only).
    if verdict_flag(reason, "inform") == "outage" and (s.identity.held_outage or {}).get("eta"):
        bits.append(phrase("identification.outage_eta", eta=s.identity.held_outage["eta"]))
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
    state = _STATE["state"]
    owner = _owner(state, rule)
    # The stage names the node the reply is traced under (and the narrator's snippet
    # for a directive): the engine's own words are an identification- or a
    # diagnosis-stage reply.
    stage = {"ticket": "ticket", "closing": "closing", "side_topic": "side_topic"}.get(
        owner, "diagnosis" if state.identity.customer_id else "intake"
    )
    if directive:
        say = Say(kind="directive", stage=stage)
    else:
        say = Say(kind="phrase", text=words, stage=stage)
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


def scripted_layer(state: Any, rt: Any) -> TurnPlan | None:
    """The engine-composed words of a stage turn, in their precedence order (§5 rows
    18, 5-15, 19): the stuck backstop, the scripted reply families, the wait
    acknowledgement. None = the narrator words the stage.

    Wave 1: this ran inside the NARRATOR (execute/say.scripted_exit), which meant the
    narrator planned, closed calls and registered tickets. It is a decide step now —
    after the procedure moved, so the words match the new position."""
    from .dialog import scripted_wait_ack, stuck_backstop

    _STATE["state"] = state
    backstop = stuck_backstop(state)
    if backstop is not None:
        return _backstop_plan(state, rt, backstop)
    plan = plan_reply(state, rt, state.dialog.last_heard)
    if plan is not None:
        return plan
    wait = scripted_wait_ack(state, rt)
    if wait is not None:
        return _plan("dialog.wait_ack", wait)
    return None


def _backstop_plan(state: Any, rt: Any, backstop: tuple[str, bool]) -> TurnPlan:
    """The stuck ladder (3 -> offer the account code, 4 -> close). Its close keeps the
    registration an identified caller was promised and hangs up on the goodbye (F-5)."""
    text, should_close = backstop
    action = Action(type="none")
    if should_close:
        action = Action(type="close", name="stuck", args={"complete": True})
    else:
        state.dialog.stuck_count += 1  # advance the ladder for the next turn
    rt.tracer.emit("stuck", count=state.dialog.stuck_count, repeated=False)
    return _plan("dialog.stuck_backstop", text, action=action)
