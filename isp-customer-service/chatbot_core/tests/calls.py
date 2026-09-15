"""Test helpers: a call's state and runtime, fake tools, and a narrator over it.

Node-level tests build `make_state()` + `make_runtime()` and call
`node(state, Runtime(context=rt))` directly; flow tests that also need the
narrator loop use `make_agent()` (it carries `.state` and `.runtime`).
"""

import json

from agent.graph_v2.state import GraphState, IdentityState
from agent.react_agent import ReactAgent
from agent.runtime import AgentRuntime, new_call
from agent.tooling import LocalToolProvider, ToolGateway


class FakeToolProvider:
    """A ToolProvider answering every call with `fn(name, args)` (a dict or a
    JSON string); `calls` records what reached it. The address registry still
    comes from the demo database."""

    def __init__(self, fn):
        self.fn = fn
        self.calls: list[tuple[str, dict]] = []
        self._local = LocalToolProvider()

    def available_tools(self):
        return self._local.available_tools()

    def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        result = self.fn(tool_name, arguments)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    def address_registry(self):
        return self._local.address_registry()


def make_state(caller_phone="unknown", **groups) -> GraphState:
    """A call's GraphState; `groups` replace whole state groups (e.g. ticket=TicketState(...))."""
    groups.setdefault("identity", IdentityState(caller_phone=caller_phone))
    return GraphState(**groups)


def make_runtime(fake_tools=None, tracer=None, language="lt") -> AgentRuntime:
    """A call's AgentRuntime. `fake_tools(name, args)` replaces the local tools."""
    tools = ToolGateway(FakeToolProvider(fake_tools)) if fake_tools else None
    _state, runtime = new_call(language=language, tracer=tracer, tools=tools)
    return runtime


def make_call(caller_phone="unknown", language="lt", tracer=None, tools=None):
    """(GraphState, AgentRuntime) for a new call — what AgentSession builds."""
    return new_call(caller_phone, language, tracer=tracer, tools=tools)


def make_agent(caller_phone="unknown", language="lt", tracer=None, tools=None):
    """The narrator loop over a new call; tests read `.state` / `.runtime` from it."""
    state, runtime = make_call(caller_phone, language, tracer=tracer, tools=tools)
    return ReactAgent(state, runtime)


def run_turn_nodes(state, runtime):
    """decide -> execute -> narrate on a perceived state (Runtime-wrapped rt); the
    last node's update (the whole state) — a turn without the perceive node."""
    from agent.decide.node import decide_node
    from agent.execute.node import execute_node, narrate_node

    upd = decide_node(state, runtime)
    upd = execute_node(GraphState(**upd), runtime)
    return narrate_node(GraphState(**upd), runtime)
