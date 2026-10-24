from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.modules.dataset.service import DatasetService

router = APIRouter()
service = DatasetService()


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    source: str | None = Form(default=None),
) -> dict:
    try:
        return await service.create(file, name=name, source=source)
    finally:
        await file.close()


@router.get("")
async def list_datasets(
    q: str | None = Query(default=None, max_length=255),
    source: str | None = Query(default=None, max_length=128),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(ready|failed)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return await service.list(q=q, source=source, status_filter=status_filter, limit=limit, offset=offset)


@router.get("/{dataset_id}/download")
async def download_dataset(dataset_id: str) -> FileResponse:
    path, filename = await service.file(dataset_id)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str) -> dict:
    return await service.get(dataset_id)


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(dataset_id: str) -> Response:
    await service.delete(dataset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
