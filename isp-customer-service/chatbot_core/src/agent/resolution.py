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
    # ESCALATE only: ask the caller's consent before registering (default). False =
    # the registration is a NECESSITY, not an offer (e.g. dr_register_router after a
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
                "provider cable in — the Internet/WAN port (usually separate, labelled "
                "'Internet' or 'WAN'), or another (LAN) port? Ask by port FUNCTION, not "
                "colour. Do NOT conclude 'teisingas lizdas' until they clearly say WAN "
                "or LAN; if unclear, ask again — do not rush."
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
                "whether it works — that is the next step. (The anamnesis question was "
                "already asked at the START of the call — do not repeat it here.)"
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
            tools=frozenset(),  # engine registers the ticket (Phase 3.11 B), not the model
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
        # Scope split (Phase 3.11, universality): callers answer in ANY order — "visuose",
        # "tik viename" (device unnamed), or straight "telefone neveikia". Each gets its
        # OWN route, so the classifier never has to guess a device from "tik viename"
        # (observed: it guessed "computer" and the agent asked a phone user about cables).
        Step(
            id="cs_scope",
            kind=StepKind.CONFIRM,
            detector="scope",
            rag_section=0,  # "### Žingsnis 1: Masto nustatymas"
            hint=(
                "Ask ONE short question and WAIT: does it fail on all devices or just "
                "one? Do NOT reflect or guess their answer — never say 'girdžiu, "
                "visuose' or 'telefone' until THEY said it. If the answer was unclear, "
                "ask the same again."
            ),
            on={
                "all": "cs_reboot",
                "one": "cs_which",  # said ONE but did not name it -> ask which
                "phone": "cs_cross_phone",  # named the device outright -> cross-check scope
                "computer": "cs_cross_computer",
            },
        ),
        Step(
            id="cs_which",
            kind=StepKind.CONFIRM,
            detector="scope",
            rag_section=0,
            hint=(
                "They said only ONE device is down but did not name it. Ask WHICH device "
                "('Kuriame įrenginyje — telefone, kompiuteryje?') and WAIT. Never assume."
            ),
            on={"phone": "cs_wifi", "computer": "cs_conn"},
        ),
        # The caller NAMED a device before the scope was known ("telefone nėra
        # interneto"). Cross-check whether the others work — if everything is down it is
        # the router path, not a device-specific one.
        Step(
            id="cs_cross_phone",
            kind=StepKind.CONFIRM,
            detector="restored",
            rag_section=0,
            hint=(
                "They said the PHONE has no internet. Cross-check ONE thing: do the "
                "other home devices have internet? If others work -> the fault is on the "
                "phone; if others are down too -> whole-home path."
            ),
            on={"yes": "cs_wifi", "no": "cs_reboot"},
        ),
        Step(
            id="cs_cross_computer",
            kind=StepKind.CONFIRM,
            detector="restored",
            rag_section=0,
            hint=(
                "They said the COMPUTER has no internet. Cross-check ONE thing: do the "
                "other home devices have internet? If others work -> the fault is on the "
                "computer; if others are down too -> whole-home path."
            ),
            on={"yes": "cs_conn", "no": "cs_reboot"},
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
            tools=frozenset(),  # engine registers the ticket (Phase 3.11 B), not the model
            hint=(
                "The simple self-service steps did not help — the fault is deeper "
                "(router/DNS/config/device). Register it ('gedimo registracija'); a "
                "worker will call the next business day."
            ),
        ),
    ),
)

