# E-Bike Hunter

Autonomous, local, token-efficient e-bike classifieds finder, tracker, and ranker for Lugano (Ticino) and Lombardia region.

## Features

- **Zero-Token Parsing**: 99%+ operations run with 0 LLM tokens using regex and deterministic rules
- **Multi-Portal Support**: Tutti.ch, Subito.it, Buycycle (planned: Facebook Marketplace)
- **Smart Filtering**: Automatic rejection of hardtails, weak motors (<85Nm), small batteries (<625Wh)
- **Intelligent Scoring**: 0-100 ranking based on price, components, condition, distance, fit
- **Price Tracking**: Detects price drops and re-listings with SQLite history
- **Red Flag Detection**: Warns about missing chargers, keys, or broken parts

## Target Profile

- **Location**: Lugano, Ticino (CH)
- **Category**: Full suspension e-MTB (Trail / All-Mountain)
- **Travel**: 130-160mm front/rear
- **Motor**: >=85Nm (Bosch CX Gen4, Brose 2.1/2.2, Shimano EP8, Yamaha PW-X2/X3)
- **Battery**: >=625Wh (extractable)
- **Frame Size**: M, S2, S3 (for 170cm rider height)
- **Budget**: Target <=2200 CHF, hard max <=3000 CHF

## Architecture

```
[Scrapers]
  ├── Tutti.ch (Ticino) - JSON API
  ├── Subito.it (Lombardia) - JSON-LD + curl_cffi
  └── Buycycle (Europe) - Algolia API
       ↓
[Parser (Zero-Token Regex)]
  ├── Motor: Bosch/Brose/EP8/Yamaha pattern matching
  ├── Battery: Wh extraction (500-1000 range)
  ├── Frame Size: M/S2/S3/17"/44cm normalization
  ├── Brakes: 4-piston vs 2-piston tier detection
  └── Travel: 130-160mm extraction
       ↓
[Filters]
  ├── Price: >3000 CHF → reject
  ├── Suspension: hardtail → reject
  ├── Motor: <85Nm → reject
  ├── Battery: <625Wh → reject
  └── Size: XL/XS → reject
       ↓
[Scoring (0-100)]
  ├── Price vs Market (35%)
  ├── Components & Battery (25%)
  ├── Condition / Km (15%)
  ├── Distance from Lugano (15%)
  └── Fit (Taglia/Escursione) (10%)
       ↓
[SQLite Storage]
  ├── Listings + Snapshots
  ├── Specifications
  └── Scores
```

## Setup

```bash
cd /Users/danielearmillotta/ebike-hunter
pip3 install pyyaml  # Only dependency for demo
```

## Usage

### Run Demo (Simulated Data)

```bash
python3 demo.py
```

### Run Tests

```bash
python3 tests/test_parser.py
python3 tests/test_scoring.py
python3 tests/test_normalizer.py
python3 tests/test_database.py
```

## Configuration

Edit `config/config.yaml`:

```yaml
buyer_profile:
  location:
    name: "Lugano, Ticino"
    latitude: 46.0037
    longitude: 8.9511
  max_radius_km:
    ticino: 45
    lombardia: 105
  budget:
    target_price: 2200
    hard_max_price: 3000
```

Edit `config/taxonomy.json` to add/remove motors, brakes, or brands.

## Scoring Formula

Score (0-100) = weighted sum:

- **Price Score (35%)**: Exponential decay from 1800 CHF (100 pts) to 3000 CHF (0 pts)
- **Component Score (25%)**: Battery Wh + Motor Nm + Brakes tier + Fork tier
- **Condition Score (15%)**: Odometer km (500 km = 100 pts, 4000 km = 30 pts)
- **Location Score (15%)**: Distance from Lugano (<20 km = 100 pts, >100 km = 20 pts)
- **Fit Score (10%)**: Frame size M/S2/S3 + Travel 130-160mm

**Deal Target**: Score >= 75 AND Price <= 3000 CHF

## Next Steps (Production)

1. **Anti-Bot Scrapers**: Implement `curl_cffi` connectors for Tutti.ch and Subito.it
2. **Chrome CDP for Facebook**: Local Chrome remote debugging for FB Marketplace
3. **Scheduler**: Cron job for automatic scanning every 15-30 minutes
4. **Deduplication**: Implement fuzzy image hashing (pHash) for re-listing detection
5. **Notifications**: Telegram bot for instant alerts on top deals and price drops
6. **CLI Dashboard**: Rich terminal UI with sortable tables and filters

## File Structure

```
ebike-hunter/
├── config/
│   ├── config.yaml           # User config (budget, location, filters)
│   └── taxonomy.json         # Hardware patterns (motors, brakes, sizes)
├── src/
│   ├── db/
│   │   └── database.py       # SQLite wrapper (WAL mode, snapshots)
│   ├── pipeline/
│   │   ├── regex_parser.py   # Zero-token spec extraction
│   │   ├── normalizer.py     # Currency & geo normalization
│   │   └── scoring.py        # 0-100 ranking algorithm
│   └── connectors/           # (To be implemented)
│       ├── tutti.py
│       ├── subito.py
│       └── buycycle.py
├── tests/
│   ├── test_parser.py
│   ├── test_scoring.py
│   ├── test_normalizer.py
│   └── test_database.py
├── data/
│   └── emtb_hunter.db        # SQLite database
├── demo.py                   # End-to-end demo with simulated data
└── README.md
```

## Test Coverage

All tests pass:

- ✅ Motor detection (Bosch/Brose/EP8/Yamaha patterns + weak motor rejection)
- ✅ Battery extraction (500-1000 Wh range)
- ✅ Frame size detection (M/S2/S3/17"/44cm)
- ✅ Suspension type (full vs hardtail)
- ✅ Travel extraction (130-160mm)
- ✅ Red flag detection (missing charger/keys)
- ✅ Price scoring (exponential decay curve)
- ✅ Component scoring (battery/motor/brakes/fork tiers)
- ✅ Location scoring (Haversine distance from Lugano)
- ✅ Fit scoring (size + travel range)
- ✅ Currency normalization (CHF ↔ EUR)
- ✅ Database operations (insert, update, price drop detection)

## License

Private project for personal use.
