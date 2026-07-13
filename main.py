#!/usr/bin/env python3
"""
True Mafia Builder — pure Python entry point.

  python main.py

No Docker. No nginx. No extra services required.
Logs: bot.log  →  tail -f bot.log
"""

from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def setup_logging(level: str = "INFO") -> Path:
    log_path = ROOT / "bot.log"
    lvl = getattr(logging, level.upper(), logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(lvl)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    return log_path


def main() -> None:
    # load settings early for log level
    from builder.config import get_settings

    settings = get_settings()
    log_path = setup_logging(settings.log_level)
    log = logging.getLogger("main")
    log.info("Mafia Builder v2 — pure Python")
    log.info("log file: %s", log_path)
    log.info("cwd: %s", ROOT)

    from builder.app import run_bot

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log.info("interrupted")


if __name__ == "__main__":
    main()
