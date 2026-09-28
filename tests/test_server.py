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


def test_reject_keeps_listing_visible_greyed_then_restore_active():
    # Rejected/sold listings stay on the page (greyed out, filterable by the
    # dedicated Status control) rather than disappearing — otherwise there'd
    # be no way to find one again to hit "restore".
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/x_1/reject")
    assert resp.status_code == 200

    page = client.get("/").data
    assert b'data-id="x_1"' in page
    assert b'data-status-group="rejected"' in page

    resp = client.post("/api/listings/x_1/restore")
    assert resp.status_code == 200
    assert b'data-status-group="active"' in client.get("/").data
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


def test_favorite_toggle_persists_and_survives_reload():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/x_1/favorite")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "is_favorite": True}

    # Favoriting must not change status/visibility — still in the default view.
    assert b'data-id="x_1"' in client.get("/").data
    assert b'data-favorite="1"' in client.get("/").data

    resp = client.post("/api/listings/x_1/favorite")
    assert resp.get_json() == {"ok": True, "is_favorite": False}
    assert b'data-favorite="0"' in client.get("/").data

    Path(db_path).unlink()
    print("✅ Server favorite-toggle test passed")


def test_favorite_unknown_listing_returns_404():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/does_not_exist/favorite")
    assert resp.status_code == 404

    Path(db_path).unlink()
    print("✅ Server favorite unknown-listing 404 test passed")


def test_specs_correction_unknown_listing_returns_404():
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/does_not_exist/specs", json={"motor_brand": "Bosch"})
    assert resp.status_code == 404

    Path(db_path).unlink()
    print("✅ Server unknown-listing 404 test passed")


def test_cross_site_post_is_refused():
    # Any other page open in the browser can POST to 127.0.0.1:5050 — that
    # must not be able to delete or edit listings.
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    resp = client.post("/api/listings/x_1/delete", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    resp = client.post("/api/listings/x_1/delete", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403
    # text/plain body = no CORS preflight; get_json(force=True) would accept it.
    resp = client.post(
        "/api/listings/x_1/specs", data='{"frame_size": "XL"}',
        headers={"Origin": "null", "Content-Type": "text/plain"},
    )
    assert resp.status_code == 403

    db = Database(db_path)
    row = db.get_listing_with_specs("x_1")
    assert row is not None, "the listing must survive the cross-site delete"
    assert row["frame_size"] == "M"
    db.close()

    # The dashboard's own same-origin requests still work.
    resp = client.post(
        "/api/listings/x_1/favorite",
        headers={"Origin": "http://127.0.0.1:5050", "Sec-Fetch-Site": "same-origin"},
    )
    assert resp.status_code == 200

    Path(db_path).unlink()
    print("✅ Server cross-site POST refusal test passed")


def test_foreign_host_header_is_refused():
    # DNS rebinding: a public hostname resolving to 127.0.0.1.
    db_path = _fresh_db_with_listing()
    client = server_module.app.test_client()

    assert client.get("/", headers={"Host": "evil.example:5050"}).status_code == 403
    assert client.get("/", headers={"Host": "127.0.0.1:5050"}).status_code == 200

    Path(db_path).unlink()
    print("✅ Server foreign Host refusal test passed")


def test_scraped_title_and_url_are_escaped_in_dashboard():
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    db.upsert_listing({
        "portal": "x", "portal_id": "1", "url": "javascript:alert(1)",
        "title": '<img src=x onerror="alert(1)">', "price_raw": 2000, "currency": "CHF",
        "price_chf": 2000, "price_eur": 1900, "distance_km": 10.0, "status": "ACTIVE",
    })
    db.save_specifications("x_1", {
        "motor_brand": '"><script>alert(2)</script>', "motor_torque_nm": 85,
        "battery_capacity_wh": 625, "frame_size": "<b>M</b>",
    })
    db.save_score("x_1", {
        "score_total": 90.0, "score_price_value": 90.0, "score_component_quality": 90.0,
        "score_condition_mileage": 90.0, "score_location_proximity": 90.0,
        "score_fit_geometry": 90.0, "is_deal_target": True, "breakdown": {},
    })
    db.close()
    server_module.DB_PATH = db_path

    page = server_module.app.test_client().get("/").data.decode()

    assert '<img src=x onerror' not in page
    assert '<script>alert(2)</script>' not in page
    assert '<b>M</b>' not in page
    assert 'href="javascript:' not in page
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in page

    Path(db_path).unlink()
    print("✅ Dashboard escaping test passed")


if __name__ == "__main__":
    test_index_lists_active_listing()
    test_reject_keeps_listing_visible_greyed_then_restore_active()
    test_sold_marks_listing()
    test_specs_correction_marks_verified_and_rescores_higher()
    test_specs_correction_unknown_listing_returns_404()
    test_favorite_toggle_persists_and_survives_reload()
    test_favorite_unknown_listing_returns_404()
    test_cross_site_post_is_refused()
    test_foreign_host_header_is_refused()
    test_scraped_title_and_url_are_escaped_in_dashboard()
    print("\n✅ All server tests passed!")
