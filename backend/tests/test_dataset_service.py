import csv
import hashlib
import io

import pytest
from app.api.routes.datasets import get_dataset_service
from app.main import app
from app.modules.dataset.service import REQUIRED_COLUMNS, DatasetService
from fastapi.testclient import TestClient


def csv_text(row: dict[str, str] | None = None, *, count: int = 1) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=REQUIRED_COLUMNS
        + ["is_remote", "source", "capture", "attack_type", "label", "label_quality"],
    )
    writer.writeheader()
    valid = {
        "timestamp": "1.25",
        "can_id": "0x123",
        "dlc": "8",
        **{f"data_{index}": str(index) for index in range(8)},
        "is_remote": "False",
        "source": "unit-test",
        "capture": "inline",
        "attack_type": "normal",
        "label": "0",
        "label_quality": "frame",
    }
    for _ in range(count):
        writer.writerow({**valid, **(row or {})})
    return output.getvalue()


@pytest.fixture
def client():
    service = DatasetService()
    app.dependency_overrides[get_dataset_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def post_csv(client: TestClient, text: str, filename: str = "inline.csv"):
    return client.post(
        "/api/v1/datasets",
        files={"file": (filename, text.encode("utf-8"), "text/csv")},
        data={"name": "inline", "source": "test"},
    )


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"can_id": "not-an-id"}, "can_id must be an integer"),
        ({"can_id": "0x20000000"}, "can_id must be between 0 and 0x1FFFFFFF"),
        ({"dlc": "many"}, "dlc must be an integer from 0 to 8"),
        ({"dlc": "9"}, "dlc must be an integer from 0 to 8"),
        ({"data_0": ""}, "data_0 must be a non-empty integer from 0 to 255"),
        ({"data_0": "256"}, "data_0 must be a non-empty integer from 0 to 255"),
        ({"dlc": "7", "data_7": "1"}, "data_7 must be empty or 0"),
        (
            {"timestamp": "not-a-number"},
            "timestamp must be a finite, non-negative number",
        ),
        ({"timestamp": "NaN"}, "timestamp must be a finite, non-negative number"),
        ({"timestamp": "-1"}, "timestamp must be a finite, non-negative number"),
        ({"is_remote": "maybe"}, "is_remote must be True, False, 1, or 0"),
        ({"label": "2"}, "label must be 0 or 1"),
    ],
)
def test_invalid_row_returns_422_without_persisting(client, row, message):
    before = client.get("/api/v1/datasets").json()["total"]
    response = post_csv(client, csv_text(row))
    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert client.get("/api/v1/datasets").json()["total"] == before


def test_valid_17_column_csv_records_row_count_columns_and_sha256(client):
    text = csv_text(count=5)
    response = post_csv(client, text)
    assert response.status_code == 201
    body = response.json()
    assert body["row_count"] == 5
    assert body["columns"] == REQUIRED_COLUMNS + [
        "is_remote",
        "source",
        "capture",
        "attack_type",
        "label",
        "label_quality",
    ]
    assert body["sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert client.get("/api/v1/datasets").json()["total"] == 1


def test_upload_without_file_returns_422_without_persisting(client):
    before = client.get("/api/v1/datasets").json()["total"]
    response = client.post("/api/v1/datasets", data={"name": "missing"})
    assert response.status_code == 422
    assert "CSV file is required" in response.json()["detail"]
    assert client.get("/api/v1/datasets").json()["total"] == before


def test_metadata_columns_are_retained_as_given(client):
    response = post_csv(
        client,
        csv_text(
            {
                "source": "raw source text",
                "capture": "capture-7",
                "attack_type": "unmapped",
                "label_quality": "custom",
            }
        ),
    )
    assert response.status_code == 201
