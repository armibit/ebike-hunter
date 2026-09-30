# Architecture

## Pipeline

```
[Portal connectors]      src/connectors/*.py
       ↓
[Regex parser]           src/pipeline/regex_parser.py + config/taxonomy.json
       ↓                 motor · battery · size · brakes · travel · odometer · year
[Hard filters]           src/pipeline/filters.py
       ↓                 budget · hardtail · motor · battery · size · distance
[Scoring 0–100]          src/pipeline/scoring.py
       ↓
[Postgres / Supabase]    src/db/database.py
       ↓
[Optional AI pass]       analyze.py → src/pipeline/ai_analyzer.py (Claude Haiku)
       ↓
[Dashboard]              server.py (live) · index.html (static snapshot)
                         both rendered by scripts/generate_dashboard.py
```

## Project layout

```
ebike-hunter/
├── config/
│   ├── config.yaml            # buyer profile, filters, scoring weights, portals
│   └── taxonomy.json          # spec detection patterns
├── src/
│   ├── connectors/            # one module per portal + base.py, registry.py
│   ├── db/database.py         # Postgres access layer (psycopg2)
│   ├── pipeline/
│   │   ├── regex_parser.py    # zero-token spec extraction
│   │   ├── filters.py         # hard reject rules
│   │   ├── scoring.py         # 0–100 ranking
│   │   ├── normalizer.py      # currency normalization
│   │   ├── geo_data.py        # province/canton geocoding
│   │   ├── dedupe.py          # cross-portal duplicate detection
│   │   ├── corrections.py     # apply spec corrections + rescore
│   │   ├── analysis_text.py   # deterministic Italian verdict
│   │   └── ai_analyzer.py     # Claude batch analysis
│   └── utils/                 # config loading, logging, console output
├── scripts/
│   ├── generate_dashboard.py  # dashboard HTML renderer
│   ├── reprocess_all.py       # re-apply parser/filters to stored listings
│   ├── validate_supabase.py   # connection check + schema creation
│   └── migrate_to_supabase.py # one-off SQLite → Supabase copy
├── tests/                     # pytest suite (see development.md)
├── run.py                     # scan entry point
├── analyze.py                 # AI pass entry point
├── server.py                  # dashboard entry point (Flask, :5050)
└── debug_listing.py           # inspect one listing's extraction
```

## Database

The schema is created automatically by `Database._init_schema()`.

| Table | Contents |
|-------|----------|
| `listings` | One row per ad: portal, URL, title, price, location, status, AI verdict. `numeric_id` is the `#` shown in the dashboard |
| `listing_snapshots` | Price history (one row per observed price change) |
| `specifications` | Parsed specs: motor, battery, size, travel, brakes… |
| `scores` | Score breakdown per listing |
| `spec_overrides` | Manual and AI spec corrections, re-applied on reprocess |
| `deleted_listings` | Tombstones, so deleted ads are not re-imported |

Connections run in autocommit mode. Multi-statement writes are wrapped in a single transaction (the `@_atomic` decorator in `database.py`).
