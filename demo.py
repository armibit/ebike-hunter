#!/usr/bin/env python3
"""
Demo script showing end-to-end ebike-hunter pipeline.
Uses simulated listings to demonstrate parsing, filtering, scoring, and storage.
"""

import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from db.database import Database
from pipeline.regex_parser import RegexParser
from pipeline.normalizer import Normalizer
from pipeline.scoring import ScoringEngine


# Simulated listings from different portals
SIMULATED_LISTINGS = [
    {
        "portal": "tutti",
        "portal_id": "1001",
        "url": "https://tutti.ch/ti/lugano/specialized-levo",
        "title": "Specialized Turbo Levo Comp S2 2022 fully",
        "description": "E-MTB biammortizzata full suspension. Motore Brose 2.1 90nm, batteria 700Wh, forcella Fox 36 Performance Elite, freni Shimano XT 4 pistoni. Escursione 150mm / 140mm. Solo 800 km. Taglia S2.",
        "price_raw": 2100,
        "currency": "CHF",
        "location_raw": "Lugano, TI"
    },
    {
        "portal": "subito",
        "portal_id": "2001",
        "url": "https://subito.it/como/cube-stereo",
        "title": "Cube Stereo Hybrid 140 HPC Race fully taglia M",
        "description": "E-bike biammortizzata full. Motore Bosch Performance CX Gen4 85nm, batteria 625Wh. Escursione 140mm. Freni Magura MT5 4 pistoncini. Anno 2023, 1200 km.",
        "price_raw": 2300,
        "currency": "EUR",
        "location_raw": "Como, CO"
    },
    {
        "portal": "buycycle",
        "portal_id": "3001",
        "url": "https://buycycle.com/trek-rail-97",
        "title": "Trek Rail 9.7 Gen2 Medium Full Suspension",
        "description": "E-MTB fully biammortizzata. Motore Bosch CX Smart System 85nm, batteria 750Wh, sospensioni Fox Factory (Kashima) 160mm, freni SRAM Code RSC 4 pistoni. 2024, 300 km.",
        "price_raw": 2850,
        "currency": "EUR",
        "location_raw": "Milano, MI"
    },
    {
        "portal": "tutti",
        "portal_id": "1002",
        "url": "https://tutti.ch/ti/focus-jam",
        "title": "Focus JAM² 6.8 taglia M hardtail",
        "description": "Motore Bosch CX Gen4, batteria 625Wh, ma solo front suspension. Taglia M.",
        "price_raw": 1800,
        "currency": "CHF",
        "location_raw": "Bellinzona, TI"
    },
    {
        "portal": "subito",
        "portal_id": "2002",
        "url": "https://subito.it/varese/levo-sl",
        "title": "Specialized Levo SL S3",
        "description": "Motore leggero Specialized SL 1.1 50nm, batteria 320Wh. Full suspension 130mm.",
        "price_raw": 3200,
        "currency": "EUR",
        "location_raw": "Varese, VA"
    },
    {
        "portal": "tutti",
        "portal_id": "1003",
        "url": "https://tutti.ch/ti/canyon-spectral",
        "title": "Canyon Spectral:ON CF 7 taglia M 2021 Full",
        "description": "E-MTB fully biammortizzata. Motore Shimano EP8 85nm, batteria 720Wh, sospensioni RockShox Lyrik Select+ / Super Deluxe Select+ 150mm, freni Shimano XT 4 pistoni. 2800 km.",
        "price_raw": 2400,
        "currency": "CHF",
        "location_raw": "Mendrisio, TI"
    }
]


