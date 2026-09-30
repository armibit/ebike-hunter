# E-Bike Hunter - Usage Guide

See `README.md` for what the tool does. This file covers day-to-day use,
automation and troubleshooting.

## Setup

```bash
pip3 install -r requirements.txt
cp .env.example .env   # set DATABASE_URL (Supabase Session pooler); ANTHROPIC_API_KEY only for analyze.py
```

Data lives in Supabase Postgres (`DATABASE_URL` in `.env`). Tests use a local
Postgres (`TEST_DATABASE_URL`, default `postgresql:///postgres`).

## Everyday commands

```bash
python3 run.py                        # scan every enabled portal, then check unseen listings for "sold"
python3 server.py                     # interactive dashboard (app window on http://127.0.0.1:5050)
python3 analyze.py --dry-run          # what the AI pass would do, and how many API calls
python3 analyze.py                    # AI read of new listings
python3 analyze.py --problematic      # AI re-read of listings with spec gaps it can fix
python3 analyze.py --force --limit 150  # full re-analysis, in resumable batches
python3 scripts/reprocess_all.py --dry-run   # re-apply parser/filters/locations to the stored DB
python3 scripts/reprocess_all.py
```

`reprocess_all.py` is the way to apply a parser, taxonomy, location or
filter change to listings already in the database without a network scan.
It never touches a listing you rejected or marked sold by hand.

## What a scan does with sold listings

1. Shop feeds (Upway, eCycles, Buybestgear, Z-Bike) say when a bike is
   sold out — the stored listing becomes SOLD and a new one isn't imported.
2. After the scan, live listings that no longer appear in any search
   result are checked on their portal. SOLD when the page is gone
   (404/410), redirects away from the ad, carries schema.org `OutOfStock`,
   or shows an "annuncio non più disponibile"-type message. A blocked or
   failed check changes nothing.
3. At most `app.availability_checks_per_run` listings (default 300) are
   checked per scan, least recently checked first — a big backlog is
   worked through over a few scans.

## Configuration highlights

```yaml
buyer_profile:
  max_radius_km:
    italy: 150          # Italian listings beyond this are rejected; Switzerland always accepted
    exempt_portals: [...]   # shops that ship: never rejected for distance
  budget:
    full_score_price: 1800  # at or below: full price score
portals:
  subito_it:
    search_paths:       # exactly as in Subito's URLs: a region or a single province
      - "/annunci-lombardia/vendita/biciclette"
      - "/annunci-piemonte/vendita/biciclette/verbano-cusio-ossola"
```

Locations are resolved at province / canton level (`src/pipeline/geo_data.py`),
so no list of towns needs maintaining.

## Automation (macOS/Linux)

```
*/30 * * * * cd /path/to/ebike-hunter && /usr/bin/env python3 run.py >> logs/scan.log 2>&1
```

## Troubleshooting

- **A portal returns 0 listings**: check `logs/run.log` (DEBUG level, full
  tracebacks). Portals change their HTML/APIs; the matching connector is
  `src/connectors/<portal>.py`, and every connector has tests with a saved
  sample of the page it parses.
- **Specs not extracted**: test the parser directly —
  `python3 -c "import sys; sys.path.insert(0,'src'); from pipeline.regex_parser import RegexParser; print(RegexParser('config/taxonomy.json').parse('Turbo Levo M Bosch CX 625Wh', 'fully'))"`
  — then adjust `config/taxonomy.json`.
- **A listing is placed at the wrong distance**: check its `location_raw`
  in the DB; add the missing alias to `src/pipeline/geo_data.py`.
- **Cannot connect to the DB**: use the Supabase *Session pooler* URL
  (`...pooler.supabase.com`); the direct `db.<ref>.supabase.co` host is IPv6-only.
  Check with `python3 scripts/validate_supabase.py`.

## Tests

```bash
python3 -m pytest -q
```
