import sys
import os
import uuid
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.database import Database, MANUAL_REJECT_REASON


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


def test_database_init(db):
    assert db.conn is not None
    print("✅ Database initialization test passed")


def test_ai_analysis_written_without_description_is_dropped_when_description_arrives(db):
    listing = {"portal": "subito", "portal_id": "1", "url": "https://s/1", "title": "Cube",
               "description_raw": "", "price_raw": 2000, "currency": "EUR", "price_chf": 1900,
               "price_eur": 2000, "location_raw": "Brescia", "distance_km": 50.0, "region": "lombardia"}
    listing_id, _, _ = db.upsert_listing(listing)
    db.save_ai_analysis(listing_id, "motore non dichiarato", 40.0)

    db.upsert_listing({**listing, "description_raw": "Bosch Performance Line CX Gen4 85 Nm, batteria 750 Wh"})

    cursor = db.conn.cursor()
    cursor.execute("SELECT ai_analysis, ai_score FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["ai_analysis"] is None and row["ai_score"] is None

    # an analysis made WITH a description survives later rescans
    db.save_ai_analysis(listing_id, "ok", 70.0)
    db.upsert_listing({**listing, "description_raw": "Bosch Performance Line CX Gen4 85 Nm, batteria 750 Wh"})
    cursor.execute("SELECT ai_analysis FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()[0] == "ok"

    print("✅ AI analysis persistence test passed")


def test_listing_insert(db):
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

    print("✅ Listing insert test passed")


def test_price_drop_detection(db):
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

    print("✅ Price drop detection test passed")


def test_specifications_and_score(db):
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

    print("✅ Specifications and score test passed")


def test_price_drop_status_persists(db):
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

    print("✅ PRICE_DROP persistence test passed")


def test_rejected_status_not_overridden_by_price_drop(db):
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
    cursor.execute("SELECT status FROM listings WHERE id = %s", ("subito_11111",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED", "REJECTED status was overridden by a price drop"

    price_drops = db.get_price_drops()
    assert not any(d["id"] == "subito_11111" for d in price_drops)

    print("✅ REJECTED-not-overridden test passed")


def test_zero_price_not_treated_as_drop(db):
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

    print("✅ Zero-price-not-a-drop test passed")


def test_ai_analysis_columns_and_save(db):
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
    cursor.execute("SELECT ai_analysis, ai_score, ai_analyzed_at FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["ai_analysis"] is None
    assert row["ai_score"] is None
    assert row["ai_analyzed_at"] is None

    db.save_ai_analysis(listing_id, "Solid buy, minor cosmetic wear only.", 81.5)

    cursor.execute("SELECT ai_analysis, ai_score, ai_analyzed_at FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["ai_analysis"] == "Solid buy, minor cosmetic wear only."
    assert row["ai_score"] == 81.5
    assert row["ai_analyzed_at"] is not None

    print("✅ AI analysis save test passed")


def test_get_listings_needing_ai_analysis(db):
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

    # Rejected by the scan's own hard filters, never scored — the whole
    # point of including rejects: the regex parser can miss a spec that's
    # actually in the description, so this MUST now be returned too.
    rejected_by_hard_filter = {
        "portal": "tutti", "portal_id": "3", "url": "https://tutti.ch/3",
        "title": "Rejected by hard filter", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0,
        "status": "REJECTED", "rejection_reason": "No motor detected (likely not an e-bike)",
    }
    rejected_by_hard_filter_id, _, _ = db.upsert_listing(rejected_by_hard_filter)

    # Rejected AFTER being scored (a spec correction that pushed it outside
    # your own criteria) — it was a real candidate once, so it MUST still
    # be returned, not silently skipped forever.
    rejected_scored = {
        "portal": "tutti", "portal_id": "4", "url": "https://tutti.ch/4",
        "title": "Rejected but scored bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0,
        "status": "REJECTED", "rejection_reason": "Taglia esclusa dopo correzione manuale",
    }
    rejected_scored_id, _, _ = db.upsert_listing(rejected_scored)
    db.save_score(rejected_scored_id, {
        "score_total": 82.0, "score_price_value": 82.0, "score_component_quality": 82.0,
        "score_condition_mileage": 82.0, "score_location_proximity": 82.0,
        "score_fit_geometry": 82.0, "is_deal_target": False, "breakdown": {},
    })

    # Rejected by hand with no other reason — your own explicit decision,
    # must be left alone, NOT sent to the AI.
    rejected_manually = {
        "portal": "tutti", "portal_id": "5", "url": "https://tutti.ch/5",
        "title": "Manually rejected bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    rejected_manually_id, _, _ = db.upsert_listing(rejected_manually)
    db.set_manual_status(rejected_manually_id, "REJECTED")  # no reason -> MANUAL_REJECT_REASON

    # SOLD — genuinely off the market, must NOT be returned.
    sold = {
        "portal": "tutti", "portal_id": "6", "url": "https://tutti.ch/6",
        "title": "Sold bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    sold_id, _, _ = db.upsert_listing(sold)
    db.set_manual_status(sold_id, "SOLD")

    eligible = db.get_listings_needing_ai_analysis()
    eligible_ids = {row["id"] for row in eligible}

    assert pending_id in eligible_ids
    assert analyzed_id not in eligible_ids
    assert rejected_by_hard_filter_id in eligible_ids
    assert rejected_scored_id in eligible_ids
    assert rejected_manually_id not in eligible_ids
    assert sold_id not in eligible_ids

    print("✅ get_listings_needing_ai_analysis filtering test passed")


def test_get_listings_needing_ai_analysis_force_ignores_already_analyzed(db):
    analyzed = {
        "portal": "tutti", "portal_id": "10", "url": "https://tutti.ch/10",
        "title": "Already analyzed bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    analyzed_id, _, _ = db.upsert_listing(analyzed)
    db.save_ai_analysis(analyzed_id, "Already judged.", 70.0)

    # Without force, an already-analyzed ACTIVE listing is skipped (existing
    # behavior) — with force=True it must come back regardless.
    assert analyzed_id not in {row["id"] for row in db.get_listings_needing_ai_analysis()}
    assert analyzed_id in {row["id"] for row in db.get_listings_needing_ai_analysis(force=True)}

    print("✅ get_listings_needing_ai_analysis force=True test passed")


def test_get_listings_needing_ai_analysis_by_listing_id(db):
    target = {
        "portal": "tutti", "portal_id": "11", "url": "https://tutti.ch/11",
        "title": "Target bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "REJECTED",
        "rejection_reason": "no_motor_detected",
    }
    target_id, _, _ = db.upsert_listing(target)

    other = {
        "portal": "tutti", "portal_id": "12", "url": "https://tutti.ch/12",
        "title": "Other bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    db.upsert_listing(other)

    # A specific listing_id is returned even though it's REJECTED (excluded
    # from the normal status filter) — a deliberate test-just-one-bike escape
    # hatch, so it must bypass the status/force filtering entirely.
    result = db.get_listings_needing_ai_analysis(listing_id=target_id)
    assert [row["id"] for row in result] == [target_id]

    print("✅ get_listings_needing_ai_analysis listing_id test passed")


def test_resolve_listing_id_accepts_numeric_rowid_or_real_id(db):
    listing = {
        "portal": "tutti", "portal_id": "99", "url": "https://tutti.ch/99",
        "title": "Numeric id bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(listing)

    cursor = db.conn.cursor()
    cursor.execute("SELECT numeric_id FROM listings WHERE id = %s", (listing_id,))
    numeric_id = cursor.fetchone()["numeric_id"]

    assert db.resolve_listing_id(str(numeric_id)) == listing_id
    assert db.resolve_listing_id(listing_id) == listing_id
    assert db.resolve_listing_id("999999") is None
    assert db.resolve_listing_id("does_not_exist") is None

    print("✅ resolve_listing_id test passed")


def test_get_high_score_ai_exclusions(db):
    def _make(portal_id, title, status, score_total, ai_analysis=None, rejection_reason=None):
        listing = {
            "portal": "tutti", "portal_id": portal_id, "url": f"https://tutti.ch/{portal_id}",
            "title": title, "price_raw": 2000, "currency": "CHF",
            "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": status,
        }
        if rejection_reason:
            listing["rejection_reason"] = rejection_reason
        listing_id, _, _ = db.upsert_listing(listing)
        db.save_score(listing_id, {
            "score_total": score_total, "score_price_value": score_total,
            "score_component_quality": score_total, "score_condition_mileage": score_total,
            "score_location_proximity": score_total, "score_fit_geometry": score_total,
            "is_deal_target": False, "breakdown": {},
        })
        if ai_analysis:
            db.save_ai_analysis(listing_id, ai_analysis, score_total)
        return listing_id

    # High score but rejected (manually, or by a spec correction), never
    # analyzed — now genuinely eligible (a scored listing is always in
    # scope regardless of status), so it must NOT be explained away here.
    rejected_scored_id = _make("20", "High score but rejected", "REJECTED", 82.0,
                                rejection_reason="Taglia esclusa dopo correzione manuale")

    # High score, ACTIVE, but already analyzed — must be explained
    # (needs --force to redo).
    analyzed_id = _make("21", "High score, already analyzed", "ACTIVE", 75.0, ai_analysis="Verdetto.")

    # High score, ACTIVE, never analyzed — genuinely eligible, must NOT
    # appear in the exclusions list.
    eligible_id = _make("22", "High score, still pending", "ACTIVE", 80.0)

    # Low score, ACTIVE, never analyzed — below the threshold, irrelevant.
    _make("23", "Low score", "ACTIVE", 40.0)

    exclusions = {row["id"]: row for row in db.get_high_score_ai_exclusions(min_score=70.0)}

    assert rejected_scored_id not in exclusions
    assert analyzed_id in exclusions
    assert "già analizzata" in exclusions[analyzed_id]["reason"]
    assert eligible_id not in exclusions

    # Confirm it actually comes back from the real eligibility query too,
    # not just "not excluded" in the diagnostic.
    assert rejected_scored_id in {row["id"] for row in db.get_listings_needing_ai_analysis()}

    # Rejected by the scan's own hard filters — never scored at all, but
    # now genuinely in scope too (the whole point of the fix), so it must
    # NOT be explained away even at min_score=0.
    unscored_listing = {
        "portal": "tutti", "portal_id": "24", "url": "https://tutti.ch/24",
        "title": "Rejected by hard filter, never scored", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0,
        "status": "REJECTED", "rejection_reason": "No motor detected (likely not an e-bike)",
    }
    unscored_id, _, _ = db.upsert_listing(unscored_listing)

    exclusions_zero = {row["id"]: row for row in db.get_high_score_ai_exclusions(min_score=0.0)}
    assert unscored_id not in exclusions_zero
    assert unscored_id in {row["id"] for row in db.get_listings_needing_ai_analysis()}

    # Rejected manually, with no other reason — your own explicit call,
    # left alone. Must be explained even at min_score=0 (it's unscored).
    manual_reject_listing = {
        "portal": "tutti", "portal_id": "25", "url": "https://tutti.ch/25",
        "title": "Manually rejected", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    manual_reject_id, _, _ = db.upsert_listing(manual_reject_listing)
    db.set_manual_status(manual_reject_id, "REJECTED")

    exclusions_zero = {row["id"]: row for row in db.get_high_score_ai_exclusions(min_score=0.0)}
    assert manual_reject_id in exclusions_zero
    assert "scartata manualmente" in exclusions_zero[manual_reject_id]["reason"]
    assert manual_reject_id not in {row["id"] for row in db.get_listings_needing_ai_analysis()}

    # SOLD, with a real score — genuinely off the market, must be
    # explained (and excluded from the real query) regardless of score.
    sold_id = _make("26", "Sold high scorer", "SOLD", 90.0)
    exclusions_high = {row["id"]: row for row in db.get_high_score_ai_exclusions(min_score=70.0)}
    assert sold_id in exclusions_high
    assert "SOLD" in exclusions_high[sold_id]["reason"]
    assert sold_id not in {row["id"] for row in db.get_listings_needing_ai_analysis()}

    print("✅ get_high_score_ai_exclusions test passed")


def test_price_drop_after_ai_analysis_is_eligible_again(db):
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

    print("✅ Price-drop re-eligibility test passed")


def test_set_manual_status_reject_and_restore(db):
    listing = {
        "portal": "tutti", "portal_id": "55555", "url": "https://tutti.ch/manual",
        "title": "Manually reviewed bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(listing)

    db.set_manual_status(listing_id, "REJECTED")
    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert row["rejection_reason"]

    # Undo must clear the rejection_reason too, not just flip status back.
    db.set_manual_status(listing_id, "ACTIVE")
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["status"] == "ACTIVE"
    assert row["rejection_reason"] is None

    db.set_manual_status(listing_id, "SOLD")
    cursor.execute("SELECT status FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()["status"] == "SOLD"

    try:
        db.set_manual_status(listing_id, "BOGUS")
        assert False, "should have raised ValueError"
    except ValueError:
        pass

    print("✅ Manual status reject/restore test passed")


def test_get_listing_with_specs(db):
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

    print("✅ get_listing_with_specs test passed")


def test_toggle_favorite(db):
    listing = {
        "portal": "tutti", "portal_id": "77777", "url": "https://tutti.ch/fav",
        "title": "Favorite candidate", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    listing_id, _, _ = db.upsert_listing(listing)

    cursor = db.conn.cursor()
    cursor.execute("SELECT is_favorite FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()["is_favorite"] == 0, "new listings must start unfavorited"

    assert db.toggle_favorite(listing_id) is True
    cursor.execute("SELECT is_favorite FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()["is_favorite"] == 1

    assert db.toggle_favorite(listing_id) is False
    cursor.execute("SELECT is_favorite FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()["is_favorite"] == 0

    try:
        db.toggle_favorite("does_not_exist")
        assert False, "should have raised ValueError"
    except ValueError:
        pass

    print("✅ Toggle favorite test passed")


def _rescan_listing(**overrides):
    base = {
        "portal": "tutti", "portal_id": "88888", "url": "https://tutti.ch/rescan",
        "title": "Rescanned bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 2100, "distance_km": 5.0, "status": "ACTIVE",
    }
    base.update(overrides)
    return base


def test_manual_reject_survives_rescan(db):
    # Regression: every scan used to write status=ACTIVE for a listing that
    # passes the hard filters, silently undoing the user's own "Scarta".
    listing_id, _, _ = db.upsert_listing(_rescan_listing())
    db.set_manual_status(listing_id, "REJECTED")

    # Next scan: still on the portal, now even cheaper.
    _, _, is_price_drop = db.upsert_listing(_rescan_listing(price_raw=1800, price_chf=1800))

    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason, price_chf FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert row["rejection_reason"] == MANUAL_REJECT_REASON
    assert row["price_chf"] == 1800, "price/text still refresh on a locked listing"
    assert is_price_drop is False

    print("✅ Manual reject survives rescan test passed")


def test_manual_sold_survives_rescan_and_restore_unlocks(db):
    listing_id, _, _ = db.upsert_listing(_rescan_listing())
    db.set_manual_status(listing_id, "SOLD")
    db.upsert_listing(_rescan_listing())

    cursor = db.conn.cursor()
    cursor.execute("SELECT status FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()["status"] == "SOLD"

    # "Ripristina attiva" hands the listing back to the scanner.
    db.set_manual_status(listing_id, "ACTIVE")
    db.upsert_listing(_rescan_listing(status="REJECTED", rejection_reason="Over budget"))
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = %s", (listing_id,))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert row["rejection_reason"] == "Over budget"

    print("✅ Manual sold survives rescan / restore unlocks test passed")


def test_automatic_reject_with_reason_is_not_locked(db):
    # A REJECTED set with a reason is the correction path's automatic
    # re-check, not the user's call — a later scan may still revive it.
    listing_id, _, _ = db.upsert_listing(_rescan_listing())
    db.set_manual_status(listing_id, "REJECTED", reason="Batteria troppo piccola dopo correzione manuale")
    db.upsert_listing(_rescan_listing())

    cursor = db.conn.cursor()
    cursor.execute("SELECT status FROM listings WHERE id = %s", (listing_id,))
    assert cursor.fetchone()["status"] == "ACTIVE"

    print("✅ Automatic reject not locked test passed")


def test_spec_overrides_roundtrip_and_clear(db):
    listing_id, _, _ = db.upsert_listing(_rescan_listing())
    assert db.get_spec_overrides(listing_id) == {}

    db.save_spec_overrides(listing_id, {"motor_brand": "Bosch", "motor_torque_nm": 85.0})
    assert db.get_spec_overrides(listing_id) == {"motor_brand": "Bosch", "motor_torque_nm": 85.0}

    # Clearing a field ("I don't know") drops the override instead of pinning None.
    db.save_spec_overrides(listing_id, {"motor_brand": None, "motor_torque_nm": 90})
    assert db.get_spec_overrides(listing_id) == {"motor_torque_nm": 90}

    # Deleting the listing removes its overrides too (FK cascade).
    db.delete_listing(listing_id)
    assert db.get_spec_overrides(listing_id) == {}

    print("✅ Spec overrides roundtrip test passed")


def test_migration_locks_legacy_manual_rejects(db):
    # A DB created before status_locked existed: the manual "Scarta" rows
    # (recognizable by their reason) must come out locked.
    manual_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="1"))
    auto_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="2"))
    db.set_manual_status(manual_id, "REJECTED")
    db.set_manual_status(auto_id, "REJECTED", reason="Over budget")

    cursor = db.conn.cursor()
    cursor.execute("SELECT id, status_locked FROM listings")
    locked = {row["id"]: row["status_locked"] for row in cursor.fetchall()}
    assert locked[manual_id] == 1
    assert locked[auto_id] == 0

    print("✅ Legacy manual-reject migration test passed")


def test_ai_scope_skips_rejections_no_correction_can_fix(db):
    # Sending an over-budget or too-far listing to the AI is wasted money:
    # no corrected_specs field can change price or distance.
    fixable_id, _, _ = db.upsert_listing(_rescan_listing(
        portal_id="1", status="REJECTED", rejection_reason="No motor detected (likely not an e-bike)",
    ))
    over_budget_id, _, _ = db.upsert_listing(_rescan_listing(
        portal_id="2", status="REJECTED",
        rejection_reason="Over budget (3500 > 3000 CHF); No motor detected (likely not an e-bike)",
    ))
    too_far_id, _, _ = db.upsert_listing(_rescan_listing(
        portal_id="3", status="REJECTED", rejection_reason="Too far (130 km > 105 km)",
    ))
    active_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="4"))

    eligible = {row["id"] for row in db.get_listings_needing_ai_analysis()}
    assert eligible == {fixable_id, active_id}

    # --force really processes everything in scope, hopeless rejections included.
    assert {row["id"] for row in db.get_listings_needing_ai_analysis(force=True)} == {
        fixable_id, over_budget_id, too_far_id, active_id,
    }
    # An explicit --id still analyzes whatever you point it at.
    assert [row["id"] for row in db.get_listings_needing_ai_analysis(listing_id=too_far_id)] == [too_far_id]
    # limit still applies after the filtering.
    assert len(db.get_listings_needing_ai_analysis(limit=1)) == 1

    print("✅ AI scope skips uncorrectable rejections test passed")


def test_problematic_mode_targets_fixable_spec_gaps_even_if_analyzed(db):
    ok_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="1"))
    db.save_specifications(ok_id, {"motor_brand": "Bosch", "motor_torque_nm": 85, "motor_verified": True,
                                   "battery_capacity_wh": 625, "frame_size": "M"})
    guessed_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="2"))
    db.save_specifications(guessed_id, {"motor_brand": "Unknown Motor", "motor_torque_nm": 60, "motor_verified": False,
                                        "battery_capacity_wh": 625, "frame_size": "M"})
    no_size_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="3"))
    db.save_specifications(no_size_id, {"motor_brand": "Bosch", "motor_torque_nm": 85, "motor_verified": True,
                                        "battery_capacity_wh": 625, "frame_size": "unknown"})
    fixable_reject_id, _, _ = db.upsert_listing(_rescan_listing(
        portal_id="4", status="REJECTED", rejection_reason="No motor detected (likely not an e-bike)"))
    hopeless_id, _, _ = db.upsert_listing(_rescan_listing(
        portal_id="5", status="REJECTED", rejection_reason="Over budget (3500 > 3000 CHF)"))
    # Already analyzed: the problematic mode re-runs it anyway.
    db.save_ai_analysis(guessed_id, "Vecchia analisi", 50)

    picked = [row["id"] for row in db.get_listings_needing_ai_analysis(problematic_only=True)]
    assert set(picked) == {guessed_id, no_size_id, fixable_reject_id}
    # Never-analyzed first, the already-analyzed one last (resumable with --limit).
    assert picked[-1] == guessed_id
    assert hopeless_id not in picked and ok_id not in picked

    print("✅ Problematic AI mode test passed")


def test_force_mode_walks_the_backlog_stalest_first(db):
    ids = [db.upsert_listing(_rescan_listing(portal_id=str(i)))[0] for i in range(3)]
    db.save_ai_analysis(ids[0], "a", 50)
    db.save_ai_analysis(ids[1], "b", 50)

    first = db.get_listings_needing_ai_analysis(force=True, limit=2)
    assert [row["id"] for row in first] == [ids[2], ids[0]], "never analyzed, then oldest analysis"

    for row in first:
        db.save_ai_analysis(row["id"], "new", 60)
    second = db.get_listings_needing_ai_analysis(force=True, limit=2)
    assert second[0]["id"] == ids[1], "next run continues where the last one stopped"

    print("✅ Force mode resumable ordering test passed")


def test_deleted_listing_is_remembered(db):
    listing_id, _, _ = db.upsert_listing(_rescan_listing())
    assert db.is_deleted(listing_id) is False

    db.delete_listing(listing_id)

    assert db.is_deleted(listing_id) is True
    assert db.get_listing_with_specs(listing_id) is None
    print("✅ Deleted-listing tombstone test passed")


def test_mark_unavailable_respects_manual_decisions(db):
    live_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="1"))
    rejected_by_hand_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="2"))
    db.set_manual_status(rejected_by_hand_id, "REJECTED")

    assert db.mark_unavailable(live_id) is True
    assert db.mark_unavailable(rejected_by_hand_id) is False
    assert db.mark_unavailable("tutti_does_not_exist") is False

    cursor = db.conn.cursor()
    cursor.execute("SELECT id, status, delisted_at FROM listings")
    rows = {row["id"]: row for row in cursor.fetchall()}
    assert rows[live_id]["status"] == "SOLD" and rows[live_id]["delisted_at"]
    assert rows[rejected_by_hand_id]["status"] == "REJECTED"
    print("✅ mark_unavailable test passed")


def test_listings_to_verify_are_the_unseen_ones_least_recently_checked_first(db):
    old_a, _, _ = db.upsert_listing(_rescan_listing(portal_id="1"))
    old_b, _, _ = db.upsert_listing(_rescan_listing(portal_id="2"))
    db.mark_checked(old_a)  # checked more recently than old_b
    from datetime import datetime, timezone
    scan_started = datetime.now(timezone.utc).isoformat()
    seen_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="3"))  # seen by this scan
    sold_id, _, _ = db.upsert_listing(_rescan_listing(portal_id="4"))
    cursor = db.conn.cursor()
    cursor.execute("UPDATE listings SET last_seen_at = %s WHERE id = %s", ('2000-01-01', sold_id))
    db.conn.commit()
    db.mark_unavailable(sold_id)

    to_verify = [row["id"] for row in db.get_listings_to_verify(scan_started, limit=10)]
    assert to_verify == [old_b, old_a]
    assert [row["id"] for row in db.get_listings_to_verify(scan_started, limit=1)] == [old_b]
    print("✅ Listings-to-verify test passed")


def test_price_history_records_increases_and_currency_switches(db):
    listing_id, _, _ = db.upsert_listing(_rescan_listing(price_raw=2000, price_chf=2000))
    db.upsert_listing(_rescan_listing(price_raw=2000, price_chf=2000))           # unchanged: no snapshot
    _, _, drop = db.upsert_listing(_rescan_listing(price_raw=2200, price_chf=2200))  # increase
    assert drop is False

    # Same bike re-posted in EUR: 2100 EUR ≈ 2000 CHF is a drop in real terms,
    # even though 2100 > 2200 would say nothing and 2100 < 2200 is a
    # meaningless cross-currency comparison.
    _, _, drop = db.upsert_listing(_rescan_listing(price_raw=2100, currency="EUR", price_chf=2000))
    assert drop is True

    cursor = db.conn.cursor()
    cursor.execute("SELECT price_raw, currency FROM listing_snapshots WHERE listing_id = %s ORDER BY id", (listing_id,))
    assert [(r["price_raw"], r["currency"]) for r in cursor.fetchall()] == [
        (2000, "CHF"), (2200, "CHF"), (2100, "EUR"),
    ]
    print("✅ Price history test passed")


def test_cross_currency_increase_is_not_a_drop(db):
    db.upsert_listing(_rescan_listing(price_raw=2000, price_chf=2000))
    # 2000 EUR ≈ 1905 CHF? No: here CHF value goes UP (2100) though the raw
    # number is equal — compare in CHF, not raw.
    _, _, drop = db.upsert_listing(_rescan_listing(price_raw=2000, currency="EUR", price_chf=2100))
    assert drop is False
    print("✅ Cross-currency increase test passed")


def test_filtered_top_deals_hides_rejected_unless_asked(db):
    """Regression: "Tutti" in the Top 10 used to include REJECTED listings;
    now they're hidden unless show_rejected (or status='rejected') is set."""
    score = {"score_total": 80.0, "score_price_value": 80.0, "score_component_quality": 80.0,
             "score_condition_mileage": 80.0, "score_location_proximity": 80.0,
             "score_fit_geometry": 80.0, "is_deal_target": True}
    ids = {}
    for pid in ("ok", "ko"):
        ids[pid], _, _ = db.upsert_listing({
            "portal": "tutti", "portal_id": pid, "url": f"https://tutti.ch/{pid}", "title": f"Bike {pid}",
            "price_raw": 1900, "currency": "CHF", "price_chf": 1900, "price_eur": 1800,
            "distance_km": 10.0, "status": "ACTIVE"})
        db.save_score(ids[pid], score)
    db.set_manual_status(ids["ko"], "REJECTED")

    assert {d["id"] for d in db.get_filtered_top_deals()} == {ids["ok"]}
    assert {d["id"] for d in db.get_filtered_top_deals(show_rejected=True)} == set(ids.values())
    assert {d["id"] for d in db.get_filtered_top_deals(status="rejected")} == {ids["ko"]}
    print("✅ Filtered top deals test passed")
