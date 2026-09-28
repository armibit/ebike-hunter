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
from pipeline.filters import TOO_FAR_PREFIX, hard_filter_reasons
from pipeline.scoring import ScoringEngine

EDITABLE_SPEC_FIELDS = ["motor_brand", "motor_model", "motor_torque_nm", "battery_capacity_wh", "frame_size", "suspension_type"]

# Rejection reasons a spec correction can never fix, because the value behind
# them isn't one of EDITABLE_SPEC_FIELDS and isn't stored in `specifications`
# (the parser's excluded_category and the resolved location live only in the
# scan's reject reason).
_UNCORRECTABLE_REJECT_MARKERS = ("Wrong category", TOO_FAR_PREFIX)


def _normalize_size(value: str) -> str:
    return "".join(str(value).lower().split())


def apply_spec_overrides(specs: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Merge stored overrides (see Database.get_spec_overrides) over freshly
    parsed specs — used by run.py so a rescan keeps every correction."""
    merged = {**specs, **overrides}
    if overrides.get("motor_brand") or overrides.get("motor_torque_nm"):
        merged["motor_verified"] = True
    return merged


def corrected_reject_reason(current: Dict[str, Any], applied_fields: list, config: Dict[str, Any]) -> Optional[str]:
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

    if "suspension_type" in applied_fields and current.get("suspension_type") == "hardtail":
        return "Hardtail dopo correzione manuale (serve full suspension)"

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


def _restore_blocker(current: Dict[str, Any], applied_fields: list, config: Dict[str, Any]) -> Optional[str]:
    """Why an automatically-REJECTED listing (the scan's own filters, or a
    previous correction — never a manual "Scarta", see MANUAL_REJECT_REASON)
    must stay rejected after a correction, or None if it can be restored to
    ACTIVE. Runs the scan's exact hard filters (pipeline/filters.py —
    price and red flags included, not just the corrected fields) plus the
    strict target-size check for a frame size the correction itself set.
    An 'unknown' frame size still passes, as it would have at scan time."""
    original_reason = current.get("rejection_reason") or ""
    for marker in _UNCORRECTABLE_REJECT_MARKERS:
        if marker in original_reason:
            return original_reason

    strict_reason = corrected_reject_reason(current, applied_fields, config)
    if strict_reason:
        return strict_reason

    reasons = hard_filter_reasons(current.get("price_chf"), current, config)
    return "; ".join(reasons) if reasons else None


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
    — see corrected_reject_reason(). For a listing that's REJECTED for an
    automatic reason (the scan's hard filters, or an earlier correction —
    never a manual "Scarta", which is left alone), the correction is
    instead checked against every hard requirement via
    _restore_blocker(); if it now passes, the listing is restored to
    ACTIVE — this is the whole point of sending rejected listings to the
    AI pass: the regex parser can miss a spec the description actually
    states. A status the user locked by hand (Scarta / Segna venduta) is
    never changed. Passing config=None skips all of this (score/text still
    update normally, status untouched).

    The corrected fields are also stored as overrides, so the next scan
    applies them on top of the parser's output instead of losing them."""
    current = db.get_listing_with_specs(listing_id)
    if current is None:
        return None

    status_locked = bool(current.get("status_locked"))
    was_auto_rejected = (
        current.get("status") == "REJECTED"
        and current.get("rejection_reason") != MANUAL_REJECT_REASON
        and not status_locked
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
    db.save_spec_overrides(listing_id, {field: corrected_fields[field] for field in applied_fields})

    listing_data = {"price_chf": current.get("price_chf"), "distance_km": current.get("distance_km")}
    score_result = scorer.calculate_score(listing_data, current)
    db.save_score(listing_id, score_result)

    # Otherwise the written verdict keeps describing the pre-correction
    # specs (e.g. still calling the motor unverified after you've just
    # confirmed it) even though the score and spec grid have moved on.
    analysis = generate_user_analysis(score_result["score_total"], current, listing_data)
    db.save_user_analysis(listing_id, analysis)

    if config is not None and not status_locked:
        if was_auto_rejected:
            reject_reason = _restore_blocker(current, applied_fields, config)
            if reject_reason is None:
                db.set_manual_status(listing_id, "ACTIVE")
            else:
                db.set_manual_status(listing_id, "REJECTED", reason=reject_reason)
        else:
            reject_reason = corrected_reject_reason(current, applied_fields, config)
            if reject_reason:
                db.set_manual_status(listing_id, "REJECTED", reason=reject_reason)

    return score_result
