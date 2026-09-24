# E-Bike Hunter - Usage Guide

## Quick Start

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Test with Demo (Simulated Data)

```bash
python3 demo.py
```

### 3. Test Live Connectors (Real HTTP Requests)

```bash
python3 test_connectors.py
```

This will fetch a few listings from Tutti.ch and Subito.it to verify the scraper works.

### 4. Run Full Scan

```bash
python3 run.py
```

This will:
1. Search Tutti.ch (Ticino) for all configured queries
2. Search Subito.it (Lombardia: Como, Varese, Milano, Lecco) for all queries
3. Parse, filter, and score each listing
4. Save to SQLite database
5. Display top deals and price drops

## Configuration

Edit `config/config.yaml` to customize:

### Buyer Profile

```yaml
buyer_profile:
  location:
    name: "Lugano, Ticino"
    latitude: 46.0037
    longitude: 8.9511
  max_radius_km:
    ticino: 45      # Max distance for Ticino listings
    lombardia: 105  # Max distance for Lombardia listings
  budget:
    target_price: 2200         # Ideal price
    hard_max_price: 3000       # Absolute maximum
    suspicious_min_price: 900  # Flag suspiciously low prices
  rider_specs:
    height_cm: 170
    target_sizes: ["M", "S2", "S3", "42cm", "43cm", "44cm", "45cm", "46cm"]
```

### Search Queries

```yaml
portals:
  tutti_ch:
    enabled: true
    search_queries:
      - "ebike fully"
      - "e-mtb full"
      - "turbo levo"
      - "stereo hybrid"
      - "trek rail"
      - "canyon spectral on"

  subito_it:
    enabled: true
    search_queries:
      - "ebike full"
      - "emtb biammortizzata"
      - "turbo levo"
      - "stereo hybrid"
```

## Database

All data is stored in `data/emtb_hunter.db` (SQLite).

### View Database

```bash
sqlite3 data/emtb_hunter.db
```

Useful queries:

```sql
-- Top deals
SELECT title, price_chf, score_total, distance_km, url
FROM listings l
JOIN scores s ON l.id = s.listing_id
WHERE l.status = 'ACTIVE' AND s.score_total >= 75
ORDER BY s.score_total DESC
LIMIT 10;

-- Price drops
SELECT title, price_raw, currency, url
FROM listings
WHERE status = 'PRICE_DROP'
ORDER BY last_checked_at DESC
LIMIT 10;

-- All specs
SELECT l.title, l.price_chf, s.motor_model, s.battery_capacity_wh, s.frame_size
FROM listings l
JOIN specifications s ON l.id = s.listing_id
WHERE l.status = 'ACTIVE';
```

## Automation

### Run Every 30 Minutes (macOS/Linux)

Add to crontab:

```bash
crontab -e
```

Add line:

```
*/30 * * * * cd /Users/danielearmillotta/ebike-hunter && /usr/local/bin/python3 run.py >> logs/scan.log 2>&1
```

Create logs directory:

```bash
mkdir -p logs
```

### Run with Notifications (Telegram Bot - Future)

To be implemented:
1. Create Telegram bot via @BotFather
2. Add bot token to config
3. Implement notification module
4. Send alerts on new deal targets (score >= 75) and price drops

## Troubleshooting

### No Results Found

If `test_connectors.py` or `run.py` returns 0 results:

1. **HTML Structure Changed**: Websites frequently update their HTML. Inspect the live page:
   - Open Tutti.ch or Subito.it in browser
   - Search for "ebike fully"
   - Right-click on a listing card → Inspect
   - Update CSS selectors in `src/connectors/tutti.py` or `subito.py`

2. **Anti-Bot Protection**: Site may have detected scraper:
   - Add longer delays between requests
   - Use different User-Agent headers
   - Consider using `curl_cffi` library for better TLS fingerprinting

3. **Rate Limiting**: Too many requests:
   - Increase `min_delay` in `base.py`
   - Reduce number of search queries in config

### Parser Not Extracting Specs

If listings are accepted but specs are empty:

1. Check actual listing text in database:
   ```bash
   sqlite3 data/emtb_hunter.db "SELECT title, description_raw FROM listings LIMIT 5;"
   ```

2. Test parser directly:
   ```bash
   python3 -c "
   import sys
   sys.path.insert(0, 'src')
   from pipeline.regex_parser import RegexParser
   parser = RegexParser('config/taxonomy.json')
   specs = parser.parse('Specialized Turbo Levo Comp M Bosch CX 625Wh', 'fully biammortizzata')
   print(specs)
   "
   ```

3. Update patterns in `config/taxonomy.json`

### Database Locked

If you see `database is locked` error:

```bash
# Close all connections
pkill -f run.py

# Reset WAL checkpoint
sqlite3 data/emtb_hunter.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

## Advanced

### Custom Filters

Edit `run.py` function `process_listing()` to add custom filters:

```python
# Example: Only bikes from 2023 or newer
if specs["model_year"] and specs["model_year"] < 2023:
    reject_reasons.append("Too old (< 2023)")
```

### Custom Scoring Weights

Edit `config/config.yaml`:

```yaml
scoring_weights:
  price_value: 0.40          # Increase if price is most important
  component_quality: 0.25
  condition_mileage: 0.15
  location_proximity: 0.10   # Decrease if willing to travel far
  fit_geometry: 0.10
```

### Export to CSV

```bash
sqlite3 -header -csv data/emtb_hunter.db "SELECT * FROM listings WHERE status='ACTIVE';" > listings.csv
```

## Next Steps

1. **Implement Buycycle Connector**: Reverse-engineer their Algolia search
2. **Facebook Marketplace**: Chrome CDP with local browser
3. **Deduplication**: Image hashing (`imagehash`) for cross-portal duplicates
4. **Telegram Bot**: Real-time notifications
5. **Web Dashboard**: Flask/Streamlit UI for browsing deals
