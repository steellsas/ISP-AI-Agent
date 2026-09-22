"""Wave 3e: the agent never gives up on a device (P-8).

The CRM may not know what the caller has, and the caller may have bought their own. So an
instruction comes from the most specific level that exists — the model, its manufacturer
family, or the basic device, which is always there.

The other half is that what the caller SEES becomes a fact: "INTERNET orange" on a TP-Link
and "the internet light is off" on an unknown box both mean `wan_link=down`, so no fault
card ever has to know a model.
"""

import pytest
from agent.contract import equipment as catalog
from agent.equipment import for_device, for_signals


class TestTheLadder:
    def test_a_known_manufacturer_wins(self):
        device = for_device("router", "TP-Link Archer C6")
        assert device.level == "tplink"

    def test_an_unknown_make_still_gets_the_basic_device(self):
        """A router we have never described is still a router: pull the power lead."""
        device = for_device("router", "Huawei HG8245")
        assert device.level == "router"
        assert device.how_to("reboot.power")

    def test_nothing_known_at_all_still_answers(self):
        assert for_device("router", None).level == "router"
        assert for_signals({}).level == "router"

    def test_what_is_not_described_is_not_offered(self):
        """The basic level has no button instruction, so the agent does not invent where
        the button is — it reboots from the power lead, which is true of every router."""
        basic = for_device("router", None)
        assert basic.can("reboot.power") and not basic.can("reboot.button")

    def test_a_family_inherits_what_it_does_not_override(self):
        family, basic = for_device("router", "TP-Link"), for_device("router", None)
        assert family.how_to("reboot.power") == basic.how_to("reboot.power")  # inherited
        assert family.how_to("reboot.button") and not basic.how_to("reboot.button")
        assert family.light_question("internet") != basic.light_question("internet")

    def test_the_crm_model_reaches_the_catalogue(self):
        assert (
            for_signals({"device_type": "router", "device_model": "TP-Link Archer C80"}).level
            == "tplink"
        )

    def test_another_device_type_has_its_own_basic_level(self):
        box = for_device("tv_box")
        assert box.level == "tv_box" and box.name()


class TestLightsBecomeFacts:
    """The cards speak of `wan_link`; only the catalogue knows about lights.

    We ask what we can READ. The reader we have (`detect_lights`) understands lit / not lit,
    so that is what the catalogue asks and maps — a question inviting a colour would produce
    answers nothing could interpret. Colour reading arrives with a colour reader (wave 4).
    """

    @pytest.mark.parametrize(
        "model, light, seen, fact",
        [
            ("TP-Link Archer C6", "internet", "yes", ("wan_link", "up")),
            ("TP-Link Archer C6", "internet", "no", ("wan_link", "down")),
            (None, "internet", "yes", ("wan_link", "up")),
            (None, "internet", "no", ("wan_link", "down")),
            (None, "power", "no", ("power", "no")),
        ],
    )
    def test_what_the_caller_saw_means_a_fact(self, model, light, seen, fact):
        assert for_device("router", model).fact_from_light(light, seen) == fact

    def test_an_answer_we_cannot_read_is_not_a_fact(self):
        """ "It is sort of flickering" is not evidence — the engine asks again rather than
        inventing a reading."""
        assert for_device("router", None).fact_from_light("internet", "flickering") is None

    def test_a_light_the_device_does_not_have_says_nothing(self):
        assert for_device("tv_box").fact_from_light("internet", "yes") is None

    def test_the_question_and_the_reader_agree(self):
        """Every light the catalogue asks about must be answerable by the reader whose
        labels it maps — otherwise we ask something we cannot understand."""
        from agent.contract import equipment as catalog

        for name, spec in catalog.get().items():
            for light, described in spec.lights.items():
                if described.means:
                    assert set(described.means) <= {"yes", "no"}, f"{name}.{light}"


class TestTheCatalogueIsComplete:
    def test_every_type_can_answer(self):
        """A type without a basic level would be a device the agent gives up on."""
        for device_type in {spec.type for spec in catalog.get().values()}:
            assert catalog.basic(device_type) is not None, device_type

    def test_every_level_inherits_something_that_exists(self):
        specs = catalog.get()
        for name, spec in specs.items():
            assert spec.extends is None or spec.extends in specs, name