# B6 — the line is healthy but NO device is seen on it: the router is off, unplugged
# or dead. Try power/cables first (cheapest), and if the router is really dead offer
# the BRIDGE: the incoming cable straight into a computer + bind its MAC = temporary
# internet on that one machine until they get a new router. A phone/tablet cannot take
# a cable, so no computer -> register.
_DEAD_ROUTER = Strategy(
    verdict="no_mac_observed",
    rag_doc="troubleshooting/internet_mires_routeris_tiltas",
    steps=(
        Step(
            id="dr_intro",
            kind=StepKind.CONFIRM,
            detector="yes_no",
            rag_section=0,  # "### Žingsnis 0: Paaiškinti, ką matome"
            hint=(
                "Do NOT start ordering them about. First explain what YOU can see and "
                "what it likely means — the internet reaches the flat but the line does "
                "not see their device, so it is usually no power, an unplugged cable, or "
                "a dead router — and ASK whether it suits them to check it together now. "
                "Wait for their answer. If they cannot (not home, busy), do not push: "
                "offer to register the fault or to call back."
            ),
            on={"yes": "dr_lights", "no": "escalate"},
        ),
        Step(
            id="dr_lights",
            kind=StepKind.CONFIRM,
            detector="lights",
            rag_section=1,  # "### Žingsnis 1: Nuvesti prie routerio"
            hint=(
                "They agreed. First take them TO the device, then ask ONE thing: ask "
                "them to find the router (the box the internet cable goes into) and, "
                "once there, whether ANY light is lit. Do not guess the answer."
            ),
            on={"yes": "dr_cable", "no": "dr_power"},
        ),
        Step(
            id="dr_power",
            kind=StepKind.CONFIRM,
            detector="lights",
            rag_section=2,  # "### Žingsnis 2: Maitinimas ir kabelis"
            hint=(
                "No lights at all. ONE instruction, then wait: check the power lead is "
                "firmly in the socket and in the router, try another socket — and ask "
                "whether any light came on now."
            ),
            on={"yes": "dr_cable", "no": "dr_offer_bridge"},
        ),
        Step(
            id="dr_cable",
            kind=StepKind.INSTRUCT,
            rag_section=2,
            goto="dr_recheck",
            hint=(
                "It has power but the line does not see it. ONE instruction, then wait: "
                "reseat the cable coming from the wall into the router's internet port "
                "and say when done."
            ),
        ),
        Step(
            id="dr_recheck",
            kind=StepKind.CONFIRM,
            detector="restored",
            rag_section=8,  # "### Žingsnis 6: Patikrinti, ar atsirado internetas"
            hint=(
                "Ask whether the internet is back now. If yes -> resolved. If not, the "
                "router is likely dead — move on to offering the temporary bridge."
            ),
            on={"yes": "resolve", "no": "dr_offer_bridge"},
        ),
        Step(
            id="dr_offer_bridge",
            kind=StepKind.CONFIRM,
            detector="have_device",
            rag_section=3,  # "### Žingsnis 3: Pasiūlyti laikiną tiltą"
            hint=(
                "The router looks dead. In ONE short sentence say so and ask whether "
                "they have a computer — you could run the internet through it for now. "
                "A COMPUTER IS ENOUGH: 'neturiu kito routerio, tik kompiuterį' is a YES. "
                "Never tell them internet is impossible while they have a computer. "
                "(A phone/tablet cannot take a cable.) 'I'll fetch it' is also a yes — "
                "wait, do not re-ask."
            ),
            on={"yes": "dr_pick_cable", "no": "escalate"},
        ),
        Step(
            id="dr_pick_cable",
            kind=StepKind.INSTRUCT,
            rag_section=4,  # "### Žingsnis 4a: Kurį kabelį imti"
            goto="dr_plug_pc",
            hint=(
                "Make sure they take the RIGHT cable — this is where people go wrong. "
                "ONE instruction, then wait: the cable that comes from the wall (the "
                "provider's) and is now in the router's internet port — ask them to "
                "unplug THAT one from the router and tell you when it is in their hand. "
                "Not the power lead, not a cable between the router and a device."
            ),
        ),
        Step(
            id="dr_plug_pc",
            kind=StepKind.INSTRUCT,
            rag_section=5,  # "### Žingsnis 4b: Įkišti į kompiuterį"
            goto="dr_see_device",
            hint=(
                "ONE instruction, then wait: plug that cable into the COMPUTER's network "
                "socket (the one the same plug fits, on the back/side) until it clicks, "
                "and say when done. NEVER say to plug it back into the router — the whole "
                "point is bypassing the dead router. If they say it does not fit or they "
                "cannot find it, help with WHERE to look — do not move on."
            ),
        ),
        Step(
            id="dr_see_device",
            kind=StepKind.VERIFY,
            rag_section=6,  # "### Žingsnis 5: Ar matome įrenginį linijoje"
            hint=(
                "The engine re-reads the line to see whether the newly connected device "
                "actually shows up. If it does NOT, the cable is in the wrong socket or "
                "not seated — walk that back calmly, do not bind blindly."
            ),
        ),
        Step(
            id="dr_bind",
            kind=StepKind.ACTION,
            tools=frozenset({"update_mac"}),
            tool_actions=("update_mac",),
            rag_section=7,  # "### Žingsnis 6: Pririšti kompiuterį"
            hint=(
                "We can now SEE their computer on the line. The engine binds it silently "
                "— you do NOT call the tool. Announce it: 'Matau jūsų kompiuterį "
                "linijoje. Dabar pririšiu jį prie tinklo — turėtų atsirasti internetas. "
                "Palaukite akimirką.' Do not ask yet if it works."
            ),
        ),
        Step(
            id="dr_verify",
            kind=StepKind.CONFIRM,
            detector="restored",
            rag_section=8,  # "### Žingsnis 7: Patikrinti, ar atsirado internetas"
            hint=(
                "Ask whether the internet is now up on that computer. If yes: say "
                "plainly that this is TEMPORARY (that one computer only), that the "
                "router is dead and needs replacing, and go register the fault for it. "
                "If no -> register too. Either way the caller leaves with a registration."
            ),
            on={"yes": "dr_register_router", "no": "escalate"},
        ),
        Step(
            id="dr_register_router",
            kind=StepKind.ESCALATE,
            tools=frozenset(),  # engine registers the ticket (Phase 3.11 B), not the model
            consent=False,  # a necessity, not an offer — the engine registers on arrival
            hint=(
                "The bridge works, but their router is dead. The ENGINE has ALREADY "
                "registered the fault — ANNOUNCE it, do not ask permission: "
                "'Užregistravau gedimą dėl sugedusio routerio — kolegos susisieks ir "
                "detaliau paaiškins.' Add that the internet works on this computer for "
                "now, and once they have a new router they should call so we bind it."
            ),
        ),
        Step(
            id="escalate",
            kind=StepKind.ESCALATE,
            tools=frozenset(),  # engine registers the ticket (Phase 3.11 B), not the model
            hint=(
                "The bridge is not possible (no computer / cannot connect) or it did not "
                "help. Register the fault ('gedimo registracija') and explain they will "
                "likely need a new router; a worker calls the next business day."
            ),
        ),
    ),
)

