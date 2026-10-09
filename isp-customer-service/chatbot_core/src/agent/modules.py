"""Running a card's solution, one module at a time (wave 3d).

A v1 pack carried its own steps, its own routing table and its own English instruction for
the narrator, so the same reboot was written out in four cards. A v2 solution is a list of
MODULE CALLS, and this is what turns one call into what the turn must do:

    ask        a question whose answer is a fact (what the caller can see, we cannot)
    instruct   one thing for the caller to do, worded by the equipment catalogue
    action     the engine does it (a tool), the narrator only announces it
    verify     the probe and the caller's word together — did it actually work
    escalate   a technician, with what the ticket must say

The words come from the catalogue, not from the card: `reboot(device=router)` is the same
call for a TP-Link and for a box we have never seen, and the caller hears the instruction
that fits what they own (P-8).

The pointer lives in the CALL's state, so a checkpoint resume continues the same solution
at the same step rather than starting the fix again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contract import cards as catalog
from .contract.locale import maybe_phrase
from .contract.schema import Condition, ModuleCall, ModuleSpec
from .equipment import for_device


@dataclass(frozen=True)
class StepPlan:
    """What ONE module call wants from this turn. The engine turns it into a TurnPlan;
    the wording stays the narrator's, with `text` as the fallback the card guarantees."""

    kind: str  # ask | instruct | action | verify | escalate
    module: str
    goal: str  # what this step must achieve, for the narrator
    text: str | None = None  # the catalogue's words for this device
    awaits: str | None = None  # the fact this step is waiting for
    tool: str | None = None  # an engine action / a verification probe
    args: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = field(default_factory=tuple)  # what proves it worked
    note: str | None = None  # what the ticket must say (escalate)


def plan_step(call: ModuleCall, *, model: str | None = None) -> StepPlan | None:
    """What this module call asks of the turn, worded for the caller's equipment."""
    spec = catalog.module(call.module)
    if spec is None:  # pragma: no cover - startup validation refuses unknown modules
        return None
    args = _with_defaults(spec, call)
    device_type = str(args.get("device") or args.get("to") or "router")
    device = for_device(device_type, model)
    return StepPlan(
        kind=spec.kind,
        module=call.module,
        goal=spec.goal.format(**{"device": device_type, **args}),
        text=_words(spec, args, device),
        awaits=_awaits(spec, args, device),
        tool=spec.tool or (spec.probe if spec.kind == "verify" else None),
        args=args,
        evidence=tuple(args.get("evidence") or []),
        note=args.get("note"),
    )


def _with_defaults(spec: ModuleSpec, call: ModuleCall) -> dict[str, Any]:
    """The call's arguments, with what the module declares as its default — `reboot`
    without a method means from the power lead, and every card gets that for free."""
    defaults = {
        name: rules.default for name, rules in spec.params.items() if rules.default is not None
    }
    return {**defaults, **call.args}


def _words(spec: ModuleSpec, args: dict[str, Any], device) -> str | None:
    """The catalogue's sentence for this device, or None when it does not describe it —
    and then the agent does not offer it (no inventing where a button is).

    A `guide` step is the exception: its words are a knowledge document's own step, so the
    equipment catalogue has nothing to say about it (wave 4b).
    """
    if spec.module == "guide":
        return _guide_step(args)
    if device is None:
        return None
    if spec.module == "check_lights":
        return device.light_question(str(args.get("light") or "internet"))
    action = _action_key(spec, args)
    if action is None and spec.module == "device_check":
        action = f"device_check.{args.get('what', 'wifi')}"
    if action:
        return device.how_to(action)
    if spec.module == "reach":
        return maybe_phrase(device.locate_key)
    return None


def _guide_written(args: dict[str, Any]) -> list[str]:
    """The ACTIONS this call walks: the document's steps, cut to what the card says is the
    caller's, and split into one action per turn.

    A written step holds several numbered points, and live (2026-09-30) only the first of
    three was ever spoken: the caller never heard the address or the password, and the model
    filled the gap with an address the document does not give. One point, one turn.
    """
    from .knowledge_base import parts

    count = args.get("count")
    return parts(str(args.get("knowledge") or ""), limit=int(count) if count else None)


