import logging
import math
import re
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


LUGANO_LAT = 46.0037
LUGANO_LON = 8.9511

# Approximate coordinates for frequent regions/cities
KNOWN_COORDINATES: Dict[str, Tuple[float, float]] = {
    # Ticino
    "lugano": (46.0037, 8.9511),
    "mendrisio": (45.8711, 8.9878),
    "chiasso": (45.8344, 9.0308),
    "bellinzona": (46.1928, 9.0180),
    "locarno": (46.1683, 8.7984),
    "biasca": (46.3594, 8.9710),
    "ascona": (46.1550, 8.7733),
    "massagno": (46.0125, 8.9450),
    "paradiso": (45.9922, 8.9483),
    "grigioni": (46.8508, 9.5320),
    # Lombardia
    "como": (45.8081, 9.0852),
    "cantù": (45.7417, 9.1306),
    "erba": (45.8117, 9.2272),
    "varese": (45.8206, 8.8251),
    "busto arsizio": (45.6120, 8.8518),
    "gallarate": (45.6597, 8.7933),
    "saronno": (45.6264, 9.0361),
    "lecco": (45.8566, 9.3977),
    "merate": (45.6989, 9.4244),
    "monza": (45.5845, 9.2744),
    "lissone": (45.6111, 9.2433),
    "seregno": (45.6517, 9.2061),
    "milano": (45.4642, 9.1900),
    "rho": (45.5328, 9.0408),
    "legnano": (45.5967, 8.9167),
    "brescia": (45.5416, 10.2118),
    "luino": (46.0017, 8.7433),
    "laveno": (45.9086, 8.6187),
    # Piemonte — Verbano (Lago Maggiore / Ossola), 30–50 km from Lugano
    "verbania": (45.9214, 8.5519),
    "verbano-cusio-ossola": (45.9214, 8.5519),
    "stresa": (45.8836, 8.5333),
    "omegna": (45.8766, 8.4078),
    "domodossola": (46.1159, 8.2926),
    "cannobio": (46.0617, 8.6961),
}

_PROVINCE_CAPITALS = {
    "vb": "verbania", "va": "varese", "co": "como", "lc": "lecco",
    "mb": "monza", "mi": "milano", "bs": "brescia",
}


class Normalizer:
    def __init__(self, chf_to_eur: float = 1.05, eur_to_chf: float = 0.9524):
        self.chf_to_eur = chf_to_eur
        self.eur_to_chf = eur_to_chf

    def normalize_currency(self, amount: float, currency: str) -> Tuple[float, float]:
        """
        Returns (price_chf, price_eur).
        """
        curr = currency.upper().strip()
        if curr in ("CHF", "FR", "FR."):
            return round(amount, 2), round(amount * self.chf_to_eur, 2)
        elif curr in ("EUR", "€"):
            return round(amount * self.eur_to_chf, 2), round(amount, 2)
        logger.warning("Unknown currency %r for amount %s — returning raw value", currency, amount)
        return amount, amount

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float = LUGANO_LAT, lon2: float = LUGANO_LON) -> float:
        r = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
        return round(2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)), 1)

    def resolve_location(self, location_raw: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
        """
        Resolves raw location string into (lat, lon, distance_km, region).
        """
        if not location_raw:
            return None, None, 999.0, "unknown"

        loc_lower = location_raw.lower().strip()
        region = "other"

        # Check known city coordinates
        for city, coords in KNOWN_COORDINATES.items():
            # Whole words only — a plain substring test put "Verbania" at
            # Erba and would match "rho"/"como" inside unrelated names.
            if re.search(rf"\b{re.escape(city)}\b", loc_lower):
                lat, lon = coords
                dist = self.haversine_km(lat, lon)
                if dist <= 50.0 and (
                    any(k in loc_lower for k in ["lugano", "mendrisio", "chiasso", "bellinzona", "locarno", "ticino"])
                    or re.search(r"\bti\b", loc_lower)
                ):
                    region = "ticino"
                else:
                    region = "lombardia" if dist <= 120.0 else "other"
                return lat, lon, dist, region

        # Italian province code, e.g. "Gravellona Toce (VB)" — a town not in
        # KNOWN_COORDINATES still gets its province capital's position.
        province = re.search(r"\((vb|va|co|lc|mb|mi|bs)\)", loc_lower)
        if province:
            lat, lon = KNOWN_COORDINATES[_PROVINCE_CAPITALS[province.group(1)]]
            dist = self.haversine_km(lat, lon)
            return lat, lon, dist, "lombardia" if dist <= 120.0 else "other"

        # Regional heuristics
        if any(t in loc_lower for t in ["ticino", "lugano", "mendrisiotto"]) or re.search(r"\bti\b", loc_lower):
            return LUGANO_LAT, LUGANO_LON, 15.0, "ticino"
        if re.search(r"\b(?:como|varese|lecco|monza|milano|lombardia)\b", loc_lower):
            return 45.8081, 9.0852, 35.0, "lombardia"

        return None, None, 150.0, "other"
