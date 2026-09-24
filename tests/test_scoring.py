import sys
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
    test_location_scoring()
    test_fit_scoring()
    test_full_score_calculation()
    test_config_missing_key_raises()
    print("\n✅ All scoring tests passed!")
