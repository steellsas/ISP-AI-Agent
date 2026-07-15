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
            on={Outcome.YES: "bind_mac", Outcome.NO: "cable_check"},
        ),
        # Cable check — walked step by step, ONE instruction per turn (INSTRUCT steps
        # advance on any caller reply). A LAN mis-plug makes the router a switch and
        # the line shows a jumping MAC, so fix the cable BEFORE binding.
        Step(
            id="cable_check",
            kind=StepKind.CONFIRM,
            detector="port",
            tools=frozenset(),
            rag_section=1,  # "### Žingsnis 2a: Į kokį lizdą įkištas kabelis"
            hint=(
                "The caller changed nothing, so the foreign/jumping MAC is usually a "
                "mis-plugged cable. Ask ONE thing and WAIT: which port is the incoming "
                "line cable in — the router's blue WAN (internet) port, or a yellow LAN "
                "port? Do NOT assume or conclude 'teisingas lizdas' until they clearly "
                "say a colour; if unclear, ask again. Do not explain more this turn."
            ),
            on={"wan": "bind_mac", "lan": "cable_reconnect"},
        ),
        Step(
            id="cable_reconnect",
            kind=StepKind.INSTRUCT,
            tools=frozenset(),
            rag_section=2,  # "### Žingsnis 2b: Perjungti į WAN"
            hint=(
                "The cable is in the wrong (yellow LAN) port. Give ONE instruction and "
                "wait: unplug it and plug it into the blue WAN port, and say when done. "
                "Do NOT suggest rebooting — it changes nothing if the cable is misplugged."
            ),
        ),
        Step(
            id="bind_mac",
            kind=StepKind.ACTION,
            tools=frozenset({"update_mac"}),  # only NOW is binding exposed to the model
            tool_actions=("update_mac",),  # engine chains reset_port + re-diagnose silently
            rag_section=3,  # "### Žingsnis 3: Pririšti įrenginį"
            hint=(
                "The engine binds the device silently — you do NOT call the tool. "
                "Announce it naturally: 'Dabar pririšiu jūsų naujai matomą įrenginį — "
                "turėtų atsirasti internetas. Palaukite akimirką.' Do NOT ask yet "
                "whether it works — that is the next step."
            ),
        ),
        Step(
            id="confirm_restored",
            kind=StepKind.CONFIRM,
            tools=frozenset(),
            rag_section=4,  # "### Žingsnis 4: Patikrinti, ar internetas atsirado"
            hint=(
                "The device is ALREADY bound. ASK whether the internet is back now "
                "('ar internetas jau atsirado?') and wait. Do NOT say you 'will' bind, "
                "do NOT say it is 'not yet bound', do NOT re-explain that another device "
                "is on the line — that is done. Do NOT declare it fixed yourself. If not "
                "yet, reassure it may take a minute or two and ask them to check again."
            ),
        ),
        Step(
            id="client_side",
            kind=StepKind.CONFIRM,
            detector="restored",  # "veikia/neveikia" answer, not keičiau/nekeičiau
            tools=frozenset(),
            rag_section=5,  # "### Žingsnis 5: Kliento pusės gedimas"
            hint=(
                "The provider side is restored (telemetry OK) but the caller still has "
                "no internet, so the fault is INSIDE their home — Wi-Fi off, device "
                "settings, or the cable to the device. Guide ONE simple client-side "
                "check (restart the device, check Wi-Fi is on, try a cable straight "
                "into the device) and ask if it works now. If yes -> resolved; if not "
                "-> register the fault."
            ),
            on={Outcome.YES: "resolve", Outcome.NO: "escalate"},
        ),
        Step(
            id="escalate",
            kind=StepKind.ESCALATE,
            tools=frozenset({"create_ticket"}),
            hint=(
                "Binding did not restore the line (or the in-home checks did not help). "
                "Register the fault for a technician check ('gedimo registracija') — a "
                "worker will call the next business day."
            ),
        ),
    ),
)

