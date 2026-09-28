import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import reprocess_all
from db.database import Database


def test_reprocess_refreshes_specs_of_rejected_listings(monkeypatch):
    """Regression: specs (e.g. the new brand field) were only re-saved for
    listings that pass the filters, so rejected rows kept stale values."""
    tmp = tempfile.mktemp(suffix=".db")
    db = Database(tmp)
    db.upsert_listing({
        "portal": "tutti", "portal_id": "1", "url": "https://example.com/1",
        "title": "Engwe L20 Foldable", "description_raw": "e-bike pieghevole",
        "price_raw": 900, "currency": "CHF", "price_chf": 900, "price_eur": 850,
        "location_raw": "Lugano", "status": "ACTIVE",
    })
    db.close()

    config = reprocess_all.load_config()
    config["app"]["db_path"] = tmp
    monkeypatch.setattr(reprocess_all, "load_config", lambda: config)
    monkeypatch.setattr(sys, "argv", ["reprocess_all.py"])
    reprocess_all.main()

    db = Database(tmp)
    row = db.conn.execute(
        "SELECT l.status, s.brand FROM listings l JOIN specifications s ON s.listing_id = l.id"
    ).fetchone()
    db.close()
    Path(tmp).unlink()
    assert row["status"] == "REJECTED"
    assert row["brand"] == "Engwe"
