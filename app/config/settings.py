"""Application settings loaded from environment variables (12-factor)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        ..., description="SQLAlchemy async DSN, e.g. sqlite+aiosqlite:///./data/badminton.db"
    )
    log_level: str = Field("info", description="Log level: debug|info|warning|error")
    tz: str = Field("Asia/Kolkata", description="Timezone for date display")
    upi_id: str | None = Field(None, description="Default UPI ID interpolated into messages")
    metrics_enabled: bool = Field(True, description="Whether to expose /metrics")
