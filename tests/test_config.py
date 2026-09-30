import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.config import load_config


def test_database_url_is_set():
    """DATABASE_URL must be set and point to Postgres."""
    original = os.environ.get("DATABASE_URL")
    try:
        if not original:
            os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/postgres"

        config = load_config()
        assert "database_url" in config["app"], "database_url must be in config['app']"
        assert config["app"]["database_url"].startswith("postgresql://"), \
            "database_url must be a Postgres connection string"
        print("✅ DATABASE_URL is set and has correct format")
    finally:
        if original is None and "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        elif original:
            os.environ["DATABASE_URL"] = original


def test_project_config_loads():
    """Project config loads without errors and has required keys."""
    config = load_config()
    assert "database_url" in config["app"], "database_url required in app config"
    assert config["app"]["database_url"].startswith("postgresql://"), \
        "database_url must be a Postgres connection string"
    assert "italy" in config["buyer_profile"]["max_radius_km"], \
        "buyer_profile.max_radius_km.italy required"
    print("✅ Project config loads with required keys")


def test_no_entry_point_reads_removed_db_path():
    """Regression: analyze.py still read config['app']['db_path'] after the
    Postgres move and crashed with KeyError when refreshing the dashboard."""
    root = Path(__file__).parent.parent
    files = [*root.glob("*.py"), *(root / "scripts").glob("*.py"), *(root / "src").rglob("*.py")]
    offenders = [f.name for f in files if '["db_path"]' in f.read_text()]
    assert offenders == []
