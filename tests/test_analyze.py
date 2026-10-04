import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import analyze


def _parse(*argv):
    saved = sys.argv
    sys.argv = ["analyze.py", *argv]
    try:
        return analyze.parse_args()
    finally:
        sys.argv = saved


def test_cli_accepts_the_new_modes():
    args = _parse("--problematic", "--limit", "5", "--dry-run")
    assert args.problematic and args.limit == 5 and args.dry_run and not args.force
    print("✅ analyze.py: --problematic --limit --dry-run")


def test_force_active_is_exclusive_with_force():
    assert _parse("--force-active").force_active
    try:
        _parse("--force", "--force-active")
        assert False, "argparse should refuse --force together with --force-active"
    except SystemExit:
        pass


def test_force_and_problematic_are_exclusive():
    try:
        _parse("--force", "--problematic")
        assert False, "argparse should refuse --force together with --problematic"
    except SystemExit:
        pass
    print("✅ analyze.py: --force / --problematic exclusive")


def test_dry_run_summary_counts_calls_and_reasons():
    listings = [
        {"status": "ACTIVE", "motor_torque_nm": 85, "motor_verified": 1, "battery_capacity_wh": 625,
         "frame_size": "M", "suspension_type": "full_suspension", "ai_analyzed_at": "2026-01-01"},
        {"status": "ACTIVE", "motor_torque_nm": 60, "motor_verified": 0, "battery_capacity_wh": None,
         "frame_size": "M", "suspension_type": "full_suspension"},
        {"status": "REJECTED", "rejection_reason": "No motor detected (likely not an e-bike)"},
        {"status": "REJECTED", "rejection_reason": "Over budget (3500 > 3000 CHF)"},
    ] * 4  # 16 listings -> ceil(16 / MAX_BATCH_SIZE) API calls

    summary = analyze.dry_run_summary(listings)

    assert summary["listings"] == 16
    assert summary["api_calls"] == -(-16 // analyze.MAX_BATCH_SIZE)
    assert summary["already_analyzed"] == 4
    assert summary["reasons"] == {
        "specifiche complete": 4,
        "motore da verificare": 4,
        "batteria mancante": 4,
        "scartato per specifiche": 4,
        "scartato (motivo non correggibile)": 4,
    }
    print("✅ analyze.py: dry-run summary")


if __name__ == "__main__":
    test_cli_accepts_the_new_modes()
    test_force_and_problematic_are_exclusive()
    test_dry_run_summary_counts_calls_and_reasons()
    print("\n✅ All analyze tests passed!")


def _full_listing(**overrides):
    base = {
        "id": "tutti_1", "portal": "tutti_ch", "portal_id": "1", "url": "https://www.tutti.ch/x/1",
        "description_raw": "Descrizione lunga abbastanza per essere letta dall'AI senza problemi.",
        "motor_torque_nm": 85, "motor_verified": 1, "battery_capacity_wh": 625, "frame_size": "M",
        "suspension_type": "full_suspension", "travel_front_mm": 150, "travel_rear_mm": 140, "model_year": 2021,
    }
    base.update(overrides)
    return base


def test_needs_page_fetch_when_key_spec_missing():
    assert not analyze.needs_page_fetch(_full_listing())
    assert analyze.needs_page_fetch(_full_listing(travel_rear_mm=None))
    assert analyze.needs_page_fetch(_full_listing(model_year=None))
    assert analyze.needs_page_fetch(_full_listing(frame_size="unknown"))
    assert analyze.needs_page_fetch(_full_listing(motor_verified=0))
    assert analyze.needs_page_fetch(_full_listing(description_raw="corta"))


def test_enrich_fetches_page_for_missing_specs_and_saves_description(monkeypatch):
    """A long description with a missing spec must still trigger a live page
    fetch, and a fuller page text is persisted to the DB."""
    page_text = "Testo completo dall'annuncio: anno 2021, ammortizzatore 140mm, forcella 150mm, taglia M."
    calls = []

    class FakeConnector:
        def __init__(self, config):
            pass

        def get_listing_details(self, portal_id, url):
            calls.append(url)
            return {"description_raw": page_text}

    class FakeDB:
        saved = {}

        def update_description_raw(self, listing_id, text):
            self.saved[listing_id] = text

    monkeypatch.setitem(analyze.CONNECTOR_CLASSES, "tutti_ch", FakeConnector)
    db = FakeDB()
    complete = _full_listing(id="tutti_2")
    missing = _full_listing(travel_rear_mm=None)

    assert analyze.enrich_thin_descriptions([complete, missing], db, {}) == 1
    assert calls == ["https://www.tutti.ch/x/1"]
    assert db.saved == {"tutti_1": page_text}
    assert missing["description_raw"] == page_text


def test_gallery_pass_only_for_listings_with_more_photos():
    class FakeConnector:
        def __init__(self, config): pass
        def get_gallery_images(self, url):
            return {"u1": ["c1", "g2", "g3"], "u2": ["c2"]}[url]

    analyze.CONNECTOR_CLASSES["fake"] = FakeConnector
    try:
        a = {"id": "a", "portal": "fake", "url": "u1", "image_urls": ["c1"]}
        b = {"id": "b", "portal": "fake", "url": "u2", "image_urls": ["c2"]}
        retry = analyze.attach_gallery_photos([a, b], {})
    finally:
        del analyze.CONNECTOR_CLASSES["fake"]
    assert retry == [a] and a["image_urls"] == ["c1", "g2", "g3"]
    listings = [{"suspension_type": "unknown", "image_url": "p"}, {"suspension_type": "hardtail", "image_url": "p"}]
    assert analyze.attach_card_photos(listings) == 1 and "image_urls" not in listings[1]
