"""
LangGraph orchestration for the agent (docs/pokalbio_variklis.md §6, Phase 3.5
step 3).

Step 3.2 — the NODE SPLIT. A deterministic router sends each turn to one of two
focused nodes:

  START --(customer_id?)--> address_validation   (Režimas A: lookup-only)
                       ` -> diagnosis             (Režimas B: full toolset)

The split makes the tool-access gate STRUCTURAL: the identification node simply
does not expose `diagnose_connection` / `update_mac` / `reset_port` /
`create_ticket`, so "diagnose before identification" is impossible by
construction (the in-engine gate from 1.3 remains as a backstop). Each node also
gets a short focus prompt on top of the shared system prompt.

Both nodes delegate the actual LLM tool-loop to the existing ReactAgent
(`run_turn_scoped`), so tools, the verdict tree, resolve_address, NLU prefill and
tracing are all REUSED, not rewritten. Conversation state still lives in the
engine (read by the router via `engine.state`); migrating it into the typed graph
state is a later refinement.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

# Identification stage: lookup tools only — NO diagnostics / mutations / tickets.
LOOKUP_TOOLS = frozenset({"resolve_address", "find_customer", "check_outages", "search_knowledge"})

_ADDRESS_NODE_PROMPT = (
    "=== STAGE: IDENTIFICATION ===\n"
    "The customer is NOT yet identified. Your ONLY goal now is to capture and "
    "confirm the service address (or an account code). You currently have ONLY "
    "lookup tools — you CANNOT diagnose, change anything, or create a ticket yet, "
    "so do not promise it. Ask only for the MISSING address parts, call "
    "resolve_address, and echo-confirm what you found "
    '("Radau ... Ar šiuo adresu neveikia internetas?"). Once the address '
    "resolves and the customer confirms, the diagnosis stage begins next turn."
)

_DIAGNOSIS_NODE_PROMPT = (
    "=== STAGE: DIAGNOSIS ===\n"
    "The customer is identified (customer_id is in KNOWN FACTS). Solve the "
    "problem: call diagnose_connection(customer_id) and route STRICTLY by its "
    "verdict, then use the technical tools as needed. If the customer now says "
    "the address is wrong, re-resolve it with resolve_address before anything else."
)


class TurnState(TypedDict, total=False):
    """Per-turn graph state (the conversation state itself still lives in the
    engine; it migrates here in a later refinement)."""

    user_input: str | None
    reply: str | None


def build_turn_graph(engine: Any):
    """
    Compile the router + two-node graph around `engine` (a ReactAgent),
    checkpointed with MemorySaver (thread_id = session_id).
    """

    def address_validation(state: TurnState) -> TurnState:
        return {
            "reply": engine.run_turn_scoped(
                state.get("user_input"), LOOKUP_TOOLS, _ADDRESS_NODE_PROMPT
            )
        }

    def diagnosis(state: TurnState) -> TurnState:
        return {
            "reply": engine.run_turn_scoped(state.get("user_input"), None, _DIAGNOSIS_NODE_PROMPT)
        }

    def route(state: TurnState) -> str:
        # Deterministic: identified -> diagnosis, else keep identifying.
        return "diagnosis" if engine.state.customer_id else "address_validation"

    builder = StateGraph(TurnState)
    builder.add_node("address_validation", address_validation)
    builder.add_node("diagnosis", diagnosis)
    builder.set_conditional_entry_point(
        route,
        {"address_validation": "address_validation", "diagnosis": "diagnosis"},
    )
    builder.add_edge("address_validation", END)
    builder.add_edge("diagnosis", END)
    return builder.compile(checkpointer=MemorySaver())
