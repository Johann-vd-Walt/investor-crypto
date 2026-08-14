"""Shared scoring primitives for the signal layers.

Every layer returns a ``LayerScore`` in [-1, 1] plus the list of sub-signals
that fired, so the engine can build a fully transparent rationale (§8, §10 —
"no hidden black-box confidence").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubSignal:
    name: str
    detail: str
    contribution: float  # signed contribution to the layer score


@dataclass
class LayerScore:
    score: float
    subsignals: list[SubSignal] = field(default_factory=list)
    extra: dict = field(default_factory=dict)  # layer-specific facts (e.g. atr)

    def as_rationale(self) -> dict:
        return {
            "score": round(self.score, 4),
            "signals": [
                {"name": s.name, "detail": s.detail, "contribution": round(s.contribution, 4)}
                for s in self.subsignals
            ],
            **self.extra,
        }


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))
