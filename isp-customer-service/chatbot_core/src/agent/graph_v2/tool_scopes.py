"""
Per-stage tool scopes — the structural tool-access gate.

Each stage node exposes only its own toolset to the LLM, so e.g.
"diagnose before identification" is impossible by construction.
"""

from __future__ import annotations

# Identification stage: NO tools — the engine runs every lookup (the phone
# preflight, the street outage check, resolve_address from the heard slots, the
# account code) and closes the case itself; the narrator only talks.
IDENTIFICATION_TOOLS: frozenset[str] = frozenset()

# Closing stage: NO tools at all — structurally cannot diagnose or ask for an
# address; the agent can only say a short goodbye.
CLOSING_TOOLS: frozenset[str] = frozenset()

# Ticket-registration stage: NO tools — the engine collects the contacts and
# creates the ticket deterministically; the node's LLM only answers off-script
# questions ("kokiu numeriu?") between the scripted stage questions.
TICKET_TOOLS: frozenset[str] = frozenset()

# Security-sensitive resolution actions — only exposed on the strategy STEP
# that permits them (update_mac on bind_mac, create_ticket on escalate). So the
# model cannot bind a device during a CONFIRM step, before the caller confirms.
STRATEGY_ACTION_TOOLS = frozenset({"update_mac", "reset_port", "create_ticket"})
# Diagnostics the ENGINE owns during a strategy — the model must not call them
# (observed: it looped check_network_status / run_ping_test instead of talking).
STRATEGY_DIAG_TOOLS = frozenset(
    {"diagnose_connection", "check_network_status", "run_ping_test", "check_port_status"}
)
