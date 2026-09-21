from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.dependencies import get_integration
from app.integrations.base import Integration

router = APIRouter()


@router.get("/health")
async def health(integration: Integration = Depends(get_integration)) -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment, "integration": integration.mode}
