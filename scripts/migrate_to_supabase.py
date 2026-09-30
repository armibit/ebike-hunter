#!/usr/bin/env python3
"""
Migrate existing ebike-hunter data from SQLite to Supabase (Postgres).

Reads from local data/emtb_hunter.db and writes to DATABASE_URL (Supabase).
Preserves each listing's rowid as the new numeric_id, then resets the sequence.
Idempotent-safe: re-running doesn't duplicate rows (ON CONFLICT DO NOTHING).

Usage:
    python3 scripts/migrate_to_supabase.py
"""
import os
import sqlite3
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


def migrate():
    config = load_config()
    database_url = config["app"]["database_url"]

    # Open local SQLite database
    sqlite_path = BASE_DIR / "data" / "emtb_hunter.db"
    if not sqlite_path.exists():
        print(f"❌ SQLite database not found: {sqlite_path}")
        print("   Migration requires old data/emtb_hunter.db to read from")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Open Postgres connection
    pg_conn = psycopg2.connect(database_url)
    pg_cursor = pg_conn.cursor()

    try:
        print("=" * 80)
        print("MIGRATE: SQLite → Supabase (Postgres)")
        print("=" * 80)
        print()

        # 1. Migrate listings (preserve rowid as numeric_id)
        print("Migrating listings...")
        sqlite_cursor.execute("""
            SELECT rowid, id, portal, portal_id, title, description_raw, url, image_url,
                   price_raw, currency, price_chf, price_eur,
                   latitude, longitude, location_raw, location_normalized, region, distance_km,
                   first_seen_at, last_seen_at,
                   status, rejection_reason, status_locked,
                   is_favorite, user_analysis, ai_analysis, ai_score, has_red_flag, red_flag_details,
                   dedupe_signature
            FROM listings
        """)

        rows = sqlite_cursor.fetchall()
        listings_by_id = {}

        for row in rows:
            rowid = row["rowid"]
            listings_by_id[row["id"]] = rowid

            pg_cursor.execute("""
                INSERT INTO listings (
                    numeric_id, id, portal, portal_id, title, description_raw, url, image_url,
                    price_raw, currency, price_chf, price_eur,
                    latitude, longitude, location_raw, location_normalized, region, distance_km,
                    first_seen_at, last_seen_at,
                    status, rejection_reason, status_locked,
                    is_favorite, user_analysis, ai_analysis, ai_score, has_red_flag, red_flag_details,
                    dedupe_signature
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s
                )
                ON CONFLICT (id) DO NOTHING
            """, (
                rowid, row["id"], row["portal"], row["portal_id"], row["title"], row["description_raw"],
                row["url"], row["image_url"],
                row["price_raw"], row["currency"], row["price_chf"], row["price_eur"],
                row["latitude"], row["longitude"], row["location_raw"], row["location_normalized"],
                row["region"], row["distance_km"],
                row["first_seen_at"], row["last_seen_at"],
                row["status"], row["rejection_reason"], row["status_locked"],
                row["is_favorite"], row["user_analysis"], row["ai_analysis"], row["ai_score"],
                row["has_red_flag"], row["red_flag_details"],
                row["dedupe_signature"],
            ))

        pg_conn.commit()
        print(f"✓ Migrated {len(rows)} listings")

        # 2. Reset numeric_id sequence to avoid collision on next insert
        if rows:
            max_numeric_id = max(listings_by_id.values())
            pg_cursor.execute(f"""
                SELECT setval('listings_numeric_id_seq', %s)
            """, (max_numeric_id + 1,))
            pg_conn.commit()
            print(f"✓ Reset numeric_id sequence to {max_numeric_id + 1}")

        # 3. Migrate listing_snapshots
        print("Migrating listing_snapshots...")
        sqlite_cursor.execute("""
            SELECT id, listing_id, price_raw, currency, captured_at
            FROM listing_snapshots
        """)

        snapshot_rows = sqlite_cursor.fetchall()
        for row in snapshot_rows:
            pg_cursor.execute("""
                INSERT INTO listing_snapshots (id, listing_id, price_raw, currency, captured_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (row["id"], row["listing_id"], row["price_raw"], row["currency"], row["captured_at"]))

        pg_conn.commit()
        print(f"✓ Migrated {len(snapshot_rows)} listing_snapshots")

        # 4. Migrate specifications
        print("Migrating specifications...")
        sqlite_cursor.execute("""
            SELECT id, listing_id, brand, motor_brand, motor_model, motor_torque_nm, motor_verified,
                   battery_capacity_wh, frame_size, model_year, odometer_km,
                   travel_front_mm, brakes_tier, suspension_type,
                   has_red_flag, red_flag_details
            FROM specifications
        """)

        spec_rows = sqlite_cursor.fetchall()
        for row in spec_rows:
            pg_cursor.execute("""
                INSERT INTO specifications (
                    id, listing_id, brand, motor_brand, motor_model, motor_torque_nm, motor_verified,
                    battery_capacity_wh, frame_size, model_year, odometer_km,
                    travel_front_mm, brakes_tier, suspension_type,
                    has_red_flag, red_flag_details
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (id) DO NOTHING
            """, (
                row["id"], row["listing_id"], row["brand"], row["motor_brand"], row["motor_model"],
                row["motor_torque_nm"], row["motor_verified"],
                row["battery_capacity_wh"], row["frame_size"], row["model_year"], row["odometer_km"],
                row["travel_front_mm"], row["brakes_tier"], row["suspension_type"],
                row["has_red_flag"], row["red_flag_details"],
            ))

        pg_conn.commit()
        print(f"✓ Migrated {len(spec_rows)} specifications")

        # 5. Migrate scores
        print("Migrating scores...")
        sqlite_cursor.execute("""
            SELECT id, listing_id, score_total, score_price_value, score_component_quality,
                   score_condition_mileage, score_location_proximity, score_fit_geometry
            FROM scores
        """)

        score_rows = sqlite_cursor.fetchall()
        for row in score_rows:
            pg_cursor.execute("""
                INSERT INTO scores (
                    id, listing_id, score_total, score_price_value, score_component_quality,
                    score_condition_mileage, score_location_proximity, score_fit_geometry
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (id) DO NOTHING
            """, (
                row["id"], row["listing_id"], row["score_total"], row["score_price_value"],
                row["score_component_quality"],
                row["score_condition_mileage"], row["score_location_proximity"], row["score_fit_geometry"],
            ))

        pg_conn.commit()
        print(f"✓ Migrated {len(score_rows)} scores")

        # 6. Migrate spec_overrides
        print("Migrating spec_overrides...")
        sqlite_cursor.execute("""
            SELECT listing_id, field_name, corrected_value
            FROM spec_overrides
        """)

        override_rows = sqlite_cursor.fetchall()
        for row in override_rows:
            pg_cursor.execute("""
                INSERT INTO spec_overrides (listing_id, field_name, corrected_value)
                VALUES (%s, %s, %s)
                ON CONFLICT (listing_id, field_name) DO NOTHING
            """, (row["listing_id"], row["field_name"], row["corrected_value"]))

        pg_conn.commit()
        print(f"✓ Migrated {len(override_rows)} spec_overrides")

        # 7. Migrate deleted_listings
        print("Migrating deleted_listings...")
        sqlite_cursor.execute("""
            SELECT listing_id, reason
            FROM deleted_listings
        """)

        deleted_rows = sqlite_cursor.fetchall()
        for row in deleted_rows:
            pg_cursor.execute("""
                INSERT INTO deleted_listings (listing_id, reason)
                VALUES (%s, %s)
                ON CONFLICT (listing_id) DO NOTHING
            """, (row["listing_id"], row["reason"]))

        pg_conn.commit()
        print(f"✓ Migrated {len(deleted_rows)} deleted_listings")

        print()
        print("=" * 80)
        print("✓ MIGRATION COMPLETE")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"  Listings:          {len(rows)}")
        print(f"  Listing snapshots: {len(snapshot_rows)}")
        print(f"  Specifications:    {len(spec_rows)}")
        print(f"  Scores:            {len(score_rows)}")
        print(f"  Spec overrides:    {len(override_rows)}")
        print(f"  Deleted listings:  {len(deleted_rows)}")
        print()
        print("Old SQLite database remains at: data/emtb_hunter.db")
        print("Postgres now has all data. You can delete the SQLite file if desired.")
        print()

    except Exception as e:
        pg_conn.rollback()
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sqlite_cursor.close()
        sqlite_conn.close()
        pg_cursor.close()
        pg_conn.close()


if __name__ == "__main__":
    migrate()
