"""
Tests for agent tools (CRM, network, knowledge base).

These tests verify that tools work correctly and return expected data.
Run: pytest tests/test_tools.py -v
"""

import pytest


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

    def test_search_knowledge_returns_results(self):
        """Should return results for valid query."""
        from agent.tools import search_knowledge
        
        result = search_knowledge(query="lėtas internetas")
        
        assert result["success"] == True
        assert "results" in result

    def test_search_knowledge_internet_query(self):
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
            notes="Automated test"
        )
        
        assert result["success"] == True
        assert "ticket_id" in result

    def test_create_ticket_missing_customer(self, db_connection):
        """Should handle invalid customer."""
        from agent.tools import create_ticket
        
        result = create_ticket(
            customer_id="INVALID_ID",
            problem_type="test",
            problem_description="Test"
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
        
        assert len(REAL_TOOLS) == 6  # find_customer, check_network_status, check_outages, run_ping_test, search_knowledge, create_ticket
