#!/usr/bin/env python3
"""Debug description extraction for a specific listing.

Usage:
    python3 debug_listing.py --id 140              # By dashboard ID
    python3 debug_listing.py --url https://...     # By direct URL
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import sqlite3
from connectors.subito import SubitoConnector
from utils.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Dashboard listing ID")
    parser.add_argument("--url", help="Direct listing URL")
    parser.add_argument("--portal_id", help="Portal-specific ID")
    args = parser.parse_args()

    config = load_config()
    connector = SubitoConnector(config)

    # Resolve listing from database if dashboard ID provided
    if args.id:
        db_path = config["app"]["db_path"]
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT portal, portal_id, url FROM listings WHERE rowid = ?", (args.id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            print(f"❌ Listing {args.id} not found in database")
            sys.exit(1)

        portal, portal_id, url = row
        print(f"✓ Found in DB: portal={portal}, portal_id={portal_id}")
        if portal != "subito":
            print(f"❌ Listing {args.id} is from {portal}, not Subito — cannot debug")
            sys.exit(1)
        args.portal_id = portal_id
        args.url = url

    if not args.url and not args.portal_id:
        print("❌ Provide --id, --url, or --portal_id")
        sys.exit(1)

    print(f"\n📍 Debugging description extraction:")
    print(f"   Portal ID: {args.portal_id}")
    print(f"   URL: {args.url}")
    print()

    try:
        details = connector.get_listing_details(args.portal_id, args.url)
        desc = details.get("description_raw", "")

        if desc:
            print(f"✅ Description extracted ({len(desc)} chars):")
            print(f"\n   {desc[:300]}...")
            print(f"\n   Full length: {len(desc)} characters")
        else:
            print("❌ No description extracted (empty)")
            print("\nTrying JSON-LD extraction...")

            from bs4 import BeautifulSoup
            response = connector.get(args.url)
            soup = BeautifulSoup(response.text, "lxml")

            import json
            scripts = soup.find_all("script", type="application/ld+json")
            print(f"   Found {len(scripts)} JSON-LD script(s)")

            for i, script in enumerate(scripts, 1):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        print(f"   Script {i}: array with {len(data)} items")
                        for item in data:
                            if item.get("@type") == "Product":
                                desc_field = item.get("description")
                                print(f"     - Product found, description field: {bool(desc_field)}")
                                if desc_field:
                                    print(f"       Length: {len(desc_field)}")
                    else:
                        if data.get("@type") == "Product":
                            desc_field = data.get("description")
                            print(f"   Script {i}: Product with description={bool(desc_field)}")
                except:
                    pass

            print("\nTrying HTML fallback selector...")
            import re
            desc_tag = soup.find(class_=lambda c: c and re.search(r"description$", c.lower()))
            if desc_tag:
                print(f"   ✓ Found tag with class ending in 'description'")
                text = desc_tag.get_text(strip=True)
                print(f"   Text: {text[:200]}...")
            else:
                print(f"   ❌ No tag with class ending in 'description'")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
