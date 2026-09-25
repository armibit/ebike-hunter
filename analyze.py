#!/usr/bin/env python3
"""AI analysis pass — run manually after a scan (run.py).

Reads ANTHROPIC_API_KEY from the environment (.env), pulls listings due for
an AI read, batches them through Claude Haiku, and writes ai_analysis/
ai_score back to the DB. Does not touch score_total or get_top_deals()'s
filtering — this is a separate, additive, on-demand pass so its API cost
stays predictable and decoupled from the automatic poll cycle.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "src"))

from db.database import Database
from pipeline.ai_analyzer import AIAnalyzer, MAX_BATCH_SIZE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    config_path = BASE_DIR / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def chunked(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def main():
    load_dotenv(BASE_DIR / ".env")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set — add it to .env in the project root. Aborting.")
        sys.exit(1)

    config = load_config()
    db = Database(config["app"]["db_path"])
    analyzer = AIAnalyzer(config["buyer_profile"])

    listings = db.get_listings_needing_ai_analysis()
    if not listings:
        print("No listings need AI analysis — all up to date.")
        db.close()
        return

    batches = chunked(listings, MAX_BATCH_SIZE)
    print(f"Analyzing {len(listings)} listing(s) with Claude Haiku, in {len(batches)} batch(es)...")

    analyzed = 0
    for i, batch in enumerate(batches, 1):
        results = analyzer.analyze_batch(batch)
        for result in results:
            db.save_ai_analysis(result["listing_id"], result["ai_analysis"], result["ai_score"])
            analyzed += 1
        print(f"  batch {i}/{len(batches)}: {len(results)}/{len(batch)} analyzed")

    db.close()
    print(f"Done — {analyzed}/{len(listings)} listing(s) analyzed.")


if __name__ == "__main__":
    main()
