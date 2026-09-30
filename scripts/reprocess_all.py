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

from connectors.registry import portal_country
from db.database import Database, MANUAL_REJECT_REASON
from pipeline.analysis_text import generate_user_analysis
from pipeline.corrections import apply_spec_overrides, corrected_reject_reason
from pipeline.dedupe import dedupe_signature
from pipeline.filters import distance_reject_reason, hard_filter_reasons
from pipeline.normalizer import Normalizer
from pipeline.regex_parser import RegexParser, price_from_text
from pipeline.scoring import ScoringEngine
from utils.config import load_config


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
    db = Database(config["app"]["database_url"])
    parser = RegexParser(str(BASE_DIR / "config" / "taxonomy.json"))
    scorer = ScoringEngine(config)

    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT id, portal, title, description_raw, location_raw, price_chf, currency, distance_km,
               status, rejection_reason, status_locked
        FROM listings
        WHERE status IN ('ACTIVE', 'PRICE_DROP', 'REJECTED')
    """)
    rows = cursor.fetchall()
    home = config["buyer_profile"]["location"]
    normalizer = Normalizer(home_lat=home.get("latitude", 46.0037), home_lon=home.get("longitude", 8.9511))

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

        # Stored with a 0 price (portal field empty): retry from the ad text.
        if price_chf <= 0:
            text_price = price_from_text(f"{row['title']}\n{row['description_raw'] or ''}")
            if text_price:
                price_chf, price_eur = normalizer.normalize_currency(text_price, row["currency"] or "EUR")
                print(f"  PRICE   {listing_id}: 0 -> {price_chf} CHF (from text)")
                if not dry_run:
                    cursor.execute(
                        "UPDATE listings SET price_raw = %s, price_chf = %s, price_eur = %s WHERE id = %s",
                        (text_price, price_chf, price_eur, listing_id),
                    )

        if row["status_locked"] or (status == "REJECTED" and old_reason == MANUAL_REJECT_REASON):
            skipped_manual += 1
            continue

        # Re-resolve the location too, so normalizer fixes (new towns,
        # province codes) and the distance filter reach stored listings.
        location = normalizer.resolve(row["location_raw"] or "", portal_country(row["portal"]))
        lat, lon, distance_km, region = location.as_tuple()
        if not dry_run:
            cursor.execute(
                "UPDATE listings SET latitude = %s, longitude = %s, distance_km = %s, region = %s,"
                " location_normalized = COALESCE(%s, location_normalized), dedupe_signature = %s WHERE id = %s",
                (lat, lon, distance_km, region, location.place, dedupe_signature(row["title"], price_chf), listing_id),
            )

        overrides = db.get_spec_overrides(listing_id)
        specs = apply_spec_overrides(parser.parse(row["title"], row["description_raw"] or ""), overrides)
        reasons = evaluate_reject_reasons(specs, price_chf, config, list(overrides))
        distance_reason = distance_reject_reason(row["portal"], lat, distance_km, location.country, config)
        if distance_reason:
            reasons.append(distance_reason)
        was_active = status in ("ACTIVE", "PRICE_DROP")

        if reasons:
            new_reason = "; ".join(reasons)
            if was_active:
                print(f"  REJECT  {listing_id}: {new_reason}")
                newly_rejected += 1
                if not dry_run:
                    cursor.execute(
                        "UPDATE listings SET status = 'REJECTED', rejection_reason = %s WHERE id = %s",
                        (new_reason, listing_id),
                    )
            elif new_reason != old_reason:
                print(f"  REASON  {listing_id}: {old_reason!r} -> {new_reason!r}")
                reason_text_fixed += 1
                if not dry_run:
                    cursor.execute(
                        "UPDATE listings SET rejection_reason = %s WHERE id = %s",
                        (new_reason, listing_id),
                    )
        else:
            listing_data = {"price_chf": price_chf, "distance_km": distance_km}
            score_result = scorer.calculate_score(listing_data, specs)

            if not was_active:
                print(f"  RESTORE {listing_id}: score {score_result['score_total']}")
                restored += 1
                if not dry_run:
                    cursor.execute(
                        "UPDATE listings SET status = 'ACTIVE', rejection_reason = NULL WHERE id = %s",
                        (listing_id,),
                    )
                    analysis = generate_user_analysis(score_result["score_total"], specs, listing_data)
                    db.save_user_analysis(listing_id, analysis)
            else:
                rescored += 1

            if not dry_run:
                db.save_score(listing_id, score_result)

        if not dry_run:
            # Rejected rows too (as run.py does): they're shown greyed in the
            # dashboard and filtered by brand/size, so stale specs mislead.
            db.save_specifications(listing_id, specs)
            db.conn.commit()

    cursor.close()
    print()
    print(f"{'[DRY RUN] ' if dry_run else ''}Processed {len(rows)} listings:")
    print(f"  Restored to ACTIVE:        {restored}")
    print(f"  Newly REJECTED:            {newly_rejected}")
    print(f"  Rejection reason fixed:    {reason_text_fixed}")
    print(f"  Rescored (still ACTIVE):   {rescored}")
    print(f"  Skipped (manual reject):   {skipped_manual}")


if __name__ == "__main__":
    main()
