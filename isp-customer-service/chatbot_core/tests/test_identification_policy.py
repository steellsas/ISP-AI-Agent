"""
Tests for the declarative identification policy (Phase 3.8 step 5d).

The policy KNOBS (offer the phone address, require an apartment, extra verification
questions) live in agent/knowledge/identification.yaml; these guard that the loader reads
them, fails loudly on a missing file, and that an extra question turns into injected guidance.
"""

import agent.identification as ident
import pytest
from agent.contract import loader
from agent.contract.schema import KnowledgeError


def _reload_with(tmp_path, monkeypatch, text):
    p = tmp_path / "identification.yaml"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setattr(ident, "_PATH", p)
    loader.reload()


class TestDefaults:
    def test_shipped_file_offers_address_and_no_extra_questions(self):
        loader.reload()
        assert ident.offer_phone_address() is True
        assert ident.require_apartment() is True
        # default ships with no extra questions → no guidance injected
        assert ident.extra_questions_guidance() is None


class TestKnobs:
    def test_extra_question_becomes_guidance(self, tmp_path, monkeypatch):
        _reload_with(
            tmp_path,
            monkeypatch,
            "identification:\n  extra_questions: [name]\n",
        )
        g = ident.extra_questions_guidance()
        assert g and "O kaip į jus kreiptis — koks jūsų vardas?" in g
        loader.reload()  # restore shipped file for other tests

    def test_offer_phone_address_knob_off(self, tmp_path, monkeypatch):
        _reload_with(tmp_path, monkeypatch, "identification:\n  offer_phone_address: false\n")
        assert ident.offer_phone_address() is False
        loader.reload()

    def test_missing_file_fails_loudly(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ident, "_PATH", tmp_path / "does_not_exist.yaml")
        loader.reload()
        with pytest.raises(KnowledgeError, match="does_not_exist.yaml"):
            ident.offer_phone_address()
        loader.reload()

    def test_unset_knob_takes_its_default(self, tmp_path, monkeypatch):
        _reload_with(tmp_path, monkeypatch, "identification: {}\n")
        assert ident.offer_phone_address() is True
        loader.reload()
