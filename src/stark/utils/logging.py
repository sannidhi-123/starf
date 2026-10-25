"""Logging utilities for STARK."""

from __future__ import annotations

import logging
import sys


def get_logger(name: str = "stark") -> logging.Logger:
    """Return a configured logger for STARK modules.

    Args:
        name: Name of the logger to retrieve.

    Returns:
        logging.Logger: Configured logger instance writing to stdout.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger
