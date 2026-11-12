"""
R4 perception merge — one LLM call returns BOTH the understanding read and the
active step's classification; the walker consumes the cached read instead of a
second round-trip. Tests patch the LLM boundary only.
"""

from types import SimpleNamespace
from unittest.mock import patch

from agent.graph_v2.state import GraphState, TurnScratch
from agent.perceive import understand as und

from tests.engine_fakes import as_call

FUNCTION = "Suvokimo sujungimas"


class TestMergedUnderstand:
    def _call(self, payload, step_options=None):
        with patch("src.services.llm.client.llm_json_completion", return_value=payload):
            return und.understand(
                "Taip, keičiau routerį.",
                anchor="Ar neseniai keitėte routerį?",
                needs="",
                ledger_summary="",
                step_options=step_options,
            )

    def test_zingsnis_made_from_status_and_quoted_fact(self):
        # 2026-11-06: the model returns a reply STATUS and the facts; the step's label is
        # made from the fact the step's `answers` name. A quoted fact = heard (confidence 1).
        u = self._call(
            {
                "facts": {"changed_device": {"value": "yes", "quote": "keičiau routerį"}},
                "type": "answer",
                "understood": "keitė routerį",
                "confidence": 0.9,
                "status": "answered",
            },
            step_options={"yes": "keitė įrangą", "no": "nekeitė"},
        )
        assert u["status"] == "answered"
        # No `answers` given -> no label can be made: not an answer to THIS step.
        assert u["step"]["label"] == "unclear"

    def test_label_from_fact_via_answers(self):
        with patch(
            "src.services.llm.client.llm_json_completion",
            return_value={
                "facts": {"changed_device": {"value": "yes", "quote": "keičiau routerį"}},
                "type": "answer",
                "confidence": 0.9,
                "status": "answered",
            },
        ):
            u = und.understand(
                "Taip, keičiau routerį.",
                anchor="Ar neseniai keitėte routerį?",
                needs="",
                ledger_summary="",
                step_options={"yes": "keitė", "no": "nekeitė"},
                step_answers={"yes": "changed_device=yes", "no": "changed_device=no"},
            )
        assert u["step"] == {
            "label": "yes",
            "is_answer": True,
            "internally_inconsistent": False,
            "confidence": 1.0,
        }

    def test_answered_without_the_fact_is_not_an_answer(self):
        # „Aha, supratau" — answered, but nothing the step waits for: asked again (phantom).
        step = und.step_from_status(
            "answered", {}, {}, {"yes": "a", "no": "b"}, {"yes": "x=yes", "no": "x=no"}
        )
        # No value comes from it; but it is not „still doing" — the engine's own readers
        # („ištraukiau ir įkišau atgal" = done) still read the sentence (eval S6).
        assert step["label"] == "unclear" and step["is_answer"] is True

    def test_unquoted_fact_is_a_guess(self):
        step = und.step_from_status(
            "answered", {"x": "yes"}, {}, {"yes": "a", "no": "b"}, {"yes": "x=yes", "no": "x=no"}
        )
        assert step["label"] == "yes" and step["confidence"] < 1.0

    def test_instruction_status(self):
        opts = {"done": "padarė", "waiting": "dar daro"}
        assert und.step_from_status("answered", {}, {}, opts, None)["label"] == "done"
        doing = und.step_from_status("doing", {}, {}, opts, None)
        assert doing["label"] == "waiting" and doing["is_answer"] is False

    def test_unknown_status_is_dropped(self):
        u = self._call(
            {"facts": {}, "type": "answer", "confidence": 0.9, "status": "maybe"},
            step_options={"yes": "keitė", "no": "nekeitė"},
        )
        assert u["step"] is None and u["status"] is None

    def test_no_step_options_means_no_zingsnis(self):
        u = self._call(
            {
                "facts": {},
                "type": "answer",
                "confidence": 0.9,
                "step": {"label": "yes", "is_answer": True},
            }
        )
        assert u["step"] is None

    def test_step_block_rendered_only_with_options(self):
        base = und._system("K?", "", "", {})
        merged = und._system("K?", "", "", {}, {"yes": "sutinka", "no": "nesutinka"})
        assert '"status"' not in base
        assert '"status"' in merged
        assert "sutinka" in merged


class TestFactCatalog:
    """2026-11-06: every fact a caller can state, built from the knowledge files."""

    def test_ladder_facts_are_allowed(self):
        allowed = und._merged_allowed(None)
        assert allowed["wifi_on"] == {"yes", "no"}
        assert "restored" in allowed and "wifi_network" in allowed

    def test_telemetry_facts_are_not(self):
        from agent.contract import signals

        allowed = und._merged_allowed(None)
        assert not set(signals.get()) & set(allowed)

    def test_every_catalog_fact_can_be_said_back(self):
        from agent.fact_catalog import client_facts, said_back

        missing = [
            f"{key}={value}"
            for key, item in client_facts().items()
            for value in item.values
            if not said_back(key, value)
        ]
        assert missing == []

    def test_hedge_words(self):
        from agent.fact_catalog import hedged

        assert hedged("Taip, lyg ir veikia")
        assert hedged("Turbūt, dega.")
        assert not hedged("Galiu, palaukit")
        assert not hedged("Wi-Fi įjungtas")


def test_does_not_know_is_not_no():
    from agent import modules

    assert modules._does_not_know("Nežinau")
    assert not modules._does_not_know("Ne")
