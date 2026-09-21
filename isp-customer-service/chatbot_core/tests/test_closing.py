"""
Tests for call closing: the call ends on a farewell / 'no more' or a 2nd closing
turn, and observations drive the END-state flags (moved from the deleted
legacy-graph test module).

Run: pytest tests/test_closing.py -v
"""


class TestClosing:
    """The call ends (is_complete) on a farewell / 'no more', or a 2nd closing turn —
    so the agent does not loop goodbyes."""

    def _agent(self):
        from tests.calls import make_agent

        return make_agent("unknown")

    def test_farewell_ends_the_call(self):
        from agent.decide.rules.closing import maybe_finish

        agent = self._agent()
        agent.state.closing.case_closed = True
        maybe_finish(agent.state, agent.runtime, "ne, ačiū")
        assert agent.state.closing.is_complete is True

    def test_question_keeps_it_open_then_caps(self):
        from agent.decide.rules.closing import maybe_finish

        agent = self._agent()
        agent.state.closing.case_closed = True
        maybe_finish(agent.state, agent.runtime, "o kiek tai kainuos?")  # a real follow-up
        assert agent.state.closing.is_complete is False
        maybe_finish(agent.state, agent.runtime, "gerai, supratau")  # 2nd closing turn -> cap
        assert agent.state.closing.is_complete is True

    def test_noop_when_not_closed(self):
        from agent.decide.rules.closing import maybe_finish

        agent = self._agent()
        maybe_finish(agent.state, agent.runtime, "viso gero")  # case not closed -> ignore
        assert agent.state.closing.is_complete is False

    def test_the_goodbye_plan_ends_the_call(self):
        """Wave 1: the farewell and the hang-up are ONE plan — a reply is never read
        back for goodbye words (the narrator's wording is not a decision)."""
        from agent.decide.rules import closing as closing_rules
        from agent.execute.actions import run_action

        agent = self._agent()
        agent.state.identity.customer_id = "CUST009"
        agent.state.closing.case_closed = True
        agent.state.ticket.ticket_id = "TKT1"
        agent.state.turn.user_input = "ačiū"

        plan = closing_rules.plan(agent.state, agent.runtime)
        assert plan.rule == "closing.goodbye_after_ticket"
        assert plan.action.type == "close" and plan.action.args == {"complete": True}
        run_action(agent.state, agent.runtime, plan)

        assert agent.state.closing.is_complete is True

    def test_a_farewell_said_with_the_call_open_is_traced(self):
        """The net that used to hang up on goodbye words is gone; the gap is visible."""
        from agent.speak.postprocess import finalize

        agent = self._agent()
        events = []
        agent.runtime.tracer.emit = lambda event, **f: events.append((event, f))

        finalize(agent.state, agent.runtime, "Ačiū, kad paskambinote. Geros dienos!")

        assert agent.state.closing.is_complete is False
        assert any(e == "goodbye_unclosed" for e, _ in events)

    def test_a_midconversation_reply_is_not_a_farewell(self):
        from agent.speak.postprocess import finalize

        agent = self._agent()
        events = []
        agent.runtime.tracer.emit = lambda event, **f: events.append((event, f))

        finalize(agent.state, agent.runtime, "Pasakykite adresą, kuriuo neveikia internetas.")

        assert not any(e == "goodbye_unclosed" for e, _ in events)


class TestCaseStateTransitions:
    """_update_state_from_observation drives the END-state flags."""

    def _agent(self):
        from tests.calls import make_agent

        return make_agent("unknown")

    def test_active_outage_sets_reported_not_closed(self):
        import json

        from agent.execute.observe import update_state_from_observation

        agent = self._agent()
        update_state_from_observation(
            agent.state,
            agent.runtime,
            "check_outages",
            json.dumps(
                {"success": True, "affected": True, "active_outages": [{"street": "Dainų g."}]}
            ),
        )
        assert agent.state.diagnosis.outage_reported is True
        assert agent.state.closing.case_closed is False  # an outage does NOT close the case

    def test_no_outage_leaves_reported_false(self):
        import json

        from agent.execute.observe import update_state_from_observation

        agent = self._agent()
        update_state_from_observation(
            agent.state,
            agent.runtime,
            "check_outages",
            json.dumps({"success": True, "affected": False, "active_outages": []}),
        )
        assert agent.state.diagnosis.outage_reported is False


class TestClosingNode:
    """The node contract on a bare state + runtime: `run_turn_nodes(state, runtime)`
    returns the whole state as its update and reaches tools only via the gateway."""

    def test_number_correction_is_noted_through_the_gateway(self, make_state, make_runtime):
        from agent.graph_v2.state import ClosingState, TicketState, TurnScratch
        from langgraph.runtime import Runtime

        from tests.calls import run_turn_nodes

        rt = make_runtime(lambda name, args: {"success": True})
        state = make_state(
            "+37060012353",
            ticket=TicketState(ticket_id="TCK-1"),
            closing=ClosingState(case_closed=True),
            turn=TurnScratch(user_input="Skambinkite kitu numeriu 868321007"),
        )
        upd = run_turn_nodes(state, Runtime(context=rt))
        assert "Užsirašiau" in upd["turn"].reply
        assert [c[0] for c in rt.tools.provider.calls] == ["append_ticket_note"]
        assert "868321007" in rt.tools.provider.calls[0][1]["note"]
        assert state.turn.reply is None  # the node worked on its own copy
