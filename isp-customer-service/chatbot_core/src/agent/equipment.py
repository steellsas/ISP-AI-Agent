"""The equipment catalogue — model, then family, then the basic one (wave 3e, P-8).

The agent never gives up on a device. The CRM may not know what the caller has, and the
caller may have bought their own, so an instruction is chosen from the most specific level
that exists down to one that always does:

    TP-Link Archer C6   -> equipment/archer_c6.yaml   (if we ever describe that model)
    "a TP-Link"         -> equipment/tplink.yaml      (the manufacturer family)
    a router            -> equipment/router.yaml      (the basic one — always there)

Each level inherits the one below and overrides only what differs, so the basic file holds
what is true of every router (pull the power lead, wait, plug it back) and a family file
holds what is not (where the button is, what the lights are called).

The catalogue also turns what the caller SEES into facts the cards reason about: "INTERNET
red" on a TP-Link and "LOS blinking" on an ONT both become `wan_link=down`, so no card ever
has to know a model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contract import equipment as catalog
from .contract.locale import maybe_phrase


@dataclass(frozen=True)
class Device:
    """One device as the agent will talk about it: the levels that describe it, merged."""

    type: str
    level: str  # which file won: the model, the family, or the basic one
    name_key: str | None
    locate_key: str | None
    actions: dict[str, str]  # "reboot.power" -> phrase key
    lights: dict[str, dict]  # light -> {ask_key, means {value: "fact=value"}}

    def name(self) -> str | None:
        return maybe_phrase(self.name_key)

    def how_to(self, action: str) -> str | None:
        """The words for `reboot.power`, `cable.reseat` … at the most specific level that
        describes this device; None when no level does (the engine then does not offer it)."""
        return maybe_phrase(self.actions.get(action))

    def can(self, action: str) -> bool:
        return action in self.actions

    def light_question(self, light: str) -> str | None:
        return maybe_phrase((self.lights.get(light) or {}).get("ask_key"))

    def fact_from_light(self, light: str, seen: str) -> tuple[str, str] | None:
        """What the caller's answer MEANS: ("wan_link", "down"). None when this light says
        nothing about that value — an answer we cannot read is not a fact."""
        means = (self.lights.get(light) or {}).get("means") or {}
        stated = means.get(str(seen).strip().lower())
        if not stated or "=" not in stated:
            return None
        fact, value = stated.split("=", 1)
        return fact, value


def for_device(device_type: str, model: str | None = None) -> Device | None:
    """The best description we have for this device. `model` is what the CRM recorded
    ("TP-Link Archer C6") or what the caller said ("TP-Link")."""
    chain = catalog.chain_for(device_type, model)
    if not chain:
        return None
    merged: dict = {"actions": {}, "lights": {}, "name_key": None, "locate_key": None}
    for spec in chain:  # least specific first; each level overrides the one before
        merged["name_key"] = spec.name_key or merged["name_key"]
        merged["locate_key"] = spec.locate_key or merged["locate_key"]
        merged["actions"].update(spec.actions)
        for light, described in spec.lights.items():
            known = dict(merged["lights"].get(light) or {})
            known["ask_key"] = described.ask_key or known.get("ask_key")
            known["means"] = {**(known.get("means") or {}), **described.means}
            merged["lights"][light] = known
    return Device(
        type=device_type,
        level=chain[-1].equipment,
        name_key=merged["name_key"],
        locate_key=merged["locate_key"],
        actions=merged["actions"],
        lights=merged["lights"],
    )


def for_signals(signals: dict | None, default_type: str = "router") -> Device | None:
    """The caller's device as the telemetry saw it: the CRM's model when there is one,
    otherwise the basic level for the type — because a call must go on either way."""
    signals = signals or {}
    return for_device(signals.get("device_type") or default_type, signals.get("device_model"))
