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


if __name__ == "__main__":
    test_generate_user_analysis_is_italian_not_english()
    test_generate_user_analysis_verdict_tiers()
    test_generate_user_analysis_does_not_duplicate_the_spec_grid()
    test_generate_user_analysis_includes_red_flags()
    print("\n✅ All run.py tests passed!")
