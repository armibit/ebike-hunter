#!/usr/bin/env python3
"""
Re-run RegexParser + reject filters + scoring against every stored listing,
using the *current* taxonomy.json/regex_parser.py — picks up any parser or
taxonomy fix without a full network rescan.

Uses run.py::process_listing()'s exact reject filters (pipeline/filters.py)
and re-applies stored spec corrections (spec_overrides) on top of the
parser's output, but reads title/description_raw already in the DB instead
of hitting the connectors again.

Skips listings a human explicitly decided on, so a regex fix can never
silently overturn a manual choice:
  - status SOLD / DELISTED (listing is gone, not a filtering decision)
  - a status the user locked by hand ("Scarta" / "Segna venduta")

Usage:
    python3 scripts/reprocess_all.py [--dry-run]
"""
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

import yaml

from db.database import Database, MANUAL_REJECT_REASON
from pipeline.analysis_text import generate_user_analysis
from pipeline.corrections import apply_spec_overrides, corrected_reject_reason
from pipeline.dedupe import dedupe_signature
from pipeline.filters import distance_reject_reason, hard_filter_reasons
from pipeline.normalizer import Normalizer
from pipeline.regex_parser import RegexParser
from pipeline.scoring import ScoringEngine


def load_config() -> Dict[str, Any]:
    with open(BASE_DIR / "config" / "config.yaml", "r") as f:
        return yaml.safe_load(f)


def evaluate_reject_reasons(
    specs: Dict[str, Any], price_chf: float, config: Dict[str, Any], overridden_fields: List[str] = (),
) -> List[str]:
    reasons = hard_filter_reasons(price_chf, specs, config)
    if overridden_fields:
        override_reason = corrected_reject_reason(specs, list(overridden_fields), config)
        if override_reason:
            reasons.append(override_reason)
    return reasons


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    config = load_config()
    db = Database(config["app"]["db_path"])
    parser = RegexParser(str(BASE_DIR / "config" / "taxonomy.json"))
    scorer = ScoringEngine(config)

    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT id, portal, title, description_raw, location_raw, price_chf, distance_km,
               status, rejection_reason, status_locked
        FROM listings
        WHERE status IN ('ACTIVE', 'PRICE_DROP', 'REJECTED')
    """)
    rows = cursor.fetchall()
    normalizer = Normalizer()

    restored = 0
    newly_rejected = 0
    reason_text_fixed = 0
    rescored = 0
    skipped_manual = 0

    for row in rows:
        listing_id = row["id"]
        status = row["status"]
        old_reason = row["rejection_reason"]
        price_chf = row["price_chf"] or 0

        if row["status_locked"] or (status == "REJECTED" and old_reason == MANUAL_REJECT_REASON):
            skipped_manual += 1
            continue

        # Re-resolve the location too, so normalizer fixes (new towns,
        # province codes) and the distance filter reach stored listings.
        lat, lon, distance_km, region = normalizer.resolve_location(row["location_raw"] or "")
        if not dry_run:
            db.conn.execute(
                "UPDATE listings SET latitude = ?, longitude = ?, distance_km = ?, region = ?,"
                " dedupe_signature = ? WHERE id = ?",
                (lat, lon, distance_km, region, dedupe_signature(row["title"], price_chf), listing_id),
            )

        overrides = db.get_spec_overrides(listing_id)
        specs = apply_spec_overrides(parser.parse(row["title"], row["description_raw"] or ""), overrides)
        reasons = evaluate_reject_reasons(specs, price_chf, config, list(overrides))
        distance_reason = distance_reject_reason(row["portal"], lat, distance_km, region, config)
        if distance_reason:
            reasons.append(distance_reason)
        was_active = status in ("ACTIVE", "PRICE_DROP")

        if reasons:
            new_reason = "; ".join(reasons)
            if was_active:
                print(f"  REJECT  {listing_id}: {new_reason}")
                newly_rejected += 1
                if not dry_run:
                    db.conn.execute(
                        "UPDATE listings SET status = 'REJECTED', rejection_reason = ? WHERE id = ?",
                        (new_reason, listing_id),
                    )
            elif new_reason != old_reason:
                print(f"  REASON  {listing_id}: {old_reason!r} -> {new_reason!r}")
                reason_text_fixed += 1
                if not dry_run:
                    db.conn.execute(
                        "UPDATE listings SET rejection_reason = ? WHERE id = ?",
                        (new_reason, listing_id),
                    )
        else:
            listing_data = {"price_chf": price_chf, "distance_km": distance_km}
            score_result = scorer.calculate_score(listing_data, specs)

            if not was_active:
                print(f"  RESTORE {listing_id}: score {score_result['score_total']}")
                restored += 1
                if not dry_run:
                    db.conn.execute(
                        "UPDATE listings SET status = 'ACTIVE', rejection_reason = NULL WHERE id = ?",
                        (listing_id,),
                    )
                    analysis = generate_user_analysis(score_result["score_total"], specs, listing_data)
                    db.save_user_analysis(listing_id, analysis)
            else:
                rescored += 1

            if not dry_run:
                db.save_specifications(listing_id, specs)
                db.save_score(listing_id, score_result)

        if not dry_run:
            db.conn.commit()

    print()
    print(f"{'[DRY RUN] ' if dry_run else ''}Processed {len(rows)} listings:")
    print(f"  Restored to ACTIVE:        {restored}")
    print(f"  Newly REJECTED:            {newly_rejected}")
    print(f"  Rejection reason fixed:    {reason_text_fixed}")
    print(f"  Rescored (still ACTIVE):   {rescored}")
    print(f"  Skipped (manual reject):   {skipped_manual}")


if __name__ == "__main__":
    main()
