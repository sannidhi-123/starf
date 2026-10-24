"""CLI script to initialize the STARK SQLite database and execute migrations."""

from __future__ import annotations

import argparse
from pathlib import Path

from stark.config import DATABASE_PATH
from stark.storage.db import get_connection, run_migrations
from stark.utils.logging import get_logger

logger = get_logger("06_init_db")


def main() -> None:
    """Initialize the SQLite database and verify WAL and foreign key settings."""
    parser = argparse.ArgumentParser(
        description="Initialize STARK database and apply schema migrations."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DATABASE_PATH),
        help=f"Path to SQLite database file (defaults to {DATABASE_PATH})",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    logger.info("Initializing database at: %s", db_path)

    run_migrations(db_path=db_path)

    # Verify settings
    conn = get_connection(db_path=db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    journal_mode = cursor.fetchone()[0]

    cursor.execute("PRAGMA foreign_keys;")
    foreign_keys = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    print(
        f"Database initialized successfully at {db_path}:\n"
        f"  journal_mode: {journal_mode} (WAL expected)\n"
        f"  foreign_keys: {foreign_keys} (1 expected)"
    )


if __name__ == "__main__":
    main()
