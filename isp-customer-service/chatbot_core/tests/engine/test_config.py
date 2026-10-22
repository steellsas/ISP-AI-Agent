"""Variklis — Konfigūracija."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agent.call_record.finalizer import build_call_summary, finalize
from agent.graph_v2.state import TicketContext

from tests.tool_fakes import install_fake_tools

FUNCTION = "Konfigūracija"

# --- from test_agent.py ---


class TestAgentConfig:
    """Tests for agent configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        from agent.config import get_config

        config = get_config()

        assert config.max_turns == 50
        assert config.temperature == 0.3
        assert config.language == "lt"
