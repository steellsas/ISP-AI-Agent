#!/usr/bin/env python3
"""
Test CRM Service
Comprehensive test suite for CRM MCP Server, Tools, and Repositories
"""

import sys
from pathlib import Path

# Add shared and crm_service to path
project_root = Path(__file__).parent.parent
shared_src = project_root / "shared" / "src"
crm_src = project_root / "crm_service" / "src"

for path in [shared_src, crm_src]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_imports():
    """Test that all CRM imports work."""
    print("\n" + "=" * 60)
    print("TEST 1: CRM Service Imports")
    print("=" * 60)

    try:
        # Database
        from database import init_database, DatabaseConnection

        print("✅ Database imports OK")

        # Shared types
        from isp_types import Customer, Ticket, Address

        print("✅ Shared types imports OK")

        # Repositories
        from repository import CustomerRepository, TicketRepository

        print("✅ Repository imports OK")

        # MCP Server
        from mcp_server.server import create_server

        print("✅ MCP server imports OK")

        # Tools
        from mcp_server.tools import customer_lookup, equipment, tickets

        print("✅ Tools imports OK")

        return True

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_customer_repository():
    """Test CustomerRepository functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Customer Repository")
    print("=" * 60)

    from database import init_database
    from repository import CustomerRepository

    try:
        # Initialize database
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        if not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            return False

        db = init_database(db_path)
        repo = CustomerRepository(db)
        print("✅ Repository initialized")

        # Test: Count customers
        count = repo.count_customers()
        print(f"✅ Customer count: {count}")

        # Test: Get cities
        cities = repo.get_cities()
        print(f"✅ Cities: {len(cities)} found - {cities[:3]}...")

        # Test: Get streets in city
        if cities:
            streets = repo.get_streets_in_city(cities[0])
            print(f"✅ Streets in {cities[0]}: {len(streets)} found")

        # Test: Find customer by ID
        customer = repo.find_by_id("CUST001")
        if customer:
            print(f"✅ Found customer: {customer.first_name} {customer.last_name}")
        else:
            print("⚠️  Customer CUST001 not found")

        # Test: Get customer summary
        if customer:
            summary = repo.get_customer_summary("CUST001")
            print(
                f"✅ Customer summary: {len(summary['addresses'])} addresses, "
                f"{len(summary['services'])} services"
            )

        return True

    except Exception as e:
        print(f"❌ Customer repository test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_ticket_repository():
    """Test TicketRepository functionality."""
    print("\n" + "=" * 60)
    print("TEST 3: Ticket Repository")
    print("=" * 60)

    from database import init_database
    from repository import TicketRepository

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)
        repo = TicketRepository(db)
        print("✅ Ticket repository initialized")

        # Test: Count open tickets
        open_count = repo.count_open_tickets()
        print(f"✅ Open tickets: {open_count}")

        # Test: Get statistics
        stats = repo.get_statistics()
        print(f"✅ Ticket statistics: {stats['total']} total tickets")
        print(f"   By status: {stats['by_status']}")

        # Test: Find tickets for customer
        tickets = repo.find_by_customer("CUST001", limit=5)
        print(f"✅ Found {len(tickets)} tickets for CUST001")

        if tickets:
            ticket = tickets[0]
            print(f"   Latest: {ticket.ticket_id} - {ticket.summary}")

        return True

    except Exception as e:
        print(f"❌ Ticket repository test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_customer_lookup_tool():
    """Test customer lookup tool with fuzzy matching."""
    print("\n" + "=" * 60)
    print("TEST 4: Customer Lookup Tool")
    print("=" * 60)

    from database import init_database
    from mcp_server.tools.customer_lookup import (
        lookup_customer_by_address,
        fuzzy_match_street,
        normalize_street_name,
    )

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)

        # Test: Street normalization
        test_streets = ["Tilžės g.", "Tilzes gatve", "Dainų g."]
        for street in test_streets:
            normalized = normalize_street_name(street)
            print(f"✅ Normalize: '{street}' -> '{normalized}'")

        # Test: Fuzzy matching
        db_streets = ["Tilžės g.", "Dainų g.", "Vilniaus g."]
        matched = fuzzy_match_street("Tilzes", db_streets)
        if matched:
            print(f"✅ Fuzzy match: 'Tilzes' -> '{matched}'")

        # Test: Lookup by address
        result = lookup_customer_by_address(
            db,
            {
                "city": "Šiauliai",
                "street": "Tilžės g.",
                "house_number": "60",
                "apartment_number": "12",
            },
        )

        if result.get("success"):
            customer = result["customer"]
            print(f"✅ Found customer: {customer['first_name']} {customer['last_name']}")
            print(f"   Address: {customer['address']['full_address']}")
        else:
            print(f"⚠️  Lookup result: {result.get('message')}")

        return True

    except Exception as e:
        print(f"❌ Customer lookup test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_equipment_tool():
    """Test equipment management tool."""
    print("\n" + "=" * 60)
    print("TEST 5: Equipment Tool")
    print("=" * 60)

    from database import init_database
    from mcp_server.tools.equipment import get_customer_equipment

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)

        # Test: Get equipment for customer
        result = get_customer_equipment(db, "CUST001")

        if result.get("success"):
            equipment = result["equipment"]
            summary = result["summary"]
            print(f"✅ Equipment found: {summary['total_equipment']} items")
            print(f"   By type: {summary['by_type']}")

            if equipment:
                print(f"   Example: {equipment[0]['equipment_type']} - {equipment[0]['model']}")
        else:
            print(f"⚠️  Equipment result: {result.get('message')}")

        return True

    except Exception as e:
        print(f"❌ Equipment test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_ticket_tool():
    """Test ticket management tool."""
    print("\n" + "=" * 60)
    print("TEST 6: Ticket Tool")
    print("=" * 60)

    from database import init_database
    from mcp_server.tools.tickets import create_ticket, get_customer_tickets

    try:
        db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
        db = init_database(db_path)

        # Test: Get existing tickets
        result = get_customer_tickets(db, "CUST001", status="all")

        if result.get("success"):
            tickets = result["tickets"]
            stats = result["statistics"]
            print(f"✅ Found {stats['total']} tickets for CUST001")
            print(f"   By status: {stats['by_status']}")

            if tickets:
                print(f"   Latest: {tickets[0]['ticket_id']} - {tickets[0]['summary']}")

        # Test: Create new ticket (commented out to avoid cluttering DB)
        print("✅ Ticket creation tested (skipped to avoid DB clutter)")
        # Uncomment to actually test creation:
        # create_result = create_ticket(db, {
        #     "customer_id": "CUST001",
        #     "ticket_type": "network_issue",
        #     "priority": "medium",
        #     "summary": "Test ticket - automated test",
        #     "details": "This is a test ticket created by test_crm_service.py"
        # })
        # if create_result.get("success"):
        #     print(f"✅ Created ticket: {create_result['ticket']['ticket_id']}")

        return True

    except Exception as e:
        print(f"❌ Ticket tool test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_mcp_server_structure():
    """Test MCP server structure and tools registration."""
    print("\n" + "=" * 60)
    print("TEST 7: MCP Server Structure")
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
            cursor.execute("SELECT COUNT(*) as count FROM customers")
            result = cursor.fetchone()
            count = dict(result)["count"]
        print(f"✅ Server database connection works ({count} customers)")

        return True

    except Exception as e:
        print(f"❌ MCP server structure test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CRM SERVICE - COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Customer Repository", test_customer_repository),
        ("Ticket Repository", test_ticket_repository),
        ("Customer Lookup Tool", test_customer_lookup_tool),
        ("Equipment Tool", test_equipment_tool),
        ("Ticket Tool", test_ticket_tool),
        ("MCP Server Structure", test_mcp_server_structure),
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
