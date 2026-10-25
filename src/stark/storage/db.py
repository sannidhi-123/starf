"""Database connection factory and migration runner for STARK SQLite storage.

Enforces Rule 8:
- SQL uses '?' placeholders only.
- WAL journal mode enabled.
- Foreign key constraints strictly enabled.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from stark.config import DATABASE_PATH
from stark.utils.logging import get_logger

logger = get_logger(__name__)

MIGRATIONS_FILE = Path(__file__).parent / "migrations.sql"


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create and return an SQLite connection configured with WAL and foreign keys.

    Args:
        db_path: Path to SQLite database file. Defaults to config.DATABASE_PATH.

    Returns:
        sqlite3.Connection: Configured connection with Row factory.
    """
    path = Path(db_path) if db_path is not None else DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enforce Rule 8: WAL and foreign keys
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.close()

    return conn


def run_migrations(
    conn: sqlite3.Connection | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Execute migrations.sql to ensure all tables and indexes exist.

    Args:
        conn: Optional active connection. If None, acquires one via get_connection().
        db_path: Optional custom database path if conn is None.
    """
    should_close = False
    if conn is None:
        conn = get_connection(db_path)
        should_close = True

    try:
        sql = MIGRATIONS_FILE.read_text(encoding="utf-8")
        with conn:
            conn.executescript(sql)
        logger.info("Successfully executed migrations from %s", MIGRATIONS_FILE.name)
    finally:
        if should_close:
            conn.close()
