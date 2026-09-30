# Setup

## Requirements

- Python 3.11+ (developed on 3.13)
- A [Supabase](https://supabase.com) project (hosted Postgres)
- Optional: an Anthropic API key, needed only for the AI pass (`analyze.py`)
- Optional: a local Postgres, needed only to run the tests (see [Development](development.md))

## 1. Install dependencies

```bash
pip3 install -r requirements.txt
```

## 2. Configure `.env`

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | yes | Supabase connection string (Session pooler, see below) |
| `ANTHROPIC_API_KEY` | for `analyze.py` | Claude API key |
| `ANTHROPIC_MODEL` | no | Model override (default `claude-haiku-4-5`) |
| `ANTHROPIC_BASE_URL` | no | Anthropic-compatible endpoint instead of the real API |
| `TEST_DATABASE_URL` | no | Local Postgres for tests (default `postgresql:///postgres`) |

`.env` is gitignored. Never commit it.

### Getting `DATABASE_URL` from Supabase

1. Open your Supabase project and click **Connect** at the top of the page.
2. Choose **Session pooler**. Don't use "Direct connection": the direct `db.<ref>.supabase.co` host is IPv6-only and fails on most home networks.
3. Copy the URI and replace `[YOUR-PASSWORD]` with the database password:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres
```

If the password contains special characters (`@`, `#`, `/`…), URL-encode them.

## 3. Verify the connection

```bash
python3 scripts/validate_supabase.py
```

This checks that the database is reachable and creates the tables if they are missing. Every entry point (`run.py`, `server.py`…) also creates missing tables on start.

## Migrating from the old SQLite database (one-off)

Earlier versions stored data in `data/emtb_hunter.db`. To copy it into Supabase:

```bash
python3 scripts/validate_supabase.py
python3 scripts/migrate_to_supabase.py
```

The script reads SQLite read-only and can be re-run safely (existing rows are skipped). It prints a row-count comparison per table at the end.

Next: [Usage](usage.md).
