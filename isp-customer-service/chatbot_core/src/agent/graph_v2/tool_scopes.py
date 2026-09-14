"""
Per-stage tool scopes — the structural tool-access gate.

Each stage node exposes only its own toolset to the LLM, so e.g.
"diagnose before identification" is impossible by construction.
"""

from __future__ import annotations

# Identification stage: lookup tools only — NO diagnostics / mutations / tickets.
# close_case is allowed here too, so an outage (found pre-identification) can be
# acknowledged and the call closed without forcing a full ID first.
LOOKUP_TOOLS = frozenset(
    {"resolve_address", "find_customer", "check_outages", "search_knowledge", "close_case"}
)

# Closing stage: NO tools at all — structurally cannot diagnose or ask for an
# address; the agent can only say a short goodbye.
CLOSING_TOOLS: frozenset[str] = frozenset()

# Ticket-registration stage: NO tools — the engine collects the contacts and
# creates the ticket deterministically; the node's LLM only answers off-script
# questions ("kokiu numeriu?") between the scripted stage questions.
TICKET_TOOLS: frozenset[str] = frozenset()
