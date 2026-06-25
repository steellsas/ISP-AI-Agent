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
    "confirm the service address (or an account code). You have ONLY lookup tools "
    "— you CANNOT diagnose, change anything, or create a ticket yet; do not "
    "promise it.\n"
    "- If KNOWN FACTS lists a HEARD ADDRESS, USE those values for resolve_address "
    "instead of re-reading the raw text.\n"
    "- LEAD WITH THE STREET: pass street + house to resolve_address WITHOUT a city "
    "— it derives the locality. Ask the city only if resolve_address says the "
    "street is in several localities or none. Do NOT recite 'miestą, gatvę, namą, "
    "butą' — ask the missing part naturally and ECHO the parsed parts (\"Gatvė "
    'Tilžės, namas 60, butas 7 — teisingai?").\n'
    "- Ask only for the MISSING parts, call resolve_address, and echo-confirm what "
    'it returned ("Radau <rastas adresas>. Ar šiuo adresu neveikia internetas?"). '
    'Say "Radau" ONLY on a real customer hit, not on a partial street match.\n'
    "- ECHO what you heard so the caller can catch STT errors: when a part fails, "
    'echo the VALUE ("Išgirdau namo numerį 8 — ar teisingai?") — do NOT just '
    "repeat the generic question.\n"
    "- GRACEFUL EXIT: if the SAME part fails about twice, STOP repeating the "
    'identical ask — offer the account code ("Gal turite abonento kodą nuo '
    'sąskaitos?") or register the issue for a callback. Never loop the same '
    "sentence like a stuck record.\n"
    "- MASS OUTAGE — do this BEFORE asking for the apartment. The moment you know "
    'the STREET, call check_outages(area="Miestas, Gatvė") — ALWAYS include the '
    "street, NEVER city-only (a city-only result covers other streets and proves "
    "nothing). If there is an active outage on that street, INFORM the caller + "
    "estimated time, then STOP: do NOT ask for the house/apartment, do NOT "
    "re-confirm the address, do NOT diagnose — the outage IS the final answer. "
    'Close politely ("Ar dar kuo galiu padėti?"). A street-wide outage needs no '
    "apartment and no full identification. ESPECIALLY when resolve_address says "
    "'kelios sutartys / paklausk buto' — check the outage FIRST; only ask for the "
    "apartment if there is NO outage.\n"
    "- Never invent or parrot an address you were not given. Once the address "
    "resolves and the customer confirms, diagnosis begins next turn."
)

_DIAGNOSIS_NODE_PROMPT = (
    "=== STAGE: DIAGNOSIS ===\n"
    "The customer is identified. Call diagnose_connection(customer_id) and route "
    "STRICTLY by its verdict; use the technical tools as needed. You MAY re-run "
    "diagnose_connection to re-check the facts whenever the customer contradicts a "
    "finding or after you take an action.\n"
    "- FACTS WIN. The DIAGNOSTIKA findings (network telemetry) are GROUND TRUTH; the "
    "caller's words are a HYPOTHESIS to verify against them. Callers often look at "
    "the wrong device or confuse the router with the power brick.\n"
    "- If the line shows a device / IP / traffic (e.g. a MAC is observed), the "
    "signal DOES reach the home — do NOT chase power / cable / 'lights off'. Say what "
    "the line shows and route by the VERDICT (e.g. B6 foreign_mac -> ask if they "
    "changed the router -> update_mac). Do NOT improvise a troubleshooting path the "
    "facts contradict.\n"
    "- If the customer says one thing then corrects it, CONFIRM your understanding "
    '("Ar teisingai supratau, kad …?") before acting.\n'
    "- ONE step at a time, SHORT replies, and REACT to what the customer JUST said: "
    "if they say it now works, acknowledge and close — do not push the script. If "
    "the address is now wrong, re-resolve it first."
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
