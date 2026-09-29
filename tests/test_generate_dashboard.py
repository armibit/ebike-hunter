import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_dashboard import (
    _format_price,
    _format_date,
    _build_price_history_html,
    _build_spec_table_html,
    _build_score_breakdown_html,
    _build_red_flags_html,
    _build_detail_html,
    _render_text_block,
    render_dashboard_html,
)


def test_format_price_shows_original_currency_not_converted():
    # CHF listing: no conversion hint needed, it's already the "home" currency.
    assert _format_price({"price_raw": 2100.0, "currency": "CHF", "price_chf": 2100.0}) == "2100 CHF"

    # EUR listing: shown exactly as posted, with no converted CHF figure —
    # the "~CHF" hint was dropped on purpose in 879a60e ("without
    # conversions"); scoring/filtering still use price_chf internally.
    text = _format_price({"price_raw": 2400.0, "currency": "EUR", "price_chf": 2280.0})
    assert text == "2400 EUR"

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


def test_price_history_html_requires_at_least_two_snapshots():
    single = [{"price_raw": 2400.0, "currency": "EUR", "captured_at": "2026-09-10T00:00:00+00:00"}]
    assert _build_price_history_html(single) == "", "a single snapshot isn't a 'history' yet"

    two = single + [{"price_raw": 2200.0, "currency": "EUR", "captured_at": "2026-09-20T00:00:00+00:00"}]
    html = _build_price_history_html(two)
    assert "2400 EUR" in html and "2200 EUR" in html
    assert html.index("2400 EUR") < html.index("2200 EUR"), "history must read oldest to newest"
    assert "price-chip" in html
    print("✅ Price history HTML test passed")


def test_render_text_block_converts_bold_and_bullets_to_real_html():
    # The exact bug reported: literal "\n" characters showing up as text in
    # the modal instead of real line breaks/paragraphs/lists.
    text = "**RECOMMENDATION**\n\n• Motor: Bosch 85Nm — great\n• Battery: unknown\n\nFinal note."
    html = _render_text_block(text)

    assert "\\n" not in html, "must never leak a literal backslash-n into the rendered HTML"
    assert "<strong>RECOMMENDATION</strong>" in html
    assert "<li>Motor: Bosch 85Nm — great</li>" in html
    assert "<li>Battery: unknown</li>" in html
    assert "<p>Final note.</p>" in html
    print("✅ Text block markdown-lite rendering test passed")


