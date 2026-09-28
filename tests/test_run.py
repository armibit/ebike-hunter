import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import run


def _specs(**overrides):
    base = {
        "motor_brand": "Bosch", "motor_torque_nm": 85, "motor_verified": True,
        "battery_capacity_wh": 625, "frame_size": "M", "suspension_type": "full_suspension",
        "travel_front_mm": 150, "brakes_tier": "four_piston", "odometer_km": 500,
        "red_flag_details": [],
    }
    base.update(overrides)
    return base


def test_generate_user_analysis_is_italian_not_english():
    # Regression test: this text used to be hardcoded in English while the
    # rest of the dashboard is Italian-facing.
    text = run.generate_user_analysis(85, _specs(), {"distance_km": 10, "price_chf": 2000})

    italian_markers = ["FORTEMENTE CONSIGLIATA", "Posizione", "Prezzo", "Raccomandazione"]
    for marker in italian_markers:
        assert marker in text, f"expected Italian marker {marker!r} in analysis text"

    english_leftovers = ["HIGHLY RECOMMENDED", "WORTH CONSIDERING", "Excellent power", "Good range", "Recommendation:"]
    for leftover in english_leftovers:
        assert leftover not in text, f"found leftover English text: {leftover!r}"

    print("✅ generate_user_analysis Italian-language test passed")


def test_generate_user_analysis_verdict_tiers():
    high = run.generate_user_analysis(90, _specs(), {"distance_km": 10, "price_chf": 2000})
    assert "FORTEMENTE CONSIGLIATA" in high

    low = run.generate_user_analysis(40, _specs(), {"distance_km": 10, "price_chf": 2000})
    assert "PRIORITÀ BASSA" in low

    print("✅ generate_user_analysis verdict tiers test passed")


def test_generate_user_analysis_does_not_duplicate_the_spec_grid():
    # Motor/battery/frame/suspension/brakes are already shown, with a
    # verified/unverified badge, in the detail card's spec grid — repeating
    # them here as prose bullets would just be redundant reading, so this
    # text should stick to what the grid can't show (condition read,
    # location framing, price framing, red flags, the headline verdict).
    text = run.generate_user_analysis(85, _specs(), {"distance_km": 10, "price_chf": 2000})

    for should_be_absent in ("Motore:", "Batteria:", "Taglia:", "Sospensione:", "Freni:"):
        assert should_be_absent not in text, f"spec bullet {should_be_absent!r} should have been dropped"

    for should_be_present in ("Condizione:", "Posizione:", "Prezzo:"):
        assert should_be_present in text

    print("✅ generate_user_analysis non-duplication test passed")


def test_generate_user_analysis_includes_red_flags():
    text = run.generate_user_analysis(
        70, _specs(red_flag_details=["senza caricatore"]), {"distance_km": 10, "price_chf": 2000}
    )
    assert "Segnalazioni" in text
    assert "senza caricatore" in text

    print("✅ generate_user_analysis red flags test passed")


CONFIG = {
    "buyer_profile": {
        "budget": {"target_price": 2200, "hard_max_price": 3000},
        "rider_specs": {"target_sizes": ["M", "S2", "S3"]},
    },
    "hardware_requirements": {"min_motor_torque_nm": 60, "min_battery_wh": 500},
    "scoring_weights": {
        "price_value": 0.35, "component_quality": 0.25, "condition_mileage": 0.15,
        "location_proximity": 0.15, "fit_geometry": 0.10,
    },
}


class _FakeParser:
    """Stands in for RegexParser so a test controls exactly what "the
    parser read" on each scan."""

    def __init__(self, **specs):
        self.specs = specs

    def parse(self, title, description):
        return {
            "suspension_type": "full_suspension", "motor_brand": None, "motor_model": None,
            "motor_torque_nm": None, "motor_verified": None, "battery_capacity_wh": 625,
            "frame_size": "M", "has_red_flag": False, "red_flag_details": [],
            **self.specs,
        }


def _raw_listing(**overrides):
    base = {
        "portal": "tutti", "portal_id": "42", "url": "https://tutti.ch/42", "title": "Cube Stereo Hybrid",
        "description_raw": "Bici in ottime condizioni", "price_raw": 2000, "currency": "CHF",
        "location_raw": "Lugano",
    }
    base.update(overrides)
    return base


def _process(db, parser):
    from pipeline.normalizer import Normalizer
    from pipeline.scoring import ScoringEngine
    return run.process_listing(_raw_listing(), parser, Normalizer(), ScoringEngine(CONFIG), db, CONFIG)


def _fresh_db():
    import tempfile
    from db.database import Database
    db_path = tempfile.mktemp(suffix=".db")
    return db_path, Database(db_path)


