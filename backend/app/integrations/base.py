from abc import ABC, abstractmethod
from typing import Any


class Integration(ABC):
    mode: str

    @abstractmethod
    async def list_datasets(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def run_detection(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def list_alerts(self) -> list[dict[str, Any]]:
        ...
