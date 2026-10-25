"""Repositories for STARK database entities.

Enforces Rule 8:
- SQL statements use '?' placeholders strictly.
- AlertRepo.insert_many uses executemany in chunks of 1,000.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from stark.storage.db import get_connection
from stark.utils.logging import get_logger

logger = get_logger(__name__)


class DatasetRepo:
    """Repository managing dataset records in SQLite."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn if conn is not None else get_connection()

    def create(
        self,
        dataset_id: str,
        name: str,
        source: str,
        file_path: str,
        row_count: int = 0,
        size_bytes: int = 0,
    ) -> dict[str, Any]:
        """Insert a new dataset metadata entry."""
        query = (
            "INSERT INTO datasets (id, name, source, file_path, row_count, size_bytes) "
            "VALUES (?, ?, ?, ?, ?, ?);"
        )
        with self.conn:
            self.conn.execute(
                query, (dataset_id, name, source, file_path, row_count, size_bytes)
            )
        return self.get(dataset_id)  # type: ignore[return-value]

    def get(self, dataset_id: str) -> dict[str, Any] | None:
        """Fetch a dataset record by ID."""
        query = "SELECT * FROM datasets WHERE id = ?;"
        cursor = self.conn.cursor()
        cursor.execute(query, (dataset_id,))
        row = cursor.fetchone()
        cursor.close()
        return dict(row) if row is not None else None

    def list_all(self) -> list[dict[str, Any]]:
        """List all dataset records ordered by creation date."""
        query = "SELECT * FROM datasets ORDER BY created_at DESC;"
        cursor = self.conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        return [dict(r) for r in rows]

    def delete(self, dataset_id: str) -> bool:
        """Delete a dataset and its cascading dependencies."""
        query = "DELETE FROM datasets WHERE id = ?;"
        with self.conn:
            cursor = self.conn.execute(query, (dataset_id,))
            return cursor.rowcount > 0


class RunRepo:
    """Repository managing detection execution run records."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn if conn is not None else get_connection()

    def create(
        self,
        run_id: str,
        dataset_id: str,
        model_version: str,
        status: str = "completed",
        total_frames: int = 0,
        anomalies_detected: int = 0,
    ) -> dict[str, Any]:
        """Insert a detection run record."""
        query = (
            "INSERT INTO runs (id, dataset_id, model_version, status, total_frames, anomalies_detected) "
            "VALUES (?, ?, ?, ?, ?, ?);"
        )
        with self.conn:
            self.conn.execute(
                query,
                (
                    run_id,
                    dataset_id,
                    model_version,
                    status,
                    total_frames,
                    anomalies_detected,
                ),
            )
        return self.get(run_id)  # type: ignore[return-value]

    def get(self, run_id: str) -> dict[str, Any] | None:
        """Fetch a detection run by ID."""
        query = "SELECT * FROM runs WHERE id = ?;"
        cursor = self.conn.cursor()
        cursor.execute(query, (run_id,))
        row = cursor.fetchone()
        cursor.close()
        return dict(row) if row is not None else None

    def list_by_dataset(self, dataset_id: str) -> list[dict[str, Any]]:
        """List all runs for a specific dataset."""
        query = "SELECT * FROM runs WHERE dataset_id = ? ORDER BY started_at DESC;"
        cursor = self.conn.cursor()
        cursor.execute(query, (dataset_id,))
        rows = cursor.fetchall()
        cursor.close()
        return [dict(r) for r in rows]


class AlertRepo:
    """Repository managing detected anomaly alerts. Alerts store anomalies only."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn if conn is not None else get_connection()

    def insert_many(self, alerts: list[dict[str, Any]]) -> int:
        """Insert alerts in batches of 1,000 using executemany with '?' placeholders.

        Args:
            alerts: List of alert dictionaries containing run_id, timestamp, can_id,
                    attack_type, severity, confidence, and optional details.

        Returns:
            int: Total number of inserted alerts.
        """
        if not alerts:
            return 0

        query = (
            "INSERT INTO alerts (run_id, timestamp, can_id, attack_type, severity, confidence, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);"
        )

        chunk_size = 1000
        total_inserted = 0

        with self.conn:
            cursor = self.conn.cursor()
            for start_idx in range(0, len(alerts), chunk_size):
                chunk = alerts[start_idx : start_idx + chunk_size]
                tuples = [
                    (
                        item["run_id"],
                        float(item["timestamp"]),
                        int(item["can_id"]),
                        str(item["attack_type"]),
                        str(item["severity"]),
                        float(item.get("confidence", 1.0)),
                        (
                            str(item.get("details", ""))
                            if item.get("details") is not None
                            else None
                        ),
                    )
                    for item in chunk
                ]
                cursor.executemany(query, tuples)
                total_inserted += len(chunk)
            cursor.close()

        logger.info("Inserted %d alerts in chunks of %d", total_inserted, chunk_size)
        return total_inserted

    def filter(
        self,
        run_id: str | None = None,
        severity: str | None = None,
        can_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query and filter anomalies by severity, CAN ID, and run ID."""
        clauses: list[str] = []
        params: list[Any] = []

        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity.lower())
        if can_id is not None:
            clauses.append("can_id = ?")
            params.append(int(can_id))

        where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            f"SELECT * FROM alerts {where_stmt} "
            f"ORDER BY timestamp ASC LIMIT ? OFFSET ?;"
        )
        params.extend([limit, offset])

        cursor = self.conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        return [dict(r) for r in rows]

    def count(
        self,
        run_id: str | None = None,
        severity: str | None = None,
        can_id: int | None = None,
    ) -> int:
        """Count total matching anomaly alerts."""
        clauses: list[str] = []
        params: list[Any] = []

        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity.lower())
        if can_id is not None:
            clauses.append("can_id = ?")
            params.append(int(can_id))

        where_stmt = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT COUNT(*) FROM alerts {where_stmt};"

        cursor = self.conn.cursor()
        cursor.execute(query, tuple(params))
        total = cursor.fetchone()[0]
        cursor.close()
        return int(total)


class MetricsRepo:
    """Repository managing model evaluation metrics per run."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn if conn is not None else get_connection()

    def insert(
        self,
        run_id: str,
        metric_name: str,
        metric_value: float,
        split: str = "test",
    ) -> int:
        """Insert a single evaluation metric entry."""
        query = (
            "INSERT INTO metrics (run_id, metric_name, metric_value, split) "
            "VALUES (?, ?, ?, ?);"
        )
        with self.conn:
            cursor = self.conn.execute(
                query, (run_id, metric_name, float(metric_value), split)
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def insert_many(self, metrics: list[dict[str, Any]]) -> int:
        """Insert multiple evaluation metrics."""
        query = (
            "INSERT INTO metrics (run_id, metric_name, metric_value, split) "
            "VALUES (?, ?, ?, ?);"
        )
        tuples = [
            (
                m["run_id"],
                str(m["metric_name"]),
                float(m["metric_value"]),
                str(m.get("split", "test")),
            )
            for m in metrics
        ]
        with self.conn:
            cursor = self.conn.cursor()
            cursor.executemany(query, tuples)
            count = len(tuples)
            cursor.close()
        return count

    def get_by_run(self, run_id: str) -> list[dict[str, Any]]:
        """Retrieve all metrics recorded for a given run."""
        query = "SELECT * FROM metrics WHERE run_id = ? ORDER BY id ASC;"
        cursor = self.conn.cursor()
        cursor.execute(query, (run_id,))
        rows = cursor.fetchall()
        cursor.close()
        return [dict(r) for r in rows]
