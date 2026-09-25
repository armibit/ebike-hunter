import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.database import Database
from pipeline.corrections import apply_spec_correction
from pipeline.scoring import ScoringEngine

CONFIG = {
    "buyer_profile": {
        "budget": {"target_price": 2200, "hard_max_price": 3000},
        "rider_specs": {"target_sizes": ["M", "S2", "S3", "44cm"]},
    },
    "hardware_requirements": {"min_motor_torque_nm": 60, "min_battery_wh": 500},
    "scoring_weights": {
        "price_value": 0.35, "component_quality": 0.25, "condition_mileage": 0.15,
        "location_proximity": 0.15, "fit_geometry": 0.10,
    },
}


def _fresh_db_with_unverified_motor():
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    db.upsert_listing({
        "portal": "x", "portal_id": "1", "url": "https://example.com/1", "title": "Test Bike",
        "price_raw": 2000, "currency": "CHF", "price_chf": 2000, "price_eur": 1900,
        "distance_km": 10, "status": "ACTIVE",
    })
    db.save_specifications("x_1", {
        "motor_brand": "Unknown Motor", "motor_torque_nm": 60, "motor_verified": False,
        "battery_capacity_wh": 625, "frame_size": "unknown",
    })
    db.save_score("x_1", {
        "score_total": 60.0, "score_price_value": 60.0, "score_component_quality": 60.0,
        "score_condition_mileage": 60.0, "score_location_proximity": 60.0,
        "score_fit_geometry": 60.0, "is_deal_target": False, "breakdown": {},
    })
    return db_path, db


def test_apply_spec_correction_marks_verified_and_rescores_higher():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    result = apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85})

    assert result is not None
    assert result["score_total"] > 60.0

    row = db.get_listing_with_specs("x_1")
    assert row["motor_brand"] == "Bosch"
    assert row["motor_torque_nm"] == 85
    assert row["motor_verified"] == 1

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction verifies motor and rescores higher")


def test_apply_spec_correction_regenerates_user_analysis_text():
    # Otherwise the written verdict keeps describing the pre-correction
    # specs (e.g. still reading as an unverified motor right after you've
    # just confirmed it) even though the score and spec grid have moved on.
    db_path, db = _fresh_db_with_unverified_motor()
    db.save_user_analysis("x_1", "Vecchio testo obsoleto.")
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85})

    cursor = db.conn.cursor()
    cursor.execute("SELECT user_analysis FROM listings WHERE id = ?", ("x_1",))
    analysis = cursor.fetchone()["user_analysis"]
    assert analysis != "Vecchio testo obsoleto."
    assert "Raccomandazione" in analysis

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction regenerates user_analysis text")


def test_apply_spec_correction_rejects_out_of_target_frame_size():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    result = apply_spec_correction(db, scorer, "x_1", {"frame_size": "XL"}, config=CONFIG)

    assert result is not None, "score must still be saved even though the listing gets rejected"
    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert "XL" in row["rejection_reason"]

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction rejects out-of-target frame size")


def test_apply_spec_correction_keeps_active_for_in_target_frame_size():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"frame_size": "S2"}, config=CONFIG)

    cursor = db.conn.cursor()
    cursor.execute("SELECT status FROM listings WHERE id = ?", ("x_1",))
    assert cursor.fetchone()["status"] == "ACTIVE"

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction keeps in-target frame size active")


def test_apply_spec_correction_rejects_weak_motor_below_minimum():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Fazua", "motor_torque_nm": 50}, config=CONFIG)

    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert "50" in row["rejection_reason"]

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction rejects weak motor below minimum")


def test_apply_spec_correction_without_config_skips_reject_check():
    # config=None (the default) — backward compatible, no reject-on-
    # correction behavior unless a caller opts in by passing config.
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"frame_size": "XL"})

    cursor = db.conn.cursor()
    cursor.execute("SELECT status FROM listings WHERE id = ?", ("x_1",))
    assert cursor.fetchone()["status"] == "ACTIVE"

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction without config skips reject check")


def test_apply_spec_correction_ignores_unknown_fields():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    result = apply_spec_correction(db, scorer, "x_1", {"seller_name": "should be ignored"})

    assert result is None, "no editable field present — nothing to apply or rescore"

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction ignores non-editable fields")


def test_apply_spec_correction_unknown_listing_returns_none():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    result = apply_spec_correction(db, scorer, "does_not_exist", {"motor_brand": "Bosch"})

    assert result is None

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction unknown-listing test passed")


def test_apply_spec_correction_clearing_field_does_not_mark_verified():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    # Explicitly clearing the motor (null) must NOT flip motor_verified —
    # "I don't know" is not "I verified it".
    result = apply_spec_correction(db, scorer, "x_1", {"motor_brand": None, "motor_torque_nm": None})

    assert result is not None
    row = db.get_listing_with_specs("x_1")
    assert row["motor_brand"] is None
    assert row["motor_verified"] == 0, "clearing the motor must not count as verifying it"

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction clear-field test passed")


if __name__ == "__main__":
    test_apply_spec_correction_marks_verified_and_rescores_higher()
    test_apply_spec_correction_regenerates_user_analysis_text()
    test_apply_spec_correction_rejects_out_of_target_frame_size()
    test_apply_spec_correction_keeps_active_for_in_target_frame_size()
    test_apply_spec_correction_rejects_weak_motor_below_minimum()
    test_apply_spec_correction_without_config_skips_reject_check()
    test_apply_spec_correction_ignores_unknown_fields()
    test_apply_spec_correction_unknown_listing_returns_none()
    test_apply_spec_correction_clearing_field_does_not_mark_verified()
    print("\n✅ All corrections tests passed!")
