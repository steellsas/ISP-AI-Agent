"""knowledge/limits.yaml and policies.yaml: every limit is used, env overrides win,
and an unknown name fails loudly."""

import re
from pathlib import Path

import pytest
from agent.contract import limits, policies
from agent.contract.schema import KnowledgeError

SRC = Path(__file__).resolve().parents[1] / "src"


def _code_names() -> set[str]:
    text = "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.py"))
    return set(re.findall(r'limits\.get\(\s*"(\w+)"', text))


def test_every_code_limit_is_declared():
    assert _code_names() - limits.names() == set()


def test_every_declared_limit_is_used():
    assert limits.names() - _code_names() == set()


def test_env_override_wins(monkeypatch):
    assert limits.get("problem_gate_max_turns") == 5
    monkeypatch.setenv("GATE_MAX_TURNS", "7")
    assert limits.get("problem_gate_max_turns") == 7
    monkeypatch.setenv("ASR_MIN_AUDIO_S", "0.5")
    assert limits.get("asr_min_audio_s") == 0.5


def test_bad_env_value_keeps_the_file_value(monkeypatch):
    monkeypatch.setenv("ENDPOINT_SLOW_MS", "soon")
    assert limits.get("endpoint_slow_ms") == 1400


def test_unknown_limit_fails():
    with pytest.raises(KnowledgeError, match="no limit 'nope'"):
        limits.get("nope")


def test_gate_policy_comes_from_limits():
    from agent.decide.solver_guard import default_policy

    assert default_policy() == {
        "confidence_floor": 0.4,
        "low_conf_max": 3,
        "cycles_max": 3,
        "internal_hops_max": 2,
    }


def test_identification_gated_tools_come_from_policies():
    assert set(policies.get().identified_customer_required) == {
        "diagnose_connection",
        "update_mac",
        "reset_port",
        "create_ticket",
    }


def test_identified_customer_tools_exist():
    from agent.tools import REAL_TOOLS

    names = {t.name for t in REAL_TOOLS}
    assert set(policies.get().identified_customer_required) <= names
