"""
Test lookup_customer_by_phone tool with repository pattern
"""

import sys
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared" / "src"))

from crm_mcp.tools.customer_lookup import lookup_customer_by_phone
from repository.customer_repo import CustomerRepository
from database import init_database

def test_phone_lookup():
    """Test phone lookup with repository."""
    
    # Initialize database
    db_path = Path(__file__).parent.parent / "database" / "isp_database.db"
    db = init_database(db_path)
    
    print("="*60)
    print("Testing lookup_customer_by_phone (with Repository)")
    print("="*60 + "\n")
    
    # Get a valid phone number from DB first
    repo = CustomerRepository(db)
    
    # Find first customer to get valid phone
    with db.cursor() as cursor:
        cursor.execute("SELECT phone FROM customers LIMIT 1")
        result = cursor.fetchone()
        print(result)
        valid_phone = dict(result)["phone"] if result else "+37060000001"
    
    print(f"Using test phone: {valid_phone}\n")
    
    # Test 1: Valid phone
    print("Test 1: Valid phone number")
    print("-" * 60)
    result = lookup_customer_by_phone(db, {"phone_number": valid_phone})
    
    if result["success"]:
        print(f"✅ SUCCESS: Found customer")
        print(f"   Name: {result['customer']['first_name']} {result['customer']['last_name']}")
        print(f"   Customer ID: {result['customer']['customer_id']}")
        print(f"   Email: {result['customer']['email']}")
        print(f"   Status: {result['customer']['status']}")
        print(f"\n   Addresses: {len(result['addresses'])}")
        for addr in result['addresses']:
            primary = "⭐ PRIMARY" if addr.get('is_primary') else ""
            print(f"      - {addr['full_address']} {primary}")
        
        print(f"\n   Services: {len(result['services'])}")
        for svc in result['services']:
            print(f"      - {svc['plan_name']} ({svc['plan_type']}) - {svc['speed_mbps']} Mbps")
        
        print(f"\n   Equipment: {len(result['equipment'])}")
        for eq in result['equipment']:
            print(f"      - {eq['equipment_type']}: {eq['model']} ({eq['serial_number']})")
    else:
        print(f"❌ FAILED: {result['message']}")
    
    print("\n" + "="*60 + "\n")
    
    # Test 2: Invalid phone
    print("Test 2: Invalid phone number")
    print("-" * 60)
    result = lookup_customer_by_phone(db, {"phone_number": "+37099999999"})
    
    if result["success"]:
        print(f"❌ FAILED: Should not have found customer")
    else:
        print(f"✅ SUCCESS: {result['message']}")
    
    print("\n" + "="*60 + "\n")
    
    # Test 3: Empty phone
    print("Test 3: Empty phone number")
    print("-" * 60)
    result = lookup_customer_by_phone(db, {"phone_number": ""})
    
    if result["success"]:
        print(f"❌ FAILED: Should have rejected empty phone")
    else:
        print(f"✅ SUCCESS: {result['message']}")
    
    print("\n" + "="*60 + "\n")
    
    # Test 4: Missing phone parameter
    print("Test 4: Missing phone_number parameter")
    print("-" * 60)
    result = lookup_customer_by_phone(db, {})
    
    if result["success"]:
        print(f"❌ FAILED: Should have rejected missing parameter")
    else:
        print(f"✅ SUCCESS: {result['message']}")
    
    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)

if __name__ == "__main__":
    test_phone_lookup()