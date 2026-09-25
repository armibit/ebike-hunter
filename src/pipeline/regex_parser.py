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
            "red_flag_details": []
        }

        # Motor detection
        motor_data = self._detect_motor(text)
        if motor_data:
            specs["motor_brand"] = motor_data["brand"]
            specs["motor_model"] = motor_data["model"]
            specs["motor_torque_nm"] = motor_data["torque_nm"]
            specs["motor_verified"] = motor_data["verified"]

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
        # Check disallowed motors first
        weak_motor = self.motors.get("weak_motors_disallowed", {})
        for pattern in weak_motor.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                return None  # Weak motor detected, reject

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

        # Fallback: if text contains e-bike keywords, assume it's an e-bike with unknown
        # motor rather than rejecting it outright — a listing whose description simply
        # doesn't name the motor (common when it's only visible in a photo) shouldn't be
        # filtered out purely because the text is incomplete. torque_nm=60 is a neutral
        # placeholder only to satisfy the min-torque filter; `verified: False` tells the
        # scorer and the human-facing analysis not to treat it as a confirmed spec.
        ebike_keywords = [
            r"\bturbo\b", r"\bhybrid\b", r"\be-bike\b", r"\bebike\b",
            r"\be mtb\b", r"\be-mtb\b", r"\bemtb\b",
            r"electric bike", r"elektrisch", r"elektrisches bike"
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
            r"batteria\s*(\d{3,4})",
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
        # More specific patterns: require odometer-related context words
        patterns = [
            r"(?:percorsi|percorso|chilometri|kilometers?|odometer|km\s+percors)[^\d]*(\d+)",
            r"(\d+)\s*km\s+percors",
            r"chilometri\s*[:\-]?\s*(\d+)",
            r"km\s*[:\-]?\s*(\d+)(?!\s*(?:wh|mm|nm|travel))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                km = int(match.group(1))
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
