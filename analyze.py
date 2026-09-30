#!/usr/bin/env python3
"""AI analysis pass — run manually after a scan (run.py).

Reads ANTHROPIC_API_KEY from the environment (.env), pulls listings due for
an AI read, batches them through Claude Haiku, and writes ai_analysis/
ai_score back to the DB. Does not touch score_total or get_top_deals()'s
filtering — this is a separate, additive, on-demand pass so its API cost
stays predictable and decoupled from the automatic poll cycle.
"""
import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "src"))

from db.database import Database
from pipeline.ai_analyzer import AIAnalyzer, MAX_BATCH_SIZE
from pipeline.corrections import apply_spec_correction
from pipeline.filters import spec_problems
from pipeline.scoring import ScoringEngine
from connectors.registry import CONNECTOR_CLASSES
from utils.config import load_config

logger = logging.getLogger(__name__)


def setup_logging() -> Path:
    """Console stays at INFO; the file gets DEBUG so every per-listing
    check and every AI skip/discard reason (analyzer's own WARNING logs
    included) ends up somewhere reviewable after the run, not just
    scrolled past in the terminal. Mirrors run.py's logs/run.log setup."""
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / "analyze.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler], force=True)
    return log_path

# Every listing due for AI analysis, regardless of score — get_listings_needing_
# ai_analysis() defaults to limit=200 ordered by score_total DESC for other
# callers, but that silently truncated this pass: SQLite sorts NULL score_total
# (every REJECTED-by-hard-filter listing) last, so with >200 scored listings in
# the DB the ~1300 unscored ones were never reached, by --force or otherwise —
# the same top-200 got reanalyzed every run instead. This pass's whole point is
# to clear the backlog, so it must not cap it.
NO_BACKLOG_CAP = 100_000

# Below this, treat description_raw as "not enough for the AI to judge the bike
# on" rather than merely present — a one-line title-only blurb (or nothing)
# tells Claude nothing about condition, seller trustworthiness or excluded flaws.
MIN_DESCRIPTION_CHARS = 40
# A listing missing any of these gets its live detail page fetched before
# the AI reads it: the full seller text often states what the search
# snippet (and so the regex parser) never saw.
KEY_SPEC_FIELDS = ("motor_torque_nm", "battery_capacity_wh", "suspension_type",
                   "travel_front_mm", "travel_rear_mm", "model_year")


def needs_page_fetch(listing: Dict[str, Any]) -> bool:
    description = (listing.get("description_raw") or "").strip()
    if len(description) < MIN_DESCRIPTION_CHARS:
        return True
    if listing.get("frame_size") in (None, "", "unknown"):
        return True
    if listing.get("motor_verified") is not None and not listing.get("motor_verified"):
        return True
    return any(listing.get(field) is None for field in KEY_SPEC_FIELDS)


def enrich_thin_descriptions(listings: List[Dict[str, Any]], db: Database, config: Dict[str, Any]) -> int:
    """Before handing listings to Claude, backfill description_raw with a
    live fetch of the connector's detail page when it's missing/thin or when
    key specs are missing (needs_page_fetch) — the AI then reads the full
    page text and, if it states a missing spec, returns it in corrected_specs,
    which analyze.py writes to the DB. Not found on the page = nothing changes.

    run.py only ever does this at scan time, for listings the connector's
    search actually returned that run — a listing that fell off the search
    results (paginated out, re-sorted) keeps a stale/empty description
    forever even after a connector's selector bug gets fixed. This pass
    reads straight from the DB, so it's the only place that can catch and
    fix that for every listing in scope, not just freshly-scanned ones."""
    connector_cache: Dict[str, Any] = {}
    enriched = 0
    for listing in listings:
        description = (listing.get("description_raw") or "").strip()
        if not needs_page_fetch(listing) or not listing.get("url"):
            continue
        logger.debug(
            "Descrizione corta o specifiche mancanti per %s — verifico sulla pagina dell'annuncio.",
            listing["id"],
        )
        connector_cls = CONNECTOR_CLASSES.get(listing.get("portal"))
        if connector_cls is None:
            continue
        connector = connector_cache.get(listing["portal"])
        if connector is None:
            connector = connector_cls(config)
            connector_cache[listing["portal"]] = connector
        try:
            details = connector.get_listing_details(listing["portal_id"], listing["url"])
        except Exception as e:
            logger.debug("Live description fetch failed for %s: %s", listing["id"], e, exc_info=True)
            continue
        new_description = (details.get("description_raw") or "").strip()
        if len(new_description) > len(description):
            listing["description_raw"] = new_description
            db.update_description_raw(listing["id"], new_description)
            enriched += 1
    return enriched


