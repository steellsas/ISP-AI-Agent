"""The fault path, decided by the Case (wave 3f).

This replaces three drivers with one. Before: the ledger's evidence layer asked, the LLM
solver sometimes spoke, and the walker held a pointer into a pack's steps, with handover
rules between them (review finding N — 263 bailouts in the traces). Now every turn on the
fault path asks the Case one question and carries out its answer:

    learn      a probe (look), a module (do it together) or a question (ask)
    solve      the settled fault's own steps, one per turn
    escalate   a technician, honestly

The plan says WHAT the turn must achieve; the narrator words it (wave 2b skills) and the
gate runs the effects (wave 1b). Nothing here speaks and nothing here touches a tool.
"""

from __future__ import annotations

from typing import Any

from ... import ledger, modules
from ...case import judge, next_move
from ...contract import cards as catalog
from ...contract.locale import maybe_phrase, phrase, vocab
from ..plan import Action, Say, TurnPlan


def plan(state: Any, rt: Any) -> TurnPlan | None:
    """This turn on the fault path."""
    if _identification_owns_the_turn(state):
        # The Case may THINK while the caller is still being identified — the line is read,
        # the candidates narrow, the finding is worked out — but it may not ASK. Andrius
        # (2026-09-30): *„kol neįvyko identifikavimas, neturi painiotis su analize… vardo
        # pasiklausimas ir tikslinimas tai dar identifikavimo dalis."*
        #
        # Live that day: the lights question was planned on the turn the holder clarification
        # owned, was never spoken — and the caller's answer about the CONTRACT was then read
        # as the answer about the LIGHTS.
        facts = ledger.facts_of(state)
        _diagnose_quietly(state, rt, facts)
        return None
    reflect = _reflect_plan(state, rt)
    if reflect is not None:
        return reflect
    facts = ledger.facts_of(state)
    later = _not_now_plan(state, rt, facts)
    if later is not None:
        return later
    if state.case.fault is not None and _ruled_out_now(state, facts):
        # A fact arrived mid-fix that this card itself calls disqualifying. Live 2026-09-28:
        # the caller plugged a computer into the line, `device_registered=foreign` landed —
        # which `router_hung` lists in `rules_out` — and the engine carried on rebooting a
        # router that was no longer the one on the line. `rules_out` was read when the card
        # was CHOSEN and never again.
        rt.tracer.emit("case", move="ruled_out", fault=state.case.fault)
        state.case.fault, state.case.solution, state.case.step = None, None, 0
        state.case.awaiting, state.case.awaiting_probe = None, False
        state.case.guide_step, state.case.guide_said = 0, -1
    if state.case.fault is not None and _caller_is_lost(state, rt):
        # Klientas nebegali sekti žingsnių (kelis ėjimus iš eilės nesusikalbam) — telefoninis
        # sprendimas baigiamas SĄŽININGAI: pasakom, ką padarėm, ir registruojam meistrą. Tai
        # sprendimo kelio darbas, ne identifikacijos kopėčios (7f banga).
        return _escalate(state, rt, state.case.fault)
    if state.case.fault is not None:
        status = _absorb(state, rt, facts)
        # The caller's physical action must reach the line BEFORE anything reads it again,
        # or the verification judges a reboot the database never saw (live probe, S6).
        reflect = _reflect_plan(state, rt)
        if reflect is not None:
            return reflect
        if status == "failed":
            return _escalate(state, rt, state.case.fault)
        if status == "reopen":
            facts = ledger.facts_of(state)  # the verification's own reading is part of them now
        if status == "handed_over":
            return None  # the ticket dialogue owns the rest of the call
        if status == "escalating":
            return _escalate(state, rt, state.case.fault)
        if status == "solved":
            return _resolved(state, rt)
        step = _current(state)
        if step is not None:
            # The facts this turn's words established belong to THIS turn's decision. Live
            # 2026-09-30: the caller said „Nenoriu" to the temporary line, `bridge_agreed=no`
            # was written by `_absorb` — and the step was still chosen against the snapshot
            # taken before they spoke, so the cable instruction went out anyway.
            return _step_plan(state, rt, step, ledger.facts_of(state))
    if _not_a_fault(facts, state) and state.case.fault is None and _told(state):
        # An outage or a suspended service is NOT a fault we diagnose: the inform path owns
        # the turn, and escalating here hijacked it (full eval: four inform scenarios).
        return None
    move = next_move(facts, unavailable=ledger.unavailable(state))
    # A question the caller has been asked twice (the second time in other words) and still
    # not answered is not a question to ask a third time. What happens instead is the CARD's
    # to say: `assume` carries the call forward with the value it names — a hung router is
    # rebooted anyway, because that is its primary fix and a ticket without it would be help
    # we never gave (Andrius, 2026-09-23). Only a fact with no assumption is a dead end.
    while move.kind == "learn" and _asked_enough(state, move):
        explain = _explain_need(state, rt, move)
        if explain is not None:
            return explain  # a critical fact is not dropped silently — they hear why we need it
        assumed = _assume(state, rt, move)
        ledger.record_unavailable(state, rt, move.fact)
        rt.tracer.emit(
            "case",
            move="assume" if assumed else "give_up",
            fact=move.fact,
            why="asked twice, no answer",
        )
        facts = ledger.facts_of(state)
        move = next_move(facts, unavailable=ledger.unavailable(state))
    rt.tracer.emit("case", move=move.kind, fact=move.fact, fault=move.fault, why=move.why)
    if move.kind == "inform":
        # Nothing to diagnose: record what the news IS where the inform path reads it, and
        # let that path speak (its templates and clarity rules live in inform.yaml).
        network = state.diagnosis.verdicts.setdefault("network", {})
        if network.get("reason") != move.fault:
            network["reason"] = move.fault
            rt.tracer.emit("verdict", reason=move.fault, source="card")
        return None
    if move.kind == "learn":
        return _learn(state, rt, move, facts)
    if move.kind == "solve":
        if move.fault in state.case.spent:
            # Its fix already ran and did not work: the honest next step is a technician,
            # not the same instruction again.
            return _escalate(state, rt, move.fault)
        _begin(state, rt, move.fault, facts)
        step = _current(state)
        return _step_plan(state, rt, step, facts) if step else _escalate(state, rt, move.fault)
    return _escalate(state, rt, move.fault)


# Facts that mean someone else owns the turn: there is nothing to diagnose, only news to
# deliver (a registered outage, a suspended service).
NOT_OUR_FAULT = ("area_outage", "service_suspended")


def _told(state: Any) -> bool:
    """Has the news already been named? Until it is, the Case still has to name it (wave 4)."""
    return bool(((state.diagnosis.verdicts or {}).get("network") or {}).get("reason"))


def _not_a_fault(facts: dict[str, str], state: Any | None = None) -> bool:
    if any(facts.get(fact) == "yes" for fact in NOT_OUR_FAULT):
        return True
    if state is None:
        return False
    from ...inform import is_news

    return is_news(((state.diagnosis.verdicts or {}).get("network") or {}).get("reason"))


def _not_now_plan(state: Any, rt: Any, facts: dict[str, str]) -> TurnPlan | None:
    """The caller cannot get to the device right now.

    Nothing about the fault changes — what changes is WHEN. They get the instruction for
    later and are asked whether that suits them; a yes closes the call as a callback, a no
    means they would rather have a technician. Never the other way round: an agent that
    pushes a technician at someone who is simply not at home is not helping (P-C).
    """
    if facts.get("reachable") != "no":
        return None
    agreed = facts.get("later_agreed")
    if agreed == "yes":
        rt.tracer.emit("case", move="callback", fault=state.case.fault)
        return TurnPlan(
            owner="closing",
            rule="case.later_agreed",
            action=Action(type="close", name="callback"),
            say=Say(
                kind="directive",
                goal="thank them warmly, repeat that they call if it does not help, say goodbye",
                stage="closing",
            ),
        )
    if agreed == "no":
        return _escalate(state, rt, state.case.fault)
    if state.case.homework_asks >= 2:
        # They have been told twice and the answer is not readable. Asking again is pressure;
        # the honest end is a warm goodbye with the door open.
        rt.tracer.emit("case", move="callback", fault=state.case.fault, why="homework_untold")
        return TurnPlan(
            owner="closing",
            rule="case.later_assumed",
            action=Action(type="close", name="callback"),
            say=Say(
                kind="directive",
                goal="say warmly that they can call back any time if it does not help, then goodbye",
                stage="closing",
            ),
        )
    from ...contract.schema import ModuleCall

    call = ModuleCall(module="homework", args={"device": _device_type(state)})
    step = modules.plan_step(call, model=_device_model(state))
    state.case.awaiting = "later_agreed"
    state.case.homework_asks += 1
    state.diagnosis.pending_evidence_key = "later_agreed"
    rt.tracer.emit("case", move="homework", fault=state.case.fault)
    return TurnPlan(
        owner="procedure",
        rule="case.homework",
        say=Say(
            kind="directive",
            text=_homework_words(state, call),
            goal=step.goal if step else "agree what they will do when they are back",
            stage="diagnosis",
        ),
        awaiting="later_agreed",
    )


def _homework_words(state: Any, call: Any) -> str | None:
    """The instruction they were about to be given, framed for later.

    The words come from the two places that own them: the equipment catalogue (what to do)
    and the homework module (when, and the promise to call back).
    """
    later = modules.question_of(call, model=_device_model(state))
    doing = None
    for pending in (_current(state), _following(state)):
        # The caller is usually standing at the "can you reach it" question, so the thing
        # they were about to be asked to DO is the step after it.
        planned = modules.plan_step(pending, model=_device_model(state)) if pending else None
        if planned is not None and planned.kind == "instruct" and planned.text:
            doing = planned.text
            break
    if doing and later:
        return f"{doing} {later}"
    return later or doing


# --- learning a fact ------------------------------------------------------------------


