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

    # Test weak motor rejection
    title3 = "Specialized Levo SL con Fazua"
    desc3 = "Motore leggero Fazua 50nm"
    specs3 = parser.parse(title3, desc3)
    assert specs3["motor_brand"] is None

    print("✅ Motor detection tests passed")


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


if __name__ == "__main__":
    test_motor_detection()
    test_battery_extraction()
    test_frame_size_detection()
    test_suspension_type()
    test_travel_extraction()
    test_red_flags()
    test_odometer_no_false_positives()
    print("\n✅ All parser tests passed!")
