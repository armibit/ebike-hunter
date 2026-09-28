import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline.dedupe import dedupe_signature, find_duplicates


def test_same_bike_different_wording_and_order_matches():
    a = dedupe_signature("Vendo e-bike Cube Stereo Hybrid 140 625 taglia M", 2410)
    b = dedupe_signature("CUBE Stereo Hybrid 140 - 625, tg M", 2390)
    assert a and a == b
    print("✅ Dedupe: same bike, different wording")


def test_different_price_bucket_or_model_does_not_match():
    base = dedupe_signature("Cube Stereo Hybrid 140 625", 2400)
    assert dedupe_signature("Cube Stereo Hybrid 140 625", 2900) != base
    assert dedupe_signature("Cube Stereo Hybrid 160 625", 2400) != base
    print("✅ Dedupe: different price/model do not match")


def test_no_signature_without_identity_or_price():
    # Only filler words, or no usable price: never grouped with anything.
    assert dedupe_signature("Vendo ebike usata", 2000) == ""
    assert dedupe_signature("Trek Rail 9.7", 0) == ""
    assert dedupe_signature("Trek Rail 9.7", None) == ""
    print("✅ Dedupe: no signature without identity/price")


def test_find_duplicates_links_live_listings_only():
    sig = dedupe_signature("Trek Rail 9.7", 2800)
    listings = [
        {"id": "tutti_1", "portal": "tutti", "status": "ACTIVE", "dedupe_signature": sig},
        {"id": "velomarkt_7", "portal": "velomarkt", "status": "PRICE_DROP", "dedupe_signature": sig},
        {"id": "subito_3", "portal": "subito", "status": "REJECTED", "dedupe_signature": sig},
        {"id": "tutti_2", "portal": "tutti", "status": "ACTIVE", "dedupe_signature": ""},
    ]

    duplicates = find_duplicates(listings)

    assert [d["id"] for d in duplicates["tutti_1"]] == ["velomarkt_7"]
    assert [d["id"] for d in duplicates["velomarkt_7"]] == ["tutti_1"]
    assert "subito_3" not in duplicates, "a rejected copy is ignored"
    assert "tutti_2" not in duplicates, "no signature, never grouped"
    print("✅ Dedupe: find_duplicates")


if __name__ == "__main__":
    test_same_bike_different_wording_and_order_matches()
    test_different_price_bucket_or_model_does_not_match()
    test_no_signature_without_identity_or_price()
    test_find_duplicates_links_live_listings_only()
    print("\n✅ All dedupe tests passed!")
