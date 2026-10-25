"""Integration tests for the detection API endpoints.

Uses a real SQLite temp DB (same pattern as test_alerts.py).  The DB engine is
patched before the TestClient starts so the app lifespan sees the temp DB.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Override DATABASE_URL before any app import
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
_TMP_DB_PATH = _TMP.name
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database as _db_module
from app.main import app


# ---------------------------------------------------------------------------
# DB setup â€” patch engine before TestClient starts the lifespan
# ---------------------------------------------------------------------------

_ASYNC_URL = f"sqlite+aiosqlite:///{_TMP_DB_PATH}"
_TMP_ENGINE = create_async_engine(_ASYNC_URL, echo=False)
_TMP_SF: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=_TMP_ENGINE, expire_on_commit=False
)

# Patch immediately at import time so the module-level engine is replaced
# before the TestClient lifespan triggers init_db().
_db_module.engine = _TMP_ENGINE
_db_module.SessionLocal = _TMP_SF


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    """Create tables once; drop + clean up after module completes."""
    import app.modules.alerts.models  # noqa: F401

    async with _TMP_ENGINE.begin() as conn:
        await conn.run_sync(_db_module.Base.metadata.create_all)

    yield

    async with _TMP_ENGINE.begin() as conn:
        await conn.run_sync(_db_module.Base.metadata.drop_all)
    await _TMP_ENGINE.dispose()
    Path(_TMP_DB_PATH).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Health endpoint still works
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Datasets endpoint
# ---------------------------------------------------------------------------


def test_list_datasets(client):
    resp = client.get("/api/v1/datasets")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert "demo_dos_attack" in ids
    assert "demo_normal" in ids


# ---------------------------------------------------------------------------
# POST /api/v1/detection/run â€” DoS dataset
# ---------------------------------------------------------------------------


def test_run_dos_dataset_produces_alerts(client):
    """POST demo_dos_attack -> alert_count > 0 and alerts in DB."""
    client.delete("/api/v1/alerts")

    resp = client.post(
        "/api/v1/detection/run",
        json={"dataset_id": "demo_dos_attack"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_frames"] > 0
    assert body["alert_count"] > 0, "DoS dataset must produce alerts"

    run_id = body["run_id"]
    alerts_resp = client.get(f"/api/v1/alerts?run_id={run_id}")
    assert alerts_resp.status_code == 200
    items = alerts_resp.json()["items"]
    assert len(items) > 0, "Alerts must be persisted for the DoS run"


def test_run_normal_dataset_few_alerts(client):
    """POST demo_normal -> alert rate <= 3%."""
    resp = client.post(
        "/api/v1/detection/run",
        json={"dataset_id": "demo_normal"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    total = body["total_frames"]
    alerts = body["alert_count"]
    rate = alerts / total if total > 0 else 0.0
    assert rate <= 0.03, f"Normal dataset alert rate {rate:.2%} exceeds 3%"


def test_run_unknown_dataset_404(client):
    resp = client.post(
        "/api/v1/detection/run",
        json={"dataset_id": "nonexistent_dataset"},
    )
    assert resp.status_code == 404


def test_run_path_traversal_rejected(client):
    resp = client.post(
        "/api/v1/detection/run",
        json={"dataset_id": "../../../etc/passwd"},
    )
    assert resp.status_code == 422


def test_run_missing_body_422(client):
    resp = client.post("/api/v1/detection/run", json={})
    assert resp.status_code == 422


def test_run_inline_frames(client):
    resp = client.post(
        "/api/v1/detection/run",
        json={
            "frames": [
                {"timestamp": 0.001, "can_id": "0x140", "dlc": 8,
                 "payload": "0102030405060708"},
                {"timestamp": 0.015, "can_id": "0x140", "dlc": 8,
                 "payload": "0102030405060708"},
                {"timestamp": 0.030, "can_id": "0x140", "dlc": 8,
                 "payload": "0102030405060708"},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["total_frames"] == 3


def test_alerts_summary_after_dos_run(client):
    resp = client.get("/api/v1/alerts/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0


def test_run_empty_frames_422(client):
    """Empty frames list returns 422 Unprocessable Entity."""
    resp = client.post("/api/v1/detection/run", json={"frames": []})
    assert resp.status_code == 422


def test_run_invalid_dlc_422(client):
    """DLC > 8 violates standard CAN bounds and returns 422."""
    resp = client.post(
        "/api/v1/detection/run",
        json={"frames": [{"timestamp": 0.1, "can_id": 0x140, "dlc": 9}]},
    )
    assert resp.status_code == 422


def test_run_mismatched_payload_dlc_422(client):
    """Payload hex length not matching DLC returns 422."""
    resp = client.post(
        "/api/v1/detection/run",
        json={"frames": [{"timestamp": 0.1, "can_id": 0x140, "dlc": 2, "payload": "01020304"}]},
    )
    assert resp.status_code == 422


def test_run_negative_timestamp_422(client):
    """Negative timestamp returns 422."""
    resp = client.post(
        "/api/v1/detection/run",
        json={"frames": [{"timestamp": -0.05, "can_id": 0x140, "dlc": 8}]},
    )
    assert resp.status_code == 422


def test_get_recent_runs(client):
    """GET /api/v1/detection/runs returns items list."""
    resp = client.get("/api/v1/detection/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
