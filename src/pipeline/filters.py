"""Hard filters shared by the scan (run.py) and the correction path
(pipeline/corrections.py).

Both need the exact same "is this listing outside the buyer's criteria"
answer — the scan to decide ACTIVE vs REJECTED in the first place, the
correction path to decide whether a corrected listing may be restored. Kept
in one place so the two can't drift apart again (they did: the correction
path used to skip the price and red-flag checks entirely, so an AI-read
motor could resurrect a listing rejected for being over budget).
"""
from typing import Any, Dict, List, Optional

TOO_FAR_PREFIX = "Too far"

# Reject reasons a spec correction (hand or AI) can overturn: they come from
# the parser missing or misreading a spec. Anything else — price, distance,
# category, red flags, hardtail — no corrected_specs field can change, so an
# AI read of such a listing is wasted money.
_CORRECTABLE_REASON_PREFIXES = (
    "No motor detected",
    "Weak motor",
    "Small battery",
    "Wrong size",
)


def is_correctable_rejection(rejection_reason: Optional[str]) -> bool:
    """True when every reason in a (";"-joined) rejection could be fixed by
    a spec correction. The Italian reasons written by pipeline/corrections.py
    after a correction are spec-based too."""
    parts = [p.strip() for p in (rejection_reason or "").split(";") if p.strip()]
    if not parts:
        return False
    return all(
        p.startswith(_CORRECTABLE_REASON_PREFIXES) or "dopo correzione manuale" in p
        for p in parts
    )


def distance_reject_reason(
    portal: str, latitude: Optional[float], distance_km: Optional[float], region: Optional[str],
    config: Dict[str, Any],
) -> Optional[str]:
    """Enforce buyer_profile.max_radius_km: a Ticino listing beyond the
    Ticino radius, or any other located listing beyond the wider (Italy/
    rest-of-area) radius, is too far to go and see.

    Only listings whose place was actually resolved are checked — an
    unknown location gets a neutral distance, not a real one. Portals in
    max_radius_km.exempt_portals (shops that ship) are never rejected for
    distance; it still lowers their score."""
    radius = config.get("buyer_profile", {}).get("max_radius_km") or {}
    if latitude is None or distance_km is None or portal in (radius.get("exempt_portals") or []):
        return None
    limit = radius.get("ticino") if region == "ticino" else radius.get("lombardia")
    if limit is None or distance_km <= limit:
        return None
    return f"{TOO_FAR_PREFIX} ({distance_km:.0f} km > {limit} km)"


def hard_filter_reasons(price_chf: float, specs: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    """Every reason this listing fails the buyer's hard requirements, in
    the order run.py has always reported them — empty list means it passes."""
    reasons: List[str] = []
    budget = config.get("buyer_profile", {}).get("budget", {})
    hw = config.get("hardware_requirements", {})

    price_chf = price_chf or 0
    # 0 or negative means price parsing failed — never a valid/cheap listing
    if price_chf <= 0:
        reasons.append("Invalid price (0 or missing — likely a parsing failure)")

    hard_max = budget.get("hard_max_price")
    if hard_max is not None and price_chf > hard_max:
        reasons.append(f"Over budget ({price_chf:.0f} > {hard_max} CHF)")

    if 0 < price_chf < budget.get("suspicious_min_price", 900):
        reasons.append(f"Suspicious price ({price_chf:.0f} CHF - possible scam)")

    # Unknown suspension type is allowed (may be full)
    if specs.get("suspension_type") == "hardtail":
        reasons.append("Hardtail (need full suspension)")

    # Not an eMTB, e.g. fat bike
    if specs.get("excluded_category"):
        reasons.append(f"Wrong category ({specs['excluded_category']})")

    min_motor_nm = hw.get("min_motor_torque_nm")
    motor_nm = specs.get("motor_torque_nm")
    if motor_nm is None:
        # No motor detected - likely muscular bike or incomplete listing
        reasons.append("No motor detected (likely not an e-bike)")
    elif min_motor_nm is not None and motor_nm < min_motor_nm:
        reasons.append(f"Weak motor ({motor_nm:g}nm < {min_motor_nm}nm)")

    min_battery = hw.get("min_battery_wh")
    battery_wh = specs.get("battery_capacity_wh")
    if battery_wh is not None and min_battery is not None and battery_wh < min_battery:
        reasons.append(f"Small battery ({battery_wh:g}Wh < {min_battery}Wh)")

    if specs.get("frame_size") == "disallowed":
        reasons.append("Wrong size (frame size outside target sizes)")

    if specs.get("has_red_flag"):
        details = specs.get("red_flag_details") or []
        reasons.append(f"Red flags: {', '.join(details[:2])}" if details else "Red flags")

    return reasons
