"""
Tests for the declarative detector glosses (Phase 3.11).

Universal answer MEANINGS live in agent/knowledge/detectors.yaml; refining how the
agent understands callers is a file edit. These guard: the shipped file loads and
covers every detector the engine uses, a file edit overrides the code defaults,
and a missing file fails soft to the code defaults.
"""

import agent.detectors as det


def _reload_with(tmp_path, monkeypatch, text):
    p = tmp_path / "detectors.yaml"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setattr(det, "_PATH", p)
    det.reload()


class TestShippedFile:
    def test_covers_every_engine_detector(self):
        det.reload()
        from agent.resolution import DETECTOR_GLOSSES

        # Every detector type the engine knows must be editable in the file —
        # otherwise "tuning without code" silently stops being true for it.
        expected = set(DETECTOR_GLOSSES) | {"instruct_done", "ticket_consent"}
        for name in expected:
            assert det.glosses(name), f"detector '{name}' missing from detectors.yaml"

    def test_result_report_counts_as_done(self):
        det.reload()
        g = det.glosses("instruct_done")
        assert "REZULTAT" in g["done"]  # the live-call lesson stays encoded

    def test_lauksiu_is_consent(self):
        det.reload()
        assert "lauksiu" in det.glosses("ticket_consent")["yes"]


class TestOverridesAndFailSoft:
    def test_file_overrides_code(self, tmp_path, monkeypatch):
        _reload_with(
            tmp_path,
            monkeypatch,
            "detectors:\n  yes_no:\n    'yes': mano nauja reikšmė\n    'no': ne\n",
        )
        assert det.glosses("yes_no")["yes"] == "mano nauja reikšmė"
        # A detector absent from the file still resolves from code defaults.
        assert det.glosses("instruct_done")
        det.reload()

    def test_missing_file_falls_back_to_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(det, "_PATH", tmp_path / "nope.yaml")
        det.reload()
        assert det.glosses("yes_no")  # from resolution.DETECTOR_GLOSSES
        assert det.glosses("ticket_consent")  # from _EXTRA_DEFAULTS
        det.reload()
