import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline.regex_parser import RegexParser

TAXONOMY_PATH = str(Path(__file__).parent.parent / "config" / "taxonomy.json")


def test_motor_detection():
    parser = RegexParser(TAXONOMY_PATH)

    # Test Bosch CX detection
    title1 = "Specialized Turbo Levo Comp con Bosch CX Gen4"
    desc1 = "Motore Bosch Performance Line CX 85Nm"
    specs1 = parser.parse(title1, desc1)
    assert specs1["motor_brand"] == "Bosch"
    assert specs1["motor_torque_nm"] == 85

    # Test Brose detection
    title2 = "Specialized Levo 2021 Brose 2.1"
    desc2 = "Motore Specialized 2.1 90nm"
    specs2 = parser.parse(title2, desc2)
    assert specs2["motor_brand"] == "Specialized / Brose"
    assert specs2["motor_torque_nm"] == 90

    # Test weak motor rejection — brand/torque are still reported (not None)
    # so the reject reason reads "Weak motor (50nm < 60nm)" instead of the
    # misleading "No motor detected"; torque stays below min_motor_torque_nm
    # either way, so the reject verdict itself is unchanged.
    title3 = "Specialized Levo SL con Fazua"
    desc3 = "Motore leggero Fazua 50nm"
    specs3 = parser.parse(title3, desc3)
    assert specs3["motor_brand"] == "Weak/Light Motor"
    assert specs3["motor_torque_nm"] == 50

    print("✅ Motor detection tests passed")


def test_motor_detection_handles_real_world_phrasing_and_typos():
    parser = RegexParser(TAXONOMY_PATH)

    # Real seller listing: "Performance CX" without "Line", plus the very
    # common "Perfomance" typo (missing the second r) — neither was matched
    # before the patterns were widened; this pins that fix.
    desc = (
        "Modello: e-bike MTB Bulls Aminga Eva trail full suspesion\n"
        "Anno: 2020\nBatteria: 500wh\nKm totali: 1241\n"
        "Motore: bosch Perfomance CX\nTaglia: M"
    )
    specs = parser.parse("e-bike MTB Bulls Aminga Eva", desc)
    assert specs["motor_brand"] == "Bosch"
    assert specs["motor_torque_nm"] == 85
    assert specs["motor_verified"] is True
    assert specs["odometer_km"] == 1241

    # Correctly-spelled "Performance CX" (no "Line") must also match.
    specs2 = parser.parse("Trek Rail", "Motore Bosch Performance CX, batteria 625Wh")
    assert specs2["motor_brand"] == "Bosch"
    assert specs2["motor_torque_nm"] == 85

    print("✅ Real-world motor phrasing/typo test passed")


def test_odometer_extracts_km_totali_label_phrasing():
    parser = RegexParser(TAXONOMY_PATH)

    specs = parser.parse("Trek Rail", "Km totali: 1241")
    assert specs["odometer_km"] == 1241

    specs2 = parser.parse("Trek Rail", "Km totale 850")
    assert specs2["odometer_km"] == 850

    print("✅ 'Km totali' odometer phrasing test passed")


def test_motor_verified_flag():
    parser = RegexParser(TAXONOMY_PATH)

    # Explicit motor model named in the text — verified.
    specs_named = parser.parse("Specialized Turbo Levo", "Motore Bosch Performance Line CX 85Nm")
    assert specs_named["motor_verified"] is True

    # No motor model named, but generic e-bike keywords present — the
    # fallback assumes a motor exists (rather than rejecting the listing
    # outright) but must flag it as unverified so it doesn't score/read as
    # a confirmed spec.
    specs_fallback = parser.parse("Trek Rail e-bike full suspension", "In ottime condizioni")
    assert specs_fallback["motor_brand"] == "Unknown Motor"
    assert specs_fallback["motor_torque_nm"] == 60
    assert specs_fallback["motor_verified"] is False

    # No motor at all, no e-bike keywords — motor_verified stays unset.
    specs_none = parser.parse("Bici muscolare", "Nessun motore")
    assert specs_none["motor_brand"] is None
    assert specs_none["motor_verified"] is None