STRATEGIES: dict[str, Strategy] = {
    "foreign_mac": _FOREIGN_MAC,
    "healthy_to_router": _CLIENT_SIDE,
    "no_mac_observed": _DEAD_ROUTER,
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
    # Engine registers the ticket (Phase 3.11 B), not the model — no tool exposed.
    steps.append(Step(id="escalate", kind=StepKind.ESCALATE, tools=frozenset()))
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
    "taip",  # the plain answer to "ar internetas atsirado?" — was missing, so a
    "aha",  # confirmed fix looked unanswered and ended in a needless ticket
    "jo",
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
_WIRELESS_ONLY = ("telefon", "planšet", "planset", "mobil", "išmanij", "ismanij")
# Devices that answer "one device, and it is wireless". "tv" needs a word boundary
# (see _TV_RE) or it fires inside words like "tvarkinga".
_ONE_PHONE = (*_WIRELESS_ONLY, "televizor")
_TV_RE = re.compile(r"\btv\b")
_ONE_COMPUTER = ("kompiuter", "kompas", "nešiojam", "nesiojam", "laptop", "stacionar")
_ONE_MARK = ("tik ", "viename", "vienam", "vien ", "tik vien")
_ALL_MARK = ("visuose", "visur", "visuos", "visi ", "visų", "nei viename", "niekur")
# "one device, unnamed" — routes to the WHICH-device step (cs_which), never a guess.
_ONE_MARK = ("viename", "vienam", "tik vien", "viena")


def detect_scope(text: str | None) -> str | None:
    """Route the "all devices or one?" question. Returns 'all', 'phone' (a Wi-Fi-only
    device — phone/tablet/TV), 'computer', or None if unclear. A named single device
    implies scope=one, so we key off the device word first."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _ONE_PHONE) or _TV_RE.search(low):
        return "phone"
    if any(m in low for m in _ONE_COMPUTER):
        return "computer"
    if any(m in low for m in _ALL_MARK):
        return "all"
    # "tik viename" WITHOUT naming the device: scope answered, device not — route to
    # the WHICH-device step ('one'), never guess a device (guessing "computer" once
    # made the agent ask a phone user about cables). Checked AFTER _ALL_MARK so "nei
    # viename" (= none work = all down) is not misread as one.
    if any(m in low for m in _ONE_MARK):
        return "one"
    return None


_CONN_WIRED = ("laid", "kabel", "eternet", "ethernet", "lan")
_CONN_WIFI = ("wifi", "wi-fi", "wi fi", " wf", "vaifa", "vaifai", "belaid", "bevieli")


def detect_conn(text: str | None) -> str | None:
    """Route "wired or Wi-Fi?". Returns 'wired', 'wifi', or None. Wi-Fi is tested
    FIRST because "belaidis" (wireless) contains "laid". A phone/tablet can only be
    wireless, so naming one answers the question."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _CONN_WIFI) or any(m in low for m in _WIRELESS_ONLY):
        return "wifi"
    if any(m in low for m in _CONN_WIRED):
        return "wired"
    return None


# Route by PORT FUNCTION, not colour (a caller may not see colours; STT garbles
# "LAN lizdą" -> "laną lėsdą"). WAN/Internet port = correct; LAN/other = must move.
_PORT_LAN = ("lan", "laną", "lėsd", "kit", "antr", "treči", "eternet", "gelton")
_PORT_WAN = ("wan", "internet", "pirm", "atskir", "mėlyn", "melyn")


def detect_port(text: str | None) -> str | None:
    """Route the incoming-cable question. 'wan' (Internet/WAN port — correct) / 'lan'
    (LAN or another port — must move) / None if unclear (stay and re-ask, do NOT
    assume). LAN is tested first so an explicit 'LAN' wins."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _PORT_LAN):
        return "lan"
    if any(m in low for m in _PORT_WAN):
        return "wan"
    return None


# "Are any lights on?" — NO is tested first because "nedega" contains "dega".
# STT mangles these badly ("nedega" -> "nedaga"/"neusidaga"), and a stuck detector
# here made the agent repeat the same question six times. Keep the NO markers loose.
_LIGHTS_NO = (
    "nedega",
    "nedaga",
    "neusidaga",
    "neužsidega",
    "neuzsidega",
    "neišdegė",
    "neisdege",
    "nešviečia",
    "nesviecia",
    "nemirksi",
    "tamsu",
    "jokių",
    "jokia",
    "niekas",
    "vis tiek ne",
    "negyv",
)
_LIGHTS_YES = ("dega", "šviečia", "sviecia", "mirksi", "užsidegė", "uzsidege", "žalia", "raudona")


def detect_lights(text: str | None) -> str | None:
    """Route "is any light on the router lit?". 'yes' / 'no' / None if unclear."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _LIGHTS_NO) or re.search(r"\bne\b", low):
        return "no"
    if any(m in low for m in _LIGHTS_YES):
        return "yes"
    return None


_DEVICE_YES = (
    "turiu",
    "yra",
    "kompiuter",
    "nešiojam",
    "nesiojam",
    "router",
    "atsineš",
    "atsines",
    "pajung",
    "prijung",
)


_USABLE_DEVICE = ("kompiuter", "nešiojam", "nesiojam", "laptop", "router", "kompas")


def detect_have_device(text: str | None) -> str | None:
    """Route "do you have a computer / another router we could plug into?".

    Read CLAUSE BY CLAUSE: "neturiu kito routerio, aš tik kompiuterį turiu" is a YES —
    a computer is exactly what the bridge needs. Scanning the whole sentence for
    "neturiu" answered NO and told the caller nothing could be done, with a usable
    machine sitting right there."""
    if not text:
        return None
    low = text.lower()
    clauses = [c for c in re.split(r"[,;]| bet | tačiau ", low) if c.strip()]
    saw_device_clause = False
    for c in clauses:
        if not any(d in c for d in _USABLE_DEVICE):
            continue
        saw_device_clause = True
        if "neturiu" not in c and "nėra" not in c and not re.search(r"\bne\b", c):
            return "yes"  # a device named without being denied — that is enough
    if saw_device_clause:
        return "no"  # every device they mentioned was denied
    # No device named at all — fall back to a plain yes/no, denial first.
    if any(m in low for m in _NEG) or "neturiu" in low or re.search(r"\bne\b", low):
        return "no"
    if any(m in low for m in _DEVICE_YES) or any(m in low for m in _POS):
        return "yes"
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
    "lights": detect_lights,
    "have_device": detect_have_device,
}

