from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.modules.dataset.models import DatasetRecord

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
ALLOWED_FORMATS = {".csv", ".parquet"}
DEFAULT_STORAGE = Path(__file__).resolve().parents[4] / "data" / "uploads"


def _inspect_csv(payload: bytes) -> tuple[int, list[str]]:
    try:
        text = io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", errors="strict", newline="")
        rows = csv.reader(text, strict=True)
        first = next((row for row in rows if row and any(value.strip() for value in row)), None)
        if first is None:
            raise ValueError("CSV contains no records")
        try:
            float(first[0].strip())
            has_header = False
        except ValueError:
            has_header = True
        if has_header:
            columns = [value.strip() for value in first]
            if any(not column for column in columns):
                raise ValueError("CSV header contains an empty column name")
            if len(set(columns)) != len(columns):
                raise ValueError("CSV header contains duplicate column names")
            expected = len(columns)
            count = 0
        else:
            expected = len(first)
            columns = [f"field_{index + 1}" for index in range(expected)]
            count = 1
        for line_number, row in enumerate(rows, start=2):
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != expected:
                raise ValueError(f"CSV row {line_number} has {len(row)} fields; expected {expected}")
            count += 1
        if count == 0:
            raise ValueError("CSV contains a header but no data rows")
        return count, columns
    except (UnicodeDecodeError, csv.Error, StopIteration) as exc:
        raise ValueError("CSV is not valid UTF-8 delimited data") from exc


def _inspect_parquet(payload: bytes) -> tuple[int, list[str]]:
    try:
        frame = pd.read_parquet(io.BytesIO(payload))
    except Exception as exc:
        raise ValueError("File is not a readable Parquet dataset") from exc
    if frame.empty or len(frame.columns) == 0:
        raise ValueError("Parquet dataset must contain at least one row and one column")
    return len(frame), [str(column) for column in frame.columns]


def _metadata(record: DatasetRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "filename": record.filename,
        "format": record.format,
        "source": record.source,
        "status": record.status,
        "row_count": record.row_count,
        "columns": json.loads(record.columns_json),
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


class DatasetService:
    """Validates, stores, and indexes uploaded datasets."""

    def __init__(self, storage_dir: Path = DEFAULT_STORAGE, session_factory=SessionFactory):
        self.storage_dir = storage_dir
        self.session_factory = session_factory

    async def create(
        self, upload: UploadFile, name: str | None = None, source: str | None = None
    ) -> dict[str, Any]:
        filename = Path((upload.filename or "").replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in ALLOWED_FORMATS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a CSV or Parquet file")
        payload = await upload.read(MAX_UPLOAD_BYTES + 1)
        if not payload:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds the 100 MB upload limit")
        try:
            row_count, columns = _inspect_csv(payload) if suffix == ".csv" else _inspect_parquet(payload)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

        dataset_id = str(uuid.uuid4())
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.storage_dir / f"{dataset_id}{suffix}"
        stored_path.write_bytes(payload)
        record = DatasetRecord(
            id=dataset_id,
            name=(name or Path(filename).stem).strip()[:255] or Path(filename).stem,
            filename=filename[:255],
            storage_path=str(stored_path.resolve()),
            format=suffix[1:],
            source=(source.strip()[:128] or None) if source else None,
            status="ready",
            row_count=row_count,
            columns_json=json.dumps(columns),
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            created_at=datetime.now(UTC),
        )
        try:
            async with self.session_factory() as session:
                session.add(record)
                await session.commit()
                await session.refresh(record)
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        return _metadata(record)

    async def list(
        self, q: str | None = None, source: str | None = None, status_filter: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        async with self.session_factory() as session:
            filters = []
            if q:
                filters.append(DatasetRecord.name.ilike(f"%{q.strip()}%"))
            if source:
                filters.append(DatasetRecord.source == source)
            if status_filter:
                filters.append(DatasetRecord.status == status_filter)
            total = await session.scalar(select(func.count()).select_from(DatasetRecord).where(*filters)) or 0
            statement: Select[tuple[DatasetRecord]] = (
                select(DatasetRecord).where(*filters)
                .order_by(DatasetRecord.created_at.desc(), DatasetRecord.id)
                .offset(offset).limit(limit)
            )
            records = (await session.scalars(statement)).all()
            return {"items": [_metadata(record) for record in records], "total": total, "limit": limit, "offset": offset}

    async def get(self, dataset_id: str) -> dict[str, Any]:
        async with self.session_factory() as session:
            record = await session.get(DatasetRecord, dataset_id)
            if record is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
            return _metadata(record)

    async def file(self, dataset_id: str) -> tuple[Path, str]:
        async with self.session_factory() as session:
            record = await session.get(DatasetRecord, dataset_id)
            if record is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
            path = Path(record.storage_path)
            if not path.is_file():
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset file is missing")
            return path, record.filename

    async def delete(self, dataset_id: str) -> None:
        async with self.session_factory() as session:
            record = await session.get(DatasetRecord, dataset_id)
            if record is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
            stored_path = Path(record.storage_path)
            await session.delete(record)
            await session.commit()
        stored_path.unlink(missing_ok=True)
