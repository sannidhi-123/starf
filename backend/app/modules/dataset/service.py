from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import uuid
from typing import Any

from fastapi import HTTPException, UploadFile

REQUIRED_COLUMNS = [
    "timestamp",
    "can_id",
    "dlc",
    *(f"data_{index}" for index in range(8)),
]
OPTIONAL_COLUMNS = [
    "is_remote",
    "source",
    "capture",
    "attack_type",
    "label",
    "label_quality",
]
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class DatasetService:
    """Validate CSV datasets and maintain an in-process dataset catalog."""

    def __init__(self) -> None:
        self._datasets: dict[str, dict[str, Any]] = {}

    async def upload(
        self,
        file: UploadFile | None,
        name: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        if file is None:
            raise HTTPException(
                status_code=422, detail="A CSV file is required in the 'file' field."
            )
        if not file.filename or not file.filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=400, detail="The uploaded file must have a .csv extension."
            )

        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"The uploaded file exceeds the {MAX_UPLOAD_BYTES}-byte limit.",
            )
        if not content:
            raise HTTPException(status_code=422, detail="The CSV file is empty.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=422, detail="The CSV file must use UTF-8 encoding."
            ) from exc

        try:
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            header = next(reader, None)
        except csv.Error as exc:
            raise HTTPException(
                status_code=422, detail=f"Invalid CSV structure: {exc}."
            ) from exc
        if not header:
            raise HTTPException(status_code=422, detail="The CSV header is missing.")
        if len(set(header)) != len(header):
            raise HTTPException(
                status_code=422, detail="The CSV header contains duplicate columns."
            )
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Missing required CSV columns: {', '.join(missing)}.",
            )

        rows: list[dict[str, str]] = []
        columns = list(header)
        try:
            for row_number, values in enumerate(reader, start=2):
                if not values or all(not value.strip() for value in values):
                    continue
                if len(values) != len(header):
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Row {row_number}: expected {len(header)} fields, "
                            f"found {len(values)}."
                        ),
                    )
                row = dict(zip(header, values, strict=True))
                self._validate_row(row, row_number)
                rows.append(row)
        except csv.Error as exc:
            raise HTTPException(
                status_code=422, detail=f"Invalid CSV structure: {exc}."
            ) from exc

        if not rows:
            raise HTTPException(
                status_code=422, detail="The CSV file has no data rows."
            )

        dataset_id = str(uuid.uuid4())
        result = {
            "id": dataset_id,
            "name": name or file.filename.rsplit(".", 1)[0],
            "source": source,
            "filename": file.filename,
            "status": "ready",
            "row_count": len(rows),
            "columns": columns,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        self._datasets[dataset_id] = result
        return result

    async def list_datasets(self) -> dict[str, Any]:
        return {"items": list(self._datasets.values()), "total": len(self._datasets)}

    async def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        dataset = self._datasets.get(dataset_id)
        if dataset is None:
            raise HTTPException(
                status_code=404, detail=f"Dataset '{dataset_id}' was not found."
            )
        return dataset

    @staticmethod
    def _validate_row(row: dict[str, str], row_number: int) -> None:
        try:
            can_id_text = row["can_id"].strip()
            if not re.fullmatch(r"[+-]?(?:0[xX][0-9a-fA-F]+|[0-9]+)", can_id_text):
                raise ValueError
            can_id = int(can_id_text, 16 if "x" in can_id_text.lower() else 10)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: can_id must be an integer in decimal or 0x-prefixed hexadecimal form.",
            ) from exc
        if not 0 <= can_id <= 0x1FFFFFFF:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: can_id must be between 0 and 0x1FFFFFFF.",
            )

        try:
            dlc_text = row["dlc"].strip()
            if not dlc_text or any(
                character not in "+-0123456789" for character in dlc_text
            ):
                raise ValueError
            dlc = int(dlc_text, 10)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: dlc must be an integer from 0 to 8.",
            ) from exc
        if not 0 <= dlc <= 8:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: dlc must be an integer from 0 to 8.",
            )

        for index in range(dlc):
            value = row[f"data_{index}"].strip()
            try:
                if not re.fullmatch(r"[+-]?[0-9]+", value):
                    raise ValueError
                byte = int(value, 10)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: data_{index} must be a non-empty integer from 0 to 255 when index is less than dlc.",
                ) from exc
            if not 0 <= byte <= 255:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: data_{index} must be a non-empty integer from 0 to 255 when index is less than dlc.",
                )
        for index in range(dlc, 8):
            if row[f"data_{index}"].strip() not in {"", "0"}:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: data_{index} must be empty or 0 when index is greater than or equal to dlc.",
                )

        try:
            timestamp_text = row["timestamp"].strip()
            if not re.fullmatch(
                r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",
                timestamp_text,
            ):
                raise ValueError
            timestamp = float(timestamp_text)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: timestamp must be a finite, non-negative number.",
            ) from exc
        if not math.isfinite(timestamp) or timestamp < 0:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: timestamp must be a finite, non-negative number.",
            )

        if "is_remote" in row and row["is_remote"].strip().casefold() not in {
            "true",
            "false",
            "1",
            "0",
        }:
            raise HTTPException(
                status_code=422,
                detail=f"Row {row_number}: is_remote must be True, False, 1, or 0 (case-insensitive).",
            )
        if "label" in row and row["label"].strip() not in {"0", "1"}:
            raise HTTPException(
                status_code=422, detail=f"Row {row_number}: label must be 0 or 1."
            )
