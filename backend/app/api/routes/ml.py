from fastapi import APIRouter, Depends

from app.core.dependencies import get_integration
from app.integrations.base import Integration

router = APIRouter()


@router.get("/models")
async def list_models(integration: Integration = Depends(get_integration)) -> dict:
    return {"items": await integration.list_models()}
