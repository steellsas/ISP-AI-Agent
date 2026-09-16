"""Resolution strategy registry + step sequencer (pure, unit-testable).

Each diagnosis VERDICT maps to a Strategy = an ordered list of Steps. The engine
walks the steps DETERMINISTICALLY — the model cannot skip: per turn it exposes
only the current step's tools + content, and the engine advances afterwards.

Step kinds:
- CONFIRM  — ask the caller a yes/no and WAIT (client-facing).
- ACTION   — backend tool(s) the engine runs SILENTLY, then verifies (no wait).
- INSTRUCT — guide the caller through one step and WAIT (client does something).
- VERIFY   — re-read telemetry; decide fixed -> resolve, or not -> retry/escalate.
             A fresh verdict here can PIVOT the whole flow to another strategy.
- ESCALATE — register the fault (ticket) and close.

This module is PURE (no LLM, no DB, no I/O) so the sequencing is unit-testable;
the engine wires the tool calls, telemetry and prompts around it.
Adding a fault = one Strategy here + one RAG doc — the skeleton does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepKind(str, Enum):
    CONFIRM = "confirm"
    ACTION = "action"
    INSTRUCT = "instruct"
    VERIFY = "verify"
    ESCALATE = "escalate"


class Outcome(str, Enum):
    """What the last turn produced, fed back to advance the sequence."""

    YES = "yes"  # caller confirmed / step succeeded
    NO = "no"  # caller declined / denied
    FIXED = "fixed"  # verify: telemetry shows the line restored
    NOT_FIXED = "not_fixed"  # verify: fault persists (same verdict)
    PIVOT = "pivot"  # verify: telemetry shows a DIFFERENT verdict


@dataclass(frozen=True)
class Step:
    """One node in a strategy. `tools` are exposed to the LLM this turn; for an
    ACTION step `tool_actions` are what the ENGINE runs silently (backend + verify).
    `rag_section` names the "### Žingsnis N" chunk to inject (RAG chunking, step 2).
    """

    id: str
    kind: StepKind
    # What the step DOES in the procedure (`role:` in the pack) — the engine acts
    # on roles, never on step ids (D-18).
    role: str = ""
    hint: str = ""  # LT guidance shown to the LLM for THIS step only
    # The step's GOAL in the caller's terms (`goal:` in the pack) — the
    # narrator states it, evaluates the caller's move against it ("Gerai —
    # radote" / "Ne, ne šis kabelis") and knows what "done" means here.
    goal: str = ""
    tools: frozenset[str] = frozenset()  # tools the LLM may call this step
    tool_actions: tuple[str, ...] = ()  # backend tools the engine runs (ACTION)
    # 0-based index of the "### Žingsnis N" section in the strategy's RAG doc to
    # inject for THIS step (only that section, never the whole file). None = none.
    rag_section: int | None = None
    # CONFIRM only: which detector reads the caller's reply into a routing KEY
    # ("yes_no" default, "restored", "scope", "conn"). The key indexes `on`.
    detector: str = ""
    # Routing by key -> next step id. Keys are detector outputs ("yes"/"no" or
    # "all"/"phone"/… ). Missing key = fall through to the next step in order.
    # "resolve"/"escalate"/"end" are terminal sentinels.
    on: dict[str, str] = field(default_factory=dict)
    # INSTRUCT/ACTION only: explicit next step (overrides fall-through), so two
    # instruct chains can converge on the same verify step.
    goto: str = ""
    # ESCALATE only: ask the caller's consent before registering (default). False =
    # the registration is a NECESSITY, not an offer (e.g. register_after_bridge after a
    # working bridge — the router IS dead): the engine registers on arrival and the
    # narrator only ANNOUNCES it ("užregistravau, kolegos susisieks ir paaiškins").
    consent: bool = True


@dataclass(frozen=True)
class Strategy:
    verdict: str
    rag_doc: str | None
    steps: tuple[Step, ...]

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def by_role(self, role: str) -> Step | None:
        return next((s for s in self.steps if s.role == role), None)

    def index_of(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        return -1


# Terminal sentinels a step can route to. "escalate" is a real ESCALATE step (the
# agent registers a fault there), so it is NOT a terminal — only resolve/end are.
TERMINALS = frozenset({"resolve", "end"})


def next_step_id(strategy: Strategy, current_id: str, outcome: str | None) -> str:
    """Given the current step and the turn's routing KEY (a detector output: "yes",
    "no", "all", "wifi"… — Outcome members work too, since Outcome is a str Enum),
    return the next step id (or a terminal sentinel). Explicit `on` routing wins;
    otherwise fall through to the next step in order; past the last step -> 'end'."""
    step = strategy.step(current_id)
    if step is None:
        return "end"
    if outcome is not None and outcome in step.on:
        return step.on[outcome]
    i = strategy.index_of(current_id)
    if i < 0 or i + 1 >= len(strategy.steps):
        return "end"
    return strategy.steps[i + 1].id


def get_strategy(verdict: str | None) -> Strategy | None:
    """The strategy for a diagnosis verdict reason, or None if unhandled (the
    caller falls back to the generic instruct/inform flow).

    Built from the fault pack (`knowledge/faults/`) — changing a procedure or adding
    a fault is a file edit. Imported lazily to keep the module free of a cycle."""
    if not verdict:
        return None
    from .faults import build_strategy

    return build_strategy(verdict)


def verify_target(strategy: Strategy, fixed: bool) -> str | None:
    """The terminal a strategy's VERIFY step routes to for a fixed / not-fixed
    telemetry outcome (e.g. 'resolve' / 'escalate'). None if it has no VERIFY step.
    Used by the engine after a silent action to decide resolve vs escalate."""
    vstep = next((s for s in strategy.steps if s.kind == StepKind.VERIFY), None)
    if vstep is None:
        return None
    return next_step_id(strategy, vstep.id, Outcome.FIXED if fixed else Outcome.NOT_FIXED)
