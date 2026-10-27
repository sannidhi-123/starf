from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.dataset.models import Base
from app.modules.dataset.service import DatasetService


@pytest.fixture
async def dataset_service(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'datasets.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = DatasetService(
        storage_dir=tmp_path / "uploads",
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )
    yield service
    await engine.dispose()


def upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


@pytest.mark.asyncio
async def test_upload_metadata_filter_download_and_delete(
    dataset_service: DatasetService, tmp_path: Path
) -> None:
    content = b"timestamp,can_id,dlc\n0.0,0x123,1\n0.1,0x456,2\n"
    item = await dataset_service.create(
        upload("drive.csv", content), source="Car-Hacking"
    )

    assert item["name"] == "drive"
    assert item["source"] == "Car-Hacking"
    assert item["row_count"] == 2
    assert item["columns"] == ["timestamp", "can_id", "dlc"]
    assert item["size_bytes"] == len(content)
    assert (tmp_path / "uploads" / f"{item['id']}.csv").read_bytes() == content

    page = await dataset_service.list(
        q="DRIVE", source="Car-Hacking", status_filter="ready"
    )
    assert page["total"] == 1
    assert page["items"][0]["id"] == item["id"]
    assert (await dataset_service.get(item["id"]))["sha256"] == item["sha256"]
    assert await dataset_service.file(item["id"]) == (
        tmp_path / "uploads" / f"{item['id']}.csv",
        "drive.csv",
    )

    await dataset_service.delete(item["id"])
    assert not (tmp_path / "uploads" / f"{item['id']}.csv").exists()
    assert (await dataset_service.list())["total"] == 0


@pytest.mark.asyncio
async def test_rejects_malformed_csv_without_persisting(
    dataset_service: DatasetService,
) -> None:
    malformed = b"timestamp,can_id,dlc\n0.0,0x123\n"

    with pytest.raises(HTTPException) as error:
        await dataset_service.create(upload("bad.csv", malformed))

    assert error.value.status_code == 422
    assert (await dataset_service.list())["total"] == 0


@pytest.mark.asyncio
async def test_rejects_unsupported_file_type(dataset_service: DatasetService) -> None:
    with pytest.raises(HTTPException) as error:
        await dataset_service.create(upload("capture.log", b"not a supported file"))

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_dataset_api_upload_list_download_and_delete(
    dataset_service: DatasetService, monkeypatch
) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.api.routes import datasets as dataset_routes
    from app.main import app

    monkeypatch.setattr(dataset_routes, "service", dataset_service)
    content = b"timestamp,can_id,dlc\n0.0,0x123,1\n"

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/datasets",
                files={"file": ("capture.csv", content, "text/csv")},
                data={"name": "CAN capture", "source": "fixture"},
            )
            assert response.status_code == 201
            dataset_id = response.json()["id"]

            listed = await client.get(
                "/api/v1/datasets", params={"q": "capture", "source": "fixture"}
            )
            assert listed.status_code == 200
            assert listed.json()["total"] == 1
            assert listed.json()["items"][0]["id"] == dataset_id

            details = await client.get(f"/api/v1/datasets/{dataset_id}")
            assert details.status_code == 200
            assert details.json()["name"] == "CAN capture"

            downloaded = await client.get(f"/api/v1/datasets/{dataset_id}/download")
            assert downloaded.status_code == 200
            assert downloaded.content == content

            deleted = await client.delete(f"/api/v1/datasets/{dataset_id}")
            assert deleted.status_code == 204
            missing = await client.get(f"/api/v1/datasets/{dataset_id}")
            assert missing.status_code == 404


@pytest.mark.asyncio
async def test_accepts_parquet_and_records_schema(
    dataset_service: DatasetService,
) -> None:
    import pandas as pd

    buffer = BytesIO()
    pd.DataFrame({"timestamp": [0.0, 0.1], "can_id": [291, 1110]}).to_parquet(
        buffer, index=False
    )
    item = await dataset_service.create(upload("frames.parquet", buffer.getvalue()))

    assert item["format"] == "parquet"
    assert item["row_count"] == 2
    assert item["columns"] == ["timestamp", "can_id"]
