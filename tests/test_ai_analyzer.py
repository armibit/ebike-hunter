import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline.ai_analyzer import AIAnalyzer, MAX_BATCH_SIZE, DEFAULT_MODEL

BUYER_PROFILE = {
    "location": {"name": "Lugano, Ticino"},
    "budget": {"target_price": 2200, "hard_max_price": 3000},
    "rider_specs": {"height_cm": 170, "target_sizes": ["M", "S2", "S3"]},
}


def _listing(listing_id="tutti_1", **overrides):
    base = {
        "id": listing_id,
        "title": "Specialized Turbo Levo Comp",
        "description_raw": "Ottime condizioni, piccolo graffio sul tubo anteriore.",
        "price_chf": 2100,
        "distance_km": 5.0,
        "brand": "Specialized",
        "model": "Turbo Levo Comp",
        "motor_brand": "Brose",
        "motor_model": "Specialized 2.2",
        "motor_torque_nm": 90,
        "battery_capacity_wh": 700,
        "frame_size": "M",
        "suspension_type": "full_suspension",
        "travel_front_mm": 150,
        "brakes_tier": "four_piston",
        "odometer_km": 800,
        "score_total": 82.5,
    }
    base.update(overrides)
    return base


def _tool_use_response(results):
    block = SimpleNamespace(type="tool_use", name="submit_analysis", input={"results": results})
    return SimpleNamespace(content=[block])


def test_analyze_batch_empty_input_skips_api_call():
    client = MagicMock()
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([])

    assert results == []
    client.messages.create.assert_not_called()


def test_analyze_batch_too_large_raises():
    client = MagicMock()
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)
    listings = [_listing(f"tutti_{i}") for i in range(MAX_BATCH_SIZE + 1)]

    try:
        analyzer.analyze_batch(listings)
        assert False, "expected ValueError for oversized batch"
    except ValueError:
        pass
    client.messages.create.assert_not_called()


def test_analyze_batch_happy_path_parses_results():
    prev = os.environ.pop("ANTHROPIC_MODEL", None)
    try:
        client = MagicMock()
        client.messages.create.return_value = _tool_use_response([
            {"listing_id": "tutti_1", "ai_analysis": "Good condition, minor cosmetic scratch noted.", "ai_score": 78.0},
        ])
        analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

        results = analyzer.analyze_batch([_listing("tutti_1")])

        assert results == [{
            "listing_id": "tutti_1",
            "ai_analysis": "Good condition, minor cosmetic scratch noted.",
            "ai_score": 78.0,
            "corrected_specs": {},
        }]

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == DEFAULT_MODEL
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "submit_analysis"}
        assert call_kwargs["tools"][0]["name"] == "submit_analysis"
        prompt = call_kwargs["messages"][0]["content"]
        assert "tutti_1" in prompt
        assert "graffio" in prompt  # raw description text must reach the prompt verbatim
        assert "Lugano" in prompt  # buyer profile context included
    finally:
        if prev is not None:
            os.environ["ANTHROPIC_MODEL"] = prev
    print("✅ AI analyze_batch happy path test passed")


def test_analyze_batch_respects_anthropic_model_env_override():
    prev = os.environ.get("ANTHROPIC_MODEL")
    os.environ["ANTHROPIC_MODEL"] = "local-llama-70b"
    try:
        client = MagicMock()
        client.messages.create.return_value = _tool_use_response([
            {"listing_id": "tutti_1", "ai_analysis": "Fine.", "ai_score": 70.0},
        ])
        analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

        analyzer.analyze_batch([_listing("tutti_1")])

        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "local-llama-70b"
    finally:
        if prev is None:
            os.environ.pop("ANTHROPIC_MODEL", None)
        else:
            os.environ["ANTHROPIC_MODEL"] = prev
    print("✅ AI analyze_batch ANTHROPIC_MODEL override test passed")


def test_analyze_batch_api_error_returns_empty_list():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("connection reset")
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results == []
    print("✅ AI analyze_batch API-error handling test passed")


