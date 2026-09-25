import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from db.database import Database
import server as server_module


def _fresh_db_with_listing():
    """A temp DB with one ACTIVE listing whose motor is an unverified
    RegexParser fallback guess — exactly the case the /specs endpoint's
    manual correction is meant to fix. Points server_module.DB_PATH at it
    so the app's routes operate on this DB instead of config.yaml's."""
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    db.upsert_listing({
        "portal": "x", "portal_id": "1", "url": "https://example.com/1",
        "title": "Test Bike", "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 1900, "distance_km": 10.0, "status": "ACTIVE",
    })
    db.save_specifications("x_1", {
        "motor_brand": "Unknown Motor", "motor_torque_nm": 60, "motor_verified": False,
        "battery_capacity_wh": 625, "frame_size": "M",
    })
    db.save_score("x_1", {
        "score_total": 60.0, "score_price_value": 60.0, "score_component_quality": 60.0,
        "score_condition_mileage": 60.0, "score_location_proximity": 60.0,
        "score_fit_geometry": 60.0, "is_deal_target": False, "breakdown": {},
    })
    db.close()
    server_module.DB_PATH = db_path
    return db_path


def test_index_lists_active_listing():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.get("/")
    assert resp.status_code == 200
    assert b'data-id="x_1"' in resp.data

    Path(db_path).unlink()
    print("✅ Server index test passed")


def test_reject_hides_then_restore_shows_listing():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/x_1/reject")
    assert resp.status_code == 200

    assert b'data-id="x_1"' not in client.get("/").data
    assert b'data-id="x_1"' in client.get("/?all=1").data

    resp = client.post("/api/listings/x_1/restore")
    assert resp.status_code == 200
    assert b'data-id="x_1"' in client.get("/").data

    Path(db_path).unlink()
    print("✅ Server reject/restore test passed")


def test_sold_marks_listing():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/x_1/sold")
    assert resp.status_code == 200

    db = Database(db_path)
    cursor = db.conn.cursor()
    cursor.execute("SELECT status FROM listings WHERE id = ?", ("x_1",))
    assert cursor.fetchone()["status"] == "SOLD"
    db.close()

    Path(db_path).unlink()
    print("✅ Server mark-sold test passed")


def test_specs_correction_marks_verified_and_rescores_higher():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post(
        "/api/listings/x_1/specs",
        json={"motor_brand": "Bosch", "motor_model": "Performance CX Gen4", "motor_torque_nm": 85},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    # A manually confirmed 85Nm Bosch motor scores higher than the 60Nm
    # unverified placeholder it replaced.
    assert body["score_total"] > 60.0

    db = Database(db_path)
    row = db.get_listing_with_specs("x_1")
    assert row["motor_brand"] == "Bosch"
    assert row["motor_torque_nm"] == 85
    assert row["motor_verified"] == 1  # editing it by hand counts as verifying it
    db.close()

    Path(db_path).unlink()
    print("✅ Server specs-correction test passed")


def test_specs_correction_unknown_listing_returns_404():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/does_not_exist/specs", json={"motor_brand": "Bosch"})
    assert resp.status_code == 404

    Path(db_path).unlink()
    print("✅ Server unknown-listing 404 test passed")


if __name__ == "__main__":
    test_index_lists_active_listing()
    test_reject_hides_then_restore_shows_listing()
    test_sold_marks_listing()
    test_specs_correction_marks_verified_and_rescores_higher()
    test_specs_correction_unknown_listing_returns_404()
    print("\n✅ All server tests passed!")