def chunked(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def dry_run_summary(listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """What a run would send to the AI, without sending anything: how many
    listings, in how many API calls, and why they're in the batch."""
    reasons: Counter = Counter()
    for listing in listings:
        problems = spec_problems(listing)
        if listing.get("status") == "REJECTED" and not problems:
            reasons["scartato (motivo non correggibile)"] += 1
        for problem in problems:
            reasons[problem] += 1
        if not problems and listing.get("status") != "REJECTED":
            reasons["specifiche complete"] += 1
    return {
        "listings": len(listings),
        "api_calls": -(-len(listings) // MAX_BATCH_SIZE),
        "already_analyzed": sum(1 for l in listings if l.get("ai_analyzed_at")),
        "reasons": dict(reasons.most_common()),
    }


def print_dry_run(listings: List[Dict[str, Any]], args) -> None:
    summary = dry_run_summary(listings)
    mode = "--force" if args.force else "--problematic" if args.problematic else "normale"
    print(f"[DRY RUN — modalità {mode}] {summary['listings']} annunci verrebbero analizzati "
          f"in {summary['api_calls']} chiamate API ({MAX_BATCH_SIZE} per chiamata); "
          f"{summary['already_analyzed']} già analizzati in passato.")
    for reason, count in summary["reasons"].items():
        print(f"   {count:5d}  {reason}")
    if args.limit:
        print(f"   (limitato a --limit {args.limit}: il prossimo run riparte dai successivi)")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--force", action="store_true",
        help="Rianalizza TUTTI gli annunci in lista (attivi, price-drop e scartati "
             "automaticamente, di qualunque motivo), anche quelli già analizzati — es. "
             "dopo aver cambiato il prompt AI. Prima quelli mai analizzati, poi i più "
             "vecchi: con --limit puoi procedere a blocchi, run dopo run.",
    )
    mode_group.add_argument(
        "--problematic", action="store_true",
        help="Rianalizza solo gli annunci con specifiche problematiche che l'AI può "
             "correggere: scartati per motore/batteria/taglia, oppure attivi con motore "
             "da verificare o motore/batteria/taglia mancanti — anche se già analizzati.",
    )
    parser.add_argument(
        "--limit", type=int, metavar="N",
        help="Analizza al massimo N annunci in questo run (i successivi al prossimo "
             "run: l'ordine riparte da quelli mai o meno recentemente analizzati).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Mostra quanti annunci verrebbero analizzati e perché, senza chiamare "
             "l'API (non serve la API key).",
    )
    id_group = parser.add_mutually_exclusive_group()
    id_group.add_argument(
        "--id", dest="listing_id", metavar="ID",
        help="Analizza solo questo annuncio, per test — accetta sia l'id numerico "
             "mostrato nella dashboard (es. 42) sia l'id completo (es. tutti_12345). "
             "Ignora --force e lo stato dell'annuncio.",
    )
    id_group.add_argument(
        "--ids", dest="listing_ids", metavar="ID1,ID2,...",
        help="Analizza solo questi annunci — lista separata da virgole, ognuno "
             "sia id numerico da dashboard sia id completo (es. 12,tutti_12345,44). "
             "Ignora --force e lo stato degli annunci.",
    )
    id_group.add_argument(
        "--id-range", dest="id_range", nargs=2, type=int, metavar=("MIN", "MAX"),
        help="Analizza solo gli annunci con id numerico da dashboard compreso tra "
             "MIN e MAX (inclusi), es. --id-range 10 50. Ignora --force e lo stato "
             "degli annunci.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    log_path = setup_logging()

    # override=True: .env is this project's explicit local config (e.g. pointing
    # ANTHROPIC_BASE_URL at a local gateway) — it should win over stray vars
    # already exported in the shell, not the other way around.
    load_dotenv(BASE_DIR / ".env", override=True)

    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set — add it to .env in the project root. Aborting.")
        sys.exit(1)

    config = load_config()
    db = Database(config["app"]["db_path"])
    scorer = ScoringEngine(config)

    listing_id = None
    listing_ids = None
    id_range = None
    if args.listing_id is not None:
        listing_id = db.resolve_listing_id(args.listing_id)
        if listing_id is None:
            logger.error("Nessun annuncio trovato con id %r.", args.listing_id)
            db.close()
            sys.exit(1)
    elif args.listing_ids is not None:
        listing_ids = []
        for raw in (v.strip() for v in args.listing_ids.split(",")):
            if not raw:
                continue
            resolved = db.resolve_listing_id(raw)
            if resolved is None:
                logger.error("Nessun annuncio trovato con id %r.", raw)
                db.close()
                sys.exit(1)
            listing_ids.append(resolved)
    elif args.id_range is not None:
        id_range = (args.id_range[0], args.id_range[1])

    listings = db.get_listings_needing_ai_analysis(
        limit=args.limit if args.limit else NO_BACKLOG_CAP, force=args.force,
        listing_id=listing_id, listing_ids=listing_ids, id_range=id_range,
        problematic_only=args.problematic,
    )

    if args.dry_run:
        print_dry_run(listings, args)
        db.close()
        return

    # Diagnostic: a scored listing is always in scope for the AI pass
    # regardless of status — REJECTED (manual "Scarta", or a spec
    # correction that pushed it outside your own criteria) included — so
    # the only reason a decent-scoring listing wouldn't be processed now is
    # that it was already analyzed (skipped on purpose unless you pass
    # --force). Print it explicitly instead of leaving "why wasn't this
    # processed" to be reverse-engineered from silence.
    if listing_id is None and listing_ids is None and id_range is None and not (args.force or args.problematic):
        exclusions = db.get_high_score_ai_exclusions(min_score=70.0)
        if exclusions:
            print(f"\n⚠️  {len(exclusions)} annunci con punteggio >= 70 NON verranno analizzati ora:")
            for item in exclusions:
                print(f"   #{item['numeric_id']} score={item['score_total']:.1f} \"{item['title'][:60]}\" — {item['reason']}")
            print()

    if not listings:
        print("No listings need AI analysis — all up to date.")
        db.close()
        return

    enriched = enrich_thin_descriptions(listings, db, config)
    if enriched:
        print(f"✓ Fetched a fuller description from the live listing page for {enriched} listing(s).")

    analyzer = AIAnalyzer(config["buyer_profile"], hardware_requirements=config.get("hardware_requirements"))
    batches = chunked(listings, MAX_BATCH_SIZE)
    print(f"Analyzing {len(listings)} listing(s) with Claude Haiku, in {len(batches)} batch(es)...")

    analyzed = 0
    corrected = 0
    discarded: List[Dict[str, str]] = []
    for i, batch in enumerate(batches, 1):
        for listing in batch:
            logger.info(
                "[batch %d/%d] Controllo annuncio %s: \"%s\" (%s CHF)",
                i, len(batches), listing["id"], (listing.get("title") or "")[:60], listing.get("price_chf"),
            )

        results = analyzer.analyze_batch(batch)
        result_ids = {result["listing_id"] for result in results}

        for result in results:
            db.save_ai_analysis(result["listing_id"], result["ai_analysis"], result["ai_score"])
            analyzed += 1
            logger.info("  -> %s analizzato, ai_score=%.1f", result["listing_id"], result["ai_score"])

            # If Claude read a spec directly off the seller's text that the
            # regex parser missed (e.g. an unverified/guessed motor, or an
            # unrecognized frame size), apply it and recalculate score_total
            # — otherwise the fix would only ever show up as prose in
            # ai_analysis, never actually move the listing's ranking.
            corrected_specs = result.get("corrected_specs") or {}
            if corrected_specs:
                score_result = apply_spec_correction(db, scorer, result["listing_id"], corrected_specs, config=config)
                if score_result is not None:
                    corrected += 1
                    logger.info(
                        "AI corrected specs for %s: %s (new score_total=%.1f)",
                        result["listing_id"], corrected_specs, score_result["score_total"],
                    )

        # A listing sent in this batch but absent from result_ids never got a
        # valid verdict back — either the whole API call failed (analyzer logs
        # and returns [] for the batch) or the model skipped/malformed just
        # this item (analyzer already logs the specific reason as a WARNING
        # right above this). Track it here too so the end-of-run report has a
        # per-listing count, not just a log line to go dig for.
        for listing in batch:
            if listing["id"] not in result_ids:
                reason = "nessun risultato valido dall'AI per questo annuncio (vedi log WARNING sopra per il motivo esatto)"
                discarded.append({"id": listing["id"], "title": listing.get("title") or "", "reason": reason})
                logger.warning("  -> %s SCARTATO — %s", listing["id"], reason)

        print(f"  batch {i}/{len(batches)}: {len(results)}/{len(batch)} analyzed")

    db.close()
    print(f"Done — {analyzed}/{len(listings)} listing(s) analyzed"
          + (f", {corrected} rescored from AI-read spec corrections." if corrected else "."))

    logger.info("=== REPORT ANALISI ===")
    logger.info("Controllati: %d", len(listings))
    logger.info("Analizzati con successo: %d", analyzed)
    logger.info("Rescored da correzioni AI: %d", corrected)
    logger.info("Scartati: %d", len(discarded))
    for item in discarded:
        logger.info("  - %s \"%s\" — %s", item["id"], item["title"][:60], item["reason"])
    logger.info("=== FINE REPORT ===")
    print(f"✓ Report completo in {log_path}")

    from scripts.generate_dashboard import generate_dashboard
    dashboard_path = BASE_DIR / "index.html"
    generate_dashboard(config["app"]["db_path"], str(dashboard_path))
    print(f"✓ Dashboard refreshed: {dashboard_path}")


if __name__ == "__main__":
    main()
