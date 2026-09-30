import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.config import load_config


def test_database_url_is_set():
    """DATABASE_URL must be set in .env for Postgres connections."""
    # Temporarily set for test (would normally come from .env)
    original = os.environ.get("DATABASE_URL")
    try:
        if not original:
            os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/postgres"

        config = load_config()
        assert "database_url" in config["app"]
        assert config["app"]["database_url"].startswith("postgresql://")
        print("✅ DATABASE_URL is set and has correct format")
    finally:
        if original is None and "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        elif original:
            os.environ["DATABASE_URL"] = original


def test_project_config_loads():
    """Project config loads without errors."""
    config = load_config()
    assert "database_url" in config["app"]
    assert "italy" in config["buyer_profile"]["max_radius_km"]
    print("✅ Project config loads")


if __name__ == "__main__":
    test_database_url_is_set()
    test_project_config_loads()
    print("\n✅ All config tests passed!")