# B7 — line healthy up to the router, but the caller has no usable internet: the
# fault is INSIDE the home and telemetry is BLIND to it, so verification is the
# caller's word only. Only simple self-service actions (reboot, Wi-Fi checks, cable
# reseat); anything deeper is registered, not taught. Device-aware: a phone/tablet
# is Wi-Fi only, so the cable branch is reachable ONLY via "computer -> wired".
_CLIENT_SIDE = Strategy(
    verdict="healthy_to_router",
    rag_doc="troubleshooting/kliento_puse_internetas",
    steps=(
        Step(
            id="cs_scope",
            kind=StepKind.CONFIRM,
            detector="scope",
            rag_section=0,  # "### Žingsnis 1: Masto nustatymas"
            hint=(
                "Ask ONE short question and WAIT: does it fail on all devices or just "
                "one? Do NOT reflect or guess their answer — never say 'girdžiu, "
                "visuose' or 'telefone' until THEY said it. If you did not clearly hear "
                "the answer, say 'Atsiprašau, neišgirdau' and ask the same again."
            ),
            on={"all": "cs_reboot", "phone": "cs_wifi", "computer": "cs_conn"},
        ),
        Step(
            id="cs_reboot",
            kind=StepKind.INSTRUCT,
            rag_section=1,  # "### Žingsnis 2: Perkrauti routerį"
            goto="cs_verify_all",
            hint=(
                "All devices are down -> the cheapest, highest-yield fix first: ask "
                "them to reboot the router (unplug from the socket 10 seconds, plug "
                "back in, wait for the lights) and to tell you when it is back. ONE "
                "instruction."
            ),
        ),
        Step(
            id="cs_verify_all",
            kind=StepKind.CONFIRM,
            detector="restored",
            rag_section=2,  # "### Žingsnis 3: Patikrinti po perkrovimo"
            hint=(
                "Ask whether the internet works now. If yes -> resolved. If not, it is "
                "beyond simple self-service (router/DNS/config) -> register the fault."
            ),
            on={"yes": "resolve", "no": "escalate"},
        ),
        Step(
            id="cs_conn",
            kind=StepKind.CONFIRM,
            detector="conn",
            rag_section=3,  # "### Žingsnis 4: Kompiuteris — laidu ar WiFi"
            hint=(
                "Only ONE computer is affected. Ask whether that computer connects by "
                "cable or by Wi-Fi. Wait."
            ),
            on={"wired": "cs_cable", "wifi": "cs_wifi"},
        ),
        Step(
            id="cs_cable",
            kind=StepKind.INSTRUCT,
            rag_section=4,  # "### Žingsnis 5: Patikrinti laidą"
            goto="cs_verify_dev",
            hint=(
                "Wired computer: ask them to check the cable between router and "
                "computer — pushed in fully (a click), not damaged — and reseat it. "
                "Tell you when done. ONE instruction. (Do NOT mention cables for a "
                "phone/tablet — that branch never reaches here.)"
            ),
        ),
        Step(
            id="cs_wifi",
            kind=StepKind.INSTRUCT,
            rag_section=5,  # "### Žingsnis 6: WiFi patikra"
            goto="cs_wifi2",
            hint=(
                "Wi-Fi device (phone/tablet/laptop): ask them to check Wi-Fi is ON and "
                "that they are connected to THEIR OWN network (not a neighbour's). ONE "
                "thing, wait."
            ),
        ),
        Step(
            id="cs_wifi2",
            kind=StepKind.INSTRUCT,
            rag_section=6,  # "### Žingsnis 7: Perjungti WiFi / perkrauti įrenginį"
            goto="cs_verify_dev",
            hint=(
                "Next Wi-Fi step: ask them to 'forget' the network and reconnect with "
                "the password (watch upper/lowercase), then restart the device. Tell "
                "you when done. ONE instruction."
            ),
        ),
        Step(
            id="cs_verify_dev",
            kind=StepKind.CONFIRM,
            detector="restored",
            rag_section=7,  # "### Žingsnis 8: Patikrinti įrenginį"
            hint=(
                "Ask whether it works now on that device. Yes -> resolved. No -> it is "
                "beyond simple help (device settings/drivers) -> register the fault."
            ),
            on={"yes": "resolve", "no": "escalate"},
        ),
        Step(
            id="escalate",
            kind=StepKind.ESCALATE,
            tools=frozenset({"create_ticket"}),
            hint=(
                "The simple self-service steps did not help — the fault is deeper "
                "(router/DNS/config/device). Register it ('gedimo registracija'); a "
                "worker will call the next business day."
            ),
        ),
    ),
)

STRATEGIES: dict[str, Strategy] = {
    "foreign_mac": _FOREIGN_MAC,
    "healthy_to_router": _CLIENT_SIDE,
}

# Verdicts whose fix is a straight, branch-free, action-free sequence: give them a
# RAG doc here and the engine builds a linear guided walk (N INSTRUCT steps from the
# doc -> caller verify -> resolve/escalate) with NO bespoke strategy code. Empty for
# now; adding an entry + a RAG doc is all a new simple linear fault needs.
LINEAR_DOCS: dict[str, str] = {}


