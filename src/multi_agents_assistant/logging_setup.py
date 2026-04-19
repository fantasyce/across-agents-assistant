from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(log_dir: Path, log_name: str, debug: bool = True) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_name

    logger = logging.getLogger("multi_agents_assistant")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()

    handler = RotatingFileHandler(str(log_path), maxBytes=5 * 1024 * 1024, backupCount=3)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    return logger