def _learn(state: Any, rt: Any, move: Any, facts: dict[str, str]) -> TurnPlan:
    """Look, act together, or ask — whichever the index offered as cheapest."""
    source = move.source
    state.case.awaiting = move.fact
    if source.kind == "probe":
        # The engine looks and decides again in the SAME turn: the caller is not asked to
        # wait for something we can read ourselves.
        return TurnPlan(
            owner="diagnosis",
            rule="case.probe",
            action=Action(type="tool", name=source.tool, args={"customer_id": _cid(state)}),
            say=Say(kind="none"),
            awaiting=move.fact,
            redecide_after_action=True,
        )
    if source.kind == "module":
        call = _call_for(source.module, state)
        return _module_plan(state, rt, call, facts, rule=f"case.learn.{source.module}")
    # The reading layer gives a short answer its meaning from the question that is out
    # ("Tik viename." only means fail_scope=one because that is what we asked).
    state.diagnosis.pending_evidence_key = move.fact
    from ...case import reason_for

    card = catalog.card(state.case.fault or move.fault)
    why = reason_for(move.fact, card)
    goal = f"learn {move.fact} — only the caller can tell us"
    if why:
        # A caller who knows WHY answers better, and follows the instruction that comes next.
        goal = f"{goal}. Say why in half a sentence: {why}"
    asked = state.case.asks.setdefault(move.fact, [])
    if state.dialog.turn_count not in asked:
        asked.append(state.dialog.turn_count)
    words = maybe_phrase(source.ask)
    need = card.needs.get(move.fact) if card and move.fact else None
    if len(asked) > 1 and need is not None and need.again:
        # They answered about something else. The same sentence again is what makes an agent
        # sound like a machine — the card's second wording says it differently, usually with
        # an example of how to check (live 2026-09-23).
        words = maybe_phrase(need.again) or words
        goal = f"{goal}. They did not answer this yet, so ask it DIFFERENTLY and say why it matters"
    return TurnPlan(
        owner="diagnosis",
        rule="case.ask",
        say=Say(kind="directive", text=words, goal=goal, stage="diagnosis"),
        awaiting=move.fact,
    )


def _unchecked_words(state: Any) -> str:
    """What we could not check together, and what we are working with instead.

    The caller hears it before anything is asked of them or registered in their name: an
    assumption said out loud can be corrected, a silent one cannot (Andrius, 2026-09-23).
    """
    from ...facts import gloss

    bits = []
    for fact, value in (state.case.assumed or {}).items():
        said = gloss(fact, value)
        if said:
            bits.append(said)
    for fact in state.case.unavailable or []:
        if fact in (state.case.assumed or {}):
            continue
        card = catalog.card(state.case.fault)
        need = card.needs.get(fact) if card else None
        label = maybe_phrase(need.ask) if need else None
        if label:
            bits.append(label)
    return "; ".join(bits)


def _explain_need(state: Any, rt: Any, move: Any) -> TurnPlan | None:
    """A fact the card calls CRITICAL, asked twice and still not answered.

    Neither a third repeat nor a silent assumption: the caller is told what we need and what
    it changes ("kad galėčiau suprasti, kur problema — kitaip tektų siųsti meistrą"). Once.
    """
    card = catalog.card(state.case.fault or move.fault)
    need = card.needs.get(move.fact) if card and move.fact else None
    if need is None or not need.critical:
        return None
    asked = state.case.asks.setdefault(move.fact, [])
    if len(asked) > _asks_max():
        return None  # already explained; the call moves on without it
    if state.dialog.turn_count not in asked:
        asked.append(state.dialog.turn_count)
    why = maybe_phrase(need.why) or ""
    rt.tracer.emit("case", move="need", fact=move.fact, why="critical")
    return TurnPlan(
        owner="diagnosis",
        rule="case.need",
        say=Say(
            kind="directive",
            goal=(
                "say plainly that without this one thing we cannot tell what is wrong, and "
                "that the only other way is a technician — then ask it once more, warmly"
                + (f". Why it matters: {why}" if why else "")
            ),
            stage="diagnosis",
        ),
        awaiting=move.fact,
    )


def _asks_max() -> int:
    from ...contract import limits

    return int(limits.get("case_fact_asks_max"))


def _assume(state: Any, rt: Any, move: Any) -> bool:
    """Carry the call forward on the card's own assumption, and remember to say it."""
    card = catalog.card(state.case.fault or move.fault)
    need = card.needs.get(move.fact) if card and move.fact else None
    if need is None or not need.assume:
        return False
    return ledger.record_assumed(state, rt, move.fact, need.assume)


def _asked_enough(state: Any, move: Any) -> bool:
    """Has this fact already been asked as often as we may ask?

    Only a QUESTION counts: a probe costs the caller nothing and a module is something we do
    together, so neither wears out. The limit is knowledge (`case_fact_asks_max`).
    """
    if move.source is None or move.source.kind != "ask" or not move.fact:
        return False
    return len(state.case.asks.get(move.fact, [])) >= _asks_max()


def _call_for(module: str, state: Any):
    """A module run to LEARN something: the device is whatever the line shows the caller
    has, so `check_lights` asks about the box they actually own."""
    from ...contract.schema import ModuleCall

    return ModuleCall(module=module, args={"device": _device_type(state)})


# --- running a solution ---------------------------------------------------------------


def _begin(state: Any, rt: Any, fault: str | None, facts: dict[str, str]) -> None:
    """Start the fault's solution: the branch whose conditions the facts satisfy."""
    card = catalog.card(fault) if fault else None
    if card is None:
        return
    from ...contract.schema import Condition

    for index, solution in enumerate(card.solution):
        conditions = [Condition.parse(t) for t in solution.when]
        if all(c.holds(facts) is True for c in conditions) and solution.steps:
            state.case.fault, state.case.solution, state.case.step = fault, index, 0
            state.case.awaiting = None
            state.case.guide_step, state.case.guide_said = 0, -1
            # The fault the Case settled on IS the call's verdict — what the record, the
            # ticket and the eval all read (wave 4: the tree that used to name it is gone).
            network = state.diagnosis.verdicts.setdefault("network", {})
            if network.get("reason") != fault:
                network["reason"] = fault
                rt.tracer.emit("verdict", reason=fault, source="card")
            _announce_finding(state, rt, card, facts)
            rt.tracer.emit("case", move="begin", fault=fault, solution=index)
            return


def announce(state: Any, rt: Any, fault: str) -> None:
    """Work out and hold this fault's finding, for a path that does not run through the Case.

    The TV-with-no-card road (`execute/diagnosis.py`) registers a ticket without ever asking
    the Case anything, so the caller heard "priežastis telefonu nenustatyta" with no word of
    what HAD been checked (live 2026-09-23).
    """
    card = catalog.card(fault)
    if card is not None:
        _announce_finding(state, rt, card, ledger.facts_of(state))


def _announce_finding(state: Any, rt: Any, card: Any, facts: dict[str, str]) -> None:
    """Say what we found before asking for anything.

    A caller who does not know WHY does not follow the instruction (Andrius, 2026-09-22), so
    the turn that starts a fix also carries the finding: what we see, and what it means. The
    facts are the card's own reasons (`when`), glossed for a person; the conclusion is the
    card's. The narrator says it through the `explain_finding` skill (wave 2b).
    """
    from ...contract.locale import maybe_phrase
    from ...facts import summary

    if card.fault in state.case.announced:
        return  # a finding is news once
    reasons = [str(c.fact) for c in (judge(card, facts).why and _reasons(card))]
    # Plus whatever else the card says is worth telling (the honest ending matches on
    # nothing, yet the caller must hear that the line up to their flat was checked).
    seen = summary(facts, reasons + [f for f in card.explain_facts if f not in reasons])
    conclusion = maybe_phrase(card.explain.get("conclusion"))
    if not seen and not conclusion:
        return
    state.case.announced.append(card.fault)
    told = {
        "faktai": seen,
        "isvada": conclusion or "",
        "solutions": "",
        "offer": "",
        # What the caller could not tell us and what we are assuming instead — said out loud,
        # so they can correct it before anything is done in their name.
        "prielaida": _unchecked_words(state),
    }
    state.turn.directives.findings = told
    # It is also kept OUTSIDE the turn: if another rule owns this turn (the name question, the
    # ticket intro), the finding is said with that reply instead of being lost.
    state.case.finding = told
    rt.tracer.emit("case", move="finding", fault=card.fault, facts=seen)


def _reasons(card: Any) -> list:
    """The conditions the card itself names — what we would tell the caller we saw."""
    from ...contract.schema import Condition

    return [Condition.parse(text) for text in card.when.all + card.when.any]


def _following(state: Any):
    """The step after the one we are on (what the caller was about to be asked to do)."""
    card = catalog.card(state.case.fault)
    if card is None or state.case.solution is None:
        return None
    steps = card.solution[state.case.solution].steps
    index = state.case.step + 1
    return steps[index] if index < len(steps) else None


def _current(state: Any):
    """The module call this turn is on, or None when the solution is finished."""
    card = catalog.card(state.case.fault)
    if card is None or state.case.solution is None:
        return None
    steps = card.solution[state.case.solution].steps
    if state.case.step >= len(steps):
        return None
    step = steps[state.case.step]
    if state.case.retrying and step.on_fail is not None:
        return step.on_fail  # the card's clarified second attempt
    return step


def _identification_owns_the_turn(state: Any) -> bool:
    """Is the caller still being identified (the name and the holder clarification count)?"""
    s = state
    if not s.identity.customer_id:
        return True
    if s.identity.holder_clarify_open and not s.identity.holder_clarify_asked:
        return True
    return bool(s.identity.result_pending and not s.identity.caller_name)


def _diagnose_quietly(state: Any, rt: Any, facts: dict[str, str]) -> None:
    """The silent half of the Case: settle the card and hold its finding, say nothing.

    The finding is NOT lost — `state.case.finding` carries it into the reply the
    identification rule is building, which is how the caller hears what the line showed in
    the same breath as the answer to their own question.
    """
    if state.case.fault is not None:
        return
    move = next_move(facts, unavailable=ledger.unavailable(state))
    if move.kind == "solve" and move.fault and move.fault not in state.case.spent:
        _begin(state, rt, move.fault, facts)


def _ruled_out_now(state: Any, facts: dict[str, str]) -> bool:
    """Does the card we are working on now rule ITSELF out?

    `rules_out` is read when a card is chosen; a fact that arrives later (the caller plugs a
    different device into the line, the neighbours' outage is confirmed) makes the same card
    wrong, and nothing was re-reading it.
    """
    from ...contract.schema import Condition

    card = catalog.card(state.case.fault)
    if card is None or not card.rules_out:
        return False
    return any(Condition.parse(text).holds(facts) is True for text in card.rules_out)


