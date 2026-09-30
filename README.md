# E-Bike Hunter

Personal tool that scrapes full-suspension e-MTB classifieds from 14 portals (Switzerland, Northern Italy, EU shops), filters and scores them against a buyer profile, and shows the results in a local interactive dashboard.

## Features

- **12 portal connectors**: Tutti.ch, Subito.it, Upway, Velomarkt, TCS Velocorner, Ridewill, Z-Bike, Godspeed, eBikeLab, eCycles Shop, eBikeStore Brescia, Buybestgear. Buycycle and Decathlon.ch are disabled stubs.
- **Zero-token spec parsing**: regex/taxonomy extraction of motor, battery, frame size, brakes, travel, odometer and model year. The main scan makes no LLM calls.
- **Hard filters + 0–100 score**: over budget, hardtail, weak motor, small battery and wrong size are rejected. Everything else is ranked on price, components, condition, distance and fit.
- **Sold detection, price history, duplicate flag**: listings that disappear are checked on the portal and marked SOLD. Price drops are tracked. The same bike on two portals is flagged.
- **Optional AI second opinion** (`analyze.py`, Claude Haiku): an Italian verdict, red flags, and spec corrections read from the seller's text.
- **Interactive dashboard** (`server.py`): reject, mark sold, favorite, or correct specs by hand.

## Quick start

Requires Python 3.11+ and a Supabase (Postgres) project.

```bash
pip3 install -r requirements.txt
cp .env.example .env                  # set DATABASE_URL (and ANTHROPIC_API_KEY for the AI pass)
python3 scripts/validate_supabase.py  # checks the connection, creates the tables
python3 run.py                        # scan all portals
python3 server.py                     # open the dashboard at http://127.0.0.1:5050
```

## Documentation

| Doc | Contents |
|-----|----------|
| [Setup](docs/setup.md) | Install, `.env`, Supabase connection, migrating the old SQLite DB |
| [Usage](docs/usage.md) | Scanning, dashboard, AI pass, reprocessing, automation |
| [Configuration](docs/configuration.md) | `config.yaml`, buyer profile, filters, scoring formula, portals |
| [Architecture](docs/architecture.md) | Pipeline, project layout, database tables |
| [Development](docs/development.md) | Running tests, adding a portal connector |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and fixes |

## License

Private project for personal use.