def test_rescan_keeps_ai_corrected_motor_and_active_status():
    # Regression: the AI read "Bosch CX" off a listing the parser had
    # rejected for "no motor" and restored it; the next scan re-parsed it,
    # rejected it again and — since it was already AI-analyzed — nothing
    # ever looked at it again.
    from pipeline.corrections import apply_spec_correction
    from pipeline.scoring import ScoringEngine

    db_path, db = _fresh_db()
    parser = _FakeParser()  # parser never finds the motor

    assert _process(db, parser) is False
    apply_spec_correction(db, ScoringEngine(CONFIG), "tutti_42",
                          {"motor_brand": "Bosch", "motor_torque_nm": 85}, config=CONFIG)
    assert db.get_listing_with_specs("tutti_42")["status"] == "ACTIVE"

    assert _process(db, parser) is True  # rescan

    row = db.get_listing_with_specs("tutti_42")
    assert row["status"] == "ACTIVE"
    assert row["motor_brand"] == "Bosch"
    assert row["motor_torque_nm"] == 85
    assert row["motor_verified"] == 1

    db.close()
    Path(db_path).unlink()
    print("✅ Rescan keeps AI-corrected motor test passed")


def test_rescan_rechecks_overridden_frame_size_strictly():
    # A hand-set "XL" isn't the parser's "disallowed" marker — the scan must
    # still reject it, as the correction itself did.
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)

    assert _process(db, parser) is True
    db.save_spec_overrides("tutti_42", {"frame_size": "XL"})

    assert _process(db, parser) is False
    row = db.get_listing_with_specs("tutti_42")
    assert row["status"] == "REJECTED"
    assert "XL" in row["rejection_reason"]

    db.close()
    Path(db_path).unlink()
    print("✅ Rescan re-checks overridden frame size test passed")


def test_rescan_does_not_undo_manual_reject():
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)

    assert _process(db, parser) is True
    db.set_manual_status("tutti_42", "REJECTED")
    _process(db, parser)

    assert db.get_listing_with_specs("tutti_42")["status"] == "REJECTED"

    db.close()
    Path(db_path).unlink()
    print("✅ Rescan does not undo manual reject test passed")


def test_rejected_listing_still_gets_its_parsed_specs_saved():
    # The AI pass and the restore check both need what the parser found
    # (battery, frame) for an auto-rejected listing, not NULLs.
    db_path, db = _fresh_db()

    assert _process(db, _FakeParser(battery_capacity_wh=400)) is False

    row = db.get_listing_with_specs("tutti_42")
    assert row["status"] == "REJECTED"
    assert row["battery_capacity_wh"] == 400
    assert row["frame_size"] == "M"

    db.close()
    Path(db_path).unlink()
    print("✅ Rejected listing keeps parsed specs test passed")


def _process_raw(db, parser, config, **raw_overrides):
    from pipeline.normalizer import Normalizer
    from pipeline.scoring import ScoringEngine
    return run.process_listing(_raw_listing(**raw_overrides), parser, Normalizer(), ScoringEngine(config), db, config)


RADIUS_CONFIG = {**CONFIG, "buyer_profile": {**CONFIG["buyer_profile"], "max_radius_km": {
    "italy": 150, "exempt_portals": ["ebikestorebrescia"],
}}}


def test_far_italian_listing_is_rejected_unless_the_portal_ships():
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)

    # Brescia (~110 km) is fine now: province-level distances are indicative.
    assert _process_raw(db, parser, RADIUS_CONFIG, portal="subito", portal_id="9", location_raw="Brescia (BS)") is True
    # Verona (~170 km): too far to go and see.
    assert _process_raw(db, parser, RADIUS_CONFIG, portal="subito", portal_id="10", location_raw="Bussolengo (VR)") is False
    assert "Too far" in db.get_listing_with_specs("subito_10")["rejection_reason"]
    # A shop that ships is never rejected for distance.
    assert _process_raw(db, parser, RADIUS_CONFIG, portal="ebikestorebrescia", portal_id="9",
                        location_raw="Verona") is True

    db.close()
    Path(db_path).unlink()
    print("✅ Distance filter in process_listing test passed")


def test_all_of_switzerland_is_accepted_but_weighs_on_the_score():
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)

    assert _process_raw(db, parser, RADIUS_CONFIG, portal="tutti", portal_id="1", location_raw="Lugano, Ticino") is True
    assert _process_raw(db, parser, RADIUS_CONFIG, portal="tutti", portal_id="2", location_raw="Genève, Genève") is True

    cursor = db.conn.cursor()
    cursor.execute("SELECT l.id, l.region, l.distance_km, sc.score_location_proximity FROM listings l"
                   " JOIN scores sc ON sc.listing_id = l.id")
    rows = {row["id"]: row for row in cursor.fetchall()}
    assert rows["tutti_2"]["region"] == "svizzera" and rows["tutti_2"]["distance_km"] > 200
    assert rows["tutti_2"]["score_location_proximity"] < rows["tutti_1"]["score_location_proximity"]

    db.close()
    Path(db_path).unlink()
    print("✅ Whole-Switzerland acceptance test passed")


