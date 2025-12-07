"""
Scenario Tests for ISP Customer Service Agent.

Tests all 8 customer scenarios to verify:
- Customer lookup returns correct data
- Network diagnostics detect correct issues
- Outages are properly detected
- Account status is correctly returned

Run: pytest tests/test_scenarios.py -v
"""

import pytest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def tools():
    """Import tools module."""
    from agent import tools
    return tools


@pytest.fixture(scope="module")
def db(tools):
    """Get database connection."""
    return tools.get_db()


# =============================================================================
# SCENARIO 1: HAPPY PATH (Jonas - CUST001)
# =============================================================================

class TestScenario01HappyPath:
    """
    CUST001 - Jonas Jonaitis (+37060012345)
    Expected: All systems normal, no issues
    """
    
    PHONE = "+37060012345"
    CUSTOMER_ID = "CUST001"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Jonas" in result["name"]
        assert result["status"] == "active"
    
    def test_no_outages(self, tools):
        """Should have no outages in area."""
        result = tools.check_outages(customer_id=self.CUSTOMER_ID)
        
        assert result.get("affected") == False or len(result.get("active_outages", [])) == 0
    
    def test_network_healthy(self, tools):
        """Should have healthy network status."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["success"] == True
        assert result["port_status"] == "up"
        assert result["ip_assigned"] == True
        assert result["overall_status"] == "healthy"


# =============================================================================
# SCENARIO 2: AREA OUTAGE (Marija - CUST002)
# =============================================================================

class TestScenario02AreaOutage:
    """
    CUST002 - Marija Kazlauskienė (+37060012346)
    Address: Dainų g. 5-7 (has active outage)
    Expected: Outage detected
    """
    
    PHONE = "+37060012346"
    CUSTOMER_ID = "CUST002"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Marija" in result["name"]
    
    def test_outage_detected(self, tools):
        """Should detect area outage."""
        result = tools.check_outages(customer_id=self.CUSTOMER_ID)
        
        assert result.get("affected") == True or len(result.get("active_outages", [])) > 0


# =============================================================================
# SCENARIO 3: SLOW INTERNET / WIFI (Petras - CUST003)
# =============================================================================

class TestScenario03SlowInternet:
    """
    CUST003 - Petras Petraitis (+37060012347)
    Expected: Network healthy (WiFi issue is customer-side)
    """
    
    PHONE = "+37060012347"
    CUSTOMER_ID = "CUST003"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Petras" in result["name"]
    
    def test_no_outages(self, tools):
        """Should have no outages."""
        result = tools.check_outages(customer_id=self.CUSTOMER_ID)
        
        assert result.get("affected") == False or len(result.get("active_outages", [])) == 0
    
    def test_network_healthy(self, tools):
        """Network should be healthy (slow WiFi is customer issue)."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["success"] == True
        assert result["port_status"] == "up"
        assert result["ip_assigned"] == True


# =============================================================================
# SCENARIO 4: PORT DOWN - TECHNICIAN NEEDED (Andrius - CUST004)
# =============================================================================

class TestScenario04PortDown:
    """
    CUST004 - Andrius Andriuška (+37060012348)
    Expected: Port is DOWN, requires technician
    """
    
    PHONE = "+37060012348"
    CUSTOMER_ID = "CUST004"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Andrius" in result["name"]
    
    def test_port_down_detected(self, tools):
        """Should detect port is down."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["success"] == True
        assert result["port_status"] == "down"
        assert result["overall_status"] == "issues_detected"
        assert any("port" in issue.lower() for issue in result.get("issues", []))
    


    def test_create_ticket(self, tools):
        """Should be able to create ticket for port issue."""
        result = tools.create_ticket(
            customer_id=self.CUSTOMER_ID,
            problem_type="technician_visit",  # Valid: network_issue, technician_visit, etc.
            problem_description="Port down - needs technician",
            priority="high"
        )
        
        assert result["success"] == True
        assert result.get("ticket_id") is not None


# =============================================================================
# SCENARIO 5: TV NO SIGNAL (Ona - CUST005)
# =============================================================================

class TestScenario05TvNoSignal:
    """
    CUST005 - Ona Onaitė (+37060012349)
    Expected: Has TV service, network OK
    """
    
    PHONE = "+37060012349"
    CUSTOMER_ID = "CUST005"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Ona" in result["name"]
    
    def test_has_tv_service(self, tools):
        """Should have TV service in active services."""
        result = tools.find_customer(phone=self.PHONE)
        
        services = result.get("active_services", [])
        # Check if any service contains TV
        has_tv = any("tv" in str(s).lower() for s in services)
        assert has_tv, f"Expected TV service, got: {services}"
    
    def test_network_healthy(self, tools):
        """Network should be healthy."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["success"] == True
        assert result["port_status"] == "up"


