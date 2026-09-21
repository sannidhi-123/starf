from fastapi import APIRouter

from app.api.routes import alerts, datasets, detection, health, ml

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(detection.router, prefix="/detection", tags=["detection"])
api_router.include_router(ml.router, prefix="/ml", tags=["ml"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
