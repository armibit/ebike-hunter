import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def price_from_text(text: str) -> float:
    """Asking price written in the ad body ("prezzo € 2450", "Preis: 1'900.-"),
    for listings whose portal price field is empty/0. 0.0 when not found."""
    match = re.search(
        r"\b(?:prezzo|price|preis|prix)\b[^\d\n]{0,15}?(\d{1,2}[.' ]\d{3}|\d{3,5})(?![\d.,]*\s*(?:km|wh|nm|mm))",
        text or "", re.IGNORECASE,
    )
    if match:
        price = float(re.sub(r"\D", "", match.group(1)))
        if 100 <= price <= 20000:
            return price
    return 0.0


# Subito/tutti sellers pad an ad with a trailing SEO keyword dump naming
# dozens of bikes the ad isn't selling: "... orbea rallon, occam, wild, e-mtb,
# emtb, e-bike, ebike, elettrica, carbonio, ... 150mm, 170mm, 180mm.". Parsed
# as if it described the bike for sale, it invents specs out of thin air — a
# muscular Merida One-Twenty became an e-bike off the "e-bike, ebike" in that
# list, and its "150mm, 170mm" made any hardtail full-suspension. The list is
# always a run of comma/newline-separated fragments too short to be prose.
# Commas only, never newlines: a label-per-line spec sheet ("Ammortizzatore\n
# RockShox Deluxe\nSerie Sterzo\n...") is just as fragmented as a keyword dump,
# and it holds the motor/battery this project exists to read.
_SPAM_SEPARATOR = re.compile(r",")
_SPAM_MIN_RUN = 8
_SPAM_MAX_WORDS = 3
# A comma-separated spec sheet ("29”, batteria integrata, travel 160 mm, Boost
# 12x148 mm") looks just as fragmented as a keyword dump, and cutting it throws
# away the real specs. What a dump never has is measurements: a fragment
# carrying a number with a unit, or a "label: value", ends the run.
_SPAM_SPEC_FRAGMENT = re.compile(
    r"""\d\s*(?:mm|cm|kg|wh|nm|v\b|ah|tpi|zoll|pollici|["”']|x\s*\d)|:""", re.IGNORECASE
)


def strip_keyword_spam(text: str) -> str:
    """Cut a trailing SEO keyword list off an ad body, at the start of the
    first run of >= _SPAM_MIN_RUN fragments that are each at most
    _SPAM_MAX_WORDS words long and state no measurement. Text with no such
    run is returned unchanged."""
    if not text:
        return text
    bounds = [m.start() for m in _SPAM_SEPARATOR.finditer(text)]
    run_start, run = None, 0
    for start, end in zip([0] + [b + 1 for b in bounds], bounds + [len(text)]):
        fragment = text[start:end]
        words = fragment.split()
        if not words:
            continue  # ",\n" and friends: separator noise, not a fragment
        if len(words) <= _SPAM_MAX_WORDS and not _SPAM_SPEC_FRAGMENT.search(fragment):
            if run_start is None:
                run_start = start
            run += 1
            if run >= _SPAM_MIN_RUN:
                return text[:run_start].rstrip(" \t\r\n,;.")
        else:
            run_start, run = None, 0
    return text


