"""Wave 2a: one reading per turn.

- The fast path reads a closed answer to a standing question without the model.
- A fact the model reports must be backed by the caller's own words (quote grounding).
"""

from unittest.mock import patch

import pytest
from agent.perceive.perception import Fact, Perception, fast_read, ground


def _asked(agent, key="lights", verdict="no_mac_observed", step="dr_lights"):
    agent.state.identity.customer_id = "CUST009"
    agent.state.resolution.procedure = {"verdict": verdict, "step": step, "asked": True}
    agent.state.diagnosis.pending_evidence_key = key
    return agent


def _agent():
    from tests.calls import make_agent

    return make_agent("+37060012353")


# (utterance, what the fast path makes of it)
FAST = [
    ("nedega", {"facts": {"lights": "off"}}),  # the pending question, answered
    ("dega", {"facts": {"lights": "on"}}),
    ("mhm", {"facts": {}}),  # heard, nothing claimed
    # "gerai" while a lights question stands is ambiguous (agreement? the light is on?)
    # — the full reading takes it.
    ("gerai", None),
    ("nežinau, reikia pažiūrėti ar ta dėžutė ten stovi", None),  # too much of their own
    ("o kur ta dėžutė?", None),  # a question is never a closed answer
]


@pytest.mark.parametrize("utterance, expected", FAST)
def test_the_fast_path_reads_closed_answers_without_the_model(utterance, expected, db_connection):
    agent = _asked(_agent())

    with patch("agent.perceive.understand.understand", side_effect=AssertionError("no LLM")):
        read = fast_read(agent.state, utterance, None)

    if expected is None:
        assert read is None  # the full reading takes this turn
        return
    assert read is not None and read.source == "fast_path"
    assert read.values() == expected["facts"]
    if expected["facts"]:
        assert read.understood  # the narrator can reflect it back
        assert (
            read.step
            == {
                "label": "no" if "off" in expected["facts"].values() else "yes",
                "is_answer": True,
                "internally_inconsistent": False,
                "confidence": 1.0,
            }
            or read.step is None
        )


def test_the_fast_path_needs_a_standing_question(db_connection):
    """Without a pending evidence question a bare yes/no is not enough: the step's
    answer often implies a fact only the model reads from a garbled utterance."""
    agent = _agent()
    agent.state.identity.customer_id = "CUST009"

    assert fast_read(agent.state, "nedega", {"yes": "dega", "no": "nedega"}) is None


# (the caller's words, what the model claims to have heard, does the fact survive?)
GROUNDING = [
    ("Lemputės nedega visai", "Lemputės nedega", True),
    ("Lemputės nedega visai", "nedega", True),
    ("Lemputės nedega visai", "ištraukiau laidą", False),  # never said
    ("Lemputės nedega visai", None, True),  # no quote -> the old corroboration rules
]


@pytest.mark.parametrize("utterance, quote, survives", GROUNDING)
def test_a_fact_needs_the_callers_own_words(utterance, quote, survives):
    read = Perception(source="llm", facts={"lights": Fact(value="off", quote=quote)})

    grounded = ground(read, utterance)

    assert grounded.facts["lights"].grounded is survives


class TestGroundingInTheReadingPath:
    def test_an_unquoted_hallucination_never_reaches_the_ledger(self, db_connection, monkeypatch):
        """Live 2026-08-10: five facts the caller never said poisoned the ledger."""
        import os

        from agent.perceive.evidence import ingest_client_evidence

        monkeypatch.setitem(os.environ, "CLASSIFIER", "on")
        monkeypatch.setitem(os.environ, "UNDERSTAND", "on")
        agent = _asked(_agent(), key="device_present")
        agent.state.diagnosis.pending_evidence_key = None  # nothing pending -> full reading
        canned = {
            "facts": {"power_cable": "unplugged"},
            "quotes": {"power_cable": "ištraukiau maitinimo laidą"},
            "type": "answer",
            "understood": "laidas ištrauktas",
            "confusion": "",
            "confidence": 0.9,
        }

        with patch("agent.perceive.understand.understand", return_value=canned):
            ingest_client_evidence(agent.state, agent.runtime, "Galim patikrinti ką man daryti?")

        assert "power_cable" not in agent.state.diagnosis.evidence
        assert agent.state.turn.perception["source"] == "llm"

    def test_a_quoted_fact_lands(self, db_connection, monkeypatch):
        import os

        from agent.perceive.evidence import ingest_client_evidence

        monkeypatch.setitem(os.environ, "CLASSIFIER", "on")
        monkeypatch.setitem(os.environ, "UNDERSTAND", "on")
        agent = _asked(_agent())
        agent.state.diagnosis.pending_evidence_key = None
        canned = {
            "facts": {"power_cable": "unplugged"},
            "quotes": {"power_cable": "ištraukiau laidą"},
            "type": "answer",
            "understood": "laidas ištrauktas",
            "confusion": "",
            "confidence": 0.9,
        }

        with patch("agent.perceive.understand.understand", return_value=canned):
            ingest_client_evidence(agent.state, agent.runtime, "Taip, ištraukiau laidą iš routerio")

        assert agent.state.diagnosis.evidence["power_cable"]["value"] == "unplugged"
