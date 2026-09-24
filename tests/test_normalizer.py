import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pipeline.normalizer import Normalizer


def test_currency_normalization():
    norm = Normalizer(chf_to_eur=1.05, eur_to_chf=0.9524)

    # CHF to both
    price_chf, price_eur = norm.normalize_currency(2000, "CHF")
    assert price_chf == 2000
    assert 2090 <= price_eur <= 2110

    # EUR to both
    price_chf2, price_eur2 = norm.normalize_currency(2000, "EUR")
    assert price_eur2 == 2000
    assert 1900 <= price_chf2 <= 1910

    print("✅ Currency normalization tests passed")


def test_haversine_distance():
    norm = Normalizer()

    # Lugano to Lugano (should be ~0)
    dist_lugano = norm.haversine_km(46.0037, 8.9511)
    assert dist_lugano < 1.0

    # Lugano to Como (~23km)
    dist_como = norm.haversine_km(45.8081, 9.0852)
    assert 20 <= dist_como <= 26

    # Lugano to Milano (~65km)
    dist_milano = norm.haversine_km(45.4642, 9.1900)
    assert 60 <= dist_milano <= 70

    print("✅ Haversine distance tests passed")


def test_location_resolution():
    norm = Normalizer()

    # Lugano detection
    lat1, lon1, dist1, region1 = norm.resolve_location("Lugano, Ticino")
    assert region1 == "ticino"
    assert dist1 < 20

    # Como detection
    lat2, lon2, dist2, region2 = norm.resolve_location("Como, Lombardia")
    assert region2 == "lombardia"
    assert 20 <= dist2 <= 30

    # Varese detection
    lat3, lon3, dist3, region3 = norm.resolve_location("Varese (VA)")
    assert region3 == "lombardia"
    assert 20 <= dist3 <= 30

    # Unknown location
    lat4, lon4, dist4, region4 = norm.resolve_location("Sconosciuto")
    assert region4 == "other"

    print("✅ Location resolution tests passed")


def test_unknown_currency_returns_raw():
    import logging
    norm = Normalizer(chf_to_eur=1.05, eur_to_chf=0.9524)

    with_log = []
    handler = logging.handlers_test = type("H", (logging.Handler,), {"emit": lambda self, r: with_log.append(r.getMessage())})()
    logging.getLogger("pipeline.normalizer").addHandler(handler)

    chf_val, eur_val = norm.normalize_currency(1500, "GBP")
    assert chf_val == 1500
    assert eur_val == 1500
    assert any("GBP" in m or "Unknown" in m for m in with_log), "Expected warning for unknown currency"

    logging.getLogger("pipeline.normalizer").removeHandler(handler)
    print("✅ Unknown currency test passed")


if __name__ == "__main__":
    test_currency_normalization()
    test_haversine_distance()
    test_location_resolution()
    test_unknown_currency_returns_raw()
    print("\n✅ All normalizer tests passed!")
