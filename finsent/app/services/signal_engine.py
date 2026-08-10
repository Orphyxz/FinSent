from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot, is_usable_quote_snapshot
from finsent.app.services.news_providers import NormalizedNewsArticle


@dataclass(slots=True)
class CompositeSignal:
    composite_score: float
    composite_label: str
    signal_confidence: float
    mode: str
    explanation_bullets: list[str]


class CompositeSignalEngine:
    def compute(
        self,
        quote: QuoteSnapshot | None,
        article_pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]],
        aggregate: AggregateAnalysis,
    ) -> CompositeSignal:
        news_score = 0.0
        if article_pairs:
            total_weight = 0.0
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for article, analysis in article_pairs:
                age_hours = max((now - article.published_at).total_seconds() / 3600.0, 0.0)
                recency_weight = max(0.2, 1.0 - min(age_hours / 72.0, 0.8))
                direction = 1.0 if analysis.sentiment == "bullish" else -1.0 if analysis.sentiment == "bearish" else 0.0
                weight = recency_weight * analysis.confidence * analysis.impact_strength
                news_score += direction * weight
                total_weight += weight
            if total_weight > 0:
                news_score /= total_weight

        quote_usable = is_usable_quote_snapshot(quote)

        liquidity_penalty = 0.0
        if quote_usable and quote is not None and quote.spread_percentage is not None:
            liquidity_penalty = min(quote.spread_percentage / 0.01, 1.0)

        freshness_penalty = 0.0
        if quote_usable and quote is not None and quote.freshness_seconds is not None and quote.freshness_seconds > 300:
            freshness_penalty = min((quote.freshness_seconds - 300) / 1800.0, 1.0)

        market_component = 0.0
        if quote_usable and quote is not None:
            market_component = 0.1 if quote.quality_status == "live" else 0.0

        composite_score = max(min((0.75 * news_score) + (0.25 * market_component) - (0.10 * liquidity_penalty) - (0.10 * freshness_penalty), 1.0), -1.0)
        aggregate_confidence = aggregate.overall_confidence if article_pairs else 0.0
        signal_confidence = max(min(aggregate_confidence - (0.1 * freshness_penalty), 1.0), 0.0)

        if composite_score > 0.18:
            label = "bullish"
        elif composite_score < -0.18:
            label = "bearish"
        else:
            label = "neutral"

        if quote_usable and article_pairs:
            mode = "News + Quote Quality"
        elif quote_usable:
            mode = "Quote-quality fallback"
        elif article_pairs:
            mode = "News-only signal"
        else:
            mode = "Unavailable"

        bullets = [
            f"Mode: {mode}",
            f"Aggregate view: {aggregate.net_short_term_view}",
            f"Quote quality: {quote.quality_status if quote is not None else 'unavailable'}",
        ]
        if article_pairs:
            bullets.append(f"Fresh relevant headlines: {sum(1 for _, analysis in article_pairs if analysis.relevant)}")
        else:
            bullets.append("No relevant fresh headlines were available.")
        return CompositeSignal(
            composite_score=composite_score,
            composite_label=label,
            signal_confidence=signal_confidence,
            mode=mode,
            explanation_bullets=bullets,
        )
