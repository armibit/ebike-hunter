# Development

## Running the tests

The tests use a **local** Postgres, never Supabase. Each test creates a throwaway schema and drops it afterwards (`tests/pgtest.py`).

```bash
brew install postgresql@16 && brew services start postgresql@16   # macOS, once
python3 -m pytest -q
```

By default the tests connect to `postgresql:///postgres` (local socket, current user). Point them elsewhere with `TEST_DATABASE_URL`.

Every bug fix ships with a regression test that fails without the fix.

## Adding a portal connector

1. Create `src/connectors/<portal>.py` with a class extending `BaseConnector` (`src/connectors/base.py`). Follow an existing connector with a similar data source:

   | Data source | Example connectors |
   |-------------|--------------------|
   | Shopify feed | `upway.py` |
   | WooCommerce Store API | `zbike.py` |
   | HTML scraping | `subito.py`, `tutti.py` |

2. Register the class in `src/connectors/registry.py`.
3. Add a `portals.<portal>` block to `config/config.yaml` with `enabled: true`.
4. Add `tests/test_<portal>.py` that parses a saved sample of the page. Connector tests must not hit the network.

## Conventions

- SQL uses `%s` placeholders. Rows come back as dicts (`RealDictCursor`).
- Don't commit `.env`, `index.html` or anything under `logs/`.
