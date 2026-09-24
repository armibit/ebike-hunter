from typing import Dict, Any


class ScoringEngine:
    def __init__(self, config: Dict[str, Any]):
        self.weights = config.get("scoring_weights", {
            "price_value": 0.35,
            "component_quality": 0.25,
            "condition_mileage": 0.15,
            "location_proximity": 0.15,
            "fit_geometry": 0.10
        })
        try:
            self.budget = config["buyer_profile"]["budget"]
            self.target_price = self.budget["target_price"]
            self.hard_max_price = self.budget["hard_max_price"]
        except KeyError as e:
            raise ValueError(f"Config missing required key: {e}") from e

    def calculate_score(self, listing: Dict[str, Any], specs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate 0-100 score for listing.
        Returns score breakdown.
        """
        price_chf = listing.get("price_chf", 9999)
        distance_km = listing.get("distance_km", 999)

        # Individual scores
        score_price = self._score_price(price_chf)
        score_components = self._score_components(specs)
        score_condition = self._score_condition(specs)
        score_location = self._score_location(distance_km)
        score_fit = self._score_fit(specs)

        # Weighted total
        score_total = (
            self.weights["price_value"] * score_price +
            self.weights["component_quality"] * score_components +
            self.weights["condition_mileage"] * score_condition +
            self.weights["location_proximity"] * score_location +
            self.weights["fit_geometry"] * score_fit
        )

        is_deal_target = score_total >= 75.0 and price_chf <= self.hard_max_price

        return {
            "score_total": round(score_total, 1),
            "score_price_value": round(score_price, 1),
            "score_component_quality": round(score_components, 1),
            "score_condition_mileage": round(score_condition, 1),
            "score_location_proximity": round(score_location, 1),
            "score_fit_geometry": round(score_fit, 1),
            "is_deal_target": is_deal_target,
            "breakdown": {
                "price_chf": price_chf,
                "distance_km": distance_km,
                "motor": specs.get("motor_model"),
                "battery_wh": specs.get("battery_capacity_wh"),
                "frame_size": specs.get("frame_size"),
                "travel_mm": specs.get("travel_front_mm"),
                "brakes": specs.get("brakes_tier"),
                "fork": specs.get("fork_tier"),
                "odometer_km": specs.get("odometer_km"),
                "year": specs.get("model_year")
            }
        }

    def _score_price(self, price_chf: float) -> float:
        """
        Score based on price vs target budget.
        <= 1800 CHF = 100
        1800-3000 CHF = decay curve
        > 3000 CHF = 0
        """
        if price_chf <= 1800:
            return 100.0
        elif price_chf > self.hard_max_price:
            return 0.0
        else:
            # Decay curve
            ratio = (price_chf - 1800) / (self.hard_max_price - 1800)
            return max(0, 100.0 * (1 - ratio ** 0.85))

    def _score_components(self, specs: Dict[str, Any]) -> float:
        """
        Score based on motor, battery, brakes, fork quality.
        """
        score = 0.0

        # Battery (max 40 points)
        battery_wh = specs.get("battery_capacity_wh") or 0
        if battery_wh >= 750:
            score += 40
        elif battery_wh >= 700:
            score += 36
        elif battery_wh >= 625:
            score += 30
        elif battery_wh >= 500:
            score += 20
        else:
            score += 0

        # Motor (max 30 points)
        motor_nm = specs.get("motor_torque_nm") or 0
        if motor_nm >= 90:
            score += 30
        elif motor_nm >= 85:
            score += 28
        elif motor_nm >= 75:
            score += 22
        elif motor_nm >= 65:
            score += 18
        elif motor_nm >= 60:
            score += 15
        else:
            score += 0

        # Brakes (max 15 points)
        brakes_tier = specs.get("brakes_tier", "unknown")
        if brakes_tier == "four_piston":
            score += 15
        elif brakes_tier == "two_piston":
            score += 5

        # Fork tier (max 15 points)
        fork_tier = specs.get("fork_tier", "unknown")
        if fork_tier == "high":
            score += 15
        elif fork_tier == "mid":
            score += 10
        elif fork_tier == "entry":
            score += 5

        return min(100.0, score)

    def _score_condition(self, specs: Dict[str, Any]) -> float:
        """
        Score based on odometer km and model year.
        """
        odometer_km = specs.get("odometer_km")
        model_year = specs.get("model_year")

        if odometer_km is not None:
            if odometer_km <= 500:
                return 100.0
            elif odometer_km <= 2500:
                return 100.0 - ((odometer_km - 500) / 2000) * 40
            elif odometer_km <= 4000:
                return 60.0 - ((odometer_km - 2500) / 1500) * 30
            else:
                return 30.0
        elif model_year is not None:
            # Fallback to year-based scoring
            if model_year >= 2024:
                return 95.0
            elif model_year == 2023:
                return 85.0
            elif model_year == 2022:
                return 75.0
            elif model_year == 2021:
                return 60.0
            else:
                return 45.0
        else:
            return 50.0  # Neutral if unknown

    def _score_location(self, distance_km: float) -> float:
        """
        Score based on distance from Lugano.
        <= 20 km = 100
        20-50 km = 85
        50-100 km = 60
        > 100 km = 20
        """
        if distance_km <= 20:
            return 100.0
        elif distance_km <= 50:
            return 85.0
        elif distance_km <= 100:
            return 60.0
        else:
            return 20.0

    def _score_fit(self, specs: Dict[str, Any]) -> float:
        """
        Score based on frame size and travel range fit.
        """
        score = 0.0

        # Frame size (max 60 points)
        frame_size = specs.get("frame_size", "unknown")
        if frame_size in ("M", "S2", "S3"):
            score += 60
        elif frame_size == "unknown":
            score += 30  # Neutral

        # Travel range (max 40 points)
        travel_mm = specs.get("travel_front_mm")
        if travel_mm:
            if 140 <= travel_mm <= 150:
                score += 40
            elif 130 <= travel_mm < 140 or 150 < travel_mm <= 160:
                score += 35
            elif travel_mm < 130 or travel_mm > 160:
                score += 20

        return min(100.0, score)
