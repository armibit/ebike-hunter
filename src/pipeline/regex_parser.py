import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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

    def parse(self, title: str, description: str) -> Dict[str, Any]:
        text = f"{title} {description}".lower()

        specs = {
            "brand": None,
            "model": None,
            "suspension_type": self._detect_suspension_type(text),
            "frame_size": self._detect_frame_size(text),
            "motor_brand": None,
            "motor_model": None,
            "motor_torque_nm": None,
            "motor_verified": None,
            "battery_capacity_wh": self._extract_battery_wh(text),
            "travel_front_mm": None,
            "travel_rear_mm": None,
            "brakes_model": None,
            "brakes_tier": self._detect_brakes_tier(text),
            "fork_tier": self._detect_fork_tier(text),
            "odometer_km": self._extract_odometer(text),
            "model_year": self._extract_year(text),
            "has_red_flag": False,
            "red_flag_details": [],
            "excluded_category": self._detect_excluded_category(text)
        }

        # Motor detection
        motor_data = self._detect_motor(text)
        if motor_data:
            specs["motor_brand"] = motor_data["brand"]
            specs["motor_model"] = motor_data["model"]
            specs["motor_torque_nm"] = motor_data["torque_nm"]
            specs["motor_verified"] = motor_data["verified"]
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

        # Travel detection
        travel_front, travel_rear = self._extract_travel(text)
        specs["travel_front_mm"] = travel_front
        specs["travel_rear_mm"] = travel_rear

        # Brand & Model extraction (basic heuristics)
        brand_model = self._extract_brand_model(title)
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
        patterns = [
            r"(\d{3,4})\s*wh",
            r"batteria\s*(?:da|di)?\s*(\d{3,4})",
            r"akku\s*(\d{3,4})",
            r"battery\s*(\d{3,4})"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                wh = int(match.group(1))
                if 250 <= wh <= 1000:
                    return wh
        return None

    def _detect_suspension_type(self, text: str) -> str:
        # Check hardtail disallowed first
        for kw in self.suspension_types["hardtail_disallowed"]:
            if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
                return "hardtail"

        # Check full suspension keywords
        for kw in self.suspension_types["full_keywords"]:
            if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
                return "full_suspension"

        return "unknown"

    def _detect_excluded_category(self, text: str) -> Optional[str]:
        for kw in self.excluded_categories:
            if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
                return kw
        return None

    def _detect_frame_size(self, text: str) -> str:
        # Check target sizes
        for pattern in self.frame_sizes["target_m"]:
            if re.search(pattern, text, re.IGNORECASE):
                # Normalize to M
                if re.search(r"\bs2\b", text, re.IGNORECASE):
                    return "S2"
                if re.search(r"\bs3\b", text, re.IGNORECASE):
                    return "S3"
                return "M"

        # Check disallowed sizes
        for pattern in self.frame_sizes["disallowed_sizes"]:
            if re.search(pattern, text, re.IGNORECASE):
                return "disallowed"

        return "unknown"

    def _extract_travel(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        # Extract all travel mentions
        travel_values = []
        for pattern in self.suspensions["travel_patterns"]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                val = int(match)
                if 100 <= val <= 200:
                    travel_values.append(val)

        if len(travel_values) >= 2:
            return travel_values[0], travel_values[1]
        elif len(travel_values) == 1:
            return travel_values[0], travel_values[0]
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
            rf"km\s*[:\-]?\s*({NUM})(?!\s*(?:wh|mm|nm|travel))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                km = int(match.group(1).replace(".", ""))
                if 0 <= km <= 20000:
                    return km
        return None

    def _extract_year(self, text: str) -> Optional[int]:
        match = re.search(r"\b(20\d{2})\b", text)
        if match:
            year = int(match.group(1))
            if 2018 <= year <= 2026:
                return year
        return None

    def _extract_brand_model(self, title: str) -> Optional[Tuple[str, str]]:
        title_lower = title.lower()
        brands = ["specialized", "trek", "cube", "canyon", "focus", "scott", "giant", "merida", "mondraker", "orbea", "santa cruz", "rocky mountain"]

        for brand in brands:
            if brand in title_lower:
                # Extract model (simple heuristic: words after brand)
                match = re.search(rf"{brand}\s+([a-z0-9\s\-]+)", title_lower, re.IGNORECASE)
                if match:
                    model_raw = match.group(1).strip()
                    model = " ".join(model_raw.split()[:3])  # Take first 3 words
                    return brand.title(), model.title()
        return None

    def _detect_red_flags(self, text: str) -> List[str]:
        matches = []
        for flag in self.red_flags:
            if re.search(flag, text, re.IGNORECASE):
                matches.append(flag)
        return matches
