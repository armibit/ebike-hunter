"""Reference places for location resolution — provinces and cantons, not
towns. Coordinates are the capital's (or a central point), accurate to a
few km: distances only need to tell 100 km from 400 km apart.

Every entry: code -> (name aliases, lat, lon, region label).
"""
from typing import Dict, List, Tuple

Place = Tuple[List[str], float, float, str]

# Italian provinces, keyed by their two-letter code as Subito shows it
# ("Gravellona Toce (VB)"). Full detail for the North, where a buyer from
# Lugano would actually go; the rest of Italy is covered at region level
# below (distance there is always far anyway).
ITALIAN_PROVINCES: Dict[str, Place] = {
    # Lombardia
    "VA": (["varese"], 45.8206, 8.8251, "lombardia"),
    "CO": (["como"], 45.8081, 9.0852, "lombardia"),
    "LC": (["lecco"], 45.8566, 9.3977, "lombardia"),
    "SO": (["sondrio"], 46.1699, 9.8715, "lombardia"),
    "MB": (["monza e brianza", "monza", "brianza"], 45.5845, 9.2744, "lombardia"),
    "MI": (["milano", "milan"], 45.4642, 9.1900, "lombardia"),
    "BG": (["bergamo"], 45.6983, 9.6773, "lombardia"),
    "BS": (["brescia"], 45.5416, 10.2118, "lombardia"),
    "PV": (["pavia"], 45.1847, 9.1582, "lombardia"),
    "LO": (["lodi"], 45.3097, 9.5037, "lombardia"),
    "CR": (["cremona"], 45.1333, 10.0227, "lombardia"),
    "MN": (["mantova", "mantua"], 45.1564, 10.7914, "lombardia"),
    # Piemonte / Valle d'Aosta
    "VB": (["verbano-cusio-ossola", "verbano cusio ossola", "verbania", "verbano"], 45.9214, 8.5519, "piemonte"),
    "NO": (["novara"], 45.4469, 8.6220, "piemonte"),
    "VC": (["vercelli"], 45.3202, 8.4185, "piemonte"),
    "BI": (["biella"], 45.5629, 8.0583, "piemonte"),
    "TO": (["torino", "turin"], 45.0703, 7.6869, "piemonte"),
    "CN": (["cuneo"], 44.3845, 7.5427, "piemonte"),
    "AT": (["asti"], 44.9008, 8.2064, "piemonte"),
    "AL": (["alessandria"], 44.9133, 8.6150, "piemonte"),
    "AO": (["aosta", "valle d'aosta", "valle d’aosta"], 45.7376, 7.3172, "valle d'aosta"),
    # Liguria
    "GE": (["genova", "genoa"], 44.4056, 8.9463, "liguria"),
    "SV": (["savona"], 44.3091, 8.4772, "liguria"),
    "IM": (["imperia"], 43.8896, 8.0386, "liguria"),
    "SP": (["la spezia", "spezia"], 44.1025, 9.8241, "liguria"),
    # Emilia-Romagna
    "PC": (["piacenza"], 45.0526, 9.6930, "emilia-romagna"),
    "PR": (["parma"], 44.8015, 10.3279, "emilia-romagna"),
    "RE": (["reggio emilia", "reggio nell'emilia"], 44.6989, 10.6297, "emilia-romagna"),
    "MO": (["modena"], 44.6471, 10.9252, "emilia-romagna"),
    "BO": (["bologna"], 44.4949, 11.3426, "emilia-romagna"),
    "FE": (["ferrara"], 44.8381, 11.6198, "emilia-romagna"),
    "RA": (["ravenna"], 44.4184, 12.2035, "emilia-romagna"),
    "FC": (["forlì-cesena", "forli-cesena", "forlì", "forli", "cesena"], 44.2227, 12.0407, "emilia-romagna"),
    "RN": (["rimini"], 44.0678, 12.5695, "emilia-romagna"),
    # Veneto
    "VR": (["verona"], 45.4384, 10.9916, "veneto"),
    "VI": (["vicenza"], 45.5455, 11.5354, "veneto"),
    "PD": (["padova", "padua"], 45.4064, 11.8768, "veneto"),
    "VE": (["venezia", "venice"], 45.4408, 12.3155, "veneto"),
    "TV": (["treviso"], 45.6669, 12.2430, "veneto"),
    "BL": (["belluno"], 46.1425, 12.2167, "veneto"),
    "RO": (["rovigo"], 45.0698, 11.7902, "veneto"),
    # Trentino-Alto Adige
    "TN": (["trento", "trentino"], 46.0748, 11.1217, "trentino-alto adige"),
    "BZ": (["bolzano", "bozen", "alto adige", "südtirol", "sudtirol"], 46.4983, 11.3548, "trentino-alto adige"),
    # Friuli-Venezia Giulia
    "UD": (["udine"], 46.0711, 13.2346, "friuli-venezia giulia"),
    "PN": (["pordenone"], 45.9564, 12.6615, "friuli-venezia giulia"),
    "TS": (["trieste"], 45.6495, 13.7768, "friuli-venezia giulia"),
    "GO": (["gorizia"], 45.9409, 13.6217, "friuli-venezia giulia"),
}

