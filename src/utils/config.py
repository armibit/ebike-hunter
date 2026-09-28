"""Load config/config.yaml the same way from every entry point.

app.db_path may be relative ("data/emtb_hunter.db"): it's resolved against
the project root, not the current directory, so run.py from cron, the
dashboard server and scripts/* all open the same database — and the project
works on any machine, not only at one absolute path.
"""
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    config_path = Path(path) if path else PROJECT_ROOT / "config" / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    app = config.setdefault("app", {})
    db_path = Path(app.get("db_path", "data/emtb_hunter.db")).expanduser()
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    app["db_path"] = str(db_path)
    return config
