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

import re
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


# Terminal sentinels a step can route to. "escalate" is a real ESCALATE step (the
# agent registers a fault there), so it is NOT a terminal — only resolve/end are.
TERMINALS = frozenset({"resolve", "end"})


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
# B6 — foreign MAC after a router change. The default resolution is to BIND: the
# line cable physically reaches the caller's flat, so the device on it is almost
# certainly theirs. Flow: confirm (did you change a device?) -> if not, check the
# WAN cable (a mis-plug into a LAN port makes the router act as a switch and the
# line then shows a *jumping* device MAC — bind the WAN'd router MAC, not a
# jumping one) -> bind (silent action: reset_port + re-diagnose) -> verify ->
# resolve, or escalate ONLY if binding did not restore the line.
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
                "Tell the caller plainly that the line shows a new/other device and "
                "that is why there is no internet, then ask whether they recently "
                "changed or connected a device — a new router, or a PC/TV plugged "
                "straight into the line (a valid temporary bridge). If YES -> we bind "
                "it. If they changed NOTHING -> do NOT escalate: the line cable "
                "reaches their own flat, so the device is almost certainly theirs; "
                "move on to checking how the cable is plugged (next step)."
            ),
            on={Outcome.YES: "bind_mac", Outcome.NO: "check_cable"},
        ),
        Step(
            id="check_cable",
            kind=StepKind.CONFIRM,
            tools=frozenset(),
            rag_section=1,  # "### Žingsnis 2: Patikrinti kabelius"
            hint=(
                "The caller changed nothing, so the foreign/jumping MAC is usually a "
                "mis-plugged cable. The incoming line cable must sit in the router's "
                "WAN (internet) port — often a different colour or marked 'Internet' — "
                "not a LAN port. A LAN plug turns the router into a switch and the line "
                "then shows a jumping device MAC. Ask them to check the cable is in "
                "WAN; if it was elsewhere, ask them to move it to WAN (the correct "
                "router MAC then appears). Do NOT suggest rebooting — it changes "
                "nothing if the cable is in the wrong port. Whatever they answer, we "
                "proceed to bind next."
            ),
        ),
        Step(
            id="bind_mac",
            kind=StepKind.ACTION,
            tools=frozenset({"update_mac"}),  # only NOW is binding exposed to the model
            tool_actions=("update_mac",),  # engine chains reset_port + re-diagnose silently
            rag_section=2,  # "### Žingsnis 3: Pririšti įrenginį"
            hint=(
                "Announce the fix plainly first ('dabar pririšiu jūsų įrenginį prie "
                "tinklo, palaukite') — say WHAT you are doing and WHY (the line shows a "
                "device that is not yet bound) — then call update_mac. Do not rush."
            ),
        ),
        Step(
            id="verify",
            kind=StepKind.VERIFY,
            rag_section=3,  # "### Žingsnis 4: Patikrinti srautą"
            hint=(
                "If the telemetry shows the line restored, tell the caller it is fixed "
                "and close as resolved. If not, escalate (register)."
            ),
            on={Outcome.FIXED: "resolve", Outcome.NOT_FIXED: "escalate"},
        ),
        Step(
            id="escalate",
            kind=StepKind.ESCALATE,
            tools=frozenset({"create_ticket"}),
            hint=(
                "Binding did not restore the line (or the device cannot be reached). "
                "Register the fault for a technician check ('gedimo registracija') — a "
                "worker will call the next business day."
            ),
        ),
    ),
)

STRATEGIES: dict[str, Strategy] = {
    "foreign_mac": _FOREIGN_MAC,
}


# Deterministic yes/no read of a caller reply, to advance a CONFIRM step. Coarse
# on purpose: a clear affirmative advances (e.g. to bind), anything with a denial
# or "nothing changed" does NOT advance to an action — so the agent never binds a
# device the caller did not knowingly connect.
_NEG = (
    "nekeič",
    "nekeit",
    "nekyč",  # STT garbling of "nekeičiau"
    "nekėč",
    "nekič",
    "nekie",  # STT garbling of "nekeičiau" -> "nekiečiau"
    "nieko nekeit",
    "nieko nedar",
    "nieko nekyč",
    "neprijung",
    "nemaiš",
    "nežinau",
    "neatsimen",
)
_POS = (
    "taip",
    "aha",
    "teisingai",
    "keičiau",
    "pakeič",
    "prijungiau",
    "prijungėm",
    "naują",
    "naujas",
    "nusipirk",
)


# A STRONG device-change signal (not a bare "taip"): the caller volunteered that
# they changed/connected equipment, so a CONFIRM step can advance even if its
# question was not asked yet (they pre-answered — common: "neveikia, keičiau
# routerį"). A bare affirmative alone must NOT advance a confirm before it is asked.
_DEVICE_CHANGE = (
    "keičiau",
    "keitėm",
    "pakeič",
    "prijungiau",
    "prijungėm",
    "prijungiau naują",
    "nusipirk",
    "naują router",
    "naujas router",
    "kitą įrenginį",
    "kitą router",
    "kompiuter",  # PC plugged straight into the line (temporary bridge)
    "kompiuterį",
    "televizor",
    "prijungiau tv",
)


def confirms_device_change(text: str | None) -> bool:
    """True if the caller clearly stated they changed/connected a device."""
    if not text:
        return False
    low = text.lower()
    if any(m in low for m in _NEG):
        return False
    return any(m in low for m in _DEVICE_CHANGE)


def detect_yes_no(text: str | None) -> Outcome | None:
    """YES / NO / None from a free-text caller reply (Lithuanian). Denials win over
    affirmatives ('routerio nekeičiau' -> NO), so an ambiguous or negative answer
    never advances a CONFIRM step into a binding action."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _NEG):
        return Outcome.NO
    if re.search(r"\bne\b", low):
        return Outcome.NO
    if any(m in low for m in _POS):
        return Outcome.YES
    return None


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