# Italian regions (name -> capital), for "…, Lombardia" style strings and
# for province codes outside the detailed list above.
ITALIAN_REGIONS: Dict[str, Tuple[List[str], float, float]] = {
    "lombardia": (["lombardia", "lombardy"], 45.4642, 9.1900),
    "piemonte": (["piemonte", "piedmont"], 45.0703, 7.6869),
    "valle d'aosta": (["valle d'aosta", "valle d’aosta"], 45.7376, 7.3172),
    "liguria": (["liguria"], 44.4056, 8.9463),
    "emilia-romagna": (["emilia-romagna", "emilia romagna"], 44.4949, 11.3426),
    "veneto": (["veneto"], 45.4408, 12.3155),
    "trentino-alto adige": (["trentino-alto adige", "trentino alto adige"], 46.0748, 11.1217),
    "friuli-venezia giulia": (["friuli-venezia giulia", "friuli venezia giulia", "friuli"], 45.6495, 13.7768),
    "toscana": (["toscana", "tuscany"], 43.7696, 11.2558),
    "umbria": (["umbria"], 43.1107, 12.3908),
    "marche": (["marche"], 43.6158, 13.5189),
    "lazio": (["lazio"], 41.9028, 12.4964),
    "abruzzo": (["abruzzo"], 42.3498, 13.3995),
    "molise": (["molise"], 41.5603, 14.6627),
    "campania": (["campania"], 40.8518, 14.2681),
    "puglia": (["puglia", "apulia"], 41.1171, 16.8719),
    "basilicata": (["basilicata"], 40.6404, 15.8056),
    "calabria": (["calabria"], 38.9098, 16.5877),
    "sicilia": (["sicilia", "sicily"], 38.1157, 13.3615),
    "sardegna": (["sardegna", "sardinia"], 39.2238, 9.1217),
}

# Province codes outside the North -> their region (located at the
# region's capital: always hundreds of km away, which is all that matters).
OTHER_PROVINCE_REGIONS: Dict[str, str] = {
    **{c: "toscana" for c in ("FI", "PO", "PT", "LU", "MS", "PI", "LI", "AR", "SI", "GR")},
    **{c: "umbria" for c in ("PG", "TR")},
    **{c: "marche" for c in ("PU", "AN", "MC", "FM", "AP")},
    **{c: "lazio" for c in ("RM", "VT", "RI", "LT", "FR")},
    **{c: "abruzzo" for c in ("AQ", "TE", "PE", "CH")},
    **{c: "molise" for c in ("CB", "IS")},
    **{c: "campania" for c in ("CE", "BN", "NA", "AV", "SA")},
    **{c: "puglia" for c in ("FG", "BT", "BA", "TA", "BR", "LE")},
    **{c: "basilicata" for c in ("PZ", "MT")},
    **{c: "calabria" for c in ("CS", "KR", "CZ", "VV", "RC")},
    **{c: "sicilia" for c in ("TP", "PA", "ME", "AG", "CL", "EN", "CT", "RG", "SR")},
    **{c: "sardegna" for c in ("SS", "NU", "CA", "OR", "SU")},
}