def test_render_text_block_escapes_html_in_seller_text():
    # Seller-provided text is untrusted — must not inject markup.
    html = _render_text_block("Prezzo <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    print("✅ Text block HTML-escaping test passed")


def test_build_spec_table_marks_unverified_motor():
    verified = _build_spec_table_html({"motor_brand": "Bosch", "motor_torque_nm": 85, "motor_verified": True})
    assert "badge-ok" in verified and "verificato" in verified

    unverified = _build_spec_table_html({"motor_brand": "Unknown Motor", "motor_torque_nm": 60, "motor_verified": 0})
    assert "badge-warn" in unverified and "da verificare" in unverified
    print("✅ Spec table motor-verified badge test passed")


def test_build_score_breakdown_renders_all_subscores():
    html = _build_score_breakdown_html({
        "score_total": 75.4,
        "score_price_value": 80,
        "score_component_quality": 70,
        "score_condition_mileage": 60,
        "score_location_proximity": 90,
        "score_fit_geometry": 65,
    })
    assert "75/100" in html
    for label in ("Prezzo", "Componenti", "Condizione / Km", "Posizione", "Taglia / Escursione"):
        assert label in html
    print("✅ Score breakdown test passed")


def test_build_red_flags_html_only_when_flagged():
    assert _build_red_flags_html({"has_red_flag": False}) == ""
    assert _build_red_flags_html({"has_red_flag": True, "red_flag_details": None}) == ""

    import json
    html = _build_red_flags_html({"has_red_flag": True, "red_flag_details": json.dumps(["senza caricatore"])})
    assert "senza caricatore" in html
    print("✅ Red flags HTML test passed")


def test_build_detail_html_includes_metadata_history_and_ai_verdict():
    bike = {
        "first_seen_at": "2026-09-10T00:00:00+00:00",
        "model_year": 2022,
        "odometer_km": 1200.0,
        "price_raw": 2400.0,
        "currency": "EUR",
        "price_chf": 2280.0,
        "user_analysis": "Buon affare.",
        "ai_analysis": "Ottimo prezzo per le specifiche.",
        "ai_score": 82.0,
        "score_total": 75.0,
    }
    history = [
        {"price_raw": 2400.0, "currency": "EUR", "captured_at": "2026-09-10T00:00:00+00:00"},
        {"price_raw": 2200.0, "currency": "EUR", "captured_at": "2026-09-20T00:00:00+00:00"},
    ]
    html = _build_detail_html(bike, history)

    assert "\\n" not in html
    assert "2022" in html
    assert "1200 km" in html
    assert "Storico prezzo" in html
    assert "Buon affare." in html
    assert "Ottimo prezzo per le specifiche." in html
    assert "82/100" in html
    print("✅ Detail HTML assembly test passed")


def test_render_dashboard_html_no_literal_backslash_n_end_to_end():
    """Regression test for the reported bug: opening a listing's modal
    showed literal '\\n' text instead of line breaks. Renders a full page
    against a real temp DB and checks the per-listing <template> content."""
    import tempfile, os, re
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from db.database import Database

    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    db.upsert_listing({
        "portal": "x", "portal_id": "1", "url": "https://example.com/1", "title": "Test Bike",
        "price_raw": 2000, "currency": "CHF", "price_chf": 2000, "price_eur": 1900,
        "distance_km": 10, "status": "ACTIVE",
    })
    db.save_user_analysis("x_1", "**Verdict**\n\n• Point one\n• Point two\n\nClosing line.")
    db.close()

    html = render_dashboard_html(tmp, interactive=True)
    os.remove(tmp)

    match = re.search(r'<template data-listing-id="x_1">.*?</template>', html, re.S)
    assert match, "expected a per-listing <template> block"
    assert "\\n" not in match.group(0)
    assert "<strong>Verdict</strong>" in match.group(0)
    print("✅ End-to-end no-literal-backslash-n test passed")


def test_render_dashboard_order_and_badge_follow_ranking_score():
    """Regressions: a rejected favorite stayed on top (looked like 'Scarta'
    did nothing), and the badge showed score_total while the list sorted by
    the AI-blended ranking_score (88.4 above 89.5). Also inline/modal spec
    edits must reload so the new score shows."""
    import tempfile, os, re
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from db.database import Database

    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    scores = {"a": (89.5, None), "b": (88.0, 95.0), "c": (95.0, None)}
    for pid, (total, ai) in scores.items():
        db.upsert_listing({
            "portal": "x", "portal_id": pid, "url": f"https://example.com/{pid}", "title": f"Bike {pid}",
            "price_raw": 2000, "currency": "CHF", "price_chf": 2000, "price_eur": 1900,
            "distance_km": 10, "status": "ACTIVE",
        })
        db.save_score(f"x_{pid}", {
            "score_total": total, "score_price_value": 0, "score_component_quality": 0,
            "score_condition_mileage": 0, "score_location_proximity": 0, "score_fit_geometry": 0,
        })
        if ai is not None:
            db.save_ai_analysis(f"x_{pid}", "ok", ai)
    db.toggle_favorite("x_c")
    db.set_manual_status("x_c", "REJECTED")
    db.close()

    html = render_dashboard_html(tmp, interactive=True)
    os.remove(tmp)

    tbody = html[html.index('<tbody id="tbody">'):]
    rows = re.findall(r'<tr[^>]*data-id="(x_\w)"[^>]*data-score="([\d.]+)"', tbody)
    assert [r[0] for r in rows] == ["x_b", "x_a", "x_c"]  # b: .6*88+.4*95=90.8
    assert dict(rows)["x_b"] == str(0.6 * 88.0 + 0.4 * 95.0)
    assert "AI 95 (60/40)" in tbody
    assert "if (specsChanged) location.reload()" in html
    # "Marca" checkbox filter: no brand parsed -> "Altro".
    assert 'class="brand-cb" value="Altro"> Altro (3)' in html
    assert 'data-brand="Altro"' in tbody
    # Brands sit in a collapsible list with select/deselect all.
    assert '<details class="brand-dropdown">' in html
    assert "setAllBrands(true)" in html and "setAllBrands(false)" in html


def test_render_dashboard_thumbnail_and_image_kept_on_rescan():
    """List thumbnails: image_url from the connector is stored, survives a
    rescan whose card had no image (COALESCE), and non-http URLs never render."""
    import tempfile, os
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from db.database import Database
    from bs4 import BeautifulSoup
    from connectors.base import card_image

    card = BeautifulSoup('<div><img src="/icons/info.svg"><img class="lazy" src="https://ik.imagekit.io/q-10,bl-90/a.jpg" '
                         'data-src="https://ik.imagekit.io/q-80/a.jpg"></div>', "html.parser")
    assert card_image(card, "ik.imagekit.io") == "https://ik.imagekit.io/q-80/a.jpg"
    assert card_image(card, "img.velocorner.ch") is None

    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    base = {"portal": "x", "url": "https://example.com/", "title": "Bike", "price_raw": 2000, "currency": "CHF",
            "price_chf": 2000, "price_eur": 1900, "distance_km": 10, "status": "ACTIVE"}
    db.upsert_listing({**base, "portal_id": "a", "image_url": "https://cdn.example.com/a.jpg"})
    db.upsert_listing({**base, "portal_id": "a"})  # rescan, card without image
    db.upsert_listing({**base, "portal_id": "b", "title": "Other", "image_url": "javascript:alert(1)"})
    db.close()

    html = render_dashboard_html(tmp, interactive=True)
    os.remove(tmp)
    assert '<img class="thumb" src="https://cdn.example.com/a.jpg"' in html
    assert "javascript:alert" not in html
    assert html.count('<img class="thumb"') == 1
    # No image (or unsafe one) -> placeholder, so rows stay aligned
    assert html.count('class="thumb none"') == 1


if __name__ == "__main__":
    test_format_price_shows_original_currency_not_converted()
    test_format_price_falls_back_without_raw_price()
    test_format_date_parses_iso_timestamp()
    test_price_history_html_requires_at_least_two_snapshots()
    test_render_text_block_converts_bold_and_bullets_to_real_html()
    test_render_text_block_escapes_html_in_seller_text()
    test_build_spec_table_marks_unverified_motor()
    test_build_score_breakdown_renders_all_subscores()
    test_build_red_flags_html_only_when_flagged()
    test_build_detail_html_includes_metadata_history_and_ai_verdict()
    test_render_dashboard_html_no_literal_backslash_n_end_to_end()
    test_render_dashboard_order_and_badge_follow_ranking_score()
    test_render_dashboard_thumbnail_and_image_kept_on_rescan()
    print("\n✅ All generate_dashboard tests passed!")
