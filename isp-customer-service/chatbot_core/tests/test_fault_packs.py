"""
Fault packs (R5) — one file per fault + reusable modules + meta/tags.

The heart is the EQUIVALENCE test: the split pack files with module calls must
build byte-identical Strategy structures to the pre-split monolith (snapshot in
tests/data/strategies_snapshot.json, captured before the migration). If a pack
edit changes the tree, the snapshot must be updated DELIBERATELY.
"""

import json
from pathlib import Path

from agent.faults import (
    _modules,
    build_strategy,
    depends_on,
    fault_meta,
    find_by_tag,
    step_options,
)

_SNAPSHOT = json.loads(
    (Path(__file__).parent / "data" / "strategies_snapshot.json").read_text(encoding="utf-8-sig")
)


def _dump(strat):
    return {
        "rag_doc": strat.rag_doc,
        "steps": [
            {
                "id": s.id,
                "kind": s.kind.value,
                "detector": s.detector,
                "on": dict(s.on),
                "goto": s.goto,
                "tools": sorted(s.tools),
                "tool_actions": list(s.tool_actions),
                "rag_section": s.rag_section,
                "consent": s.consent,
            }
            for s in strat.steps
        ],
    }


class TestEquivalence:
    """Split packs + expanded modules == the pre-split monolith, structurally."""

    def test_foreign_mac_matches_snapshot(self):
        assert _dump(build_strategy("foreign_mac")) == _SNAPSHOT["foreign_mac"]

    def test_healthy_to_router_matches_snapshot(self):
        assert _dump(build_strategy("healthy_to_router")) == _SNAPSHOT["healthy_to_router"]

    def test_no_mac_observed_matches_snapshot(self):
        assert _dump(build_strategy("no_mac_observed")) == _SNAPSHOT["no_mac_observed"]

    def test_step_options_resolve_through_modules(self):
        # answers must be found for module-expanded ids too (instance override wins)
        assert step_options("no_mac_observed", "dr_verify") == {
            "yes": "prijungtame kompiuteryje internetas dabar veikia",
            "no": "prijungtame kompiuteryje interneto vis tiek nėra",
        }
        assert step_options("foreign_mac", "confirm_change")


class TestModulesAndMeta:
    def test_modules_load(self):
        mods = _modules()
        assert "patikrinti_ar_atsirado" in mods
        assert "priristi_mac" in mods
        assert mods["patikrinti_ar_atsirado"]["isejimai"] == ["pavyko", "nepavyko"]

    def test_meta_and_tags(self):
        meta = fault_meta("no_mac_observed")
        assert meta.get("domenas") == "internet"
        assert "tiltas" in meta.get("tags", [])
        by_tag = find_by_tag("nera_interneto")
        assert set(by_tag) == {"foreign_mac", "healthy_to_router", "no_mac_observed"}

    def test_depends_on_default_empty(self):
        assert depends_on("foreign_mac") == []
        assert depends_on("nezinomas") == []


class TestEvidenceDeclared:
    """A variantas (2026-08-13): every internet pack declares its analysis
    knowledge — the perception vocabulary and the hypothesis logic."""

    def test_all_three_packs_have_evidence(self):
        from agent.evidence import spec_for

        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            spec = spec_for(verdict)
            assert spec is not None, verdict
            assert spec.get("client"), verdict

    def test_foreign_mac_facts_and_confirmation(self):
        from agent.evidence import spec_for

        spec = spec_for("foreign_mac")
        assert set(spec["client"]) == {"changed_device", "cable_port"}
        assert spec["patvirtinta_kai"] == ["changed_device=keite"]
        # perception vocabulary: canonical values are declared per fact
        assert set(spec["client"]["changed_device"]["atsakymai"]) == {"keite", "nekeite"}

    def test_healthy_to_router_conditional_asking(self):
        from agent.evidence import spec_for

        spec = spec_for("healthy_to_router")
        assert spec["client"]["connection_type"]["kada"] == ["fail_device=kompiuteris"]
        assert spec["client"]["rebooted"]["kada"] == ["fail_scope=visuose"]

    def test_reikia_present_for_narrator_directives(self):
        """`reikia` is the future narrator directive (skriptas -> mąstymas) —
        every declared fact must state its GOAL, not only the wording."""
        from agent.evidence import spec_for

        for verdict in ("foreign_mac", "healthy_to_router", "no_mac_observed"):
            for key, item in spec_for(verdict)["client"].items():
                assert item.get("reikia"), f"{verdict}.{key} be 'reikia'"
