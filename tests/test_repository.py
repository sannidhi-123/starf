"""Tests for STARK SQLite database repositories and performance."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from stark.storage.db import get_connection, run_migrations
from stark.storage.repository import AlertRepo, DatasetRepo, MetricsRepo, RunRepo


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    """Fixture providing an initialized SQLite test database with WAL and foreign keys."""
    db_file = tmp_path / "test_stark.db"
    run_migrations(db_path=db_file)
    conn = get_connection(db_path=db_file)
    yield conn
    conn.close()


def test_insert_and_read_back(test_db: sqlite3.Connection):
    """Verify insert and read-back for datasets, runs, alerts, and metrics."""
    dataset_repo = DatasetRepo(test_db)
    run_repo = RunRepo(test_db)
    alert_repo = AlertRepo(test_db)
    metrics_repo = MetricsRepo(test_db)

    # 1. Dataset
    ds = dataset_repo.create(
        dataset_id="ds_test_01",
        name="Test Dataset",
        source="car_hacking",
        file_path="/tmp/test.csv",
        row_count=5000,
        size_bytes=102400,
    )
    assert ds["id"] == "ds_test_01"
    assert ds["name"] == "Test Dataset"
    assert ds["row_count"] == 5000

    fetched_ds = dataset_repo.get("ds_test_01")
    assert fetched_ds is not None
    assert fetched_ds["source"] == "car_hacking"

    # 2. Run
    run = run_repo.create(
        run_id="run_test_01",
        dataset_id="ds_test_01",
        model_version="stark_v1.0",
        total_frames=5000,
        anomalies_detected=10,
    )
    assert run["id"] == "run_test_01"
    assert run["dataset_id"] == "ds_test_01"

    # 3. Alert
    inserted_count = alert_repo.insert_many(
        [
            {
                "run_id": "run_test_01",
                "timestamp": 12.345678,
                "can_id": 0x316,
                "attack_type": "rpm_spoof",
                "severity": "critical",
                "confidence": 0.98,
                "details": "High RPM surge detected",
            }
        ]
    )
    assert inserted_count == 1
    alerts = alert_repo.filter(run_id="run_test_01")
    assert len(alerts) == 1
    assert alerts[0]["can_id"] == 0x316
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["confidence"] == 0.98

    # 4. Metrics
    metrics_repo.insert(
        run_id="run_test_01",
        metric_name="macro_f1",
        metric_value=0.992,
        split="test",
    )
    metrics = metrics_repo.get_by_run("run_test_01")
    assert len(metrics) == 1
    assert metrics[0]["metric_name"] == "macro_f1"
    assert pytest.approx(metrics[0]["metric_value"]) == 0.992


def test_filter_by_severity_and_can_id(test_db: sqlite3.Connection):
    """Verify AlertRepo filtering by severity, CAN ID, and combinations."""
    dataset_repo = DatasetRepo(test_db)
    run_repo = RunRepo(test_db)
    alert_repo = AlertRepo(test_db)

    dataset_repo.create("ds_01", "DS", "synthetic", "/data/ds.csv")
    run_repo.create("run_01", "ds_01", "v1.0")

    alerts = [
        {
            "run_id": "run_01",
            "timestamp": 1.0,
            "can_id": 0x100,
            "attack_type": "dos",
            "severity": "critical",
        },
        {
            "run_id": "run_01",
            "timestamp": 2.0,
            "can_id": 0x200,
            "attack_type": "fuzzy",
            "severity": "high",
        },
        {
            "run_id": "run_01",
            "timestamp": 3.0,
            "can_id": 0x100,
            "attack_type": "dos",
            "severity": "high",
        },
        {
            "run_id": "run_01",
            "timestamp": 4.0,
            "can_id": 0x300,
            "attack_type": "gear_spoof",
            "severity": "medium",
        },
    ]
    alert_repo.insert_many(alerts)

    # Filter by severity
    critical_alerts = alert_repo.filter(severity="critical")
    assert len(critical_alerts) == 1
    assert critical_alerts[0]["severity"] == "critical"

    # Filter by CAN ID
    id_100_alerts = alert_repo.filter(can_id=0x100)
    assert len(id_100_alerts) == 2
    assert all(a["can_id"] == 0x100 for a in id_100_alerts)

    # Filter by both severity and CAN ID
    high_100_alerts = alert_repo.filter(severity="high", can_id=0x100)
    assert len(high_100_alerts) == 1
    assert high_100_alerts[0]["timestamp"] == 3.0


def test_one_thousand_inserts_under_one_second(test_db: sqlite3.Connection):
    """Verify AlertRepo.insert_many inserts 1,000 alerts in under 1 second."""
    dataset_repo = DatasetRepo(test_db)
    run_repo = RunRepo(test_db)
    alert_repo = AlertRepo(test_db)

    dataset_repo.create("ds_perf", "Perf DS", "synthetic", "/path")
    run_repo.create("run_perf", "ds_perf", "v1.0")

    alerts = [
        {
            "run_id": "run_perf",
            "timestamp": float(i) * 0.001,
            "can_id": int(0x100 + (i % 16)),
            "attack_type": "dos",
            "severity": "critical" if i % 2 == 0 else "high",
            "confidence": 0.95,
            "details": f"Anomaly frame {i}",
        }
        for i in range(1000)
    ]

    start_time = time.perf_counter()
    inserted = alert_repo.insert_many(alerts)
    elapsed = time.perf_counter() - start_time

    assert inserted == 1000
    assert alert_repo.count(run_id="run_perf") == 1000
    assert elapsed < 1.0, f"1,000 inserts took {elapsed:.4f}s, expected < 1.0s"


def test_foreign_key_violation_rejected(test_db: sqlite3.Connection):
    """Verify SQLite foreign key constraints reject orphaned records."""
    run_repo = RunRepo(test_db)
    alert_repo = AlertRepo(test_db)

    # Attempt to insert a run referencing a non-existent dataset_id
    with pytest.raises(sqlite3.IntegrityError):
        run_repo.create("run_bad", "non_existent_dataset_id", "v1.0")

    # Attempt to insert an alert referencing a non-existent run_id
    with pytest.raises(sqlite3.IntegrityError):
        alert_repo.insert_many(
            [
                {
                    "run_id": "non_existent_run_id",
                    "timestamp": 1.0,
                    "can_id": 0x100,
                    "attack_type": "dos",
                    "severity": "high",
                }
            ]
        )