def test_motor_reads_explicit_torque_for_unrecognized_brand():
    # A budget/generic motor brand that isn't in taxonomy.json's curated
    # list (e.g. Lankeleisi's own motor) still states its real torque in
    # the text — that's a value read off the text, not a guess, so it must
    # be used (and marked verified) instead of falling back to the flat
    # 60Nm "unverified guess" placeholder.
    parser = RegexParser(TAXONOMY_PATH)

    specs = parser.parse(
        "Lankeleisi MG600 Pro 29 Full Suspension E-MTB",
        "Maximum Torque 65 N·m Controller 18A Controller Riding Mode",
    )
    assert specs["motor_brand"] == "Unknown Motor"
    assert specs["motor_torque_nm"] == 65
    assert specs["motor_verified"] is True

    # Same, with the "N.m" (period) and plain "Nm" spellings.
    specs_period = parser.parse("Generic e-bike", "torque of up to 65 N.m , allowing you to control terrain")
    assert specs_period["motor_torque_nm"] == 65
    assert specs_period["motor_verified"] is True

    specs_plain = parser.parse("Generic e-bike", "Motor torque: 70Nm, great for climbing")
    assert specs_plain["motor_torque_nm"] == 70
    assert specs_plain["motor_verified"] is True

    # An implausible number (well outside any real e-bike motor's range)
    # must NOT be taken at face value — falls through to the generic
    # unverified e-bike-keyword fallback instead.
    specs_out_of_range = parser.parse("E-bike", "Some unrelated spec: 999 Nm torque wrench")
    assert specs_out_of_range["motor_brand"] == "Unknown Motor"
    assert specs_out_of_range["motor_torque_nm"] == 60
    assert specs_out_of_range["motor_verified"] is False

    print("✅ Motor verified flag tests passed")


def test_battery_extraction():
    parser = RegexParser(TAXONOMY_PATH)

    title1 = "Trek Rail 7 Batteria 625Wh"
    specs1 = parser.parse(title1, "")
    assert specs1["battery_capacity_wh"] == 625

    title2 = "Cube Stereo Hybrid 140 HPC 750 Wh"
    specs2 = parser.parse(title2, "")
    assert specs2["battery_capacity_wh"] == 750

    print("✅ Battery extraction tests passed")


def test_frame_size_detection():
    parser = RegexParser(TAXONOMY_PATH)

    title1 = "Specialized Levo S2 taglia M"
    specs1 = parser.parse(title1, "")
    assert specs1["frame_size"] in ("M", "S2")

    title2 = "Trek Rail XL"
    specs2 = parser.parse(title2, "")
    assert specs2["frame_size"] == "disallowed"

    print("✅ Frame size detection tests passed")


def test_suspension_type():
    parser = RegexParser(TAXONOMY_PATH)

    title1 = "E-bike fully ammortizzata"
    specs1 = parser.parse(title1, "full suspension 140mm")
    assert specs1["suspension_type"] == "full_suspension"

    title2 = "E-MTB hardtail"
    specs2 = parser.parse(title2, "")
    assert specs2["suspension_type"] == "hardtail"

    # Regression: a bare "front" keyword in hardtail_disallowed used to
    # match the completely ordinary "150mm front travel" phrasing every
    # full-suspension bike's own spec sheet uses (front fork travel vs.
    # rear shock travel) — misreading a genuine full-suspension bike as a
    # hardtail purely because its description names its front travel.
    title3 = "Lankeleisi MG600 Pro Full Suspension E-MTB"
    specs3 = parser.parse(title3, "150mm front travel 130mm rear travel, full suspension")
    assert specs3["suspension_type"] == "full_suspension"

    # Bug #380: Italian listings often call the rear shock "ammortizzatore
    # centrale" (central shock) rather than "posteriore" (rear) — both mean
    # the bike has a rear shock in addition to the front fork.
    title4 = "Moustache Samedi Trail 5 bosch CX"
    specs4 = parser.parse(
        title4,
        "Forcella: ammortizza e ammortizzatore centrale regolabili ad aria",
    )
    assert specs4["suspension_type"] == "full_suspension"

    print("✅ Suspension type tests passed")


