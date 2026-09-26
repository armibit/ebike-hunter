"""Apply a partial spec correction to a listing and rescore it.

Shared by two callers that both need the same "merge a few fields into the
stored specs, mark the motor verified, recalculate score_total" sequence:
server.py's POST /api/listings/<id>/specs (a human correcting a field by
hand from the dashboard) and analyze.py's AI pass (Claude reading the raw
description and confidently naming a spec the regex parser missed).
"""
import json
from typing import Any, Dict, Optional

from db.database import Database, MANUAL_REJECT_REASON
from pipeline.analysis_text import generate_user_analysis
from pipeline.scoring import ScoringEngine

EDITABLE_SPEC_FIELDS = ["motor_brand", "motor_model", "motor_torque_nm", "battery_capacity_wh", "frame_size"]


def _normalize_size(value: str) -> str:
    return "".join(str(value).lower().split())


def _corrected_reject_reason(current: Dict[str, Any], applied_fields: list, config: Dict[str, Any]) -> Optional[str]:
    """A manual/AI correction can move a listing outside the buyer's actual
    criteria (e.g. you read the real frame size off a photo and it's XL,
    not the "unknown" the parser had) — it should be rejected the same as
    if a scan had read that value from the text in the first place, not
    stay ACTIVE just because the correction path never re-checks it."""
    rider_specs = config.get("buyer_profile", {}).get("rider_specs", {})
    target_sizes = {_normalize_size(s) for s in rider_specs.get("target_sizes", [])}
    if "frame_size" in applied_fields and current.get("frame_size") and target_sizes:
        value = str(current["frame_size"])
        if _normalize_size(value) not in target_sizes:
            return f"Taglia esclusa dopo correzione manuale ({value} non tra le taglie target)"

    hw = config.get("hardware_requirements", {})
    min_motor_nm = hw.get("min_motor_torque_nm")
    if "motor_torque_nm" in applied_fields and current.get("motor_torque_nm") is not None and min_motor_nm is not None:
        if current["motor_torque_nm"] < min_motor_nm:
            return f"Motore troppo debole dopo correzione manuale ({current['motor_torque_nm']:.0f}Nm < {min_motor_nm}Nm)"

    min_battery_wh = hw.get("min_battery_wh")
    if "battery_capacity_wh" in applied_fields and current.get("battery_capacity_wh") is not None and min_battery_wh is not None:
        if current["battery_capacity_wh"] < min_battery_wh:
            return f"Batteria troppo piccola dopo correzione manuale ({current['battery_capacity_wh']:.0f}Wh < {min_battery_wh}Wh)"

    return None


def _meets_original_hard_filters(current: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
    """Mirrors run.py's process_listing() hard filters exactly — used only
    to decide whether an automatically-REJECTED listing (the scan's own
    filters, or a previous correction — never a manual "Scarta", see
    MANUAL_REJECT_REASON) can be restored to ACTIVE once a correction
    supplies a spec the regex parser missed. Deliberately looser than
    _corrected_reject_reason's strict target_sizes check, which exists for
    a fresh, deliberate correction of that exact field — here, 'unknown'
    or an unlisted-but-not-explicitly-disallowed frame size passes, exactly
    as it would have at scan time, since the original rejection may have
    been about a completely different field."""
    if current.get("frame_size") == "disallowed":
        return f"Taglia non ammessa ({current.get('frame_size')})"

    hw = config.get("hardware_requirements", {})
    motor_nm = current.get("motor_torque_nm")
    if motor_nm is None:
        return "Nessun motore rilevato"
    min_motor_nm = hw.get("min_motor_torque_nm")
    if min_motor_nm is not None and motor_nm < min_motor_nm:
        return f"Motore troppo debole ({motor_nm:.0f}Nm < {min_motor_nm}Nm)"

    battery_wh = current.get("battery_capacity_wh")
    min_battery_wh = hw.get("min_battery_wh")
    if battery_wh is not None and min_battery_wh is not None and battery_wh < min_battery_wh:
        return f"Batteria troppo piccola ({battery_wh:.0f}Wh < {min_battery_wh}Wh)"

    return None


def apply_spec_correction(
    db: Database,
    scorer: ScoringEngine,
    listing_id: str,
    corrected_fields: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Merge corrected_fields into listing_id's stored specs, persist, and
    recalculate its score. Returns the new score_result dict, or None if the
    listing doesn't exist. Only keys in EDITABLE_SPEC_FIELDS are applied —
    anything else in corrected_fields is silently ignored.

    When config is given: for a currently ACTIVE/PRICE_DROP listing, a
    correction that pushes it outside the buyer's own criteria (wrong
    frame size, motor/battery below the hard minimums) marks it REJECTED
    — see _corrected_reject_reason(). For a listing that's REJECTED for an
    automatic reason (the scan's hard filters, or an earlier correction —
    never a manual "Scarta", which is left alone), the correction is
    instead checked against every hard requirement via
    _meets_original_hard_filters(); if it now passes, the listing is
    restored to ACTIVE — this is the whole point of sending rejected
    listings to the AI pass: the regex parser can miss a spec the
    description actually states. Passing config=None skips all of this
    (score/text still update normally, status untouched)."""
    current = db.get_listing_with_specs(listing_id)
    if current is None:
        return None

    was_auto_rejected = (
        current.get("status") == "REJECTED" and current.get("rejection_reason") != MANUAL_REJECT_REASON
    )

    # A field present with an explicit None/"" clears it back to unset —
    # that's a deliberate "I don't actually know this" from whoever is
    # correcting it, so it must NOT also flip motor_verified (checked
    # separately below, against the actual values, not just presence).
    applied_fields = [f for f in EDITABLE_SPEC_FIELDS if f in corrected_fields]
    if not applied_fields:
        return None
    for field in applied_fields:
        current[field] = corrected_fields[field]

    # Naming/correcting the motor — whether typed in by a human or read
    # directly off the seller's own description text by the AI — is, by
    # definition, a verified spec: full tier credit in scoring, not
    # RegexParser's flat "unverified guess" penalty (see
    # ScoringEngine._score_components). Only counts when a real value was
    # given, not when the field was cleared to null/empty.
    if corrected_fields.get("motor_brand") or corrected_fields.get("motor_torque_nm"):
        current["motor_verified"] = True

    current["red_flag_details"] = json.loads(current["red_flag_details"]) if current.get("red_flag_details") else []
    db.save_specifications(listing_id, current)

    listing_data = {"price_chf": current.get("price_chf"), "distance_km": current.get("distance_km")}
    score_result = scorer.calculate_score(listing_data, current)
    db.save_score(listing_id, score_result)

    # Otherwise the written verdict keeps describing the pre-correction
    # specs (e.g. still calling the motor unverified after you've just
    # confirmed it) even though the score and spec grid have moved on.
    analysis = generate_user_analysis(score_result["score_total"], current, listing_data)
    db.save_user_analysis(listing_id, analysis)

    if config is not None:
        if was_auto_rejected:
            reject_reason = _meets_original_hard_filters(current, config)
            if reject_reason is None:
                db.set_manual_status(listing_id, "ACTIVE")
            else:
                db.set_manual_status(listing_id, "REJECTED", reason=reject_reason)
        else:
            reject_reason = _corrected_reject_reason(current, applied_fields, config)
            if reject_reason:
                db.set_manual_status(listing_id, "REJECTED", reason=reject_reason)

    return score_result
