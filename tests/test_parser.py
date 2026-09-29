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

    # Yamaha's motor series is literally named "PW-S2"/"PW-Series S2" —
    # must not be mistaken for a Specialized S2 frame size when the real
    # size (M) is stated separately (upway.ch/products/haibike-trekking-4-rk5fe8).
    title3 = "Haibike Trekking 4"
    desc3 = "Herstellergröße: M (45 cm) Motor Modell: PW-Series S2 Drehmoment: 75 Nm"
    specs3 = parser.parse(title3, desc3)
    assert specs3["frame_size"] == "M", f"Yamaha PW-S2 motor name misread as frame size: {specs3['frame_size']}"

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

    # Regression: Haibike "Trekking" line is hardtail by design but listings
    # never say so — they came out "unknown", passed the filter and ranked
    # top. A full-suspension trekking bike that says so must stay full.
    specs5 = parser.parse("E-Bike Haibike Trekking Cross 6 Low", "Come nuova: solo 153km")
    assert specs5["suspension_type"] == "hardtail"
    specs6 = parser.parse("Brinke explorer tg S - trekking full suspended", "")
    assert specs6["suspension_type"] == "full_suspension"
    # Naming only the rear shock model (no "full") still means full — even
    # on a "trekking" title, which must not be forced to hardtail then.
    specs7 = parser.parse("E-bike trekking Bosch CX", "ammortizzatore Fox Float DPS")
    assert specs7["suspension_type"] == "full_suspension"
    # Saying nothing about suspension stays unknown (kept, not rejected).
    specs8 = parser.parse("Cube Stereo Hybrid 140", "Bosch CX 625Wh")
    assert specs8["suspension_type"] == "unknown"

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


def test_bosch_smart_system_does_not_default_to_cx():
    parser = RegexParser(TAXONOMY_PATH)

    # "Smart System" alone names the Bosch platform, not a specific motor —
    # it must NOT be read as the 85Nm CX. With no torque figure or other
    # motor keyword in the text, it falls to the generic unverified e-bike
    # fallback (60Nm placeholder) instead of a confirmed CX match.
    specs = parser.parse("Haibike AllMtn 2023", "Bosch Smart System, e-bike full suspension")
    assert specs["motor_brand"] != "Bosch" or specs["motor_torque_nm"] != 85
    assert specs["motor_verified"] is False

    # Explicit CX still matches CX.
    specs_cx = parser.parse("Trek Rail", "Bosch CX Smart System 85Nm")
    assert specs_cx["motor_brand"] == "Bosch"
    assert specs_cx["motor_torque_nm"] == 85

    print("✅ Bosch Smart System CX-ambiguity test passed")


def test_bosch_sx_detected_as_weak_motor():
    parser = RegexParser(TAXONOMY_PATH)

    specs = parser.parse("Cube Reaction Hybrid SX", "Motore Bosch SX 55Nm, Smart System")
    assert specs["motor_brand"] == "Weak/Light Motor"
    assert specs["motor_torque_nm"] == 50

    print("✅ Bosch SX weak-motor detection test passed")


def test_travel_jolly_ignores_dropper_post_measurement():
    parser = RegexParser(TAXONOMY_PATH)

    # A hardtail with only a dropper post size in the 120-169mm jolly range
    # must NOT be read as having rear travel (which would misclassify it as
    # full suspension).
    specs = parser.parse("Trek Marlin hardtail", "Dropper post 150mm, reggisella telescopico")
    assert specs["travel_rear_mm"] is None, f"Dropper post read as rear travel: {specs['travel_rear_mm']}"
    assert specs["suspension_type"] == "hardtail"

    # A genuine bare travel number (no dropper/seatpost context) still counts.
    specs2 = parser.parse("Some e-bike", "140")
    assert specs2["travel_front_mm"] == 140

    print("✅ Travel jolly dropper-post exclusion test passed")


