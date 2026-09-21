from typing import Any

from app.integrations.base import Integration


class MockIntegration(Integration):
    mode = "mock"

    async def list_datasets(self) -> list[dict[str, Any]]:
        return [{"id": "demo-dataset", "name": "Demo dataset", "status": "ready"}]

    async def run_detection(self) -> dict[str, Any]:
        return {"job_id": "demo-job", "status": "queued", "matches": 0}

    async def list_models(self) -> list[dict[str, Any]]:
        return [{"id": "baseline", "name": "Baseline model", "status": "available"}]

    async def list_alerts(self) -> list[dict[str, Any]]:
        return []
