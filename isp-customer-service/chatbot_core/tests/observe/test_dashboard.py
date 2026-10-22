"""Stebėsena — Dashboard."""

import pytest

FUNCTION = "Dashboard"

# --- from test_wave9_promises.py ---


def test_scenario_reset_is_wired_in_the_dashboard():
    """T6: a picked scenario's call starts from the seeded DB."""
    from pathlib import Path

    js = Path(__file__).resolve().parents[2] / "src" / "app" / "static" / "js"
    app = (js / "app.js").read_text(encoding="utf-8")
    assert "Scenarios.current()" in app and "/admin/db/reset" in app
    assert "current: () => current" in (js / "scenarios.js").read_text(encoding="utf-8")
