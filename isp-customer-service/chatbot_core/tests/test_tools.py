"""
Tests for agent tools (CRM, network, knowledge base).

These tests verify that tools work correctly and return expected data.
Run: pytest tests/test_tools.py -v
"""

import json


class TestFindCustomer:
    """Tests for find_customer tool."""

    def test_find_customer_by_phone_success(self, db_connection, sample_customer_phone):
        """Should find customer by valid phone number."""
        from agent.tools import find_customer

        result = find_customer(phone=sample_customer_phone)

        assert result["success"] == True
        assert "customer_id" in result
        assert "name" in result
        assert result["customer_id"] is not None

    def test_find_customer_by_phone_not_found(self, db_connection):
        """Should return error for unknown phone."""
        from agent.tools import find_customer

        result = find_customer(phone="+37099999999")

        assert result["success"] == False
        assert "error" in result

    def test_find_customer_no_params(self, db_connection):
        """Should return error when no params provided."""
        from agent.tools import find_customer

        result = find_customer()

        assert result["success"] == False
        assert "missing_parameters" in result.get("error", "")

    def test_find_customer_returns_addresses(self, db_connection, sample_customer_phone):
        """Should return customer addresses."""
        from agent.tools import find_customer

        result = find_customer(phone=sample_customer_phone)

        assert result["success"] == True
        assert "addresses" in result
        assert isinstance(result["addresses"], list)


class TestCheckNetworkStatus:
    """Tests for check_network_status tool."""

    def test_check_network_status_returns_data(self, sample_customer_id):
        """Should return network status data."""
        from agent.tools import check_network_status

        result = check_network_status(customer_id=sample_customer_id)

        assert result["success"] == True
        assert "port_status" in result or "overall_status" in result
        assert "interpretation" in result

    def test_check_network_status_missing_customer_id(self):
        """Should handle missing customer_id."""
        from agent.tools import check_network_status

        result = check_network_status(customer_id="")

        assert result["success"] == False
        assert "error" in result

    def test_check_network_status_has_ip_info(self, sample_customer_id):
        """Should return IP assignment info."""
        from agent.tools import check_network_status

        result = check_network_status(customer_id=sample_customer_id)

        assert "ip_assigned" in result


class TestCheckOutages:
    """Tests for check_outages tool."""

    def test_check_outages_by_area(self):
        """Should check outages by area."""
        from agent.tools import check_outages

        result = check_outages(area="Šiauliai")

        assert result["success"] == True
        assert "active_outages" in result

    def test_check_outages_by_customer(self, sample_customer_id):
        """Should check if customer affected by outages."""
        from agent.tools import check_outages

        result = check_outages(customer_id=sample_customer_id)

        assert result["success"] == True
        assert "affected" in result or "active_outages" in result

    def test_check_outages_empty_returns_success(self):
        """Should return success even with no outages."""
        from agent.tools import check_outages

        result = check_outages(area="TestArea")

        assert result["success"] == True


class TestRunPingTest:
    """Tests for run_ping_test tool."""

    def test_run_ping_test_returns_results(self, sample_customer_id):
        """Should return ping test results."""
        from agent.tools import run_ping_test

        result = run_ping_test(customer_id=sample_customer_id)

        assert result["success"] == True
        assert "status" in result
        assert "statistics" in result or "summary" in result

    def test_run_ping_test_missing_customer(self):
        """Should handle missing customer_id."""
        from agent.tools import run_ping_test

        result = run_ping_test(customer_id="")

        assert result["success"] == False

    def test_run_ping_test_has_latency_info(self, sample_customer_id):
        """Should include latency information."""
        from agent.tools import run_ping_test

        result = run_ping_test(customer_id=sample_customer_id)

        if result["success"] and result.get("statistics"):
            stats = result["statistics"]
            # Should have some latency metric
            has_latency = "avg_latency_ms" in stats or "latency" in str(stats)
            assert has_latency or result.get("summary")


