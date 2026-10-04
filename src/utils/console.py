"""Multi-line animated status indicator for TTY stdout (shell-style spinner).

Connectors funnel every HTTP call through BaseConnector.get()/post(), which
updates this display keyed by portal name — so each portal scanning in
parallel gets its own live "what's happening right now" line, without any
connector needing to know about the others. Real log lines (logger.info/
error/...) clear the block first so they never get garbled by it.
"""
import logging
import shutil
import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_WIDTH = 118
_SEPARATOR = "─" * _WIDTH


def _width() -> int:
    """Block width, capped to the terminal: a row wider than the window wraps
    onto two, the cursor-up count is then off and separators pile up."""
    return max(20, min(_WIDTH, shutil.get_terminal_size((_WIDTH + 1, 24)).columns - 1))


class StatusLine:
    def __init__(self):
        self._enabled = sys.stdout.isatty()
        self._lines: dict[str, str] = {}
        self._order: list[str] = []
        self._frame = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._rendered_count = 0

    def start(self):
        if not self._enabled or self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, key: str, text: str):
        with self._lock:
            if key not in self._lines:
                self._order.append(key)
            self._lines[key] = text

    def finish(self, key: str):
        """Drop a job's line — it stops being drawn on the next tick."""
        with self._lock:
            self._lines.pop(key, None)
            if key in self._order:
                self._order.remove(key)

    def _move_up(self, n: int):
        if n:
            sys.stdout.write(f"\033[{n}A")

    def _run(self):
        while not self._stop.is_set():
            self._render()
            time.sleep(0.1)

    def _render(self):
        with self._lock:
            frame = _FRAMES[self._frame % len(_FRAMES)]
            self._frame += 1
            width = _width()
            job_lines = [
                f"{frame} {self._lines[k]}"[:width].ljust(width)
                for k in self._order if self._lines.get(k)
            ]
            # A leading separator row, redrawn as part of the block itself, keeps
            # the live status area visually distinct from scrolling log lines
            # above it — otherwise both look like plain text in scrollback.
            lines = ["─" * width] + job_lines if job_lines else []
            old_n, new_n = self._rendered_count, len(lines)

            if old_n:
                self._move_up(old_n)
            for line in lines:
                sys.stdout.write("\r" + line + "\n")
            if new_n < old_n:
                extra = old_n - new_n
                for _ in range(extra):
                    sys.stdout.write("\r" + " " * width + "\n")
                self._move_up(extra)

            self._rendered_count = new_n
            sys.stdout.flush()

    def clear(self):
        """Blank the whole block and park the cursor at its top row."""
        if not self._enabled:
            return
        with self._lock:
            width = _width()
            n = self._rendered_count
            if n:
                self._move_up(n)
                for _ in range(n):
                    sys.stdout.write("\r" + " " * width + "\n")
                self._move_up(n)
                self._rendered_count = 0
                sys.stdout.flush()

    def stop(self):
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=0.5)
        self._thread = None
        with self._lock:
            self._lines.clear()
            self._order.clear()
        self.clear()


status = StatusLine()


class StatusAwareStreamHandler(logging.StreamHandler):
    """StreamHandler that clears the live status block before printing a record."""

    def emit(self, record):
        status.clear()
        super().emit(record)