# =============================================================================
# SCENARIO 6: NO IP / DHCP EXPIRED (Laima - CUST006)
# =============================================================================

class TestScenario06NoIp:
    """
    CUST006 - Laima Laimutė (+37060012350)
    Expected: IP assignment expired/missing
    """
    
    PHONE = "+37060012350"
    CUSTOMER_ID = "CUST006"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Laima" in result["name"]
    
    def test_no_ip_detected(self, tools):
        """Should detect no active IP assignment."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["success"] == True
        assert result["ip_assigned"] == False
        assert result["overall_status"] == "issues_detected"


# =============================================================================
# SCENARIO 7: SUSPENDED ACCOUNT (Tomas - CUST007)
# =============================================================================

class TestScenario07Suspended:
    """
    CUST007 - Tomas Tomauskas (+37060012351)
    Expected: Account status is suspended
    """
    
    PHONE = "+37060012351"
    CUSTOMER_ID = "CUST007"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Tomas" in result["name"]
    
    def test_account_suspended(self, tools):
        """Should return suspended status."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["status"] == "suspended"


# =============================================================================
# SCENARIO 8: INTERMITTENT / PACKET LOSS (Rūta - CUST008)
# =============================================================================

class TestScenario08Intermittent:
    """
    CUST008 - Rūta Rūtaitė (+37060012352)
    Expected: High packet loss detected
    """
    
    PHONE = "+37060012352"
    CUSTOMER_ID = "CUST008"
    
    def test_find_customer_success(self, tools):
        """Should find customer by phone."""
        result = tools.find_customer(phone=self.PHONE)
        
        assert result["success"] == True
        assert result["customer_id"] == self.CUSTOMER_ID
        assert "Rūta" in result["name"] or "Ruta" in result["name"]
    
    def test_packet_loss_detected(self, tools):
        """Should detect packet loss."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["success"] == True
        
        # Check packet loss data
        packet_loss = result.get("packet_loss", {})
        assert packet_loss.get("has_packet_loss") == True
        assert packet_loss.get("avg_packet_loss", 0) > 10  # Should be ~30%
    
    def test_issues_detected(self, tools):
        """Should have issues in status."""
        result = tools.check_network_status(customer_id=self.CUSTOMER_ID)
        
        assert result["overall_status"] == "issues_detected"
        issues = result.get("issues", [])
        assert len(issues) > 0
        
        # Should mention packet loss in issues
        issues_text = " ".join(issues).lower()
        assert "packet" in issues_text or "loss" in issues_text


# =============================================================================
# ADDITIONAL TOOL TESTS
# =============================================================================

class TestSearchKnowledge:
    """Tests for RAG search_knowledge tool."""
    
    def test_search_slow_internet(self, tools):
        """Should find slow internet troubleshooting."""
        result = tools.search_knowledge(query="lėtas internetas")
        
        assert result["success"] == True
        assert len(result.get("results", [])) > 0
        
        # Should contain relevant content
        content = str(result.get("results", [])).lower()
        assert "wifi" in content or "speed" in content or "greitis" in content or "router" in content
    
    def test_search_no_connection(self, tools):
        """Should find no connection troubleshooting."""
        result = tools.search_knowledge(query="nėra interneto ryšio")
        
        assert result["success"] == True
        assert len(result.get("results", [])) > 0
    
    def test_search_tv_issues(self, tools):
        """Should find TV troubleshooting."""
        result = tools.search_knowledge(query="TV nėra signalo")
        
        assert result["success"] == True
        assert len(result.get("results", [])) > 0


class TestCustomerNotFound:
    """Tests for handling non-existent customers."""
    
    def test_invalid_phone(self, tools):
        """Should handle invalid phone gracefully."""
        result = tools.find_customer(phone="+37099999999")
        
        assert result["success"] == False
        assert "not_found" in result.get("error", "") or "not found" in result.get("message", "").lower()
    
    def test_empty_phone(self, tools):
        """Should handle empty phone."""
        result = tools.find_customer(phone="")
        
        assert result["success"] == False


# =============================================================================
# SUMMARY
# =============================================================================

"""
Test Summary:
=============

Scenario 1 (CUST001 - Jonas): Happy path - all OK
Scenario 2 (CUST002 - Marija): Area outage detected
Scenario 3 (CUST003 - Petras): Slow internet (WiFi) - network OK
Scenario 4 (CUST004 - Andrius): Port DOWN - needs technician
Scenario 5 (CUST005 - Ona): TV no signal - has TV service
Scenario 6 (CUST006 - Laima): No IP assignment
Scenario 7 (CUST007 - Tomas): Account suspended
Scenario 8 (CUST008 - Rūta): Packet loss / intermittent

Run all tests:
    pytest tests/test_scenarios.py -v

Run specific scenario:
    pytest tests/test_scenarios.py::TestScenario04PortDown -v

Run with output:
    pytest tests/test_scenarios.py -v -s
"""
