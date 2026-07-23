#!/usr/bin/env python3
"""
Manual bridge-device simulation — "I just plugged the cable into the computer".

Run this in a SECOND terminal DURING a voice test (dead-router / bridge scenario) to
make a new, unbound device appear on the caller's line, exactly as if they physically
plugged a PC into the wall cable. The agent's next telemetry read then sees the device
(foreign_mac) and the bridge binds it — so you drive the physical action yourself instead
of the engine faking it on a keyword.

For this to be YOUR trigger (not the engine's auto-fire), run voice_demo with the
auto-simulation OFF:  $env:SIMULATE_BRIDGE="off"

Usage:
    uv run python scripts/sim_plug_cable.py +37060012353     # by caller phone
    uv run python scripts/sim_plug_cable.py CUST009          # by customer id
    uv run python scripts/sim_plug_cable.py +37060012353 --unplug   # clear it again
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `agent` importable like the app does.
_SRC = Path(__file__).resolve().parent.parent / "chatbot_core" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _resolve_customer_id(who: str) -> str | None:
    """A phone (+3706…) is looked up to a customer_id; anything else is taken as one."""
    if not who.startswith("+"):
        return who
    from agent.tools import execute_tool

    r = json.loads(execute_tool("find_customer", {"phone": who}))
    cid = r.get("customer_id")
    if not cid:
        cid = (r.get("customers") or [{}])[0].get("customer_id")
    return cid


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulate plugging a PC into the wall cable.")
    ap.add_argument("who", help="caller phone (+3706…) or customer id (CUST009)")
    ap.add_argument("--unplug", action="store_true", help="clear the device instead")
    args = ap.parse_args()

    cid = _resolve_customer_id(args.who)
    if not cid:
        print(f"Could not resolve a customer for {args.who!r}.")
        return 1

    from agent.tools import (
        execute_tool,
        simulate_bridge_connect,
        simulate_bridge_disconnect,
    )

    res = simulate_bridge_disconnect(cid) if args.unplug else simulate_bridge_connect(cid)
    print(f"[{cid}] {res.get('message', res)}")

    # Show the resulting line state so you can confirm what the agent will see next.
    d = json.loads(execute_tool("diagnose_connection", {"customer_id": cid}))
    v = (d.get("verdict") or {}).get("reason")
    s = d.get("signals") or {}
    print(f"   line now: verdict={v} observed_mac={s.get('observed_mac')}")
    if not args.unplug:
        print("   → agentui: 'Matau jūsų kompiuterį, pririšiu' (kitas telemetrijos skaitymas)")
    return 0 if res.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