def _absorb(state: Any, rt: Any, facts: dict[str, str]) -> str:
    """Did the step we are on finish?

    A verification is settled by its own evidence (the probe). A question is settled by the
    fact arriving. An instruction is settled by the caller SAYING they did it — which is
    the one thing the engine cannot read from the line.

    Returns "waiting", "moved", "solved", "failed", "handed_over" or "escalating".
    """
    call = _current(state)
    if call is not None:
        _tick_waiting(state, rt, call)
    if call is None:
        if state.case.summarised:
            # Išvada jau pasakyta — šis skambutis eina pas meistrą. Be šito ėjimas po išvados
            # grįždavo į „žingsnių nebėra, vadinasi išspręsta" ir agentas pasakydavo, kad
            # internetas veikia (7c banga).
            return "handed_over" if state.ticket.stage else "escalating"
        return "solved" if state.case.fault and state.case.solution is not None else "waiting"
    if (
        call is not None
        and call.module == "guide"
        and state.case.guide_said != state.case.guide_step
    ):
        # This written step has not been SAID yet, so nothing the caller says can finish it.
        # The mark is set when the reply is built (`speak/context_card.py`), never when the plan
        # is made: on a turn the identification rule owned, the guide plan existed, was never
        # spoken, and the caller's next words skipped the first step (2026-09-23).
        rt.tracer.emit(
            "case", move="guide_wait", at=state.case.guide_step, said=state.case.guide_said
        )
        return "waiting"
    if _is_escalate(call) and state.ticket.stage:
        # The technician has been asked for and the contact dialogue is collecting the
        # details: the Case has nothing left to add, and re-planning the same step made the
        # agent promise "užregistruosiu meistrą" on every turn of that dialogue.
        return "handed_over"
    if _action_ran(state, call):
        # An engine action needs nothing from the caller: once its tool has actually run the
        # step is done. Measured on the tool COUNTER, because a planned action may never run
        # (a scripted reply overrode the plan and the engine walked past the bind).
        return _advance(state, rt)
    if state.case.awaiting_probe:
        return "waiting"  # its own reading has not come back yet
    settled = modules.step_done(call, facts)
    if settled is True:
        if _verify_must_be_told(state, call):
            # Įrodymas yra, bet klientas jo dar NEIŠGIRDO. Gyvai 2026-10-02: po pririšimo
            # telemetrija jau rodė `device_seen=yes, traffic=flowing`, patikra užsidarė tylėdama,
            # ir tą patį ėjimą kortelė nuėjo į eskalaciją — klientas išgirdo tik „telefonu
            # neišspręsime", o paskui dar ir kad internetas neveiks, nors kompiuteris jau buvo
            # pririštas. Andrius (2026-09-28): *„turėtų pasakyti, kad matau, jog srautas atsirado,
            # ir pasiklausti kliento — įsitikinti, ar problema išspręsta."*
            return "waiting"
        return _advance(state, rt)
    if settled is False:
        if _model_says_not_an_answer(state) or state.dialog.last_intent == "in_progress":
            # Linija dar nerodo pokyčio, bet klientas dar DARO („ir rodo atsiverti…") — išvadų
            # dabar neskubam (Andrius, 2026-10-05: *„kad agentas neskubėtų su veiksmais ir
            # nenubėgtų į išvadas"*).
            return "waiting"
        return _retry_or_give_up(state, rt)
    walked = _jumped_ahead(state, rt)
    if walked is not None:
        return walked
    if state.case.moved_on_turn == state.dialog.turn_count:
        return "waiting"  # their words already moved us once this turn
    # A module that asks reads its OWN answer (the generic policies own their questions) — but
    # ONLY when that question was actually asked. A plan can be built and never spoken (the
    # identification or ticket rule owns the turn), and then its readers meet an answer to a
    # different question: live 2026-09-30 „Ne, tai mano vardu, Giedriaus vardu" was read as
    # `lights=no`, the lights question counted as answered, and the agent jumped to the power
    # lead without ever asking what the caller saw.
    if _step_was_asked(state) and not _model_says_not_an_answer(state):
        # Kontekstą turintis skaitymas viršesnis už bekontekstį: jei jis sako, kad klientas dar
        # daro arba klausia atgal, tai nei žodynas, nei euristikos žingsnio nejudina. „Einu
        # pasižiūrėti, ar tas kompiuteris veikia" žodynui atrodo „turi kompiuterį" (paminėtas ir
        # nepaneigtas), bet tai dar ne atsakymas (7b banga).
        read = modules.read_answer(call, state.dialog.last_heard, device=_device(state))
        if read is not None:
            fact, value = read
            ledger.record_client(state, rt, fact, value)
            facts = ledger.facts_of(state)
        # What the CALLER owns, beside what their answer MEANS: the lights they see are
        # theirs, `wan_link` is the line's, and only the first settles a question we asked.
        own = modules.client_fact(call, state.dialog.last_heard)
        if own is not None:
            ledger.record_client(state, rt, own[0], own[1])
            facts = ledger.facts_of(state)
        # Antra eilė po žodyno (7 banga): tą patį sakinį to paties ėjimo supratimo kvietimas
        # perskaitė ŽINODAMAS, ko paklausėme, ir grąžino etiketę iš UŽDARO šio modulio sąrašo.
        # Žodynas lieka pirmas (jis nemokamas ir tikslus), bet jo tyla nebėra aklavietė:
        # 2026-10-01 „Neturiu." ir „tik telefonas" žodynui nereiškė nieko, ir klausimas
        # kartojosi tris kartus.
        if state.case.awaiting and state.case.awaiting not in facts:
            model = _model_read(state, rt, call)
            if model is not None:
                ledger.record_client(state, rt, model[0], model[1])
                facts = ledger.facts_of(state)
            else:
                _note_reader_silent(state, rt, call)
    awaited = state.case.awaiting
    confirming = _confirms_hypothesis(call)
    if confirming and awaited and not _client_said(state, awaited):
        # Hipotezę patvirtinantį klausimą užskaito TIK paties kliento atsakymas. Nei „taip,
        # padariau", nei linijos duomenys, nei bendras „gerai" nepasako, ar lemputė dega —
        # 2026-10-01 gyvai tokiu neaiškiu atsakymu buvo peršokta prie maitinimo klausimo, o
        # paskui gedimas konstatuotas be lempučių. Perklausiame paprastai.
        return _answer_was_unclear(state, rt, call)
    if awaited and awaited in facts:
        if awaited == "restored" and facts[awaited] == "no":
            # Their own answer says it did not work: the card decides what that means.
            return _retry_or_give_up(state, rt)
        return _advance(state, rt, by_words=True)
    if call.module == "guide" and _answered_the_written_step(state):
        # A written step is walked by TELLING them one action and hearing what happened. Any
        # substantive answer — "radau", "pasirinkau", "atsidarė langas" — finishes that action;
        # waiting for the word "padariau" left the agent re-wording the same line while the
        # caller was already two actions ahead (live 2026-09-30).
        return _advance(state, rt, by_words=True)
    if confirming:
        return _answer_was_unclear(state, rt, call)
    if _model_says_not_an_answer(state):
        # Kontekstą turintis skaitymas pasakė, kad klientas dar daro arba klausia atgal. Tada
        # bekontekstės euristikos („veikia" sakinyje = rezultatas) nebeturi teisės pajudinti
        # žingsnio: „Einu pasižiūrėti, ar tas kompiuteris veikia" nėra sutikimas su tiltu.
        return "waiting"
    if (
        _step_was_asked(state)
        and not _model_says_still_working(state)
        and (_reported_done(state) or _model_reports_done(state) or _reported_outcome(state, call))
    ):
        # They DID it. That answers any question about being able to (live S6: "ištraukiau
        # iš routerio ir įkišau atgal" against "can you get to it now" — the engine waited
        # three turns for a yes it no longer needed) and finishes an instruction.
        if awaited:
            ledger.record_client(state, rt, awaited, _done_value(awaited))
        return _advance(state, rt, by_words=True)
    return "waiting"


# --- what the caller has actually told us, and where they have walked to -------------------


def _model_read(state: Any, rt: Any, call: Any) -> tuple[str, str] | None:
    """Atsakymas į ŠĮ klausimą, perskaitytas to paties ėjimo supratimo kvietime.

    Tai ne naujas kvietimas: `perceive` kiekvieną ėjimą paduoda modeliui šio žingsnio
    variantus (`perceive/evidence.py::_case_step_options`) ir gauna
    `{label, is_answer, internally_inconsistent, confidence}`. Čia tik nusprendžiama, ar tuo
    pasitikėti, ir etiketė verčiama faktu modulio taisyklėmis.

    Trys atsisakymo atvejai, kurie NĖRA „nesupratau": `label="unclear"` (modelis sąžiningai
    nepriskyrė), `is_answer=false` (klientas dar daro arba klausia atgal) ir sakinys, kuris
    pats sau prieštarauja.
    """
    from ...contract import limits

    read = (state.turn.perception or {}).get("step") or {}
    label = str(read.get("label") or "")
    if not label or label == "unclear" or not read.get("is_answer"):
        return None
    if read.get("internally_inconsistent"):
        return None
    confidence = float(read.get("confidence") or 0.0)
    if confidence < limits.get("reading_confirm_confidence"):
        return None
    answer = modules.answer_from_label(call, label, device=_device(state))
    if answer is None:
        return None
    if label == "no" and not _heard_a_negation(state.dialog.last_heard):
        # Modelis gali atverti duris, bet ne užverti jų be kliento žodžio. Eval D8: į „Visuose"
        # (atsakymą apie įrenginius) modelis atsakė, kad klientas prie routerio prieiti NEGALI —
        # pasitikėjimas 1,0 — ir skambutis nuėjo į namų darbus. Lietuviškas atsakymas „ne" beveik
        # visada nešasi neiginį; be jo tai spėjimas, ir klausiame iš naujo (7e banga).
        rt.tracer.emit("case", move="model_no_without_words", module=call.module, label=label)
        return None
    if confidence < limits.get("reading_accept_confidence"):
        # Vidutinis pasitikėjimas: užskaitom, bet atsakyme pakeliui patvirtinam — kad klientas
        # galėtų pataisyti, o ne kad agentas apsimestų tikras.
        from ...evidence import gloss_label, gloss_value

        said = f"{gloss_label(answer[0])} {gloss_value(answer[1], answer[0])}".strip()
        state.turn.confirm_reading = said or None
    rt.tracer.emit(
        "case",
        move="read_by_model",
        module=call.module,
        label=label,
        confidence=round(confidence, 2),
        sets=f"{answer[0]}={answer[1]}",
    )
    return answer


def _verify_must_be_told(state: Any, call: Any) -> bool:
    """Ar ši patikra turi pirma PASAKYTI, ką linija rodo, ir paklausti kliento?

    Taikoma tik patikrai, kuri pati turi klausimą (`ask:`): tada telemetrijos įrodymas yra
    pagrindas PASAKYTI, o ne praleisti žingsnį. Kai klausimas jau nuskambėjo, kliento atsakymas
    žingsnį užbaigia įprastu keliu.
    """
    spec = catalog.module(call.module)
    if spec is None or spec.kind != "verify" or not call.args.get("ask"):
        return False
    return state.case.step_said != state.case.step


