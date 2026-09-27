#!/usr/bin/env python3
"""
Re-run RegexParser + reject filters + scoring against every stored listing,
using the *current* taxonomy.json/regex_parser.py — picks up any parser or
taxonomy fix without a full network rescan.

Mirrors run.py::process_listing()'s reject-filter cascade exactly (same
order, same reasons) but reads title/description_raw already in the DB
instead of hitting the connectors again.

Skips listings a human explicitly decided on, so a regex fix can never
silently overturn a manual choice:
  - status SOLD / DELISTED (listing is gone, not a filtering decision)
  - status REJECTED with rejection_reason == MANUAL_REJECT_REASON ("Scarta")

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
from pipeline.regex_parser import RegexParser
from pipeline.scoring import ScoringEngine


def load_config() -> Dict[str, Any]:
    with open(BASE_DIR / "config" / "config.yaml", "r") as f:
        return yaml.safe_load(f)


def evaluate_reject_reasons(specs: Dict[str, Any], price_chf: float, config: Dict[str, Any]) -> List[str]:
    reasons = []

    if price_chf <= 0:
        reasons.append("Invalid price (0 or missing — likely a parsing failure)")

    if price_chf > config["buyer_profile"]["budget"]["hard_max_price"]:
        reasons.append(f"Over budget ({price_chf:.0f} > {config['buyer_profile']['budget']['hard_max_price']} CHF)")

    if price_chf > 0 and price_chf < config["buyer_profile"]["budget"].get("suspicious_min_price", 900):
        reasons.append(f"Suspicious price ({price_chf:.0f} CHF - possible scam)")

    if specs["suspension_type"] == "hardtail":
        reasons.append("Hardtail (need full suspension)")

    if specs.get("excluded_category"):
        reasons.append(f"Wrong category ({specs['excluded_category']})")

    min_motor_nm = config["hardware_requirements"]["min_motor_torque_nm"]
    if specs["motor_torque_nm"] is None:
        reasons.append("No motor detected (likely not an e-bike)")
    elif specs["motor_torque_nm"] < min_motor_nm:
        reasons.append(f"Weak motor ({specs['motor_torque_nm']}nm < {min_motor_nm}nm)")

    min_battery = config["hardware_requirements"]["min_battery_wh"]
    if specs["battery_capacity_wh"] is not None and specs["battery_capacity_wh"] < min_battery:
        reasons.append(f"Small battery ({specs['battery_capacity_wh']}Wh < {min_battery}Wh)")

    if specs["frame_size"] == "disallowed":
        reasons.append(f"Wrong size ({specs['frame_size']})")

    if specs["has_red_flag"]:
        reasons.append(f"Red flags: {', '.join(specs['red_flag_details'][:2])}")

    return reasons


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    config = load_config()
    db = Database(config["app"]["db_path"])
    parser = RegexParser(str(BASE_DIR / "config" / "taxonomy.json"))
    scorer = ScoringEngine(config)

    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT id, title, description_raw, price_chf, distance_km, status, rejection_reason
        FROM listings
        WHERE status IN ('ACTIVE', 'PRICE_DROP', 'REJECTED')
    """)
    rows = cursor.fetchall()

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

        if status == "REJECTED" and old_reason == MANUAL_REJECT_REASON:
            skipped_manual += 1
            continue

        specs = parser.parse(row["title"], row["description_raw"] or "")
        reasons = evaluate_reject_reasons(specs, price_chf, config)
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
            listing_data = {"price_chf": price_chf, "distance_km": row["distance_km"]}
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
