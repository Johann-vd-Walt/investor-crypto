"""Schemas for the dev admin run-job endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunJobRequest(BaseModel):
    job_name: str = Field(..., description="Registered job name, e.g. ingest_daily_prices")
    # Optional kwargs passed through to the job (e.g. {"tickers": ["NPN"]}).
    params: dict[str, Any] = Field(default_factory=dict)


class RunJobResponse(BaseModel):
    job_name: str
    result: Any
