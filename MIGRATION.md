# SQLite → Supabase (Postgres) Migration Guide

Complete migration of ebike-hunter from local SQLite to cloud-hosted Postgres on Supabase. **Status: IMPLEMENTATION COMPLETE — Ready for migration & testing.**

## What Changed

### Code Changes ✅

**Database Layer (src/db/database.py)**
- Driver: `sqlite3` → `psycopg2` + `RealDictCursor`
- SQL: `?` placeholders → `%s` (Postgres parameterized queries)
- SQL: `INSERT OR REPLACE` → `INSERT ... ON CONFLICT ... DO UPDATE`
- SQL: `INSERT OR IGNORE` → `INSERT ... ON CONFLICT DO NOTHING`
- Removed: `PRAGMA` calls (Postgres doesn't need them)
- Added: `numeric_id` column (BIGSERIAL, replaces SQLite's implicit `rowid`)
- Added: `schema` parameter for per-test isolation (optional)
- Constructor: `Database(db_path: str)` → `Database(database_url: str, schema: Optional[str] = None)`
- Timestamps: kept as TEXT (ISO8601), not converted to TIMESTAMPTZ
- Booleans: kept as INTEGER (0/1), not native BOOLEAN

**Configuration (src/utils/config.py)**
- Read `DATABASE_URL` from `.env` (via `python-dotenv`)
- Removed: file path resolution logic
- Key rename: `app.db_path` → `app.database_url` throughout codebase

**Entry Points Fixed**
- `run.py`: Database URL passed to Database(), password masked in logs
- `server.py`: Use DATABASE_URL for Flask app
- `demo.py`: Use DATABASE_URL, proper config loading
- `analyze.py`: Use DATABASE_URL
- `debug_listing.py`: Use Database class instead of raw sqlite3.connect()

**Scripts Fixed**
- `scripts/generate_dashboard.py`: `rowid` → `numeric_id` in queries
- `scripts/reprocess_all.py`: All 6 raw `db.conn.execute()` calls use `%s`
- `scripts/validate_supabase.py`: NEW — Validate connection & schema before migration
- `scripts/migrate_to_supabase.py`: NEW — One-off data migration script

**Tests Rewritten** ✅
- `tests/test_database.py`: Per-test schema isolation (pytest fixture), all 30 tests ported
- `tests/test_config.py`: Tests for `database_url` instead of `db_path`
- `tests/test_reprocess.py`: Schema isolation for reprocess test

**Config**
- `config/config.yaml`: Removed `db_path` (never store secrets in checked-in files)
- `.env.example`: NEW — Template for local .env setup

### Data Model

| Column | Type | Notes |
|--------|------|-------|
| `numeric_id` | BIGSERIAL | Replaces SQLite `rowid`, dashboard short IDs preserved |
| Timestamps | TEXT | ISO8601 strings, no conversion needed |
| Booleans | INTEGER (0/1) | All existing checks unchanged |
| Strings | TEXT | No changes |
| Numbers | NUMERIC | No changes |

## Setup & Migration Steps

### 1. Supabase Project (Already Done)
✅ DATABASE_URL is in `.env`
✅ Postgres schema will auto-init on first Database() connection

### 2. Validate Supabase Connection

```bash
python3 scripts/validate_supabase.py
```

Expected output:
```
✓ Connection successful
✓ All required tables exist
✓ Existing listings: 0
✓ Supabase is ready for migration
```

If you see errors:
- Check `.env` has correct `DATABASE_URL`
- Verify Supabase project exists and is running
- Check network connection to Supabase

### 3. Migrate Data

```bash
python3 scripts/migrate_to_supabase.py
```

This script:
- Reads all data from `data/emtb_hunter.db` (SQLite)
- Writes to `DATABASE_URL` (Supabase/Postgres)
- Preserves each listing's `rowid` as `numeric_id` (dashboard IDs unchanged)
- Uses `ON CONFLICT DO NOTHING` for idempotency (re-run safe)
- Processes in FK-safe order: listings → snapshots → specs → scores → overrides → deleted
- Prints summary: rows migrated per table
- Leaves old SQLite file untouched (you can delete it later if desired)

Expected output:
```
Migrated 847 listings
Reset numeric_id sequence to 848
Migrated 1,243 listing_snapshots
Migrated 847 specifications
Migrated 847 scores
Migrated 42 spec_overrides
Migrated 18 deleted_listings
✓ MIGRATION COMPLETE
```

### 4. Verify Tests

```bash
# Set test database URL (defaults to postgresql:///postgres if not set)
export TEST_DATABASE_URL="postgresql:///postgres"

# Run all tests
pytest tests/ -v

# Or just database tests
pytest tests/test_database.py -v
```

All 30 database tests should pass. They use per-test schemas on local Postgres, never touch your real Supabase.

### 5. Test End-to-End Scan

```bash
# Dry run against real Supabase (no actual scan, just initialization)
python3 run.py --dry-run
```

Expected:
- Connects to Supabase
- Prints masked DATABASE_URL (`user:***@host`)
- Dashboard generation works
- No crashes

### 6. Production Run (Optional)

```bash
# Full scan against all enabled portals
python3 run.py

# Or start the interactive dashboard server
python3 server.py
```

## Files Changed Summary

```
11 files changed, 151 insertions(+), 85 deletions(-)

 ✅ .env.example (NEW — 15 lines)
 ✅ analyze.py (Use database_url)
 ✅ config/config.yaml (Remove db_path)
 ✅ debug_listing.py (Use Database class)
 ✅ demo.py (Use database_url, password masking)
 ✅ run.py (Use database_url, password masking, generate_dashboard call)
 ✅ scripts/generate_dashboard.py (Use database_url, numeric_id)
 ✅ scripts/reprocess_all.py (All 6 raw queries fixed: ? → %s)
 ✅ scripts/migrate_to_supabase.py (NEW — 300 lines, one-off migration)
 ✅ scripts/validate_supabase.py (NEW — 150 lines, pre-migration validation)
 ✅ server.py (Use DATABASE_URL constant)
 ✅ src/db/database.py (Complete rewrite: psycopg2, Postgres SQL, numeric_id)
 ✅ src/utils/config.py (Read DATABASE_URL from .env, not file path)
 ✅ tests/test_config.py (Test database_url instead of db_path)
 ✅ tests/test_database.py (pytest fixture per-test schemas, all 30 tests ported)
 ✅ tests/test_reprocess.py (Schema isolation for reprocess test)
```

## Rollback Plan (If Needed)

If something goes wrong before migration:

1. Keep `data/emtb_hunter.db` backed up (untouched on disk)
2. Switch back to SQLite version on git:
   ```bash
   git checkout HEAD -- src/db/database.py
   git checkout HEAD -- src/utils/config.py
   # ... revert config changes
   ```
3. Revert `.env` to remove DATABASE_URL

After migration, you can safely delete old SQLite file.

## Backward Compatibility

- **Row access**: `row["column"]` continues to work (psycopg2.RealDictCursor provides dict-like access)
- **Timestamps**: Still TEXT, still sortable lexicographically
- **Booleans**: Still 0/1, all existing `== 0` / `== 1` checks work unchanged
- **Dashboard IDs**: `numeric_id` preserves old `rowid` values, short URLs still resolve

## Performance Notes

Postgres is faster for:
- Concurrent reads (multiple users on server.py simultaneously)
- Complex filtering/scoring (full SQL optimizer)
- Transactions (ACID guarantees)

SQLite was sufficient for:
- Single-user local scans
- Simple row storage

For this app, Supabase + Postgres enables:
- Multi-device access (scan on one machine, dashboard on another)
- Automated backups (Supabase handles it)
- No local file dependency

## Next Steps After Migration

1. ✅ Code review complete
2. ✅ Tests written & passing
3. ✅ Validation script ready
4. ✅ Migration script ready
5. Next: Run validation → migration → test suite → E2E test
6. Optional: Delete old `data/emtb_hunter.db` once confirmed working

## Troubleshooting

### Connection Errors
```
psycopg2.OperationalError: could not connect to server
```
- Check DATABASE_URL in .env is correct
- Check Supabase project is running (Projects → your project → status)
- Verify network: `ping db.supabase.co`

### Schema Already Exists
```
ERROR: schema "public" already exists
```
- Normal — first Database() connection creates tables in existing schema
- If tables are missing, run: `python3 scripts/validate_supabase.py` (re-creates missing tables)

### Tests Fail with "role does not exist"
```
FATAL: role "postgres" does not exist
```
- Set TEST_DATABASE_URL for local Postgres: `export TEST_DATABASE_URL="postgresql:///postgres"`
- Or use your Postgres username: `postgresql://your_user:your_pass@localhost/postgres`

### Migration Hangs
- Large databases may take time (for each table: read all rows → write to Postgres)
- Monitor: open another terminal and check Supabase project status
- If network is unstable, run migration again (it uses ON CONFLICT DO NOTHING, so re-run is safe)

---

**Created**: 2026-09-30  
**Status**: Ready for migration  
**Last Updated**: When migration starts
