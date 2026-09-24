#!/usr/bin/env python3
"""
E-Bike Hunter - Main runner script.
Scans Tutti.ch and Subito.it for e-bike listings, filters, scores, and stores in database.
"""

import logging
import sys
import traceback
import yaml
from pathlib import Path
from typing import Dict, List, Any

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "src"))

from db.database import Database
from pipeline.regex_parser import RegexParser
from pipeline.normalizer import Normalizer
from pipeline.scoring import ScoringEngine
from connectors.tutti import TuttiConnector
from connectors.subito import SubitoConnector
from connectors.buycycle import BuycycleConnector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_path = BASE_DIR / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def process_listing(
    listing_raw: Dict[str, Any],
    parser: RegexParser,
    normalizer: Normalizer,
    scorer: ScoringEngine,
    db: Database,
    config: Dict[str, Any]
) -> bool:
    """
    Process a single listing through the pipeline.
    Returns True if accepted, False if rejected.
    """
    # Normalize currency
    price_chf, price_eur = normalizer.normalize_currency(
        listing_raw["price_raw"],
        listing_raw["currency"]
    )

    # Resolve location
    lat, lon, distance_km, region = normalizer.resolve_location(listing_raw.get("location_raw", ""))

    # Parse specs
    specs = parser.parse(listing_raw["title"], listing_raw.get("description_raw", ""))

    # Check filters
    reject_reasons = []

    # Filter: Price
    if price_chf > config["buyer_profile"]["budget"]["hard_max_price"]:
        reject_reasons.append(f"Over budget ({price_chf:.0f} > {config['buyer_profile']['budget']['hard_max_price']} CHF)")

    # Filter: Suspicious low price
    if price_chf > 0 and price_chf < config["buyer_profile"]["budget"].get("suspicious_min_price", 900):
        reject_reasons.append(f"Suspicious price ({price_chf:.0f} CHF - possible scam)")

    # Filter: Suspension type
    if specs["suspension_type"] == "hardtail":
        reject_reasons.append("Hardtail (need full suspension)")
    elif specs["suspension_type"] == "unknown":
        # Allow unknown suspension type for now (may be full)
        pass

    # Filter: Motor
    min_motor_nm = config["hardware_requirements"]["min_motor_torque_nm"]
    if specs["motor_torque_nm"] is None:
        # No motor detected - might still be OK if description incomplete
        pass
    elif specs["motor_torque_nm"] < min_motor_nm:
        reject_reasons.append(f"Weak motor ({specs['motor_torque_nm']}nm < {min_motor_nm}nm)")

    # Filter: Battery
    min_battery = config["hardware_requirements"]["min_battery_wh"]
    if specs["battery_capacity_wh"] is not None and specs["battery_capacity_wh"] < min_battery:
        reject_reasons.append(f"Small battery ({specs['battery_capacity_wh']}Wh < {min_battery}Wh)")

    # Filter: Frame size
    if specs["frame_size"] == "disallowed":
        reject_reasons.append(f"Wrong size ({specs['frame_size']})")

    # Filter: Red flags
    if specs["has_red_flag"]:
        reject_reasons.append(f"Red flags: {', '.join(specs['red_flag_details'][:2])}")

    # Prepare listing data
    listing_data = {
        **listing_raw,
        "price_chf": price_chf,
        "price_eur": price_eur,
        "latitude": lat,
        "longitude": lon,
        "distance_km": distance_km,
        "region": region
    }

    if reject_reasons:
        # Rejected
        listing_data["status"] = "REJECTED"
        listing_data["rejection_reason"] = "; ".join(reject_reasons)
        db.upsert_listing(listing_data)
        return False
    else:
        # Accepted - calculate score
        listing_data["status"] = "ACTIVE"
        listing_id, is_new, is_price_drop = db.upsert_listing(listing_data)

        db.save_specifications(listing_id, specs)

        score_result = scorer.calculate_score(listing_data, specs)
        db.save_score(listing_id, score_result)

        if is_price_drop:
            print(f"  📉 PRICE DROP: {listing_raw['title'][:60]}")

        return True


