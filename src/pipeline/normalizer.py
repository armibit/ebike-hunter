import logging
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from pipeline.geo_data import (
    COUNTRY_WORDS,
    ITALIAN_PROVINCES,
    ITALIAN_REGIONS,
    OTHER_PROVINCE_REGIONS,
    SWISS_CANTONS,
    SWISS_PLZ_PREFIX_CANTON,
    TICINO_PLZ_PREFIX_COORDS,
)

logger = logging.getLogger(__name__)


LUGANO_LAT = 46.0037
LUGANO_LON = 8.9511

# Neutral distances when a place can't be pinned down: no location text at
# all, or text we couldn't place (or only a country). Never used to reject.
DISTANCE_NO_LOCATION = 999.0
DISTANCE_UNRESOLVED = 150.0

# A handful of towns resolved more precisely than their province/canton —
# the ones around Lugano, where a few km change the score. Everything else
# resolves at province/canton level (see pipeline/geo_data.py).
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
    # Piemonte — Verbano
    "verbania": (45.9214, 8.5519),
}
_TICINO_TOWNS = {"lugano", "mendrisio", "chiasso", "bellinzona", "locarno", "biasca", "ascona", "massagno", "paradiso"}
_PIEMONTE_TOWNS = {"verbania"}


@dataclass
class Location:
    latitude: Optional[float]
    longitude: Optional[float]
    distance_km: float
    region: str               # "ticino", "svizzera", an Italian region ("lombardia"…), "other", "unknown"
    country: Optional[str]    # "CH", "IT" or None
    area: Optional[str] = None  # canton / province code, when resolved at that level

    def as_tuple(self) -> Tuple[Optional[float], Optional[float], float, str]:
        return self.latitude, self.longitude, self.distance_km, self.region


def _alias_table() -> List[Tuple[str, str, str]]:
    """(alias, country, code) for every province and canton name, longest
    first — so "basel-landschaft" wins over "basel", "reggio emilia" over
    nothing shorter, etc."""
    table = [(alias, "IT", code) for code, (aliases, *_rest) in ITALIAN_PROVINCES.items() for alias in aliases]
    table += [(alias, "CH", code) for code, (aliases, *_rest) in SWISS_CANTONS.items() for alias in aliases]
    return sorted(table, key=lambda entry: len(entry[0]), reverse=True)


_ALIASES = _alias_table()


def _has_word(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


class Normalizer:
    def __init__(self, chf_to_eur: float = 1.05, eur_to_chf: float = 0.9524,
                 home_lat: float = LUGANO_LAT, home_lon: float = LUGANO_LON):
        self.chf_to_eur = chf_to_eur
        self.eur_to_chf = eur_to_chf
        self.home_lat = home_lat
        self.home_lon = home_lon

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

    def _at(self, lat: float, lon: float, region: str, country: str, area: Optional[str] = None) -> Location:
        return Location(lat, lon, self.haversine_km(lat, lon, self.home_lat, self.home_lon), region, country, area)

    def _canton(self, code: str, coords: Optional[Tuple[float, float]] = None) -> Location:
        _aliases, lat, lon, region = SWISS_CANTONS[code]
        if coords:
            lat, lon = coords
        return self._at(lat, lon, region, "CH", code)

    def _province(self, code: str) -> Optional[Location]:
        if code in ITALIAN_PROVINCES:
            _aliases, lat, lon, region = ITALIAN_PROVINCES[code]
            return self._at(lat, lon, region, "IT", code)
        if code in OTHER_PROVINCE_REGIONS:
            region = OTHER_PROVINCE_REGIONS[code]
            _aliases, lat, lon = ITALIAN_REGIONS[region]
            return self._at(lat, lon, region, "IT", code)
        return None

    def resolve(self, location_raw: Optional[str], country_hint: Optional[str] = None) -> Location:
        """Place a listing's free-text location at province/canton level.

        Tried in order, first hit wins: a few precise towns around Lugano;
        a Swiss postcode ("9524 St. Gallen"); an Italian province code
        ("Gravellona Toce (VB)"); a province or canton name, in any of the
        languages portals use ("Zürich", "Ticino", "Bergamo"); an Italian
        region name ("…, Lombardia"); a bare country ("Switzerland").
        country_hint ("CH"/"IT", from the portal) settles codes that exist in
        both countries, e.g. "(GR)" is Grosseto on Subito but Graubünden on
        a Swiss site."""
        if not location_raw or not location_raw.strip():
            return Location(None, None, DISTANCE_NO_LOCATION, "unknown", country_hint)

        text = location_raw.lower().strip()

        for town, (lat, lon) in KNOWN_COORDINATES.items():
            if _has_word(text, town):
                if town in _TICINO_TOWNS:
                    return self._at(lat, lon, "ticino", "CH", "TI")
                return self._at(lat, lon, "piemonte" if town in _PIEMONTE_TOWNS else "lombardia", "IT")

        if country_hint != "IT":
            plz = re.search(r"(?<!\d)([1-9]\d{3})(?!\d)", text)
            if plz and plz.group(1)[:2] in SWISS_PLZ_PREFIX_CANTON:
                prefix = plz.group(1)[:2]
                return self._canton(SWISS_PLZ_PREFIX_CANTON[prefix], TICINO_PLZ_PREFIX_COORDS.get(prefix))

        code_match = re.search(r"\(([a-z]{2})\)", text)
        if code_match:
            code = code_match.group(1).upper()
            if country_hint == "CH" and code in SWISS_CANTONS:
                return self._canton(code)
            province = self._province(code)
            if province:
                return province
            if code in SWISS_CANTONS:
                return self._canton(code)

        # Names: the hinted country's entries first, then the other's.
        for preferred in ((country_hint,) if country_hint else ()) + (None,):
            for alias, country, code in _ALIASES:
                if preferred and country != preferred:
                    continue
                if _has_word(text, alias):
                    return self._canton(code) if country == "CH" else self._province(code)

        for region, (aliases, lat, lon) in ITALIAN_REGIONS.items():
            if any(_has_word(text, alias) for alias in aliases):
                return self._at(lat, lon, region, "IT")

        for country, words in COUNTRY_WORDS.items():
            if any(_has_word(text, word) for word in words):
                return Location(None, None, DISTANCE_UNRESOLVED, "svizzera" if country == "CH" else "italia", country)

        return Location(None, None, DISTANCE_UNRESOLVED, "other", country_hint)

    def resolve_location(self, location_raw: Optional[str],
                         country_hint: Optional[str] = None) -> Tuple[Optional[float], Optional[float], float, str]:
        """(lat, lon, distance_km, region) — see resolve()."""
        return self.resolve(location_raw, country_hint).as_tuple()
