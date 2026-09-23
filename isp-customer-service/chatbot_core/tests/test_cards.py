"""Wave 3: a fault card is a contract a technician can edit.

The diagnosis used to live in a decision tree in code, so a new fault meant new Python.
Now a card declares when it is a CANDIDATE, what would settle it and how it is fixed —
and because the file is hand-edited, a typo must stop the app at startup rather than
quietly never matching anything.
"""

import pytest
from agent.contract import cards as catalog
from agent.contract.loader import _check_cards
from agent.contract.schema import Condition, FaultCard, KnowledgeError, ModuleSpec


class TestACondition:
    """`fact=value` — and "not asked yet" is not "not so"."""

    def test_it_reads_a_fact(self):
        c = Condition.parse("traffic=none")
        assert c.holds({"traffic": "none"}) is True
        assert c.holds({"traffic": "flowing"}) is False

    def test_an_unknown_fact_is_neither_true_nor_false(self):
        """The difference between a line we checked and a line we never saw."""
        assert Condition.parse("traffic=none").holds({}) is None

    def test_it_reads_a_denial(self):
        c = Condition.parse("device_registered!=foreign")
        assert c.holds({"device_registered": "match"}) is True
        assert c.holds({"device_registered": "foreign"}) is False

    @pytest.mark.parametrize("text", ["traffic", "traffic == none", "TRAFFIC=none", "=none"])
    def test_nonsense_is_refused(self, text):
        with pytest.raises(ValueError):
            Condition.parse(text)


class TestTheRouterHungCard:
    """The first converted card: nine v1 steps as three module calls."""

    def test_it_says_when_it_is_a_candidate(self):
        card = catalog.card("router_hung")
        facts = {
            "node_reachable": "yes",
            "line_link": "up",
            "device_seen": "yes",
            "dhcp": "ok",
            "traffic": "none",
        }
        wanted, _any = card.when.parsed()
        assert all(c.holds(facts) for c in wanted)

    def test_traffic_flowing_is_not_this_card(self):
        card = catalog.card("router_hung")
        wanted, _any = card.when.parsed()
        assert not all(
            c.holds({**dict.fromkeys(("node_reachable",), "yes"), "traffic": "flowing"})
            for c in wanted
        )

    def test_the_faults_that_own_the_case_instead_rule_it_out(self):
        card = catalog.card("router_hung")
        out = [Condition.parse(c) for c in card.rules_out]
        assert any(c.holds({"device_registered": "foreign"}) for c in out)
        assert any(c.holds({"area_outage": "yes"}) for c in out)

    def test_the_fix_is_three_modules(self):
        card = catalog.card("router_hung")
        steps = card.solution[0].steps
        assert [s.module for s in steps] == ["reach", "reboot", "verify"]
        assert steps[1].args == {"device": "router", "method": "power"}
        # telemetry saw no flap -> the reboot did not really happen: clarify and retry once
        assert steps[1].on_fail.args["reason"] == "no_flap"

    def test_one_device_is_another_cards_case(self):
        card = catalog.card("router_hung")
        assert card.needs["fail_scope"].values["one"] == "hands_to=healthy_to_router"


class TestABrokenCardStopsTheApp:
    """Every one of these is a typo a technician can make in a YAML file."""

    def _card(self, **over) -> FaultCard:
        base = {
            "fault": "x",
            "service": "internet",
            "when": {"all": ["traffic=none"]},
            "solution": [
                {"when": [], "steps": [{"module": "reboot", "args": {"device": "router"}}]}
            ],
        }
        return FaultCard(**{**base, **over})

    def _modules(self) -> dict[str, ModuleSpec]:
        return catalog.modules()

    def _check(self, card: FaultCard):
        _check_cards({card.fault: card}, self._modules())

    def test_a_good_card_passes(self):
        self._check(self._card())

    def test_a_misspelled_fact(self):
        with pytest.raises(KnowledgeError, match="unknown fact 'trafic'"):
            self._check(self._card(when={"all": ["trafic=none"]}))

    def test_a_value_the_fact_never_takes(self):
        with pytest.raises(KnowledgeError, match="is never 'non'"):
            self._check(self._card(when={"all": ["traffic=non"]}))

    def test_a_module_that_does_not_exist(self):
        with pytest.raises(KnowledgeError, match="unknown module 'reboott'"):
            self._check(
                self._card(solution=[{"steps": [{"module": "reboott", "args": {"device": "r"}}]}])
            )

    def test_a_module_call_missing_its_argument(self):
        with pytest.raises(KnowledgeError, match="needs 'device'"):
            self._check(self._card(solution=[{"steps": [{"module": "reboot"}]}]))

    def test_an_argument_outside_its_closed_set(self):
        with pytest.raises(KnowledgeError, match="not one of"):
            self._check(
                self._card(
                    solution=[
                        {"steps": [{"module": "reboot", "args": {"device": "r", "method": "kick"}}]}
                    ]
                )
            )

    def test_handing_over_to_a_card_that_is_not_there(self):
        with pytest.raises(KnowledgeError, match="unknown card 'ghost'"):
            self._check(self._card(solution=[{"hands_to": "ghost"}]))

    def test_a_phrase_key_that_is_not_in_the_locale(self):
        with pytest.raises(KnowledgeError, match="explain phrase"):
            self._check(self._card(explain={"conclusion": "pack.nope.gloss"}))


def test_every_module_a_card_can_call_declares_what_it_does():
    for name, spec in catalog.modules().items():
        assert spec.goal, name
        assert spec.kind in ("ask", "instruct", "action", "verify", "escalate"), name
        # An action runs a tool; a verification reads one; the rest speak.
        if spec.kind == "action":
            assert spec.tool, name
        if spec.kind == "verify":
            assert spec.probe, name


class TestEveryV1PackHasACard:
    """Nothing may be lost in the conversion: the v1 packs and the v2 cards are the same
    set of faults, by id (the locale keys and the ticket reasons hang off those ids)."""

    def test_no_v1_fault_was_lost(self):
        import yaml
        from agent.contract.schema import KNOWLEDGE_DIR

        v1 = {
            yaml.safe_load(p.read_text(encoding="utf-8"))["verdict"]
            for p in (KNOWLEDGE_DIR / "faults").glob("*.yaml")
        }
        # The reverse is no longer true: wave 4 added the NEWS cards, which the packs never
        # had (they were branches in the tree).
        assert v1 <= set(catalog.cards())

    def test_a_news_card_tells_and_a_fault_card_fixes(self):
        for name, card in catalog.cards().items():
            if card.news:
                assert not card.solution and not card.needs, f"{name}: news does not ask or act"
            elif not card.fallback:
                assert card.solution, f"{name}: a fault card must say how it is fixed"

    def test_exactly_one_card_is_the_honest_fallback(self):
        fallbacks = [c.fault for c in catalog.cards().values() if c.fallback]
        assert fallbacks == ["unclear_fault"]
