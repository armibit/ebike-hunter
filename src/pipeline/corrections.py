"""Apply a partial spec correction to a listing and rescore it.

Shared by two callers that both need the same "merge a few fields into the
stored specs, mark the motor verified, recalculate score_total" sequence:
server.py's POST /api/listings/<id>/specs (a human correcting a field by
hand from the dashboard) and analyze.py's AI pass (Claude reading the raw
description and confidently naming a spec the regex parser missed).
"""
import json
from typing import Any, Dict, Optional

from db.database import Database
from pipeline.analysis_text import generate_user_analysis
from pipeline.scoring import ScoringEngine

EDITABLE_SPEC_FIELDS = ["motor_brand", "motor_model", "motor_torque_nm", "battery_capacity_wh", "frame_size"]


def apply_spec_correction(
    db: Database, scorer: ScoringEngine, listing_id: str, corrected_fields: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Merge corrected_fields into listing_id's stored specs, persist, and
    recalculate its score. Returns the new score_result dict, or None if the
    listing doesn't exist. Only keys in EDITABLE_SPEC_FIELDS are applied —
    anything else in corrected_fields is silently ignored."""
    current = db.get_listing_with_specs(listing_id)
    if current is None:
        return None

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

    return score_result
