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
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def test_farewell_ends_the_call(self):
        agent = self._agent()
        agent.state.case_closed = True
        agent._maybe_finish("ne, ačiū")
        assert agent.state.is_complete is True

    def test_question_keeps_it_open_then_caps(self):
        agent = self._agent()
        agent.state.case_closed = True
        agent._maybe_finish("o kiek tai kainuos?")  # a real follow-up
        assert agent.state.is_complete is False
        agent._maybe_finish("gerai, supratau")  # 2nd closing turn -> cap
        assert agent.state.is_complete is True

    def test_noop_when_not_closed(self):
        agent = self._agent()
        agent._maybe_finish("viso gero")  # case not closed -> ignore
        assert agent.state.is_complete is False

    def test_goodbye_reply_ends_call_any_path(self):
        # Catch-all: the agent's own farewell ends the call even without case_closed
        # (e.g. the stuck backstop's "užregistruosiu… geros dienos" that used to loop).
        agent = self._agent()
        agent._maybe_end_on_goodbye(
            "Užregistruosiu problemą, specialistas susisieks. Geros dienos!"
        )
        assert agent.state.is_complete is True

    def test_midconversation_reply_does_not_end(self):
        agent = self._agent()
        agent._maybe_end_on_goodbye("Pasakykite adresą, kuriuo neveikia internetas.")
        assert agent.state.is_complete is False


class TestCaseStateTransitions:
    """_update_state_from_observation drives the END-state flags."""

    def _agent(self):
        from agent.react_agent import ReactAgent

        return ReactAgent(caller_phone="unknown")

    def test_close_case_observation_sets_closed(self):
        import json

        agent = self._agent()
        agent._update_state_from_observation(
            "close_case",
            json.dumps({"success": True, "case_closed": True, "reason": "resolved"}),
        )
        assert agent.state.case_closed is True
        assert agent.state.closed_reason == "resolved"

    def test_active_outage_sets_reported_not_closed(self):
        import json

        agent = self._agent()
        agent._update_state_from_observation(
            "check_outages",
            json.dumps(
                {"success": True, "affected": True, "active_outages": [{"street": "Dainų g."}]}
            ),
        )
        assert agent.state.outage_reported is True
        assert agent.state.case_closed is False  # an outage does NOT close the case

    def test_no_outage_leaves_reported_false(self):
        import json

        agent = self._agent()
        agent._update_state_from_observation(
            "check_outages",
            json.dumps({"success": True, "affected": False, "active_outages": []}),
        )
        assert agent.state.outage_reported is False
