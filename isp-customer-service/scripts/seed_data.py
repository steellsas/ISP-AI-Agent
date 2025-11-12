#!/usr/bin/env python3
"""
Database seed script.
Populates database with mock customer and network data.

Usage:
    python scripts/seed_data.py
    or
    uv run python scripts/seed_data.py
"""

import os
import sqlite3
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def get_db_path() -> Path:
    """Get the database file path."""
    return get_project_root() / "database" / "isp_database.db"


def load_seed_file(seed_name: str) -> str:
    """Load SQL seed data from file."""
    seed_path = get_project_root() / "database" / "seeds" / f"{seed_name}.sql"
    
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")
    
    with open(seed_path, 'r', encoding='utf-8') as f:
        return f.read()


def seed_database():
    """Load mock data into database."""
    db_path = get_db_path()
    
    if not db_path.exists():
        print("❌ Database not found! Run setup_db.py first.")
        return False
    
    print(f"📦 Loading mock data into: {db_path}")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Seed CRM data
        print("📋 Seeding CRM data...")
        
        print("   - Loading customers...")
        customers_sql = load_seed_file("customers")
        cursor.executescript(customers_sql)
        
        print("   - Loading addresses...")
        addresses_sql = load_seed_file("addresses")
        cursor.executescript(addresses_sql)
        
        print("   - Loading service plans...")
        service_plans_sql = load_seed_file("service_plans")
        cursor.executescript(service_plans_sql)
        
        print("   - Loading equipment...")
        equipment_sql = load_seed_file("equipment")
        cursor.executescript(equipment_sql)
        
        print("   ✅ CRM data loaded")
        
        # Seed Network data
        print("📋 Seeding Network data...")
        
        print("   - Loading network infrastructure...")
        network_sql = load_seed_file("network")
        cursor.executescript(network_sql)
        
        print("   ✅ Network data loaded")
        
        # Commit changes
        conn.commit()
        print('commited')
        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]

        
        cursor.execute("SELECT COUNT(*) FROM switches")
        switch_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ports")
        port_count = cursor.fetchone()[0]
        
        print("\n Mock data loaded successfully!")
        print(f" Statistics:")
        print(f"   - Customers: {customer_count}")
        print(f"   - Switches: {switch_count}")
        print(f"   - Ports: {port_count}")
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Hint: Seed files should be created first:")
        print("   - database/seeds/customers.sql")
        print("   - database/seeds/addresses.sql")
        print("   - database/seeds/service_plans.sql")
        print("   - database/seeds/equipment.sql")
        print("   - database/seeds/network.sql")
        conn.close()
        return False
        
    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.rollback()
        conn.close()
        return False
        
    finally:
        conn.close()
    
    return True


def main():
    """Main function."""
    print("=" * 60)
    print("ISP Customer Service - Database Seed")
    print("=" * 60)
    print()
    
    success = seed_database()
    
    if success:
        print("\n" + "=" * 60)
        print("Database ready!")
        print("You can now start the chatbot application.")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Seeding failed. Please fix errors and try again.")
        print("=" * 60)
        exit(1)


if __name__ == "__main__":
    main()