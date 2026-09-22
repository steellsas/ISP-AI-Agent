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

    def test_zingsnis_parsed_and_validated(self):
        u = self._call(
            {
                "facts": {},
                "type": "answer",
                "understood": "keitė routerį",
                "confidence": 0.9,
                "step": {"label": "yes", "is_answer": True, "confidence": 0.95},
            },
            step_options={"yes": "keitė įrangą", "no": "nekeitė"},
        )
        assert u["step"] == {
            "label": "yes",
            "is_answer": True,
            "internally_inconsistent": False,
            "confidence": 0.95,
        }

    def test_unknown_label_is_dropped(self):
        u = self._call(
            {
                "facts": {},
                "type": "answer",
                "confidence": 0.9,
                "step": {"label": "maybe", "is_answer": True},
            },
            step_options={"yes": "keitė", "no": "nekeitė"},
        )
        assert u["step"] is None

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
        assert "step" not in base
        assert '"step"' in merged
        assert "sutinka" in merged
