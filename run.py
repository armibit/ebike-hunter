#!/usr/bin/env python3
"""
E-Bike Hunter - Main runner script.
Scans Tutti.ch and Subito.it for e-bike listings, filters, scores, and stores in database.
"""

import logging
import sys
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "src"))

from db.database import Database
from pipeline.analysis_text import generate_user_analysis
from pipeline.regex_parser import RegexParser
from pipeline.normalizer import Normalizer
from pipeline.scoring import ScoringEngine
from connectors.tutti import TuttiConnector
from connectors.subito import SubitoConnector
from connectors.buycycle import BuycycleConnector
from connectors.upway import UpwayConnector
from connectors.decathlon import DecathlonConnector
from connectors.velomarkt import VelomarktConnector
from connectors.tcs_velocorner import TcsVelocornerConnector
from connectors.ridewill import RidewillConnector
from connectors.zbike import ZbikeConnector
from connectors.godspeed import GodspeedConnector
from connectors.ebikelab import EbikelabConnector
from connectors.ecycles_shop import EcyclesShopConnector
from connectors.ebikestorebrescia import EbikestorebresciaConnector
from connectors.buybestgear import BuybestgearConnector
from utils.console import status, StatusAwareStreamHandler
import requests

logger = logging.getLogger(__name__)


