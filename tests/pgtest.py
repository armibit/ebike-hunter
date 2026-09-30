"""Throwaway Postgres schema per test, addressed by a plain URL.

The schema is baked into the URL (libpq search_path option), so code that
reconnects from the URL -- server, dashboard -- lands in the same schema.
"""
import os
import uuid
from urllib.parse import quote

import psycopg2

BASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql:///postgres")


def new_test_url():
    schema = f"test_{uuid.uuid4().hex[:12]}"
    conn = psycopg2.connect(BASE_URL)
    conn.autocommit = True
    conn.cursor().execute(f'CREATE SCHEMA "{schema}"')
    conn.close()
    sep = "&" if "?" in BASE_URL else "?"
    return f"{BASE_URL}{sep}options={quote(f'-csearch_path={schema}')}"


def drop_test_url(url):
    schema = url.rsplit("csearch_path%3D", 1)[1]
    conn = psycopg2.connect(BASE_URL)
    conn.autocommit = True
    conn.cursor().execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.close()
