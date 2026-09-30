# Troubleshooting

## Cannot connect to the database

- **`could not translate host name "db.<ref>.supabase.co"`**: that direct host is IPv6-only. Use the **Session pooler** URL (`...pooler.supabase.com:5432`); see [Setup](setup.md#getting-database_url-from-supabase).
- **`password authentication failed`**: check the password in `.env`, and URL-encode any special characters.
- **Check** the connection with `python3 scripts/validate_supabase.py`.

## A portal returns 0 listings

Check `logs/run.log`, which has DEBUG level and full tracebacks. Portals change their HTML and APIs often.

The connector to fix is `src/connectors/<portal>.py`. Its test in `tests/test_<portal>.py` has a saved page sample you can update.

## Many listings rejected (red dot in the scan output)

Rejections are expected. Common reasons:

- no motor (a regular bike);
- hardtail;
- wrong frame size;
- over budget.

`analyze.py --problematic` lets the AI recover listings rejected only because a spec was missing or misread.

## Specs not extracted or wrong

1. Test the parser on the title (see [Configuration](configuration.md#taxonomyjson)).
2. Adjust `config/taxonomy.json`.
3. Run `python3 scripts/reprocess_all.py`.

To fix a single listing, open 📋 Dettagli in the dashboard and use 💾 Salva correzioni.

## Listing placed at the wrong distance

Check the listing's `location_raw` in the database. Then add the missing alias to `src/pipeline/geo_data.py` and reprocess.

## Dashboard doesn't reflect a code change

Restart `server.py`. The running process keeps the old code.

## `analyze.py` aborts with "ANTHROPIC_API_KEY not set"

Add the key to `.env`. `--dry-run` works without it.
