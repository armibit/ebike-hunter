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


def test_rejected_status_not_overridden_by_price_drop():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    base = {
        "portal": "subito",
        "portal_id": "11111",
        "url": "https://subito.it/rejected",
        "title": "Bici muscolare no motore",
        "price_raw": 3000,
        "currency": "EUR",
        "price_chf": 2857,
        "price_eur": 3000,
        "distance_km": 20.0,
        "status": "REJECTED",
        "rejection_reason": "no_motor_detected",
    }
    db.upsert_listing(base)

    # Rescraped at a lower price but re-classified REJECTED again — must not
    # be promoted to PRICE_DROP just because the price fell.
    rescanned = {**base, "price_raw": 2000, "price_chf": 1905, "price_eur": 2000}
    _, is_new, is_price_drop = db.upsert_listing(rescanned)
    assert is_new is False
    assert is_price_drop is False

    cursor = db.conn.cursor()
    cursor.execute("SELECT status FROM listings WHERE id = ?", ("subito_11111",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED", "REJECTED status was overridden by a price drop"

    price_drops = db.get_price_drops()
    assert not any(d["id"] == "subito_11111" for d in price_drops)

    db.close()
    Path(db_path).unlink()
    print("✅ REJECTED-not-overridden test passed")


def test_zero_price_not_treated_as_drop():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    base = {
        "portal": "decathlon",
        "portal_id": "22222",
        "url": "https://decathlon.ch/test",
        "title": "Rockrider E-ST 900",
        "price_raw": 2200,
        "currency": "CHF",
        "price_chf": 2200,
        "price_eur": 2310,
        "distance_km": 40.0,
        "status": "ACTIVE",
    }
    db.upsert_listing(base)

    # A failed scrape reporting price_raw=0.0 must never register as a drop.
    failed_scrape = {**base, "price_raw": 0.0, "price_chf": 0.0, "price_eur": 0.0}
    _, is_new, is_price_drop = db.upsert_listing(failed_scrape)
    assert is_new is False
    assert is_price_drop is False

    price_drops = db.get_price_drops()
    assert not any(d["id"] == "decathlon_22222" for d in price_drops)

    db.close()
    Path(db_path).unlink()
    print("✅ Zero-price-not-a-drop test passed")


def test_ai_analysis_columns_and_save():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    listing = {
        "portal": "tutti",
        "portal_id": "33333",
        "url": "https://tutti.ch/ai-test",
        "title": "Cube Stereo Hybrid 140",
        "description_raw": "Ottime condizioni, piccolo graffio anteriore.",
        "price_raw": 2100,
        "currency": "CHF",
        "price_chf": 2100,
        "price_eur": 2205,
        "distance_km": 5.0,
        "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(listing)

    cursor = db.conn.cursor()
    cursor.execute("SELECT ai_analysis, ai_score, ai_analyzed_at FROM listings WHERE id = ?", (listing_id,))
    row = cursor.fetchone()
    assert row["ai_analysis"] is None
    assert row["ai_score"] is None
    assert row["ai_analyzed_at"] is None

    db.save_ai_analysis(listing_id, "Solid buy, minor cosmetic wear only.", 81.5)

    cursor.execute("SELECT ai_analysis, ai_score, ai_analyzed_at FROM listings WHERE id = ?", (listing_id,))
    row = cursor.fetchone()
    assert row["ai_analysis"] == "Solid buy, minor cosmetic wear only."
    assert row["ai_score"] == 81.5
    assert row["ai_analyzed_at"] is not None

    db.close()
    Path(db_path).unlink()
    print("✅ AI analysis save test passed")


def test_get_listings_needing_ai_analysis():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    # Not yet analyzed — must be returned.
    pending = {
        "portal": "tutti", "portal_id": "1", "url": "https://tutti.ch/1",
        "title": "Pending bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    pending_id, _, _ = db.upsert_listing(pending)

    # Already analyzed and unchanged since — must NOT be returned.
    analyzed = {
        "portal": "tutti", "portal_id": "2", "url": "https://tutti.ch/2",
        "title": "Already analyzed bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    analyzed_id, _, _ = db.upsert_listing(analyzed)
    db.save_ai_analysis(analyzed_id, "Already judged.", 70.0)

    # Rejected — must NOT be returned regardless of ai_analysis state.
    rejected = {
        "portal": "tutti", "portal_id": "3", "url": "https://tutti.ch/3",
        "title": "Rejected bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0,
        "status": "REJECTED", "rejection_reason": "no_motor_detected",
    }
    db.upsert_listing(rejected)

    eligible = db.get_listings_needing_ai_analysis()
    eligible_ids = {row["id"] for row in eligible}

    assert pending_id in eligible_ids
    assert analyzed_id not in eligible_ids
    assert all("rejected" not in row["title"].lower() for row in eligible)

    db.close()
    Path(db_path).unlink()
    print("✅ get_listings_needing_ai_analysis filtering test passed")


def test_price_drop_after_ai_analysis_is_eligible_again():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    base = {
        "portal": "subito", "portal_id": "44444", "url": "https://subito.it/drop",
        "title": "Trek Rail 9.7", "price_raw": 2500, "currency": "EUR",
        "price_chf": 2381, "price_eur": 2500, "distance_km": 30.0, "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(base)
    db.save_ai_analysis(listing_id, "Solid at this price.", 75.0)

    # No longer eligible right after analysis.
    eligible_ids = {row["id"] for row in db.get_listings_needing_ai_analysis()}
    assert listing_id not in eligible_ids

    # A genuine price drop should surface it again for a fresh AI read.
    dropped = {**base, "price_raw": 2200, "price_chf": 2095, "price_eur": 2200}
    db.upsert_listing(dropped)

    eligible_ids = {row["id"] for row in db.get_listings_needing_ai_analysis()}
    assert listing_id in eligible_ids

    db.close()
    Path(db_path).unlink()
    print("✅ Price-drop re-eligibility test passed")


def test_set_manual_status_reject_and_restore():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    listing = {
        "portal": "tutti", "portal_id": "55555", "url": "https://tutti.ch/manual",
        "title": "Manually reviewed bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(listing)

    db.set_manual_status(listing_id, "REJECTED")
    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", (listing_id,))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert row["rejection_reason"]

    # Undo must clear the rejection_reason too, not just flip status back.
    db.set_manual_status(listing_id, "ACTIVE")
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", (listing_id,))
    row = cursor.fetchone()
    assert row["status"] == "ACTIVE"
    assert row["rejection_reason"] is None

    db.set_manual_status(listing_id, "SOLD")
    cursor.execute("SELECT status FROM listings WHERE id = ?", (listing_id,))
    assert cursor.fetchone()["status"] == "SOLD"

    try:
        db.set_manual_status(listing_id, "BOGUS")
        assert False, "should have raised ValueError"
    except ValueError:
        pass

    db.close()
    Path(db_path).unlink()
    print("✅ Manual status reject/restore test passed")


def test_get_listing_with_specs():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path)

    listing = {
        "portal": "tutti", "portal_id": "66666", "url": "https://tutti.ch/specs",
        "title": "Spec lookup bike", "price_raw": 2100, "currency": "CHF",
        "price_chf": 2100, "price_eur": 2205, "distance_km": 12.0, "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(listing)
    db.save_specifications(listing_id, {
        "motor_brand": "Unknown Motor", "motor_torque_nm": 60, "motor_verified": False,
        "battery_capacity_wh": 625, "frame_size": "M",
    })

    fetched = db.get_listing_with_specs(listing_id)
    assert fetched["price_chf"] == 2100
    assert fetched["distance_km"] == 12.0
    assert fetched["motor_brand"] == "Unknown Motor"
    assert fetched["motor_verified"] == 0

    assert db.get_listing_with_specs("nonexistent_id") is None

    db.close()
    Path(db_path).unlink()
    print("✅ get_listing_with_specs test passed")


if __name__ == "__main__":
    test_database_init()
    test_listing_insert()
    test_price_drop_detection()
    test_specifications_and_score()
    test_price_drop_status_persists()
    test_rejected_status_not_overridden_by_price_drop()
    test_zero_price_not_treated_as_drop()
    test_ai_analysis_columns_and_save()
    test_get_listings_needing_ai_analysis()
    test_price_drop_after_ai_analysis_is_eligible_again()
    test_set_manual_status_reject_and_restore()
    test_get_listing_with_specs()
    print("\n✅ All database tests passed!")
