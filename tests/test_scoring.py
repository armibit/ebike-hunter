import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline.scoring import ScoringEngine


def test_price_scoring():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000}
        },
        "scoring_weights": {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        }
    }
    engine = ScoringEngine(config)

    # Test excellent price
    assert engine._score_price(1500) == 100.0

    # Test target price
    score_2200 = engine._score_price(2200)
    assert 30 <= score_2200 <= 70

    # Test max price
    score_3000 = engine._score_price(3000)
    assert score_3000 < 10

    # Test over budget
    assert engine._score_price(3500) == 0.0

    # Test invalid price (0 or negative = failed price parse, never a real
    # deal — must score 0, not fall into the "<= 1800 = 100" bucket)
    assert engine._score_price(0) == 0.0
    assert engine._score_price(-50) == 0.0

    print("✅ Price scoring tests passed")


def test_component_scoring():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000}
        },
        "scoring_weights": {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        }
    }
    engine = ScoringEngine(config)

    # Top spec bike
    specs_top = {
        "battery_capacity_wh": 750,
        "motor_torque_nm": 90,
        "brakes_tier": "four_piston",
        "fork_tier": "high"
    }
    score_top = engine._score_components(specs_top)
    assert score_top >= 95

    # Mid spec bike
    specs_mid = {
        "battery_capacity_wh": 625,
        "motor_torque_nm": 85,
        "brakes_tier": "two_piston",
        "fork_tier": "mid"
    }
    score_mid = engine._score_components(specs_mid)
    assert 60 <= score_mid <= 85

    print("✅ Component scoring tests passed")


def test_component_scoring_unverified_motor_gets_flat_low_credit():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000}
        },
        "scoring_weights": {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        }
    }
    engine = ScoringEngine(config)

    # RegexParser's e-bike-keyword fallback sets motor_torque_nm=60 as a
    # placeholder with motor_verified=False — it must not score as if it
    # were a confirmed 60Nm motor (15pts), only a flat, low credit (8pts),
    # so an unverified listing never outranks one with the same specs but
    # a genuinely identified motor.
    specs_unverified = {
        "battery_capacity_wh": 625,
        "motor_torque_nm": 60,
        "motor_verified": False,
        "brakes_tier": "two_piston",
        "fork_tier": "mid"
    }
    specs_confirmed = {
        "battery_capacity_wh": 625,
        "motor_torque_nm": 60,
        "motor_verified": True,
        "brakes_tier": "two_piston",
        "fork_tier": "mid"
    }
    score_unverified = engine._score_components(specs_unverified)
    score_confirmed = engine._score_components(specs_confirmed)

    assert score_unverified < score_confirmed
    assert score_confirmed - score_unverified == 7  # 15pts tier credit vs flat 8pts

    # Specs read back from SQLite carry 0/1 instead of False/True — the
    # penalty must hold for those too; None (never set) is not "unverified".
    assert engine._score_components({**specs_unverified, "motor_verified": 0}) == score_unverified
    assert engine._score_components({**specs_unverified, "motor_verified": 1}) == score_confirmed
    assert engine._score_components({**specs_unverified, "motor_verified": None}) == score_confirmed

    print("✅ Unverified motor scoring test passed")


def test_location_scoring():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000}
        },
        "scoring_weights": {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        }
    }
    engine = ScoringEngine(config)

    # Very close (Lugano area)
    assert engine._score_location(10) == 100.0

    # Border area (Como/Varese)
    assert engine._score_location(35) == 85.0

    # Lombardia
    assert engine._score_location(75) == 60.0

    # Far
    assert engine._score_location(150) == 20.0

    print("✅ Location scoring tests passed")


