"""Per-security news-sentiment score (§10).

Combines recent news sentiment (-1..1) with headline volume into a score in
[-1, 1]. An event flag (upcoming results/dividends/SENS) is part of the spec,
but we have no events feed yet, so it is reported as False rather than guessed
(Guardrail 2.7). Pure and deterministic (§14).

Input ``sentiments`` is a list of (sentiment, relevance) pairs for recent
articles tagged to the security; ``None`` sentiment values are ignored.
"""

from __future__ import annotations

from app.signals.scoring import LayerScore, SubSignal, clamp

# Headline volume that counts as "high interest".
_VOLUME_FULL = 5


def sentiment_score(
    sentiments: list[tuple[float | None, float | None]],
    *,
    event_flag: bool = False,
) -> LayerScore:
    scored = [(s, r) for s, r in sentiments if s is not None]
    if not scored:
        return LayerScore(
            score=0.0,
            subsignals=[],
            extra={"article_count": 0, "event_flag": event_flag, "note": "no recent news"},
        )

    # Relevance-weighted mean sentiment (fall back to equal weights).
    total_w = sum((r or 1.0) for _s, r in scored)
    mean_sentiment = sum(s * (r or 1.0) for s, r in scored) / total_w

    subs: list[SubSignal] = [
        SubSignal(
            "news_sentiment",
            f"Avg sentiment {mean_sentiment:+.2f} over {len(scored)} article(s)",
            round(mean_sentiment, 4),
        )
    ]

    # Volume scales conviction: more coverage -> closer to the raw mean.
    volume_factor = min(1.0, len(scored) / _VOLUME_FULL)
    score = mean_sentiment * volume_factor
    if volume_factor < 1.0:
        subs.append(
            SubSignal("headline_volume", f"Low coverage ({len(scored)}) dampens conviction", 0.0)
        )

    if event_flag:
        subs.append(SubSignal("event", "Upcoming scheduled event flagged", 0.0))

    return LayerScore(
        score=clamp(score),
        subsignals=subs,
        extra={
            "article_count": len(scored),
            "mean_sentiment": round(mean_sentiment, 4),
            "event_flag": event_flag,
        },
    )
