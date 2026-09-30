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


def test_ticino_word_boundary_false_positive():
    norm = Normalizer()

    # "Stiviere" contains the bare substring "ti" but is not the Ticino
    # abbreviation — must not be misclassified as Ticino.
    lat, lon, dist, region = norm.resolve_location("Castiglione delle Stiviere, Lombardia")
    assert region == "lombardia", f"expected lombardia, got {region}"

    # Genuine "TI" canton abbreviation must still resolve to Ticino.
    lat2, lon2, dist2, region2 = norm.resolve_location("Bellinzona TI")
    assert region2 == "ticino"

    print("✅ Ticino word-boundary false-positive test passed")


def test_city_match_is_whole_word_only():
    from pipeline.normalizer import KNOWN_COORDINATES
    norm = Normalizer()

    # "Verbania" contains "erba" — it used to get Erba's coordinates.
    lat, lon, dist, region = norm.resolve_location("Verbania (VB)")
    assert (lat, lon) != KNOWN_COORDINATES["erba"]

    # "Rhodes"/"Comologno" contain "rho"/"como" as plain substrings.
    assert norm.resolve_location("Comologno")[:2] != KNOWN_COORDINATES["como"]
    assert norm.resolve_location("Rhodes")[:2] != KNOWN_COORDINATES["rho"]

    # Real whole-word matches, accents included, still resolve.
    assert norm.resolve_location("Erba (CO)")[:2] == KNOWN_COORDINATES["erba"]
    assert norm.resolve_location("Cantù (CO)")[:2] == KNOWN_COORDINATES["cantù"]

    print("✅ Whole-word city match test passed")


def test_verbano_and_province_codes_resolve_nearby():
    from pipeline.normalizer import KNOWN_COORDINATES
    norm = Normalizer()

    # Verbano towns are 30–50 km away — they used to fall back to 150 km.
    lat, lon, dist, region = norm.resolve_location("Verbania")
    assert (lat, lon) == KNOWN_COORDINATES["verbania"]
    assert 25 <= dist <= 45

    # A town not in the list still gets its province capital's position.
    lat, lon, dist, region = norm.resolve_location("Gravellona Toce (VB)")
    assert (lat, lon) == KNOWN_COORDINATES["verbania"]
    assert dist < 50

    # Subito's usual "Town (XX)" format for a Lombardia province.
    assert norm.resolve_location("Gavirate (VA)")[:2] == KNOWN_COORDINATES["varese"]

    print("✅ Verbano / province code resolution test passed")


def test_any_town_resolves_by_province_or_canton():
    # The bug: any town not in a hand-made list fell back to a fake 150 km.
    # Now the province code / canton / postcode places it, whatever the town.
    norm = Normalizer()

    loc = norm.resolve("Merone (CO)")          # Subito format, unknown town
    assert (loc.country, loc.area, loc.region) == ("IT", "CO", "lombardia")
    assert loc.distance_km < 35

    loc = norm.resolve("Treviglio (BG)")
    assert loc.area == "BG" and 60 <= loc.distance_km <= 90

    loc = norm.resolve("Bergamo")               # province name alone
    assert loc.area == "BG"

    loc = norm.resolve("Winterthur, Zürich")    # Tutti "town, canton"
    assert (loc.country, loc.area, loc.region) == ("CH", "ZH", "svizzera")
    assert 120 <= loc.distance_km <= 170

    loc = norm.resolve("9524 Zuzwil")           # Velomarkt "PLZ town"
    assert (loc.country, loc.area) == ("CH", "SG")

    loc = norm.resolve("6743 Bodio")            # Ticino postcode: district-level
    assert (loc.area, loc.region) == ("TI", "ticino") and loc.distance_km < 50

    loc = norm.resolve("Genève")                # French canton name
    assert loc.area == "GE" and loc.distance_km > 200

    print("✅ Province / canton / postcode resolution test passed")


def test_far_italy_is_far():
    norm = Normalizer()
    for text in ("Roma (RM)", "Napoli, Campania", "Palermo (PA)", "Verona (VR)"):
        loc = norm.resolve(text)
        assert loc.country == "IT" and loc.distance_km > 150, (text, loc)
    print("✅ Far Italy resolves far")


def test_country_hint_settles_codes_valid_in_both_countries():
    norm = Normalizer()
    # "(GR)" is Grosseto on an Italian portal, Graubünden on a Swiss one.
    assert norm.resolve("Castiglione (GR)", country_hint="IT").region == "toscana"
    assert norm.resolve("Davos (GR)", country_hint="CH").area == "GR"
    # A 4-digit number on an Italian portal is not a Swiss postcode.
    assert norm.resolve("Merone 6900").area == "TI"
    assert norm.resolve("Merone 6900", country_hint="IT").country == "IT"
    print("✅ Country hint test passed")


def test_country_only_and_unknown_locations_are_neutral():
    norm = Normalizer()
    loc = norm.resolve("Switzerland")
    assert (loc.country, loc.latitude, loc.region) == ("CH", None, "svizzera")
    loc = norm.resolve("Europe")
    assert (loc.latitude, loc.region, loc.distance_km) == (None, "other", 150.0)
    loc = norm.resolve("")
    assert (loc.region, loc.distance_km) == ("unknown", 999.0)
    print("✅ Neutral location test passed")


def test_home_location_comes_from_config():
    # Distances are from the buyer's configured home, not a hard-coded Lugano.
    zurich_home = Normalizer(home_lat=47.3769, home_lon=8.5417)
    assert zurich_home.resolve("Zürich").distance_km < 1
    print("✅ Configurable home location test passed")


if __name__ == "__main__":
    test_currency_normalization()
    test_haversine_distance()
    test_location_resolution()
    test_unknown_currency_returns_raw()
    test_ticino_word_boundary_false_positive()
    test_city_match_is_whole_word_only()
    test_verbano_and_province_codes_resolve_nearby()
    test_any_town_resolves_by_province_or_canton()
    test_far_italy_is_far()
    test_country_hint_settles_codes_valid_in_both_countries()
    test_country_only_and_unknown_locations_are_neutral()
    test_home_location_comes_from_config()
    print("\n✅ All normalizer tests passed!")


def test_postcode_pins_exact_town():
    norm = Normalizer()
    # Tutti: PLZ + town; Pregassona is Lugano-side, not the Ticino centroid
    loc = norm.resolve("6963 Pregassona, Ticino", "CH")
    assert loc.place == "Pregassona" and loc.region == "ticino" and loc.distance_km < 5
    # Subito-style: 5-digit CAP with only a province in the text
    loc = norm.resolve("22100 Como (CO)", "IT")
    assert loc.place == "Como" and loc.area == "CO" and loc.region == "lombardia"
    # CAP alone, no hint
    assert norm.resolve("28922").place is not None
    # Unknown code falls back to the old text resolution
    assert norm.resolve("Lugano, Ticino").place is None
