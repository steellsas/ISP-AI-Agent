"""
W0–W2 dialogue-quality waves (Andrius 2026-08-25): order guards after the
garbled-call analysis, hear-the-caller mechanics, and the quiet analyst.
"""

from types import SimpleNamespace

from agent.delivery import apply_delivery
from agent.evidence import Contradiction
from agent.graph_v2.state import TicketContext


def _turn_state(agent, text):
    """The agent's state as a node input for one caller turn."""
    from agent.graph_v2.state import TurnScratch

    return agent.state.model_copy(update={"turn": TurnScratch(user_input=text)})


class TestUnheardQuestion:
    """Andrius 2026-08-26: the agent must never believe it asked a question
    the caller could not hear — an unheard '?' rolls the ask back and the
    narrator reacts + re-asks."""

    def _agent(self):
        from tests.calls import make_agent

        agent = make_agent("+37060012353")
        agent.state.identity.customer_id = "CUST009"
        agent.state.resolution.procedure = {
            "verdict": "no_mac_observed",
            "step": "dr_lights",
            "presented": {"dr_lights": 1},
        }
        agent.state.messages.append({"role": "assistant", "content": "irrelevant"})
        return agent

    def test_unheard_question_rolls_the_ask_back(self, db_connection):
        from agent.speak.context_card import context_card

        agent = self._agent()
        agent.state.dialog.last_question = "Ar dega bent viena lemputė?"
        agent.state.diagnosis.pending_evidence_key = "lights"
        agent.state.diagnosis.evidence_ask_counts = {"lights": 1}
        apply_delivery(
            agent.state, agent.runtime, ["Gerai, kad radote.", "Ar dega bent viena lemputė?"], 1
        )
        assert agent.state.dialog.last_question is None
        # the pending key STAYS (live 2026-08-27: clearing it looped the call —
        # the interrupting ANSWER had no key to land on); only the ask counter
        # steps back.
        assert agent.state.diagnosis.pending_evidence_key == "lights"
        assert agent.state.diagnosis.evidence_ask_counts["lights"] == 0
        assert agent.state.resolution.procedure["presented"]["dr_lights"] == 0
        assert agent.state.voice.unheard_question == "Ar dega bent viena lemputė?"
        assert agent.state.voice.undelivered_tail is None  # superseded by the strong note
        block = context_card(agent.state, agent.runtime) or ""
        assert "YOUR QUESTION NEVER WENT OUT" in block and "lemputė" in block
        assert "KLAUSIMAS NEIŠĖJO" not in (context_card(agent.state, agent.runtime) or "")

    def test_heard_question_keeps_the_ask(self, db_connection):
        agent = self._agent()
        agent.state.dialog.last_question = "Ar dega bent viena lemputė?"
        agent.state.diagnosis.pending_evidence_key = "lights"
        agent.state.diagnosis.evidence_ask_counts = {"lights": 1}
        apply_delivery(
            agent.state,
            agent.runtime,
            ["Ar dega bent viena lemputė?", "Tai parodys, ar gauna srovę."],
            1,
        )
        assert agent.state.dialog.last_question == "Ar dega bent viena lemputė?"
        assert agent.state.diagnosis.pending_evidence_key == "lights"
        assert agent.state.voice.unheard_question is None
        assert agent.state.voice.undelivered_tail  # the plain advisory note stands
