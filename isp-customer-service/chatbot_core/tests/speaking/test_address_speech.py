"""Kalba — Adreso tarimas."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import TicketContext

from tests.tool_fakes import install_fake_tools

FUNCTION = "Adreso tarimas"

# --- from test_agent.py ---


class TestAddressSpeech:
    """How an address is SAID (Andrius, 2026-09-23): abbreviations spoken in full, the place
    in the locative when the address is stated, and everything in the genitive after „dėl"."""

    def test_the_address_is_stated_in_the_locative(self):
        from agent.voice_pipeline import speech_text as n

        assert n("Supratau — Šiauliai, Tilžės g. 60-3.") == (
            "Supratau — Šiauliuose, Tilžės gatvėje 60, butas 3."
        )

    def test_a_village_and_a_district_are_spoken_in_full(self):
        from agent.voice_pipeline import speech_text as n

        assert n("Supratau — Šiaulių r., Ginkūnų k., Žeimių g. 12-6.") == (
            "Supratau — Šiaulių rajone, Ginkūnų kaime, Žeimių gatvėje 12, butas 6."
        )

    def test_after_del_everything_is_in_the_genitive(self):
        from agent.voice_pipeline import speech_text as n

        assert n("Ar skambinate dėl Tilžės g. 60-7?") == (
            "Ar skambinate dėl Tilžės gatvės 60, buto 7?"
        )
        assert n("Ar skambinate dėl Žeimių g. 12, butas 6?") == (
            "Ar skambinate dėl Žeimių gatvės 12, buto 6?"
        )

    def test_a_reply_with_no_address_is_untouched(self):
        from agent.voice_pipeline import speech_text as n

        assert n("Jokio adreso čia nėra") == "Jokio adreso čia nėra"
        assert n("Perkraukite routerį ir pasakykite.") == "Perkraukite routerį ir pasakykite."
