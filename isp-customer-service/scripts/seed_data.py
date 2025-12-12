#!/usr/bin/env python3
"""
Database seed script.
Populates database with mock customer and network data.
Supports both SQLite (local) and PostgreSQL (Railway).

Usage:
    python scripts/seed_data.py
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


def load_seed_file(seed_name: str) -> str:
    seed_path = get_project_root() / "database" / "seeds" / f"{seed_name}.sql"
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")
    with open(seed_path, "r", encoding="utf-8") as f:
        return f.read()


def remove_sql_comments(sql: str) -> str:
    """Remove SQL comments from string."""
    lines = []
    for line in sql.split('\n'):
        # Check if line is a full comment (starts with --)
        stripped = line.strip()
        if stripped.startswith('--'):
            continue  # Skip full comment lines
        
        # Remove inline comments (-- after code)
        if '--' in line:
            line = line.split('--')[0]
        
        lines.append(line)
    return '\n'.join(lines)


def convert_sql_for_postgres(sql: str) -> str:
    """Convert SQLite SQL to PostgreSQL compatible."""
    import re
    
    # Pattern to match datetime('now', 'interval') - captures the interval part
    def replace_datetime(match):
        interval = match.group(1)  # e.g., '-2 hours', '+1 hour', '-15 minutes'
        return f"NOW() + INTERVAL '{interval}'"
    
    # Match datetime('now', 'anything') - flexible pattern
    sql = re.sub(
        r"datetime\s*\(\s*'now'\s*,\s*'([^']+)'\s*\)",
        replace_datetime,
        sql,
        flags=re.IGNORECASE
    )
    
    # Convert datetime('now') -> NOW()
    sql = re.sub(r"datetime\s*\(\s*'now'\s*\)", "NOW()", sql, flags=re.IGNORECASE)
    
    return sql


def is_postgres() -> bool:
    database_url = os.getenv("DATABASE_URL")
    return database_url is not None and database_url.startswith("postgres")


def seed_database_sqlite():
    """Seed SQLite database."""
    import sqlite3

    db_path = get_db_path()

    if not db_path.exists():
        print("❌ Database not found! Run setup_db.py first.")
        return False

    print(f"📦 Loading mock data into SQLite: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        seed_files = ["customers", "addresses", "service_plans", "equipment", "network"]

        for seed_name in seed_files:
            print(f"   - Loading {seed_name}...")
            seed_sql = load_seed_file(seed_name)
            cursor.executescript(seed_sql)

        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]

        print(f"\n✅ Mock data loaded!")
        print(f"   Customers: {customer_count}")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def seed_database_postgres():
    """Seed PostgreSQL database."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2-binary not installed!")
        return False

    database_url = os.getenv("DATABASE_URL")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    print(f"📦 Loading mock data into PostgreSQL...")

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # Check if data already exists
        cursor.execute("SELECT COUNT(*) FROM customers")
        count = cursor.fetchone()[0]

        if count > 0:
            print(f"⚠️ Database already has {count} customers.")
            response = input("   Do you want to reseed? This will DELETE all data. (y/N): ")
            if response.lower() != 'y':
                print("   Skipping seed.")
                cursor.close()
                conn.close()
                return True
            
            # Clear existing data
            print("   🗑️ Clearing existing data...")
            cursor.execute("DELETE FROM conversations")
            cursor.execute("DELETE FROM customer_memory")
            cursor.execute("DELETE FROM customer_history")
            cursor.execute("DELETE FROM tickets")
            cursor.execute("DELETE FROM customer_equipment")
            cursor.execute("DELETE FROM service_plans")
            cursor.execute("DELETE FROM addresses")
            cursor.execute("DELETE FROM streets")
            cursor.execute("DELETE FROM customers")
            cursor.execute("DELETE FROM traceroute_logs")
            cursor.execute("DELETE FROM ping_tests")
            cursor.execute("DELETE FROM network_events")
            cursor.execute("DELETE FROM signal_quality")
            cursor.execute("DELETE FROM area_outages")
            cursor.execute("DELETE FROM bandwidth_logs")
            cursor.execute("DELETE FROM ip_assignments")
            cursor.execute("DELETE FROM ports")
            cursor.execute("DELETE FROM switches")
            conn.commit()

        seed_files = ["customers", "addresses", "service_plans", "equipment", "network"]

        for seed_name in seed_files:
            print(f"   - Loading {seed_name}...")
            seed_sql = load_seed_file(seed_name)
            
            # Remove comments for cleaner processing
            seed_sql = remove_sql_comments(seed_sql)
            
            # Convert SQLite syntax to PostgreSQL
            seed_sql = convert_sql_for_postgres(seed_sql)
            
            # Split by semicolon and execute each statement
            for statement in seed_sql.split(';'):
                statement = statement.strip()
                if statement:
                    try:
                        cursor.execute(statement)
                        conn.commit()
                    except psycopg2.Error as e:
                        error_msg = str(e).lower()
                        if "duplicate" not in error_msg and "already exists" not in error_msg:
                            print(f"      ⚠️ {e}")
                        conn.rollback()

        # Get statistics
        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM switches")
        switch_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ports")
        port_count = cursor.fetchone()[0]

        print(f"\n✅ Mock data loaded!")
        print(f"   Customers: {customer_count}")
        print(f"   Switches: {switch_count}")
        print(f"   Ports: {port_count}")

        cursor.close()
        conn.close()
        return True

    except psycopg2.Error as e:
        print(f"\n❌ PostgreSQL error: {e}")
        return False


def seed_database():
    if is_postgres():
        return seed_database_postgres()
    else:
        return seed_database_sqlite()


def main():
    print("=" * 60)
    print("ISP Customer Service - Database Seed")
    print("=" * 60)

    if is_postgres():
        print(f"📊 Database: PostgreSQL")
    else:
        print(f"📊 Database: SQLite")
        print(f"   Path: {get_db_path()}")

    print()

    success = seed_database()

    if success:
        print("\n" + "=" * 60)
        print("Database ready!")
        print("You can now start the application.")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Seeding failed. Please fix errors and try again.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