# What each detector's routing keys MEAN, in plain Lithuanian. The keys are abstract
# (yes/no/all/phone…) so the LLM classifier cannot map a reply to them without knowing
# the meaning — passing these glosses is what lets it pick "no" for "nedega jokia
# lemputė" while refusing to force "yes" onto "susiradau routerį" (→ unclear, hold).
DETECTOR_GLOSSES: dict[str, dict[str, str]] = {
    "yes_no": {"yes": "sutinka / patvirtina / taip", "no": "atsisako / neigia / ne"},
    "lights": {
        "yes": "ant įrenginio dega bent viena lemputė",
        "no": "nedega jokia lemputė",
    },
    "restored": {
        "yes": "internetas dabar veikia / atsirado",
        "no": "internetas vis dar neveikia",
    },
    "scope": {
        "all": "sako, kad internetas neveikia VISUOSE įrenginiuose",
        "one": "sako, kad neveikia tik VIENAME įrenginyje, bet NEĮVARDIJA kuriame",
        "phone": "AIŠKIAI įvardija telefoną ar planšetę (pvz. 'telefone nėra interneto')",
        "computer": "AIŠKIAI įvardija kompiuterį ar nešiojamą",
    },
    "conn": {
        "wifi": "įrenginys jungiasi per WiFi (bevielį)",
        "wired": "įrenginys jungiasi laidu",
    },
    "port": {
        "wan": "kabelis įkištas į interneto (WAN) lizdą",
        "lan": "kabelis įkištas į kitą (LAN) lizdą",
    },
    "have_device": {
        "yes": "klientas turi kompiuterį arba kitą routerį",
        "no": "klientas neturi jokio kito įrenginio",
    },
}


_FAREWELL = (
    "viso gero",
    "viso labo",
    "geros dienos",
    "gero vakaro",
    "sudie",
    "ačiū, viskas",
    "tai viskas",
    "viskas ačiū",
    "daugiau ne",
    "nieko daugiau",
    "pakaks",
    "ne ačiū",
    "nebereikia",
    # NOTE: "iki" and "ate" are NOT in this substring list — they hide inside
    # "neveIKIa"/"ATEina"; detect_farewell checks them as whole words instead.
    # STT garbles of "viso gero / viso labo" heard in live calls — a farewell must
    # still close the call when whisper mangles the vowels.
    "visą gerą",
    "visa gera",
    "visą gera",
    "viso gera",
    "visai ger",  # "Ne visai gero" = garbled "ne, viso gero" (observed live)
)


