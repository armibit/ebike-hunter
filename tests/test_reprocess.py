import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import psycopg2
import psycopg2.extras
import reprocess_all
from db.database import Database


def test_reprocess_refreshes_specs_of_rejected_listings(monkeypatch):
    """Regression: specs (e.g. the new brand field) were only re-saved for
    listings that pass the filters, so rejected rows kept stale values."""
    # Get test database URL
    test_database_url = os.getenv("TEST_DATABASE_URL", "postgresql:///postgres")
    test_schema = f"test_{uuid4().hex}"

    # Create fresh schema for this test
    pg_conn = psycopg2.connect(test_database_url)
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(f"CREATE SCHEMA {test_schema}")
    pg_conn.commit()
    pg_cursor.close()
    pg_conn.close()

    try:
        # Database with test schema
        db_url_with_schema = f"{test_database_url.split('?')[0]}?options=-c%20search_path%3D{test_schema}" if "?" in test_database_url else f"{test_database_url}?options=-c%20search_path%3D{test_schema}"
        db = Database(test_database_url, schema=test_schema)
        db.upsert_listing({
            "portal": "tutti", "portal_id": "1", "url": "https://example.com/1",
            "title": "Engwe L20 Foldable", "description_raw": "e-bike pieghevole",
            "price_raw": 900, "currency": "CHF", "price_chf": 900, "price_eur": 850,
            "location_raw": "Lugano", "status": "ACTIVE",
        })
        db.close()

        config = reprocess_all.load_config()
        config["app"]["database_url"] = test_database_url
        # Patch the schema parameter if reprocess_all can accept it
        monkeypatch.setattr(reprocess_all, "load_config", lambda: config)
        monkeypatch.setattr(sys, "argv", ["reprocess_all.py"])

        # Monkey-patch Database class to use test schema
        original_database = reprocess_all.Database
        reprocess_all.Database = lambda url: Database(url, schema=test_schema)

        reprocess_all.main()

        reprocess_all.Database = original_database

        db = Database(test_database_url, schema=test_schema)
        row = db.conn.cursor()
        row.execute(
            "SELECT l.status, s.brand FROM listings l JOIN specifications s ON s.listing_id = l.id"
        )
        result = row.fetchone()
        db.close()

        assert result["status"] == "REJECTED"
        assert result["brand"] == "Engwe"
    finally:
        # Cleanup: drop test schema
        pg_conn = psycopg2.connect(test_database_url)
        pg_cursor = pg_conn.cursor()
        pg_cursor.execute(f"DROP SCHEMA {test_schema} CASCADE")
        pg_conn.commit()
        pg_cursor.close()
        pg_conn.close()
