"""Duplicate detection: the same bike listed twice.

It happens three ways: a shop posting on Tutti.ch *and* its own site, a
private seller on two portals (Tutti + Velomarkt, Subito + Ridewill), or a
seller re-listing the same ad under a new id. Titles are never identical
("Cube Stereo Hybrid 140 625 tg M" vs "CUBE Stereo Hybrid 140 HPC Race
2022"), prices move by a few %, and one portal may know the battery while
the other doesn't — so an exact key misses most real pairs.

Instead every pair of live listings that shares title words is scored:

  * title similarity  — overlap of the significant words (brand, model,
                        numbers; filler like "vendo", "ebike" ignored);
  * price             — within PRICE_TOLERANCE of each other (in CHF);
  * specs as vetoes   — frame size, battery Wh, model year, motor brand:
                        if BOTH listings know a value and they differ, it's
                        a different bike, whatever the title says;
  * specs as support  — each value both listings know and agree on lowers
                        the title-similarity bar;
  * place as a veto   — two located private listings far apart are two bikes.

Pairs that match are merged into groups (a bike on three portals is one
group). A duplicate is only *flagged* in the dashboard ("🔁 anche su …"),
never merged or hidden, so a rare false match costs nothing.
"""
import hashlib
import math
import re
from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Set

PRICE_BUCKET_CHF = 50
PRICE_TOLERANCE = 0.08          # 8 %: a small haggle-room edit or CHF/EUR rounding
TITLE_SIMILARITY_ALONE = 0.6    # enough on its own (with a matching price)
TITLE_SIMILARITY_MIN = 0.34     # the floor, when specs agree
MAX_APART_KM = 60               # two located listings farther apart: different bikes

# Words every e-MTB ad title uses — they carry no identity.
_FILLER_WORDS = {
    "vendo", "vendesi", "bici", "bicicletta", "ebike", "bike", "emtb", "mtb",
    "elettrica", "usata", "usato", "come", "nuova", "nuovo", "taglia", "tg",
    "full", "fully", "biammortizzata", "occasione", "occasion", "gebraucht",
    "di", "da", "con", "in", "e", "the", "and", "mit", "und", "size", "grösse",
    "perfetta", "perfette", "condizioni", "ottime", "ottimo", "stato", "top",
    "ebikes", "mountainbike", "mountain", "elektro", "vtt", "electric",
}

_LIVE_STATUSES = {"ACTIVE", "PRICE_DROP", "NEW"}


def title_tokens(title: Optional[str]) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", (title or "").lower().replace("e-bike", "ebike"))
    return {w for w in words if len(w) >= 2 and w not in _FILLER_WORDS}


def dedupe_signature(title: Optional[str], price_chf: Optional[float]) -> str:
    """Coarse stored key (listings.dedupe_signature): same significant title
    words + same 50-CHF price bucket. Handy for SQL lookups; the dashboard
    uses find_duplicates(), which also catches reworded titles."""
    significant = sorted(title_tokens(title))
    if not significant or not price_chf or price_chf <= 0:
        return ""
    bucket = int(round(price_chf / PRICE_BUCKET_CHF))
    key = " ".join(significant) + f"|{bucket}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _norm_size(value: Any) -> Optional[str]:
    text = "".join(str(value or "").split()).upper()
    return None if text in ("", "UNKNOWN", "DISALLOWED", "NONE") else text


def _known(value: Any) -> bool:
    return value not in (None, "", "unknown")


