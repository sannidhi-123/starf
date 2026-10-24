from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "STARK API"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./stark.db"
    integration_mode: str = "mock"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @field_validator("integration_mode")
    @classmethod
    def validate_integration_mode(cls, value: str) -> str:
        if value not in {"mock", "real"}:
            raise ValueError("integration_mode must be 'mock' or 'real'")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
