"""Shared logging configuration for run.py and analyze.py."""
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from utils.console import StatusAwareStreamHandler


def setup_logging(
    log_file: str,
    config: Optional[Dict[str, Any]] = None,
    use_status_handler: bool = False,
    base_dir: Optional[Path] = None,
) -> Path:
    """Configure logging with console + file handlers.

    Args:
        log_file: Name of log file (e.g., "run.log", "analyze.log")
        config: Optional config dict. If provided + use_status_handler=True,
                reads app.log_level from config for console level.
        use_status_handler: If True, use StatusAwareStreamHandler (spinner-aware).
                           If False, use plain StreamHandler.
        base_dir: Base directory for logs/ folder. Defaults to current working dir.

    Returns:
        Path to the log file created.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Console handler
    if use_status_handler:
        console_handler = StatusAwareStreamHandler()
        console_level_name = str(config.get("app", {}).get("log_level", "INFO")).upper() if config else "INFO"
        console_level = getattr(logging, console_level_name, logging.INFO)
    else:
        console_handler = logging.StreamHandler()
        console_level = logging.INFO

    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    # File handler
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / log_file
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler], force=True)

    return log_path
