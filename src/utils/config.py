"""Load config/config.yaml the same way from every entry point.

app.database_url is read from .env (DATABASE_URL env var), not the config file.
Secrets never live in config.yaml (checked in); only in .env (gitignored).
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    # Load .env from project root (once per app startup, safe to call multiple times)
    load_dotenv(PROJECT_ROOT / ".env")

    config_path = Path(path) if path else PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    app = config.setdefault("app", {})

    # DATABASE_URL from environment, required for Postgres connections
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL not set in .env. Copy .env.example, update with your Supabase credentials."
        )
    app["database_url"] = database_url

    return config