def _model_reports_done(state: Any) -> bool:
    """Ar šio ėjimo skaitymas (su ŠIO žingsnio variantais) pasakė, kad veiksmas ATLIKTAS?

    Nurodymo žingsnis nelaukia jokio fakto, tad per `state.case.awaiting` einanti antra eilė jo
    neapima — o būtent čia žodynas ir pralenda. Gyvai 2026-10-02: ASR sudarkė „įkišau" į „Iki
    šau", liko tik „pavyko", modelis grąžino `label="done", is_answer=true, confidence=1.0`, o
    variklis to nepaėmė ir pakartojo tą pačią instrukciją (7c banga).
    """
    from ...contract import limits

    read = (state.turn.perception or {}).get("step") or {}
    if read.get("label") != "done" or not read.get("is_answer"):
        return False
    return float(read.get("confidence") or 0.0) >= limits.get("reading_accept_confidence")


def _heard_a_negation(heard: str | None) -> bool:
    """Ar kliento sakinyje apskritai yra neiginys / atsisakymas?

    Tai ne atsakymo skaitymas, o SARGAS modelio „ne": be jokio „ne-" sakinyje toks atsakymas
    yra spėjimas (eval D8: „Visuose" perskaityta kaip „negaliu prieiti").
    """
    from ...evidence import _fold

    if not heard:
        return False
    # Lietuviškas neiginys yra priešdėlis: „ne-" / „nė-" („nedega", „nėra", „neturiu",
    # „nebūtina", „nelabai"). Tad užtenka vieno tokio žodžio — o „Visuose" jo neturi.
    return any(_fold(token).startswith("ne") for token in heard.lower().split())


def _model_says_still_working(state: Any) -> bool:
    """Ar šio ėjimo skaitymas sako, kad veiksmas DAR vyksta (`waiting`)?

    Tada nei „matau", nei „gerai" neužskaito žingsnio: gyvai 2026-10-05 „Matau admin, admin sakot
    įvesti, ne?" per `detect_restored` pajudino vedimą, nors klientas tik klausė, ką vesti.
    """
    read = (state.turn.perception or {}).get("step") or {}
    return read.get("label") == "waiting"


def _model_says_not_an_answer(state: Any) -> bool:
    """Ar šio ėjimo skaitymas (su ŠIO klausimo variantais) pasakė, kad tai ne atsakymas?

    `is_answer=false` reiškia „dar daro / klausia atgal / nesupranta" — ne „nesupratau aš".
    Tai vienintelis signalas, kuris žino KLAUSIMĄ, tad jis viršesnis už bekontekstes
    euristikas (7 banga).
    """
    read = (state.turn.perception or {}).get("step") or {}
    return "is_answer" in read and not read.get("is_answer")


def _note_reader_silent(state: Any, rt: Any, call: Any) -> None:
    """Niekas nesuprato atsakymo į klausimą, kurį uždavėme — ir tai turi būti MATOMA.

    Be šito „kitais žodžiais" radiniai ateina tik iš gyvų skambučių ir tik tada, kai agentas
    jau užsiciklino. Dabar po testų sesijos trace'e yra sąrašas, ko žodynai ir modelis
    nesuprato — iš jo auga žodynai ir parafrazių testai (7 banga).
    """
    spec = catalog.module(call.module)
    if spec is None or spec.kind != "ask" or not state.dialog.last_heard:
        return
    rt.tracer.emit(
        "reader_silent",
        module=call.module,
        detector=spec.detector,
        fact=state.case.awaiting,
        heard=state.dialog.last_heard,
        turn=state.dialog.turn_count,
    )


def _tick_waiting(state: Any, rt: Any, call: Any) -> None:
    """Ar šis ėjimas ką nors PRIDĖJO — ir kiek jau laukiam šio žingsnio.

    Žmogus suporte neskaičiuoja pakartojimų; jis stebi, ar kitas žmogus vis dar dirba su juo.
    Tą ir skaičiuojam: tušti ėjimai (nei informacijos, nei veiksmo, nei klausimo) didina
    `case.stall`, o bet kokia įnašas jį nulina. Tyla turi savo kelią — ji nėra tuščias ėjimas.
    """
    state.case.waits += 1
    heard = (state.dialog.last_heard or "").strip()
    if not heard:
        state.case.silence_asks += 1
        rt.tracer.emit("case", move="silence", step=state.case.step, asks=state.case.silence_asks)
        return
    state.case.silence_asks = 0
    if _turn_contributed(state, heard):
        state.case.stall = 0
        return
    state.case.stall += 1
    rt.tracer.emit(
        "case", move="stall", step=state.case.step, stall=state.case.stall, heard=heard[:60]
    )


def _turn_contributed(state: Any, heard: str) -> bool:
    """Ar klientas pridėjo ką nors: faktą, veiksmą, klausimą ar bent naują sakinį."""
    from ...dialog_utils import similar
    from ...perceive.detectors import INTENT_IN_PROGRESS, is_real_question

    if (state.turn.perception or {}).get("facts"):
        return True  # naujas faktas — net jei ne tas, kurio klausėm
    if state.dialog.last_intent == INTENT_IN_PROGRESS:
        return True  # „einu", „tuoj", „ieškau" — klientas dirba
    if is_real_question(heard):
        return True  # klausia — vadinasi, įsitraukęs
    if _only_a_shrug(heard):
        return False  # trumpas „nežinau" be jokios detalės nieko nepridėjo
    return not any(similar(heard, earlier) for earlier in state.dialog.recent_heard)


def _only_a_shrug(heard: str) -> bool:
    """Ar tai tik „nežinau" be jokios detalės?

    Viskas, kas pasako, KUR klientas užstrigo („nerandu", „čia dvi dėžutės"), yra informacija —
    su ja agentas dirba toliau. Tuščias yra tik trumpas gūžtelėjimas pečiais.
    """
    from ...contract.locale import vocab

    low = heard.lower().strip(" .,!?")
    if len(low.split()) > 3:
        return False
    return any(mark in low for mark in vocab("shrug"))


def _confirms_hypothesis(call: Any) -> bool:
    """Ar šis žingsnis yra klausimas, kuriuo laikosi hipotezė (`confirms: true`)?

    Andrius (2026-09-30): *„žingsniai, kurių negalima praleisti — tie, kurie patvirtina
    hipotezę."* Tokio klausimo negalima nei praleisti (`_jumped_ahead`), nei užskaityti iš
    netiesioginio atsakymo (čia).
    """
    spec = catalog.module(call.module)
    if spec is None or spec.kind != "ask":
        return False
    return bool(getattr(spec, "confirms", False))


def _answer_was_unclear(state: Any, rt: Any, call: Any) -> str:
    """Klausimas lieka stovėti, o atsakymas pažymimas neaiškiu — kad atsakymas būtų
    perklaustas paprastai („dega ar nedega?"), o ne tas pats klausimas tais pačiais žodžiais.
    Pakartojimų sargas (`_repeat_guard`) ir toliau neleidžia klausti be galo."""
    if state.dialog.last_heard and _step_was_asked(state):
        state.case.unclear = state.case.step
        rt.tracer.emit(
            "case",
            move="unclear",
            fault=state.case.fault,
            step=state.case.step,
            module=call.module,
        )
    return "waiting"


def _client_said(state: Any, fact: str | None) -> bool:
    """Did the CALLER tell us this — or did a probe merely fill the same fact name?

    A question exists to hear what only the caller can see. `check_lights` waits for
    `wan_link`, which the line also produces, so on 2026-09-30 the whole lights / power /
    socket conversation was skipped as "already known" and the agent went straight to the
    bridge: it had never established that the router was even alive. Telemetry cannot see
    whether a box is unplugged; that is the caller's to say.

    Andrius (2026-09-30): *„žingsniai, kurių negalima praleisti — tie, kurie patvirtina hipotezę.
    Routerio gedimui nustatyti reikia lempučių ir ar elektra pasiekia įrenginį."*
    """
    if not fact:
        return False
    return fact in (state.case.said or []) and bool(state.case.facts.get(fact))


def _solution_steps(state: Any) -> list:
    card = catalog.card(state.case.fault)
    if card is None or state.case.solution is None:
        return []
    return list(card.solution[state.case.solution].steps)


def _reported_index(state: Any, steps: list) -> int | None:
    """The LAST step whose own words the caller just used — how far ahead they have walked.

    The words belong to the module (`reported:`), not to the engine, so a technician can
    widen them without touching this file.
    """
    heard = (state.dialog.last_heard or "").lower()
    if not heard:
        return None
    from ...contract.locale import vocab

    found = None
    for index, call in enumerate(steps):
        spec = catalog.module(call.module)
        key = getattr(spec, "reported", None) if spec else None
        if key and any(marker.lower() in heard for marker in vocab(key)):
            found = index
    return found


def _jumped_ahead(state: Any, rt: Any) -> str | None:
    """The caller did more than they were asked — accept it, but never skip a question.

    Two rules, and they come from the same place (Andrius, 2026-09-30): an instruction the
    LINE can verify may be taken on the caller's word (" įrenginys dingo iš linijos" is a fact
    we can read), but a question whose answer only THEY have — the lights, the socket, a
    computer in the house — confirms the hypothesis and cannot be passed over. So a jump
    forward is accepted over `instruct` steps and stops at the first unanswered `ask`.
    """
    steps = _solution_steps(state)
    here = state.case.step
    said = _reported_index(state, steps)
    if said is None or said <= here or said >= len(steps):
        return None
    blocking = None
    for index in range(here, said):
        plan = modules.plan_step(steps[index])
        spec = catalog.module(steps[index].module)
        if plan is None or plan.kind != "ask" or not getattr(spec, "confirms", False):
            # An instruction the line can verify, or a question that only arranges the work
            # ("can you reach it"): somebody who just unplugged the router can reach it.
            continue
        if not _client_said(state, plan.awaits):
            # The same words may answer this question too ("galiu prieiti, jau išjungiau iš
            # elektros" answers BOTH), so the module's own reader gets first refusal.
            read = modules.read_answer(steps[index], state.dialog.last_heard, device=_device(state))
            if read is not None:
                ledger.record_client(state, rt, read[0], read[1])
        if not _client_said(state, plan.awaits):
            blocking = index
            break
    if blocking is not None:
        # Back to the question the hypothesis stands on — and the reply says what we already
        # know, so the caller hears WHY they are asked to step back.
        state.case.step = blocking
        state.case.awaiting = None
        state.case.retrying = False
        rt.tracer.emit(
            "case",
            move="back",
            fault=state.case.fault,
            to=steps[blocking].module,
            because=steps[said].module,
        )
        _explain_retry(state, rt)
        return "moved"
    state.case.step = said
    rt.tracer.emit("case", move="jumped", fault=state.case.fault, to=steps[said].module)
    return _advance(state, rt, by_words=True)


