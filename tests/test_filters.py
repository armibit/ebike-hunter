import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connectors.base import MAX_RETRY_AFTER_SECONDS, _retry_after_seconds
from pipeline.filters import distance_reject_reason, hard_filter_reasons, is_correctable_rejection, spec_problems

CONFIG = {
    "buyer_profile": {"budget": {"target_price": 2200, "hard_max_price": 3000}},
    "hardware_requirements": {"min_motor_torque_nm": 60, "min_battery_wh": 500},
}

GOOD_SPECS = {
    "suspension_type": "full_suspension", "motor_torque_nm": 85, "battery_capacity_wh": 625,
    "frame_size": "M", "has_red_flag": False, "red_flag_details": [],
}


def test_good_listing_passes():
    assert hard_filter_reasons(2000, GOOD_SPECS, CONFIG) == []
    print("✅ Hard filters: good listing passes")


def test_each_hard_filter_fires():
    cases = [
        (0, {}, "Invalid price"),
        (3500, {}, "Over budget"),
        (500, {}, "Suspicious price"),
        (2000, {"suspension_type": "hardtail"}, "Hardtail"),
        (2000, {"excluded_category": "fat bike"}, "Wrong category (fat bike)"),
        (2000, {"motor_torque_nm": None}, "No motor detected"),
        (2000, {"motor_torque_nm": 50}, "Weak motor (50nm < 60nm)"),
        (2000, {"battery_capacity_wh": 400.0}, "Small battery (400Wh < 500Wh)"),
        (2000, {"frame_size": "disallowed"}, "Wrong size"),
        (2000, {"has_red_flag": True, "red_flag_details": ["senza caricatore"]}, "Red flags: senza caricatore"),
    ]
    for price, spec_changes, expected in cases:
        reasons = hard_filter_reasons(price, {**GOOD_SPECS, **spec_changes}, CONFIG)
        assert any(expected in r for r in reasons), f"{expected!r} not in {reasons!r}"
    print("✅ Hard filters: every filter fires")


def test_unknown_values_are_allowed():
    # Unknown suspension, frame size or battery are not reasons to reject.
    specs = {**GOOD_SPECS, "suspension_type": "unknown", "frame_size": "unknown", "battery_capacity_wh": None}
    assert hard_filter_reasons(2000, specs, CONFIG) == []
    print("✅ Hard filters: unknown values allowed")


RADIUS_CONFIG = {"buyer_profile": {"max_radius_km": {
    "italy": 150, "exempt_portals": ["ebikestorebrescia"],
}}}


def test_distance_filter_rejects_only_far_italian_listings():
    assert distance_reject_reason("subito", 45.5, 110, "IT", RADIUS_CONFIG) is None
    assert distance_reject_reason("subito", 41.9, 520, "IT", RADIUS_CONFIG) == "Too far (520 km > 150 km)"
    # All of Switzerland is accepted, however far — distance only weighs on the score.
    assert distance_reject_reason("tutti", 46.2, 250, "CH", RADIUS_CONFIG) is None
    print("✅ Distance filter: Italy radius, Switzerland always accepted")


def test_distance_filter_reads_legacy_lombardia_setting():
    legacy = {"buyer_profile": {"max_radius_km": {"ticino": 45, "lombardia": 105}}}
    assert distance_reject_reason("subito", 45.5, 110, "IT", legacy) == "Too far (110 km > 105 km)"
    print("✅ Distance filter: legacy config key")


def test_distance_filter_skips_unknown_location_and_shipping_shops():
    # Unknown location gets a neutral placeholder distance, not a real one.
    assert distance_reject_reason("subito", None, 150, "IT", RADIUS_CONFIG) is None
    # A shop that ships is never rejected for distance.
    assert distance_reject_reason("ebikestorebrescia", 41.9, 520, "IT", RADIUS_CONFIG) is None
    # No radius configured at all: no filter.
    assert distance_reject_reason("subito", 41.9, 520, "IT", {}) is None
    print("✅ Distance filter: unknown location / exempt portals")


def test_wrong_size_reason_names_the_size_found():
    reasons = hard_filter_reasons(2000, {**GOOD_SPECS, "frame_size": "disallowed", "frame_size_detected": "XL"}, CONFIG)
    assert "Wrong size (XL — outside target sizes)" in reasons
    print("✅ Wrong-size reason names the size")


def test_spec_problems():
    complete = {"status": "ACTIVE", "motor_torque_nm": 85, "motor_verified": 1,
                "battery_capacity_wh": 625, "frame_size": "M"}
    assert spec_problems(complete) == []
    assert spec_problems({**complete, "motor_verified": 0}) == ["motore da verificare"]
    assert spec_problems({**complete, "motor_torque_nm": None, "battery_capacity_wh": None, "frame_size": "unknown"}) == [
        "motore mancante", "batteria mancante", "taglia mancante",
    ]
    assert spec_problems({"status": "REJECTED", "rejection_reason": "No motor detected (likely not an e-bike)"})
    assert spec_problems({"status": "REJECTED", "rejection_reason": "Over budget (3500 > 3000 CHF)"}) == []
    print("✅ spec_problems")


def test_correctable_rejections():
    assert is_correctable_rejection("No motor detected (likely not an e-bike)")
    assert is_correctable_rejection("Weak motor (50nm < 60nm); Small battery (400Wh < 500Wh)")
    assert is_correctable_rejection("Taglia esclusa dopo correzione manuale (XL non tra le taglie target)")
    # One uncorrectable part is enough to make the whole rejection final.
    assert not is_correctable_rejection("No motor detected (likely not an e-bike); Over budget (3500 > 3000 CHF)")
    assert not is_correctable_rejection("Hardtail (need full suspension)")
    assert not is_correctable_rejection("Too far (130 km > 105 km)")
    assert not is_correctable_rejection("Red flags: senza caricatore")
    assert not is_correctable_rejection("Wrong category (fat bike)")
    assert not is_correctable_rejection(None)
    print("✅ Correctable-rejection classification")


def test_retry_after_parsing():
    assert _retry_after_seconds(None) == 60
    assert _retry_after_seconds("") == 60
    assert _retry_after_seconds("30") == 30
    assert _retry_after_seconds("not a date") == 60
    # HTTP-date form used to crash int() and abort the whole portal scan.
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)
    assert 100 <= _retry_after_seconds(future) <= 120
    past = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=120), usegmt=True)
    assert _retry_after_seconds(past) == 0
    # Capped so one portal can't park its thread for hours.
    assert _retry_after_seconds("86400") == MAX_RETRY_AFTER_SECONDS
    print("✅ Retry-After parsing test passed")


if __name__ == "__main__":
    test_good_listing_passes()
    test_each_hard_filter_fires()
    test_unknown_values_are_allowed()
    test_distance_filter_rejects_only_far_italian_listings()
    test_distance_filter_reads_legacy_lombardia_setting()
    test_distance_filter_skips_unknown_location_and_shipping_shops()
    test_wrong_size_reason_names_the_size_found()
    test_spec_problems()
    test_correctable_rejections()
    test_retry_after_parsing()
    print("\n✅ All filter tests passed!")
