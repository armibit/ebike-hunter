"""Single-line animated status indicator for TTY stdout (shell-style spinner).

Connectors funnel every HTTP call through BaseConnector.get()/post(), which
updates this line — so the spinner reflects live "what's happening right
now" progress (which portal/URL is in flight) without each connector having
to know about it. Real log lines (logger.info/error/...) clear the spinner
line first so they never get garbled by it.
"""
import logging
import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_WIDTH = 118


class StatusLine:
    def __init__(self):
        self._enabled = sys.stdout.isatty()
        self._text = ""
        self._frame = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if not self._enabled or self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, text: str):
        with self._lock:
            self._text = text

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                text, frame = self._text, _FRAMES[self._frame % len(_FRAMES)]
                self._frame += 1
            if text:
                line = f"{frame} {text}"[:_WIDTH]
                sys.stdout.write("\r" + line.ljust(_WIDTH))
                sys.stdout.flush()
            time.sleep(0.1)

    def clear(self):
        if self._enabled:
            sys.stdout.write("\r" + " " * _WIDTH + "\r")
            sys.stdout.flush()

    def stop(self):
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=0.5)
        self._thread = None
        self.clear()


status = StatusLine()


class StatusAwareStreamHandler(logging.StreamHandler):
    """StreamHandler that clears the live status line before printing a record."""

    def emit(self, record):
        status.clear()
        super().emit(record)
