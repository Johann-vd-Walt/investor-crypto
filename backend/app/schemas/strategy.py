"""Schemas for the strategy auditor."""

from __future__ import annotations

from pydantic import BaseModel


class Finding(BaseModel):
    severity: str            # critical | warn | good | info
    title: str
    detail: str
    suggestion: str | None


class AuditMetrics(BaseModel):
    total_return_pct: float | None
    sharpe: float | None
    psr: float | None
    deflated_sharpe: float | None
    btc_buyhold_pct: float | None
    rebalances: int


class AuditResponse(BaseModel):
    findings: list[Finding]
    metrics: AuditMetrics | None
