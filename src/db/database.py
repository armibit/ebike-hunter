import functools
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from pipeline.filters import is_correctable_rejection, spec_problems

logger = logging.getLogger(__name__)

# Default rejection_reason set by set_manual_status(status="REJECTED") when
# the caller (server.py's ✕ "Scarta" button) gives no specific reason —
# distinguishes a deliberate "I don't want this one" from an automatic
# rejection (the scan's hard filters, or a spec correction that pushed a
# listing outside the buyer's own criteria), so other code — see
# pipeline/corrections.py — can tell whether a REJECTED listing is a
# candidate for the AI to reconsider or an explicit human decision to leave
# alone.
MANUAL_REJECT_REASON = "Scartata manualmente dall'utente"

_VALID_SCHEMA_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _atomic(method):
    """Run a multi-statement write as one transaction. The connection is
    otherwise autocommit, so plain reads never leave the session "idle in
    transaction" (holding locks/snapshots on Supabase for a whole scan)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        self.conn.autocommit = False
        try:
            result = method(self, *args, **kwargs)
            self.conn.commit()
            return result
        except BaseException:
            self.conn.rollback()
            raise
        finally:
            self.conn.autocommit = True
    return wrapper


class Database:
    def __init__(self, database_url: str, schema: Optional[str] = None):
        """database_url is a Postgres connection string (e.g. Supabase's
        "Session pooler" URI). schema, when given, isolates everything in
        its own Postgres schema instead of the default "public" one — used
        by tests to get a fresh, disposable namespace per test on a shared
        local Postgres, the same way each test used to get its own throwaway
        SQLite file."""
        self.database_url = database_url
        self.schema = schema
        self.conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
        self.conn.autocommit = True
        if schema:
            if not _VALID_SCHEMA_NAME.match(schema):
                raise ValueError(f"Invalid schema name: {schema!r}")
            cursor = self.conn.cursor()
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(f'SET search_path TO "{schema}"')
            self.conn.commit()
        self._init_schema()

    def _init_schema(self):
        cursor = self.conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            numeric_id BIGSERIAL UNIQUE NOT NULL,
            portal TEXT NOT NULL,
            portal_id TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            description_raw TEXT,
            seller_id TEXT,
            seller_name TEXT,
            price_raw REAL NOT NULL,
            currency TEXT NOT NULL,
            price_chf REAL NOT NULL,
            price_eur REAL NOT NULL,
            location_raw TEXT,
            location_normalized TEXT,
            region TEXT,
            latitude REAL,
            longitude REAL,
            distance_km REAL,
            status TEXT NOT NULL DEFAULT 'NEW',
            rejection_reason TEXT,
            status_locked INTEGER NOT NULL DEFAULT 0,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            dedupe_signature TEXT,
            image_phash TEXT,
            image_url TEXT,
            user_analysis TEXT,
            ai_analysis TEXT,
            ai_score REAL,
            ai_analyzed_at TIMESTAMP,
            first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            delisted_at TIMESTAMP,
            CONSTRAINT uq_portal_item UNIQUE (portal, portal_id)
        );

        CREATE TABLE IF NOT EXISTS listing_snapshots (
            id BIGSERIAL PRIMARY KEY,
            listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
            price_raw REAL NOT NULL,
            currency TEXT NOT NULL,
            price_chf REAL NOT NULL,
            status TEXT NOT NULL,
            captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS specifications (
            listing_id TEXT PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
            brand TEXT,
            model TEXT,
            model_year INTEGER,
            category TEXT,
            suspension_type TEXT,
            travel_front_mm INTEGER,
            travel_rear_mm INTEGER,
            frame_size TEXT,
            motor_brand TEXT,
            motor_model TEXT,
            motor_torque_nm REAL,
            motor_verified INTEGER,
            battery_capacity_wh REAL,
            odometer_km REAL,
            brakes_model TEXT,
            brakes_tier TEXT,
            fork_tier TEXT,
            has_red_flag INTEGER DEFAULT 0,
            red_flag_details TEXT,
            gears INTEGER,
            extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scores (
            listing_id TEXT PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
            score_total REAL NOT NULL,
            score_price_value REAL NOT NULL,
            score_component_quality REAL NOT NULL,
            score_condition_mileage REAL NOT NULL,
            score_location_proximity REAL NOT NULL,
            score_fit_geometry REAL NOT NULL,
            is_deal_target INTEGER DEFAULT 0,
            breakdown_json TEXT NOT NULL,
            calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        -- Spec values set by hand (dashboard) or read by the AI pass. They win
        -- over whatever RegexParser extracts on the next scan, which would
        -- otherwise silently overwrite every correction. value_json holds the
        -- JSON-encoded value so numbers stay numbers.
        CREATE TABLE IF NOT EXISTS spec_overrides (
            listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
            field TEXT NOT NULL,
            value_json TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (listing_id, field)
        );

        -- Listings deleted from the dashboard (🗑️). Kept so the next scan
        -- doesn't re-insert them as brand-new listings.
        CREATE TABLE IF NOT EXISTS deleted_listings (
            listing_id TEXT PRIMARY KEY,
            deleted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_listings_portal_status ON listings(portal, status);
        CREATE INDEX IF NOT EXISTS idx_listings_status_price ON listings(status, price_chf);
        CREATE INDEX IF NOT EXISTS idx_listings_dedupe ON listings(dedupe_signature);
        CREATE INDEX IF NOT EXISTS idx_scores_total ON scores(score_total DESC);
        CREATE INDEX IF NOT EXISTS idx_snapshots_listing ON listing_snapshots(listing_id, captured_at DESC);
        """)

        # Migration: older DBs may predate a column added later. Postgres
        # supports ADD COLUMN IF NOT EXISTS natively, so — unlike SQLite —
        # there's no need to inspect the column list by hand first.
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS user_analysis TEXT")
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS ai_analysis TEXT")
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS ai_score REAL")
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS ai_analyzed_at TIMESTAMP")
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS is_favorite INTEGER NOT NULL DEFAULT 0")
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS image_url TEXT")

        # status_locked: back-fill for DBs that predate it — a manual "Scarta"
        # is recognizable by its reason; lock those so the next scan stops
        # flipping them back to ACTIVE. A manual SOLD can't be told apart from
        # a 404-detected one, so those stay unlocked. Only run the backfill
        # the first time the column is actually added.
        cursor.execute("""
            SELECT NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = 'listings' AND column_name = 'status_locked'
            )
        """)
        needs_lock_backfill = cursor.fetchone()["exists" if False else list(cursor.fetchone.__self__.description[0].name for _ in [0]) and None] if False else None
        cursor.execute("""
            SELECT NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = 'listings' AND column_name = 'status_locked'
            ) AS missing
        """)
        needs_lock_backfill = cursor.fetchone()["missing"]
        cursor.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS status_locked INTEGER NOT NULL DEFAULT 0")
        if needs_lock_backfill:
            cursor.execute(
                "UPDATE listings SET status_locked = 1 WHERE status = 'REJECTED' AND rejection_reason = %s",
                (MANUAL_REJECT_REASON,),
            )

        cursor.execute("ALTER TABLE specifications ADD COLUMN IF NOT EXISTS motor_verified INTEGER")
        cursor.execute("ALTER TABLE specifications ADD COLUMN IF NOT EXISTS gears INTEGER")

        self.conn.commit()

    @staticmethod
    def make_listing_id(portal: str, portal_id: Any) -> str:
        return f"{portal}_{portal_id}"

    @_atomic
    def upsert_listing(self, item: Dict[str, Any]) -> Tuple[str, bool, bool]:
        """
        Upserts listing.
        Returns: (listing_id, is_new, is_price_drop)
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        portal = item["portal"]
        portal_id = str(item["portal_id"])
        listing_id = self.make_listing_id(portal, portal_id)

        cursor.execute(
            "SELECT id, price_raw, currency, price_chf, status, rejection_reason, status_locked"
            " FROM listings WHERE portal = %s AND portal_id = %s",
            (portal, portal_id),
        )
        existing = cursor.fetchone()

        is_new = existing is None
        is_price_drop = False

        if is_new:
            cursor.execute("""
            INSERT INTO listings (
                id, portal, portal_id, url, title, description_raw, seller_id, seller_name,
                price_raw, currency, price_chf, price_eur, location_raw, location_normalized,
                region, latitude, longitude, distance_km, status, rejection_reason,
                dedupe_signature, image_phash, image_url, first_seen_at, last_seen_at, last_checked_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                listing_id, portal, portal_id, item["url"], item["title"],
                item.get("description_raw", ""), item.get("seller_id"), item.get("seller_name"),
                item["price_raw"], item["currency"], item["price_chf"], item.get("price_eur", item["price_chf"]),
                item.get("location_raw", ""), item.get("location_normalized", ""),
                item.get("region", ""), item.get("latitude"), item.get("longitude"),
                item.get("distance_km"), item.get("status", "NEW"), item.get("rejection_reason"),
                item.get("dedupe_signature", ""), item.get("image_phash"), item.get("image_url"), now, now, now
            ))
            cursor.execute("""
            INSERT INTO listing_snapshots (listing_id, price_raw, currency, price_chf, status, captured_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (listing_id, item["price_raw"], item["currency"], item["price_chf"], item.get("status", "NEW"), now))
        else:
            old_status = existing["status"]
            requested_status = item.get("status", old_status)
            new_status = requested_status
            rejection_reason = item.get("rejection_reason")
            locked = bool(existing["status_locked"])

            # Compare like with like: the posted price in its own currency,
            # or the CHF equivalents if the listing switched currency.
            same_currency = (existing["currency"] or "").upper() == (item["currency"] or "").upper()
            old_price = existing["price_raw"] if same_currency else existing["price_chf"]
            new_price = item["price_raw"] if same_currency else item["price_chf"]
            price_changed = not same_currency or item["price_raw"] != existing["price_raw"]

            if locked:
                # The user decided this one by hand (Scarta / Segna venduta):
                # a rescan refreshes price/text but never overrides that call.
                new_status = old_status
                rejection_reason = existing["rejection_reason"]
            # Never let a price-drop promotion override an explicit rejection,
            # and ignore bogus 0/negative prices (failed scraping) as drops.
            elif requested_status != "REJECTED" and new_price > 0 and old_price > 0 and new_price < old_price:
                is_price_drop = True
                new_status = "PRICE_DROP"
            elif requested_status != "REJECTED" and old_status == "PRICE_DROP" and new_price == old_price:
                # Keep PRICE_DROP status — price hasn't recovered
                new_status = "PRICE_DROP"

            # Every real price change goes into the history — increases and
            # re-listings at a new price too, not just drops.
            if price_changed and item["price_raw"] > 0:
                cursor.execute("""
                INSERT INTO listing_snapshots (listing_id, price_raw, currency, price_chf, status, captured_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """, (listing_id, item["price_raw"], item["currency"], item["price_chf"], new_status, now))

            self._drop_blind_ai_analysis(listing_id, item.get("description_raw", ""))
            cursor.execute("""
            UPDATE listings SET
                title = %s, description_raw = %s, price_raw = %s, currency = %s,
                price_chf = %s, price_eur = %s, location_raw = %s, location_normalized = %s,
                region = %s, latitude = %s, longitude = %s, distance_km = %s,
                status = %s, rejection_reason = %s, dedupe_signature = %s, last_seen_at = %s, last_checked_at = %s,
                image_url = COALESCE(%s, image_url)
            WHERE id = %s
            """, (
                item["title"], item.get("description_raw", ""), item["price_raw"], item["currency"],
                item["price_chf"], item.get("price_eur", item["price_chf"]), item.get("location_raw", ""),
                item.get("location_normalized", ""), item.get("region", ""), item.get("latitude"),
                item.get("longitude"), item.get("distance_km"), new_status, rejection_reason,
                item.get("dedupe_signature", ""), now, now, item.get("image_url"), listing_id
            ))

        self.conn.commit()
        return listing_id, is_new, is_price_drop

    def save_specifications(self, listing_id: str, specs: Dict[str, Any]):
        cursor = self.conn.cursor()
        motor_verified = specs.get("motor_verified")
        cursor.execute("""
        INSERT INTO specifications (
            listing_id, brand, model, model_year, category, suspension_type,
            travel_front_mm, travel_rear_mm, frame_size, motor_brand, motor_model,
            motor_torque_nm, motor_verified, battery_capacity_wh, odometer_km, brakes_model,
            brakes_tier, fork_tier, has_red_flag, red_flag_details, gears
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (listing_id) DO UPDATE SET
            brand = EXCLUDED.brand, model = EXCLUDED.model, model_year = EXCLUDED.model_year,
            category = EXCLUDED.category, suspension_type = EXCLUDED.suspension_type,
            travel_front_mm = EXCLUDED.travel_front_mm, travel_rear_mm = EXCLUDED.travel_rear_mm,
            frame_size = EXCLUDED.frame_size, motor_brand = EXCLUDED.motor_brand,
            motor_model = EXCLUDED.motor_model, motor_torque_nm = EXCLUDED.motor_torque_nm,
            motor_verified = EXCLUDED.motor_verified, battery_capacity_wh = EXCLUDED.battery_capacity_wh,
            odometer_km = EXCLUDED.odometer_km, brakes_model = EXCLUDED.brakes_model,
            brakes_tier = EXCLUDED.brakes_tier, fork_tier = EXCLUDED.fork_tier,
            has_red_flag = EXCLUDED.has_red_flag, red_flag_details = EXCLUDED.red_flag_details,
            gears = EXCLUDED.gears, extracted_at = CURRENT_TIMESTAMP
        """, (
            listing_id, specs.get("brand"), specs.get("model"), specs.get("model_year"),
            specs.get("category"), specs.get("suspension_type"), specs.get("travel_front_mm"),
            specs.get("travel_rear_mm"), specs.get("frame_size"), specs.get("motor_brand"),
            specs.get("motor_model"), specs.get("motor_torque_nm"),
            None if motor_verified is None else (1 if motor_verified else 0),
            specs.get("battery_capacity_wh"),
            specs.get("odometer_km"), specs.get("brakes_model"), specs.get("brakes_tier"),
            specs.get("fork_tier"), 1 if specs.get("has_red_flag") else 0,
            json.dumps(specs.get("red_flag_details", [])), specs.get("gears")
        ))
        self.conn.commit()

    def save_score(self, listing_id: str, score_data: Dict[str, Any]):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT INTO scores (
            listing_id, score_total, score_price_value, score_component_quality,
            score_condition_mileage, score_location_proximity, score_fit_geometry,
            is_deal_target, breakdown_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (listing_id) DO UPDATE SET
            score_total = EXCLUDED.score_total, score_price_value = EXCLUDED.score_price_value,
            score_component_quality = EXCLUDED.score_component_quality,
            score_condition_mileage = EXCLUDED.score_condition_mileage,
            score_location_proximity = EXCLUDED.score_location_proximity,
            score_fit_geometry = EXCLUDED.score_fit_geometry,
            is_deal_target = EXCLUDED.is_deal_target, breakdown_json = EXCLUDED.breakdown_json,
            calculated_at = CURRENT_TIMESTAMP
        """, (
            listing_id, score_data["score_total"], score_data["score_price_value"],
            score_data["score_component_quality"], score_data["score_condition_mileage"],
            score_data["score_location_proximity"], score_data["score_fit_geometry"],
            1 if score_data.get("is_deal_target") else 0,
            json.dumps(score_data.get("breakdown", {}))
        ))
        self.conn.commit()

    def save_user_analysis(self, listing_id: str, analysis: str):
        """Save user's verdict/analysis for a listing."""
        cursor = self.conn.cursor()
        cursor.execute("""
        UPDATE listings SET user_analysis = %s WHERE id = %s
        """, (analysis, listing_id))
        self.conn.commit()

    def get_listings_needing_ai_analysis(
        self, limit: int = 200, force: bool = False, listing_id: Optional[str] = None,
        listing_ids: Optional[List[str]] = None, id_range: Optional[Tuple[int, int]] = None,
        problematic_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Listings due for an AI read: never analyzed yet, or analyzed
        before their most recent price drop.

        Three modes (analyze.py flags):
          default            — due listings, minus automatic rejections no
                               spec correction could overturn;
          problematic_only   — listings with spec gaps the AI could fix
                               (filters.spec_problems), analyzed or not;
          force              — every in-scope listing, rejections included.
        The re-run modes return never-analyzed listings first, then the
        stalest, so a `limit` works as a resumable batch size.

        In scope: everything except SOLD/DELISTED (genuinely off the
        market — no decision left to make either way) and a listing you
        explicitly rejected by hand with no other reason
        (rejection_reason == MANUAL_REJECT_REASON — you already looked at
        it and said no, so leave that alone). That deliberately INCLUDES
        listings rejected by the original scan's own hard filters (no
        motor detected, wrong size, weak motor/battery) — the regex
        parser can miss a spec that's actually spelled out in the
        description (an odd phrasing, a typo, text split across lines),
        so a listing rejected purely on a regex miss deserves the AI's
        eyes too, not silence. Its corrected_specs can then restore it to
        ACTIVE — see pipeline/corrections.py.

        listing_id / listing_ids / id_range: skip all of the above and
        return just those listings (any status) — for testing the AI pass
        against a hand-picked set without touching the rest. listing_id is
        a single already-resolved id; listing_ids is a list of already-
        resolved ids; id_range is an inclusive (min, max) numeric_id range
        (the short numeric id shown in the dashboard) — the three are
        mutually exclusive, listing_id taking priority if more than one is
        passed. force: re-send every in-scope listing regardless of
        whether it was already analyzed — for deliberately re-running the
        AI after a prompt change, at the cost of one API call per listing
        it processes."""
        cursor = self.conn.cursor()
        base_select = """
        SELECT l.id, l.portal, l.portal_id, l.url, l.title, l.description_raw,
               l.price_chf, l.distance_km, l.status, l.rejection_reason, l.ai_analyzed_at,
               s.brand, s.model, s.motor_brand, s.motor_model, s.motor_torque_nm, s.motor_verified,
               s.battery_capacity_wh, s.frame_size, s.suspension_type, s.travel_front_mm,
               s.travel_rear_mm, s.model_year,
               s.brakes_tier, s.odometer_km, s.red_flag_details,
               sc.score_total
        FROM listings l
        LEFT JOIN specifications s ON l.id = s.listing_id
        LEFT JOIN scores sc ON l.id = sc.listing_id
        """

        if listing_id is not None:
            cursor.execute(base_select + " WHERE l.id = %s", (listing_id,))
            return [dict(row) for row in cursor.fetchall()]

        if listing_ids is not None:
            if not listing_ids:
                return []
            placeholders = ",".join("%s" for _ in listing_ids)
            cursor.execute(base_select + f" WHERE l.id IN ({placeholders})", listing_ids)
            return [dict(row) for row in cursor.fetchall()]

        if id_range is not None:
            lo, hi = id_range
            cursor.execute(base_select + " WHERE l.numeric_id BETWEEN %s AND %s", (lo, hi))
            return [dict(row) for row in cursor.fetchall()]

        scope_filter = (
            "WHERE l.status NOT IN ('SOLD', 'DELISTED')"
            " AND NOT (l.status = 'REJECTED' AND l.rejection_reason = %s)"
            " AND l.status_locked = 0"
        )
        params: List[Any] = [MANUAL_REJECT_REASON]
        if force or problematic_only:
            # Re-runs: never-analyzed first, then the stalest analysis — so
            # repeated `--force --limit N` runs walk through the whole
            # backlog instead of redoing the same N listings every time.
            order = " ORDER BY l.ai_analyzed_at IS NOT NULL, l.ai_analyzed_at ASC, sc.score_total DESC"
        else:
            scope_filter += (
                " AND (l.ai_analysis IS NULL"
                " OR (l.status = 'PRICE_DROP' AND (l.ai_analyzed_at IS NULL OR l.ai_analyzed_at < l.last_seen_at)))"
            )
            order = " ORDER BY sc.score_total DESC"
        cursor.execute(base_select + scope_filter + order, params)
        rows = [dict(row) for row in cursor.fetchall()]

        if problematic_only:
            # Only listings whose specs the AI could actually fix — see
            # filters.spec_problems — even if already analyzed.
            rows = [row for row in rows if spec_problems(row)]
        elif not force:
            # An automatic rejection is only worth an AI read when a spec
            # correction could overturn it (filters.is_correctable_rejection)
            # — over budget, too far, hardtail, wrong category or red flags
            # stay rejected whatever the AI reads. --force still sends them.
            rows = [
                row for row in rows
                if row["status"] != "REJECTED" or is_correctable_rejection(row["rejection_reason"])
            ]
        return rows[:limit]

    def resolve_listing_id(self, value: str) -> Optional[str]:
        """Accept either a listing's real id (e.g. "tutti_12345") or the
        short numeric id shown in the dashboard (listings.numeric_id) and
        return the real id, or None if neither matches. Lets --id on the
        CLI take whichever one you can see."""
        cursor = self.conn.cursor()
        if value.isdigit():
            cursor.execute("SELECT id FROM listings WHERE numeric_id = %s", (int(value),))
            row = cursor.fetchone()
            if row:
                return row["id"]
        cursor.execute("SELECT id FROM listings WHERE id = %s", (value,))
        row = cursor.fetchone()
        return row["id"] if row else None

    def get_high_score_ai_exclusions(self, min_score: float = 70.0) -> List[Dict[str, Any]]:
        """Diagnostic for "why didn't analyze.py touch this listing" — every
        listing scoring >= min_score that get_listings_needing_ai_analysis()
        is NOT currently returning, with the reason: SOLD/DELISTED (off the
        market), an explicit manual "Scarta" with no other reason (your own
        decision, left alone on purpose), or already analyzed (needs
        --force to redo). A REJECTED listing with an automatic reason (the
        scan's hard filters, or a spec correction) is NOT excluded by
        status alone anymore — see get_listings_needing_ai_analysis."""
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT l.id, l.numeric_id AS numeric_id, l.title, l.status, l.rejection_reason,
               l.ai_analysis, l.ai_analyzed_at, l.last_seen_at,
               sc.score_total
        FROM listings l
        LEFT JOIN scores sc ON l.id = sc.listing_id
        WHERE COALESCE(sc.score_total, 0) >= %s
        ORDER BY sc.score_total DESC
        """, (min_score,))

        excluded = []
        for row in cursor.fetchall():
            row = dict(row)
            if row["status"] in ("SOLD", "DELISTED"):
                row["reason"] = f"stato {row['status']} (non più sul mercato)"
            elif row["status"] == "REJECTED" and row["rejection_reason"] == MANUAL_REJECT_REASON:
                row["reason"] = "scartata manualmente da te — lasciata invariata"
            elif row["status"] == "REJECTED" and not is_correctable_rejection(row["rejection_reason"]):
                row["reason"] = "scartata per un motivo che nessuna correzione delle specifiche può cambiare"
            elif row["ai_analysis"] is not None:
                due_for_recheck = (
                    row["status"] == "PRICE_DROP"
                    and (row["ai_analyzed_at"] is None or row["ai_analyzed_at"] < row["last_seen_at"])
                )
                if due_for_recheck:
                    continue
                row["reason"] = "già analizzata in precedenza — usa --force per ripeterla"
            else:
                continue  # genuinely eligible right now, nothing to explain
            excluded.append(row)
        return excluded

    MIN_DESCRIPTION_CHARS = 40

    def _drop_blind_ai_analysis(self, listing_id: str, new_description: str):
        """An AI verdict written while the description was missing ("motore non
        dichiarato", ...) is worthless once the real text arrives — clear it so
        the next analyze run redoes it."""
        if len((new_description or "").strip()) < self.MIN_DESCRIPTION_CHARS:
            return
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE listings SET ai_analysis = NULL, ai_score = NULL, ai_analyzed_at = NULL "
            "WHERE id = %s AND ai_analysis IS NOT NULL AND length(trim(coalesce(description_raw, ''))) < %s",
            (listing_id, self.MIN_DESCRIPTION_CHARS),
        )

    def update_description_raw(self, listing_id: str, description_raw: str):
        """Persist a description fetched live during the AI pass (analyze.py)
        when the stored one was missing or too thin — so the enrichment
        survives beyond this one run instead of being re-fetched every time."""
        self._drop_blind_ai_analysis(listing_id, description_raw)
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE listings SET description_raw = %s WHERE id = %s",
            (description_raw, listing_id),
        )
        self.conn.commit()

    def save_ai_analysis(self, listing_id: str, ai_analysis: str, ai_score: float):
        """Save Claude's verdict for a listing. Additive only — never touches
        scores.score_total, so get_top_deals()'s filtering is unaffected."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        UPDATE listings SET ai_analysis = %s, ai_score = %s, ai_analyzed_at = %s WHERE id = %s
        """, (ai_analysis, ai_score, now, listing_id))
        self.conn.commit()

    def mark_sold_or_delisted(self, listing_id: str, status: str = "SOLD"):
        """Mark listing as SOLD or DELISTED."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        UPDATE listings SET status = %s, delisted_at = %s WHERE id = %s
        """, (status, now, listing_id))
        self.conn.commit()

    def set_manual_status(self, listing_id: str, status: str, reason: Optional[str] = None):
        """User-driven status override from the interactive dashboard
        (server.py) — REJECTED ("non mi piace"), SOLD, or ACTIVE (undo).
        Distinct from mark_sold_or_delisted(), which the scanner itself uses
        for automated 404-detected SOLD marks; this one also clears/sets
        rejection_reason so a restored listing doesn't carry a stale one.

        A REJECTED with no reason (the user's own "Scarta") and a SOLD lock
        the status, so the next scan can't flip it back to ACTIVE; a REJECTED
        with a reason (pipeline/corrections.py's automatic re-check) and an
        ACTIVE restore leave it unlocked."""
        if status not in ("REJECTED", "SOLD", "ACTIVE"):
            raise ValueError(f"Unsupported manual status: {status!r}")
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        if status == "REJECTED":
            cursor.execute(
                "UPDATE listings SET status = %s, rejection_reason = %s, delisted_at = %s, status_locked = %s WHERE id = %s",
                (status, reason or MANUAL_REJECT_REASON, now, 0 if reason else 1, listing_id),
            )
        elif status == "SOLD":
            cursor.execute(
                "UPDATE listings SET status = %s, rejection_reason = NULL, delisted_at = %s, status_locked = 1 WHERE id = %s",
                (status, now, listing_id),
            )
        else:  # ACTIVE — undo a manual reject/sold
            cursor.execute(
                "UPDATE listings SET status = %s, rejection_reason = NULL, delisted_at = NULL, status_locked = 0 WHERE id = %s",
                (status, listing_id),
            )
        self.conn.commit()

    @_atomic
    def save_spec_overrides(self, listing_id: str, fields: Dict[str, Any]) -> None:
        """Remember hand/AI-corrected spec values so the next scan applies them
        on top of the parser's output instead of overwriting them. A None/""
        value means "I don't actually know this" — it drops the override and
        lets the parser decide again."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        for field, value in fields.items():
            if value is None or value == "":
                cursor.execute(
                    "DELETE FROM spec_overrides WHERE listing_id = %s AND field = %s", (listing_id, field)
                )
            else:
                cursor.execute(
                    "INSERT INTO spec_overrides (listing_id, field, value_json, updated_at)"
                    " VALUES (%s, %s, %s, %s)"
                    " ON CONFLICT (listing_id, field) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = EXCLUDED.updated_at",
                    (listing_id, field, json.dumps(value), now),
                )
        self.conn.commit()

    def get_spec_overrides(self, listing_id: str) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT field, value_json FROM spec_overrides WHERE listing_id = %s", (listing_id,))
        return {row["field"]: json.loads(row["value_json"]) for row in cursor.fetchall()}

    @_atomic
    def toggle_favorite(self, listing_id: str) -> bool:
        """Flip is_favorite for a listing and return the new value. A
        favorite is independent of status (ACTIVE/REJECTED/SOLD/...) — a
        starred listing keeps its star even after being marked sold, so it
        isn't lost from view once you've flagged it as one you actually want."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT is_favorite FROM listings WHERE id = %s", (listing_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Unknown listing_id: {listing_id!r}")
        new_value = 0 if row["is_favorite"] else 1
        cursor.execute("UPDATE listings SET is_favorite = %s WHERE id = %s", (new_value, listing_id))
        self.conn.commit()
        return bool(new_value)

    @_atomic
    def delete_listing(self, listing_id: str) -> None:
        """Physically delete a listing and all its related data from the DB,
        and remember the id so the next scan doesn't bring it back as new."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM listings WHERE id = %s", (listing_id,))
        cursor.execute("INSERT INTO deleted_listings (listing_id) VALUES (%s) ON CONFLICT DO NOTHING", (listing_id,))
        self.conn.commit()

    def is_deleted(self, listing_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM deleted_listings WHERE listing_id = %s", (listing_id,))
        return cursor.fetchone() is not None

    def mark_unavailable(self, listing_id: str) -> bool:
        """The portal says this listing is sold/expired/removed: mark it SOLD
        unless the user already decided on it by hand. Returns True if a
        live listing was actually switched off."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE listings SET status = 'SOLD', delisted_at = %s, last_checked_at = %s"
            " WHERE id = %s AND status_locked = 0 AND status IN ('ACTIVE', 'PRICE_DROP', 'NEW', 'REJECTED')",
            (now, now, listing_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def mark_checked(self, listing_id: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE listings SET last_checked_at = %s WHERE id = %s",
            (datetime.now(timezone.utc).isoformat(), listing_id),
        )
        self.conn.commit()

    def get_listings_to_verify(self, not_seen_since: str, limit: int) -> List[Dict[str, Any]]:
        """Live listings the latest scan did NOT see in any search result
        (last_seen_at before this scan started) — the ones that may have been
        sold or removed. Least recently checked first, so a per-run cap still
        cycles through all of them over successive scans."""
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT id, portal, portal_id, url FROM listings
        WHERE status IN ('ACTIVE', 'PRICE_DROP', 'NEW') AND last_seen_at < %s
        ORDER BY last_checked_at ASC
        LIMIT %s
        """, (not_seen_since, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_listing_with_specs(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one listing's price/distance plus its full specifications
        row, flattened into a single dict — everything the scoring engine
        and save_specifications() need to apply and persist a manual spec
        correction from the dashboard."""
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT l.id, l.price_chf, l.distance_km, l.status, l.rejection_reason, l.status_locked,
               s.brand, s.model, s.model_year, s.category, s.suspension_type,
               s.travel_front_mm, s.travel_rear_mm, s.frame_size, s.motor_brand,
               s.motor_model, s.motor_torque_nm, s.motor_verified, s.battery_capacity_wh,
               s.odometer_km, s.brakes_model, s.brakes_tier, s.fork_tier,
               s.has_red_flag, s.red_flag_details
        FROM listings l
        LEFT JOIN specifications s ON l.id = s.listing_id
        WHERE l.id = %s
        """, (listing_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_top_deals(self, min_score: float = 65.0, limit: int = 50) -> List[Dict[str, Any]]:
        """Entry into the list stays fully deterministic (score_total >= min_score)
        — the AI never rescues a listing that failed the heuristic bar. Order
        within it blends in Claude's read: ranking_score = 0.6*score_total +
        0.4*ai_score once a listing has been AI-analyzed, else score_total alone
        (a listing not yet analyzed isn't penalized for having no ai_score)."""
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT l.*, s.motor_model, s.motor_torque_nm, s.battery_capacity_wh, s.frame_size,
               s.travel_front_mm, s.brakes_tier, sc.score_total, sc.score_price_value,
               sc.score_component_quality, sc.is_deal_target,
               CASE WHEN l.ai_score IS NOT NULL THEN 0.6 * sc.score_total + 0.4 * l.ai_score
                    ELSE sc.score_total END AS ranking_score
        FROM listings l
        JOIN scores sc ON l.id = sc.listing_id
        LEFT JOIN specifications s ON l.id = s.listing_id
        WHERE l.status IN ('ACTIVE', 'PRICE_DROP') AND sc.score_total >= %s
        ORDER BY ranking_score DESC, l.price_chf ASC
        LIMIT %s
        """, (min_score, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_filtered_top_deals(self, **filters) -> List[Dict[str, Any]]:
        """Get top deals with dynamic filtering. Filters: price_min, price_max, dist_max,
        motor_brand, battery_min, frame_size, year_min, year_max, score_min, status, fav_only, ai_only."""
        cursor = self.conn.cursor()

        price_min = filters.get('price_min')
        price_max = filters.get('price_max')
        dist_max = filters.get('dist_max')
        motor_brand = filters.get('motor_brand')
        battery_min = filters.get('battery_min')
        frame_size = filters.get('frame_size')
        year_min = filters.get('year_min')
        year_max = filters.get('year_max')
        score_min = filters.get('score_min', 60.0)
        status = filters.get('status')
        fav_only = filters.get('fav_only', False)
        ai_only = filters.get('ai_only', False)
        limit = filters.get('limit', 10)

        where_parts = ["sc.score_total >= %s"]
        params = [score_min]

        if price_min is not None:
            where_parts.append("l.price_chf >= %s")
            params.append(price_min)
        if price_max is not None:
            where_parts.append("l.price_chf <= %s")
            params.append(price_max)
        if dist_max is not None:
            where_parts.append("l.distance_km <= %s")
            params.append(dist_max)
        if motor_brand:
            where_parts.append("s.motor_brand = %s")
            params.append(motor_brand)
        if battery_min is not None:
            where_parts.append("s.battery_capacity_wh >= %s")
            params.append(battery_min)
        if frame_size:
            where_parts.append("s.frame_size = %s")
            params.append(frame_size)
        if year_min is not None:
            where_parts.append("s.model_year >= %s")
            params.append(year_min)
        if year_max is not None:
            where_parts.append("s.model_year <= %s")
            params.append(year_max)
        if status == 'active':
            where_parts.append("l.status IN ('ACTIVE', 'PRICE_DROP')")
        elif status == 'rejected':
            where_parts.append("l.status = 'REJECTED'")
        elif status == 'sold':
            where_parts.append("l.status = 'SOLD'")
        elif filters.get('show_rejected'):
            where_parts.append("l.status IN ('ACTIVE', 'PRICE_DROP', 'REJECTED', 'SOLD', 'DELISTED')")
        else:
            where_parts.append("l.status IN ('ACTIVE', 'PRICE_DROP', 'SOLD', 'DELISTED')")

        if fav_only:
            where_parts.append("l.is_favorite = 1")
        if ai_only:
            where_parts.append("l.ai_analysis IS NOT NULL")

        where_clause = " AND ".join(where_parts)

        query = f"""
        SELECT l.*, s.motor_model, s.motor_brand, s.motor_torque_nm, s.battery_capacity_wh, s.frame_size,
               s.travel_front_mm, s.brakes_tier, s.model_year, sc.score_total, sc.score_price_value,
               sc.score_component_quality, sc.is_deal_target,
               CASE WHEN l.ai_score IS NOT NULL THEN 0.6 * sc.score_total + 0.4 * l.ai_score
                    ELSE sc.score_total END AS ranking_score
        FROM listings l
        LEFT JOIN scores sc ON l.id = sc.listing_id
        LEFT JOIN specifications s ON l.id = s.listing_id
        WHERE {where_clause}
        ORDER BY ranking_score DESC NULLS LAST, l.price_chf ASC
        LIMIT %s
        """
        params.append(limit)
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_price_drops(self, limit: int = 20) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT l.*, sc.score_total,
               (SELECT price_raw FROM listing_snapshots WHERE listing_id = l.id ORDER BY captured_at ASC LIMIT 1) as original_price
        FROM listings l
        LEFT JOIN scores sc ON l.id = sc.listing_id
        WHERE l.status = 'PRICE_DROP' AND l.rejection_reason IS NULL
        ORDER BY l.last_checked_at DESC
        LIMIT %s
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()

    def __enter__(self):
        """Context manager entry — returns self for use in with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit — always closes connection, even on exception."""
        self.close()
        return False  # Propagate exceptions
