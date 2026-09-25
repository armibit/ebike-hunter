import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_dashboard import _format_price, _format_date, _format_history, _build_modal_text


def test_format_price_shows_original_currency_not_converted():
    # CHF listing: no conversion hint needed, it's already the "home" currency.
    assert _format_price({"price_raw": 2100.0, "currency": "CHF", "price_chf": 2100.0}) == "2100 CHF"

    # EUR listing: must show the original EUR amount as the primary value,
    # not the silently-converted CHF figure — with a small CHF hint since
    # the budget filters are CHF-based.
    text = _format_price({"price_raw": 2400.0, "currency": "EUR", "price_chf": 2280.0})
    assert text.startswith("2400 EUR")
    assert "2280 CHF" in text

    print("✅ Price display (original currency) test passed")


def test_format_price_falls_back_without_raw_price():
    assert _format_price({"price_raw": None, "currency": None, "price_chf": 1900.0}) == "1900 CHF"
    assert _format_price({"price_raw": None, "currency": None, "price_chf": None}) == "N/A"
    print("✅ Price display fallback test passed")


def test_format_date_parses_iso_timestamp():
    assert _format_date("2026-09-25T14:58:10.040123+00:00") == "25/09/2026"
    assert _format_date(None) == "N/A"
    # Malformed input degrades gracefully instead of raising.
    assert _format_date("not-a-date") == "not-a-date"
    print("✅ Date formatting test passed")


def test_format_history_requires_at_least_two_snapshots():
    single = [{"price_raw": 2400.0, "currency": "EUR", "captured_at": "2026-09-10T00:00:00+00:00"}]
    assert _format_history(single) == "", "a single snapshot isn't a 'history' yet"

    two = single + [{"price_raw": 2200.0, "currency": "EUR", "captured_at": "2026-09-20T00:00:00+00:00"}]
    text = _format_history(two)
    assert "2400 EUR" in text and "2200 EUR" in text
    assert text.index("2400 EUR") < text.index("2200 EUR"), "history must read oldest to newest"
    print("✅ Price history formatting test passed")


def test_build_modal_text_includes_metadata_and_history():
    bike = {
        "first_seen_at": "2026-09-10T00:00:00+00:00",
        "model_year": 2022,
        "odometer_km": 1200.0,
        "user_analysis": "Buon affare.",
    }
    history = [
        {"price_raw": 2400.0, "currency": "EUR", "captured_at": "2026-09-10T00:00:00+00:00"},
        {"price_raw": 2200.0, "currency": "EUR", "captured_at": "2026-09-20T00:00:00+00:00"},
    ]
    text = _build_modal_text(bike, history)
    assert "2022" in text
    assert "1200 km" in text
    assert "Storico prezzo" in text
    assert "Buon affare." in text
    print("✅ Modal text assembly test passed")


if __name__ == "__main__":
    test_format_price_shows_original_currency_not_converted()
    test_format_price_falls_back_without_raw_price()
    test_format_date_parses_iso_timestamp()
    test_format_history_requires_at_least_two_snapshots()
    test_build_modal_text_includes_metadata_and_history()
    print("\n✅ All generate_dashboard tests passed!")
