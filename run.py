#!/usr/bin/env python3
"""
E-Bike Hunter - Main runner script.
Scans every enabled portal for e-bike listings, filters, scores, and stores in database.
"""

import logging
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

import psycopg2

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "src"))

from db.database import Database
from pipeline.analysis_text import generate_user_analysis
from pipeline.corrections import apply_spec_overrides, corrected_reject_reason
from pipeline.dedupe import dedupe_signature
from pipeline.filters import distance_reject_reason, hard_filter_reasons
from pipeline.regex_parser import RegexParser, price_from_text
from pipeline.normalizer import Normalizer
from pipeline.scoring import ScoringEngine
from connectors.registry import PORTALS, is_enabled, portal_country
from utils.config import load_config
from utils.console import status, StatusAwareStreamHandler

logger = logging.getLogger(__name__)

# Availability checks per scan for listings the scan didn't see (see
# verify_unseen_listings); overridable with app.availability_checks_per_run.
DEFAULT_AVAILABILITY_CHECKS_PER_RUN = 300


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

    # Connectors log every HTTP call at INFO — verbose for console. Keep DEBUG
    # in file for debugging, but mute on console to avoid spam.
    logging.getLogger("connectors").setLevel(logging.WARNING)
    logging.getLogger("pipeline").setLevel(logging.WARNING)


def verify_unseen_listings(db: Database, connectors: Dict[str, Any], config: Dict[str, Any],
                           scan_started: str) -> int:
    """Ask each portal whether the live listings this scan did NOT find are
    still for sale — a listing drops out of search results when it's sold,
    expired or removed, and portals mark that in many ways (404/410,
    redirect to search, "annuncio non più disponibile", schema.org
    OutOfStock, Shopify/WooCommerce stock flags — see
    BaseConnector.check_availability). Sold ones become SOLD; an
    inconclusive check (blocked, network error) changes nothing.

    Capped per run, least recently checked first, so a big backlog is
    worked through over successive scans. Portals run in parallel, each at
    its own rate limit. Returns how many listings were marked SOLD."""
    cap = config.get("app", {}).get("availability_checks_per_run", DEFAULT_AVAILABILITY_CHECKS_PER_RUN)
    candidates = db.get_listings_to_verify(scan_started, cap)
    by_portal: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for listing in candidates:
        if listing["portal"] in PORTALS:
            by_portal[listing["portal"]].append(listing)

    if not by_portal:
        return 0

    total_to_check = sum(len(listings) for listings in by_portal.values())
    status.update("verify", f"Checking {total_to_check} listings (capped at {cap})...")

    def check_portal(portal: str) -> tuple[str, List[tuple], int]:
        connector = connectors.get(portal) or PORTALS[portal].cls(config)
        verdicts = []
        sold_count = 0
        for i, listing in enumerate(by_portal[portal], 1):
            try:
                available = connector.check_availability(listing["portal_id"], listing["url"])
                if available is False:
                    sold_count += 1
            except Exception:
                logger.debug("Availability check crashed for %s", listing["id"], exc_info=True)
                available = None
            verdicts.append((listing["id"], available))
        return portal, verdicts, sold_count

    sold = 0
    with ThreadPoolExecutor(max_workers=max(1, min(len(by_portal), 5))) as pool:
        for future in as_completed([pool.submit(check_portal, p) for p in by_portal]):
            portal, verdicts, portal_sold = future.result()
            for listing_id, available in verdicts:
                # SQLite writes stay on this thread.
                if available is False and db.mark_unavailable(listing_id):
                    sold += 1
                else:
                    db.mark_checked(listing_id)
            # Per-portal summary
            total = len(by_portal[portal])
            if total > 0:
                still_active = total - portal_sold
                print(f"  {portal:20s} │ {total:3d} checked │ {portal_sold:3d} sold │ {still_active:3d} active")

    status.finish("verify")
    return sold


def search_and_enrich(connector: Any) -> List[Dict[str, Any]]:
    """Runs on the portal's worker thread: search + per-listing detail fetch
    (both pure network I/O, no DB access) so slow-to-enrich portals no longer
    serialize behind each other on the main thread — see search_all's
    ThreadPoolExecutor in main()."""
    listings = connector.search_all()
    enrich_key = f"{connector.portal_name}:enrich"
    for idx, listing in enumerate(listings, 1):
        if not listing.get("description_raw"):
            status.update(enrich_key, f"[{connector.portal_name}] fetching detail {idx}/{len(listings)}")
            try:
                details = connector.get_listing_details(listing["portal_id"], listing["url"])
                if details.get("description_raw"):
                    listing["description_raw"] = details["description_raw"]
                if details.get("is_available") is False:
                    listing["is_available"] = False
            except Exception as e:
                logger.debug("Detail fetch failed for %s: %s", listing.get("url"), e, exc_info=True)
    status.finish(enrich_key)
    return listings


