# Usage

The typical cycle is: **scan** (`run.py`), optionally run the **AI pass** (`analyze.py`), then **review** in the dashboard (`server.py`).

## 1. Scan the portals

```bash
python3 run.py
```

For every enabled portal in `config/config.yaml`, the scan:

1. fetches the listings;
2. parses the specs;
3. applies the hard filters;
4. scores the accepted listings and saves everything to the database.

It prints accepted and rejected counts per portal, then the top deals.

A red dot next to a portal means most of its listings were rejected (≤20 % accepted). That's normal for portals that also list hardtails, non-e-bikes or other frame sizes.

A full debug log goes to `logs/run.log`.

### What a scan does with sold listings

1. Shop feeds (Upway, eCycles, Buybestgear, Z-Bike) report sold-out items directly. The stored listing becomes SOLD.
2. After the scan, live listings that no longer appear in any search result are checked on their portal. A listing is marked SOLD when:
   - the page is gone (404/410);
   - the page redirects away from the ad;
   - it carries schema.org `OutOfStock`;
   - it shows an "annuncio non più disponibile"-type message.

   A blocked or failed check changes nothing.
3. At most `app.availability_checks_per_run` listings (default 300) are checked per scan, least recently checked first.

## 2. Review in the dashboard

```bash
python3 server.py
```

This opens a local Flask app at `http://127.0.0.1:5050` as a standalone app-mode browser window. It reads the database live on every page load.

Buttons per listing:

| Button | Effect |
|--------|--------|
| ☆ / ⭐ (Preferito) | Toggle favorite |
| ✕ Scarta | Reject: hidden, and a rescan or reprocess won't bring it back |
| ✅ Segna venduta | Mark SOLD |
| ↩️ Ripristina attiva | Undo a reject or sold mark |
| 🗑️ Cancella dalla lista | Delete; it won't be re-imported |
| 📋 Dettagli → 💾 Salva correzioni | Override parsed specs and rescore. A correction that breaks your criteria (wrong size, motor or battery below the minimum) auto-rejects the listing |

Restart `server.py` after changing code. Reloading the page is not enough.

## 3. AI second opinion (optional)

`analyze.py` sends listings to Claude Haiku in batches. For each listing it:

- writes an Italian verdict;
- reads the listing's condition and red flags;
- corrects specs the regex parser missed, but only when the seller's text states the value explicitly. Corrections are applied and the listing is rescored.

It needs `ANTHROPIC_API_KEY` in `.env`.

```bash
python3 analyze.py --dry-run               # what would be analyzed, how many API calls; no key needed
python3 analyze.py                         # listings never analyzed (or re-checked after a price drop)
python3 analyze.py --problematic           # only listings with spec gaps the AI can fix
python3 analyze.py --force --limit 150     # re-analyze everything, in resumable batches of 150
python3 analyze.py --id 42                 # one listing (dashboard # or full id, e.g. tutti_12345)
python3 analyze.py --ids 12,44,tutti_123   # several listings
python3 analyze.py --id-range 10 50        # dashboard ids 10..50
```

`--force` and `--problematic` are mutually exclusive. `--id`, `--ids` and `--id-range` ignore listing status. The log goes to `logs/analyze.log`.

## 4. Reprocess stored listings (no network)

After changing the parser, `config/taxonomy.json`, locations or filters, you can re-apply them to every listing already in the database:

```bash
python3 scripts/reprocess_all.py --dry-run   # show what would change
python3 scripts/reprocess_all.py
```

The script never touches listings you rejected or marked sold by hand, or listings that are SOLD or DELISTED.

## 5. Static snapshot

`run.py` and `analyze.py` also write `index.html`, a read-only copy of the dashboard for sharing. The file is gitignored. Use `server.py` for anything interactive.

## Debugging a single listing

```bash
python3 debug_listing.py --id 140            # by dashboard id
python3 debug_listing.py --url https://...   # by URL
```

It shows the description extraction for that listing.

## Automation (cron)

To scan every 30 minutes:

```
*/30 * * * * cd /path/to/ebike-hunter && /usr/bin/env python3 run.py >> logs/scan.log 2>&1
```

Keep `analyze.py` manual so its API cost stays predictable.