def setup_logging(config: Dict[str, Any]) -> None:
    """Console stays at config's log_level and spinner-aware (live view).
    The file always gets DEBUG — every retry, parse failure, and swallowed
    exception with its traceback — because connector breakage (a selector
    going stale, a portal changing its API) only ever shows up here, after
    the fact, never in the console scrollback."""
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_level_name = str(config.get("app", {}).get("log_level", "INFO")).upper()
    console_level = getattr(logging, console_level_name, logging.INFO)

    console_handler = StatusAwareStreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(logs_dir / "run.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler], force=True)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_path = BASE_DIR / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def check_listing_validity(url: str, timeout: int = 5) -> bool:
    """Check if listing URL is still valid (not 404). Returns True if valid."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code != 404
    except Exception:
        logger.debug("Validity check failed for %s — assuming still valid", url, exc_info=True)
        return True  # Assume valid if unreachable (network error, etc.)


def process_listing(
    listing_raw: Dict[str, Any],
    parser: RegexParser,
    normalizer: Normalizer,
    scorer: ScoringEngine,
    db: Database,
    config: Dict[str, Any],
    connector: Any = None
) -> bool:
    """
    Process a single listing through the pipeline.
    Returns True if accepted, False if rejected.
    """
    # Enrich with full listing-detail description when the search card gave none —
    # spec regex (motor/battery) often only appears in the full ad body, not the card.
    # Also check availability: if product is marked unavailable (out of stock),
    # reject it as the item is no longer for sale.
    if connector is not None and not listing_raw.get("description_raw"):
        try:
            details = connector.get_listing_details(listing_raw["portal_id"], listing_raw["url"])
            if details.get("description_raw"):
                listing_raw["description_raw"] = details["description_raw"]
            if details.get("is_available") is False:
                return False  # Item no longer available, skip processing
        except Exception as e:
            logger.debug("Detail fetch failed for %s: %s", listing_raw.get("url"), e, exc_info=True)

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

    # Filter: Invalid price (0 or negative means price parsing failed —
    # never treat this as a valid/cheap listing)
    if price_chf <= 0:
        reject_reasons.append("Invalid price (0 or missing — likely a parsing failure)")

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

    # Filter: Excluded category (not an eMTB, e.g. fat bike)
    if specs.get("excluded_category"):
        reject_reasons.append(f"Wrong category ({specs['excluded_category']})")

    # Filter: Motor
    min_motor_nm = config["hardware_requirements"]["min_motor_torque_nm"]
    if specs["motor_torque_nm"] is None:
        # No motor detected - reject (likely muscular bike or incomplete listing)
        reject_reasons.append("No motor detected (likely not an e-bike)")
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

        # Generate user analysis (saved to DB)
        if is_new:
            analysis = generate_user_analysis(score_result["score_total"], specs, listing_data)
            db.save_user_analysis(listing_id, analysis)

        if is_price_drop:
            print(f"  📉 PRICE DROP: {listing_raw['title'][:60]}")

        return True


def main():
    # Load config and wire up logging before anything else runs, so every
    # subsequent line — including the banners below — is on the record.
    config = load_config()
    setup_logging(config)

    print("=" * 80)
    print("E-BIKE HUNTER - Live Scraper")
    print("=" * 80)
    print()

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

    if config["portals"]["upway"]["enabled"]:
        connectors.append(("Upway", UpwayConnector(config)))

    if config["portals"]["decathlon"]["enabled"]:
        connectors.append(("Decathlon", DecathlonConnector(config)))

    if config["portals"]["velomarkt"]["enabled"]:
        connectors.append(("Velomarkt", VelomarktConnector(config)))

    if config["portals"]["tcs_velocorner"]["enabled"]:
        connectors.append(("TCS Velocorner", TcsVelocornerConnector(config)))

    if config["portals"]["ridewill"]["enabled"]:
        connectors.append(("Ridewill.it", RidewillConnector(config)))

    if config["portals"]["zbike"]["enabled"]:
        connectors.append(("Z-Bike.ch", ZbikeConnector(config)))

    if config["portals"]["godspeed"]["enabled"]:
        connectors.append(("Godspeed.ch", GodspeedConnector(config)))

    if config["portals"]["ebikelab"]["enabled"]:
        connectors.append(("Ebikelab.it", EbikelabConnector(config)))

    if config["portals"]["ecycles_shop"]["enabled"]:
        connectors.append(("Ecycles-shop.it", EcyclesShopConnector(config)))

    if config["portals"]["ebikestorebrescia"]["enabled"]:
        connectors.append(("Ebikestore Brescia", EbikestorebresciaConnector(config)))

    if config["portals"]["buybestgear"]["enabled"]:
        connectors.append(("Buybestgear.com", BuybestgearConnector(config)))

    # Scan each portal. The search itself (connector.search_all()) is pure
    # network I/O rate-limited per-connector, so it's safe and effective to
    # run several portals concurrently — one portal's wait time no longer
    # blocks the next. Processing results (DB writes, scoring) stays on the
    # main thread, sequential, as each portal's search finishes.
    total_found = 0
    total_accepted = 0
    total_rejected = 0
    max_parallel = min(config["app"].get("parallel_scans", 5), len(connectors)) or 1

    status.start()
    try:
        print(f"Scanning {len(connectors)} portals ({max_parallel} in parallel)...")
        print("-" * 80)

        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            future_to_portal = {
                pool.submit(connector.search_all): (portal_name, connector)
                for portal_name, connector in connectors
            }

            for future in as_completed(future_to_portal):
                portal_name, connector = future_to_portal[future]
                status.finish(connector.portal_name)

                try:
                    listings = future.result()
                except Exception as e:
                    status.clear()
                    logger.exception("[%s] Error during scan: %s", portal_name, e)
                    continue

                logger.info("✓ [%s] scan done — %d listing(s) found, processing...", portal_name, len(listings))

                total_found += len(listings)
                accepted = 0
                rejected = 0
                enrich_key = f"{connector.portal_name}:enrich"

                for idx, listing in enumerate(listings, 1):
                    # Only listings missing a description trigger a live detail
                    # fetch (base.get() re-updates connector.portal_name's own
                    # status line while it runs) — label that sub-phase under
                    # its own key so it reads as "still working" rather than a
                    # stale scan line resurrecting after status.finish() above.
                    if not listing.get("description_raw"):
                        status.update(enrich_key, f"[{portal_name}] fetching detail {idx}/{len(listings)}")
                    is_accepted = process_listing(listing, parser, normalizer, scorer, db, config, connector)
                    if is_accepted:
                        accepted += 1
                        total_accepted += 1
                    else:
                        rejected += 1
                        total_rejected += 1

                status.finish(enrich_key)
                status.clear()
                print(f"[{portal_name}] Found: {len(listings)} | Accepted: {accepted} | Rejected: {rejected}")
    finally:
        status.stop()

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

    # Verify existing listings (mark SOLD if 404)
    print()
    print("=" * 80)
    print("VERIFYING & ANALYZING EXISTING LISTINGS...")
    print("=" * 80)
    cursor = db.conn.cursor()
    cursor.execute("SELECT id, url FROM listings WHERE status IN ('ACTIVE', 'PRICE_DROP', 'NEW')")
    existing = cursor.fetchall()

    sold_count = 0
    for listing_id, url in existing:
        if not check_listing_validity(url):
            db.mark_sold_or_delisted(listing_id, "SOLD")
            sold_count += 1

    if sold_count > 0:
        print(f"✓ Marked {sold_count} listings as SOLD")
    else:
        print("✓ All existing listings still valid")

    # Regenerate user_analysis for every active listing, not just ones
    # missing it — it's a pure, cheap, local recomputation from specs/score
    # already in the DB (no network/API cost), so there's no reason to let
    # stale text survive a wording or language change (this is exactly how
    # a batch of listings ended up stuck showing English text after the
    # heuristic copy was translated to Italian — nothing re-ran it). This
    # also means a manual spec correction's new score shows consistent text
    # next scan, not a description that still reflects the old spec.
    cursor.execute("""
    SELECT l.id, COALESCE(sc.score_total, 0) as score, l.price_chf, l.distance_km
    FROM listings l
    LEFT JOIN scores sc ON l.id = sc.listing_id
    WHERE l.status IN ('ACTIVE', 'PRICE_DROP', 'NEW')
    """)
    active_listings = cursor.fetchall()

    if active_listings:
        print(f"Generating analysis for {len(active_listings)} listings...")
        for listing_id, score, price, distance in active_listings:
            # Fetch specs for this listing
            cursor.execute("SELECT * FROM specifications WHERE listing_id = ?", (listing_id,))
            spec_row = cursor.fetchone()
            if spec_row:
                specs = dict(spec_row)
                listing_data = {"price_chf": price, "distance_km": distance}
                analysis = generate_user_analysis(float(score), specs, listing_data)
                db.save_user_analysis(listing_id, analysis)
        print(f"✓ Generated analysis for {len(active_listings)} listings")
    else:
        print("✓ No active listings to analyze")

    print()

    db.close()

    # Generate HTML dashboard
    print("=" * 80)
    print("GENERATING DASHBOARD...")
    print("=" * 80)
    from scripts.generate_dashboard import generate_dashboard
    dashboard_path = BASE_DIR / "index.html"
    generate_dashboard(config["app"]["db_path"], str(dashboard_path))
    print(f"✓ Dashboard: {dashboard_path}")
    print()
    print("✓ Scan complete. Database saved.")


if __name__ == "__main__":
    main()