def process_listing(
    listing_raw: Dict[str, Any],
    parser: RegexParser,
    normalizer: Normalizer,
    scorer: ScoringEngine,
    db: Database,
    config: Dict[str, Any],
) -> bool:
    """
    Process a single listing through the pipeline.
    Returns True if accepted, False if rejected (or sold / deleted by hand).
    """
    listing_id = Database.make_listing_id(listing_raw["portal"], listing_raw["portal_id"])

    # Deleted by hand from the dashboard (🗑️): never bring it back.
    if db.is_deleted(listing_id):
        return False

    # Shops keep sold-out bikes in their catalogue feeds (Shopify
    # "available": false, WooCommerce is_in_stock=false): switch the stored
    # listing off instead of (re)importing it as for sale.
    if listing_raw.get("is_available") is False:
        db.mark_unavailable(listing_id)
        return False

    # Seller left the portal's price field empty but wrote it in the text.
    if not listing_raw.get("price_raw") or listing_raw["price_raw"] <= 0:
        listing_raw["price_raw"] = price_from_text(
            f"{listing_raw['title']}\n{listing_raw.get('description_raw') or ''}"
        )

    # Normalize currency
    price_chf, price_eur = normalizer.normalize_currency(
        listing_raw["price_raw"],
        listing_raw["currency"]
    )

    # Resolve location at province/canton level; the portal's country
    # settles codes that exist on both sides of the border.
    location = normalizer.resolve(listing_raw.get("location_raw", ""), portal_country(listing_raw["portal"]))
    lat, lon, distance_km, region = location.as_tuple()

    # Parse specs, then put back anything corrected by hand or by the AI
    # pass — otherwise every rescan would silently overwrite those fixes
    # with the parser's own (wrong or missing) reading.
    specs = parser.parse(listing_raw["title"], listing_raw.get("description_raw", ""))
    overrides = db.get_spec_overrides(listing_id)
    specs = apply_spec_overrides(specs, overrides)

    reject_reasons = hard_filter_reasons(price_chf, specs, config)
    if overrides:
        # A corrected value is checked as strictly as when it was entered
        # (e.g. an explicit "XL" isn't the parser's "disallowed" marker).
        override_reason = corrected_reject_reason(specs, list(overrides), config)
        if override_reason:
            reject_reasons.append(override_reason)

    distance_reason = distance_reject_reason(listing_raw["portal"], lat, distance_km, location.country, config)
    if distance_reason:
        reject_reasons.append(distance_reason)

    # Same bike on another portal / re-listed — flagged in the dashboard.
    dedupe_sig = dedupe_signature(listing_raw["title"], price_chf)

    # Prepare listing data
    listing_data = {
        **listing_raw,
        "price_chf": price_chf,
        "price_eur": price_eur,
        "latitude": lat,
        "longitude": lon,
        "distance_km": distance_km,
        "region": region,
        "location_normalized": location.place or "",
        "dedupe_signature": dedupe_sig
    }

    if reject_reasons:
        # Rejected
        listing_data["status"] = "REJECTED"
        listing_data["rejection_reason"] = "; ".join(reject_reasons)
        listing_id, _, _ = db.upsert_listing(listing_data)
        # Keep the parsed specs even for a rejected listing: the AI pass
        # reviews auto-rejected ones, and restoring one after a correction
        # must re-check the battery/frame the parser did find, not NULLs.
        db.save_specifications(listing_id, specs)
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


