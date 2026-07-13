from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(root_dir: Path, level: str = "INFO") -> Path:
    """
    All app logs go to console + bot.log (project root).
    Usage on server: tail -f bot.log
    """
    log_path = root_dir / "bot.log"
    log_level = getattr(logging, level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    # Console
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(log_level)
    root.addHandler(sh)

    # File: bot.log (rotate at 10MB, keep 5)
    fh = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    fh.setLevel(log_level)
    root.addHandler(fh)

    # Noise down
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Keep aiogram events visible
    logging.getLogger("aiogram").setLevel(log_level)
    logging.getLogger("aiogram.event").setLevel(log_level)

    root.info("Logging → console + %s", log_path)
    return log_path