def test_odometer_ignores_battery_range():
    parser = RegexParser(TAXONOMY_PATH)

    # "Autonomia fino a 120 km" is battery range, not distance ridden.
    specs = parser.parse("Specialized Levo", "Autonomia fino a 120 km, batteria 700Wh")
    assert specs["odometer_km"] is None, f"Battery range read as odometer: {specs['odometer_km']}"

    # A real odometer reading using the generic "km: N" fallback still matches.
    specs2 = parser.parse("Specialized Levo", "km: 850, ottime condizioni")
    assert specs2["odometer_km"] == 850

    print("✅ Odometer battery-range exclusion test passed")


def test_frame_size_bare_number_requires_unit():
    parser = RegexParser(TAXONOMY_PATH)

    # A bare "17" with no inch/pollici marker must not match size M — could
    # be a price, date, or weight instead.
    specs = parser.parse("Trek Rail", "Prezzo 17.-, peso 18kg")
    assert specs["frame_size"] == "unknown", f"Bare number misread as frame size: {specs['frame_size']}"

    # With an explicit unit it still matches.
    specs2 = parser.parse("Trek Rail", "Taglia 17 pollici")
    assert specs2["frame_size"] == "M"

    print("✅ Frame size bare-number unit requirement test passed")


def test_frame_size_cm_ranges():
    parser = RegexParser(TAXONOMY_PATH)

    # cm-only sizing is not classified past the seller-observed anchors
    # (43-46cm=M, 50/52/54cm=disallowed): the same cm number maps to a
    # different letter on MTB vs. trekking/city geometry (e.g. 54cm is
    # "too big" on an MTB but a genuine M on many trekking bikes), so
    # cm ranges outside those exact validated values stay "unknown"
    # rather than risk hard-rejecting a real M bike.
    for cm in (43, 44, 45, 46):
        specs = parser.parse("Canyon Neuron", f"Taglia {cm} cm")
        assert specs["frame_size"] == "M", f"{cm}cm should be M, got {specs['frame_size']}"

    for cm in (50, 52, 54):
        specs = parser.parse("Canyon Neuron", f"Taglia {cm} cm")
        assert specs["frame_size"] == "disallowed", f"{cm}cm should be disallowed, got {specs['frame_size']}"

    for cm in (38, 42, 47, 48, 53, 58, 61):
        specs = parser.parse("Canyon Neuron", f"Taglia {cm} cm")
        assert specs["frame_size"] == "unknown", f"{cm}cm should stay unknown, got {specs['frame_size']}"

    print("✅ Frame size cm range test passed")


def test_disallowed_frame_size_remembers_what_was_written():
    # The reject reason used to read "Wrong size (disallowed)" — useless for
    # deciding whether the parser misread it. Now it keeps the size found.
    parser = RegexParser(TAXONOMY_PATH)
    specs = parser.parse("Trek Rail 9.7 taglia XL", "")
    assert specs["frame_size"] == "disallowed"
    assert specs["frame_size_detected"] == "XL"
    assert "frame_size_detected" not in parser.parse("Trek Rail 9.7 taglia M", "")
    print("✅ Disallowed frame size keeps the detected size")


def test_old_bike_year_and_bosch_cx_generation():
    parser = RegexParser(TAXONOMY_PATH)
    # Real tutti listing: 2017 bike, generic "bosch performance CX".
    specs = parser.parse(
        "E-bike Moustache Samedi Trail 5 bosch CX",
        "Anno: 2017\nBatteria: 500wh\nMotore: bosch performance CX\nRevisionata 2025",
    )
    assert specs["model_year"] == 2017
    assert specs["motor_torque_nm"] == 75

    # Stated 85Nm keeps Gen4 even on an old year.
    specs = parser.parse("Trek Rail 2019", "Bosch CX 85Nm")
    assert specs["motor_torque_nm"] == 85


