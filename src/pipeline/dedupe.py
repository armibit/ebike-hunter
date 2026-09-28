"""Cross-portal duplicate detection.

The same bike often shows up twice: a shop posting on Tutti.ch and on its
own site, or a private seller on both Tutti and Velomarkt, or a seller
re-listing under a new id. Two listings count as the same bike when their
titles carry the same significant words (order and filler words ignored)
and their CHF prices fall in the same 50-CHF bucket.

Deliberately conservative: a duplicate is only *flagged* in the dashboard
("anche su …"), never merged or hidden, so a false match costs nothing.
"""
import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

PRICE_BUCKET_CHF = 50

# Words every e-MTB ad title uses — they carry no identity.
_FILLER_WORDS = {
    "vendo", "vendesi", "bici", "bicicletta", "ebike", "bike", "emtb", "mtb",
    "elettrica", "usata", "usato", "come", "nuova", "nuovo", "taglia", "tg",
    "full", "fully", "biammortizzata", "occasione", "occasion", "gebraucht",
    "di", "da", "con", "in", "e", "the", "and", "mit", "und",
}


def dedupe_signature(title: Optional[str], price_chf: Optional[float]) -> str:
    """Stable key for "probably the same bike" — empty when the title has no
    identifying words or the price is unknown (never grouped then)."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower().replace("e-bike", "ebike"))
    significant = sorted({w for w in words if len(w) >= 2 and w not in _FILLER_WORDS})
    if not significant or not price_chf or price_chf <= 0:
        return ""
    bucket = int(round(price_chf / PRICE_BUCKET_CHF))
    key = " ".join(significant) + f"|{bucket}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def find_duplicates(listings: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Map listing id -> the *other* listings sharing its signature.

    Each listing dict needs id, portal and dedupe_signature; REJECTED/SOLD/
    DELISTED ones are ignored, since pointing at a dead copy helps nobody."""
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for listing in listings:
        signature = listing.get("dedupe_signature")
        if signature and listing.get("status") not in ("REJECTED", "SOLD", "DELISTED"):
            groups[signature].append(listing)

    duplicates: Dict[str, List[Dict[str, Any]]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        for listing in members:
            duplicates[listing["id"]] = [other for other in members if other["id"] != listing["id"]]
    return duplicates