def test_sold_out_listing_in_feed_switches_stored_listing_off():
    # Shops keep sold-out bikes in their feeds (Shopify available=false):
    # the stored listing must go SOLD, not stay ACTIVE forever.
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)

    assert _process_raw(db, parser, CONFIG) is True
    assert db.get_listing_with_specs("tutti_42")["status"] == "ACTIVE"

    assert _process_raw(db, parser, CONFIG, is_available=False) is False
    assert db.get_listing_with_specs("tutti_42")["status"] == "SOLD"

    # Sold-out and never seen before: not imported at all.
    assert _process_raw(db, parser, CONFIG, portal_id="99", is_available=False) is False
    assert db.get_listing_with_specs("tutti_99") is None

    db.close()
    Path(db_path).unlink()
    print("✅ Sold-out feed item test passed")


def test_sold_flag_from_detail_page_switches_listing_off():
    class _DetailSaysSold:
        def get_listing_details(self, listing_id, url):
            return {"description_raw": "Bosch CX", "is_available": False}

    from pipeline.normalizer import Normalizer
    from pipeline.scoring import ScoringEngine
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)
    _process_raw(db, parser, CONFIG)

    accepted = run.process_listing(_raw_listing(description_raw=""), parser, Normalizer(), ScoringEngine(CONFIG),
                                   db, CONFIG, connector=_DetailSaysSold())

    assert accepted is False
    assert db.get_listing_with_specs("tutti_42")["status"] == "SOLD"
    db.close()
    Path(db_path).unlink()
    print("✅ Sold flag from detail page test passed")


def test_deleted_listing_is_not_reimported():
    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)
    _process_raw(db, parser, CONFIG)
    db.delete_listing("tutti_42")

    assert _process_raw(db, parser, CONFIG) is False
    assert db.get_listing_with_specs("tutti_42") is None
    db.close()
    Path(db_path).unlink()
    print("✅ Deleted listing not re-imported test passed")


def test_verify_unseen_listings_marks_sold_and_keeps_inconclusive():
    from datetime import datetime, timezone

    class _FakeConnector:
        portal_name = "tutti"

        def __init__(self, verdicts):
            self.verdicts = verdicts
            self.checked = []

        def check_availability(self, listing_id, url):
            self.checked.append(listing_id)
            return self.verdicts[listing_id]

    db_path, db = _fresh_db()
    parser = _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True)
    for pid in ("1", "2", "3"):
        _process_raw(db, parser, CONFIG, portal_id=pid)
    scan_started = datetime.now(timezone.utc).isoformat()
    _process_raw(db, parser, CONFIG, portal_id="4")  # seen by this scan: never checked

    connector = _FakeConnector({"1": False, "2": True, "3": None})
    sold = run.verify_unseen_listings(db, {"tutti": connector}, CONFIG, scan_started)

    assert sold == 1
    assert sorted(connector.checked) == ["1", "2", "3"]
    statuses = {pid: db.get_listing_with_specs(f"tutti_{pid}")["status"] for pid in ("1", "2", "3", "4")}
    assert statuses == {"1": "SOLD", "2": "ACTIVE", "3": "ACTIVE", "4": "ACTIVE"}

    db.close()
    Path(db_path).unlink()
    print("✅ verify_unseen_listings test passed")


def test_process_listing_stores_dedupe_signature():
    from pipeline.dedupe import dedupe_signature
    db_path, db = _fresh_db()

    _process(db, _FakeParser(motor_brand="Bosch", motor_torque_nm=85, motor_verified=True))

    cursor = db.conn.cursor()
    cursor.execute("SELECT dedupe_signature, price_chf FROM listings WHERE id = 'tutti_42'")
    row = cursor.fetchone()
    assert row["dedupe_signature"] == dedupe_signature("Cube Stereo Hybrid", row["price_chf"])

    db.close()
    Path(db_path).unlink()
    print("✅ Dedupe signature stored test passed")


if __name__ == "__main__":
    test_generate_user_analysis_is_italian_not_english()
    test_generate_user_analysis_verdict_tiers()
    test_generate_user_analysis_does_not_duplicate_the_spec_grid()
    test_generate_user_analysis_includes_red_flags()
    test_rescan_keeps_ai_corrected_motor_and_active_status()
    test_rescan_rechecks_overridden_frame_size_strictly()
    test_rescan_does_not_undo_manual_reject()
    test_rejected_listing_still_gets_its_parsed_specs_saved()
    test_far_italian_listing_is_rejected_unless_the_portal_ships()
    test_all_of_switzerland_is_accepted_but_weighs_on_the_score()
    test_sold_out_listing_in_feed_switches_stored_listing_off()
    test_sold_flag_from_detail_page_switches_listing_off()
    test_deleted_listing_is_not_reimported()
    test_verify_unseen_listings_marks_sold_and_keeps_inconclusive()
    test_process_listing_stores_dedupe_signature()
    print("\n✅ All run.py tests passed!")