def test_labelled_frame_size_field():
    """Regression: velocorner's "Frame size Small" (Husqvarna MC4, #1824)
    was not recognised at all -> unknown."""
    parser = RegexParser(TAXONOMY_PATH)
    text = "Model year 2024 Condition Used Frame size Small Dimensions Color White"
    specs = parser.parse("Husqvarna Mountain Cross MC4", text)
    assert specs["frame_size"] == "disallowed"
    assert specs["frame_size_detected"] == "S"
    assert parser.parse("Bike", "Frame size Medium Color Black")["frame_size"] == "M"
    assert parser.parse("Bike", "Rahmengrösse: L")["frame_size_detected"] == "L"
    assert parser.parse("Bike", "Taglia telaio S2")["frame_size"] == "S2"
    # Labelled field wins over a loose "M" elsewhere ("M10" isn't a size anyway).
    assert parser.parse("Orbea Rise M", "Frame size Large")["frame_size"] == "disallowed"
    # Ranges / lists that include M fit.
    assert parser.parse("Focus THRON", "Frame size S-M Color Black")["frame_size"] == "M"
    assert parser.parse("Cannondale", "Rahmengrösse: S, M oder L")["frame_size"] == "M"


def test_bike_brand_extraction():
    """Frame brand as its own field for the dashboard "Marca" filter.
    Regression: substring match made "Haibike TREKKING 4" a Trek."""
    parser = RegexParser(TAXONOMY_PATH)
    assert parser.parse("Haibike TREKKING 4", "")["brand"] == "Haibike"
    assert parser.parse("Moustache Samedi Trail 5", "")["brand"] == "Moustache"
    assert parser.parse("Vendo Riese & Müller Delite", "")["brand"] == "Riese & Müller"
    assert parser.parse("Santa Cruz Heckler 9", "")["brand"] == "Santa Cruz"
    assert parser.parse("Turbo Levo Comp", "")["brand"] == "Specialized"
    # Not in the title -> taken from the description.
    assert parser.parse("E-MTB full 150mm", "Vendo la mia Lapierre Overvolt")["brand"] == "Lapierre"
    assert parser.parse("E-MTB full 150mm", "motore Bosch CX")["brand"] is None


def test_brand_alias_in_prose_is_not_a_brand():
    """Regression: buybestgear's Vakole EMT29 body says "known for EU
    warehousing and e-mobility focus. The EMT29 12s ...", and the description
    fallback turned every page carrying that blurb into a Focus."""
    parser = RegexParser(TAXONOMY_PATH)
    blurb = (
        "Vakole distributes its E-MTBs via the BuyBestGear online platform, known for "
        "EU warehousing and e-mobility focus. The EMT29 12s makes a bold statement."
    )
    specs = parser.parse('Vakole EMT29 29" 12s E-Mountain Bike 691Wh Full Suspension EMTB', blurb)
    assert specs["brand"] == "Vakole"

    # Nothing but the prose "focus" anywhere: no brand beats the wrong brand.
    prose_only = "Sold via a platform known for EU warehousing and e-mobility focus. The bike ships fast."
    assert parser.parse("E-Mountain Bike 691Wh", prose_only)["brand"] is None
    # A real "Brand Model" mention later in the prose is still picked up.
    assert parser.parse("E-MTB full", f"{prose_only} Vendo Focus Jam2 6.8")["brand"] == "Focus"
    # Brand as the last meaningful word keeps working.
    assert parser.parse("Vendo MTB elettrica Cube.", "")["brand"] == "Cube"


