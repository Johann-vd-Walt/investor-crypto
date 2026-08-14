"""Pydantic response schemas for the health endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    connected: bool
    error: str | None = None


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    app_env: str
    database: DatabaseHealth
    providers: dict[str, bool]  # provider-key name -> enabled