def main():
    print("=" * 80)
    print("E-BIKE HUNTER - Live Scraper")
    print("=" * 80)
    print()

    # Load config
    config = load_config()

    # Initialize components
    db = Database(config["app"]["db_path"])
    parser = RegexParser(str(BASE_DIR / "config" / "taxonomy.json"))
    normalizer = Normalizer(
        chf_to_eur=config["exchange_rates"]["chf_to_eur"],
        eur_to_chf=config["exchange_rates"]["eur_to_chf"]
    )
    scorer = ScoringEngine(config)

    print(f"✓ Database: {config['app']['db_path']}")
    print(f"✓ Target: {config['buyer_profile']['location']['name']}")
    print(f"✓ Budget: {config['buyer_profile']['budget']['target_price']}-{config['buyer_profile']['budget']['hard_max_price']} CHF")
    print()

    # Initialize connectors
    connectors = []

    if config["portals"]["tutti_ch"]["enabled"]:
        connectors.append(("Tutti.ch", TuttiConnector(config)))

    if config["portals"]["subito_it"]["enabled"]:
        connectors.append(("Subito.it", SubitoConnector(config)))

    if config["portals"]["buycycle"]["enabled"]:
        connectors.append(("Buycycle", BuycycleConnector(config)))

    # Scan each portal
    total_found = 0
    total_accepted = 0
    total_rejected = 0

    for portal_name, connector in connectors:
        print(f"[{portal_name}] Starting scan...")
        print("-" * 80)

        try:
            listings = connector.search_all()
            total_found += len(listings)

            accepted = 0
            rejected = 0

            for listing in listings:
                is_accepted = process_listing(listing, parser, normalizer, scorer, db, config)
                if is_accepted:
                    accepted += 1
                    total_accepted += 1
                else:
                    rejected += 1
                    total_rejected += 1

            print(f"[{portal_name}] Found: {len(listings)} | Accepted: {accepted} | Rejected: {rejected}")
            print()

        except Exception as e:
            logger.error("[%s] Error during scan: %s", portal_name, e)
            logger.debug(traceback.format_exc())
            print()

    # Summary
    print("=" * 80)
    print("SCAN SUMMARY")
    print("=" * 80)
    print(f"Total listings found: {total_found}")
    print(f"Accepted: {total_accepted}")
    print(f"Rejected: {total_rejected}")
    print()

    # Show top deals
    print("=" * 80)
    print("TOP DEALS (Score >= 70)")
    print("=" * 80)
    print()

    top_deals = db.get_top_deals(min_score=70.0, limit=20)

    if top_deals:
        for i, deal in enumerate(top_deals, 1):
            marker = "🔥" if deal.get("is_deal_target") else "  "
            print(f"{marker} {i}. [{deal['portal'].upper()}] {deal['title'][:70]}")
            print(f"      Score: {deal['score_total']:.1f}/100 | {deal['price_chf']:.0f} CHF | {deal['distance_km']:.1f} km")
            print(f"      {deal['url']}")
            print()
    else:
        print("No high-scoring deals found. Try adjusting filters or search queries.")

    # Show price drops
    price_drops = db.get_price_drops(limit=10)
    if price_drops:
        print("=" * 80)
        print("RECENT PRICE DROPS")
        print("=" * 80)
        print()
        for drop in price_drops:
            old_price = drop.get("original_price", 0)
            new_price = drop["price_raw"]
            discount = ((old_price - new_price) / old_price * 100) if old_price > 0 else 0
            print(f"  📉 {drop['title'][:70]}")
            print(f"      {old_price:.0f} → {new_price:.0f} {drop['currency']} (-{discount:.1f}%)")
            print(f"      {drop['url']}")
            print()

    db.close()
    print("✓ Scan complete. Database saved.")


if __name__ == "__main__":
    main()
