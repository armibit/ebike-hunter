import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.config import PROJECT_ROOT, load_config


def _write_config(db_path: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    handle.write(f'app:\n  db_path: "{db_path}"\n')
    handle.close()
    return Path(handle.name)


def test_relative_db_path_resolves_under_project_root():
    # A relative path must not depend on the current directory (cron, the
    # dashboard server and scripts/* all start from different places).
    path = _write_config("data/emtb_hunter.db")
    assert load_config(path)["app"]["db_path"] == str(PROJECT_ROOT / "data" / "emtb_hunter.db")
    path.unlink()
    print("✅ Relative db_path resolution")


def test_absolute_db_path_is_kept():
    path = _write_config("/tmp/somewhere/else.db")
    assert load_config(path)["app"]["db_path"] == "/tmp/somewhere/else.db"
    path.unlink()
    print("✅ Absolute db_path kept")


def test_project_config_loads():
    config = load_config()
    assert Path(config["app"]["db_path"]).is_absolute()
    assert "italy" in config["buyer_profile"]["max_radius_km"]
    print("✅ Project config loads")


if __name__ == "__main__":
    test_relative_db_path_resolves_under_project_root()
    test_absolute_db_path_is_kept()
    test_project_config_loads()
    print("\n✅ All config tests passed!")