def _guide_step(args: dict[str, Any]) -> str | None:
    """The written procedure's step this turn is on — or None when it has none left."""
    written = _guide_written(args)
    at = int(args.get("at") or 0)
    return written[at] if 0 <= at < len(written) else None


def guide_length(call: ModuleCall) -> int:
    """How many steps this guide call walks."""
    return len(_guide_written(_with_defaults(catalog.module("guide"), call)))


def _action_key(spec: ModuleSpec, args: dict[str, Any]) -> str | None:
    """`reboot(method=power)` -> "reboot.power", the key the catalogue describes."""
    if spec.module == "reboot":
        # `reason` — kodėl kartojam. Katalogas tam turi savo sakinį, ir klientas išgirsta
        # PRIEŽASTĪ, o ne tą pačią instrukciją dar kartą (G5, gyvai 2026-09-28).
        reason = args.get("reason")
        method = args.get("method", "power")
        return f"reboot.{method}.{reason}" if reason else f"reboot.{method}"
    if spec.module == "cable":
        return f"cable.{args.get('action', 'reseat')}"
    if spec.module == "device_check":
        return f"device_check.{args.get('what', 'wifi')}"
    if spec.module == "connect_direct":
        return "connect_direct"
    if spec.module == "plug_power":
        return "power.plug"
    return None


# The fact a module gets from the CALLER, where that differs from what the module produces.
# `check_lights` produces `wan_link` (what the light MEANS, from the equipment catalogue), but
# telemetry owns that name and refuses the caller's word for it — so the step could never be
# settled by an answer, only by a reading. What the caller actually gives is `lights`, and
# that is what the step waits for (wave 6, live 2026-09-30).
CLIENT_FACT = {"check_lights": "lights"}


# Skaitytuvo etiketė nėra fakto reikšmė. `detect_lights` sako „no" / „yes" / spalvą, o
# kortelės `needs.lights` kalba reikšmėmis off / on / blinking — gyvai 2026-10-01 tas pats
# atsakymas užrašė iš pradžių `lights=off` (per `evidence.py`), o paskui `lights=no`, ir
# kortelės `values: {off: confirms, on: rules_out}` nebeturėjo ką pasakyti. Spalva reiškia, kad
# lemputė DEGA — ką ta spalva reiškia linijai, pasako įrangos katalogas (`wan_link`).
# {faktas: ({etiketė: reikšmė}, reikšmė visoms kitoms etiketėms)}
CLIENT_FACT_VALUES = {"lights": ({"no": "off", "blinking": "blinking"}, "on")}


def client_fact(call: ModuleCall, text: str | None) -> tuple[str, str] | None:
    """The CALLER-owned fact their answer establishes for this module, if it has one."""
    name = CLIENT_FACT.get(call.module)
    if not name or not text:
        return None
    label = _detect(name, text)
    if not label:
        return None
    stated = CLIENT_FACT_VALUES.get(name)
    if stated is None:
        return name, label
    mapping, otherwise = stated
    return name, mapping.get(label, otherwise)


def _awaits(spec: ModuleSpec, args: dict[str, Any], device) -> str | None:
    """The fact this step is waiting for: what the caller must tell us, or the first fact
    the module produces."""
    if spec.module in CLIENT_FACT:
        return CLIENT_FACT[spec.module]
    if spec.kind == "ask":
        return spec.produces[0] if spec.produces else None
    if spec.kind == "verify" and args.get("ask") and not args.get("evidence"):
        # Nothing on the line can tell us whether a phone's Wi-Fi works: that verification is
        # the caller's word, so the step waits for the fact their answer establishes.
        stated = next(iter(spec.answers.values()), None)
        return stated.split("=", 1)[0] if stated else None
    return None


