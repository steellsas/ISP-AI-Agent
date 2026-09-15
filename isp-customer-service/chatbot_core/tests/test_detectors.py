"""
Tests for the declarative detector glosses (Phase 3.11).

Universal answer MEANINGS live in agent/knowledge/detectors.yaml; refining how the
agent understands callers is a file edit. These guard: the shipped file loads and
covers every detector the engine uses and a file edit changes the meaning.
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
        from agent.contract.schema import CODE_DETECTORS

        # Every detector type the engine knows must be editable in the file —
        # otherwise "tuning without code" silently stops being true for it.
        for name in CODE_DETECTORS | {"instruct_done", "ticket_consent"}:
            assert det.glosses(name), f"detector '{name}' missing from detectors.yaml"

    def test_result_report_counts_as_done(self):
        det.reload()
        g = det.glosses("instruct_done")
        assert "REZULTAT" in g["done"]  # the live-call lesson stays encoded

    def test_lauksiu_is_consent(self):
        det.reload()
        assert "lauksiu" in det.glosses("ticket_consent")["yes"]


class TestFileEdits:
    def test_file_edit_changes_the_meaning(self, tmp_path, monkeypatch):
        _reload_with(
            tmp_path,
            monkeypatch,
            "detectors:\n  yes_no:\n    'yes': mano nauja reikšmė\n    'no': ne\n",
        )
        assert det.glosses("yes_no")["yes"] == "mano nauja reikšmė"
        assert det.glosses("instruct_done") == {}  # no code copy behind the file
        det.reload()
