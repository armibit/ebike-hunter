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
from pipeline.corrections import apply_spec_correction
from pipeline.scoring import ScoringEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    config_path = BASE_DIR / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def chunked(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def main():
    # override=True: .env is this project's explicit local config (e.g. pointing
    # ANTHROPIC_BASE_URL at a local gateway) — it should win over stray vars
    # already exported in the shell, not the other way around.
    load_dotenv(BASE_DIR / ".env", override=True)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set — add it to .env in the project root. Aborting.")
        sys.exit(1)

    config = load_config()
    db = Database(config["app"]["db_path"])
    analyzer = AIAnalyzer(config["buyer_profile"])
    scorer = ScoringEngine(config)

    listings = db.get_listings_needing_ai_analysis()
    if not listings:
        print("No listings need AI analysis — all up to date.")
        db.close()
        return

    batches = chunked(listings, MAX_BATCH_SIZE)
    print(f"Analyzing {len(listings)} listing(s) with Claude Haiku, in {len(batches)} batch(es)...")

    analyzed = 0
    corrected = 0
    for i, batch in enumerate(batches, 1):
        results = analyzer.analyze_batch(batch)
        for result in results:
            db.save_ai_analysis(result["listing_id"], result["ai_analysis"], result["ai_score"])
            analyzed += 1

            # If Claude read a spec directly off the seller's text that the
            # regex parser missed (e.g. an unverified/guessed motor, or an
            # unrecognized frame size), apply it and recalculate score_total
            # — otherwise the fix would only ever show up as prose in
            # ai_analysis, never actually move the listing's ranking.
            corrected_specs = result.get("corrected_specs") or {}
            if corrected_specs:
                score_result = apply_spec_correction(db, scorer, result["listing_id"], corrected_specs)
                if score_result is not None:
                    corrected += 1
                    logger.info(
                        "AI corrected specs for %s: %s (new score_total=%.1f)",
                        result["listing_id"], corrected_specs, score_result["score_total"],
                    )

        print(f"  batch {i}/{len(batches)}: {len(results)}/{len(batch)} analyzed")

    db.close()
    print(f"Done — {analyzed}/{len(listings)} listing(s) analyzed"
          + (f", {corrected} rescored from AI-read spec corrections." if corrected else "."))

    from scripts.generate_dashboard import generate_dashboard
    dashboard_path = BASE_DIR / "index.html"
    generate_dashboard(config["app"]["db_path"], str(dashboard_path))
    print(f"✓ Dashboard refreshed: {dashboard_path}")


if __name__ == "__main__":
    main()