def can_offer(call: ModuleCall, *, model: str | None = None) -> bool:
    """Does the catalogue describe this action for this device? An instruction we cannot
    word for what the caller owns is skipped, not improvised."""
    spec = catalog.module(call.module)
    if spec is None or spec.kind != "instruct":
        return True
    plan = plan_step(call, model=model)
    return bool(plan and plan.text)


def question_of(call: ModuleCall, *, model: str | None = None) -> str | None:
    """The module's question for THIS device.

    Lithuanian inflects the device ("prie routerio", "prie priedėlio"), so the catalogue's
    own wording wins when it has one and the module's generic phrase is the fallback.
    """
    spec = catalog.module(call.module)
    if spec is None:
        return None
    args = _with_defaults(spec, call)
    device = for_device(str(args.get("device") or args.get("to") or "router"), model)
    if spec.module == "check_lights":
        return device.light_question(str(args.get("light") or "internet")) if device else None
    specific = device.how_to(spec.module) if device else None
    return specific or maybe_phrase(spec.ask) or maybe_phrase(spec.announce)


def read_answer(call: ModuleCall, text: str | None, *, device=None) -> tuple[str, str] | None:
    """What the caller's answer to THIS module means, as ("fact", "value").

    A module declares its reader (`detector`) and what each label means, so the generic
    policies read their own answers — the S6 probe hung for three turns because `reach`
    had no reader and nothing could settle `reachable`.
    """
    spec = catalog.module(call.module)
    if spec is None or not spec.detector or not text:
        return None
    label = _detect(spec.detector, text)
    if label is None:
        return None
    return answer_from_label(call, label, device=device)


def answer_from_label(call: ModuleCall, label: str, *, device=None) -> tuple[str, str] | None:
    """Ką šio modulio atsakymo ETIKETĖ reiškia faktais, kaip ("fact", "value").

    Atskirta nuo `read_answer`, nes etiketę gali atnešti ne tik žodynas: tą patį sakinį to
    paties ėjimo supratimo kvietimas perskaito ŽINODAMAS klausimą (7 banga), ir jo etiketė
    turi virsti faktu lygiai taip pat — vertimas yra modulio, ne skaitytuvo dalykas.
    """
    spec = catalog.module(call.module)
    if spec is None or not label:
        return None
    if spec.module == "check_lights" and device is not None:
        light = str(_with_defaults(spec, call).get("light") or "internet")
        return device.fact_from_light(light, label)
    stated = spec.answers.get(label)
    if not stated or "=" not in stated:
        return None
    fact, value = stated.split("=", 1)
    return fact, value


def label_from(detector: str | None, text: str | None) -> str | None:
    """Šio skaitytuvo etiketė šiam sakiniui, arba None. Viešas `_detect` vardas: tą pačią
    etiketę skaito ir perception greitasis kelias (L1), ne tik modulio atsakymas."""
    if not detector or not text:
        return None
    return _detect(detector, text)


def _detect(detector: str, text: str) -> str | None:
    """Run one of the deterministic readers (perceive/detectors.py) and return its label."""
    from .perceive import detectors

    reader = getattr(detectors, f"detect_{detector}", None)
    if reader is None:  # pragma: no cover - startup validation names the readers
        return None
    outcome = reader(text)
    if outcome is None:
        return None
    return str(getattr(outcome, "value", outcome)).lower()


def step_done(call: ModuleCall, facts: dict[str, str]) -> bool | None:
    """Is this step finished? True / False for a verification with evidence, None while we
    are still waiting (a verification with only the caller's word is settled by the engine
    from their answer, not from here)."""
    spec = catalog.module(call.module)
    if spec is None:  # pragma: no cover
        return None
    conditions = [Condition.parse(t) for t in (call.args.get("evidence") or [])]
    if not conditions:
        return None
    holds = [c.holds(facts) for c in conditions]
    if any(h is False for h in holds):
        return False
    return True if all(h is True for h in holds) else None
