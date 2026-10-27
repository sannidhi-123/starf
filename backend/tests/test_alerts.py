"""Integration tests for the Alerts API endpoints and AlertService.

Strategy
--------
* A temporary SQLite file is created for each test module session.
* ``DATABASE_URL`` is patched before app import so SQLAlchemy uses the temp DB.
* ``init_db()`` is called once to create tables.
* Three alert records are inserted via AlertService.add_many().
* Tests exercise list, severity filter, summary, and delete.

All existing tests (test_health, test_detection_schemas) must continue to pass
because they import ``app.main`` independently and hit MockIntegration which
does NOT touch the alerts table.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# We must configure the temp DB *before* any app module is imported so that
# ``settings.database_url`` picks up the override.
# ---------------------------------------------------------------------------
_TMP_DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_FILE.close()
_TMP_DB_PATH = _TMP_DB_FILE.name
_TMP_DB_URL = f"sqlite:///{_TMP_DB_PATH}"

os.environ["DATABASE_URL"] = _TMP_DB_URL

# Patch engine + SessionLocal immediately before app components initialize
_ASYNC_URL = _TMP_DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
_TMP_ENGINE = create_async_engine(_ASYNC_URL, echo=False)
_TMP_SF: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=_TMP_ENGINE, expire_on_commit=False
)

# ---------------------------------------------------------------------------
# Now it is safe to import app modules.
# ---------------------------------------------------------------------------
import app.core.database as _db_module  # noqa: E402

_db_module.engine = _TMP_ENGINE
_db_module.SessionLocal = _TMP_SF

from app.main import app  # noqa: E402
from app.modules.alerts.service import AlertService  # noqa: E402

# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Create all tables in the temp SQLite file once per module."""
    _db_module.engine = _TMP_ENGINE
    _db_module.SessionLocal = _TMP_SF

    import app.modules.alerts.models  # noqa: F401 — registers Alert with Base

    async with _TMP_ENGINE.begin() as conn:
        await conn.run_sync(_db_module.Base.metadata.create_all)

    try:
        yield
    finally:
        try:
            async with _TMP_ENGINE.begin() as conn:
                await conn.run_sync(_db_module.Base.metadata.drop_all)
        except Exception:
            pass
        await _TMP_ENGINE.dispose()
        Path(_TMP_DB_PATH).unlink(missing_ok=True)


@pytest.fixture(scope="module")
async def seeded_service(setup_db):
    """Insert 3 alerts and return the AlertService instance."""
    svc = AlertService()

    alerts = [
        {
            "timestamp": 1.0,
            "can_id": 0x100,
            "label": "dos",
            "confidence": 0.965,
            "stage": "both",
            "severity_level": "CRITICAL",
            "severity_score": 11,
            "rule_ids": "R1,R3",
            "reason": "Dual confirmation DoS",
            "rule_evidence": ["unknown CAN ID 0x100"],
            "stage2_prediction": "dos",
            "stage2_confidence": 0.93,
            "stage2_mode": "demo",
        },
        {
            "timestamp": 2.0,
            "can_id": 0x200,
            "label": "fuzzy",
            "confidence": 0.72,
            "stage": "stage2",
            "severity_level": "MEDIUM",
            "severity_score": 5,
            "rule_ids": "R5",
            "reason": "Moderate fuzzy confidence",
        },
        {
            "timestamp": 3.0,
            "can_id": 0x300,
            "label": "normal",
            "confidence": 1.0,
            "stage": "stage1",
            "severity_level": "NONE",
            "severity_score": 0,
            "rule_ids": "",
            "reason": "Clean frame",
        },
    ]

    inserted = await svc.add_many("run-test-001", alerts)
    assert inserted == 3, f"Expected 3 inserts, got {inserted}"
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alerts_all(seeded_service):
    """list_alerts() with no filters returns all 3 inserted records."""
    svc = seeded_service
    items = await svc.list_alerts()
    assert len(items) == 3
    labels = {a.label for a in items}
    assert labels == {"dos", "fuzzy", "normal"}


@pytest.mark.asyncio
async def test_list_alerts_filter_by_run_id(seeded_service):
    """list_alerts(run_id='run-test-001') returns exactly the 3 seeded rows."""
    svc = seeded_service
    items = await svc.list_alerts(run_id="run-test-001")
    assert len(items) == 3


@pytest.mark.asyncio
async def test_list_alerts_filter_by_severity(seeded_service):
    """list_alerts(severity='CRITICAL') returns only the dos alert."""
    svc = seeded_service
    items = await svc.list_alerts(severity="CRITICAL")
    assert len(items) == 1
    assert items[0].label == "dos"
    assert items[0].severity_score == 11


@pytest.mark.asyncio
async def test_alert_out_can_id_hex(seeded_service):
    """AlertOut.can_id_hex is formatted as a 4-digit uppercase hex string."""
    svc = seeded_service
    items = await svc.list_alerts(severity="CRITICAL")
    alert = items[0]
    assert alert.can_id == 0x100
    assert alert.can_id_hex == "0x0100"
    assert alert.details["stage2_prediction"] == "dos"
    assert alert.details["stage2_mode"] == "demo"


@pytest.mark.asyncio
async def test_summary_counts(seeded_service):
    """summary() reflects the 3 inserted rows accurately."""
    svc = seeded_service
    s = await svc.summary(run_id="run-test-001")
    assert s.total == 3
    assert s.by_label.get("dos") == 1
    assert s.by_label.get("fuzzy") == 1
    assert s.by_label.get("normal") == 1
    assert s.by_severity.get("CRITICAL") == 1
    assert s.by_severity.get("MEDIUM") == 1
    assert s.by_severity.get("NONE") == 1


@pytest.mark.asyncio
async def test_summary_no_run_filter(seeded_service):
    """summary() without run_id sums all rows across all runs."""
    svc = seeded_service
    s = await svc.summary()
    assert s.total >= 3  # may be more if other tests share the module DB


# ---------------------------------------------------------------------------
# HTTP endpoint tests via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(setup_db):
    """TestClient that exercises the real FastAPI app (lifespan enabled)."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_http_list_alerts(client):
    """GET /api/v1/alerts returns {"items": [...]} with 3 entries."""
    resp = client.get("/api/v1/alerts?run_id=run-test-001")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 3


def test_http_list_alerts_filter_severity(client):
    """GET /api/v1/alerts?severity=CRITICAL returns only the CRITICAL alert."""
    resp = client.get("/api/v1/alerts?severity=CRITICAL")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["label"] == "dos"
    assert items[0]["can_id_hex"] == "0x0100"


def test_http_summary(client):
    """GET /api/v1/alerts/summary returns correct aggregation."""
    resp = client.get("/api/v1/alerts/summary?run_id=run-test-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["by_label"]["dos"] == 1
    assert body["by_severity"]["CRITICAL"] == 1


def test_http_delete(client):
    """DELETE /api/v1/alerts removes all rows and returns the deleted count."""
    resp = client.delete("/api/v1/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted" in data
    assert data["deleted"] >= 3

    # Confirm the table is now empty
    resp2 = client.get("/api/v1/alerts")
    assert resp2.json()["items"] == []


def test_http_health_still_works(client):
    """GET /api/v1/health must still return 200 with integration=mock."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["integration"] == "mock"
