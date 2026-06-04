#!/usr/bin/env python3
"""
Test shared library functionality.
Comprehensive test suite for database, types, and utilities.

Run with:  uv run python scripts/test_shared.py
"""

import sys
from pathlib import Path

# Add shared/src to path
shared_src = Path(__file__).parent.parent / "shared" / "src"
if str(shared_src) not in sys.path:
    sys.path.insert(0, str(shared_src))


def test_imports():
    """Test that all imports work."""
    print("\n" + "=" * 60)
    print("TEST 1: Imports")
    print("=" * 60)

    try:
        from database import DatabaseConnection, get_db_connection, init_database

        print("✅ Database imports OK")
    except ImportError as e:
        print(f"❌ Database import failed: {e}")
        return False

    try:
        from isp_types import (
            Address,
            Customer,
            CustomerEquipment,
            IPAssignment,
            Port,
            PortStatus,
            ServicePlan,
            Switch,
            Ticket,
            TicketPriority,
            TicketStatus,
            TicketType,
        )

        print("✅ All types imported OK")
    except ImportError as e:
        print(f"❌ Types import failed: {e}")
        return False

    try:
        from utils import get_config, get_logger, load_env, setup_logger

        print("✅ Utils imports OK")
    except ImportError as e:
        print(f"❌ Utils import failed: {e}")
        return False

    return True


