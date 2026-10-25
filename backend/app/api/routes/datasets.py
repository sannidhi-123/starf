from email.parser import BytesParser
from email.policy import default
from io import BytesIO

from fastapi import APIRouter, Depends, Request, status
from starlette.datastructures import UploadFile

from app.modules.dataset.service import DatasetService

router = APIRouter()
_dataset_service = DatasetService()


def get_dataset_service() -> DatasetService:
    return _dataset_service


async def _read_multipart_fields(
    request: Request,
) -> tuple[UploadFile | None, str | None, str | None]:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        return None, None, None

    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + await request.body()
    )
    if not message.is_multipart():
        return None, None, None

    uploaded_file = None
    fields: dict[str, str] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue
        value = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if field_name == "file" and filename is not None:
            uploaded_file = UploadFile(filename=filename, file=BytesIO(value))
        elif filename is None:
            fields[field_name] = value.decode(part.get_content_charset() or "utf-8")

    return uploaded_file, fields.get("name"), fields.get("source")


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    request: Request,
    service: DatasetService = Depends(get_dataset_service),  # noqa: B008
) -> dict:
    file, name, source = await _read_multipart_fields(request)
    return await service.upload(file=file, name=name, source=source)


@router.get("")
async def list_datasets(
    service: DatasetService = Depends(get_dataset_service),  # noqa: B008
) -> dict:
    return await service.list_datasets()


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    service: DatasetService = Depends(get_dataset_service),  # noqa: B008
) -> dict:
    return await service.get_dataset(dataset_id)
