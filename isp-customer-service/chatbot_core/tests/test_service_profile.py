"""The service profile (M6, D-10): what the customer has, and what depends on what."""

from agent.services import depends_on, subscribed


class TestCatalog:
    def test_iptv_depends_on_the_internet(self):
        assert depends_on("tv", "iptv") == "internet"

    def test_cable_tv_does_not(self):
        assert depends_on("tv", "dvbc") is None

    def test_the_internet_depends_on_nothing(self):
        assert depends_on("internet", "ethernet") is None


class TestProfile:
    def test_identification_loads_the_customers_services(self, db_connection):
        from agent.tools import resolve_address

        from tests.calls import make_call

        state, rt = make_call("+37060020112")
        result = rt.tools.run(
            state,
            rt,
            "resolve_address",
            {"street": "Vilniaus g.", "house_number": "33", "apartment_number": "2"},
            reason="test",
        )

        assert result.data.get("success"), resolve_address
        assert state.identity.customer_id == "CUST112"
        tv = subscribed(state.identity.service_profile, "tv")
        assert tv and tv["technology"] == "iptv"
        assert subscribed(state.identity.service_profile, "internet")["technology"] == "ethernet"

    def test_a_customer_without_tv(self, db_connection):
        from tests.calls import make_call

        state, rt = make_call("+37060012353")
        rt.tools.run(state, rt, "find_customer", {"phone": "+37060012353"}, reason="test")

        assert state.identity.customer_id == "CUST009"
        assert subscribed(state.identity.service_profile, "tv") is None
