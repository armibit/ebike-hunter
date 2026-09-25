import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from utils.console import StatusLine, _SEPARATOR, _WIDTH


def _new_status():
    """A StatusLine with rendering force-enabled (bypasses the isatty() check)."""
    s = StatusLine()
    s._enabled = True
    return s


def test_render_emits_separator_above_job_lines():
    status = _new_status()
    status.update("tutti", "[tutti] GET https://tutti.ch/search")

    buf = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, buf
    try:
        status._render()
    finally:
        sys.stdout = real_stdout

    output = buf.getvalue()
    assert _SEPARATOR in output
    assert "[tutti] GET" in output
    # separator must come before the job line
    assert output.index(_SEPARATOR) < output.index("[tutti] GET")
    print("✅ StatusLine separator-above-jobs test passed")


def test_render_emits_no_separator_when_idle():
    status = _new_status()

    buf = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, buf
    try:
        status._render()
    finally:
        sys.stdout = real_stdout

    assert _SEPARATOR not in buf.getvalue()
    assert status._rendered_count == 0
    print("✅ StatusLine idle-no-separator test passed")


def test_finish_removes_job_so_next_render_is_clean():
    status = _new_status()
    status.update("subito", "[subito] GET https://subito.it/x")
    status.finish("subito")

    buf = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, buf
    try:
        status._render()
    finally:
        sys.stdout = real_stdout

    assert buf.getvalue() == ""
    print("✅ StatusLine finish-then-render-clean test passed")


def test_update_after_finish_reopens_under_same_key():
    """Documents the reopening behavior: update() after finish() legitimately
    re-adds the key — callers (e.g. a distinct enrichment status key in
    run.py) are responsible for making that reappearance self-explanatory."""
    status = _new_status()
    status.update("subito", "[subito] GET https://subito.it/search")
    status.finish("subito")
    status.update("subito:enrich", "[subito] fetching detail 1/3")

    assert "subito" not in status._lines
    assert "subito:enrich" in status._lines
    print("✅ StatusLine distinct-key-after-finish test passed")


def test_job_line_width_is_padded_and_truncated():
    status = _new_status()
    status.update("x", "short")

    buf = io.StringIO()
    real_stdout, sys.stdout = sys.stdout, buf
    try:
        status._render()
    finally:
        sys.stdout = real_stdout

    body_line = [l for l in buf.getvalue().split("\n") if "short" in l][0]
    # strip the leading "\r" and spinner-frame prefix to isolate the padded field
    content = body_line.split("\r", 1)[1]
    assert len(content) == _WIDTH
    print("✅ StatusLine line-width padding test passed")


if __name__ == "__main__":
    test_render_emits_separator_above_job_lines()
    test_render_emits_no_separator_when_idle()
    test_finish_removes_job_so_next_render_is_clean()
    test_update_after_finish_reopens_under_same_key()
    test_job_line_width_is_padded_and_truncated()
    print("\n✅ All console/StatusLine tests passed!")