_CONFUSED = (
    "nesuprantu",
    "nesupratau",
    "kas tai",
    "kas tas",
    "kas ta ",
    "ką reiškia",
    "ka reiskia",
    "nesigaudau",
    "nežinau kur",
    "nezinau kur",
    "nežinau kas",
    "neišmanau",
    "neismanau",
    "nemoku",
    "nesu tech",
    "paaiškinkite",
    "paaiskinkite",
)


# --- Turn intent -------------------------------------------------------------
# What KIND of turn the caller just took. Only ANSWER and DONE may advance a step;
# everything else holds the walker where it is. Without this every non-answer
# ("einu prie routerio", "nesuprantu", "o kiek kainuos?") collapsed into "repeat the
# question", and the agent ran ahead of the caller.
INTENT_ANSWER = "answer"  # a real answer to what we asked -> route it
INTENT_IN_PROGRESS = "in_progress"  # "einu / atsinešiu / tuoj" -> wait, do NOT check
INTENT_DONE = "done"  # "padariau / įkišau" -> the action completed
INTENT_QUESTION = "question"  # asking us something -> answer it, stay
INTENT_CONFUSED = "confused"  # does not follow -> explain finer, stay
INTENT_SILENCE = "silence"  # nothing usable -> wait, do not scold
INTENT_UNKNOWN = "unknown"  # safe default: hold and ask, never advance

_IN_PROGRESS = (
    "einu",
    "eisiu",
    "nueisiu",
    "atsineš",
    "atsines",
    "tuoj",
    "tuojau",
    "palauk",
    "sekundėl",
    "sekundel",
    "minutėl",
    "minutel",
    "bandau",
    "bandysiu",
    "darau",
    "darysiu",
    "žiūriu",
    "ziuriu",
    "ieškau",
    "iesk",
    "einam",
)
_DONE = (
    "padariau",
    "padaryta",
    "atlikau",
    "įkišau",
    "ikisau",
    "įjungiau",
    "ijungiau",
    "išjungiau",
    "isjungiau",
    "perkroviau",
    "perjungiau",
    "ištraukiau",
    "istraukiau",
    "prijungiau",
    "pajungiau",
    "jau",
    "gatava",
    "viskas",
)
_QUESTION = (
    "kiek",
    "kodėl",
    "kodel",
    "kada",
    "ar galima",
    "o kaip",
    "kur ",
    "kuris",
    "kokiu",
    "koks ",
    "kokia ",
)


def detect_turn_intent(text: str | None) -> str:
    """Classify the caller's turn before the walker routes it.

    Deterministic on purpose (same reasoning as the step detectors): the model
    phrases, the engine decides whether the conversation may move. Order matters —
    confusion and questions are checked before completion words, because "nesuprantu,
    ką padariau" is confusion, not a completed action."""
    if not text or not text.strip():
        return INTENT_SILENCE
    low = text.lower()
    if detect_confusion(low):
        return INTENT_CONFUSED
    if "?" in low or any(m in low for m in _QUESTION):
        return INTENT_QUESTION
    if any(m in low for m in _IN_PROGRESS):
        return INTENT_IN_PROGRESS
    if any(m in low for m in _DONE):
        return INTENT_DONE
    return INTENT_ANSWER