def test_parse_response_skips_unknown_listing_id():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {"listing_id": "tutti_1", "ai_analysis": "Fine.", "ai_score": 70},
        {"listing_id": "hallucinated_999", "ai_analysis": "Should be dropped.", "ai_score": 99},
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert len(results) == 1
    assert results[0]["listing_id"] == "tutti_1"
    print("✅ AI parse_response unknown-id filtering test passed")


def test_parse_response_skips_incomplete_result():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {"listing_id": "tutti_1", "ai_analysis": "", "ai_score": 70},
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results == []
    print("✅ AI parse_response incomplete-result filtering test passed")


def test_parse_response_clamps_out_of_range_score():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {"listing_id": "tutti_1", "ai_analysis": "Excellent.", "ai_score": 150},
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results[0]["ai_score"] == 100.0
    print("✅ AI parse_response score-clamping test passed")


def test_parse_response_skips_non_numeric_score():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {"listing_id": "tutti_1", "ai_analysis": "Fine.", "ai_score": "not-a-number"},
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results == []
    print("✅ AI parse_response non-numeric-score filtering test passed")


def test_parse_response_keeps_well_typed_corrected_specs():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {
            "listing_id": "tutti_1",
            "ai_analysis": "Text names the motor explicitly.",
            "ai_score": 80,
            "corrected_specs": {
                "motor_brand": "Bosch",
                "motor_torque_nm": 85,
                "frame_size": "L",
            },
        },
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results[0]["corrected_specs"] == {
        "motor_brand": "Bosch",
        "motor_torque_nm": 85.0,
        "frame_size": "L",
    }
    print("✅ AI corrected_specs happy-path test passed")


def test_parse_response_drops_malformed_corrected_specs_fields():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {
            "listing_id": "tutti_1",
            "ai_analysis": "Fine.",
            "ai_score": 70,
            "corrected_specs": {
                "motor_torque_nm": "eighty-five",  # wrong type — must be dropped, not crash
                "motor_brand": "",  # blank — must be dropped
                "frame_size": "M",  # valid — must survive
                "unknown_field": "should be ignored",
            },
        },
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results[0]["corrected_specs"] == {"frame_size": "M"}
    print("✅ AI corrected_specs malformed-field filtering test passed")


def test_parse_response_missing_corrected_specs_defaults_to_empty():
    client = MagicMock()
    client.messages.create.return_value = _tool_use_response([
        {"listing_id": "tutti_1", "ai_analysis": "Fine.", "ai_score": 70},
    ])
    analyzer = AIAnalyzer(BUYER_PROFILE, client=client)

    results = analyzer.analyze_batch([_listing("tutti_1")])

    assert results[0]["corrected_specs"] == {}
    print("✅ AI corrected_specs default-empty test passed")


def test_build_prompt_includes_all_listings():
    analyzer = AIAnalyzer(BUYER_PROFILE, client=MagicMock())
    listings = [_listing("tutti_1"), _listing("subito_2", title="Trek Rail 9.7")]

    prompt = analyzer._build_prompt(listings)

    assert "tutti_1" in prompt
    assert "subito_2" in prompt
    assert "Trek Rail 9.7" in prompt
    print("✅ AI build_prompt multi-listing test passed")


if __name__ == "__main__":
    test_analyze_batch_empty_input_skips_api_call()
    test_analyze_batch_too_large_raises()
    test_analyze_batch_happy_path_parses_results()
    test_analyze_batch_respects_anthropic_model_env_override()
    test_analyze_batch_api_error_returns_empty_list()
    test_parse_response_skips_unknown_listing_id()
    test_parse_response_skips_incomplete_result()
    test_parse_response_clamps_out_of_range_score()
    test_parse_response_skips_non_numeric_score()
    test_parse_response_keeps_well_typed_corrected_specs()
    test_parse_response_drops_malformed_corrected_specs_fields()
    test_parse_response_missing_corrected_specs_defaults_to_empty()
    test_build_prompt_includes_all_listings()
    print("\n✅ All AI analyzer tests passed!")