def main():
    print("=" * 70)
    print("E-BIKE HUNTER - Demo End-to-End Pipeline")
    print("=" * 70)
    print()

    # Load config using proper config loader to get DATABASE_URL from environment
    from utils.config import load_config
    config = load_config()

    # Initialize components
    db = Database(config["app"]["database_url"])
    parser = RegexParser(str(Path(__file__).parent / "config" / "taxonomy.json"))
    normalizer = Normalizer(
        chf_to_eur=config["exchange_rates"]["chf_to_eur"],
        eur_to_chf=config["exchange_rates"]["eur_to_chf"]
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
    print(f"✓ Initialized database: {masked_url}")
    print(f"✓ Buyer location: {config['buyer_profile']['location']['name']}")
    print(f"✓ Budget: {config['buyer_profile']['budget']['target_price']} - {config['buyer_profile']['budget']['hard_max_price']} CHF")
    print()

    # Process listings
    print("Processing listings...")
    print()

    accepted_count = 0
    rejected_count = 0

    for listing_raw in SIMULATED_LISTINGS:
        print(f"[{listing_raw['portal'].upper()}] {listing_raw['title']}")
        print(f"  Price: {listing_raw['price_raw']} {listing_raw['currency']}")

        # Normalize currency
        price_chf, price_eur = normalizer.normalize_currency(
            listing_raw["price_raw"],
            listing_raw["currency"]
        )

        # Resolve location
        lat, lon, distance_km, region = normalizer.resolve_location(listing_raw["location_raw"])

        # Parse specs
        specs = parser.parse(listing_raw["title"], listing_raw.get("description", ""))

        # Check filters
        reject_reasons = []

        # Filter: Price
        if price_chf > config["buyer_profile"]["budget"]["hard_max_price"]:
            reject_reasons.append(f"Over budget ({price_chf} > {config['buyer_profile']['budget']['hard_max_price']} CHF)")

        # Filter: Suspension type
        if specs["suspension_type"] != "full_suspension":
            reject_reasons.append(f"Not full suspension ({specs['suspension_type']})")

        # Filter: Motor
        if specs["motor_torque_nm"] is None or specs["motor_torque_nm"] < config["hardware_requirements"]["min_motor_torque_nm"]:
            reject_reasons.append(f"Weak motor ({specs['motor_torque_nm']} nm)")

        # Filter: Battery
        if specs["battery_capacity_wh"] is None or specs["battery_capacity_wh"] < config["hardware_requirements"]["min_battery_wh"]:
            reject_reasons.append(f"Small battery ({specs['battery_capacity_wh']} Wh)")

        # Filter: Frame size
        if specs["frame_size"] not in ("M", "S2", "S3", "unknown"):
            reject_reasons.append(f"Wrong size ({specs['frame_size']})")

        # Filter: Red flags
        if specs["has_red_flag"]:
            reject_reasons.append(f"Red flags: {', '.join(specs['red_flag_details'])}")

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
            rejected_count += 1
            print(f"  ❌ REJECTED: {reject_reasons[0]}")
        else:
            # Accepted - calculate score
            listing_data["status"] = "ACTIVE"
            listing_id, is_new, is_price_drop = db.upsert_listing(listing_data)

            db.save_specifications(listing_id, specs)

            score_result = scorer.calculate_score(listing_data, specs)
            db.save_score(listing_id, score_result)

            accepted_count += 1
            print(f"  ✅ ACCEPTED | Score: {score_result['score_total']:.1f}/100", end="")
            if score_result["is_deal_target"]:
                print(" 🔥 DEAL TARGET")
            else:
                print()

            print(f"     Distance: {distance_km:.1f} km | Motor: {specs['motor_model']} | Battery: {specs['battery_capacity_wh']} Wh")

        print()

    # Summary
    print("=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)
    print(f"Total listings processed: {len(SIMULATED_LISTINGS)}")
    print(f"Accepted: {accepted_count}")
    print(f"Rejected: {rejected_count}")
    print()

    # Show top deals
    print("=" * 70)
    print("TOP DEALS (Score >= 65)")
    print("=" * 70)
    print()

    top_deals = db.get_top_deals(min_score=65.0, limit=10)

    if top_deals:
        for i, deal in enumerate(top_deals, 1):
            print(f"{i}. {deal['title']}")
            print(f"   Score: {deal['score_total']:.1f}/100 | Price: {deal['price_chf']:.0f} CHF | Distance: {deal['distance_km']:.1f} km")
            print(f"   Motor: {deal['motor_model']} {deal['motor_torque_nm']}nm | Battery: {deal['battery_capacity_wh']} Wh")
            print(f"   URL: {deal['url']}")
            if deal['is_deal_target']:
                print("   🔥 HIGH-VALUE TARGET")
            print()
    else:
        print("No deals found matching criteria.")

    db.close()
    print("✓ Database closed")


if __name__ == "__main__":
    main()
