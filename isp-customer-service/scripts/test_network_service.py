#!/usr/bin/env python3
"""
Test Network Diagnostic Service
Comprehensive test suite for Network Diagnostic MCP Server, Tools, and Repository
"""

import sys
from pathlib import Path

# Add shared and network_diagnostic_service to path
project_root = Path(__file__).parent.parent
shared_src = project_root / "shared" / "src"
network_src = project_root / "network_diagnostic_service" / "src"

for path in [shared_src, network_src]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_imports():
    """Test that all Network Diagnostic imports work."""
    print("\n" + "=" * 60)
    print("TEST 1: Network Diagnostic Service Imports")
    print("=" * 60)

    try:
        # Database
        from database import DatabaseConnection, init_database

        print("✅ Database imports OK")

        # Shared types
        from isp_types import AreaOutage, BandwidthLog, IPAssignment, Port, Switch

        print("✅ Shared types imports OK")

        # Repository
        from repository import NetworkRepository

        print("✅ Repository imports OK")

        # MCP Server
        from mcp_server.server import create_server

        print("✅ MCP server imports OK")

        # Tools
        from mcp_server.tools import connectivity_tests, outage_checks, port_diagnostics

        print("✅ Tools imports OK")

        return True

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_network_repository():
    """Test NetworkRepository functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Network Repository")
    print("=" * 60)

    from repository import NetworkRepository

    from database import init_database

    try:
        # Initialize database
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            return False

        db = init_database(db_path)
        repo = NetworkRepository(db)
        print("✅ Repository initialized")

        # Test: Get all switches
        switches = repo.get_all_switches()
        print(f"✅ Switches: {len(switches)} found")

        if switches:
            switch = switches[0]
            print(f"   Example: {switch.switch_name} @ {switch.location}")

            # Test: Get switch statistics
            stats = repo.get_switch_statistics(switch.switch_id)
            print(
                f"✅ Switch stats: {stats.get('total_ports', 0)} ports, "
                f"{stats.get('active_ports', 0)} active"
            )

        # Test: Count active outages
        outage_count = repo.count_active_outages()
        print(f"✅ Active outages: {outage_count}")

        # Test: Find ports by customer
        ports = repo.find_ports_by_customer("CUST001")
        print(f"✅ Ports for CUST001: {len(ports)} found")

        # Test: Get bandwidth logs
        logs = repo.get_bandwidth_logs("CUST001", limit=5)
        print(f"✅ Bandwidth logs for CUST001: {len(logs)} found")

        return True

    except Exception as e:
        print(f"❌ Network repository test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_port_diagnostics():
    """Test port diagnostics tools."""
    print("\n" + "=" * 60)
    print("TEST 3: Port Diagnostics Tools")
    print("=" * 60)

    from mcp_server.tools.port_diagnostics import check_port_status, get_switch_info

    from database import init_database

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)

        # Test: Check port status
        result = check_port_status(db, "CUST001")

        if result.get("success"):
            diagnostics = result.get("diagnostics", {})
            print(
                f"✅ Port status check: {diagnostics.get('ports_up', 0)}/"
                f"{diagnostics.get('total_ports', 0)} ports up"
            )

            if result.get("ports"):
                port = result["ports"][0]
                print(f"   Example port: {port['port_number']} on {port['switch_name']}")
        else:
            print(f"⚠️  Port status: {result.get('message')}")

        # Test: Get switch info
        switch_result = get_switch_info(db, "CUST001")

        if switch_result.get("success"):
            switch = switch_result["switch"]
            print(f"✅ Switch info: {switch['switch_name']}")
            print(f"   Status: {switch['status']}, Location: {switch['location']}")

            if "health" in switch:
                health = switch["health"]
                print(f"   Health: {health['utilization_percent']}% utilization")
        else:
            print(f"⚠️  Switch info: {switch_result.get('message')}")

        return True

    except Exception as e:
        print(f"❌ Port diagnostics test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_connectivity_tools():
    """Test connectivity diagnostic tools."""
    print("\n" + "=" * 60)
    print("TEST 4: Connectivity Tools")
    print("=" * 60)

    from mcp_server.tools.connectivity_tests import (
        check_bandwidth_history,
        check_ip_assignment,
        ping_test,
    )

    from database import init_database

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)

        # Test: IP assignment
        ip_result = check_ip_assignment(db, "CUST001")

        if ip_result.get("success"):
            active = ip_result.get("active_count", 0)
            print(f"✅ IP assignment: {active} active IPs")

            if ip_result.get("ip_assignments"):
                ip = ip_result["ip_assignments"][0]
                print(f"   Example: {ip['ip_address']} ({ip['assignment_type']})")
        else:
            print(f"⚠️  IP assignment: {ip_result.get('message')}")

        # Test: Bandwidth history
        bw_result = check_bandwidth_history(db, "CUST001", limit=5)

        if bw_result.get("success"):
            logs = bw_result.get("bandwidth_logs", [])
            stats = bw_result.get("statistics", {})
            print(f"✅ Bandwidth history: {len(logs)} measurements")

            if stats.get("download"):
                print(f"   Avg download: {stats['download']['avg_mbps']} Mbps")
        else:
            print(f"⚠️  Bandwidth history: {bw_result.get('message')}")

        # Test: Ping test
        ping_result = ping_test(db, "CUST001")

        if ping_result.get("success"):
            stats = ping_result["statistics"]
            print(
                f"✅ Ping test: {stats['packet_loss_percent']}% loss, "
                f"{stats.get('avg_latency_ms', 'N/A')}ms avg"
            )
            print(f"   Status: {ping_result['status']}")
        else:
            print(f"⚠️  Ping test: {ping_result.get('message')}")

        return True

    except Exception as e:
        print(f"❌ Connectivity tools test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_outage_checks():
    """Test outage checking tools."""
    print("\n" + "=" * 60)
    print("TEST 5: Outage Checks")
    print("=" * 60)

    from mcp_server.tools.outage_checks import check_area_outages, check_customer_affected_by_outage

    from database import init_database

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)

        # Test: Check area outages
        outage_result = check_area_outages(db, "Šiauliai")

        if outage_result.get("success"):
            outages = outage_result.get("outages", [])
            print(f"✅ Area outages in Šiauliai: {len(outages)} found")

            if outages:
                summary = outage_result.get("summary", {})
                print(f"   By type: {summary.get('by_type', {})}")
                print(f"   Critical: {summary.get('has_critical', False)}")
            else:
                print(f"   {outage_result.get('message')}")

        # Test: Check if customer affected
        affected_result = check_customer_affected_by_outage(db, "CUST001")

        if affected_result.get("success"):
            is_affected = affected_result.get("affected", False)
            print(f"✅ Customer CUST001 affected: {is_affected}")

            if is_affected:
                print(f"   Affected by {len(affected_result.get('outages', []))} outages")
        else:
            print(f"⚠️  Customer check: {affected_result.get('message')}")

        return True

    except Exception as e:
        print(f"❌ Outage checks test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_mcp_server_structure():
    """Test MCP server structure and initialization."""
    print("\n" + "=" * 60)
    print("TEST 6: MCP Server Structure")
    print("=" * 60)

    from mcp_server.server import create_server

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"

        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            return False

        # Create server instance
        server = create_server(db_path)
        print("✅ MCP Server created")

        # Check server has required attributes
        assert hasattr(server, "db"), "Server missing 'db' attribute"
        assert hasattr(server, "server"), "Server missing 'server' attribute"
        print("✅ Server has required attributes")

        # Check database connection
        with server.db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM switches")
            result = cursor.fetchone()
            count = dict(result)["count"]
        print(f"✅ Server database connection works ({count} switches)")

        return True

    except Exception as e:
        print(f"❌ MCP server structure test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_network_models():
    """Test network Pydantic models."""
    print("\n" + "=" * 60)
    print("TEST 7: Network Models")
    print("=" * 60)

    from decimal import Decimal

    from isp_types import AreaOutage, BandwidthLog, IPAssignment, Port, PortStatus, Switch

    try:
        # Test Switch model
        switch = Switch(
            switch_id="SW001",
            switch_name="Test-Switch",
            location="Test Location",
            ip_address="10.0.0.1",
            model="Test Model",
        )
        print(f"✅ Switch model: {switch.switch_name}")

        # Test Port model
        port = Port(
            port_id="PORT001",
            switch_id="SW001",
            port_number=1,
            status=PortStatus.UP,
            speed_mbps=1000,
        )
        print(f"✅ Port model: Port {port.port_number} - {port.status}")
        print(f"   Is active: {port.is_active()}")

        # Test IPAssignment model
        ip = IPAssignment(assignment_id="IP001", ip_address="192.168.1.100", assignment_type="dhcp")
        print(f"✅ IPAssignment model: {ip.ip_address}")

        # Test AreaOutage model
        outage = AreaOutage(
            outage_id="OUT001", city="Test City", outage_type="internet", description="Test outage"
        )
        print(f"✅ AreaOutage model: {outage.city} - {outage.description}")
        print(f"   Is active: {outage.is_active()}")

        # Test BandwidthLog model
        bandwidth = BandwidthLog(
            log_id="LOG001",
            customer_id="CUST001",
            download_mbps=Decimal("100.5"),
            upload_mbps=Decimal("50.2"),
            latency_ms=20,
        )
        print(f"✅ BandwidthLog model: {bandwidth.download_mbps} Mbps down")

        return True

    except Exception as e:
        print(f"❌ Network models test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("NETWORK DIAGNOSTIC SERVICE - COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Network Repository", test_network_repository),
        ("Port Diagnostics", test_port_diagnostics),
        ("Connectivity Tools", test_connectivity_tools),
        ("Outage Checks", test_outage_checks),
        ("MCP Server Structure", test_mcp_server_structure),
        ("Network Models", test_network_models),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    else:
        print("⚠️  Some tests failed")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