def _step_was_asked(state: Any) -> bool:
    """Did THIS step's own question actually go out to the caller?

    The mark is set where the reply is built (`speak/context_card.py`), never where the plan
    is made — a plan another rule overrode was never heard, and nothing the caller says next
    is an answer to it.
    """
    return state.case.step_said == state.case.step


def _answered_the_written_step(state: Any) -> bool:
    """Did they answer the action we just read out?

    An ANSWER moves the written procedure; a question or a confusion does not — those are
    replied to (from the same document, `speak/context_card.py`) and the action stands. A bare
    "gerai" is not an answer either: they are about to do it, not reporting.
    """
    if state.case.guide_said != state.case.guide_step:
        return False  # this action has not been spoken yet
    heard = (state.dialog.last_heard or "").strip()
    if not heard or _just_acknowledged(state):
        return False
    # Modelis, gavęs ŠIO punkto variantus (`instruct_done`), pasako „done" arba „waiting" — ir
    # gyvai 2026-10-05 jis buvo teisus kiekviename ėjime, o variklis jo neklausė: „gerai,
    # pažiūrėsiu ant lipduko" ir „matau admin, sakot įvesti, ne?" buvo `waiting`, bet dokumentas
    # vis tiek pajudėdavo — tad agentas prašė „Išsaugoti", kai klientas dar nieko nebuvo padaręs.
    from ...perceive.detectors import INTENT_IN_PROGRESS

    read = (state.turn.perception or {}).get("step") or {}
    if read.get("label") == "waiting" or read.get("is_answer") is False:
        return False
    if state.dialog.last_intent == INTENT_IN_PROGRESS:
        return False  # „einu", „tuoj pažiūrėsiu" — dar ne rezultatas
    turn_type = str((getattr(state.turn, "understanding", None) or {}).get("type") or "answer")
    return turn_type == "answer"


def _queue_reflection(state: Any) -> None:
    """The step we are leaving was something the caller DID; in the demo the line has to
    show it before anything reads the line again."""
    call = _current(state)
    if call is None:
        return
    spec = catalog.module(call.module)
    if spec is not None and spec.simulate:
        state.case.reflect = spec.simulate


def _reported_outcome(state: Any, call: Any) -> bool:
    """Did they report the RESULT instead of the step? "Mirksi, puslapis atsidaro — veikia"
    is not an answer to "can you reach it", it is the outcome — so the step it was on is
    finished and the verification takes over (live probe, S6)."""
    from ...perceive.detectors import detect_restored

    spec_kind = getattr(catalog.module(call.module), "kind", None)
    if spec_kind not in ("instruct", "ask"):
        return False
    return detect_restored(state.dialog.last_heard) is not None


def _done_value(fact: str) -> str:
    """What a done-report settles: being able to reach something is proven by having done
    it; anything else is simply confirmed."""
    return "yes"


def _just_acknowledged(state: Any) -> bool:
    """Was the caller's turn a plain acknowledgement of an instruction we already gave?"""
    if state.case.delivered != state.case.step:
        return False
    from ...perceive.detectors import detect_turn_intent

    heard = (state.dialog.last_heard or "").strip()
    if not heard or detect_turn_intent(heard) == "done":
        return False
    from ...contract.locale import vocab

    low = heard.lower()
    return len(low.split()) <= 4 and any(mark in low for mark in vocab("acknowledge"))


def _action_ran(state: Any, call: Any) -> bool:
    """Did this step's own tool actually run since the step was entered?"""
    spec = catalog.module(call.module)
    if spec is None or spec.kind != "action" or not spec.tool:
        return False
    return state.tools.calls.get(spec.tool, 0) > state.case.act_count


def _reported_done(state: Any) -> bool:
    """Did the caller just say they did it?

    Deliberately narrow: the turn INTENT ("ištraukiau ir įkišau atgal" -> done), the
    perception layer's done-report, or a plain yes. A mere "answer" is not a done-report —
    reading it as one would advance a step on any reply at all.
    """
    if state.turn.done_report_key or state.dialog.last_intent == "done":
        return True
    from ...perceive.detectors import detect_turn_intent, detect_yes_no, says_done_action
    from ...resolution import Outcome

    heard = state.dialog.last_heard
    intent = detect_turn_intent(heard)
    if intent == "done":
        return True
    # A done-report WITH a question in it is still a done-report (live 2026-09-28, C1):
    # "Tai padariau. Kas toliau?" was read as a question, the step never moved, and the same
    # instruction came back six times. Only a question — confusion keeps its own path, because
    # "nesuprantu, ką padariau" is not a completed action.
    if intent == "question" and says_done_action(heard):
        return True
    return detect_yes_no(heard) is Outcome.YES


def _reflect_plan(state: Any, rt: Any) -> TurnPlan | None:
    """DEMO: make the seeded line show what the caller just did, then decide again in the
    same turn so the verification reads the NEW state (the S6 probe registered a ticket
    for a reboot the database never saw)."""
    import os

    tool = state.case.reflect
    if not tool:
        return None
    state.case.reflect = None
    spec = next(
        (m for m in catalog.modules().values() if m.simulate == tool),
        None,
    )
    flag = spec.simulate_env if spec else None
    if flag and os.getenv(flag, "off").lower() != "on":
        return None  # production: nothing simulates anything
    rt.tracer.emit("case", move="reflect", tool=tool)
    return TurnPlan(
        owner="procedure",
        rule="case.reflect",
        action=Action(type="tool", name=tool, args={"customer_id": _cid(state)}),
        say=Say(kind="none"),
        redecide_after_action=True,
    )


def _remember_what_we_heard(state: Any) -> None:
    """Faktas, kurį klientas ką tik pasakė, jo reikšmės žodžiais („lemputės nedega").

    Tą pačią eilutę jau statėm dviejose vietose (`_model_read` patvirtinimui ir santraukai);
    L2 ją naudoja parašytame atsakyme, kad „Gerai — lemputės nedega" nebereikėtų modelio.
    """
    from ...evidence import gloss_label, gloss_value

    state.turn.heard_said = None
    key = state.case.awaiting
    value = ledger.facts_of(state).get(key) if key else None
    if not key or not value:
        return
    label, said = gloss_label(key), gloss_value(value, key)
    # Dalis faktų pakuotėje pavadinti KLAUSIMU („ar gali dabar prieiti prie įrenginio"), nes iš
    # jų statomas klausimas klientui. Teiginiu jie neskaitomi: gyvai per eval'ą 2026-10-05 iš to
    # išėjo „Gerai — ar gali dabar prieiti prie įrenginio turite." Tokių nepatvirtinam — geriau
    # nieko, nei sulūžęs sakinys.
    if not label or not said or "?" in label or label.lower().startswith("ar "):
        return
    state.turn.heard_said = f"{label} {said}".strip() or None


def _asked_to_repeat(state: Any) -> bool:
    """Ar klientas PATS paprašė pakartoti. Tada teisingas atsakymas yra tie PATYS žodžiai —
    žmogus pakartoja sakinį, o ne perfrazuoja jį iš naujo (gyvai 2026-10-02)."""
    heard = (state.dialog.last_heard or "").lower()
    return bool(heard) and any(mark in heard for mark in vocab("repeat_request"))


def _say_as_written(state: Any, step: Any, rt: Any = None) -> bool:
    """Ar šį ėjimą galima pasakyti PARAŠYTAIS žodžiais, be narratoriaus (L2, 2026-10-05)?

    Taip — kai ėjimas neturi ką kita pasakyti: žingsnio sakinys yra kataloge ar dokumente,
    klausimas dar nenuskambėjo, klientas tik atsakė, ir nė viena kita direktyva nelaukia žodžių.
    Visais kitais atvejais — kaip iki šiol, per modelį: narratorius reikalingas būtent tada, kai
    reikia ATSAKYTI, perfrazuoti, paaiškinti ar sudėti kelis dalykus į vieną atsakymą.

    Pamatuota 2026-10-05: 49 ėjimai iš 62 ėjo per modelį, nors 16 iš jų buvo nurodymas, kurio
    sakinys kataloge jau parašytas — ir būtent tas sakinys yra tai, ko klientas turi išgirsti
    nepakeisto (7d banga: modelis buvo išradęs mygtuką, kurio dokumente nėra).
    """
    from ...contract import limits
    from ...perceive.detectors import INTENT_CONFUSED, INTENT_QUESTION

    d = state.turn.directives
    why = None
    if not limits.get("scripted_step_words"):
        why = "off"
    elif step.kind not in ("ask", "instruct"):
        why = f"kind={step.kind}"
    elif state.case.step_said == state.case.step:
        why = "already_said"  # jau sakyta — perfrazuoti moka modelis
    elif any(
        (
            d.evidence,
            d.findings,
            d.recap,
            d.ident,
            d.ticket,
            d.proof,
            d.recheck,
            d.summary,
            d.last_chance,
        )
    ):
        why = "directive"
    elif state.turn.confirm_reading or state.turn.side_topic_active:
        why = "confirm_or_side"
    elif state.case.finding or state.case.delivered != state.case.step:
        why = "finding"  # išvada dar nepasakyta — ji eina su šiuo atsakymu, per narratorių
    elif state.dialog.last_intent in (INTENT_QUESTION, INTENT_CONFUSED):
        why = f"intent={state.dialog.last_intent}"
    elif state.case.stall or state.case.silence_asks or state.case.retrying:
        why = "assisting"
    elif state.case.waits >= limits.get("waits_before_help"):
        why = "waiting"  # jau laukiam antrą ėjimą — reikia asistavimo, ne to paties sakinio
    elif state.identity.result_pending or state.identity.holder_clarify_open or state.ticket.stage:
        why = "other_owner"
    if why and rt is not None:
        rt.tracer.emit("case", move="narrator_words", why=why)
    return why is None


def _written_words(state: Any, step: Any, asked: str | None) -> str:
    """Parašytas atsakymas: ką ką tik išgirdom + žingsnio sakinys + („pasakykite, kai
    padarysite") nurodymui. Visos trys dalys — iš frazių katalogo, ne iš kodo."""
    said = (asked or step.text or "").strip()
    lead = phrase("case.heard", said=state.turn.heard_said) if state.turn.heard_said else ""
    tail = phrase("case.say_when_done") if step.kind == "instruct" else ""
    return " ".join(part for part in (lead, said, tail) if part).strip()


def _written_plan(state: Any, rt: Any, call, step, asked: str | None, rule: str) -> TurnPlan:
    """Žingsnio planas, kurio žodžiai eina kaip parašyti (L2)."""
    words = _written_words(state, step, asked)
    # Žymės, kad klausimas nuskambėjo, čia NEDEDAM: planą gali perimti kita taisyklė, ir tada
    # šie žodžiai niekada nenuskambės. Ją padeda `say.py`, kai atsakymas tikrai ištariamas.
    rt.tracer.emit("case", move="said_as_written", module=call.module, chars=len(words))
    return TurnPlan(
        owner="procedure",
        rule=rule,
        say=Say(kind="phrase", text=words, stage="diagnosis", written=True),
        awaiting=step.awaits,
    )