class RegexParser:
    def __init__(self, taxonomy_path: str):
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            self.taxonomy = json.load(f)
        self.motors = self.taxonomy["motors"]
        self.brakes = self.taxonomy["brakes"]
        self.suspensions = self.taxonomy["suspensions"]
        self.frame_sizes = self.taxonomy["frame_sizes"]
        self.suspension_types = self.taxonomy["suspension_types"]
        self.red_flags = self.taxonomy["red_flags"]
        self.excluded_categories = self.taxonomy["excluded_categories"]
        # alias -> canonical name, longest alias first ("santa cruz" before "santa").
        self.bike_brands = sorted(
            ((alias, name) for name, aliases in self.taxonomy.get("bike_brands", {}).items() for alias in aliases),
            key=lambda pair: -len(pair[0]),
        )

    def parse(self, title: str, description: str) -> Dict[str, Any]:
        # The title is the seller's own words; only the body carries the dump.
        description = strip_keyword_spam(description)
        text = f"{title} {description}".lower()

        # Travel detection early, needed to infer suspension type
        travel_front, travel_rear = self._extract_travel(text)

        specs = {
            "brand": None,
            "model": None,
            "suspension_type": self._detect_suspension_type(text, travel_rear, title),
            "frame_size": self._detect_frame_size(text),
            "motor_brand": None,
            "motor_model": None,
            "motor_torque_nm": None,
            "motor_verified": None,
            "battery_capacity_wh": self._extract_battery_wh(text),
            "travel_front_mm": travel_front,
            "travel_rear_mm": travel_rear,
            "brakes_model": None,
            "brakes_tier": self._detect_brakes_tier(text),
            "fork_tier": self._detect_fork_tier(text),
            "odometer_km": self._extract_odometer(text),
            "gears": self._extract_gears(text),
            "model_year": self._extract_year(text),
            "has_red_flag": False,
            "red_flag_details": [],
            "excluded_category": self._detect_excluded_category(text)
        }
        if specs["frame_size"] == "disallowed":
            # The size actually written ("XL", "taglia L", "52 cm") — only
            # for the reject reason; frame_size itself stays the marker.
            specs["frame_size_detected"] = self._disallowed_size_text(text)

        # Motor detection
        motor_data = self._detect_motor(text)
        if motor_data:
            specs["motor_brand"] = motor_data["brand"]
            specs["motor_model"] = motor_data["model"]
            specs["motor_torque_nm"] = motor_data["torque_nm"]
            specs["motor_verified"] = motor_data["verified"]
            # Gen4 (85Nm) arrived with MY2020: a generic "Bosch CX" on an
            # older bike is the 75Nm Gen2/3, unless 85Nm/Gen4 is stated.
            if (
                specs["motor_model"] == "Performance Line CX Gen4"
                and specs["model_year"] is not None
                and specs["model_year"] <= 2019
                and not re.search(r"gen\s?4|85\s*nm", text)
            ):
                specs["motor_model"] = "Performance Line CX Gen2/3"
                specs["motor_torque_nm"] = 75
        elif specs["battery_capacity_wh"] is not None:
            # No motor brand/keyword named anywhere in the text, but a
            # battery Wh figure was extracted — no muscular bike specs a
            # battery capacity, so this is unambiguous e-bike evidence even
            # without the word "motor". Common in structured spec-sheet
            # listings (e.g. tcs_velocorner) that print "Battery capacity:
            # 950Wh" but never name the motor.
            specs["motor_brand"] = "Unknown Motor"
            specs["motor_model"] = "Not specified"
            specs["motor_torque_nm"] = 60
            specs["motor_verified"] = False

        # Brand & Model extraction (basic heuristics)
        brand_model = self._extract_brand_model(title) or self._extract_brand_model(description)
        if brand_model:
            specs["brand"], specs["model"] = brand_model

        # Red flags detection
        red_flag_matches = self._detect_red_flags(text)
        if red_flag_matches:
            specs["has_red_flag"] = True
            specs["red_flag_details"] = red_flag_matches

        return specs

    def _detect_motor(self, text: str) -> Optional[Dict[str, Any]]:
        # Check disallowed motors first. Return the actual (low) torque_nm
        # instead of None so run.py's reject reason reads "Weak motor (50nm
        # < 60nm)" rather than the misleading "No motor detected" — a Fazua/
        # TQ/etc. motor was found, it's just below the buyer's power floor.
        weak_motor = self.motors.get("weak_motors_disallowed", {})
        for pattern in weak_motor.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    "brand": weak_motor["brand"],
                    "model": weak_motor["model"],
                    "torque_nm": weak_motor["torque_nm"],
                    "verified": True
                }

        # Check top-tier motors
        for motor_key, motor_data in self.motors.items():
            if motor_key == "weak_motors_disallowed":
                continue
            for pattern in motor_data.get("patterns", []):
                if re.search(pattern, text, re.IGNORECASE):
                    return {
                        "brand": motor_data["brand"],
                        "model": motor_data["model"],
                        "torque_nm": motor_data["torque_nm"],
                        "verified": True
                    }

        # Fallback: no known brand/model matched, but the text states an explicit
        # torque number anyway — common for budget/generic-motor brands that aren't
        # (and can't realistically all be) in taxonomy.json's curated motor list, e.g.
        # "Maximum Torque 65 N·m" on a Lankeleisi listing. This is a real value read
        # off the text, not a guess, so — unlike the generic e-bike-keyword fallback
        # below — it's marked verified.
        torque_match = re.search(r"\b(\d{2,3})\s*n[\s.·]?m\b", text, re.IGNORECASE)
        if torque_match:
            torque = int(torque_match.group(1))
            if 20 <= torque <= 160:
                return {
                    "brand": "Unknown Motor",
                    "model": "Not specified",
                    "torque_nm": torque,
                    "verified": True
                }

        # Fallback: if text contains e-bike keywords, assume it's an e-bike with unknown
        # motor rather than rejecting it outright — a listing whose description simply
        # doesn't name the motor (common when it's only visible in a photo) shouldn't be
        # filtered out purely because the text is incomplete. torque_nm=60 is a neutral
        # placeholder only to satisfy the min-torque filter; `verified: False` tells the
        # scorer and the human-facing analysis not to treat it as a confirmed spec.
        ebike_keywords = [
            r"\bturbo\b", r"\bhybrid\b", r"\be-bike\b", r"\bebike\b",
            r"\be mtb\b", r"\be-mtb\b", r"\bemtb\b",
            r"electric bike", r"elektrisch", r"elektrisches bike",
            r"e-mountainbike", r"e-mountain-bike", r"elektrofahrrad", r"pedelec",
            # Scott appends "eRIDE" only to its electric model variants
            # (Spark eRIDE, Lumen eRIDE, Genius eRIDE, ...) — never used on
            # an analog bike, so it's unambiguous e-bike evidence on its own.
            r"\beride\b", r"\belettric[ao]\b"
        ]
        for keyword in ebike_keywords:
            if re.search(keyword, text, re.IGNORECASE):
                return {
                    "brand": "Unknown Motor",
                    "model": "Not specified",
                    "torque_nm": 60,  # Minimum acceptable torque
                    "verified": False
                }

        return None

    def _extract_battery_wh(self, text: str) -> Optional[int]:
        # The labelled forms allow a ":"/"-" separator: sellers write
        # "batteria : 750w" as often as "batteria 750wh".
        patterns = [
            r"(\d{3,4})\s*wh",
            r"batteria\s*[:\-]?\s*(?:da|di)?\s*(\d{3,4})",
            r"akku\s*[:\-]?\s*(\d{3,4})",
            r"battery\s*[:\-]?\s*(\d{3,4})"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                wh = int(match.group(1))
                if 250 <= wh <= 1000:
                    return wh
        return None

    def _detect_suspension_type(self, text: str, travel_rear: Optional[int] = None, title: str = "") -> str:
        # If rear travel >= 50mm, it's definitively a full suspension
        if travel_rear is not None and travel_rear >= 50:
            return "full_suspension"

        # Check hardtail keywords
        for kw in self.suspension_types["hardtail_disallowed"]:
            if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
                return "hardtail"

        # Check full suspension keywords
        for kw in self.suspension_types["full_keywords"]:
            if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
                return "full_suspension"

        # Model lines that are hardtail by design (Haibike/Moustache "Trekking"):
        # title only, and only when nothing above said full suspension.
        for kw in self.suspension_types.get("hardtail_title_hints", []):
            if re.search(rf"\b{kw}\b", title, re.IGNORECASE):
                return "hardtail"

        return "unknown"

    def _detect_excluded_category(self, text: str) -> Optional[str]:
        for kw in self.excluded_categories:
            for match in re.finditer(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
                # "lucchetto Abus pieghevole", "folding lock": an accessory
                # that folds, not a folding bike.
                if self._FOLDING_ACCESSORY_CONTEXT.search(text[max(0, match.start() - 25):match.start()]):
                    continue
                return kw
        return None

    _FOLDING_ACCESSORY_CONTEXT = re.compile(
        r"lucchett|antifurto|lock|schloss|cadenas|pedal|cavallett|specchi", re.IGNORECASE
    )

    # Yamaha's motor series is literally named "PW-S2"/"PW-S3" (see
    # taxonomy.json's yamaha_pwx patterns), e.g. Upway's spec table prints
    # "Modell: PW-Series S2". A bare `\bs2\b` scan over the whole text
    # mistakes that motor name for Specialized's S1-S6 frame-size token,
    # so a match near this motor-naming context is excluded.
    _FRAME_S23_EXCLUSION_CONTEXT = re.compile(
        r"pw[-\s]|yamaha|series|motor|antrieb", re.IGNORECASE
    )

    def _frame_size_token_present(self, text: str, token: str) -> bool:
        for match in re.finditer(rf"\b{token}\b", text, re.IGNORECASE):
            context = text[max(0, match.start() - 20):match.start()]
            if self._FRAME_S23_EXCLUSION_CONTEXT.search(context):
                continue
            return True
        return False

    # A labelled size field ("Frame size Small" on velocorner, "Rahmengrösse
    # M", "Taglia telaio: L") beats loose words elsewhere in the text.
    _SIZE_TOKEN = r"(?:extra[\s-]?small|extra[\s-]?large|small|medium|large|xx?s|xx?l|s[1-6]|[sml])"
    _LABELLED_SIZE = re.compile(
        r"\b(?:frame\s*size|rahmengr(?:ö|oe)(?:ss|ß)e|taglia\s+telaio|taille\s+(?:du\s+)?cadre)\s*[:\-]?\s*"
        rf"({_SIZE_TOKEN}(?:\s*(?:[-/,]|oder|or|o|und|e)\s*{_SIZE_TOKEN})*)\b",
        re.IGNORECASE,
    )
    _SIZE_WORDS = {"small": "S", "medium": "M", "large": "L", "extrasmall": "XS", "extralarge": "XL"}

    def _labelled_size(self, text: str) -> Optional[str]:
        """Size from a labelled field; a range or list ("S-M", "S, M oder
        L") that includes a fitting size counts as that size."""
        match = self._LABELLED_SIZE.search(text)
        if not match:
            return None
        sizes = [
            self._SIZE_WORDS.get(re.sub(r"[\s-]", "", token.lower()), token.upper())
            for token in re.findall(self._SIZE_TOKEN, match.group(1), re.IGNORECASE)
        ]
        return next((size for size in sizes if size in ("M", "S2", "S3")), sizes[0])

    def _detect_frame_size(self, text: str) -> str:
        labelled = self._labelled_size(text)
        if labelled:
            return labelled if labelled in ("M", "S2", "S3") else "disallowed"

        # Check target sizes
        for pattern in self.frame_sizes["target_m"]:
            if re.search(pattern, text, re.IGNORECASE):
                # Normalize to M
                if self._frame_size_token_present(text, "s2"):
                    return "S2"
                if self._frame_size_token_present(text, "s3"):
                    return "S3"
                return "M"

        # Check disallowed sizes
        if self._disallowed_size_text(text):
            return "disallowed"

        return "unknown"

    def _disallowed_size_text(self, text: str) -> Optional[str]:
        labelled = self._labelled_size(text)
        if labelled:
            return labelled
        for pattern in self.frame_sizes["disallowed_sizes"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip("() ").upper()
        return None

    # Bare-number travel pattern (no "mm"/"escursione"/"federweg" anchor) — needs
    # its own handling below since it also matches dropper-post/seatpost travel
    # (e.g. "dropper post 150mm") which isn't suspension travel at all.
    _JOLLY_TRAVEL_PATTERN = r"\b(1[23456]\d)\b"
    _TRAVEL_EXCLUSION_CONTEXT = re.compile(
        r"dropper|reggisella|seatpost|sella telescopica|vario", re.IGNORECASE
    )

    def _extract_travel(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        # Extract all travel mentions
        travel_values = []
        for pattern in self.suspensions["travel_patterns"]:
            if pattern == self._JOLLY_TRAVEL_PATTERN:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    context = text[max(0, match.start() - 25):match.end() + 15]
                    if self._TRAVEL_EXCLUSION_CONTEXT.search(context):
                        continue
                    val = int(match.group(1))
                    if 80 <= val <= 300:
                        travel_values.append(val)
                continue
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                val = int(match)
                if 80 <= val <= 300:
                    travel_values.append(val)

        # De-duplicate: if we extracted identical values, it's likely the same spec
        # mentioned twice (e.g., "fork 100mm" in title and description).
        # Treat as single fork (hardtail), not dual suspension.
        if len(travel_values) >= 2 and len(set(travel_values)) == 1:
            return travel_values[0], None

        if len(travel_values) >= 2:
            return travel_values[0], travel_values[1]
        elif len(travel_values) == 1:
            # Single travel value likely means only front fork (hardtail).
            # Don't assume it's both front and rear — return None for rear
            # to avoid misclassifying hardtails as full suspension.
            return travel_values[0], None
        return None, None

    def _detect_brakes_tier(self, text: str) -> str:
        for pattern in self.brakes["four_piston_top"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "four_piston"

        for pattern in self.brakes["two_piston_penalized"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "two_piston"

        return "unknown"

    def _detect_fork_tier(self, text: str) -> str:
        for pattern in self.suspensions["high_tier_forks"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "high"

        for pattern in self.suspensions["mid_tier_forks"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "mid"

        for pattern in self.suspensions["entry_forks"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "entry"

        return "unknown"

    # "12 speed", "12v", "12s", "12 rapporti", "12-fach", "1x12". "12v" is also
    # a battery-voltage spelling, but no e-bike has 12 V — and the count is
    # bounded to real drivetrains (7-13) so "24s"/"36v" never match.
    _GEARS_RE = re.compile(
        r"\b(\d{1,2})\s*-?\s*(?:speeds?|rapporti|velocit[àa]|gang|gänge|fach|vitesses|v|s)\b"
        r"|\b1\s*x\s*(\d{1,2})\b"
    )

    def _extract_gears(self, text: str) -> Optional[int]:
        for match in self._GEARS_RE.finditer(text):
            gears = int(match.group(1) or match.group(2))
            if 7 <= gears <= 13:
                return gears
        return None

    def _extract_odometer(self, text: str) -> Optional[int]:
        # Number capture that also accepts a European thousands-separator
        # dot (e.g. "1.443" meaning 1443), so it isn't truncated at the dot
        # like plain \d+ would ("1.443" -> "1"). Requires full 3-digit
        # groups after each dot, so it won't misfire on a decimal point.
        NUM = r"\d{1,3}(?:\.\d{3})+|\d+"
        # More specific patterns: require odometer-related context words.
        # The gap after/before the keyword is capped at 30 non-digit,
        # non-newline characters so it can't jump across sentences or
        # paragraphs to grab an unrelated number (e.g. a frame material
        # code like "C:62" mentioned much later in the text).
        patterns = [
            rf"(?:percorsi|percorso|chilometri|kilometers?|odometer|km\s+percors)[^\d\n]{{0,30}}({NUM})",
            rf"({NUM})\s*km[^\d\n]{{0,30}}percors",
            rf"chilometri\s*[:\-]?\s*({NUM})",
            rf"chilometraggio\s*[:\-]?\s*({NUM})",
            # "Km totali: 1241" / "Km totale: 1241" — a field-label phrasing
            # ("<unit> totali: <value>") distinct from the generic km-value
            # fallback below, which the word "totali" between "km" and the
            # number would otherwise defeat.
            rf"km\s*total[ei]\s*[:\-]?\s*({NUM})",
            rf"total[ei]\s*km\s*[:\-]?\s*({NUM})",
            # "ha all'attivo 2.300 km"
            rf"attivo[^\d\n]{{0,15}}({NUM})\s*km",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                km = int(match.group(1).replace(".", ""))
                if 0 <= km <= 20000:
                    return km

        # Generic "km: 120" fallback — most permissive pattern, so it's the one
        # most likely to misfire on "autonomia fino a 120 km" (battery range,
        # not distance ridden). Reject a match whose nearby context names
        # range/battery instead of distance.
        range_context = re.compile(
            r"autonomia|range|batteria|akku|battery|autonomy", re.IGNORECASE
        )
        generic_pattern = rf"km\s*[:\-]?\s*({NUM})(?!\s*(?:wh|mm|nm|travel))"
        for match in re.finditer(generic_pattern, text, re.IGNORECASE):
            context = text[max(0, match.start() - 30):match.end() + 10]
            if range_context.search(context):
                continue
            km = int(match.group(1).replace(".", ""))
            if 0 <= km <= 20000:
                return km
        return None

    def _extract_year(self, text: str) -> Optional[int]:
        # A labelled year ("Anno: 2017", "Modelljahr 2019") wins over the
        # first bare 20xx, which may be a service/purchase date instead.
        max_year = date.today().year + 1
        labelled = re.search(
            r"\b(?:anno|year|jahrgang|modelljahr|baujahr|mj|my)\s*[:\-]?\s*(20\d{2})\b", text
        )
        candidates = [labelled] if labelled else []
        candidates += re.finditer(r"\b(20\d{2})\b", text)
        for match in candidates:
            year = int(match.group(1))
            if 2010 <= year <= max_year:
                return year
        return None

    # Words that can follow a brand alias in ordinary prose but never start a
    # model name. Several aliases are also everyday words ("focus", "giant",
    # "ghost", "rose"), and the description fallback below scans a whole
    # marketing body: buybestgear's Vakole EMT29 text reads "known for EU
    # warehousing and e-mobility focus. The EMT29 12s ...", which made that
    # (and every other page carrying the blurb) a Focus.
    _PROSE_STOPWORDS = frozenset("""
        the a an and or of on in for to with at by from as is was are has have be been
        this that these those its it their our also can will very more most
        il lo la le gli un una uno e di da per con su che non ha sono come del della al alla
        der die das und ist mit für auf zu ein eine den dem im von sind hat als auch sehr
        les du pour avec sur est
    """.split())

    def _is_brand_mention(self, text: str, end: int) -> bool:
        """True when what follows an alias match looks like a model name (or
        nothing), i.e. the alias is used as a brand and not as a plain word."""
        rest = text[end:]
        if not rest.strip(" \t\r\n.,;:!?-–—/|()[]\"'"):
            return True  # brand is the last meaningful word ("Vendo MTB Cube.")
        if rest[0] in ".,;:!?":
            return False  # ends a sentence mid-text -> prose, not "Brand Model"
        word = re.match(r"[^a-z0-9]*([a-z0-9][a-z0-9\-\.]*)", rest)
        return word is None or word.group(1) not in self._PROSE_STOPWORDS

    def _extract_brand_model(self, title: str) -> Optional[Tuple[str, str]]:
        """Frame brand named earliest in the text, plus up to 3 following
        words as the model. Whole words only: "TREKKING" is not Trek."""
        title_lower = (title or "").lower()
        best = None
        for alias, name in self.bike_brands:
            for match in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", title_lower):
                if not self._is_brand_mention(title_lower, match.end()):
                    continue
                if best is None or match.start() < best[0].start():
                    best = (match, name)
                break
        if not best:
            return None
        match, name = best
        model = " ".join(re.findall(r"[a-z0-9\-\.]+", title_lower[match.end():])[:3])
        return name, model.title()

    def _detect_red_flags(self, text: str) -> List[str]:
        matches = []
        for flag in self.red_flags:
            if re.search(flag, text, re.IGNORECASE):
                matches.append(flag)
        return matches
