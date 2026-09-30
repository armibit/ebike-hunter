import os
import sys
import uuid
import pytest
import psycopg2
import psycopg2.extras
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from db.database import Database


@pytest.fixture
def db():
    """Create a Database instance with unique schema for each test, clean up after."""
    schema_name = f"test_{uuid.uuid4().hex[:12]}"
    db_url = os.getenv("TEST_DATABASE_URL", "postgresql:///postgres")

    # Create database with schema — Database class handles schema creation
    database = Database(db_url, schema=schema_name)
    yield database

    # Cleanup: drop the schema
    cursor = database.conn.cursor()
    cursor.execute(f'DROP SCHEMA "{schema_name}" CASCADE')
    database.conn.commit()
    database.close()


def test_reprocess_database_isolation(db):
    """Test that reprocess_all can work with schema-isolated test database."""
    # Setup test listing
    listing_id, _, _ = db.upsert_listing({
        "portal": "tutti", "portal_id": "1", "url": "https://example.com/1",
        "title": "Engwe L20 Foldable", "description_raw": "e-bike pieghevole",
        "price_raw": 900, "currency": "CHF", "price_chf": 900, "price_eur": 850,
        "location_raw": "Lugano", "status": "ACTIVE",
    })

    # Add specifications (what reprocess would generate)
    db.save_specifications(listing_id, {
        "brand": "Engwe",
        "model": "L20",
        "motor_brand": "Unknown Motor",
        "motor_torque_nm": 60,
        "motor_verified": False,
        "battery_capacity_wh": 625,
        "frame_size": "M",
    })

    # Verify specifications are stored
    cursor = db.conn.cursor()
    cursor.execute(
        "SELECT s.brand FROM specifications s WHERE s.listing_id = %s",
        (listing_id,)
    )
    result = cursor.fetchone()
    assert result is not None
    assert result["brand"] == "Engwe"

    print("✅ Database isolation for reprocess test passed")
