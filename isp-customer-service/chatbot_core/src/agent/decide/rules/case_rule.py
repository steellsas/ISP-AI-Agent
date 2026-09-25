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
from ...contract.locale import maybe_phrase
from ..plan import Action, Say, TurnPlan


def plan(state: Any, rt: Any) -> TurnPlan | None:
    """This turn on the fault path."""
    reflect = _reflect_plan(state, rt)
    if reflect is not None:
        return reflect
    facts = ledger.facts_of(state)
    later = _not_now_plan(state, rt, facts)
    if later is not None:
        return later
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
        if status == "solved":
            return _resolved(state, rt)
        step = _current(state)
        if step is not None:
            return _step_plan(state, rt, step, facts)
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


def _absorb(state: Any, rt: Any, facts: dict[str, str]) -> str:
    """Did the step we are on finish?

    A verification is settled by its own evidence (the probe). A question is settled by the
    fact arriving. An instruction is settled by the caller SAYING they did it — which is
    the one thing the engine cannot read from the line.

    Returns "waiting", "moved", "solved" or "failed".
    """
    call = _current(state)
    if call is None:
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
        return _advance(state, rt)
    if settled is False:
        return _retry_or_give_up(state, rt)
    if state.case.moved_on_turn == state.dialog.turn_count:
        return "waiting"  # their words already moved us once this turn
    # A module that asks reads its OWN answer (the generic policies own their questions).
    read = modules.read_answer(call, state.dialog.last_heard, device=_device(state))
    if read is not None:
        fact, value = read
        ledger.record_client(state, rt, fact, value)
        facts = ledger.facts_of(state)
    awaited = state.case.awaiting
    if awaited and awaited in facts:
        if awaited == "restored" and facts[awaited] == "no":
            # Their own answer says it did not work: the card decides what that means.
            return _retry_or_give_up(state, rt)
        return _advance(state, rt, by_words=True)
    if _reported_done(state) or _reported_outcome(state, call):
        # They DID it. That answers any question about being able to (live S6: "ištraukiau
        # iš routerio ir įkišau atgal" against "can you get to it now" — the engine waited
        # three turns for a yes it no longer needed) and finishes an instruction.
        if awaited:
            ledger.record_client(state, rt, awaited, _done_value(awaited))
        return _advance(state, rt, by_words=True)
    return "waiting"


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
    from ...perceive.detectors import detect_turn_intent, detect_yes_no
    from ...resolution import Outcome

    heard = state.dialog.last_heard
    if detect_turn_intent(heard) == "done":
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


def _advance(state: Any, rt: Any, *, by_words: bool = False) -> str:
    if by_words:
        state.case.moved_on_turn = state.dialog.turn_count
    state.case.retrying = False
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


def _already_done(call: Any, facts: dict[str, str]) -> bool:
    """Does the card itself say this step is achieved (`done_when`)?"""
    from ...contract.schema import Condition

    conditions = [Condition.parse(text) for text in (getattr(call, "done_when", None) or [])]
    return bool(conditions) and all(c.holds(facts) is True for c in conditions)


def _is_escalate(call: Any) -> bool:
    spec = catalog.module(call.module) if call is not None else None
    return bool(spec and spec.kind == "escalate")


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
    model = _device_model(state)
    call = _at_guide_step(state, call)
    step = modules.plan_step(call, model=model)
    if step is None or (step.kind == "instruct" and not step.text):
        rt.tracer.emit("case", move="skip", module=call.module, why="no wording for this device")
        _advance(state, rt)
        following = _current(state)
        if following is not None:
            return _module_plan_inner(state, rt, following, facts, rule=f"case.{following.module}")
        return _escalate(state, rt, state.case.fault)

    already = _already_done(call, facts) or (
        step.kind == "ask" and step.awaits and step.awaits in facts
    )
    if already:
        # They already told us, or the card says this step is achieved — asking again is how an
        # agent stops sounding like a person ("ar galite prieiti prie routerio?" right after
        # "esu prie routerio"). The ORDER of the fix is untouched: only what is already true is
        # passed over.
        rt.tracer.emit("case", move="known", module=call.module, fact=step.awaits)
        _advance(state, rt)
        following = _current(state)
        if following is not None:
            return _module_plan_inner(state, rt, following, facts, rule=f"case.{following.module}")
        return _escalate(state, rt, state.case.fault)
    state.case.awaiting = step.awaits
    if step.awaits:
        state.diagnosis.pending_evidence_key = step.awaits
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


def _phone_work_left(state: Any, fault: str | None) -> str | None:
    """The module the card insists on before a technician — if it has not run and still can.

    "Still can" is the honest part: a caller who cannot get to the device (or refused) is not
    made to, and the ticket records that the work was not possible.
    """
    card = catalog.card(fault) if fault else None
    if card is None or not card.escalate or not card.escalate.only_after:
        return None
    facts = ledger.facts_of(state)
    if facts.get("reachable") == "no" or facts.get("later_agreed") == "no":
        return None  # not at the device / they asked for a technician: nothing to insist on
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
