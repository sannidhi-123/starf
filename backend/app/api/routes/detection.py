from fastapi import APIRouter, Depends

from app.core.dependencies import get_integration
from app.integrations.base import Integration
from app.modules.detection.pipeline import DetectionPipeline, FrameBatch

router = APIRouter()
pipeline = DetectionPipeline()


@router.post("/run")
async def run_detection(integration: Integration = Depends(get_integration)) -> dict:
    return await integration.run_detection()


@router.post("/frames")
async def detect_frames(batch: FrameBatch) -> dict:
    """Process live, uploaded, and simulated frames through one entry point."""
    results = pipeline.process(batch.frames)
    alerts = [result for result in results if result["is_alert_candidate"]]
    return {
        "items": results,
        "summary": {
            "total": len(results),
            "normal": len(results) - len(alerts),
            "alerts": len(alerts),
            "classes": {
                name: sum(result["final_class"] == name for result in results)
                for name in sorted({result["final_class"] for result in results})
            },
        },
    }
