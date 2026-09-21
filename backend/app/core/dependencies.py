from collections.abc import AsyncIterator

from app.core.config import settings
from app.integrations.base import Integration
from app.integrations.mock import MockIntegration
from app.integrations.real import RealIntegration


async def get_integration() -> AsyncIterator[Integration]:
    implementation = MockIntegration() if settings.integration_mode == "mock" else RealIntegration()
    yield implementation