def _advance(state: Any, rt: Any, *, by_words: bool = False, ran: bool = True) -> str:
    if by_words:
        state.case.moved_on_turn = state.dialog.turn_count
        _remember_what_we_heard(state)
    state.case.retrying = False
    state.case.unclear = -1
    state.case.stall, state.case.waits, state.case.silence_asks = 0, 0, 0
    done = _current(state)
    if _more_guide_steps(state, done):
        # A written procedure is walked one step per turn: the card step is not finished until
        # its document is (wave 4b).
        state.case.guide_step += 1
        state.case.awaiting = None
        rt.tracer.emit("case", move="guide", step=state.case.guide_step, module="guide")
        return "moved"
    if done is not None and done.module not in state.case.did:
        state.case.did.append(done.module)
    if ran and done is not None and done.module not in state.case.worked:
        state.case.worked.append(done.module)
    _queue_reflection(state)
    state.case.step += 1
    state.case.awaiting = None
    # Entering a verification means we need a reading of our OWN, taken after the action:
    # the previous one is what told a caller whose internet was back to reboot again. An
    # action step records how often its tool has run so far, so "it happened" is a fact.
    following = _current(state)
    if following is not None:
        spec = catalog.module(following.module)
        state.case.awaiting_probe = bool(spec and spec.kind == "verify")
        if spec is not None and spec.kind == "action" and spec.tool:
            state.case.act_count = state.tools.calls.get(spec.tool, 0)
    if _current(state) is None:
        rt.tracer.emit("case", move="solution_done", fault=state.case.fault)
        # A branch whose last step is ESCALATE ends with a technician, not with a working
        # line: "solved" here would have the narrator say the service is back (the dhcp_silent
        # card has no other step, and only the ticket dialogue holding the turn hid it).
        return "handed_over" if _ended_in_escalate(state) else "solved"
    return "moved"


def _ended_in_escalate(state: Any) -> bool:
    card = catalog.card(state.case.fault)
    if card is None or state.case.solution is None:
        return False
    steps = card.solution[state.case.solution].steps
    return bool(steps) and _is_escalate(steps[-1])


def _at_guide_step(state: Any, call: Any):
    """A `guide` call carries WHICH step of the document this turn is on (wave 4b)."""
    if call is None or call.module != "guide":
        return call
    return call.model_copy(update={"args": {**call.args, "at": state.case.guide_step}})


def _more_guide_steps(state: Any, call: Any) -> bool:
    """Is there another written step after this one? Then the card step stays where it is."""
    if call is None or call.module != "guide":
        return False
    return state.case.guide_step + 1 < modules.guide_length(call)


def _answered_elsewhere(state: Any, rt: Any, call: Any, facts: dict[str, str]) -> bool:
    """Ar į šio modulio klausimą jau atsako kitas faktas (modulio `answered_when`)?

    Gyvai 2026-10-01: klientas pasakė, kad kompiuterio neturi, o tiltas vis tiek buvo
    siūlomas ir paskui vykdomas — kortelės `done_when` sąlygos jungiamos IR, tad „praleisk,
    jei atsisakė ARBA jei nėra ko jungti" joje neišreiškiama. Modulis tai pasako pats, ir
    atsakymas įrašomas kaip kliento (jis juk tai ir pasakė), kad tolesni žingsniai praleistų
    save savo esamu `done_when`.
    """
    from ...contract.schema import Condition

    spec = catalog.module(call.module)
    for rule in getattr(spec, "answered_when", None) or []:
        if Condition.parse(rule.when).holds(facts) is not True:
            continue
        fact, value = rule.set.split("=", 1)
        if facts.get(fact) != value:
            ledger.record_client(state, rt, fact, value)
            rt.tracer.emit(
                "case", move="answered_elsewhere", module=call.module, by=rule.when, sets=rule.set
            )
        return True
    return False


def _skip_now(call: Any, facts: dict[str, str]) -> bool:
    """Ar šis žingsnis NETAIKOMAS (`skip_when`) — bet kuri sąlyga pakanka.

    `done_when` reiškia „jau padaryta" ir jungia sąlygas IR; čia reikėjo ARBA: tilto žingsnių
    nebėra ko daryti, jei klientas atsisakė ARBA jei nėra kompiuterio. Gyvai 2026-10-02
    „neturiu kompiuterio" atėjo jau PO pasiūlymo, tad `answered_when` nebeveikė, ir agentas
    tris kartus prašė kišti laidą į kompiuterį, kurio nėra — o paskui naratorius išsigalvojo
    perkrovimą (7d banga).
    """
    from ...contract.schema import Condition

    for text in getattr(call, "skip_when", None) or []:
        if Condition.parse(text).holds(facts) is True:
            return True
    return False


def _already_done(call: Any, facts: dict[str, str]) -> bool:
    """Does the card itself say this step is achieved (`done_when`)?"""
    from ...contract.schema import Condition

    conditions = [Condition.parse(text) for text in (getattr(call, "done_when", None) or [])]
    return bool(conditions) and all(c.holds(facts) is True for c in conditions)


def _is_escalate(call: Any) -> bool:
    spec = catalog.module(call.module) if call is not None else None
    return bool(spec and spec.kind == "escalate")


def _last_chance(state: Any, rt: Any, call: Any, step: Any) -> TurnPlan | None:
    """Tušti ėjimai kaupiasi — pirma sąžiningai pasakom, ko nepavyksta, ir duodam DAR VIENĄ šansą.

    Andrius (2026-10-05): *„agentas gali pasakyti, kad mums nepavyksta surasti routerio, jūs
    negalite pasakyti — klientas turi dar šansą pabandyti… dar vienas šansas visada, kad
    išvengtume, kai agentas nesuprato arba klientas nesuprato, ko nori agentas."*

    Vieną kartą vienam žingsniui. Jei po jo klientas vėl nieko nepridės, pasiduos `_repeat_guard`
    ir skambutis baigsis išvada bei meistru.
    """

    if not _no_way_forward(state):
        return None
    key = f"{state.case.fault}.{state.case.step}"
    if state.case.chances.get(key):
        return None
    state.case.chances[key] = True
    state.turn.directives.last_chance = {
        "kas": _need_words(state, step.awaits) or "",
        "kodel": _why_words(state, step.awaits) or "",
    }
    rt.tracer.emit("case", move="last_chance", module=call.module, fact=step.awaits)
    return TurnPlan(
        owner="procedure",
        rule="case.last_chance",
        say=Say(kind="directive", goal=step.goal, stage="diagnosis"),
        awaiting=step.awaits,
    )


def _no_way_forward(state: Any) -> bool:
    """Ar šiame žingsnyje judėti pirmyn nebėra kaip?

    Dvi skirtingos kantrybės: tušti ėjimai (klientas kalba, bet nieko nepriduria) ir tyla
    (klientas nieko nesako). Tyla kantresnė ir turi savo žodžius, bet ir ji negali tęstis
    amžinai (8 banga).
    """
    from ...contract import limits

    return state.case.stall >= limits.get("stall_before_last_chance") or (
        state.case.silence_asks >= limits.get("silence_before_last_chance")
    )


def _need_words(state: Any, fact: str | None) -> str | None:
    """Ko nepavyksta išsiaiškinti — kliento kalba („kokios lemputės dega")."""
    if not fact:
        return None
    from ...evidence import gloss_label

    return gloss_label(fact) or None


def _why_words(state: Any, fact: str | None) -> str | None:
    """Kodėl to reikia — kortelės `needs.<faktas>.why`, jei ji tai pasako."""
    from ...contract.locale import maybe_phrase

    card = catalog.card(state.case.fault)
    need = card.needs.get(fact) if card and fact else None
    return maybe_phrase(need.why) if need else None


def _repeat_guard(state: Any, rt: Any, call: Any) -> TurnPlan | None:
    """A step that keeps being re-said is a step that is not working.

    Live 2026-09-28: the same reboot instruction went out six times because nothing counted.
    After `step_repeat_max` the card decides — its `on_fail` runs once (different words, and
    the REASON with them) — and when there is none, the honest answer is a technician.
    """
    from ...contract import limits

    # Vedimas yra VIENAS kortelės žingsnis, einamas per daug punktų — tad raktas turi įtraukti ir
    # punktą. Gyvai 2026-10-01: kiekvienas atsakytas punktas didino tą patį skaitliuką, ir po
    # trečio agentas pasakė „telefonu neišspręsime, registruoju meistrą" — kaip tik tada, kai klientas
    # jau buvo prisijungęs prie routerio skydelio.
    if not _no_way_forward(state):
        # Klientas vis dar dirba su mumis (pridėjo faktą, klausė, pasakė „einu") — tai ne ciklas,
        # ir žingsnio atsisakyti negalima, kad ir kiek ėjimų tai užimtų (Andrius, 2026-10-05).
        return None
    key = f"{state.case.fault}.{state.case.step}"
    if call.module == "guide":
        key = f"{key}.{state.case.guide_step}"
    seen = state.case.repeats.get(key, 0)
    if seen < limits.get("step_repeat_max"):
        state.case.repeats[key] = seen + 1
        return None
    card = catalog.card(state.case.fault)
    steps = (
        card.solution[state.case.solution].steps if card and state.case.solution is not None else []
    )
    on_fail = steps[state.case.step].on_fail if 0 <= state.case.step < len(steps) else None
    if on_fail is not None and not state.case.retrying:
        state.case.retrying = True
        state.case.repeats[key] = 0
        rt.tracer.emit("case", move="repeat_limit", fault=state.case.fault, module=call.module)
        _explain_retry(state, rt)
        following = _current(state)
        return (
            _module_plan_inner(state, rt, following, ledger.facts_of(state), rule="case.retry")
            if following is not None
            else None
        )
    # The step WAS attempted — three times. Without recording that, `escalate.only_after`
    # sends us straight back into the same branch and the call spins (eval X_dhcp_silent,
    # 2026-09-30: repeat_gave_up -> phone_work_first -> the same step, for the rest of the
    # call).
    if call.module not in state.case.did:
        state.case.did.append(call.module)
    rt.tracer.emit("case", move="repeat_gave_up", fault=state.case.fault, module=call.module)
    return _escalate(state, rt, state.case.fault)


