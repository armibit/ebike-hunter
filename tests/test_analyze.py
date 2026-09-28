import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import analyze


def _parse(*argv):
    saved = sys.argv
    sys.argv = ["analyze.py", *argv]
    try:
        return analyze.parse_args()
    finally:
        sys.argv = saved


def test_cli_accepts_the_new_modes():
    args = _parse("--problematic", "--limit", "5", "--dry-run")
    assert args.problematic and args.limit == 5 and args.dry_run and not args.force
    print("✅ analyze.py: --problematic --limit --dry-run")


def test_force_and_problematic_are_exclusive():
    try:
        _parse("--force", "--problematic")
        assert False, "argparse should refuse --force together with --problematic"
    except SystemExit:
        pass
    print("✅ analyze.py: --force / --problematic exclusive")


def test_dry_run_summary_counts_calls_and_reasons():
    listings = [
        {"status": "ACTIVE", "motor_torque_nm": 85, "motor_verified": 1, "battery_capacity_wh": 625,
         "frame_size": "M", "ai_analyzed_at": "2026-01-01"},
        {"status": "ACTIVE", "motor_torque_nm": 60, "motor_verified": 0, "battery_capacity_wh": None,
         "frame_size": "M"},
        {"status": "REJECTED", "rejection_reason": "No motor detected (likely not an e-bike)"},
        {"status": "REJECTED", "rejection_reason": "Over budget (3500 > 3000 CHF)"},
    ] * 4  # 16 listings -> 2 API calls of 15

    summary = analyze.dry_run_summary(listings)

    assert summary["listings"] == 16
    assert summary["api_calls"] == 2
    assert summary["already_analyzed"] == 4
    assert summary["reasons"] == {
        "specifiche complete": 4,
        "motore da verificare": 4,
        "batteria mancante": 4,
        "scartato per specifiche": 4,
        "scartato (motivo non correggibile)": 4,
    }
    print("✅ analyze.py: dry-run summary")


if __name__ == "__main__":
    test_cli_accepts_the_new_modes()
    test_force_and_problematic_are_exclusive()
    test_dry_run_summary_counts_calls_and_reasons()
    print("\n✅ All analyze tests passed!")
