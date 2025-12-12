#!/usr/bin/env python3
"""
Database setup script.
Creates database with CRM and Network schemas.
Supports both SQLite (local) and PostgreSQL (Railway).

Usage:
    python scripts/setup_db.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()


def get_project_root() -> Path:
    return Path(__file__).parent.parent


def get_db_path() -> Path:
    return get_project_root() / "database" / "isp_database.db"


def load_schema_file(schema_name: str) -> str:
    schema_path = get_project_root() / "database" / "schema" / f"{schema_name}.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as f:
        return f.read()


def is_postgres() -> bool:
    database_url = os.getenv("DATABASE_URL")
    return database_url is not None and database_url.startswith("postgres")


def create_database_sqlite():
    """Create SQLite database."""
    import sqlite3

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        print(f"⚠️  Removing existing database: {db_path}")
        db_path.unlink()

    print(f"📦 Creating SQLite database at: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("📋 Creating CRM schema...")
        crm_schema = load_schema_file("crm_schema")
        cursor.executescript(crm_schema)
        print("   ✅ CRM schema created")

        print("📋 Creating Network schema...")
        network_schema = load_schema_file("network_schema")
        cursor.executescript(network_schema)
        print("   ✅ Network schema created")

        conn.commit()
        print(f"\n✅ SQLite database created!")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.close()
        if db_path.exists():
            db_path.unlink()
        return False
    finally:
        conn.close()


def create_database_postgres():
    """Create PostgreSQL database schema."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2-binary not installed!")
        print("   Run: uv add psycopg2-binary")
        return False

    database_url = os.getenv("DATABASE_URL")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    print(f"📦 Connecting to PostgreSQL...")

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()

        # Drop existing tables first (clean slate)
        print("🗑️  Dropping existing tables...")
        drop_tables = """
        DROP TABLE IF EXISTS conversations CASCADE;
        DROP TABLE IF EXISTS customer_memory CASCADE;
        DROP TABLE IF EXISTS customer_history CASCADE;
        DROP TABLE IF EXISTS tickets CASCADE;
        DROP TABLE IF EXISTS customer_equipment CASCADE;
        DROP TABLE IF EXISTS service_plans CASCADE;
        DROP TABLE IF EXISTS addresses CASCADE;
        DROP TABLE IF EXISTS streets CASCADE;
        DROP TABLE IF EXISTS customers CASCADE;
        DROP TABLE IF EXISTS traceroute_logs CASCADE;
        DROP TABLE IF EXISTS ping_tests CASCADE;
        DROP TABLE IF EXISTS network_events CASCADE;
        DROP TABLE IF EXISTS signal_quality CASCADE;
        DROP TABLE IF EXISTS area_outages CASCADE;
        DROP TABLE IF EXISTS bandwidth_logs CASCADE;
        DROP TABLE IF EXISTS ip_assignments CASCADE;
        DROP TABLE IF EXISTS ports CASCADE;
        DROP TABLE IF EXISTS switches CASCADE;
        DROP VIEW IF EXISTS active_customers_with_address CASCADE;
        DROP VIEW IF EXISTS customer_service_summary CASCADE;
        DROP VIEW IF EXISTS port_status_summary CASCADE;
        DROP VIEW IF EXISTS active_outages_by_area CASCADE;
        DROP VIEW IF EXISTS customer_network_health CASCADE;
        """
        cursor.execute(drop_tables)
        print("   ✅ Old tables dropped")

        # Create CRM schema
        print("📋 Creating CRM schema...")
        crm_schema = load_schema_file("crm_schema")
        
        # Convert SQLite syntax to PostgreSQL
        crm_schema = convert_to_postgres(crm_schema)
        
        # Execute as single block
        cursor.execute(crm_schema)
        print("   ✅ CRM schema created")

        # Create Network schema
        print("📋 Creating Network schema...")
        network_schema = load_schema_file("network_schema")
        network_schema = convert_to_postgres(network_schema)
        cursor.execute(network_schema)
        print("   ✅ Network schema created")

        # Verify tables created
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        tables = cursor.fetchall()
        print(f"\n📊 Tables created: {len(tables)}")
        for table in tables:
            print(f"   - {table[0]}")

        print(f"\n✅ PostgreSQL database ready!")

        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"\n❌ PostgreSQL error: {e}")
        return False


def convert_to_postgres(schema: str) -> str:
    """Convert SQLite schema to PostgreSQL."""
    
    # Fix problematic VIEW - add severity to GROUP BY
    schema = schema.replace(
        "GROUP BY city, street, outage_type;",
        "GROUP BY city, street, outage_type, severity;"
    )
    
    lines = []
    
    for line in schema.split('\n'):
        # Skip PRAGMA (SQLite only)
        if line.strip().upper().startswith('PRAGMA'):
            continue
        
        # Convert CREATE VIEW IF NOT EXISTS -> CREATE OR REPLACE VIEW
        if 'CREATE VIEW IF NOT EXISTS' in line.upper():
            line = line.replace('CREATE VIEW IF NOT EXISTS', 'CREATE OR REPLACE VIEW')
            line = line.replace('create view if not exists', 'CREATE OR REPLACE VIEW')
        
        # Convert datetime functions
        line = line.replace("datetime('now', '-30 days')", "NOW() - INTERVAL '30 days'")
        line = line.replace("datetime('now')", "NOW()")
        
        lines.append(line)
    
    return '\n'.join(lines)


def create_database():
    if is_postgres():
        return create_database_postgres()
    else:
        return create_database_sqlite()


def main():
    print("=" * 60)
    print("ISP Customer Service - Database Setup")
    print("=" * 60)

    if is_postgres():
        database_url = os.getenv("DATABASE_URL")
        print(f"📊 Database: PostgreSQL")
        safe_url = database_url.split("@")[-1] if "@" in database_url else database_url[:30]
        print(f"   URL: ...@{safe_url}")
    else:
        print(f"📊 Database: SQLite")
        print(f"   Path: {get_db_path()}")

    print()

    success = create_database()

    if success:
        print("\n" + "=" * 60)
        print("Next steps:")
        print("  1. Run seed script: python scripts/seed_data.py")
        print("  2. Start the application")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Setup failed. Please fix errors and try again.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()