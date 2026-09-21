from typing import Any

from app.integrations.base import Integration


class RealIntegration(Integration):
    """Placeholder for production service clients.

    Keep network clients and credentials in this adapter rather than in route modules.
    """

    mode = "real"

    async def list_datasets(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Configure the dataset service adapter before using real mode")

    async def run_detection(self) -> dict[str, Any]:
        raise NotImplementedError("Configure the detection service adapter before using real mode")

    async def list_models(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Configure the ML service adapter before using real mode")

    async def list_alerts(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Configure the alert service adapter before using real mode")
