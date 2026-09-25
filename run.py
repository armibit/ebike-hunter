#!/usr/bin/env python3
"""
E-Bike Hunter - Main runner script.
Scans Tutti.ch and Subito.it for e-bike listings, filters, scores, and stores in database.
"""

import logging
import sys
import traceback
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from utils.console import status, StatusAwareStreamHandler
import requests

_handler = StatusAwareStreamHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_path = BASE_DIR / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def generate_user_analysis(score: float, specs: Dict, listing_data: Dict) -> str:
    """Generate detailed user analysis based on score and specs."""
    motor = specs.get("motor_brand")
    torque = specs.get("motor_torque_nm")
    battery = specs.get("battery_capacity_wh")
    frame = specs.get("frame_size")
    suspension = specs.get("suspension_type")
    brakes = specs.get("brakes_tier")
    travel = specs.get("travel_front_mm")
    odometer = specs.get("odometer_km")
    distance = listing_data.get("distance_km", 0)
    price = listing_data.get("price_chf", 0)
    red_flags = specs.get("red_flag_details", [])

    lines = []

    # Header: Verdict
    if score >= 85:
        verdict = "🟢 HIGHLY RECOMMENDED - Top candidate for viewing"
    elif score >= 75:
        verdict = "🟡 WORTH CONSIDERING - Good balance of specs"
    elif score >= 65:
        verdict = "🟠 ACCEPTABLE - Meets minimum requirements"
    else:
        verdict = "🔴 LOWER PRIORITY - Not ideal match"

    lines.append(f"**{verdict}**\n")

    # Motor analysis
    if motor and torque:
        if torque >= 85:
            motor_note = f"{motor} {torque:.0f}Nm — Excellent power ✓✓"
        elif torque >= 75:
            motor_note = f"{motor} {torque:.0f}Nm — Good power ✓"
        else:
            motor_note = f"{motor} {torque:.0f}Nm — Weak, below target"
        lines.append(f"• Motor: {motor_note}")
    elif motor:
        lines.append(f"• Motor: {motor} — Torque not specified (check with seller)")
    else:
        lines.append("• Motor: Not detected — Likely not an e-bike or specs unclear")

    # Battery analysis
    if battery:
        if battery >= 625:
            batt_note = f"{battery:.0f}Wh — Excellent range ✓✓"
        elif battery >= 500:
            batt_note = f"{battery:.0f}Wh — Good range ✓"
        else:
            batt_note = f"{battery:.0f}Wh — Limited range ⚠️"
        lines.append(f"• Battery: {batt_note}")
    else:
        lines.append("• Battery: Not specified (ask seller)")

    # Frame size analysis
    if frame:
        if frame == "M":
            frame_note = "Perfect match ✓✓"
        elif frame in ("S2", "S3"):
            frame_note = "Close fit, might work"
        else:
            frame_note = f"Size {frame} — may not fit 170cm"
        lines.append(f"• Frame Size: {frame} — {frame_note}")
    else:
        lines.append("• Frame Size: Not specified (critical — ask immediately)")

    # Suspension analysis
    if suspension:
        if suspension == "full_suspension":
            susp_note = "Full suspension ✓✓"
        elif suspension == "hardtail":
            susp_note = "Hardtail (acceptable if price/specs exceptional)"
        else:
            susp_note = f"Unknown suspension type"
        if travel:
            susp_note += f" — {travel}mm travel"
        lines.append(f"• Suspension: {susp_note}")

    # Brakes analysis
    if brakes:
        if brakes in ("four_piston", "high"):
            brake_note = "High-end brakes ✓✓"
        elif brakes in ("two_piston", "mid"):
            brake_note = "Mid-range brakes ✓"
        else:
            brake_note = f"{brakes}"
        lines.append(f"• Brakes: {brake_note}")

    # Condition analysis
    if odometer:
        if odometer < 500:
            cond_note = "Very low mileage ✓✓"
        elif odometer < 2000:
            cond_note = "Low mileage ✓"
        elif odometer < 5000:
            cond_note = "Normal usage"
        else:
            cond_note = f"High mileage — verify condition"
        lines.append(f"• Condition: {odometer:.0f} km — {cond_note}")

    # Distance analysis
    if distance < 15:
        dist_note = f"Very close ({distance:.1f}km) ✓✓ — Easy visit"
    elif distance < 30:
        dist_note = f"Nearby ({distance:.1f}km) ✓ — Reachable by train"
    elif distance < 60:
        dist_note = f"Moderate ({distance:.1f}km) — Plan trip"
    else:
        dist_note = f"Far ({distance:.1f}km) — Worth it only if very good specs"
    lines.append(f"• Location: {dist_note}")

    # Price analysis
    target_price = 2200
    if price < 1800:
        price_note = f"Below target ({price:.0f} CHF) ✓✓ — Excellent value"
    elif price < target_price:
        price_note = f"In budget ({price:.0f} CHF, target {target_price}) ✓"
    else:
        price_note = f"Above target ({price:.0f} CHF, target {target_price}) — Negotiate"
    lines.append(f"• Price: {price_note}")

    # Red flags
    if red_flags:
        flag_str = ", ".join(red_flags[:3])
        lines.append(f"\n⚠️  Red flags: {flag_str}")

    # Final recommendation
    lines.append(f"\n**Recommendation**: Score {score:.0f}/100. " +
                ("Go see this bike — high likelihood of match." if score >= 80 else
                 "Good option, worth exploring." if score >= 70 else
                 "Acceptable but not ideal. Compare with other options first."))

    return "\n".join(lines)


def check_listing_validity(url: str, timeout: int = 5) -> bool:
    """Check if listing URL is still valid (not 404). Returns True if valid."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code != 404
    except Exception:
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
    if connector is not None and not listing_raw.get("description_raw"):
        try:
            details = connector.get_listing_details(listing_raw["portal_id"], listing_raw["url"])
            if details.get("description_raw"):
                listing_raw["description_raw"] = details["description_raw"]
        except Exception as e:
            logger.debug("Detail fetch failed for %s: %s", listing_raw.get("url"), e)

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
                    logger.error("[%s] Error during scan: %s", portal_name, e)
                    logger.debug(traceback.format_exc())
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

    # Generate user_analysis for listings without one
    cursor.execute("""
    SELECT l.id, COALESCE(sc.score_total, 0) as score, l.price_chf, l.distance_km
    FROM listings l
    LEFT JOIN scores sc ON l.id = sc.listing_id
    WHERE l.status IN ('ACTIVE', 'PRICE_DROP', 'NEW') AND l.user_analysis IS NULL
    """)
    listings_without_analysis = cursor.fetchall()

    if listings_without_analysis:
        print(f"Generating analysis for {len(listings_without_analysis)} listings...")
        for listing_id, score, price, distance in listings_without_analysis:
            # Fetch specs for this listing
            cursor.execute("SELECT * FROM specifications WHERE listing_id = ?", (listing_id,))
            spec_row = cursor.fetchone()
            if spec_row:
                specs = dict(spec_row)
                listing_data = {"price_chf": price, "distance_km": distance}
                analysis = generate_user_analysis(float(score), specs, listing_data)
                db.save_user_analysis(listing_id, analysis)
        print(f"✓ Generated analysis for {len(listings_without_analysis)} listings")
    else:
        print("✓ All listings already have analysis")

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