def _retry_or_give_up(state: Any, rt: Any) -> str:
    """The verification says it did not work. The CARD decides what that means: its
    `on_fail` runs once, and when there is none — or it has already run — the fix is spent
    and a technician is the honest next step."""
    previous = state.case.step - 1
    card = catalog.card(state.case.fault)
    steps = (
        card.solution[state.case.solution].steps if card and state.case.solution is not None else []
    )
    retry = steps[previous].on_fail if 0 <= previous < len(steps) else None
    key = f"{state.case.fault}.{previous}"
    if retry is not None and state.case.attempts.get(key, 0) == 0:
        state.case.attempts[key] = 1
        state.case.step = previous  # the card's clarified retry, once
        state.case.retrying = True
        state.case.awaiting = None
        _explain_retry(state, rt)
        rt.tracer.emit("case", move="retry", fault=state.case.fault, step=previous)
        return "moved"
    if state.case.fault and state.case.fault not in state.case.spent:
        state.case.spent.append(state.case.fault)
    state.case.awaiting = None
    rt.tracer.emit("case", move="fix_failed", fault=state.case.fault)
    # The fix did not work, and the reading has changed since it started. Before a technician,
    # the CASE looks again: another card may still be open and one cheap question may settle it
    # ("klausimai patikrina ar atmeta hipotezę" — Andrius, 2026-09-23). It is the same facts,
    # so nothing is guessed; if nothing is left, the next pass escalates honestly.
    state.case.solution, state.case.step = None, 0
    return "reopen"


def _explain_retry(state: Any, rt: Any) -> None:
    """Why we are asking again. "Nematome, kad įrenginys būtų buvęs išjungtas" is the whole
    reason the caller is asked to repeat the reboot at the router's own socket — said kindly,
    never as blame."""
    from ...facts import gloss

    facts = ledger.facts_of(state)
    told = [
        part
        for part in (
            gloss("port_flapped", facts.get("port_flapped")),
            gloss("traffic", facts.get("traffic")),
        )
        if part
    ]
    if not told:
        return
    state.turn.directives.findings = {
        "faktai": ", ".join(told),
        "isvada": "",
        "solutions": "",
        "offer": "",
    }


def _proof_plan(state: Any, rt: Any, call: Any, facts: dict[str, str], step: Any, rule: str):
    """Patikra, kurios įrodymas jau yra: pasakom, ką matom, ir paklausiam kliento.

    Be šio ėjimo telemetrija uždarydavo patikrą tyliai: gyvai 2026-10-02 po pririšimo klientas
    nieko negirdėjo apie tai, kad srautas atsirado, o po sekundės išgirdo „telefonu
    neišspręsime" ir dar kad internetas neveiks — nors kompiuteris jau buvo pririštas.
    """
    from ...contract.schema import Condition
    from ...facts import summary as facts_summary

    keys = [Condition.parse(text).fact for text in (call.args.get("evidence") or [])]
    state.turn.directives.proof = {"faktai": facts_summary(facts, keys)}
    # Klausiam, tad ir laukiam atsakymo: be šito kliento „ne, vis tiek neveikia" niekur
    # nenukeliautų — žingsnį uždarytų ta pati telemetrija, kuri jau sako, kad veikia.
    answer = modules.answer_from_label(call, "yes")
    awaits = step.awaits or (answer[0] if answer else None)
    state.case.awaiting = awaits
    if awaits:
        state.diagnosis.pending_evidence_key = awaits
    rt.tracer.emit("case", move="proof", module=call.module, facts=state.turn.directives.proof)
    return TurnPlan(
        owner="procedure",
        rule=rule,
        say=Say(kind="directive", goal=step.goal, stage="diagnosis"),
        awaiting=awaits,
    )


def _resolved(state: Any, rt: Any) -> TurnPlan:
    """The solution ran and the line agrees: say it works and close warmly. The engine
    closes on ITS verdict, never on the caller's word alone (D-07)."""
    rt.tracer.emit("case", move="resolved", fault=state.case.fault)
    return TurnPlan(
        owner="diagnosis",
        rule="case.resolved",
        action=Action(type="close", name="resolved"),
        say=Say(
            kind="directive", goal="say the service is back and close warmly", stage="diagnosis"
        ),
    )


# --- one module, one turn -------------------------------------------------------------


def _step_plan(
    state: Any, rt: Any, call, facts: dict[str, str], rule: str | None = None
) -> TurnPlan:
    return _module_plan(state, rt, call, facts, rule=rule or f"case.{call.module}")


def _module_plan(state: Any, rt: Any, call, facts: dict[str, str], *, rule: str) -> TurnPlan:
    """What this module asks of the turn."""
    # The Case decides this turn: an evidence question left by the old reading layer is not
    # this turn's goal (it chose the narrator's skill and overrode the step).
    state.turn.directives.evidence = None
    return _module_plan_inner(state, rt, call, facts, rule=rule)


def _module_plan_inner(state: Any, rt: Any, call, facts: dict[str, str], *, rule: str) -> TurnPlan:
    """What this module asks of the turn. `on_fail` retries are the card's business, and a
    step the equipment catalogue cannot word is skipped rather than improvised."""
    from ...contract import limits

    model = _device_model(state)
    call = _at_guide_step(state, call)
    step = modules.plan_step(call, model=model)
    if step is None or (step.kind == "instruct" and not step.text):
        rt.tracer.emit("case", move="skip", module=call.module, why="no wording for this device")
        _advance(state, rt, ran=False)
        following = _current(state)
        if following is not None:
            return _module_plan_inner(state, rt, following, facts, rule=f"case.{following.module}")
        return _escalate(state, rt, state.case.fault)

    settled = _answered_elsewhere(state, rt, call, facts)
    if settled:
        facts = ledger.facts_of(state)
    insists = _confirms_hypothesis(call) and state.case.step_said != state.case.step
    already = (
        settled
        or _skip_now(call, facts)
        or _already_done(call, facts)
        or (
            step.kind == "ask"
            and step.awaits
            and _client_said(state, step.awaits)
            # Hipotezę patvirtinančio klausimo NEPRALEIDŽIA pakeliui pasakytas faktas. Gyvai
            # 2026-10-02: iš „dėžutė visiškai atrodo kaip be maitinimų" modelis padarė
            # `power_cable=unplugged`, ir maitinimo klausimas — be kurio „routeris sugedęs" yra
            # spėjimas — buvo praleistas kaip „jau žinomas". Spėjimas apie išvaizdą nėra
            # atsakymas (7d banga).
            and not insists
        )
    )
    if already:
        # They already told us, or the card says this step is achieved — asking again is how an
        # agent stops sounding like a person ("ar galite prieiti prie routerio?" right after
        # "esu prie routerio"). The ORDER of the fix is untouched: only what is already true is
        # passed over.
        rt.tracer.emit("case", move="known", module=call.module, fact=step.awaits)
        _advance(state, rt, ran=False)
        following = _current(state)
        if following is not None:
            return _module_plan_inner(state, rt, following, facts, rule=f"case.{following.module}")
        return _escalate(state, rt, state.case.fault)
    state.case.awaiting = step.awaits
    if step.awaits:
        state.diagnosis.pending_evidence_key = step.awaits
    # Pokalbio sluoksnio laukimo būsena. Iki 8 bangos `dialog.awaiting` ir `awaiting_turns` v2
    # variklyje buvo tik SKAITOMI — niekas jų nepildė, tad visa kantrybės direktyvų šeima
    # („klientas dar daro, nekartok", „suskaidyk į mažesnį", „pasiteirauk, kaip sekasi") niekada
    # nesuveikdavo. Tai penktas tos pačios šeimos radinys po `step_perception_options`,
    # `bridge_bound`, `step_said` ir `progress_key`.
    state.dialog.awaiting = step.awaits or ("client_action" if step.kind != "action" else None)
    state.dialog.awaiting_turns = state.case.waits
    if insists and step.awaits and _client_said(state, step.awaits):
        # Klientas tai jau užsiminė, bet klausimas yra per svarbus, kad eitume iš spėjimo:
        # patikslinam, o ne klausiam tuščiai („jūs sakėte, kad… patikslinu").
        from ...evidence import gloss_label, gloss_value

        value = state.case.facts.get(step.awaits)
        state.turn.directives.recheck = {
            "faktas": f"{gloss_label(step.awaits)} {gloss_value(value, step.awaits)}".strip()
        }
    asked = modules.question_of(call, model=model)
    if step.kind == "instruct" and _just_acknowledged(state):
        # They said "gerai" — they are doing it. Repeating the instruction is what makes an
        # agent sound like a machine; the 2b skill already knows how to wait.
        rt.tracer.emit("case", move="wait", module=call.module)
        return TurnPlan(
            owner="procedure",
            rule="case.wait",
            say=Say(
                kind="directive",
                goal="they are doing it — say you will wait, nothing else",
                stage="diagnosis",
            ),
            awaiting=step.awaits,
        )
    if (
        step.kind in ("ask", "instruct")
        and limits.get("scripted_step_words")
        and _asked_to_repeat(state)
        and (asked or step.text)
    ):
        # Klientas paprašė pakartoti: tie patys žodžiai, be modelio ir be naujos redakcijos.
        rt.tracer.emit("case", move="repeat_as_asked", module=call.module)
        return TurnPlan(
            owner="procedure",
            rule=rule,
            say=Say(
                kind="phrase",
                text=(asked or step.text or "").strip(),
                stage="diagnosis",
                written=True,
            ),
            awaiting=step.awaits,
        )
    if step.kind in ("ask", "instruct"):
        chance = _last_chance(state, rt, call, step)
        if chance is not None:
            return chance
        exhausted = _repeat_guard(state, rt, call)
        if exhausted is not None:
            return exhausted
    state.case.delivered = state.case.step
    if step.kind == "escalate":
        return _escalate(state, rt, state.case.fault, note=step.note)
    if step.kind == "action":
        # A module with words ANNOUNCES what the engine is doing and the turn ends there —
        # the caller hears "pririšiu, sekundėlę" instead of a silent chain of tools (full
        # eval, S1). A module without words is internal plumbing: silent, same turn.
        speaks = bool(asked)
        return TurnPlan(
            owner="procedure",
            rule=rule,
            action=Action(type="tool", name=step.tool, args={"customer_id": _cid(state)}),
            say=Say(kind="directive", text=asked, goal=step.goal, stage="diagnosis")
            if speaks
            else Say(kind="none"),
            redecide_after_action=not speaks,
        )
    if step.kind == "verify":
        if _verify_must_be_told(state, call) and modules.step_done(call, facts) is True:
            # Įrodymas jau yra (zondas atsakė ankstesniame ėjime), tad šis ėjimas nebezonduoja —
            # jis PASAKO, ką linija rodo, ir paklausia kliento. Andrius (2026-09-28): *„turėtų
            # pasakyti, kad matau, jog srautas atsirado… ir pasiklausti kliento."*
            return _proof_plan(state, rt, call, facts, step, rule)
        state.case.awaiting_probe = True
        return TurnPlan(
            owner="procedure",
            rule=rule,
            action=Action(type="tool", name=step.tool, args={"customer_id": _cid(state)}),
            say=Say(
                kind="directive",
                goal=step.goal,
                stage="diagnosis",
                knowledge_need=call.knowledge_need,
            ),
            awaiting=step.awaits,
            redecide_after_action=True,
        )
    if (asked or step.text) and _say_as_written(state, step, rt):
        return _written_plan(state, rt, call, step, asked, rule)
    return TurnPlan(
        owner="procedure",
        rule=rule,
        # A module that asks speaks its own question; an instruction speaks the catalogue's
        # words for this device, and both are a FALLBACK — the narrator words them.
        say=Say(
            kind="directive",
            text=asked or step.text,
            goal=step.goal,
            stage="diagnosis",
            # Kortelės paprašytos gilesnės žinios keliauja su ŠIO žingsnio planu: jei žingsnį perėmė
            # kitas modulis (praleistas, jau padarytas), poreikis eina su juo, ne su šiuo.
            knowledge_need=call.knowledge_need,
        ),
        awaiting=step.awaits,
    )


