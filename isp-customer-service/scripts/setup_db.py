#!/usr/bin/env python3
"""
Database setup script.
Creates SQLite database with CRM and Network schemas.

Usage:
    python scripts/setup_db.py
    or
    uv run python scripts/setup_db.py
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


def load_schema_file(schema_name: str) -> str:
    """Load SQL schema from file."""
    schema_path = get_project_root() / "database" / "schema" / f"{schema_name}.sql"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        return f.read()


def create_database():
    """Create database and execute schema files."""
    db_path = get_db_path()

    # Create database directory if not exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove old database if exists
    if db_path.exists():
        print(f"⚠️  Removing existing database: {db_path}")
        db_path.unlink()

    print(f"📦 Creating database at: {db_path}")

    # Connect to database (creates file)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Load and execute CRM schema
        print("📋 Creating CRM schema...")
        crm_schema = load_schema_file("crm_schema")
        cursor.executescript(crm_schema)
        print("   ✅ CRM schema created")

        # Load and execute Network schema
        print("📋 Creating Network schema...")
        network_schema = load_schema_file("network_schema")
        cursor.executescript(network_schema)
        print("   ✅ Network schema created")

        # Commit changes
        conn.commit()
        print("\n✅ Database created successfully!")
        print(f"📍 Location: {db_path}")
        print(f"📊 Size: {db_path.stat().st_size} bytes")

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Hint: Schema files should be created first:")
        print("   - database/schema/crm_schema.sql")
        print("   - database/schema/network_schema.sql")
        conn.close()
        db_path.unlink()  # Remove incomplete database
        return False

    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        conn.close()
        if db_path.exists():
            db_path.unlink()
        return False

    finally:
        conn.close()

    return True


def main():
    """Main function."""
    print("=" * 60)
    print("ISP Customer Service - Database Setup")
    print("=" * 60)
    print()

    success = create_database()

    if success:
        print("\n" + "=" * 60)
        print("Next steps:")
        print("  1. Run seed script: python scripts/seed_data.py")
        print("  2. Verify database: sqlite3 database/isp_database.db")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Setup failed. Please fix errors and try again.")
        print("=" * 60)
        exit(1)


if __name__ == "__main__":
    main()
