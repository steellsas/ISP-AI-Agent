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
from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from .prompts import load_node_prompt

# Identification stage: lookup tools only — NO diagnostics / mutations / tickets.
# close_case is allowed here too, so an outage (found pre-identification) can be
# acknowledged and the call closed without forcing a full ID first.
LOOKUP_TOOLS = frozenset(
    {"resolve_address", "find_customer", "check_outages", "search_knowledge", "close_case"}
)

# Closing stage: NO tools at all — structurally cannot diagnose or ask for an
# address; the agent can only say a short goodbye.
CLOSING_TOOLS: frozenset[str] = frozenset()

# Per-stage prompts (dynamic prompting): each stage loads ONLY its own focused
# rules from prompts/*.txt, so the model is not diluted by the whole call's
# instructions. The shared contract + tools live in the system prompt; the dynamic
# state (KNOWN FACTS, DIAGNOSTIKA, closed reason, stuck nudge) is injected by the
# engine's facts block.
_ADDRESS_NODE_PROMPT = load_node_prompt("stages/identification")
_DIAGNOSIS_NODE_PROMPT = load_node_prompt("stages/diagnosis")
_CLOSING_NODE_PROMPT = load_node_prompt("stages/closing")


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

    def _run_node(state: TurnState, allowed_tools, node_prompt, node: str) -> TurnState:
        """Stream the reply tokens out via the LangGraph stream writer (a no-op
        under .invoke(), live under .stream(stream_mode='custom')) while collecting
        the full reply for the checkpoint. LangGraph stays the orchestrator."""
        # Which node handled this turn — the router's choice, made explicit in the
        # trace instead of inferred (feeds the DEBUG_LLM payload too).
        engine._active_node = node
        engine.tracer.emit("node", node=node, customer_id=engine.state.customer_id)
        writer = get_stream_writer()
        parts: list[str] = []
        for token in engine.run_turn_scoped_stream(
            state.get("user_input"), allowed_tools, node_prompt
        ):
            writer(token)
            parts.append(token)
        return {"reply": "".join(parts)}

    def address_validation(state: TurnState) -> TurnState:
        result = _run_node(state, LOOKUP_TOOLS, _ADDRESS_NODE_PROMPT, "address_validation")
        # resolve_address may have identified the caller mid-turn; arc v3: the same
        # reply then narrates "patikrinsiu… patikrinau: [rezultatas]" + the first
        # step's question — mark the step presented so the caller's next answer
        # advances the walker.
        engine._mark_step_presented()
        return result

    def diagnosis(state: TurnState) -> TurnState:
        # Deterministic driver: diagnose ONCE on entering the stage (before the LLM
        # narrates), so the verdict + resolution strategy are set and the flow no
        # longer depends on the model choosing to diagnose. Then walk the strategy's
        # CONFIRM step from the caller's reply (binding is only exposed after they
        # confirm connecting a device); after the reply, mark the question asked so a
        # plain yes/no advances next turn.
        engine.ensure_diagnosed()
        # Deterministic close for INFORM mode (outage / billing / no-strategy): if the
        # caller was already informed and now says goodbye, close here so the reply is a
        # single farewell — not another re-narration of the outage. Runs before narration
        # so the facts block reflects the closed state this turn.
        engine._maybe_close_inform(state.get("user_input"))
        # Phase 3.8 step 5a: for a piloted direction (behind SOLVER_DRIVE), the SOLVER runs
        # the turn end-to-end and returns the reply; the walker + LLM narrator are skipped.
        # None => not driving (flag off / other direction) => fall through to the walker.
        driven = engine.solver_drive_turn(state.get("user_input"))
        if driven is not None:
            engine._active_node = "diagnosis"
            engine.tracer.emit(
                "node", node="diagnosis_solver", customer_id=engine.state.customer_id
            )
            get_stream_writer()(driven)
            return {"reply": driven}
        engine._advance_resolution(state.get("user_input"))
        # Solver runs in SHADOW (Phase 3.8 step 2): logs its decision next to the
        # walker's move for comparison; never drives the reply. No-op unless
        # SOLVER_SHADOW=on.
        engine._shadow_solve(state.get("user_input"))
        # If the caller's reply advanced us onto an ACTION step (e.g. bind_mac after
        # they confirmed the device change), run it deterministically BEFORE the LLM
        # narrates — the engine binds + resets + re-verifies and sets case_closed, so
        # the model only PHRASES the verified result (no model-invoked update_mac,
        # so no single-tool loop and no "nepririštas, dabar pririšiu" after binding).
        engine.ensure_action_done()
        result = _run_node(state, None, _DIAGNOSIS_NODE_PROMPT, "diagnosis")
        engine._mark_step_presented()
        return result

    def closing(state: TurnState) -> TurnState:
        # Decide whether to hang up: a farewell / "no more" from the caller, or a
        # second closing turn, ends the call (is_complete) so the agent does not loop
        # goodbyes. The transport plays this last reply and then stops responding.
        engine._maybe_finish(state.get("user_input"))
        return _run_node(state, CLOSING_TOOLS, _CLOSING_NODE_PROMPT, "closing")

    def route(state: TurnState) -> str:
        # Deterministic. case_closed wins (END stage); then identified -> diagnosis,
        # else keep identifying. (State lives in the engine — see module docstring —
        # and each AgentSession has its own engine + graph, so this is per-session.)
        if engine.state.case_closed:
            return "closing"
        return "diagnosis" if engine.state.customer_id else "address_validation"

    builder = StateGraph(TurnState)
    builder.add_node("address_validation", address_validation)
    builder.add_node("diagnosis", diagnosis)
    builder.add_node("closing", closing)
    builder.set_conditional_entry_point(
        route,
        {
            "address_validation": "address_validation",
            "diagnosis": "diagnosis",
            "closing": "closing",
        },
    )
    builder.add_edge("address_validation", END)
    builder.add_edge("diagnosis", END)
    builder.add_edge("closing", END)
    return builder.compile(checkpointer=MemorySaver())