def _escalate(state: Any, rt: Any, fault: str | None, note: str | None = None) -> TurnPlan:
    """Telephone help is over: the contact dialogue collects the details and the engine
    registers (the ticket path is unchanged — wave 1b).

    Before it is over, the card gets a say: `escalate.only_after` names the phone work that
    must have been done, because a technician arriving to power-cycle a router is a visit we
    wasted (Andrius, 2026-09-23). When that work is still possible, it happens instead.
    """
    from ...execute.ticket import begin_ticket_dialogue

    pending = _phone_work_left(state, fault)
    if pending is not None:
        rt.tracer.emit("case", move="phone_work_first", fault=fault, module=pending)
        started = _start_branch_with(state, rt, fault, pending)
        if started is not None:
            return started
    card = catalog.card(fault) if fault else None
    if card is not None and card.escalate:
        note = note or card.escalate.note
    state.case.fault = state.case.fault or fault
    # IŠVADA prieš registraciją — savo ėjimu. Andrius (2026-10-02): *„pasakyti, ką padarėme ir
    # kodėl registruojame tiketą… klientas atsimins galutinį pokalbį."* Atskiras ėjimas, nes
    # išvada + kontakto klausimas viename atsakyme nebetelpa: srauto sargas baigia atsakymą ties
    # 200 simbolių, ir klausimas nukristų (7 bangos G34). Tiketo dialogas pradedamas TIK po jos,
    # kad tiketo taisyklė (3 eilutė) šio ėjimo nepaimtų.
    live_facts = ledger.facts_of(state)
    if _bridge_live(state, live_facts):
        # Laikinas internetas tikrai PALEISTAS. Šią žymę rašė tik v1 vedlys (`execute/diagnosis`),
        # tad v2 skambutyje tiketo įvadas „internetas kol kas veikia per kompiuterį" ir tiketo
        # aprašymas apie tiltą buvo tamsūs: gyvai 2026-10-02 klientas išgirdo „telefonu
        # neišspręsime", o paskui dar ir kad internetas neveiks, nors kompiuteris buvo pririštas.
        state.resolution.bridge_bound = True
    if not state.case.summarised:
        told = _summary_words(state, card, live_facts)
        state.case.summarised = True
        if told:
            state.turn.directives.summary = told
            state.case.summary = told
            rt.tracer.emit("case", move="summary", fault=fault, said=told)
            return TurnPlan(
                owner="procedure",
                rule="case.summary",
                say=Say(kind="directive", goal="sum up what was done and why", stage="diagnosis"),
            )
    begin_ticket_dialogue(state, rt, None)
    if note:
        state.case.facts.setdefault("_ticket_note", note)
    rt.tracer.emit("case", move="escalate", fault=fault, note=note)
    goal = "say WHY the phone cannot fix this and that a technician will be registered"
    unchecked = _unchecked_words(state)
    if unchecked:
        # "Jūs nežinote, ar neveikia visuose įrenginiuose" — the caller must hear what stayed
        # unclear BEFORE a technician is registered in their name (Andrius, 2026-09-23).
        goal = f"{goal}. Say plainly what we could not check together: {unchecked}"
    return TurnPlan(
        owner="ticket",
        rule="case.escalate",
        say=Say(kind="directive", goal=goal, stage="ticket"),
    )


def _caller_is_lost(state: Any, rt: Any) -> bool:
    """Ar klientas nebegali sekti žingsnių?

    `dialog.stuck_count` kyla tik tada, kai agentas IŠ TIKRŲJŲ pakartoja tą patį (ir nebekyla,
    kai klientas pats paprašė pakartoti — 7f). Pasiekus ribą telefoninis sprendimas baigiamas su
    išvada, o ne identifikacijos kopėčia.
    """
    from ...contract import limits

    if state.dialog.stuck_count < limits.get("stuck_fix_gives_up"):
        return False
    if not _no_way_forward(state):
        return False  # jis vis dar dirba su mumis — tai ne aklavietė
    if state.case.summarised or state.ticket.stage:
        return False  # jau baigiam
    state.case.facts.setdefault("_lost_the_thread", "yes")
    rt.tracer.emit(
        "case", move="caller_lost", fault=state.case.fault, stuck=state.dialog.stuck_count
    )
    return True


def _summary_words(state: Any, card: Any, facts: dict[str, str]) -> dict[str, str] | None:
    """Kas padaryta, ką tai reiškia, kas veikia dabar ir ko nepavyko — kliento kalba.

    Viskas iš to, ką variklis jau turi: `case.did` (kas tikrai VYKO), kortelės išvada, tilto
    būsena, atsisakymai ir tai, ko nepavyko patikrinti. Nieko naujo neskaičiuojama — todėl ši
    išvada negali prasilenkti su tuo, kas skambutyje buvo.
    """
    from ...contract.locale import maybe_phrase, phrase_or

    did: list[str] = []
    for module in state.case.worked:
        # Tik DARBAI: klausimų moduliai (ar galite prieiti, ar turite kompiuterį) čia frazės
        # neturi, ir to pakanka, kad į išvadą nepakliūtų.
        words = phrase_or(f"summary.did.{module}", "")
        if words and words not in did:
            did.append(words)
    missed: list[str] = []
    if facts.get("has_computer") == "no":
        # Ne atsisakė — nebuvo kuo. Gyvai 2026-10-02 tikete rašė „nenorėjot", nors klientas
        # kompiuterio neturėjo.
        missed.append(phrase_or("summary.no_computer", ""))
    elif facts.get("bridge_agreed") == "no":
        missed.append(phrase_or("summary.declined_bridge", ""))
    if facts.get("guide_agreed") == "no":
        missed.append(phrase_or("summary.declined_guide", ""))
    if facts.get("_lost_the_thread") == "yes":
        missed.append(phrase_or("summary.lost_the_thread", ""))
    unchecked = _unchecked_words(state)
    if unchecked:
        missed.append(unchecked)
    told = {
        "padaryta": ", ".join(did),
        # Po gyvo tilto kortelės išvada jau pasenusi: linijoje DABAR matomas kliento
        # kompiuteris, tad „linijoje jūsų įrenginio nematome" būtų netiesa (gyvai 2026-10-02).
        # Kodėl reikia meistro, pasako `kodel` (kortelės `escalate.need`).
        "isvada": (
            ""
            if _bridge_live(state, facts)
            else (maybe_phrase(card.explain.get("conclusion")) if card else "") or ""
        ),
        "dabar": (phrase_or("summary.bridge_live", "") if _bridge_live(state, facts) else ""),
        "nepavyko": "; ".join(part for part in missed if part),
        "kodel": (
            maybe_phrase(card.escalate.need)
            if card and card.escalate and card.escalate.need
            else ""
        )
        or "",
    }
    if not (told["padaryta"] or told["dabar"] or told["nepavyko"]):
        return None  # nieko nebuvo padaryta — nėra ko ir sumuoti
    return told


def _bridge_live(state: Any, facts: dict[str, str]) -> bool:
    """Ar laikinas internetas tikrai PALEISTAS (ne pasiūlytas): pririšimas įvyko ir linija mato
    tą patį įrenginį. Gyvai 2026-10-02 klientas apie tai neišgirdo nė žodžio."""
    return "bind" in state.case.did and facts.get("device_registered") == "match"


def _phone_work_left(state: Any, fault: str | None) -> str | None:
    """The module the card insists on before a technician — if it has not run and still can.

    "Still can" is the honest part: a caller who cannot get to the device (or refused) is not
    made to, and the ticket records that the work was not possible.
    """
    card = catalog.card(fault) if fault else None
    if card is None or not card.escalate or not card.escalate.only_after:
        return None
    facts = ledger.facts_of(state)
    if (
        facts.get("reachable") == "no"
        or facts.get("later_agreed") == "no"
        or facts.get("guide_agreed") == "no"
    ):
        # Not at the device, asked for a technician, or declined to be walked through the
        # settings: there is nothing left to insist on, and insisting is not help.
        return None
    for name in card.escalate.only_after:
        if name not in state.case.did:
            return name
    return None


def _start_branch_with(state: Any, rt: Any, fault: str | None, module: str) -> TurnPlan | None:
    """Enter the solution branch that contains this module, at its first unfinished step."""
    card = catalog.card(fault) if fault else None
    if card is None:
        return None
    from ...contract.schema import Condition

    facts = ledger.facts_of(state)
    for index, solution in enumerate(card.solution):
        if not any(call.module == module for call in solution.steps):
            continue
        # A branch whose conditions are CONTRADICTED is not the road; unknowns are fine here —
        # we are past asking, and the card named this work as necessary anyway.
        if any(Condition.parse(text).holds(facts) is False for text in solution.when):
            continue
        state.case.fault, state.case.solution, state.case.step = card.fault, index, 0
        state.case.awaiting = None
        step = _current(state)
        return _step_plan(state, rt, step, facts) if step is not None else None
    return None


# --- what the line says the caller has ------------------------------------------------


def _signals(state: Any) -> dict[str, Any]:
    return ((state.diagnosis.verdicts or {}).get("network") or {}).get("signals") or {}


def _device(state: Any):
    """The caller's device as the catalogue describes it (for reading light answers)."""
    from ...equipment import for_signals

    return for_signals(_signals(state))


def _device_type(state: Any) -> str:
    return str(_signals(state).get("device_type") or "router")


def _device_model(state: Any) -> str | None:
    return _signals(state).get("device_model")


def _cid(state: Any) -> str | None:
    return state.identity.customer_id
