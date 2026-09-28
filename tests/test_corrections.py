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


def _fresh_db_with_auto_rejected_no_motor():
    # Mirrors what run.py's process_listing() writes for a listing its own
    # hard filters rejected — REJECTED, in English (matching the actual
    # reject_reasons text run.py appends), and crucially never scored at
    # all (run.py only calls scorer.calculate_score() in the accepted
    # branch).
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    db.upsert_listing({
        "portal": "x", "portal_id": "1", "url": "https://example.com/1", "title": "Test Bike",
        "price_raw": 2000, "currency": "CHF", "price_chf": 2000, "price_eur": 1900,
        "distance_km": 10, "status": "REJECTED",
        "rejection_reason": "No motor detected (likely not an e-bike)",
    })
    db.save_specifications("x_1", {
        "motor_brand": None, "motor_torque_nm": None, "motor_verified": False,
        "battery_capacity_wh": 625, "frame_size": "unknown",
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


def test_apply_spec_correction_rejects_hardtail_on_active_listing():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    result = apply_spec_correction(db, scorer, "x_1", {"suspension_type": "hardtail"}, config=CONFIG)

    assert result is not None, "score must still be saved even though the listing gets rejected"
    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert "Hardtail" in row["rejection_reason"]

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction rejects hardtail correction on active listing")


def test_apply_spec_correction_restores_auto_rejected_listing_stays_rejected_if_hardtail():
    db_path, db = _fresh_db_with_auto_rejected_no_motor()
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(
        db, scorer, "x_1",
        {"motor_brand": "Bosch", "motor_torque_nm": 85, "suspension_type": "hardtail"},
        config=CONFIG,
    )

    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED", "a real motor alone must not resurrect a hardtail"
    assert "Hardtail" in row["rejection_reason"]

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction keeps auto-rejected hardtail listing rejected even with a good motor")


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


def test_apply_spec_correction_restores_auto_rejected_listing_when_criteria_now_met():
    # The whole point of sending REJECTED listings to the AI pass: the
    # regex parser found no motor at all, but the AI read one off the
    # description text — it should come back to life as ACTIVE, not stay
    # rejected forever just because the correction path never re-checked.
    db_path, db = _fresh_db_with_auto_rejected_no_motor()
    scorer = ScoringEngine(CONFIG)

    result = apply_spec_correction(
        db, scorer, "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG
    )

    assert result is not None
    assert result["score_total"] > 0, "a restored listing must actually get scored"

    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "ACTIVE"
    assert row["rejection_reason"] is None

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction restores auto-rejected listing to ACTIVE")


def test_apply_spec_correction_keeps_auto_rejected_listing_rejected_if_still_failing():
    # AI supplies a motor, but it's still below the hard minimum — must
    # stay REJECTED, with the reason updated to reflect the real problem.
    db_path, db = _fresh_db_with_auto_rejected_no_motor()
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Fazua", "motor_torque_nm": 40}, config=CONFIG)

    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert "40" in row["rejection_reason"]

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction keeps still-failing auto-rejected listing REJECTED")


def test_apply_spec_correction_does_not_restore_manually_rejected_listing():
    # You rejected this one yourself, for whatever reason — a later spec
    # correction must never silently flip it back to ACTIVE behind your
    # back, however good the correction looks.
    db_path, db = _fresh_db_with_unverified_motor()
    db.set_manual_status("x_1", "REJECTED")  # no reason -> MANUAL_REJECT_REASON
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG)

    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    assert row["status"] == "REJECTED"
    assert row["rejection_reason"] == "Scartata manualmente dall'utente"

    db.close()
    Path(db_path).unlink()
    print("✅ apply_spec_correction leaves a manually rejected listing alone")


def _fresh_db_with_auto_rejected(rejection_reason, price_chf=2000, **spec_overrides):
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    db.upsert_listing({
        "portal": "x", "portal_id": "1", "url": "https://example.com/1", "title": "Test Bike",
        "price_raw": price_chf, "currency": "CHF", "price_chf": price_chf, "price_eur": price_chf,
        "distance_km": 10, "status": "REJECTED", "rejection_reason": rejection_reason,
    })
    specs = {
        "motor_brand": None, "motor_torque_nm": None, "motor_verified": None,
        "battery_capacity_wh": 625, "frame_size": "unknown",
    }
    specs.update(spec_overrides)
    db.save_specifications("x_1", specs)
    return db_path, db


def _status_and_reason(db):
    cursor = db.conn.cursor()
    cursor.execute("SELECT status, rejection_reason FROM listings WHERE id = ?", ("x_1",))
    row = cursor.fetchone()
    return row["status"], row["rejection_reason"]


def test_ai_motor_does_not_restore_over_budget_listing():
    # Regression: the restore check only re-ran the spec filters, so an
    # AI-read motor brought back a listing rejected for being over budget.
    db_path, db = _fresh_db_with_auto_rejected(
        "Over budget (3500 > 3000 CHF); No motor detected (likely not an e-bike)", price_chf=3500,
    )
    apply_spec_correction(db, ScoringEngine(CONFIG), "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG)

    status, reason = _status_and_reason(db)
    assert status == "REJECTED"
    assert "Over budget" in reason

    db.close()
    Path(db_path).unlink()
    print("✅ AI motor correction does not restore over-budget listing")


def test_ai_motor_does_not_restore_red_flag_listing():
    db_path, db = _fresh_db_with_auto_rejected(
        "No motor detected (likely not an e-bike); Red flags: senza caricatore",
        has_red_flag=True, red_flag_details=["senza caricatore"],
    )
    apply_spec_correction(db, ScoringEngine(CONFIG), "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG)

    status, reason = _status_and_reason(db)
    assert status == "REJECTED"
    assert "Red flags" in reason

    db.close()
    Path(db_path).unlink()
    print("✅ AI motor correction does not restore red-flag listing")


def test_ai_motor_does_not_restore_wrong_category_listing():
    # excluded_category isn't stored in specifications — only the scan's
    # reject reason remembers it, so that's what must block the restore.
    db_path, db = _fresh_db_with_auto_rejected(
        "Wrong category (fat bike); No motor detected (likely not an e-bike)",
    )
    apply_spec_correction(db, ScoringEngine(CONFIG), "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG)

    status, reason = _status_and_reason(db)
    assert status == "REJECTED"
    assert "Wrong category" in reason

    db.close()
    Path(db_path).unlink()
    print("✅ AI motor correction does not restore wrong-category listing")


def test_restore_uses_stored_battery_not_only_corrected_fields():
    # The parser found a 400Wh battery (below the 500Wh minimum) — a motor
    # correction alone must not bring the listing back.
    db_path, db = _fresh_db_with_auto_rejected(
        "No motor detected (likely not an e-bike); Small battery (400Wh < 500Wh)",
        battery_capacity_wh=400,
    )
    apply_spec_correction(db, ScoringEngine(CONFIG), "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG)

    status, reason = _status_and_reason(db)
    assert status == "REJECTED"
    assert "400" in reason

    db.close()
    Path(db_path).unlink()
    print("✅ Restore re-checks the stored battery")


def test_ai_frame_size_outside_targets_does_not_restore():
    # The restore path used to reject only the parser's literal "disallowed"
    # marker, so an explicit "XL" read by the AI passed.
    db_path, db = _fresh_db_with_auto_rejected("No motor detected (likely not an e-bike)")
    apply_spec_correction(
        db, ScoringEngine(CONFIG), "x_1",
        {"motor_brand": "Bosch", "motor_torque_nm": 85, "frame_size": "XL"}, config=CONFIG,
    )

    status, reason = _status_and_reason(db)
    assert status == "REJECTED"
    assert "XL" in reason

    db.close()
    Path(db_path).unlink()
    print("✅ AI frame size outside targets does not restore")


def test_correction_never_changes_a_status_the_user_locked():
    # Marked sold by hand, then a correction that would normally reject it:
    # it's the user's call, so it stays SOLD.
    db_path, db = _fresh_db_with_unverified_motor()
    db.set_manual_status("x_1", "SOLD")

    apply_spec_correction(db, ScoringEngine(CONFIG), "x_1", {"frame_size": "XL"}, config=CONFIG)

    status, _ = _status_and_reason(db)
    assert status == "SOLD"

    db.close()
    Path(db_path).unlink()
    print("✅ Correction leaves a user-locked status alone")


def test_correction_is_stored_as_override_and_cleared_by_null():
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 85, "seller_name": "x"})
    assert db.get_spec_overrides("x_1") == {"motor_brand": "Bosch", "motor_torque_nm": 85}

    apply_spec_correction(db, scorer, "x_1", {"motor_brand": None})
    assert db.get_spec_overrides("x_1") == {"motor_torque_nm": 85}

    db.close()
    Path(db_path).unlink()
    print("✅ Corrections are persisted as overrides")


def test_rescore_from_db_keeps_unverified_motor_penalty():
    # Regression: specs read back from SQLite carry motor_verified=0, and
    # scoring tested `is False`, so correcting an unrelated field (battery)
    # silently upgraded an unverified motor to full tier credit.
    db_path, db = _fresh_db_with_unverified_motor()
    scorer = ScoringEngine(CONFIG)

    unverified = apply_spec_correction(db, scorer, "x_1", {"battery_capacity_wh": 625})
    verified = apply_spec_correction(db, scorer, "x_1", {"motor_brand": "Bosch", "motor_torque_nm": 60})

    assert verified["score_component_quality"] > unverified["score_component_quality"]

    db.close()
    Path(db_path).unlink()
    print("✅ Rescore from DB keeps the unverified-motor penalty")


if __name__ == "__main__":
    test_apply_spec_correction_marks_verified_and_rescores_higher()
    test_apply_spec_correction_regenerates_user_analysis_text()
    test_apply_spec_correction_rejects_out_of_target_frame_size()
    test_apply_spec_correction_keeps_active_for_in_target_frame_size()
    test_apply_spec_correction_rejects_hardtail_on_active_listing()
    test_apply_spec_correction_restores_auto_rejected_listing_stays_rejected_if_hardtail()
    test_apply_spec_correction_rejects_weak_motor_below_minimum()
    test_apply_spec_correction_without_config_skips_reject_check()
    test_apply_spec_correction_ignores_unknown_fields()
    test_apply_spec_correction_unknown_listing_returns_none()
    test_apply_spec_correction_clearing_field_does_not_mark_verified()
    test_apply_spec_correction_restores_auto_rejected_listing_when_criteria_now_met()
    test_apply_spec_correction_keeps_auto_rejected_listing_rejected_if_still_failing()
    test_apply_spec_correction_does_not_restore_manually_rejected_listing()
    test_ai_motor_does_not_restore_over_budget_listing()
    test_ai_motor_does_not_restore_red_flag_listing()
    test_ai_motor_does_not_restore_wrong_category_listing()
    test_restore_uses_stored_battery_not_only_corrected_fields()
    test_ai_frame_size_outside_targets_does_not_restore()
    test_correction_never_changes_a_status_the_user_locked()
    test_correction_is_stored_as_override_and_cleared_by_null()
    test_rescore_from_db_keeps_unverified_motor_penalty()
    print("\n✅ All corrections tests passed!")