def _km_apart(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[float]:
    if None in (a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude")):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def is_same_bike(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Pairwise verdict — see the module docstring for the rules."""
    tokens_a, tokens_b = a.get("_tokens") or title_tokens(a.get("title")), b.get("_tokens") or title_tokens(b.get("title"))
    if not tokens_a or not tokens_b:
        return False
    similarity = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    if similarity < TITLE_SIMILARITY_MIN:
        return False

    price_a, price_b = a.get("price_chf") or 0, b.get("price_chf") or 0
    if price_a <= 0 or price_b <= 0 or abs(price_a - price_b) / max(price_a, price_b) > PRICE_TOLERANCE:
        return False

    agreements = 0
    size_a, size_b = _norm_size(a.get("frame_size")), _norm_size(b.get("frame_size"))
    if size_a and size_b:
        if size_a != size_b:
            return False
        agreements += 1
    for field, tolerance in (("battery_capacity_wh", 10), ("model_year", 0)):
        if _known(a.get(field)) and _known(b.get(field)):
            if abs(float(a[field]) - float(b[field])) > tolerance:
                return False
            agreements += 1
    brand_a, brand_b = (a.get("motor_brand") or "").lower(), (b.get("motor_brand") or "").lower()
    if brand_a and brand_b and "unknown" not in (brand_a, brand_b):
        if brand_a != brand_b:
            return False
        agreements += 1

    apart = _km_apart(a, b)
    if apart is not None and apart > MAX_APART_KM:
        return False

    # Each agreeing spec lowers the title bar from "alone" towards the floor.
    required = max(TITLE_SIMILARITY_MIN, TITLE_SIMILARITY_ALONE - 0.1 * agreements)
    return similarity >= required


def find_duplicates(listings: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Map listing id -> the *other* live listings judged to be the same bike.

    Listings need id, portal, title, price_chf, status; frame_size,
    battery_capacity_wh, model_year, motor_brand, latitude/longitude are
    used when present. REJECTED/SOLD/DELISTED ones are ignored — pointing at
    a dead copy helps nobody. Pairs are only compared when they share a
    title word (an inverted index), so this stays fast on thousands of rows."""
    live = [dict(l, _tokens=title_tokens(l.get("title"))) for l in listings if l.get("status") in _LIVE_STATUSES]
    by_token: Dict[str, List[int]] = defaultdict(list)
    for index, listing in enumerate(live):
        for token in listing["_tokens"]:
            if not token.isdigit():  # "2022" or "625" alone would pair half the list
                by_token[token].append(index)

    parent = list(range(len(live)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    compared = set()
    for indexes in by_token.values():
        if len(indexes) > 400:
            continue  # a token that common ("cube") is compared via rarer ones
        for i, j in combinations(indexes, 2):
            if (i, j) in compared:
                continue
            compared.add((i, j))
            if is_same_bike(live[i], live[j]):
                parent[root(i)] = root(j)

    groups: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for index, listing in enumerate(live):
        groups[root(index)].append(listing)

    duplicates: Dict[str, List[Dict[str, Any]]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        clean = [{k: v for k, v in m.items() if k != "_tokens"} for m in members]
        for listing in clean:
            duplicates[listing["id"]] = [other for other in clean if other["id"] != listing["id"]]
    return duplicates


def collapse_identical_units(listings: List[Dict[str, Any]]):
    """Shops like Upway list every refurbished unit of a model as its own
    product (haibike-trekking-4-rk5ff1, -rk5ff6, …): same title, size, year
    and price. Not duplicates — distinct bikes — but N identical rows bury
    the list. Keep the first live one (input is ranked, so the best) and
    return {kept id: [the other units]}; non-live rows are never grouped."""
    kept: List[Dict[str, Any]] = []
    units: Dict[str, List[Dict[str, Any]]] = {}
    first_by_key: Dict[tuple, str] = {}
    for listing in listings:
        if listing.get("status") in _LIVE_STATUSES:
            key = (
                listing.get("portal"),
                " ".join((listing.get("title") or "").lower().split()),
                _norm_size(listing.get("frame_size")),
                listing.get("model_year"),
                round(listing.get("price_chf") or 0),
            )
            if key in first_by_key:
                units[first_by_key[key]].append(listing)
                continue
            first_by_key[key] = listing["id"]
            units[listing["id"]] = []
        kept.append(listing)
    return kept, {k: v for k, v in units.items() if v}