def refresh_user_analyses(db):
    """Regenerate user_analysis for every active listing, not just ones
    missing it — it's a pure, cheap, local recomputation from specs/score
    already in the DB (no network/API cost), so there's no reason to let
    stale text survive a wording or language change (this is exactly how
    a batch of listings ended up stuck showing English text after the
    heuristic copy was translated to Italian — nothing re-ran it). This
    also means a manual spec correction's new score shows consistent text
    next scan, not a description that still reflects the old spec."""
    cursor = db.conn.cursor()
    cursor.execute("""
    SELECT l.id, COALESCE(sc.score_total, 0) as score, l.price_chf, l.distance_km
    FROM listings l
    LEFT JOIN scores sc ON l.id = sc.listing_id
    WHERE l.status IN ('ACTIVE', 'PRICE_DROP', 'NEW')
    """)
    active_listings = cursor.fetchall()

    if not active_listings:
        print("✓ No active listings to analyze")
        return
    print(f"Generating analysis for {len(active_listings)} listings...")
    for row in active_listings:
        cursor.execute("SELECT * FROM specifications WHERE listing_id = %s", (row["id"],))
        spec_row = cursor.fetchone()
        if spec_row:
            listing_data = {"price_chf": row["price_chf"], "distance_km": row["distance_km"]}
            analysis = generate_user_analysis(float(row["score"]), dict(spec_row), listing_data)
            db.save_user_analysis(row["id"], analysis)
    print(f"✓ Generated analysis for {len(active_listings)} listings")


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
    db = Database(config["app"]["database_url"])
    parser = RegexParser(str(BASE_DIR / "config" / "taxonomy.json"))
    location = config["buyer_profile"]["location"]
    normalizer = Normalizer(
        chf_to_eur=config["exchange_rates"]["chf_to_eur"],
        eur_to_chf=config["exchange_rates"]["eur_to_chf"],
        home_lat=location.get("latitude", 46.0037),
        home_lon=location.get("longitude", 8.9511),
    )
    scorer = ScoringEngine(config)

    # Mask password in connection string before printing
    db_url = config["app"]["database_url"]
    if "@" in db_url:
        scheme, rest = db_url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":")[0]
        masked_url = f"{scheme}://{user}:***@{host}"
    else:
        masked_url = db_url
    print(f"✓ Database: {masked_url}")
    print(f"✓ Target: {config['buyer_profile']['location']['name']}")
    print(f"✓ Budget: {config['buyer_profile']['budget']['target_price']}-{config['buyer_profile']['budget']['hard_max_price']} CHF")
    print()

    # Initialize connectors (connectors/registry.py lists every portal)
    connectors = [
        (spec.display_name, spec.cls(config))
        for portal, spec in PORTALS.items()
        if is_enabled(portal, config)
    ]
    # Anything whose last_seen_at is older than this wasn't in this scan's results.
    scan_started = datetime.now(timezone.utc).isoformat()

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
        print()
        print("=" * 80)
        print(f"🔍 Scanning {len(connectors)} portals ({max_parallel} in parallel)...")
        print("=" * 80)

        portals_done = 0

        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            # search_and_enrich runs search + per-listing detail fetch inside
            # the same worker thread, so portals overlap on BOTH phases —
            # previously detail fetches ran one portal at a time on the main
            # thread after its search finished, serializing everyone behind
            # each portal's own rate limit.
            future_to_portal = {
                pool.submit(search_and_enrich, connector): (portal_name, connector)
                for portal_name, connector in connectors
            }

            for future in as_completed(future_to_portal):
                portal_name, connector = future_to_portal[future]
                status.finish(connector.portal_name)
                portals_done += 1

                try:
                    listings = future.result()
                except Exception as e:
                    status.clear()
                    logger.exception("[%s] Error during scan: %s", portal_name, e)
                    continue

                status.update("scan_progress", f"[{portals_done}/{len(connectors)}] Processing {portal_name}...")

                total_found += len(listings)
                accepted = 0
                rejected = 0

                for listing in listings:
                    try:
                        is_accepted = process_listing(listing, parser, normalizer, scorer, db, config)
                    except psycopg2.Error as e:
                        # Dropped DB connection: skip this listing, Database reconnects on next use.
                        logger.warning("DB error on %s/%s, skipped: %s", listing.get("portal"), listing.get("portal_id"), e)
                        is_accepted = False
                    if is_accepted:
                        accepted += 1
                        total_accepted += 1
                    else:
                        rejected += 1
                        total_rejected += 1

                status.clear()
                # Prettier summary: emoji to indicate acceptance rate
                rate = (accepted / len(listings) * 100) if listings else 0
                bar = "🟢" if rate > 50 else "🟡" if rate > 20 else "🔴"
                print(f"  {bar} {portal_name:20s} │ {len(listings):3d} found │ {accepted:3d} ✓ │ {rejected:3d} ✗")
        # Listings this scan didn't find anymore: sold, expired or removed?
        status.finish("scan_progress")
        status.clear()
        print()
        print("=" * 80)
        print("Checking listings no longer in search results (sold / expired / removed)...")
        print("=" * 80)
        sold_count = verify_unseen_listings(
            db, {connector.portal_name: connector for _, connector in connectors}, config, scan_started,
        )
        status.clear()
        print(f"✓ {sold_count} listing(s) marked SOLD" if sold_count else "✓ No sold listings detected")
    finally:
        status.stop()

    print()

    # Summary
    print("=" * 80)
    print("✓ SCAN COMPLETE")
    print("=" * 80)
    acceptance_rate = (total_accepted / total_found * 100) if total_found else 0
    print(f"  Found:    {total_found:4d}")
    print(f"  ✓ Pass:   {total_accepted:4d} ({acceptance_rate:5.1f}%)")
    print(f"  ✗ Reject: {total_rejected:4d}")
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

    print()
    print("=" * 80)
    print("REFRESHING ANALYSIS TEXT...")
    print("=" * 80)
    refresh_user_analyses(db)

    print()

    db.close()

    # Generate HTML dashboard
    print("=" * 80)
    print("GENERATING DASHBOARD...")
    print("=" * 80)
    from scripts.generate_dashboard import generate_dashboard
    dashboard_path = BASE_DIR / "index.html"
    generate_dashboard(config["app"]["database_url"], str(dashboard_path))
    print(f"✓ Dashboard: {dashboard_path}")
    print()
    print("✓ Scan complete. Database saved.")


if __name__ == "__main__":
    main()
