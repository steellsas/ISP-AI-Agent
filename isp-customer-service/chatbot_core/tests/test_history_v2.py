"""
Hygiene step 3 — istorija v2 (Andrius 2026-08-27): a deterministic summary
from STATE bridges the trimmed window; a recall trigger pulls the caller's
own earlier lines back in; nothing is ever deleted from state.messages.
"""


def _agent(db_connection=None):
    from agent.react_agent import ReactAgent

    agent = ReactAgent(caller_phone="+37060012353")
    agent.state.problem_type = "internet_down"
    agent.state.anamnesis_when = "vakar"
    agent.state.customer_id = "CUST009"
    agent.state.customer_address = "Šiauliai, Vilniaus g. 29"
    agent.state.resolution = {"verdict": "no_mac_observed", "step": "dr_power"}
    return agent


class TestHistorySummary:
    def test_no_summary_while_history_fits(self, db_connection):
        from agent.narrator_flow import history_summary

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": "labas"}] * 5
        assert history_summary(agent) is None

    def test_summary_bridges_the_cut(self, db_connection):
        from agent.narrator_flow import history_summary

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": f"r{i}"} for i in range(30)]
        text = history_summary(agent)
        assert text and "SANTRAUKA" in text
        assert "internet_down" in text and "vakar" in text
        assert "Vilniaus g. 29" in text

    def test_summary_lands_before_the_window(self, db_connection):
        agent = _agent()
        agent.state.messages = [
            {"role": "user" if i % 2 else "assistant", "content": f"replika {i}"} for i in range(30)
        ]
        messages = agent._build_messages(user_input="testas")
        idx = [
            i
            for i, m in enumerate(messages)
            if m["role"] == "system" and "SANTRAUKA" in m.get("content", "")
        ]
        assert len(idx) == 1
        # the summary comes right after the prefix, before the windowed history
        assert idx[0] == 1
        # nothing was deleted from state — prompt assembly never mutates it
        assert len(agent.state.messages) == 30


class TestRecallTrigger:
    def test_saskiau_pulls_the_old_line_back(self, db_connection):
        from agent.narrator_flow import recall_lines

        agent = _agent()
        old = [{"role": "user", "content": "internetas dingo po didelės audros vakar"}]
        filler = [
            {"role": "user" if i % 2 else "assistant", "content": f"replika {i}"} for i in range(25)
        ]
        agent.state.messages = old + filler
        agent.state.last_heard = "juk sakiau — po audros dingo"
        note = recall_lines(agent)
        assert note and "audros" in note and "PRIMENA" in note

    def test_no_marks_no_recall(self, db_connection):
        from agent.narrator_flow import recall_lines

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": "po audros"}] * 30
        agent.state.last_heard = "nedega lemputė"
        assert recall_lines(agent) is None

    def test_recent_reference_needs_no_recall(self, db_connection):
        from agent.narrator_flow import recall_lines

        agent = _agent()
        agent.state.messages = [{"role": "user", "content": "po audros dingo"}] * 5
        agent.state.last_heard = "sakiau — po audros"
        assert recall_lines(agent) is None  # the line is still inside the window
