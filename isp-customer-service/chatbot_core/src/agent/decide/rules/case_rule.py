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
from ...case import next_move
from ...contract import cards as catalog
from ...contract.locale import maybe_phrase
from ..plan import Action, Say, TurnPlan


def plan(state: Any, rt: Any) -> TurnPlan | None:
    """This turn on the fault path."""
    reflect = _reflect_plan(state, rt)
    if reflect is not None:
        return reflect
    facts = ledger.facts_of(state)
    if state.case.fault is not None:
        status = _absorb(state, rt, facts)
        # The caller's physical action must reach the line BEFORE anything reads it again,
        # or the verification judges a reboot the database never saw (live probe, S6).
        reflect = _reflect_plan(state, rt)
        if reflect is not None:
            return reflect
        if status == "failed":
            return _escalate(state, rt, state.case.fault)
        if status == "solved":
            return _resolved(state, rt)
        step = _current(state)
        if step is not None:
            return _step_plan(state, rt, step, facts)
    if _not_a_fault(facts) and state.case.fault is None:
        # An outage or a suspended service is NOT a fault we diagnose: the inform path owns
        # the turn, and escalating here hijacked it (full eval: four inform scenarios).
        return None
    move = next_move(facts, unavailable=ledger.unavailable(state))
    rt.tracer.emit("case", move=move.kind, fact=move.fact, fault=move.fault, why=move.why)
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


def _not_a_fault(facts: dict[str, str]) -> bool:
    return any(facts.get(fact) == "yes" for fact in NOT_OUR_FAULT)


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
    return TurnPlan(
        owner="diagnosis",
        rule="case.ask",
        say=Say(
            kind="directive",
            text=maybe_phrase(source.ask),
            goal=f"learn {move.fact} — only the caller can tell us",
            stage="diagnosis",
        ),
        awaiting=move.fact,
    )


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
            rt.tracer.emit("case", move="begin", fault=fault, solution=index)
            return


def _current(state: Any):
    """The module call this turn is on, or None when the solution is finished."""
    card = catalog.card(state.case.fault)
    if card is None or state.case.solution is None:
        return None
    steps = card.solution[state.case.solution].steps
    if state.case.step >= len(steps):
        return None
    return steps[state.case.step]


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
    # A module that asks reads its OWN answer (the generic policies own their questions).
    read = modules.read_answer(call, state.dialog.last_heard, device=_device(state))
    if read is not None:
        fact, value = read
        ledger.record_client(state, rt, fact, value)
        facts = ledger.facts_of(state)
    awaited = state.case.awaiting
    if awaited and awaited in facts:
        return _advance(state, rt)
    if _reported_done(state) or _reported_outcome(state, call):
        # They DID it. That answers any question about being able to (live S6: "ištraukiau
        # iš routerio ir įkišau atgal" against "can you get to it now" — the engine waited
        # three turns for a yes it no longer needed) and finishes an instruction.
        if awaited:
            ledger.record_client(state, rt, awaited, _done_value(awaited))
        return _advance(state, rt)
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


def _advance(state: Any, rt: Any) -> str:
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
        return "solved"
    return "moved"


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
        state.case.awaiting = None
        rt.tracer.emit("case", move="retry", fault=state.case.fault, step=previous)
        return "moved"
    if state.case.fault and state.case.fault not in state.case.spent:
        state.case.spent.append(state.case.fault)
    state.case.awaiting = None
    rt.tracer.emit("case", move="fix_failed", fault=state.case.fault)
    return "failed"


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
    """What this module asks of the turn. `on_fail` retries are the card's business, and a
    step the equipment catalogue cannot word is skipped rather than improvised."""
    model = _device_model(state)
    step = modules.plan_step(call, model=model)
    if step is None or (step.kind == "instruct" and not step.text):
        rt.tracer.emit("case", move="skip", module=call.module, why="no wording for this device")
        _advance(state, rt)
        following = _current(state)
        if following is not None:
            return _module_plan(state, rt, following, facts, rule=f"case.{following.module}")
        return _escalate(state, rt, state.case.fault)

    state.case.awaiting = step.awaits
    if step.awaits:
        state.diagnosis.pending_evidence_key = step.awaits
    asked = modules.question_of(call, model=model)
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
            say=Say(kind="directive", goal=step.goal, stage="diagnosis"),
            awaiting=step.awaits,
            redecide_after_action=True,
        )
    return TurnPlan(
        owner="procedure",
        rule=rule,
        # A module that asks speaks its own question; an instruction speaks the catalogue's
        # words for this device, and both are a FALLBACK — the narrator words them.
        say=Say(kind="directive", text=asked or step.text, goal=step.goal, stage="diagnosis"),
        awaiting=step.awaits,
    )


def _escalate(state: Any, rt: Any, fault: str | None, note: str | None = None) -> TurnPlan:
    """Telephone help is over: the contact dialogue collects the details and the engine
    registers (the ticket path is unchanged — wave 1b)."""
    from ...execute.ticket import begin_ticket_dialogue

    card = catalog.card(fault) if fault else None
    if card is not None and card.escalate:
        note = note or card.escalate.note
    state.case.fault = state.case.fault or fault
    begin_ticket_dialogue(state, rt, None)
    if note:
        state.case.facts.setdefault("_ticket_note", note)
    rt.tracer.emit("case", move="escalate", fault=fault, note=note)
    return TurnPlan(
        owner="ticket",
        rule="case.escalate",
        say=Say(kind="directive", goal="say a technician will be registered", stage="ticket"),
    )


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
