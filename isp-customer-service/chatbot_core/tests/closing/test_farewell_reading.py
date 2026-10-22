"""Pabaiga — Atsisveikinimo ir sutikimo skaitymas."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import TicketContext

from tests.tool_fakes import install_fake_tools

FUNCTION = "Atsisveikinimo ir sutikimo skaitymas"

# --- from test_agent.py ---


class TestConsentAndFarewellWords:
    """The consent and farewell readers on garbled / indirect words."""

    def test_lauksiu_skambucio_is_consent_not_decline(self):
        from agent.perceive.detectors import detect_ticket_consent

        assert detect_ticket_consent("Lauksiu skambučio, ačiū") == "yes"

    def test_farewell_stt_garbles_close(self):
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Neturiu, neturiu, visą gerą") is True
        assert detect_farewell("visa gera, ačiū") is True


class TestFarewellPurity:
    def test_garbled_content_with_ne_is_not_a_farewell(self, db_connection):
        # Live 2026-08-10: "Ne daganiai 1." (=nedega nė viena) fast-forwarded
        # the ticket dialogue to done-with-defaults. The bare-"ne" fallback now
        # requires EVERY token to be a known closing word.
        from agent.perceive.detectors import detect_farewell

        assert detect_farewell("Ne daganiai 1.") is False
        assert detect_farewell("Ne viena") is False
        # Policy 2026-08-20 (Andrius): a bare "Ne." is an ANSWER — its
        # question owner clarifies; never a farewell.
        assert detect_farewell("Ne.") is False
        assert detect_farewell("Ne, ačiū") is True
        assert detect_farewell("viskas gerai") is True
        assert detect_farewell("viso gero") is True
