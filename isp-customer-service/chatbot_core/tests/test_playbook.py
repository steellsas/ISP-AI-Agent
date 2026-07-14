"""Unit tests for the playbook step server (agent/playbook.py).

Serving ONE step at a time is what stops a streaming LLM from dumping a whole
troubleshooting doc as a monologue.
"""

from agent.playbook import get_step, parse_steps, step_count

_DOC = """# Title

## Simptomai
Klientas sako X.

### Žingsnis 1: Lemputės
Paklausk, ar dega lemputės.

### Žingsnis 2: Laidas
Patikrink WAN laidą.

## Kada eskaluoti
Jei nepadeda.
"""


class TestParseSteps:
    def test_extracts_only_numbered_steps(self):
        steps = parse_steps(_DOC)
        assert len(steps) == 2  # Simptomai / Kada eskaluoti are NOT steps
        assert steps[0].startswith("### Žingsnis 1: Lemputės")
        assert steps[1].startswith("### Žingsnis 2: Laidas")

    def test_step_body_is_included_but_not_next_heading(self):
        steps = parse_steps(_DOC)
        assert "Paklausk, ar dega lemputės." in steps[0]
        assert "Žingsnis 2" not in steps[0]  # stops at the next step
        # trailing non-step section is not swallowed into the last step
        assert "Kada eskaluoti" in steps[1]  # last step runs to EOF (acceptable)

    def test_empty_and_no_steps(self):
        assert parse_steps("") == []
        assert parse_steps("# Just a title\nno steps here") == []


class TestRealPlaybook:
    DOC = "troubleshooting/internet_pakeistas_routeris_mac"

    def test_mac_playbook_has_steps(self):
        assert step_count(self.DOC) == 6

    def test_get_step_returns_the_right_section(self):
        assert get_step(self.DOC, 0).startswith("### Žingsnis 1")
        assert "lizd" in get_step(self.DOC, 1).lower()  # 2a: which port
        assert "WAN" in get_step(self.DOC, 2)  # 2b: reconnect to WAN
        assert "update_mac" in get_step(self.DOC, 3)  # step 3 is the bind
        assert "atsirad" in get_step(self.DOC, 4)  # step 4 asks if restored
        assert "kliento pus" in get_step(self.DOC, 5).lower()  # step 5 client-side

    def test_out_of_range_and_missing(self):
        assert get_step(self.DOC, 99) is None
        assert get_step("troubleshooting/does_not_exist", 0) is None
        assert step_count("troubleshooting/does_not_exist") == 0
