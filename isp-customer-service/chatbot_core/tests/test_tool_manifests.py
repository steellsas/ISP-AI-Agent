"""Wave 2c: a tool is a contract, not a function (P-7).

Every tool the engine can call declares what it does, who may call it, how long it may
take and what happens when it does not answer. These tests are the contract's guard: a
new tool without a manifest, or a manifest that drifts from the rules the gateway
actually enforces, fails here — not on a call.
"""

import json

import pytest
from agent.contract import tools as manifests
from agent.contract.schema import ToolManifest
from pydantic import ValidationError


def _tool_names() -> set[str]:
    """Every name the provider can execute: the LLM-facing tools and the engine's own."""
    from agent.tooling.local_provider import ENGINE_TOOLS
    from agent.tools import REAL_TOOLS

    return {t.name for t in REAL_TOOLS} | set(ENGINE_TOOLS)


def test_every_tool_has_a_manifest():
    missing = sorted(_tool_names() - set(manifests.names()))
    assert not missing, f"tools without a manifest: {missing}"


def test_every_manifest_names_a_real_tool():
    """A manifest for a tool that no longer exists is a lie the engine would read."""
    unknown = sorted(set(manifests.names()) - _tool_names())
    assert not unknown, f"manifests for unknown tools: {unknown}"


def test_the_gate_refuses_what_the_manifest_requires(make_state, make_runtime):
    """The manifest IS the gate: a tool that requires an identified caller is refused
    while nobody is identified, and runs once they are."""
    from agent.tooling.gateway import gate

    state, rt = make_state("+37060020112"), make_runtime()
    for name, m in manifests.get().items():
        if "identified" not in m.requires:
            continue
        state.identity.customer_id = None
        assert "not_identified" in (gate(state, rt, name, {}) or ""), name
        state.identity.customer_id = "CUST009"
        assert gate(state, rt, name, {"customer_id": "CUST009"}) is None, name
        assert "id_mismatch" in (gate(state, rt, name, {"customer_id": "CUST001"}) or ""), name


def test_an_action_is_audited_and_capped():
    """A mutation on the customer's line is logged and cannot repeat itself in one call."""
    for name, m in manifests.get().items():
        if m.capability == "action":
            assert m.audit, f"{name}: an action must be audited"
            assert m.guards.max_per_call, f"{name}: an action needs max_per_call"
            assert m.on_failure.fallback == "ticket", f"{name}: a failed action needs a technician"


def test_a_slow_tool_tells_the_caller_to_wait():
    """Whatever takes seconds in production gets a filler line, so voice is never silent."""
    for name, m in manifests.get().items():
        if m.capability in ("probe", "crm") and m.timeout_s >= 5:
            assert m.filler_key, f"{name}: a slow lookup needs a filler_key"


def test_every_failure_path_reaches_the_operators_or_goes_on_quietly():
    for name, m in manifests.get().items():
        if m.on_failure.fallback != "skip":
            assert m.on_failure.say_key, f"{name}: the caller must hear something"


BASE = {
    "tool": "x",
    "capability": "probe",
    "adapter": "demo_db",
    "timeout_s": 5,
    "on_failure": {"say_key": "tools.unavailable_probe", "fallback": "ask_client"},
}

# (what is wrong with the manifest, the override)
BROKEN = [
    ("unknown capability", {"capability": "magic"}),
    ("adapter that no registry can answer", {"adapter": "postgres"}),
    ("a typo instead of a field", {"timeuot_s": 5}),
    ("no failure path at all", {"on_failure": None}),
    ("a fallback the caller never hears", {"on_failure": {"fallback": "ticket"}}),
    ("hours that are not hours", {"guards": {"allowed_hours": "8am-10pm"}}),
    ("a timeout that cannot pass", {"timeout_s": 0}),
    ("a requirement the gate does not know", {"requires": ["paid_up"]}),
]


@pytest.mark.parametrize("what, override", BROKEN)
def test_a_broken_manifest_is_refused(what, override):
    spec = {**BASE, **override}
    if override.get("on_failure") is None:
        spec.pop("on_failure")
    with pytest.raises(ValidationError):
        ToolManifest(**spec)


def test_a_good_manifest_parses():
    m = ToolManifest(**BASE)
    assert m.retries == 0 and m.audit is False and m.guards.max_per_call is None


def test_every_manifest_names_an_adapter_that_can_answer():
    """A manifest that points at an adapter nobody registered stops the app at startup —
    a switch to mcp:network before that client exists must not fall back to the demo DB."""
    from agent.contract import loader
    from agent.contract.schema import KnowledgeError
    from agent.tooling import adapters

    known = adapters.known()
    assert {m.adapter for m in manifests.get().values()} <= known

    knowledge = loader.validate()
    broken = knowledge.tools["reset_port"].model_copy(update={"adapter": "mcp:network"})
    with pytest.raises(KnowledgeError, match="not registered"):
        loader._check_adapters(type(knowledge)(tools={**knowledge.tools, "reset_port": broken}))


def test_the_fake_adapter_is_only_reachable_through_a_manifest():
    """Nothing in the shipped manifests points at `fake` — it exists for tests only."""
    assert all(m.adapter != "fake" for m in manifests.get().values())


class TestReturnsIsAPromise:
    """`returns` says which ledger facts a tool may establish. The gateway holds it to
    that: a fact from nowhere is how a diagnosis stops being traceable."""

    _VERDICT = {
        "success": True,
        "verdict": {"reason": "router_hung", "side": "customer", "group": "B6"},
        "signals": {"traffic": "none"},
    }

    def test_the_diagnosis_declares_the_facts_it_sets(self, make_state, make_runtime):
        from agent.execute.observe import update_state_from_observation

        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST112"
        update_state_from_observation(state, rt, "diagnose_connection", json.dumps(self._VERDICT))

        wrote = set(state.diagnosis.evidence)
        assert wrote, "the observation should have set the telemetry facts"
        assert wrote <= set(manifests.manifest("diagnose_connection").returns)

    def test_an_undeclared_fact_is_traced(self, make_state, make_runtime):
        """Declaration drift is reported, not silently dropped — the reading the engine
        just made is still the truth of the call."""
        from agent.tooling.gateway import _check_returns

        events: list[dict] = []
        recorder = type(
            "Rec", (), {"emit": lambda _s, kind, **f: events.append({"type": kind, **f})}
        )()
        state, rt = make_state("+37060020112"), make_runtime(tracer=recorder)
        spec = manifests.manifest("diagnose_connection").model_copy(update={"returns": ["verdict"]})
        state.diagnosis.evidence = {"verdict": {}, "side": {}}

        _check_returns(state, rt, spec, "diagnose_connection", before=set())

        event = next(e for e in events if e["type"] == "returns_violation")
        assert event["keys"] == ["side"] and event["tool"] == "diagnose_connection"

    def test_a_tool_that_declares_nothing_touches_no_facts(self, make_state, make_runtime):
        from agent.execute.observe import update_state_from_observation

        state, rt = make_state("+37060020112"), make_runtime()
        state.identity.customer_id = "CUST112"
        for name, payload in (
            ("check_outages", {"success": True, "affected": True}),
            ("create_ticket", {"success": True, "ticket_id": "T-1"}),
        ):
            assert manifests.manifest(name).returns == []
            update_state_from_observation(state, rt, name, json.dumps(payload))
        assert state.diagnosis.evidence == {}


def test_a_plan_may_only_name_a_tool_that_has_a_manifest():
    """The effect gate and the gateway read the same list now."""
    from agent.decide.gate import _tool_names

    assert _tool_names() == frozenset(manifests.names())
