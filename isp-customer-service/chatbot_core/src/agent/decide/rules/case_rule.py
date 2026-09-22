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
    facts = ledger.facts_of(state)
    if state.case.fault is not None:
        status = _absorb(state, rt, facts)
        if status == "failed":
            return _escalate(state, rt, state.case.fault)
        if status == "solved":
            return _resolved(state, rt)
        step = _current(state)
        if step is not None:
            return _step_plan(state, rt, step, facts)
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
    settled = modules.step_done(call, facts)
    if settled is True:
        return _advance(state, rt)
    if settled is False:
        return _retry_or_give_up(state, rt)
    awaited = state.case.awaiting
    if awaited and awaited in facts:
        return _advance(state, rt)
    if awaited is None and _reported_done(state):
        # An instruction with nothing to answer: their word that it is done moves us on.
        return _advance(state, rt)
    return "waiting"


def _reported_done(state: Any) -> bool:
    """Did the caller just say they did it? The perception layer reads this as the turn's
    intent; a plain "taip" to an instruction counts."""
    if state.turn.done_report_key:
        return True
    if state.dialog.last_intent in ("done", "answer"):
        return True
    understanding = state.turn.understanding or {}
    return understanding.get("turn_type") == "answer"


def _advance(state: Any, rt: Any) -> str:
    state.case.step += 1
    state.case.awaiting = None
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
    if step.kind == "escalate":
        return _escalate(state, rt, state.case.fault, note=step.note)
    if step.kind == "action":
        return TurnPlan(
            owner="procedure",
            rule=rule,
            action=Action(type="tool", name=step.tool, args={"customer_id": _cid(state)}),
            say=Say(kind="directive", goal=step.goal, stage="diagnosis"),
            redecide_after_action=True,
        )
    if step.kind == "verify":
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
        say=Say(kind="directive", text=step.text, goal=step.goal, stage="diagnosis"),
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


def _device_type(state: Any) -> str:
    return str(_signals(state).get("device_type") or "router")


def _device_model(state: Any) -> str | None:
    return _signals(state).get("device_model")


def _cid(state: Any) -> str | None:
    return state.identity.customer_id
