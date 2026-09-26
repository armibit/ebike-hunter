# E-Bike Hunter

Personal, local tool that scrapes full-suspension e-MTB classifieds — mostly used, plus a couple of new-bike budget retailers — across 14 portals (Switzerland + Northern Italy + EU), scores them against a buyer profile, flags AI-read spec corrections and red flags, and shows everything in an interactive dashboard.

## Features

- **14 portal connectors**: Tutti.ch, Subito.it, Buycycle, Upway, Decathlon.ch, Velomarkt, TCS Velocorner, Ridewill, Z-Bike, Godspeed, eBikeLab, eCycles Shop, eBikeStore Brescia, Buybestgear.com (new bikes, not used — see below)
- **Zero-token parsing**: regex/taxonomy-based spec extraction (motor, battery, frame size, brakes, travel, odometer, model year) — no LLM calls in the main scan
- **Deterministic scoring**: 0–100 score from price, components, condition/mileage, distance, fit
- **Optional AI second opinion**: `analyze.py` sends listings to Claude Haiku for an independent Italian-language verdict, red-flag/condition reading from the raw description, and — only when the seller's own text names it — spec corrections the regex parser missed
- **Interactive dashboard** (`server.py`): a local Flask app opened as a standalone app-mode browser window (no tabs/address bar). Reject, mark sold, favorite, and manually correct specs by hand — corrections that push a listing outside your own criteria (wrong frame size, motor/battery below the minimums) auto-reject it, same as if the scan had read that value in the first place
- **Price tracking**: detects price drops and re-listings, keeps a price history per listing (shown in its original currency, not silently converted)
- **Red flag detection**: missing charger/keys, broken parts, accident history mentioned in the description

## Target Profile

Configured in `config/config.yaml` — current defaults:

- **Location**: Lugano, Ticino (CH); Ticino radius 45 km, Lombardia radius 105 km
- **Category**: Full suspension e-MTB, 130–160mm travel front/rear
- **Motor / battery hard minimums** (below these, a listing is rejected outright): ≥60Nm torque, ≥500Wh battery
- **Frame size**: M, S2, S3, 42–46cm, 17"/18"
- **Budget**: target 2200 CHF, hard max 3000 CHF (over this is rejected)

## Architecture

```
[14 portal connectors]  src/connectors/*.py
       ↓
[Regex parser]  src/pipeline/regex_parser.py + config/taxonomy.json
  motor · battery · frame size · brakes · suspension · travel · odometer · model year
       ↓
[Hard filters]  run.py: process_listing()
  over budget · hardtail · no/weak motor · small battery · wrong size · red flags
       ↓
[Deterministic scoring 0-100]  src/pipeline/scoring.py
  price (35%) · components (25%) · condition/km (15%) · distance (15%) · fit (10%)
       ↓
[SQLite]  src/db/database.py — listings, snapshots (price history), specifications, scores
       ↓
[Optional AI pass]  analyze.py → src/pipeline/ai_analyzer.py (Claude Haiku)
  Italian verdict, condition/seller-trust reading, spec corrections read (not guessed) from text
       ↓
[Dashboard]  server.py (live, interactive) or generate_dashboard.py → index.html (static snapshot)
```

## Setup

```bash
pip3 install -r requirements.txt
```

To use the optional AI pass (`analyze.py`), create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### 1. Scan portals

```bash
python3 run.py
```

Fetches listings from every enabled portal in `config/config.yaml`, parses specs, applies the hard filters, scores, and saves to SQLite (`config.app.db_path`). Prints accepted/rejected counts per portal and the top deals.

### 2. Interactive dashboard (recommended)

```bash
python3 server.py
```

Opens a local Flask dashboard as a standalone app window, reading the database live on every page load. From here you can reject, mark sold/favorite, and correct specs by hand — no regeneration step needed.

### 3. Optional AI second opinion

```bash
python3 analyze.py            # analyzes listings never read by AI yet (or re-checked after a price drop)
python3 analyze.py --force    # re-analyzes EVERY active/price-drop listing, even already-analyzed ones (costs an API call each)
python3 analyze.py --id 42    # analyzes just one listing, for testing — accepts either its numeric # id (shown in the dashboard) or its full id
```

Writes an Italian-language verdict (`ai_analysis`) and, when the seller's text explicitly names a spec the regex parser missed, a correction that's applied and rescored automatically. Also regenerates the static `index.html` snapshot.

### 4. Static snapshot (optional)

`run.py`/`analyze.py` both regenerate `index.html` (gitignored — local only) via `scripts/generate_dashboard.py`. It's a read-only copy for sharing; use `server.py` for anything interactive. Note that a running `server.py` process needs restarting to pick up code changes — editing `scripts/generate_dashboard.py` and reloading the browser isn't enough while the old process is still alive.

## Configuration

Edit `config/config.yaml` — buyer profile (location, budget, target sizes), `hardware_requirements` (hard-reject minimums), `scoring_weights`, and each portal's `enabled`/search settings.

Edit `config/taxonomy.json` to add/adjust motor, brake, and frame-size detection patterns.

## Scoring Formula

Score (0–100) = weighted sum, weights configurable in `scoring_weights`:

- **Price value (35%)**: exponential decay between target and hard-max price
- **Component quality (25%)**: motor tier/torque, battery Wh, brakes, fork tier — an unverified motor guess is penalized vs. a confirmed one
- **Condition/mileage (15%)**: odometer km
- **Location proximity (15%)**: Haversine distance from Lugano
- **Fit/geometry (10%)**: frame size + suspension travel range

## File Structure

```
ebike-hunter/
├── config/
│   ├── config.yaml              # Buyer profile, hardware minimums, scoring weights, portals
│   └── taxonomy.json            # Motor/brake/frame-size detection patterns
├── src/
│   ├── connectors/               # One file per portal (+ base.py)
│   ├── db/
│   │   └── database.py           # SQLite wrapper (WAL mode, snapshots, favorites, AI columns)
│   └── pipeline/
│       ├── regex_parser.py       # Zero-token spec extraction
│       ├── normalizer.py         # Currency & geo normalization
│       ├── scoring.py            # 0-100 ranking algorithm
│       ├── ai_analyzer.py        # Claude Haiku batch analysis + spec-correction reading
│       ├── corrections.py        # Shared apply-a-spec-correction-and-rescore logic
│       └── analysis_text.py      # Deterministic Italian verdict text
├── scripts/
│   └── generate_dashboard.py     # Renders the dashboard HTML (used by both server.py and index.html)
├── tests/                        # One test file per connector, plus pipeline/DB/dashboard tests
├── data/
│   └── emtb_hunter.db            # SQLite database (gitignored)
├── run.py                        # Full scan: fetch → parse → filter → score → save
├── analyze.py                    # Optional AI second-opinion pass (--force / --id)
├── server.py                     # Interactive dashboard (Flask, app-mode window)
├── demo.py                       # End-to-end demo with simulated data
├── requirements.txt
├── README.md
└── USAGE.md                      # Extended usage notes, cron automation, troubleshooting
```

## License

Private project for personal use.