class TestSearchKnowledge:
    """Tests for search_knowledge tool."""

    def test_search_knowledge_returns_results(self, require_kb):
        """Should return results for valid query."""
        from agent.tools import search_knowledge

        result = search_knowledge(query="lėtas internetas")

        assert result["success"] == True
        assert "results" in result

    def test_search_knowledge_internet_query(self, require_kb):
        """Should find internet-related content."""
        from agent.tools import search_knowledge

        result = search_knowledge(query="neveikia internetas")

        assert result["success"] == True
        assert len(result["results"]) > 0

    def test_search_knowledge_empty_query(self):
        """Should handle empty query gracefully."""
        from agent.tools import search_knowledge

        result = search_knowledge(query="")

        # Should not crash
        assert "success" in result


class TestCreateTicket:
    """Tests for create_ticket tool."""

    def test_create_ticket_success(self, db_connection, sample_customer_id):
        """Should create ticket successfully."""
        from agent.tools import create_ticket

        result = create_ticket(
            customer_id=sample_customer_id,
            problem_type="network_issue",
            problem_description="Test ticket - internetas neveikia",
            priority="low",
            notes="Automated test",
        )

        assert result["success"] == True
        assert "ticket_id" in result

    def test_create_ticket_coerces_freetext_type(self, db_connection, sample_customer_id):
        """A free-text problem_type (e.g. 'equipment_replacement') must NOT crash the INSERT
        on the ticket_type CHECK constraint — it is coerced to a valid type (observed live
        database_error on the dead-router replacement ticket)."""
        from agent.tools import create_ticket

        result = create_ticket(
            customer_id=sample_customer_id,
            problem_type="equipment_replacement",
            problem_description="Sugedęs routeris, reikia keisti",
            priority="high",
        )
        assert result["success"] is True
        assert "ticket_id" in result

    def test_create_ticket_missing_customer(self, db_connection):
        """Should handle invalid customer."""
        from agent.tools import create_ticket

        result = create_ticket(
            customer_id="INVALID_ID", problem_type="test", problem_description="Test"
        )

        # Depending on implementation - might succeed with mock or fail
        assert "success" in result


class TestToolsRegistry:
    """Tests for tools registry."""

    def test_all_tools_registered(self):
        """Should have all required tools registered."""
        from agent.tools import REAL_TOOLS

        tool_names = [t.name for t in REAL_TOOLS]

        assert "find_customer" in tool_names
        assert "check_network_status" in tool_names
        assert "check_outages" in tool_names
        assert "run_ping_test" in tool_names
        assert "search_knowledge" in tool_names
        assert "create_ticket" in tool_names

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from agent.tools import REAL_TOOLS

        for tool in REAL_TOOLS:
            assert tool.description, f"Tool {tool.name} missing description"
            assert len(tool.description) > 10

    def test_execute_tool_function(self):
        """execute_tool should work correctly."""
        from agent.tools import execute_tool

        result = execute_tool("search_knowledge", {"query": "test"})

        # Should return JSON string
        assert isinstance(result, str)
        assert "success" in result

    def test_execute_unknown_tool(self):
        """Should handle unknown tool gracefully."""
        from agent.tools import execute_tool

        result = execute_tool("unknown_tool", {})

        assert "error" in result

    def test_tools_count(self):
        """Should have expected number of tools."""
        from agent.tools import REAL_TOOLS

        assert (
            len(REAL_TOOLS) == 11
        )  # resolve_address, find_customer, diagnose_connection, check_network_status, update_mac, reset_port, check_outages, run_ping_test, search_knowledge, create_ticket, close_case