def build_linear_strategy(verdict: str, rag_doc: str, n_steps: int) -> Strategy:
    """A purely LINEAR guided strategy: n_steps INSTRUCT steps (one per RAG section,
    walked in order) then a caller-verified check -> resolve / escalate. Telemetry is
    not consulted (these are client-side self-service fixes). Pure — the caller reads
    n_steps from the doc (playbook.step_count) and passes it in."""
    steps: list[Step] = [
        Step(id=f"step_{i + 1}", kind=StepKind.INSTRUCT, rag_section=i) for i in range(n_steps)
    ]
    steps.append(
        Step(
            id="verify",
            kind=StepKind.CONFIRM,
            detector="restored",
            hint="Ask whether it works now. Yes -> resolved; no -> register the fault.",
            on={"yes": "resolve", "no": "escalate"},
        )
    )
    steps.append(Step(id="escalate", kind=StepKind.ESCALATE, tools=frozenset({"create_ticket"})))
    return Strategy(verdict=verdict, rag_doc=rag_doc, steps=tuple(steps))


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
    "nekeč",  # STT drop of the 'i' -> "nekečiau" (must beat the "keč" positive)
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
    "keč",  # STT drop of the 'i' in "keičiau" -> "kečiau"
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
    "keč",  # STT drop of the 'i' in "keičiau" -> "kečiau"
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
    "router",  # a bare "routerį/routerė" answer to "did you change the router?" = yes
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


# "Is the internet back?" answers use DIFFERENT vocabulary than the device-change
# confirm (veikia/atsirado vs keičiau) — so confirm_restored needs its own reader.
# Negatives are tested first because "neveikia" contains "veik".
_RESTORED_NO = (
    "neveik",
    "nevyk",  # STT garble of "neveikia"
    "neatsirad",
    "vis dar ne",
    "vis tiek ne",
    "dar ne",
    "nėra internet",
    "nesat",
)
_RESTORED_YES = (
    "veikia",
    "atsirad",  # atsirado internetas
    "atsistat",  # ryšys atsistatė
    "prisijung",
    "jau yra",
    "yra internet",
    "dirba",
    "atgal",
)


def detect_restored(text: str | None) -> Outcome | None:
    """YES (internet is back) / NO (still down) / None, for the confirm_restored
    step. Separate from detect_yes_no because the vocabulary differs and 'neveikia'
    must read as NO even though it contains 'veik'."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _RESTORED_NO):
        return Outcome.NO
    if re.search(r"\bne\b", low) or low.strip() in ("ne", "ne."):
        return Outcome.NO
    if any(m in low for m in _RESTORED_YES):
        return Outcome.YES
    return None


# --- Client-side branch detectors (healthy_to_router) ------------------------
# "all devices or one?" — and, when one, WHICH device, because a phone/tablet can
# only be Wi-Fi (never suggest a cable to it).
_ONE_PHONE = ("telefon", "planšet", "planset", "mobil", "išmanij", "ismanij", "tv", "televizor")
_ONE_COMPUTER = ("kompiuter", "kompas", "nešiojam", "nesiojam", "laptop", "stacionar")
_ONE_MARK = ("tik ", "viename", "vienam", "vien ", "tik vien")
_ALL_MARK = ("visuose", "visur", "visuos", "visi ", "visų", "nei viename", "niekur")


def detect_scope(text: str | None) -> str | None:
    """Route the "all devices or one?" question. Returns 'all', 'phone' (a Wi-Fi-only
    device — phone/tablet/TV), 'computer', or None if unclear. A named single device
    implies scope=one, so we key off the device word first."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _ONE_PHONE):
        return "phone"
    if any(m in low for m in _ONE_COMPUTER):
        return "computer"
    if any(m in low for m in _ALL_MARK):
        return "all"
    if any(m in low for m in _ONE_MARK):
        return "computer"  # "tik viename" without a named device -> ask conn (computer path)
    return None


_CONN_WIRED = ("laid", "kabel", "eternet", "ethernet", "lan")
_CONN_WIFI = ("wifi", "wi-fi", "vaifa", "vaifai", "belaid", "bevielis", "bevielis")


def detect_conn(text: str | None) -> str | None:
    """Route "wired or Wi-Fi?". Returns 'wired', 'wifi', or None. Wi-Fi is tested
    FIRST because "belaidis" (wireless) contains "laid"."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _CONN_WIFI):
        return "wifi"
    if any(m in low for m in _CONN_WIRED):
        return "wired"
    return None


_PORT_WAN = ("mėlyn", "melyn", "wan", "interneto lizd")
_PORT_LAN = ("gelton", "lan lizd", "kitą", "kita spalv")


def detect_port(text: str | None) -> str | None:
    """Route the WAN cable question. 'wan' (blue/internet port — correct) / 'lan'
    (yellow/other — must move) / None if unclear (stay and re-ask, do NOT assume)."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _PORT_LAN):
        return "lan"
    if any(m in low for m in _PORT_WAN):
        return "wan"
    return None


def _yn(text: str | None) -> str | None:
    o = detect_yes_no(text)
    return o.value if o else None


def _restored(text: str | None) -> str | None:
    o = detect_restored(text)
    return o.value if o else None


# Named detectors a CONFIRM step selects with Step.detector. Each maps the caller's
# reply to a routing KEY (or None = unclear, stay and re-ask).
DETECTORS = {
    "yes_no": _yn,
    "restored": _restored,
    "scope": detect_scope,
    "conn": detect_conn,
    "port": detect_port,
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