# Swiss cantons: names in German/French/Italian/English as portals show
# them (Tutti: "Lugano, Ticino"; TCS/Velomarkt: "Zürich", "9524 St. Gallen").
SWISS_CANTONS: Dict[str, Place] = {
    "ZH": (["zürich", "zurich", "zurigo"], 47.3769, 8.5417, "svizzera"),
    "BE": (["bern", "berne", "berna"], 46.9480, 7.4474, "svizzera"),
    "LU": (["luzern", "lucerne", "lucerna"], 47.0502, 8.3093, "svizzera"),
    "UR": (["uri", "altdorf"], 46.8804, 8.6444, "svizzera"),
    "SZ": (["schwyz", "svitto"], 47.0207, 8.6530, "svizzera"),
    "OW": (["obwalden", "obwald", "obvaldo", "sarnen"], 46.8960, 8.2460, "svizzera"),
    "NW": (["nidwalden", "nidwald", "nidvaldo", "stans"], 46.9580, 8.3660, "svizzera"),
    "GL": (["glarus", "glaris", "glarona"], 47.0404, 9.0679, "svizzera"),
    "ZG": (["zug", "zoug", "zugo"], 47.1662, 8.5155, "svizzera"),
    "FR": (["freiburg", "fribourg", "friburgo"], 46.8065, 7.1619, "svizzera"),
    "SO": (["solothurn", "soleure", "soletta"], 47.2088, 7.5323, "svizzera"),
    "BS": (["basel-stadt", "basel", "bâle", "bale", "basilea"], 47.5596, 7.5886, "svizzera"),
    "BL": (["basel-landschaft", "baselland", "bâle-campagne", "basilea campagna", "liestal"], 47.4840, 7.7350, "svizzera"),
    "SH": (["schaffhausen", "schaffhouse", "sciaffusa"], 47.6973, 8.6349, "svizzera"),
    "AR": (["appenzell ausserrhoden", "herisau"], 47.3860, 9.2790, "svizzera"),
    "AI": (["appenzell innerrhoden", "appenzell"], 47.3310, 9.4090, "svizzera"),
    "SG": (["st. gallen", "st gallen", "sankt gallen", "saint-gall", "san gallo"], 47.4245, 9.3767, "svizzera"),
    "GR": (["graubünden", "graubunden", "grisons", "grigioni", "chur", "coira"], 46.8508, 9.5320, "svizzera"),
    "AG": (["aargau", "argovie", "argovia", "aarau"], 47.3925, 8.0444, "svizzera"),
    "TG": (["thurgau", "thurgovie", "turgovia", "frauenfeld"], 47.5536, 8.8987, "svizzera"),
    # Ticino: a central point (Monte Ceneri area) rather than Bellinzona —
    # canton-only strings are as likely Lugano as Bellinzona.
    "TI": (["ticino", "tessin", "tessin"], 46.1300, 8.9300, "ticino"),
    "VD": (["vaud", "waadt", "lausanne", "losanna"], 46.5197, 6.6323, "svizzera"),
    "VS": (["valais", "wallis", "vallese", "sion", "sitten"], 46.2331, 7.3606, "svizzera"),
    "NE": (["neuchâtel", "neuchatel", "neuenburg"], 46.9900, 6.9293, "svizzera"),
    "GE": (["genève", "geneve", "geneva", "genf", "ginevra"], 46.2044, 6.1432, "svizzera"),
    "JU": (["jura", "giura", "delémont", "delemont"], 47.3649, 7.3445, "svizzera"),
}

# Swiss postcodes are geographically clustered: the first two digits pin
# the canton (a few prefixes straddle a border — the majority canton wins).
SWISS_PLZ_PREFIX_CANTON: Dict[str, str] = {
    **{p: "VD" for p in ("10", "11", "13", "14", "15", "18")},
    "12": "GE",
    **{p: "FR" for p in ("16", "17")},
    "19": "VS",
    **{p: "NE" for p in ("20", "21", "22", "23")},
    **{p: "BE" for p in ("24", "25", "26", "30", "31", "32", "33", "34", "35", "36", "37", "38", "48", "49")},
    **{p: "JU" for p in ("27", "28", "29")},
    "39": "VS",
    "40": "BS",
    **{p: "BL" for p in ("41", "42", "44")},
    **{p: "SO" for p in ("45", "46", "47")},
    **{p: "AG" for p in ("43", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59")},
    **{p: "LU" for p in ("60", "61", "62")},
    "63": "ZG",
    "64": "SZ",
    **{p: "TI" for p in ("65", "66", "67", "68", "69")},
    **{p: "GR" for p in ("70", "71", "72", "73", "74", "75", "76", "77")},
    **{p: "ZH" for p in ("80", "81", "83", "84", "86", "88", "89")},
    "82": "SH",
    "85": "TG",
    "87": "GL",
    **{p: "SG" for p in ("90", "91", "92", "93", "94", "95", "96", "97")},
}

# Ticino postcodes are precise enough to place the listing in its district
# (65xx Bellinzona, 66xx Locarno, 67xx Leventina, 68xx Mendrisio, 69xx Lugano).
TICINO_PLZ_PREFIX_COORDS: Dict[str, Tuple[float, float]] = {
    "65": (46.1928, 9.0170),
    "66": (46.1683, 8.7984),
    "67": (46.3594, 8.9710),
    "68": (45.8711, 8.9878),
    "69": (46.0037, 8.9511),
}

COUNTRY_WORDS: Dict[str, List[str]] = {
    "CH": ["switzerland", "svizzera", "schweiz", "suisse", "swiss"],
    "IT": ["italy", "italia", "italie", "italien"],
}
