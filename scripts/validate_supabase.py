#!/usr/bin/env python3
"""
Validate Supabase connection and initialize schema if needed.
Run this before scripts/migrate_to_supabase.py to ensure Supabase is ready.

Usage:
    python3 scripts/validate_supabase.py
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

from utils.config import load_config
from db.database import Database


def validate():
    print("=" * 80)
    print("VALIDATE: Supabase Connection & Schema")
    print("=" * 80)
    print()

    try:
        config = load_config()
    except RuntimeError as e:
        print(f"❌ {e}")
        print("\nFix: Add DATABASE_URL to .env (copy .env.example and fill in your Supabase credentials)")
        sys.exit(1)

    database_url = config["app"]["database_url"]

    # Mask password for display
    if "@" in database_url:
        scheme, rest = database_url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":")[0]
        masked_url = f"{scheme}://{user}:***@{host}"
    else:
        masked_url = database_url

    print(f"Connecting to: {masked_url}")
    print()

    try:
        # Create Database instance, which auto-initializes schema
        db = Database(database_url)
        print("✓ Connection successful")
        print()

        # Verify tables exist
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()

        expected_tables = [
            "deleted_listings",
            "listing_snapshots",
            "listings",
            "scores",
            "spec_overrides",
            "specifications",
        ]

        print("Tables in Supabase:")
        for table in expected_tables:
            status = "✓" if table in tables else "❌"
            print(f"  {status} {table}")

        if set(expected_tables) <= set(tables):
            print()
            print("✓ All required tables exist")
        else:
            missing = set(expected_tables) - set(tables)
            print()
            print(f"❌ Missing tables: {', '.join(missing)}")
            print("   (They should have been auto-created by Database initialization)")
            sys.exit(1)

        # Check for existing data
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM listings")
        listing_count = cursor.fetchone()[0]
        cursor.close()
        db.close()

        print()
        print(f"Existing listings in Supabase: {listing_count}")

        if listing_count > 0:
            print()
            print("⚠️  WARNING: Supabase already has data.")
            print("   Migration script uses ON CONFLICT DO NOTHING for idempotency,")
            print("   so re-running won't duplicate rows, but existing data won't be updated.")
            print()
            print("   If you want a fresh migration:")
            print("   1. Back up your data")
            print("   2. Delete your Supabase project and create a new one")
            print("   3. Update DATABASE_URL in .env")
            print("   4. Re-run this validation and the migration script")

        print()
        print("=" * 80)
        print("✓ Supabase is ready for migration")
        print("=" * 80)
        print()
        print("Next steps:")
        print("  1. Verify old SQLite database exists: ls -lh data/emtb_hunter.db")
        print("  2. Run migration: python3 scripts/migrate_to_supabase.py")
        print("  3. Run tests: pytest tests/test_database.py -v")
        print("  4. Test E2E: python3 run.py --dry-run")
        print()

    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        print()
        print("Fix:")
        print("  1. Check DATABASE_URL in .env is correct")
        print("  2. Verify Supabase project is running")
        print("  3. Check your network connection")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    validate()