def test_database_connection():
    """Test database connection and queries."""
    print("\n" + "=" * 60)
    print("TEST 2: Database Connection")
    print("=" * 60)

    from database import init_database

    db_path = Path(__file__).parent.parent / "database" / "isp_database.db"

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False

    try:
        # Initialize connection
        db = init_database(db_path)
        print(f"✅ Database initialized: {db_path}")

        # Test query with cursor
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM customers")
            result = cursor.fetchone()
            count = dict(result)["count"]
            print(f"✅ Query executed: {count} customers in database")

        # Test transaction context manager
        with db.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT customer_id, first_name FROM customers LIMIT 1")
            customer = cursor.fetchone()
            if customer:
                print(f"✅ Transaction test: Found customer {dict(customer)['first_name']}")

        return True
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_customer_models():
    """Test Customer-related Pydantic models."""
    print("\n" + "=" * 60)
    print("TEST 3: Customer Models")
    print("=" * 60)

    from isp_types import Address, Customer, CustomerEquipment, ServicePlan

    try:
        # Test Customer model
        customer = Customer(
            customer_id="TEST001",
            first_name="Jonas",
            last_name="Jonaitis",
            phone="+37060012345",
            email="jonas@test.com",
        )
        print(f"✅ Customer model: {customer.first_name} {customer.last_name}")

        # Test Address model
        address = Address(
            address_id="ADDR001",
            customer_id="TEST001",
            city="Šiauliai",
            street="Tilžės g.",
            house_number="12",
            apartment_number="5",
        )
        formatted = address.format_address()
        print(f"✅ Address model: {formatted}")

        # Test ServicePlan model
        plan = ServicePlan(
            plan_id="PLAN001",
            customer_id="TEST001",
            service_type="internet",
            plan_name="Internet 300 Mbps",
            speed_mbps=300,
            price=24.99,
            activation_date="2024-01-01",
        )
        print(f"✅ ServicePlan model: {plan.plan_name} - {plan.price}€")

        # Test CustomerEquipment model
        equipment = CustomerEquipment(
            equipment_id="EQ001",
            customer_id="TEST001",
            equipment_type="router",
            model="TP-Link Archer C6",
            mac_address="00:1A:2B:3C:4D:01",
        )
        print(f"✅ Equipment model: {equipment.model}")

        return True
    except Exception as e:
        print(f"❌ Customer models test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_ticket_models():
    """Test Ticket-related Pydantic models."""
    print("\n" + "=" * 60)
    print("TEST 4: Ticket Models")
    print("=" * 60)

    from isp_types import Ticket, TicketPriority, TicketType

    try:
        # Test Ticket model with enums
        ticket = Ticket(
            ticket_id="TKT001",
            customer_id="TEST001",
            ticket_type=TicketType.NETWORK_ISSUE,
            priority=TicketPriority.HIGH,
            summary="Internet connection problem",
            details="Customer reports no internet connectivity",
        )
        print(f"✅ Ticket created: {ticket.ticket_id} - {ticket.summary}")
        print(f"   Priority: {ticket.priority}")
        print(f"   Type: {ticket.ticket_type}")
        print(f"   Is open: {ticket.is_open()}")

        return True
    except Exception as e:
        print(f"❌ Ticket models test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_network_models():
    """Test Network-related Pydantic models."""
    print("\n" + "=" * 60)
    print("TEST 5: Network Models")
    print("=" * 60)

    from isp_types import AreaOutage, IPAssignment, Port, PortStatus, Switch

    try:
        # Test Switch model
        switch = Switch(
            switch_id="SW001",
            switch_name="Šiauliai-Central-SW01",
            location="Šiauliai, Tilžės/Dainų rajonas",
            ip_address="10.10.1.1",
            model="Cisco Catalyst 2960-48TT",
        )
        print(f"✅ Switch model: {switch.switch_name}")

        # Test Port model
        port = Port(
            port_id="PORT001",
            switch_id="SW001",
            port_number=1,
            customer_id="CUST001",
            status=PortStatus.UP,
            speed_mbps=100,
            duplex="full",
        )
        print(f"✅ Port model: Port {port.port_number} - Status: {port.status}")
        print(f"   Is active: {port.is_active()}")
        print(f"   Is assigned: {port.is_assigned()}")

        # Test IPAssignment model
        ip = IPAssignment(
            assignment_id="IP001",
            customer_id="CUST001",
            ip_address="192.168.1.101",
            mac_address="00:1A:2B:3C:4D:01",
            assignment_type="dhcp",
        )
        print(f"✅ IPAssignment model: {ip.ip_address}")

        # Test AreaOutage model
        outage = AreaOutage(
            outage_id="OUT001",
            city="Šiauliai",
            street="Tilžės g.",
            outage_type="internet",
            description="Fiber cable damaged",
        )
        print(f"✅ AreaOutage model: {outage.city} - {outage.description}")
        print(f"   Is active: {outage.is_active()}")

        return True
    except Exception as e:
        print(f"❌ Network models test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_logger():
    """Test logger setup."""
    print("\n" + "=" * 60)
    print("TEST 6: Logger")
    print("=" * 60)

    from utils import get_logger, setup_logger

    try:
        # Test basic logger
        logger = setup_logger("test_service", level="INFO")
        logger.info("Test INFO message")
        logger.debug("Test DEBUG message (should not show)")
        print("✅ Basic logger works")

        # Test logger with DEBUG level
        debug_logger = setup_logger("debug_service", level="DEBUG")
        debug_logger.debug("Test DEBUG message (should show)")
        print("✅ DEBUG logger works")

        # Test get_logger
        existing_logger = get_logger("test_service")
        print("✅ get_logger works")

        return True
    except Exception as e:
        print(f"❌ Logger test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_config():
    """Test configuration management."""
    print("\n" + "=" * 60)
    print("TEST 7: Configuration")
    print("=" * 60)

    from utils import get_config, load_env

    try:
        # Load environment
        env_loaded = load_env()
        if env_loaded:
            print("✅ .env file loaded")
        else:
            print("⚠️  No .env file found (this is OK for testing)")

        # Get configuration
        config = get_config()
        print("✅ Config loaded")
        print(f"   Database path: {config.database_path}")
        print(f"   Log level: {config.log_level}")
        print(f"   CRM service port: {config.crm_service_port}")
        print(f"   Network service port: {config.network_service_port}")

        # Test validation (will fail if OpenAI key not set, but that's expected)
        is_valid = config.validate()
        if is_valid:
            print("✅ Configuration is valid")
        else:
            print("⚠️  Configuration validation failed (expected if OPENAI_API_KEY not set)")

        return True
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SHARED LIBRARY - COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Database Connection", test_database_connection),
        ("Customer Models", test_customer_models),
        ("Ticket Models", test_ticket_models),
        ("Network Models", test_network_models),
        ("Logger", test_logger),
        ("Configuration", test_config),
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
