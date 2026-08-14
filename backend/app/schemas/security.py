"""Schemas for the security / access-log endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    event: str  # success | failed | locked
    ip: str | None
    user_agent: str | None


class AuthSummary(BaseModel):
    window_hours: int
    success: int
    failed: int
    locked: int
    distinct_failed_ips: int


class AccessLogResponse(BaseModel):
    summary: AuthSummary
    events: list[AuthEventOut]
