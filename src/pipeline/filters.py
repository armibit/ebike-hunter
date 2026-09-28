"""Hard filters shared by the scan (run.py) and the correction path
(pipeline/corrections.py).

Both need the exact same "is this listing outside the buyer's criteria"
answer — the scan to decide ACTIVE vs REJECTED in the first place, the
correction path to decide whether a corrected listing may be restored. Kept
in one place so the two can't drift apart again (they did: the correction
path used to skip the price and red-flag checks entirely, so an AI-read
motor could resurrect a listing rejected for being over budget).
"""
from typing import Any, Dict, List


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
