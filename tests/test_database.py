import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.database import Database


def test_database_init():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)
    assert db.conn is not None
    db.close()

    Path(db_path).unlink()
    print("✅ Database initialization test passed")


def test_listing_insert():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    listing = {
        "portal": "tutti",
        "portal_id": "12345",
        "url": "https://tutti.ch/test",
        "title": "Specialized Turbo Levo Comp",
        "description_raw": "Excellent condition",
        "price_raw": 2100,
        "currency": "CHF",
        "price_chf": 2100,
        "price_eur": 2205,
        "location_raw": "Lugano",
        "distance_km": 5.0,
        "region": "ticino"
    }

    listing_id, is_new, is_price_drop = db.upsert_listing(listing)
    assert is_new is True
    assert is_price_drop is False
    assert listing_id == "tutti_12345"

    db.close()
    Path(db_path).unlink()
    print("✅ Listing insert test passed")


def test_price_drop_detection():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    listing_v1 = {
        "portal": "subito",
        "portal_id": "98765",
        "url": "https://subito.it/test",
        "title": "Trek Rail 9.7",
        "price_raw": 2500,
        "currency": "EUR",
        "price_chf": 2381,
        "price_eur": 2500,
        "distance_km": 30.0
    }

    db.upsert_listing(listing_v1)

    # Price drop
    listing_v2 = listing_v1.copy()
    listing_v2["price_raw"] = 2200
    listing_v2["price_chf"] = 2095
    listing_v2["price_eur"] = 2200

    listing_id, is_new, is_price_drop = db.upsert_listing(listing_v2)
    assert is_new is False
    assert is_price_drop is True

    price_drops = db.get_price_drops()
    assert len(price_drops) == 1
    assert price_drops[0]["id"] == "subito_98765"

    db.close()
    Path(db_path).unlink()
    print("✅ Price drop detection test passed")


def test_specifications_and_score():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    listing = {
        "portal": "buycycle",
        "portal_id": "555",
        "url": "https://buycycle.com/test",
        "title": "Cube Stereo Hybrid 140",
        "price_raw": 1900,
        "currency": "EUR",
        "price_chf": 1809,
        "price_eur": 1900,
        "distance_km": 15.0,
        "status": "ACTIVE"
    }

    listing_id, _, _ = db.upsert_listing(listing)

    specs = {
        "brand": "Cube",
        "model": "Stereo Hybrid 140",
        "motor_brand": "Bosch",
        "motor_model": "Performance CX Gen4",
        "motor_torque_nm": 85,
        "battery_capacity_wh": 750,
        "frame_size": "M",
        "travel_front_mm": 140,
        "brakes_tier": "four_piston",
        "fork_tier": "mid"
    }

    db.save_specifications(listing_id, specs)

    score_data = {
        "score_total": 88.5,
        "score_price_value": 95.0,
        "score_component_quality": 85.0,
        "score_condition_mileage": 80.0,
        "score_location_proximity": 100.0,
        "score_fit_geometry": 100.0,
        "is_deal_target": True
    }

    db.save_score(listing_id, score_data)

    top_deals = db.get_top_deals(min_score=80.0, limit=10)
    assert len(top_deals) == 1
    assert top_deals[0]["score_total"] == 88.5

    db.close()
    Path(db_path).unlink()
    print("✅ Specifications and score test passed")


def test_price_drop_status_persists():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    base = {
        "portal": "tutti",
        "portal_id": "77777",
        "url": "https://tutti.ch/test2",
        "title": "Canyon Spectral:ON",
        "price_raw": 2400,
        "currency": "CHF",
        "price_chf": 2400,
        "price_eur": 2520,
        "distance_km": 10.0,
        "status": "ACTIVE",
    }
    db.upsert_listing(base)

    # Price drops
    dropped = {**base, "price_raw": 2100, "price_chf": 2100, "price_eur": 2205}
    _, _, is_price_drop = db.upsert_listing(dropped)
    assert is_price_drop is True

    # Same price again — status must remain PRICE_DROP
    _, _, is_price_drop2 = db.upsert_listing(dropped)
    assert is_price_drop2 is False

    drops = db.get_price_drops()
    assert any(d["id"] == "tutti_77777" for d in drops), "PRICE_DROP status not preserved on re-scan"

    db.close()
    Path(db_path).unlink()
    print("✅ PRICE_DROP persistence test passed")


if __name__ == "__main__":
    test_database_init()
    test_listing_insert()
    test_price_drop_detection()
    test_specifications_and_score()
    test_price_drop_status_persists()
    print("\n✅ All database tests passed!")
