"""
Pydantic configuration models for CascadeBreaker.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class StorageConfig(BaseModel):


    backend: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "cascadebreaker.db"
    postgres_dsn: str | None = None
    table_prefix: str = "cb_"

    @model_validator(mode="after")
    def validate_postgres_dsn(self) -> "StorageConfig":
        if self.backend == "postgres" and not self.postgres_dsn:
            raise ValueError(
                "postgres_dsn is required when storage backend is 'postgres'"
            )
        return self


class BreakerConfig(BaseModel):

    
    failure_threshold: int = Field(default=3, ge=1, le=100)
    recovery_timeout: float = Field(default=30.0, gt=0)
    window_seconds: float = Field(default=60.0, gt=0)
    half_open_max_calls: int = Field(default=1, ge=1)
    call_timeout: float | None = Field(default=30.0, gt=0)
    exclude_exceptions: list[str] = Field(default_factory=list)
    include_exceptions: list[str] = Field(default_factory=list)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    enabled: bool = True
    name_prefix: str = ""
    extra_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}