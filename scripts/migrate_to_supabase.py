#!/usr/bin/env python3
"""
Migrate ebike-hunter data from local SQLite to Supabase (Postgres).

Reads data/emtb_hunter.db (read-only) and writes to DATABASE_URL.
For each table, copies the columns present in both databases, so it keeps
working if the schema gains columns. listings.rowid becomes numeric_id.
Re-runnable: ON CONFLICT DO NOTHING.

Usage:
    python3 scripts/validate_supabase.py   # creates the schema
    python3 scripts/migrate_to_supabase.py
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

import psycopg2
import psycopg2.extras

from utils.config import load_config

# Parents before children (foreign keys).
TABLES = ["listings", "listing_snapshots", "specifications", "scores",
          "spec_overrides", "deleted_listings"]


def pg_columns(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s", (table,))
    return {r[0] for r in cur.fetchall()}


def migrate():
    database_url = load_config()["app"]["database_url"]
    sqlite_path = BASE_DIR / "data" / "emtb_hunter.db"
    if not sqlite_path.exists():
        sys.exit(f"SQLite database not found: {sqlite_path}")

    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    dst = psycopg2.connect(database_url)
    cur = dst.cursor()

    try:
        for table in TABLES:
            sqlite_cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
            cols = [c for c in sqlite_cols if c in pg_columns(cur, table)]
            select = ", ".join(cols)
            if table == "listings":
                select = "rowid, " + select
                cols = ["numeric_id"] + cols
            rows = src.execute(f"SELECT {select} FROM {table}").fetchall()
            psycopg2.extras.execute_values(
                cur,
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s ON CONFLICT DO NOTHING",
                rows, page_size=500)
            print(f"✓ {table}: {len(rows)} rows read")

        # Sequences must continue after the copied ids.
        for table, col in (("listings", "numeric_id"), ("listing_snapshots", "id")):
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                        f"COALESCE((SELECT MAX({col}) FROM {table}), 1))")
        dst.commit()

        print("\nRows now in Supabase:")
        for table in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            n = cur.fetchone()[0]
            s = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:18} sqlite={s:5} supabase={n:5} {'OK' if n == s else 'MISMATCH'}")
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate()
