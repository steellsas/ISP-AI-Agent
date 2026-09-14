"""Test helpers: a fresh call (state + runtime) and a narrator over it."""

from agent.react_agent import ReactAgent
from agent.runtime import new_call


def make_call(caller_phone="unknown", language="lt", tracer=None, tools=None):
    """(GraphState, AgentRuntime) for a new call — what AgentSession builds."""
    return new_call(caller_phone, language, tracer=tracer, tools=tools)


def make_agent(caller_phone="unknown", language="lt", tracer=None, tools=None):
    """The narrator loop over a new call; tests read `.state` / `.runtime` from it."""
    state, runtime = make_call(caller_phone, language, tracer=tracer, tools=tools)
    return ReactAgent(state, runtime)