def test_fit_scoring():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000}
        },
        "scoring_weights": {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        }
    }
    engine = ScoringEngine(config)

    # Perfect fit
    specs_perfect = {"frame_size": "M", "travel_front_mm": 145}
    score_perfect = engine._score_fit(specs_perfect)
    assert score_perfect == 100.0

    # S2 with good travel
    specs_s2 = {"frame_size": "S2", "travel_front_mm": 150}
    score_s2 = engine._score_fit(specs_s2)
    assert score_s2 >= 95

    # Wrong size
    specs_wrong = {"frame_size": "XL", "travel_front_mm": 140}
    score_wrong = engine._score_fit(specs_wrong)
    assert score_wrong < 50

    # A hand-typed correction ("m", " s2 ") counts like the parser's "M".
    assert engine._score_fit({"frame_size": "m", "travel_front_mm": 145}) == 100.0
    assert engine._score_fit({"frame_size": " s2 ", "travel_front_mm": 145}) == 100.0
    # A stored NULL frame size is unknown (neutral), not wrong.
    assert engine._score_fit({"frame_size": None}) == engine._score_fit({"frame_size": "unknown"})

    # Rear travel (travel_rear_range) counts too when the listing states it:
    # ideal front + far-out-of-range rear averages the two travel scores.
    assert engine._score_fit({"frame_size": "M", "travel_front_mm": 145, "travel_rear_mm": 145}) == 100.0
    assert engine._score_fit({"frame_size": "M", "travel_front_mm": 145, "travel_rear_mm": 100}) == 90.0

    print("✅ Fit scoring tests passed")


def test_full_score_calculation():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000}
        },
        "scoring_weights": {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        }
    }
    engine = ScoringEngine(config)

    # Dream deal
    listing_dream = {"price_chf": 1900, "distance_km": 15}
    specs_dream = {
        "battery_capacity_wh": 750,
        "motor_torque_nm": 90,
        "brakes_tier": "four_piston",
        "fork_tier": "high",
        "odometer_km": 300,
        "frame_size": "M",
        "travel_front_mm": 145
    }
    result_dream = engine.calculate_score(listing_dream, specs_dream)
    assert result_dream["score_total"] >= 85
    assert result_dream["is_deal_target"] is True

    # Mediocre deal
    listing_med = {"price_chf": 2800, "distance_km": 80}
    specs_med = {
        "battery_capacity_wh": 625,
        "motor_torque_nm": 85,
        "brakes_tier": "two_piston",
        "fork_tier": "mid",
        "odometer_km": 3000,
        "frame_size": "M",
        "travel_front_mm": 140
    }
    result_med = engine.calculate_score(listing_med, specs_med)
    assert 40 <= result_med["score_total"] <= 70
    assert result_med["is_deal_target"] is False

    print("✅ Full score calculation tests passed")


def test_price_and_size_thresholds_come_from_config():
    config = {
        "buyer_profile": {
            "budget": {"target_price": 2200, "hard_max_price": 3000, "full_score_price": 2000},
            "rider_specs": {"target_sizes": ["M", "44cm", "17 inch"]},
        },
        "scoring_weights": {"price_value": 0.35, "component_quality": 0.25, "condition_mileage": 0.15,
                            "location_proximity": 0.15, "fit_geometry": 0.10},
    }
    engine = ScoringEngine(config)

    assert engine._score_price(1950) == 100.0      # under the configured 2000, not the old fixed 1800
    assert engine._score_price(2100) < 100.0
    # A hand-corrected "44cm" is a target size here, so it's a fit, not a miss.
    assert engine._score_fit({"frame_size": "44cm"}) == engine._score_fit({"frame_size": "M"})
    assert engine._score_fit({"frame_size": "17inch"}) == engine._score_fit({"frame_size": "M"})
    assert engine._score_fit({"frame_size": "XL"}) < engine._score_fit({"frame_size": "M"})

    # Default stays 1800 when the config doesn't say.
    default = ScoringEngine({"buyer_profile": {"budget": {"target_price": 2200, "hard_max_price": 3000}},
                             "scoring_weights": config["scoring_weights"]})
    assert default._score_price(1800) == 100.0 and default._score_price(1850) < 100.0
    print("✅ Config-driven thresholds test passed")


def test_config_missing_key_raises():
    import pytest
    bad_config = {"buyer_profile": {}}
    try:
        ScoringEngine(bad_config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "budget" in str(e).lower() or "missing" in str(e).lower()
    print("✅ Config missing key test passed")


if __name__ == "__main__":
    test_price_scoring()
    test_component_scoring()
    test_component_scoring_unverified_motor_gets_flat_low_credit()
    test_location_scoring()
    test_fit_scoring()
    test_full_score_calculation()
    test_price_and_size_thresholds_come_from_config()
    test_config_missing_key_raises()
    print("\n✅ All scoring tests passed!")


def test_age_penalty():
    assert ScoringEngine._age_penalty(None) == 0
    assert ScoringEngine._age_penalty(date.today().year - 3) == 0
    assert ScoringEngine._age_penalty(date.today().year - 5) == 6
    assert ScoringEngine._age_penalty(2010) == 20
