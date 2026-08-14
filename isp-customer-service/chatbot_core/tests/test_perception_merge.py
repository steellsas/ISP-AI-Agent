"""
R4 perception merge — one LLM call returns BOTH the understanding read and the
active step's classification; the walker consumes the cached read instead of a
second round-trip. Tests patch the LLM boundary only.
"""

from types import SimpleNamespace
from unittest.mock import patch

from agent import understand as und
from agent.walker_flow import _cached_perception


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
                "faktai": {},
                "tipas": "atsakymas",
                "supratau": "keitė routerį",
                "pasitikejimas": 0.9,
                "zingsnis": {"label": "yes", "is_answer": True, "confidence": 0.95},
            },
            step_options={"yes": "keitė įrangą", "no": "nekeitė"},
        )
        assert u["zingsnis"] == {
            "label": "yes",
            "is_answer": True,
            "internally_inconsistent": False,
            "confidence": 0.95,
        }

    def test_unknown_label_is_dropped(self):
        u = self._call(
            {
                "faktai": {},
                "tipas": "atsakymas",
                "pasitikejimas": 0.9,
                "zingsnis": {"label": "maybe", "is_answer": True},
            },
            step_options={"yes": "keitė", "no": "nekeitė"},
        )
        assert u["zingsnis"] is None

    def test_no_step_options_means_no_zingsnis(self):
        u = self._call(
            {
                "faktai": {},
                "tipas": "atsakymas",
                "pasitikejimas": 0.9,
                "zingsnis": {"label": "yes", "is_answer": True},
            }
        )
        assert u["zingsnis"] is None

    def test_step_block_rendered_only_with_options(self):
        base = und._system("K?", "", "", {})
        merged = und._system("K?", "", "", {}, {"yes": "sutinka", "no": "nesutinka"})
        assert "zingsnis" not in base
        assert '"zingsnis"' in merged
        assert "sutinka" in merged


class TestWalkerConsumesCache:
    def _step(self):
        return SimpleNamespace(id="confirm_change", detector="yes_no", on=("yes", "no"), hint="")

    def test_cache_hit_returns_observation(self):
        engine = SimpleNamespace(
            _perception_step={
                "step_id": "confirm_change",
                "input": "Taip, keičiau.",
                "obs": {"label": "yes", "is_answer": True, "confidence": 0.9},
            }
        )
        obs = _cached_perception(engine, self._step(), "Taip, keičiau.")
        assert obs is not None and obs.label == "yes" and obs.confidence == 0.9

    def test_cache_misses_on_other_step_or_input(self):
        engine = SimpleNamespace(
            _perception_step={
                "step_id": "confirm_change",
                "input": "Taip, keičiau.",
                "obs": {"label": "yes", "is_answer": True},
            }
        )
        other_step = SimpleNamespace(id="dr_power", detector="yes_no", on=("yes", "no"), hint="")
        assert _cached_perception(engine, other_step, "Taip, keičiau.") is None
        assert _cached_perception(engine, self._step(), "Kitas tekstas") is None
        engine._perception_step = None
        assert _cached_perception(engine, self._step(), "Taip, keičiau.") is None
