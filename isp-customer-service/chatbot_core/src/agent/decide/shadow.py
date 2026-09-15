"""Shadow TurnPlan — the plan the current code paths effectively executed (M4 step 2).

Nothing here decides. After each turn the session compares the state before and after,
reads the turn's trace events (decisions, tool calls) and the reply path the engine
took, and emits one `turn_plan` event. The traces of every eval scenario become the
reference the policy chain is compared with. Deleted when decide produces the plans.
"""

from __future__ import annotations

from typing import Any

from .plan import Action, HypothesisView, Say, TurnPlan

# Reply paths whose words are engine-composed (a phrase), not LLM wording.
PHRASE_PATHS = frozenset(
    {
        "greeting",
        "stuck_backstop",
        "scripted",
        "wait_ack",
        "closing_scripted",
        "max_turns",
        "llm_error",
        "timeout",
    }
)
DIRECTIVE_PATHS = frozenset({"llm", "speculation"})
MUTATING_TOOLS = frozenset({"update_mac", "reset_port", "create_ticket", "append_ticket_note"})
_DECISION_EVENTS = ("decision", "drive_decision")


class TurnEventRecorder:
    """A tracer wrapper that keeps the current turn's events for the shadow plan."""

    def __init__(self, inner: Any):
        self._inner = inner
        self.turn_events: list[dict[str, Any]] = []

    def begin_turn(self) -> None:
        self.turn_events = []

    def emit(self, event_type: str, **fields: Any) -> None:
        self.turn_events.append({"type": event_type, **fields})
        self._inner.emit(event_type, **fields)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def shadow_plan(before: Any, after: Any, events: list[dict[str, Any]]) -> tuple[TurnPlan, dict]:
    """The plan this turn effectively executed, and the raw shadow details."""
    path = after.turn.reply_path or ("none" if after.turn.reply is None else "unknown")
    node = after.turn.active_node
    decisions = [e for e in events if e.get("type") in _DECISION_EVENTS]
    tools = [e.get("name") for e in events if e.get("type") == "tool_call"]
    owner = _owner(before, after, path, node, decisions)
    rule = f"{owner}.{path}"
    if decisions:
        last = decisions[-1]
        rule += f".{last.get('intent') or 'drive'}.{last.get('action')}"
    if path == "greeting":
        rule = "intake.dialog.greeting"
    say_kind = _say_kind(path, decisions, after)
    plan = TurnPlan(
        owner=owner,
        rule=rule,
        action=_action(before, after, tools),
        say=Say(kind=say_kind),
        hypothesis=_hypothesis(after),
        awaiting=_awaiting(after),
    )
    details = {
        "path": path,
        "node": node,
        "decisions": [f"{d.get('intent') or 'drive'}.{d.get('action')}" for d in decisions],
        "tools": tools,
    }
    return plan, details


def _owner(before: Any, after: Any, path: str, node: str | None, decisions: list) -> str:
    if path == "greeting":
        return "intake"
    if node == "closing" or before.closing.case_closed:
        return "closing"
    if before.ticket.stage or node == "ticket_registration":
        return "ticket"
    if node == "side_topic" or after.turn.side_topic_active:
        return "side_topic"
    if not before.identity.customer_id:
        return "identification"
    if any(str(d.get("intent") or "").startswith("inform") for d in decisions):
        return "inform"
    if path == "solver":
        return "diagnosis"
    if after.resolution.procedure and any("from_step" in d for d in decisions):
        return "procedure"
    return "diagnosis"


def _say_kind(path: str, decisions: list, after: Any) -> str:
    if after.turn.reply is None and path == "none":
        return "none"
    if path in PHRASE_PATHS:
        return "phrase"
    if path in DIRECTIVE_PATHS:
        return "directive"
    if path == "solver":
        # The LLM solver worded it when it decided; the evidence layer's replies are phrases.
        return (
            "directive" if any(d.get("type") == "drive_decision" for d in decisions) else "phrase"
        )
    return "directive"


def _action(before: Any, after: Any, tools: list) -> Action:
    if after.ticket.ticket_id and not before.ticket.ticket_id:
        return Action(type="register_ticket")
    mutating = [t for t in tools if t in MUTATING_TOOLS]
    if mutating:
        name = mutating[-1]
        return Action(type="append_ticket" if name == "append_ticket_note" else "tool", name=name)
    if after.closing.case_closed and not before.closing.case_closed:
        return Action(type="close", name=after.closing.closed_reason)
    step_before = (before.resolution.procedure or {}).get("step")
    proc = after.resolution.procedure or {}
    if proc.get("step") and proc.get("step") != step_before:
        from ..faults import role_of

        return Action(type="procedure_step", name=role_of(proc.get("verdict"), proc.get("step")))
    return Action(type="none")


def _hypothesis(after: Any) -> HypothesisView | None:
    cause = (after.resolution.procedure or {}).get("verdict")
    return HypothesisView(cause=cause, status="active") if cause else None


def _awaiting(after: Any) -> str | None:
    if after.dialog.awaiting:
        return str(after.dialog.awaiting)
    proc = after.resolution.procedure or {}
    if proc.get("step"):
        from ..faults import role_of

        return role_of(proc.get("verdict"), proc.get("step"))
    return None
