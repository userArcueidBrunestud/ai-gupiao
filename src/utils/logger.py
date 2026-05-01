from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from config.settings import settings


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        colorize=True,
    )
    log_dir = Path("data")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "app.log",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        encoding="utf-8",
    )


def get_logger(name: str):
    """Return a logger instance bound with the given module name."""
    return logger.bind(name=name)
