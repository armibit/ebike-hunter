#!/usr/bin/env python3
"""
Test script for live connectors.
Performs a limited test search on each portal.
"""

import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from connectors.tutti import TuttiConnector
from connectors.subito import SubitoConnector


def test_tutti():
    print("=" * 70)
    print("Testing Tutti.ch Connector")
    print("=" * 70)

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    connector = TuttiConnector(config)

    print("Searching for 'ebike fully'...")
    try:
        results = connector.search("ebike fully", canton="ti", limit=10)
        print(f"\n✓ Found {len(results)} listings")

        if results:
            print("\nFirst result:")
            first = results[0]
            print(f"  Title: {first.get('title', 'N/A')}")
            print(f"  Price: {first.get('price_raw', 0)} {first.get('currency', 'CHF')}")
            print(f"  URL: {first.get('url', 'N/A')}")
            print(f"  Location: {first.get('location_raw', 'N/A')}")
        else:
            print("  (No results found - this may be normal if parsing failed)")

    except Exception as e:
        print(f"✗ Error: {e}")

    print()


def test_subito():
    print("=" * 70)
    print("Testing Subito.it Connector")
    print("=" * 70)

    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    connector = SubitoConnector(config)

    print("Searching for 'emtb biammortizzata'...")
    try:
        results = connector.search("emtb biammortizzata", limit=10)
        print(f"\n✓ Found {len(results)} listings")

        if results:
            print("\nFirst result:")
            first = results[0]
            print(f"  Title: {first.get('title', 'N/A')}")
            print(f"  Price: {first.get('price_raw', 0)} {first.get('currency', 'EUR')}")
            print(f"  URL: {first.get('url', 'N/A')}")
            print(f"  Location: {first.get('location_raw', 'N/A')}")
        else:
            print("  (No results found - this may be normal if parsing failed)")

    except Exception as e:
        print(f"✗ Error: {e}")

    print()


if __name__ == "__main__":
    print("CONNECTOR TEST SUITE")
    print("This will make real HTTP requests to Tutti.ch and Subito.it")
    print()

    test_tutti()
    test_subito()

    print("=" * 70)
    print("Test complete.")
    print()
    print("Note: If results are empty, the HTML parsing may need adjustment")
    print("based on the current site structure. Check the actual HTML manually.")