def detect_confusion(text: str | None) -> bool:
    """True when the caller signals they do not follow the technical wording ("kas tas
    WAN?", "nesuprantu", "neišmanau"). Raises the clarity level for the rest of the
    call so the agent explains in plain, visual words instead of repeating jargon."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in _CONFUSED)


# Ticket-registration consent (Phase 3.11 B): the ESCALATE step asks "užregistruosiu
# gedimą — ar tinka?" and the ENGINE registers on consent. Vocabulary differs from the
# device-change confirm (tinka/gerai/sutinku vs keičiau), so it needs its own reader.
_CONSENT_YES = (
    "taip",
    "tinka",
    "gerai",
    "sutinku",
    "sutariam",
    "sutinkam",
    "jo",
    "aha",
    "mhm",
    "registruok",
    "užregistruok",
    "uzregistruok",
    "darykit",
    "darykite",
    "lauksiu",  # "lauksiu skambučio" = expects the registration — consent, not decline
    "lauksim",
)
_CONSENT_NO = (
    "nenoriu",
    "nereikia",
    "atsisak",
    "neregistruok",
    "nedarykit",
    "ne ačiū",
    "ne aciu",
)


def detect_address_confirm(text: str | None) -> str | None:
    """Read the reply to an address OFFER ("Ar skambinate dėl X?") without trusting a
    bare leading "taip": 'yes' only when the confirmation is CLEAN, 'no' when they
    deny / name another address, None when mixed or garbled (-> re-ask, never commit).

    Live bug this guards: STT turned "ne, 60-7" into "Taip, nebija" — the model saw
    "Taip…" and committed the WRONG apartment. Problem words ("neveikia", "nėra
    interneto") are not denials; any OTHER "ne-" token alongside a "taip" is."""
    if not text or not text.strip():
        return None
    low = text.lower()
    if any(m in low for m in _ADDR_NO):
        return "no"
    ne_tokens = [
        t
        for t in re.findall(r"\bne\w*", low)
        # the PROBLEM being negated is not an address denial:
        if not t.startswith(
            ("neveik", "nevyk", "nėra", "nera", "netur", "nebeveik", "nebėr", "neber")
        )
    ]
    has_yes = any(
        m in low for m in ("taip", "tvirtinu", "to adreso", "dėl šio", "del sio", "aha", "jo")
    )
    if ne_tokens:
        return "no" if not has_yes else None  # mixed "taip…ne…" garble -> re-ask
    return "yes" if has_yes else None


_ADDR_NO = (
    "ne dėl",
    "ne del",
    "ne tas adres",
    "ne to adres",
    "ne tuo adres",
    "kitas adres",
    "kito adres",
    "kitu adres",
    "kitas butas",
    "kito buto",
    "kitam bute",
    "ne šit",
    "ne sit",
)


def detect_address_correction(text: str | None) -> bool:
    """True when an ALREADY-identified caller says they are calling about a different
    address ("tai ne dėl to adreso skambinu", "kitas butas") — the engine must reopen
    identification instead of carrying on about the wrong account (observed live)."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in _ADDR_NO)


# Refusal to troubleshoot / explicit demand for a registration. Either way the
# troubleshooting ENDS in a registration (policy 2026-07-30): a clear DEMAND registers
# immediately (the demand IS the consent); a softer refusal routes to the escalate
# step whose consent question doubles as the polite clarification.
_TICKET_DEMAND = (
    "registruok",
    "įregistruok",
    "iregistruok",
    "užregistruok",
    "uzregistruok",
    "iškviesk",
    "iskviesk",
    "kvieskit",
    "atsiųsk technik",
    "atsiusk technik",
    "tegul atvažiuoj",
    "tegul atvaziuoj",
    # Live 2026-08-13: "Išregistruoti meistrą…" (STT of "užregistruoti") and
    # "žegistruokit gedimą" both missed the imperative-only marks — the stem
    # covers registruoti/registruokite and the garbled ž-/iš- variants.
    "gistruok",
    "gistruot",
)
_TICKET_REFUSE = (
    "nedarysiu",
    "nedarysim",
    "nenoriu daryti",
    "nenoriu tikrinti",
    "nenoriu nieko",
    "neturiu laiko",
    "nesu namuose",
    "ne namuose",  # "nepatogu, ne namuose" (observed live — must offer registration)
    "nebūsiu nam",
    "nebusiu nam",
    "ne namie",
    "negaliu dabar",
    "nenam",  # STT garbles of "nedarysiu / ne namie" ("nenamosiu")
    # Live 2026-08-13: "Nebe noriu tikrinti toliau… nebesprendžiam" — the stop
    # words themselves were missing, so the demand path had to carry the turn.
    "nutrauk",
    "nebenoriu",
    "nebe noriu",
    "nebespren",
    "nebespręs",
    "nebespres",
)


def detect_refuse_or_ticket(text: str | None) -> str | None:
    """'demand' (register it, now) / 'refuse' (won't troubleshoot) / None.

    Polarity-aware for DEMAND marks (2026-08-13): "NEregistruokite" carries the
    'registruok' substring but is the OPPOSITE of a demand — a mark only counts
    when the word carrying it is not itself negated."""
    if not text:
        return None
    low = text.lower()
    for token in low.split():
        word = token.strip(".,!?…")
        if any(m in word for m in _TICKET_DEMAND) and not word.startswith(("ne", "nebe")):
            return "demand"
    if any(m in low for m in _TICKET_REFUSE):
        return "refuse"
    return None


# "netur" prefix covers neturiu/neturi/neturim(e) — live 2026-08-05 the caller
# said "Neturi kompiutera" (3rd person + garble) and "neturiu"/"netur " missed it.
_NO_DEVICE = (
    "netur",
    "nėra kompiuter",
    "nera kompiuter",
    "tik telefon",
    "vien telefon",
    "tik su telefon",
    "negaliu prijungti",
    "negaliu pasijungti",
)


_GREETING = ("laba", "labas", "sveiki", "labadien", "alio", "sveikas", "gera dien")


def is_greeting(text: str | None) -> bool:
    """A short greeting/small-talk opener with NO problem content ("Labadiena!").
    Live 2026-08-06: such a turn fell to the LLM, which jumped straight to the
    address offer BEFORE any problem was stated — the ladder then re-offered it
    and the caller got the same question twice."""
    if not text:
        return False
    low = text.lower()
    if len(low.split()) > 4:
        return False
    return any(m in low for m in _GREETING)


def detect_no_device(text: str | None) -> bool:
    """The caller has NO device to bridge through ("neturiu kompiuterio", "tik
    telefonas"). Meaningful only right after the bridge OFFER — the caller
    checks the question context. Discipline rule 2026-08-05: this answer routes
    to the TICKET deterministically; the thinker may not wander back to
    re-checks (observed live: 6x disambiguate after "Neturiu.", then a full
    walker rewind to dr_intro)."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in _NO_DEVICE)


_PLUGGED = (
    "įkišau",
    "ikisau",
    "prijungiau",
    "pajungiau",
    "įjungiau",
    "ijungiau",
    "sujungiau",
    # STT-tolerant stems (live 2026-08-11: "Jau pajungiu", "Pajangių kompiuterį"
    # were missed and the bridge instruction repeated 3×).
    "pajungi",
    "prijungi",
    "pajang",
)


def detect_plugged(text: str | None) -> bool:
    """True when the caller reports a COMPLETED plug-in ("įkišau į kompiuterį") — the
    discipline gate for a bind: the change runs only after the client actually did
    the work (and thereby agreed to it), never on the solver's anticipation.
    Diacritics-folded (STT drops nosinės); negation-prefix aware ("dar
    NEprijungiau" is not a report)."""
    if not text:
        return False
    from .evidence import _fold, _mark_hit

    low = _fold(text)
    return any(_mark_hit(low, m) for m in _PLUGGED)


def detect_ticket_consent(text: str | None) -> str | None:
    """'yes' / 'no' / None from the caller's reply to "užregistruosiu gedimą — ar
    tinka?". Denials win; a bare "ne" is a decline; anything unclear returns None so
    the step holds and re-asks instead of registering on a garble."""
    if not text:
        return None
    low = text.lower()
    if any(m in low for m in _CONSENT_NO):
        return "no"
    if re.search(r"\bne\b", low):
        return "no"
    if any(m in low for m in _CONSENT_YES):
        return "yes"
    return None


def detect_farewell(text: str | None) -> bool:
    """True when, after the case is closed, the caller signals they are done — a
    goodbye or a plain 'no' to 'anything else?'. Used to end the call so the agent
    does not loop goodbyes. A 'no' that carries a new question/topic does NOT count.
    The bare-"ne"/"viskas" fallback fires only on SHORT utterances (<=3 words): a long
    sentence containing "ne" is content, not a goodbye ("Ne, mano vardas Tomas, aš
    esu kaimynas" was read as a farewell and hung up on the caller — observed live)."""
    if not text:
        return False
    low = text.lower()
    words = [t.strip(".,!?…") for t in low.split()]
    tokens = set(words)

    # "Ačiū, nereikia" / "nebereikia" = polite done-signal (live 2026-08-13:
    # the thanks swallowed the refusal and the agent read it as gratitude).
    if "?" not in low and (
        "nebereikia" in tokens or ("nereikia" in tokens and ("ačiū" in tokens or "aciu" in tokens))
    ):
        return True

    # "iki"/"ate" must match as WHOLE WORDS — as substrings they hide inside
    # "neveIKIa" / "ATEina" and read a fault report as a goodbye (caught by tests
    # the moment farewell started being checked on every turn). And "iki" counts
    # ONLY standalone — as a PREPOSITION it is content, not a goodbye: "Pajungtas
    # IKI GALO" ended a live bridge in a ticket (2026-08-11), "iki 17 valandos"
    # is a ticket-hours answer, "Iki šau" is STT of "Įkišau". A goodbye "iki" is
    # the LAST word or leads a farewell phrase ("iki pasimatymo").
    def _standalone_goodbye(word: str) -> bool:
        for i, w in enumerate(words):
            if w != word:
                continue
            nxt = words[i + 1] if i + 1 < len(words) else None
            if nxt is None or nxt in ("pasimatymo", "viso", "gero", "ate", "iki"):
                return True
        return False

    if any(m in low for m in _FAREWELL):
        return True
    if (tokens & {"iki", "ate"}) and (_standalone_goodbye("iki") or _standalone_goodbye("ate")):
        return True
    has_followup = any(
        w in low
        for w in ("klausim", "dar ", "bet ", "problem", "taip", "tęs", "tes", "toliau", "nebaik")
    )
    short = len(low.split()) <= 3
    if not (short and not has_followup and bool(re.search(r"\bne\b", low) or "viskas" in low)):
        return False
    # The bare-"ne" fallback must be a PURE decline — every token a known
    # closing word. "Ne daganiai 1." (STT of "nedega nė viena") fast-forwarded
    # the ticket dialogue to done-with-defaults (observed live 2026-08-10):
    # unknown content words mean the caller is SAYING something, not leaving.
    _CLOSING = {"ne", "viskas", "ačiū", "aciu", "gerai", "jau", "tiek", "nieko", ""}
    return all(t in _CLOSING for t in tokens)


# Bare backchannels / one-letter STT crumbs — acknowledgement noises, NOT answers.
# Treating them as answers advanced steps through garbage (observed: "T." was read
# as "yes, I have a computer"; "Mhm." advanced two INSTRUCT steps).
_BACKCHANNEL = frozenset({"mhm", "aha", "m", "t", "hm", "mm", "nu", "na", "e", "a"})


def is_backchannel(text: str | None) -> bool:
    """True for a bare acknowledgement noise / one-letter crumb — hold, don't route."""
    if not text:
        return False
    tokens = [t.strip(".,!?…") for t in text.lower().split()]
    tokens = [t for t in tokens if t]
    return bool(tokens) and all(t in _BACKCHANNEL for t in tokens)


_NEGATION_TOKENS = {
    "ne",
    "nė",
    "nea",
    "nėra",
    "nera",
    "nežinau",
    "nezinau",
    "nematau",
    "nieko",
    "niekas",
}


_DONE_STEMS = ("patikrin", "padar", "atlik", "isband", "išband", "baig")
_DONE_ACKS = {"mhm", "aha", "gerai", "nu", "tai", "jo", "ok", "jau", "viskas", "as", "aš"}


def is_bare_done_report(text: str | None) -> bool:
    """A DONE-report without a result: "Mhm, patikrinau." says the caller DID
    the check but not WHAT they found. Live 2026-08-11 the understanding pass
    invented the missing value (power_cable=atjungtas — echoed from the agent's
    own explanation) and the hypothesis never confirmed. Such a turn earns an
    acknowledge-and-ask-what-you-found clarify, never an invented fact.
    "Patikrinau, laidas įkištas" carries content — not bare."""
    if not text:
        return False
    tokens = [t.strip(".,!?…") for t in text.lower().split()]
    tokens = [t for t in tokens if t and t not in _DONE_ACKS]
    if not tokens or len(tokens) > 3:
        return False
    return all(any(t.startswith(s) for s in _DONE_STEMS) for t in tokens)


def is_bare_negation(text: str | None) -> bool:
    """A short negation-only reply ("Ne.", "Ne, nežinau.") — a NO without an object.
    It says nothing about WHAT is denied: the pending check, the whole process, or
    a truncated "ne(dega)…" after a barge-in (live 2026-08-11: exactly that "Ne."
    was read as "won't check together" and killed the call with a cancelled
    ticket). Such a reply may answer a clarify question, never drive a destructive
    transition on its own."""
    if not text:
        return False
    tokens = [t.strip(".,!?…") for t in text.lower().split()]
    tokens = [t for t in tokens if t]
    if not tokens or len(tokens) > 3:
        return False
    return any(t in _NEGATION_TOKENS for t in tokens) and all(
        t in _NEGATION_TOKENS or len(t) <= 2 for t in tokens
    )


_QUESTION_TOKENS = {
    "kiek",
    "kodėl",
    "kodel",
    "kada",
    "kur",
    "kuris",
    "kuri",
    "koks",
    "kokia",
    "kokie",
    "kokiu",
    "kokią",
    "kokio",
    "kam",
    "kaip",
    "negi",
}


def is_real_question(text: str | None) -> bool:
    """A QUESTION by its words, not by punctuation — STT sticks '?' onto rising
    intonation ("Tomas?"), which is not the caller asking us something. Token
    based (2026-08-07): "Aš skola kokia." closed the call because the old
    substring list required "kokia " with a trailing space."""
    if not text:
        return False
    low = text.lower()
    if any(m in low for m in _QUESTION) or any(
        low.startswith(w) for w in ("kas ", "kaip ", "kam ", "kodėl", "kodel", "negi")
    ):
        return True
    tokens = [t.strip(".,!?") for t in low.split()]
    return any(t in _QUESTION_TOKENS for t in tokens)


def get_strategy(verdict: str | None) -> Strategy | None:
    """The strategy for a diagnosis verdict reason, or None if unhandled (the
    caller falls back to the generic instruct/inform flow).

    Prefers the DECLARATIVE definition in `knowledge/faults.yaml` — so changing a
    procedure (or adding a fault) is a file edit, not a code change — and falls back to
    the in-code registry below whenever the manifest does not declare it or fails to
    build. Imported lazily to keep the module free of a cycle."""
    if not verdict:
        return None
    try:
        from .faults import build_strategy

        declared = build_strategy(verdict)
        if declared is not None:
            return declared
    except Exception:  # pragma: no cover - defensive; manifest must never break a call
        pass
    return STRATEGIES.get(verdict)


def verify_target(strategy: Strategy, fixed: bool) -> str | None:
    """The terminal a strategy's VERIFY step routes to for a fixed / not-fixed
    telemetry outcome (e.g. 'resolve' / 'escalate'). None if it has no VERIFY step.
    Used by the engine after a silent action to decide resolve vs escalate."""
    vstep = next((s for s in strategy.steps if s.kind == StepKind.VERIFY), None)
    if vstep is None:
        return None
    return next_step_id(strategy, vstep.id, Outcome.FIXED if fixed else Outcome.NOT_FIXED)
