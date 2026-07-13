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
the engine (react_agent) wires the tool calls, telemetry and prompts around it.
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
    hint: str = ""  # LT guidance shown to the LLM for THIS step only
    tools: frozenset[str] = frozenset()  # tools the LLM may call this step
    tool_actions: tuple[str, ...] = ()  # backend tools the engine runs (ACTION)
    # 0-based index of the "### Žingsnis N" section in the strategy's RAG doc to
    # inject for THIS step (only that section, never the whole file). None = none.
    rag_section: int | None = None
    # Where to jump on each outcome (step id). Missing outcome = fall through to
    # the next step in order. "resolve"/"escalate"/"end" are terminal sentinels.
    on: dict[Outcome, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Strategy:
    verdict: str
    rag_doc: str | None
    steps: tuple[Step, ...]

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def index_of(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        return -1


# Terminal sentinels a step can route to.
TERMINALS = frozenset({"resolve", "escalate", "end"})


def next_step_id(strategy: Strategy, current_id: str, outcome: Outcome | None) -> str:
    """Given the current step and the turn's outcome, return the next step id (or a
    terminal sentinel). Explicit `on` routing wins; otherwise fall through to the
    next step in order; past the last step -> 'end'."""
    step = strategy.step(current_id)
    if step is None:
        return "end"
    if outcome is not None and outcome in step.on:
        return step.on[outcome]
    i = strategy.index_of(current_id)
    if i < 0 or i + 1 >= len(strategy.steps):
        return "end"
    return strategy.steps[i + 1].id


# --- Strategy registry -------------------------------------------------------
# B6 — foreign MAC after a router change. confirm -> bind (silent action that
# auto-resets the port and re-checks the line) -> verify -> resolve/escalate.
_FOREIGN_MAC = Strategy(
    verdict="foreign_mac",
    rag_doc="troubleshooting/internet_pakeistas_routeris_mac",
    steps=(
        Step(
            id="confirm_change",
            kind=StepKind.CONFIRM,
            tools=frozenset(),
            rag_section=0,  # "### Žingsnis 1: Ką klientas prijungė"
            hint=(
                "Paklausk, ar klientas neseniai keitė ar prijungė kitą įrenginį "
                "(routerį, kompiuterį ar TV). Jei nieko nekeitė ir nepaaiškina — "
                "įtartinas įrenginys, eskaluoti (registruoti)."
            ),
            on={Outcome.NO: "escalate"},
        ),
        Step(
            id="bind_mac",
            kind=StepKind.ACTION,
            tool_actions=("update_mac",),  # engine chains reset_port + re-diagnose silently
            hint="Pririšk naują įrenginį; sistema perkraus portą ir per-tikrins liniją.",
        ),
        Step(
            id="verify",
            kind=StepKind.VERIFY,
            hint=(
                "Jei telemetrija rodo, kad linija atstatyta — pasakyk klientui, kad "
                "sutvarkyta, ir uždaryk kaip resolved. Jei ne — eskaluoti."
            ),
            on={Outcome.FIXED: "resolve", Outcome.NOT_FIXED: "escalate"},
        ),
    ),
)

STRATEGIES: dict[str, Strategy] = {
    "foreign_mac": _FOREIGN_MAC,
}


def get_strategy(verdict: str | None) -> Strategy | None:
    """The strategy for a diagnosis verdict reason, or None if unhandled (the
    caller falls back to the generic instruct/inform flow)."""
    return STRATEGIES.get(verdict or "")


def verify_target(strategy: Strategy, fixed: bool) -> str | None:
    """The terminal a strategy's VERIFY step routes to for a fixed / not-fixed
    telemetry outcome (e.g. 'resolve' / 'escalate'). None if it has no VERIFY step.
    Used by the engine after a silent action to decide resolve vs escalate."""
    vstep = next((s for s in strategy.steps if s.kind == StepKind.VERIFY), None)
    if vstep is None:
        return None
    return next_step_id(strategy, vstep.id, Outcome.FIXED if fixed else Outcome.NOT_FIXED)
