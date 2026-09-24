import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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

        # Check if user_analysis column exists; if not, add it
        cursor.execute("PRAGMA table_info(listings)")
        columns = [row[1] for row in cursor.fetchall()]
        if "user_analysis" not in columns:
            cursor.execute("ALTER TABLE listings ADD COLUMN user_analysis TEXT")
            self.conn.commit()

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
            new_status = item.get("status", old_status)

            if new_price < old_price:
                is_price_drop = True
                new_status = "PRICE_DROP"
                cursor.execute("""
                INSERT INTO listing_snapshots (listing_id, price_raw, currency, price_chf, status, captured_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (listing_id, new_price, item["currency"], item["price_chf"], new_status, now))
            elif old_status == "PRICE_DROP" and new_price == old_price:
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
        cursor.execute("""
        INSERT OR REPLACE INTO specifications (
            listing_id, brand, model, model_year, category, suspension_type,
            travel_front_mm, travel_rear_mm, frame_size, motor_brand, motor_model,
            motor_torque_nm, battery_capacity_wh, odometer_km, brakes_model,
            brakes_tier, fork_tier, has_red_flag, red_flag_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            listing_id, specs.get("brand"), specs.get("model"), specs.get("model_year"),
            specs.get("category"), specs.get("suspension_type"), specs.get("travel_front_mm"),
            specs.get("travel_rear_mm"), specs.get("frame_size"), specs.get("motor_brand"),
            specs.get("motor_model"), specs.get("motor_torque_nm"), specs.get("battery_capacity_wh"),
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

    def mark_sold_or_delisted(self, listing_id: str, status: str = "SOLD"):
        """Mark listing as SOLD or DELISTED."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        UPDATE listings SET status = ?, delisted_at = ? WHERE id = ?
        """, (status, now, listing_id))
        self.conn.commit()

    def get_top_deals(self, min_score: float = 65.0, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
        SELECT l.*, s.motor_model, s.motor_torque_nm, s.battery_capacity_wh, s.frame_size,
               s.travel_front_mm, s.brakes_tier, sc.score_total, sc.score_price_value,
               sc.score_component_quality, sc.is_deal_target
        FROM listings l
        JOIN scores sc ON l.id = sc.listing_id
        LEFT JOIN specifications s ON l.id = s.listing_id
        WHERE l.status IN ('ACTIVE', 'PRICE_DROP') AND sc.score_total >= ?
        ORDER BY sc.score_total DESC, l.price_chf ASC
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
        WHERE l.status = 'PRICE_DROP'
        ORDER BY l.last_checked_at DESC
        LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
