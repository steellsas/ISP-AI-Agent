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


class TestServiceRules:
    def _identified(self, make_state, profile):
        state = make_state("+37060012353")
        state.identity.customer_id = "CUST009"
        state.identity.service_profile = profile
        state.intake.problem_type = "tv"
        return state

    def test_a_service_the_contract_lacks_is_not_diagnosed(self, make_state, make_runtime):
        from agent.decide.rules import services

        state = self._identified(make_state, [{"type": "internet", "technology": "ethernet"}])

        assert services.route(state) == "not_subscribed"
        services.not_subscribed(state, make_runtime())
        assert state.diagnosis.verdicts["network"]["reason"] == "service_not_subscribed"
        assert state.resolution.procedure is None  # nothing to walk, no ticket

    def test_iptv_rides_on_the_internet(self, make_state):
        from agent.decide.rules import services

        state = self._identified(
            make_state,
            [{"type": "internet", "technology": "ethernet"}, {"type": "tv", "technology": "iptv"}],
        )

        assert services.route(state) == "depends"

    def test_a_broken_internet_puts_the_tv_recheck_on_the_closing_list(
        self, make_state, make_runtime
    ):
        from agent.decide.rules import services

        state = self._identified(make_state, [{"type": "tv", "technology": "iptv"}])
        state.diagnosis.verdicts["network"] = {"reason": "router_hung"}

        assert services.depends_on_broken(state)
        services.recheck_after_fix(state, make_runtime())
        services.recheck_after_fix(state, make_runtime())  # once only
        assert [x["source"] for x in state.intake.secondary_problems] == ["dependency"]

    def test_a_healthy_internet_leaves_the_tv_fault_its_own(self, make_state):
        from agent.decide.rules import services

        state = self._identified(make_state, [{"type": "tv", "technology": "iptv"}])
        state.diagnosis.verdicts["network"] = {"reason": "healthy_to_router"}

        assert not services.depends_on_broken(state)

    def test_the_not_subscribed_news_names_the_service(self, make_state, make_runtime):
        from agent.inform import inform_text

        state = self._identified(make_state, [{"type": "internet", "technology": "ethernet"}])

        text = inform_text(state, make_runtime(), "service_not_subscribed")

        assert text and "televizijos paslaugos" in text


class TestStillDownAtClosing:
    """F-20: a no to "anything else?" is a goodbye, not a broken line."""

    def test_a_polite_no_is_not_a_still_down_report(self):
        from agent.decide.rules.closing import _still_down

        assert _still_down("Ne, ačiū, viso gero") is False
        assert _still_down("Ne, ačiū, viskas") is False

    def test_an_explicit_report_still_reopens(self):
        from agent.decide.rules.closing import _still_down

        assert _still_down("Internetas vis dar neveikia") is True