def test_travel_extraction():
    parser = RegexParser(TAXONOMY_PATH)

    title1 = "Trek Rail"
    desc1 = "Escursione 150mm / 140mm"
    specs1 = parser.parse(title1, desc1)
    assert specs1["travel_front_mm"] == 150
    assert specs1["travel_rear_mm"] == 140

    # Single travel value
    title2 = "Cube Stereo Hybrid 140"
    specs2 = parser.parse(title2, "")
    assert specs2["travel_front_mm"] == 140

    print("✅ Travel extraction tests passed")


def test_red_flags():
    parser = RegexParser(TAXONOMY_PATH)

    title1 = "Specialized Levo senza caricatore"
    specs1 = parser.parse(title1, "")
    assert specs1["has_red_flag"] is True
    assert len(specs1["red_flag_details"]) > 0

    title2 = "Trek Rail 9.7 perfetta con tutti gli accessori"
    specs2 = parser.parse(title2, "")
    assert specs2["has_red_flag"] is False

    print("✅ Red flag detection tests passed")


def test_odometer_no_false_positives():
    parser = RegexParser(TAXONOMY_PATH)

    # Travel distance must NOT be parsed as odometer
    specs1 = parser.parse("Trek Rail 7", "Forcella 150mm travel, ammortizzatore 140mm")
    assert specs1["odometer_km"] is None, f"False positive: travel distance parsed as odometer: {specs1['odometer_km']}"

    # Battery Wh must NOT match
    specs2 = parser.parse("E-bike 750Wh", "")
    assert specs2["odometer_km"] is None, f"False positive: 750Wh parsed as odometer: {specs2['odometer_km']}"

    # Real odometer must match
    specs3 = parser.parse("Specialized Levo", "Percorsi 1200 km, ottima condizione")
    assert specs3["odometer_km"] == 1200, f"Real odometer not detected: {specs3['odometer_km']}"

    print("✅ Odometer false positive tests passed")


def test_odometer_handles_thousands_separator_dot():
    parser = RegexParser(TAXONOMY_PATH)

    # German/Swiss listings use "." as a thousands separator, not a decimal
    # point (e.g. Upway.ch: "Kilometerstand : 1.443 km" means 1443 km, not
    # 1.443 km). A plain \d+ capture would truncate at the dot and read 1.
    specs = parser.parse("Some e-bike", "Kilometerstand : 1.443 km")
    assert specs["odometer_km"] == 1443, f"Thousands separator mishandled: {specs['odometer_km']}"

    print("✅ Odometer thousands-separator test passed")


def test_odometer_percorso_does_not_jump_to_unrelated_number():
    parser = RegexParser(TAXONOMY_PATH)

    # Real Subito.it listing (id 659597935): the real odometer figure
    # (7000) appears BEFORE "percorso", which here describes terrain
    # ("avendo percorso tracciati facili" = "having ridden easy trails"),
    # not an odometer reading. The old unbounded `[^\d]*` after
    # "percorso" would skip past this whole phrasing and grab the "62" in
    # the unrelated "C:62" frame material code several sentences later.
    desc = (
        "ebike con 7000 km ma in ottimo stato avendo percorso tracciati facili "
        "e mai enduro\n\nSpecifiche:\n\nTelaio principale C:62® Monocoque in carbonio"
    )
    specs = parser.parse("CUBE Stereo Hybrid", desc)
    assert specs["odometer_km"] == 7000, f"Expected real odometer 7000, got {specs['odometer_km']}"

    print("✅ Odometer 'percorso' non-jumping test passed")


if __name__ == "__main__":
    test_motor_detection()
    test_motor_detection_handles_real_world_phrasing_and_typos()
    test_odometer_extracts_km_totali_label_phrasing()
    test_motor_verified_flag()
    test_motor_reads_explicit_torque_for_unrecognized_brand()
    test_battery_extraction()
    test_frame_size_detection()
    test_suspension_type()
    test_travel_extraction()
    test_red_flags()
    test_odometer_no_false_positives()
    test_odometer_handles_thousands_separator_dot()
    test_odometer_percorso_does_not_jump_to_unrelated_number()
    print("\n✅ All parser tests passed!")