def test_seo_keyword_dump_is_not_read_as_specs():
    """Regression: subito sellers append a comma-separated keyword dump naming
    bikes the ad isn't selling. Parsed as the ad body it invented specs — a
    muscular Merida One-Twenty passed as an e-bike off its "e-bike, ebike",
    and "150mm, 170mm" in the same list made it full suspension."""
    from pipeline.regex_parser import strip_keyword_spam
    parser = RegexParser(TAXONOMY_PATH)

    spam = (
        "mtb, mountain bike, mountainbike, mountain-bike, enduro, trail, all mountain, am, "
        "enduro mtb, bici montagna, bicicletta, merida, team, specialized, stumpjumper, "
        "turbo levo, kenevo, commencal meta am, clash, orbea rallon, occam, wild, e-mtb, "
        "emtb, e-bike, ebike, elettrica, carbonio, fox, rockshox, 150mm, 170mm, 180mm."
    )
    specs = parser.parse("Mtb full Merida One-Twenty 7.600 Carbon GX", f"Vendo la mia MTB. {spam}")
    assert specs["motor_brand"] is None
    assert specs["motor_torque_nm"] is None
    assert specs["travel_rear_mm"] is None

    # A real e-bike body keeps its motor even with the dump appended.
    real = "Motore Bosch Performance CX, batteria 625Wh, escursione 150mm / 140mm."
    specs_real = parser.parse("Cube Stereo Hybrid", f"{real} {spam}")
    assert specs_real["motor_brand"] == "Bosch"
    assert specs_real["battery_capacity_wh"] == 625

    # A comma-separated spec sheet is fragmented too, but states measurements,
    # so it must survive — it's where the motor/battery live.
    sheet = "29”, batteria integrata, passaggio cavi interno, travel 160 mm, Boost 12x148 mm, UDH hanger"
    assert strip_keyword_spam(sheet) == sheet
    # A label-per-line sheet has no commas at all and must never be cut.
    lines = "Motore Yamaha\nBatteria Yamaha\nCambio Shimano\nDoppio ammortizzatore\nReggisella telescopico"
    assert strip_keyword_spam(lines) == lines
    assert strip_keyword_spam("") == ""


def test_battery_and_bosch_typo_from_labelled_fields():
    """"batteria : 750w" (colon separator) and the seller typo "Bosh CX"."""
    parser = RegexParser(TAXONOMY_PATH)
    specs = parser.parse("Focus Jam2 8.9 - Tg L", "Motore : Bosh CX \nbatteria : 750w eterna !!!")
    assert specs["motor_brand"] == "Bosch"
    assert specs["motor_torque_nm"] == 85
    assert specs["battery_capacity_wh"] == 750


def test_price_from_text_and_folding_excluded():
    from pipeline.regex_parser import price_from_text
    assert price_from_text("Batteria 625Wh\nprezzo € 2450 \nconsegna a mano") == 2450
    assert price_from_text("Preis: 1'900.- CHF") == 1900
    assert price_from_text("prezzo trattabile, 625 Wh") == 0.0

    parser = RegexParser(TAXONOMY_PATH)
    specs = parser.parse("Giant Trance X E+ 3", "Motore: Yamaha SyncDrive Pro. La bicicletta ha all'attivo 2.300 km")
    assert specs["motor_brand"] == "Yamaha"
    assert specs["odometer_km"] == 2300
    assert parser.parse("Engwe L20 Foldable Electric Bike", "")["excluded_category"] == "foldable"
    assert parser.parse("Cube Stereo", "copertoni Maxxis folding")["excluded_category"] is None
    assert parser.parse("Moustache Samedi", "lucchetto: Abus pieghevole")["excluded_category"] is None


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
    test_bosch_smart_system_does_not_default_to_cx()
    test_bosch_sx_detected_as_weak_motor()
    test_travel_jolly_ignores_dropper_post_measurement()
    test_odometer_ignores_battery_range()
    test_frame_size_bare_number_requires_unit()
    test_frame_size_cm_ranges()
    test_disallowed_frame_size_remembers_what_was_written()
    print("\n✅ All parser tests passed!")


def test_gears_extracted_and_bounded():
    parser = RegexParser(TAXONOMY_PATH)
    assert parser._extract_gears("sram gx eagle 12 speed") == 12
    assert parser._extract_gears("bosch cx 12v 600wh") == 12
    assert parser._extract_gears("cassetta 1x11") == 11
    assert parser._extract_gears("10 rapporti shimano") == 10
    assert parser._extract_gears("batteria 36v 24s 625wh") is None
    assert parser._extract_gears("nessun dato") is None
