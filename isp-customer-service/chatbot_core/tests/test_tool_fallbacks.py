"""Wave 2c-4: what the agent DOES when a system does not answer.

The manifest names the fallback; these tests are the proof that the engine carries it out —
the caller is asked what we can no longer see, a technician is offered when we cannot fix it
remotely, and a call whose register is down ends politely instead of stalling.
"""

import pytest
from agent.decide.rules import tools as tool_rules
from agent.graph_v2.graph import redecide


def _failure(state, fallback, *, tool="diagnose_connection", capability="probe", say_key=None):
    state.turn.tool_failure = {
        "tool": tool,
        "capability": capability,
        "fallback": fallback,
        "say_key": say_key,
        "error": "tool_timeout",
    }


class TestTheFallbackIsPlanned:
    def test_a_dead_probe_leaves_the_stage_to_plan_and_the_news_on_the_card(
        self, make_state, make_runtime
    ):
        """ask_client: the evidence ladder already knows how to work without telemetry —
        the card only makes sure the reply does not claim a check that never ran."""
        state, rt = make_state("+37060020112"), make_runtime()
        _failure(state, "ask_client", say_key="tools.unavailable_probe")

        assert tool_rules.plan(state, rt) is None  # the stage families plan as usual
        assert state.turn.tool_failure is None  # consumed
        assert state.turn.tool_trouble["fallback"] == "ask_client"

        from agent.speak.context_card import context_card

        card = context_card(state, rt) or ""
        assert "A SYSTEM DID NOT ANSWER" in card and "nematau linijos" in card

    def test_a_dead_action_offers_a_technician(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST009"
        _failure(state, "ticket", tool="reset_port", capability="action")

        assert tool_rules.plan(state, rt) is None  # the ticket family owns the turn now
        assert state.ticket.stage == "phone"  # contacts first, then register + close

    def test_a_dead_register_ends_the_call_politely(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        _failure(
            state,
            "end_call",
            tool="resolve_address",
            capability="crm",
            say_key="tools.unavailable_crm",
        )

        plan = tool_rules.plan(state, rt)

        assert plan is not None and plan.rule == "tools.systems_down"
        assert plan.action.type == "close" and plan.action.name == "stuck"
        assert plan.say.key == "tools.unavailable_crm"

    def test_skip_says_nothing(self, make_state, make_runtime):
        state, rt = make_state("+37060020112"), make_runtime()
        _failure(state, "skip", tool="check_outages", capability="outages")

        assert tool_rules.plan(state, rt) is None
        from agent.speak.context_card import context_card

        assert "A SYSTEM DID NOT ANSWER" not in (context_card(state, rt) or "")

    def test_a_failure_is_handled_once(self, make_state, make_runtime):
        """The redecide loop must not spin on the same dead tool."""
        state, rt = make_state("+37060020112"), make_runtime()
        _failure(state, "end_call", say_key="tools.unavailable_crm")

        assert tool_rules.plan(state, rt) is not None
        assert tool_rules.plan(state, rt) is None


class TestTheTurnGoesBackToDecide:
    @pytest.mark.parametrize(
        "pending, hops, expected",
        [
            (True, 0, "decide"),  # a dead tool -> plan the fallback before speaking
            (False, 0, "narrate"),
            (True, 9, "narrate"),  # the hop budget still bounds the loop
        ],
    )
    def test_a_pending_failure_sends_the_turn_back(self, pending, hops, expected, make_state):
        state = make_state("+37060020112")
        state.turn.plan = {"rule": "procedure.hold", "redecide_after_action": False}
        state.turn.plan_hops = hops
        if pending:
            _failure(state, "ask_client", say_key="tools.unavailable_probe")

        assert redecide(state) == expected
