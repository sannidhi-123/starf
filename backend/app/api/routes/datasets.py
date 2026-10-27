"""Datasets API routes.

Endpoints:
- GET  /api/v1/datasets               List all available datasets in data/samples/
- GET  /api/v1/datasets/{dataset_id}  Get dataset details, metadata, and preview sample rows
- POST /api/v1/datasets/upload        Upload/register a new CAN-bus CSV dataset (JSON payload)
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.paths import get_samples_dir

router = APIRouter()


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class DatasetUploadPayload(BaseModel):
    """Payload to upload/register a CAN dataset without requiring python-multipart."""

    filename: str = Field(..., description="File name (must end in .csv)")
    content: str = Field(..., description="Raw CSV string content")


@router.get("")
async def list_datasets() -> dict:
    """Return id, name, row-count, and file size for every CSV in data/samples/."""
    items = []
    samples_dir = get_samples_dir()
    if samples_dir.exists():
        for p in sorted(samples_dir.glob("*.csv")):
            try:
                size_bytes = p.stat().st_size
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    rows = max(0, sum(1 for _ in f) - 1)
            except Exception:
                rows = -1
                size_bytes = 0
            items.append(
                {
                    "id": p.stem,
                    "name": p.stem.replace("_", " ").title(),
                    "filename": p.name,
                    "rows": rows,
                    "size_bytes": size_bytes,
                    "size_formatted": _format_size(size_bytes),
                }
            )
    return {"items": items}


@router.get("/{dataset_id}")
async def get_dataset_details(dataset_id: str) -> dict:
    """Return detailed metadata, column list, and preview sample frames for a dataset."""
    if ".." in dataset_id or "/" in dataset_id or "\\" in dataset_id:
        raise HTTPException(status_code=422, detail="Invalid dataset_id: path traversal forbidden.")

    samples_dir = get_samples_dir()
    target = samples_dir / f"{dataset_id}.csv"
    if not target.exists():
        target = samples_dir / dataset_id
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

    try:
        df_preview = pd.read_csv(target, nrows=15, dtype=str)
        columns = list(df_preview.columns)
        size_bytes = target.stat().st_size

        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            total_rows = max(0, sum(1 for _ in f) - 1)

        sample_frames: List[Dict[str, Any]] = []
        for _, row in df_preview.iterrows():
            raw_id = row.get("CAN ID") or row.get("can_id") or row.get("id") or "0x000"
            raw_ts = row.get("Timestamp") or row.get("timestamp") or row.get("ts") or "0.0"
            raw_dlc = row.get("DLC") or row.get("dlc") or "8"

            data_cols = [f"DATA[{i}]" for i in range(8)]
            payload_bytes = []
            for col in data_cols:
                if col in row and pd.notna(row[col]):
                    val = str(row[col]).strip()
                    if val:
                        payload_bytes.append(val.upper().zfill(2))
            payload = " ".join(payload_bytes)

            sample_frames.append(
                {
                    "timestamp": str(raw_ts),
                    "can_id": str(raw_id),
                    "dlc": str(raw_dlc),
                    "payload": payload,
                    "raw_row": {k: str(v) if pd.notna(v) else "" for k, v in row.items()},
                }
            )

        return {
            "id": target.stem,
            "name": target.stem.replace("_", " ").title(),
            "filename": target.name,
            "rows": total_rows,
            "size_bytes": size_bytes,
            "size_formatted": _format_size(size_bytes),
            "columns": columns,
            "sample_frames": sample_frames,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {exc}")


@router.post("/upload")
async def upload_dataset(payload: DatasetUploadPayload) -> dict:
    """Upload/register a CAN-bus CSV file in data/samples/ using pure JSON."""
    filename = payload.filename.strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    safe_name = "".join(c for c in filename if c.isalnum() or c in ("-", "_", ".")).strip()
    if not safe_name.lower().endswith(".csv"):
        safe_name = f"{safe_name}.csv"

    if len(payload.content.strip()) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file content is empty.")

    samples_dir = get_samples_dir()
    samples_dir.mkdir(parents=True, exist_ok=True)
    destination = samples_dir / safe_name

    with open(destination, "w", encoding="utf-8") as f:
        f.write(payload.content)

    with open(destination, "r", encoding="utf-8", errors="ignore") as f:
        rows = max(0, sum(1 for _ in f) - 1)

    size_bytes = destination.stat().st_size

    return {
        "id": destination.stem,
        "name": destination.stem.replace("_", " ").title(),
        "filename": destination.name,
        "rows": rows,
        "size_bytes": size_bytes,
        "size_formatted": _format_size(size_bytes),
        "message": f"Successfully uploaded {destination.name} ({rows} rows)",
    }
