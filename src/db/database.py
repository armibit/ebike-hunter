import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


class Database:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._configure_db()
        self._init_schema()

    def _configure_db(self):
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA foreign_keys = ON;")
        self.conn.commit()

    def _init_schema(self):
        cursor = self.conn.cursor()

        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
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
            is_favorite INTEGER NOT NULL DEFAULT 0,
            dedupe_signature TEXT,
            image_phash TEXT,
            user_analysis TEXT,
            first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            delisted_at TIMESTAMP,
            CONSTRAINT uq_portal_item UNIQUE (portal, portal_id)
        );

        CREATE TABLE IF NOT EXISTS listing_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

        CREATE INDEX IF NOT EXISTS idx_listings_portal_status ON listings(portal, status);
        CREATE INDEX IF NOT EXISTS idx_listings_status_price ON listings(status, price_chf);
        CREATE INDEX IF NOT EXISTS idx_listings_dedupe ON listings(dedupe_signature);
        CREATE INDEX IF NOT EXISTS idx_scores_total ON scores(score_total DESC);
        CREATE INDEX IF NOT EXISTS idx_snapshots_listing ON listing_snapshots(listing_id, captured_at DESC);
        """)
        self.conn.commit()

        # Migration: add user_analysis column if missing (for older databases)
        cursor.execute("PRAGMA table_info(listings)")
        columns = [row[1] for row in cursor.fetchall()]
        if "user_analysis" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN user_analysis TEXT")
            self.conn.commit()

        # Migration: add AI-analysis columns if missing (for older databases).
        # Kept separate from score_total/user_analysis — ai_score is an
        # informational second opinion, never used to filter get_top_deals().
        if "ai_analysis" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN ai_analysis TEXT")
        if "ai_score" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN ai_score REAL")
        if "ai_analyzed_at" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN ai_analyzed_at TIMESTAMP")
        if "is_favorite" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()

        # Migration: add motor_verified to specifications if missing (older DBs).
        # NULL/1 = motor identified from an explicit model pattern; 0 = torque
        # is a placeholder guessed from a generic "e-bike" keyword only.
        cursor.execute("PRAGMA table_info(specifications)")
        spec_columns = [row[1] for row in cursor.fetchall()]
        if "motor_verified" not in spec_columns:
            cursor.execute("ALTER TABLE specifications ADD COLUMN motor_verified INTEGER")
            self.conn.commit()

    def upsert_listing(self, item: Dict[str, Any]) -> Tuple[str, bool, bool]:
        """
        Upserts listing.
        Returns: (listing_id, is_new, is_price_drop)
        """
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        portal = item["portal"]
        portal_id = str(item["portal_id"])
        listing_id = f"{portal}_{portal_id}"

        cursor.execute("SELECT id, price_raw, currency, price_chf, status FROM listings WHERE portal = ? AND portal_id = ?", (portal, portal_id))
        existing = cursor.fetchone()

        is_new = existing is None
        is_price_drop = False

        if is_new:
            cursor.execute("""
            INSERT INTO listings (
                id, portal, portal_id, url, title, description_raw, seller_id, seller_name,
                price_raw, currency, price_chf, price_eur, location_raw, location_normalized,
                region, latitude, longitude, distance_km, status, rejection_reason,
                dedupe_signature, image_phash, first_seen_at, last_seen_at, last_checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                listing_id, portal, portal_id, item["url"], item["title"],
                item.get("description_raw", ""), item.get("seller_id"), item.get("seller_name"),
                item["price_raw"], item["currency"], item["price_chf"], item.get("price_eur", item["price_chf"]),
                item.get("location_raw", ""), item.get("location_normalized", ""),
                item.get("region", ""), item.get("latitude"), item.get("longitude"),
                item.get("distance_km"), item.get("status", "NEW"), item.get("rejection_reason"),
                item.get("dedupe_signature", ""), item.get("image_phash"), now, now, now
            ))
            cursor.execute("""
            INSERT INTO listing_snapshots (listing_id, price_raw, currency, price_chf, status, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (listing_id, item["price_raw"], item["currency"], item["price_chf"], item.get("status", "NEW"), now))
        else:
            old_price = existing["price_raw"]
            new_price = item["price_raw"]
            old_status = existing["status"]
            requested_status = item.get("status", old_status)
            new_status = requested_status

            # Never let a price-drop promotion override an explicit rejection,
            # and ignore bogus 0/negative prices (failed scraping) as drops.
            if requested_status != "REJECTED" and new_price > 0 and old_price > 0 and new_price < old_price:
                is_price_drop = True
                new_status = "PRICE_DROP"
                cursor.execute("""
                INSERT INTO listing_snapshots (listing_id, price_raw, currency, price_chf, status, captured_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (listing_id, new_price, item["currency"], item["price_chf"], new_status, now))
            elif requested_status != "REJECTED" and old_status == "PRICE_DROP" and new_price == old_price:
                # Keep PRICE_DROP status — price hasn't recovered
                new_status = "PRICE_DROP"

            cursor.execute("""
            UPDATE listings SET
                title = ?, description_raw = ?, price_raw = ?, currency = ?,
                price_chf = ?, price_eur = ?, location_raw = ?, location_normalized = ?,
                region = ?, latitude = ?, longitude = ?, distance_km = ?,
                status = ?, rejection_reason = ?, last_seen_at = ?, last_checked_at = ?
            WHERE id = ?
            """, (
                item["title"], item.get("description_raw", ""), item["price_raw"], item["currency"],
                item["price_chf"], item.get("price_eur", item["price_chf"]), item.get("location_raw", ""),
                item.get("location_normalized", ""), item.get("region", ""), item.get("latitude"),
                item.get("longitude"), item.get("distance_km"), new_status, item.get("rejection_reason"),
                now, now, listing_id
            ))

        self.conn.commit()
        return listing_id, is_new, is_price_drop

    def save_specifications(self, listing_id: str, specs: Dict[str, Any]):
        cursor = self.conn.cursor()
        motor_verified = specs.get("motor_verified")
        cursor.execute("""
        INSERT OR REPLACE INTO specifications (
            listing_id, brand, model, model_year, category, suspension_type,
            travel_front_mm, travel_rear_mm, frame_size, motor_brand, motor_model,
            motor_torque_nm, motor_verified, battery_capacity_wh, odometer_km, brakes_model,
            brakes_tier, fork_tier, has_red_flag, red_flag_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_id, specs.get("brand"), specs.get("model"), specs.get("model_year"),
            specs.get("category"), specs.get("suspension_type"), specs.get("travel_front_mm"),
            specs.get("travel_rear_mm"), specs.get("frame_size"), specs.get("motor_brand"),
            specs.get("motor_model"), specs.get("motor_torque_nm"),
            None if motor_verified is None else (1 if motor_verified else 0),
            specs.get("battery_capacity_wh"),
            specs.get("odometer_km"), specs.get("brakes_model"), specs.get("brakes_tier"),
            specs.get("fork_tier"), 1 if specs.get("has_red_flag") else 0,
            json.dumps(specs.get("red_flag_details", []))
        ))
        self.conn.commit()

    def save_score(self, listing_id: str, score_data: Dict[str, Any]):
        cursor = self.conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO scores (
            listing_id, score_total, score_price_value, score_component_quality,
            score_condition_mileage, score_location_proximity, score_fit_geometry,
            is_deal_target, breakdown_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        UPDATE listings SET user_analysis = ? WHERE id = ?
        """, (analysis, listing_id))
        self.conn.commit()

    def get_listings_needing_ai_analysis(
        self, limit: int = 200, force: bool = False, listing_id: Optional[str] = None,
        listing_ids: Optional[List[str]] = None, id_range: Optional[Tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Listings due for an AI read: never analyzed yet, or analyzed
        before their most recent price drop.

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
        resolved ids; id_range is an inclusive (min, max) rowid range (the
        numeric id shown in the dashboard) — the three are mutually
        exclusive, listing_id taking priority if more than one is passed.
        force: re-send every in-scope listing regardless of whether it was
        already analyzed — for deliberately re-running the AI after a
        prompt change, at the cost of one API call per listing it
        processes."""
        cursor = self.conn.cursor()
        base_select = """
        SELECT l.id, l.portal, l.portal_id, l.url, l.title, l.description_raw,
               l.price_chf, l.distance_km, l.status, l.rejection_reason,
               s.brand, s.model, s.motor_brand, s.motor_model, s.motor_torque_nm, s.motor_verified,
               s.battery_capacity_wh, s.frame_size, s.suspension_type, s.travel_front_mm,
               s.brakes_tier, s.odometer_km, s.red_flag_details,
               sc.score_total
        FROM listings l
        LEFT JOIN specifications s ON l.id = s.listing_id
        LEFT JOIN scores sc ON l.id = sc.listing_id
        """

        if listing_id is not None:
            cursor.execute(base_select + " WHERE l.id = ?", (listing_id,))
            return [dict(row) for row in cursor.fetchall()]

        if listing_ids is not None:
            if not listing_ids:
                return []
            placeholders = ",".join("?" for _ in listing_ids)
            cursor.execute(base_select + f" WHERE l.id IN ({placeholders})", listing_ids)
            return [dict(row) for row in cursor.fetchall()]

        if id_range is not None:
            lo, hi = id_range
            cursor.execute(base_select + " WHERE l.rowid BETWEEN ? AND ?", (lo, hi))
            return [dict(row) for row in cursor.fetchall()]

        scope_filter = (
            "WHERE l.status NOT IN ('SOLD', 'DELISTED')"
            " AND NOT (l.status = 'REJECTED' AND l.rejection_reason = ?)"
        )
        params: List[Any] = [MANUAL_REJECT_REASON]
        if not force:
            scope_filter += (
                " AND (l.ai_analysis IS NULL"
                " OR (l.status = 'PRICE_DROP' AND (l.ai_analyzed_at IS NULL OR l.ai_analyzed_at < l.last_seen_at)))"
            )
        params.append(limit)
        cursor.execute(
            base_select + scope_filter + " ORDER BY sc.score_total DESC LIMIT ?", params
        )
        return [dict(row) for row in cursor.fetchall()]

    def resolve_listing_id(self, value: str) -> Optional[str]:
        """Accept either a listing's real id (e.g. "tutti_12345") or the
        short numeric id shown in the dashboard (SQLite's own rowid — no
        extra column needed) and return the real id, or None if neither
        matches. Lets --id on the CLI take whichever one you can see."""
        cursor = self.conn.cursor()
        if value.isdigit():
            cursor.execute("SELECT id FROM listings WHERE rowid = ?", (int(value),))
            row = cursor.fetchone()
            if row:
                return row["id"]
        cursor.execute("SELECT id FROM listings WHERE id = ?", (value,))
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
        SELECT l.id, l.rowid AS numeric_id, l.title, l.status, l.rejection_reason,
               l.ai_analysis, l.ai_analyzed_at, l.last_seen_at,
               sc.score_total
        FROM listings l
        LEFT JOIN scores sc ON l.id = sc.listing_id
        WHERE COALESCE(sc.score_total, 0) >= ?
        ORDER BY sc.score_total DESC
        """, (min_score,))

        excluded = []
        for row in cursor.fetchall():
            row = dict(row)
            if row["status"] in ("SOLD", "DELISTED"):
                row["reason"] = f"stato {row['status']} (non più sul mercato)"
            elif row["status"] == "REJECTED" and row["rejection_reason"] == MANUAL_REJECT_REASON:
                row["reason"] = "scartata manualmente da te — lasciata invariata"
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

    def update_description_raw(self, listing_id: str, description_raw: str):
        """Persist a description fetched live during the AI pass (analyze.py)
        when the stored one was missing or too thin — so the enrichment
        survives beyond this one run instead of being re-fetched every time."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE listings SET description_raw = ? WHERE id = ?",
            (description_raw, listing_id),
        )
        self.conn.commit()

    def save_ai_analysis(self, listing_id: str, ai_analysis: str, ai_score: float):
        """Save Claude's verdict for a listing. Additive only — never touches
        scores.score_total, so get_top_deals()'s filtering is unaffected."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        UPDATE listings SET ai_analysis = ?, ai_score = ?, ai_analyzed_at = ? WHERE id = ?
        """, (ai_analysis, ai_score, now, listing_id))
        self.conn.commit()

    def mark_sold_or_delisted(self, listing_id: str, status: str = "SOLD"):
        """Mark listing as SOLD or DELISTED."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        UPDATE listings SET status = ?, delisted_at = ? WHERE id = ?
        """, (status, now, listing_id))
        self.conn.commit()

    def set_manual_status(self, listing_id: str, status: str, reason: Optional[str] = None):
        """User-driven status override from the interactive dashboard
        (server.py) — REJECTED ("non mi piace"), SOLD, or ACTIVE (undo).
        Distinct from mark_sold_or_delisted(), which the scanner itself uses
        for automated 404-detected SOLD marks; this one also clears/sets
        rejection_reason so a restored listing doesn't carry a stale one."""
        if status not in ("REJECTED", "SOLD", "ACTIVE"):
            raise ValueError(f"Unsupported manual status: {status!r}")
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        if status == "REJECTED":
            cursor.execute(
                "UPDATE listings SET status = ?, rejection_reason = ?, delisted_at = ? WHERE id = ?",
                (status, reason or MANUAL_REJECT_REASON, now, listing_id),
            )
        elif status == "SOLD":
            cursor.execute(
                "UPDATE listings SET status = ?, rejection_reason = NULL, delisted_at = ? WHERE id = ?",
                (status, now, listing_id),
            )
        else:  # ACTIVE — undo a manual reject/sold
            cursor.execute(
                "UPDATE listings SET status = ?, rejection_reason = NULL, delisted_at = NULL WHERE id = ?",
                (status, listing_id),
            )
        self.conn.commit()

    def toggle_favorite(self, listing_id: str) -> bool:
        """Flip is_favorite for a listing and return the new value. A
        favorite is independent of status (ACTIVE/REJECTED/SOLD/...) — a
        starred listing keeps its star even after being marked sold, so it
        isn't lost from view once you've flagged it as one you actually want."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT is_favorite FROM listings WHERE id = ?", (listing_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Unknown listing_id: {listing_id!r}")
        new_value = 0 if row["is_favorite"] else 1
        cursor.execute("UPDATE listings SET is_favorite = ? WHERE id = ?", (new_value, listing_id))
        self.conn.commit()
        return bool(new_value)

    def get_listing_with_specs(self, listing_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one listing's price/distance plus its full specifications
        row, flattened into a single dict — everything the scoring engine
        and save_specifications() need to apply and persist a manual spec
        correction from the dashboard."""
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT l.id, l.price_chf, l.distance_km, l.status, l.rejection_reason,
               s.brand, s.model, s.model_year, s.category, s.suspension_type,
               s.travel_front_mm, s.travel_rear_mm, s.frame_size, s.motor_brand,
               s.motor_model, s.motor_torque_nm, s.motor_verified, s.battery_capacity_wh,
               s.odometer_km, s.brakes_model, s.brakes_tier, s.fork_tier,
               s.has_red_flag, s.red_flag_details
        FROM listings l
        LEFT JOIN specifications s ON l.id = s.listing_id
        WHERE l.id = ?
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
        WHERE l.status IN ('ACTIVE', 'PRICE_DROP') AND sc.score_total >= ?
        ORDER BY ranking_score DESC, l.price_chf ASC
        LIMIT ?
        """, (min_score, limit))
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
        LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