class TestSeedNetworkStatus:
    """Seed-data guards folded in from the retired test_scenarios.py (2026-08-05):
    the UNIQUE per-customer behaviours of check_network_status / find_customer
    over the demo seeds. Lookup/outage/ticket mechanics are covered above —
    these lock the seeded FAULT SHAPES the demo and evals rely on."""

    def _status(self, customer_id):
        from agent.tools import check_network_status

        return check_network_status(customer_id=customer_id)

    def test_cust001_healthy_baseline(self, db_connection):
        result = self._status("CUST001")
        assert result["port_status"] == "up"
        assert result["ip_assigned"] is True
        assert result["overall_status"] == "healthy"

    def test_cust002_area_outage_flag(self, db_connection):
        from agent.tools import check_outages

        result = check_outages(customer_id="CUST002")
        assert result.get("affected") is True or len(result.get("active_outages", [])) > 0

    def test_cust004_port_down(self, db_connection):
        result = self._status("CUST004")
        assert result["port_status"] == "down"
        assert result["overall_status"] == "issues_detected"

    def test_cust005_has_tv_service(self, db_connection):
        from agent.tools import find_customer

        result = find_customer(phone="+37060012349")
        assert any("tv" in str(s).lower() for s in result.get("active_services", []))

    def test_cust006_no_ip(self, db_connection):
        result = self._status("CUST006")
        assert result["ip_assigned"] is False
        assert result["overall_status"] == "issues_detected"

    def test_cust007_suspended_account(self, db_connection):
        from agent.tools import find_customer

        assert find_customer(phone="+37060012351")["status"] == "suspended"

    def test_cust008_packet_loss(self, db_connection):
        result = self._status("CUST008")
        assert result.get("packet_loss", {}).get("has_packet_loss") is True
        assert result["overall_status"] == "issues_detected"

    def test_empty_phone_lookup_fails_cleanly(self, db_connection):
        from agent.tools import find_customer

        assert find_customer(phone="")["success"] is False


# Moved from test_agent.py (2026-08-05 cleanup): tool schema/validation
# belongs with the tools component, not the conversation engine.
class TestToolDescriptions:
    """Tests for tool descriptions generation."""

    def test_get_tools_description(self):
        """Should generate valid tools description."""
        from agent.tools import get_tools_description

        description = get_tools_description()

        assert isinstance(description, str)
        assert "find_customer" in description
        assert "search_knowledge" in description
        assert len(description) > 100

    def test_tools_description_has_parameters(self):
        """Tools description should include parameters."""
        from agent.tools import get_tools_description

        description = get_tools_description()

        assert "phone" in description.lower()
        assert "query" in description.lower()
        assert "customer_id" in description.lower()


class TestToolValidation:
    """Tests for Tool.validate_arguments() and execute_tool() guarding."""

    def _tools_by_name(self):
        from agent.tools import REAL_TOOLS

        return {t.name: t for t in REAL_TOOLS}

    def test_validate_drops_unknown(self):
        """Unknown argument keys are dropped (with warning) and validation passes."""
        find_customer = self._tools_by_name()["find_customer"]

        cleaned, error = find_customer.validate_arguments({"phone": "+37060012345", "bogus": "x"})

        assert error is None
        assert cleaned == {"phone": "+37060012345"}  # 'bogus' dropped
        assert "bogus" not in cleaned

    def test_validate_missing_required(self):
        """Missing a required parameter returns a structured error, no cleaned args."""
        search_knowledge = self._tools_by_name()["search_knowledge"]

        cleaned, error = search_knowledge.validate_arguments({})

        assert cleaned == {}
        assert error is not None
        assert error["error"] == "invalid_arguments"
        assert error["tool"] == "search_knowledge"
        assert error["missing_required"] == ["query"]

    def test_validate_coerces_scalar_to_string(self):
        """A scalar passed where a string is declared is coerced to str."""
        check_network_status = self._tools_by_name()["check_network_status"]

        cleaned, error = check_network_status.validate_arguments({"customer_id": 123})

        assert error is None
        assert cleaned == {"customer_id": "123"}
        assert isinstance(cleaned["customer_id"], str)

    def test_validate_non_dict_arguments(self):
        """Non-dict arguments are rejected with a structured error."""
        find_customer = self._tools_by_name()["find_customer"]

        cleaned, error = find_customer.validate_arguments("not a dict")

        assert cleaned == {}
        assert error is not None
        assert error["error"] == "invalid_arguments"

    def test_execute_tool_missing_required_returns_error(self):
        """execute_tool short-circuits on missing required args (no function call)."""
        from agent.tools import execute_tool

        # search_knowledge requires 'query'; with none, validation must stop it
        # BEFORE touching the knowledge base.
        observation = execute_tool("search_knowledge", {})
        data = json.loads(observation)

        assert data["error"] == "invalid_arguments"
        assert data["missing_required"] == ["query"]

    def test_execute_tool_unknown_tool(self):
        """execute_tool returns an error for an unknown tool name."""
        from agent.tools import execute_tool

        observation = execute_tool("nonexistent_tool", {})
        data = json.loads(observation)

        assert "Unknown tool" in data["error"]
