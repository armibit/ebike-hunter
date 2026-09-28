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


def _bike(listing_id, title, price, status="ACTIVE", **extra):
    return {"id": listing_id, "portal": listing_id.split("_")[0], "title": title,
            "price_chf": price, "status": status, **extra}


def test_reworded_titles_of_the_same_bike_match():
    # Real-world pair: the shop's own site vs its Tutti ad — different
    # wording, a few % apart on price, same specs where both state them.
    duplicates = find_duplicates([
        _bike("tutti_1", "Cube Stereo Hybrid 140 HPC Race 625 - Taglia M", 2450, frame_size="M", battery_capacity_wh=625),
        _bike("zbike_7", "CUBE Stereo Hybrid 140 HPC Race 2022", 2390, frame_size="M", model_year=2022),
        _bike("tutti_2", "Trek Rail 9.7", 2800),
    ])
    assert [d["id"] for d in duplicates["tutti_1"]] == ["zbike_7"]
    assert [d["id"] for d in duplicates["zbike_7"]] == ["tutti_1"]
    assert "tutti_2" not in duplicates
    print("✅ Dedupe: reworded titles match")


def test_conflicting_known_specs_veto_a_match():
    # Same model, same price — but a different frame size or battery is a different bike.
    base = _bike("tutti_1", "Trek Rail 9.7 2022", 2800, frame_size="M", battery_capacity_wh=625)
    assert not find_duplicates([base, _bike("velomarkt_2", "Trek Rail 9.7 2022", 2800, frame_size="L")])
    assert not find_duplicates([base, _bike("velomarkt_2", "Trek Rail 9.7 2022", 2800, battery_capacity_wh=750)])
    assert not find_duplicates([dict(base, motor_brand="Bosch"),
                                _bike("velomarkt_2", "Trek Rail 9.7 2022", 2800, motor_brand="Shimano")])
    # Unknown on one side is not a conflict.
    assert find_duplicates([base, _bike("velomarkt_2", "Trek Rail 9.7 2022", 2800)])
    print("✅ Dedupe: spec vetoes")


def test_price_gap_and_distance_veto_a_match():
    a = _bike("tutti_1", "Specialized Turbo Levo Comp 2021", 3000)
    assert not find_duplicates([a, _bike("tutti_2", "Specialized Turbo Levo Comp 2021", 2400)]), "20% cheaper"
    # Two private sellers 200 km apart with the same popular model: two bikes.
    near = dict(a, latitude=46.00, longitude=8.95)
    far = _bike("tutti_3", "Specialized Turbo Levo Comp 2021", 3000, latitude=47.38, longitude=8.54)
    assert not find_duplicates([near, far])
    print("✅ Dedupe: price / distance vetoes")


def test_find_duplicates_groups_across_portals_and_ignores_dead_copies():
    duplicates = find_duplicates([
        _bike("tutti_1", "Orbea Rise M20 2023", 3000),
        _bike("velomarkt_7", "ORBEA Rise M20 (2023)", 2950, status="PRICE_DROP"),
        _bike("ridewill_4", "Orbea Rise M20 2023 usata", 2990),
        _bike("subito_3", "Orbea Rise M20 2023", 3000, status="SOLD"),
    ])
    assert sorted(d["id"] for d in duplicates["tutti_1"]) == ["ridewill_4", "velomarkt_7"]
    assert "subito_3" not in duplicates, "a sold copy is ignored"
    assert all("_tokens" not in d for group in duplicates.values() for d in group)
    print("✅ Dedupe: cross-portal groups")


if __name__ == "__main__":
    test_same_bike_different_wording_and_order_matches()
    test_different_price_bucket_or_model_does_not_match()
    test_no_signature_without_identity_or_price()
    test_reworded_titles_of_the_same_bike_match()
    test_conflicting_known_specs_veto_a_match()
    test_price_gap_and_distance_veto_a_match()
    test_find_duplicates_groups_across_portals_and_ignores_dead_copies()
    print("\n✅ All dedupe tests passed!")
