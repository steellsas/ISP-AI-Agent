"""
Test CRM Service Standalone
Direct database calls without MCP
"""

import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent / "src"))
shared_path = Path(__file__).parent.parent / "shared" / "src"
sys.path.insert(0, str(shared_path))

from database import init_database


def test_crm_service():
    """Test CRM service database operations."""

    print("=" * 60)
    print("CRM SERVICE STANDALONE TEST")
    print("=" * 60)

    # Initialize database
    db_path = Path(__file__).parent.parent / "database" / "isp_database.db"

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return

    print(f"\n1. Database: {db_path}")
    print(f"   Size: {db_path.stat().st_size / 1024:.1f} KB")

    # Connect to database
    db = init_database(db_path)
    print("✅ Database connected")

    # Test 1: Lookup customer
    print("\n" + "=" * 60)
    print("TEST 1: Customer Lookup")
    print("=" * 60)

    from mcp_server.tools.customer_lookup import lookup_customer_by_address

    result = lookup_customer_by_address(
        db, {"city": "Šiauliai", "street": "Tilžės g.", "house_number": "60"}
    )

    print(f"Result: {result}")

    if result.get("success"):
        customer = result.get("customer", {})
        print(f"\n✅ Customer found:")
        print(f"   ID: {customer.get('customer_id')}")
        print(f"   Name: {customer.get('first_name')} {customer.get('last_name')}")
        print(f"   Address: {customer.get('address', {}).get('full_address')}")
    else:
        print(f"❌ Customer not found: {result.get('message')}")

    # Test 2: Get customer details
    if result.get("success"):
        print("\n" + "=" * 60)
        print("TEST 2: Customer Details")
        print("=" * 60)

        from mcp_server.tools.customer_lookup import get_customer_details

        customer_id = result["customer"]["customer_id"]
        details = get_customer_details(db, customer_id)

        print(f"Result: {details}")

        if details.get("success"):
            print(f"\n✅ Customer details:")
            print(f"   Services: {len(details.get('services', []))}")
            print(f"   Equipment: {len(details.get('equipment', []))}")

    # Test 3: Create ticket
    print("\n" + "=" * 60)
    print("TEST 3: Create Ticket")
    print("=" * 60)

    from mcp_server.tools.tickets import create_ticket

    ticket_result = create_ticket(
        db,
        {
            "customer_id": "1",
            "ticket_type": "network_issue",
            "priority": "medium",
            "summary": "Test ticket - Internet slow",
            "details": "Customer reports slow speeds",
            "troubleshooting_steps": "Router restart performed",
        },
    )

    print(f"Result: {ticket_result}")

    if ticket_result.get("success"):
        ticket = ticket_result.get("ticket", {})
        print(f"\n✅ Ticket created:")
        print(f"   ID: {ticket.get('ticket_id')}")
        print(f"   Type: {ticket.get('ticket_type')}")
        print(f"   Priority: {ticket.get('priority')}")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    test_crm_service()
