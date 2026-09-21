from fastapi import APIRouter, Depends

from app.core.dependencies import get_integration
from app.integrations.base import Integration

router = APIRouter()


@router.post("/run")
async def run_detection(integration: Integration = Depends(get_integration)) -> dict:
    return await integration.run_detection()
