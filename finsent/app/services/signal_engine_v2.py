from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any

import pandas as pd

from finsent.app.services.llm_analyzers import ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_reliability import DataQualityAssessment, DataQualityLabel, FreshnessLabel
from finsent.app.services.symbol_registry import SymbolRecord


ENGINE_NAME_V2 = "finsent_composite"
ENGINE_VERSION_V2 = "2.0"
ENGINE_VERSION_V2_1_RESEARCH = "2.1-research"


@dataclass(frozen=True, slots=True)
class SignalEngineV2Config:
    news_weight: float = 0.55
    momentum_weight: float = 0.35
    volume_confirmation_weight: float = 0.10
    momentum_return_scale: float = 0.05
    strong_threshold: float = 0.55
    directional_threshold: float = 0.20
    confidence_high_threshold: float = 0.70
    confidence_medium_threshold: float = 0.40
    max_news_age_hours: float = 72.0
    min_news_recency_weight: float = 0.20
    wide_spread_threshold: float = 0.01


V2_0_CONFIG = SignalEngineV2Config()


def validate_signal_v2_config(config: SignalEngineV2Config) -> None:
    weights = [config.news_weight, config.momentum_weight, config.volume_confirmation_weight]
    if any(not math.isfinite(weight) or weight < 0 for weight in weights):
        raise ValueError("Signal V2 weights must be finite and non-negative.")
    if abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("Signal V2 directional weights must sum to 1.0.")
    if config.volume_confirmation_weight > 0.15:
        raise ValueError("Volume confirmation weight must remain a minority term.")
    if not 0.0 < config.directional_threshold < config.strong_threshold <= 1.0:
        raise ValueError("Directional and strong thresholds are invalid.")


@dataclass(frozen=True, slots=True)
class SignalNewsItemV2:
    article: NormalizedNewsArticle
    analysis: ArticleAnalysis


@dataclass(frozen=True, slots=True)
class SignalInputV2:
    instrument: SymbolRecord
    evaluation_timestamp: datetime
    news_items: list[SignalNewsItemV2] = field(default_factory=list)
    quote: QuoteSnapshot | None = None
    price_bars: pd.DataFrame | None = None
    quote_quality: DataQualityAssessment | None = None
    bars_quality: DataQualityAssessment | None = None
    news_quality: DataQualityAssessment | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SignalComponentV2:
    name: str
    available: bool
    raw_value: float | None
    normalized_value: float
    weight: float
    contribution: float
    reliability: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SignalResultV2:
    engine_name: str
    engine_version: str
    final_score: float
    label: str
    confidence: float
    confidence_label: str
    signal_mode: str
    components: list[SignalComponentV2]
    explanation: str
    top_supporting_factors: list[str]
    top_opposing_factors: list[str]
    warnings: list[str]
    missing_inputs: list[str]
    data_quality: dict[str, Any]
    generated_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clamp(value: float, minimum: float = -1.0, maximum: float = 1.0) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(min(value, maximum), minimum)


def score_label(score: float, config: SignalEngineV2Config = SignalEngineV2Config()) -> str:
    if score >= config.strong_threshold:
        return "strong_bullish"
    if score >= config.directional_threshold:
        return "bullish"
    if score <= -config.strong_threshold:
        return "strong_bearish"
    if score <= -config.directional_threshold:
        return "bearish"
    return "neutral"


def confidence_label(confidence: float, config: SignalEngineV2Config = SignalEngineV2Config()) -> str:
    if confidence >= config.confidence_high_threshold:
        return "high"
    if confidence >= config.confidence_medium_threshold:
        return "medium"
    return "low"


class SignalEngineV2:
    def __init__(self, config: SignalEngineV2Config | None = None) -> None:
        self.config = config or SignalEngineV2Config()

    def evaluate(self, signal_input: SignalInputV2) -> SignalResultV2:
        news_component = self.news_component(signal_input)
        momentum_component = self.momentum_component(signal_input)
        volume_component = self.volume_component(signal_input, news_component, momentum_component)
        directional_components = [news_component, momentum_component, volume_component]
        available_directional = [component for component in directional_components if component.available and component.weight > 0]
        missing_inputs = [component.name for component in directional_components if not component.available]

        raw_score = self._weighted_directional_score(available_directional)
        liquidity_component = self.liquidity_component(signal_input)
        freshness_component = self.freshness_component(signal_input)
        quality_component = self.data_quality_component(signal_input)
        reliability_components = [liquidity_component, freshness_component, quality_component]
        attenuation = self._attenuation(reliability_components)
        final_score = clamp(raw_score * attenuation)
        confidence = self._confidence(final_score, available_directional, reliability_components)
        all_components = directional_components + reliability_components
        warnings = self._warnings(signal_input, reliability_components, missing_inputs)
        mode = self._mode(news_component, momentum_component)
        explanation, supporting, opposing = self._explain(final_score, all_components, warnings, missing_inputs)
        return SignalResultV2(
            engine_name=ENGINE_NAME_V2,
            engine_version=ENGINE_VERSION_V2,
            final_score=final_score,
            label=score_label(final_score, self.config),
            confidence=confidence,
            confidence_label=confidence_label(confidence, self.config),
            signal_mode=mode,
            components=all_components,
            explanation=explanation,
            top_supporting_factors=supporting,
            top_opposing_factors=opposing,
            warnings=warnings,
            missing_inputs=missing_inputs,
            data_quality=self._quality_summary(signal_input),
            generated_at=signal_input.evaluation_timestamp,
        )

    def news_component(self, signal_input: SignalInputV2) -> SignalComponentV2:
        if not signal_input.news_items:
            return SignalComponentV2("news", False, None, 0.0, self.config.news_weight, 0.0, 0.0, "No analyzed news items were available.")
        weighted_sum = 0.0
        total_weight = 0.0
        signed_weights: list[float] = []
        for item in signal_input.news_items:
            analysis = item.analysis
            relevance = 1.0 if analysis.relevant else 0.25
            source_relevance = item.article.relevance_score if item.article.relevance_score is not None else relevance
            relevance = max(min(float(source_relevance), 1.0), 0.0) if analysis.relevant else min(relevance, 0.25)
            confidence = max(min(float(analysis.confidence or 0.0), 1.0), 0.0)
            impact = max(min(float(analysis.impact_strength or 0.0), 1.0), 0.0)
            recency = self._news_recency_weight(item.article.published_at, signal_input.evaluation_timestamp)
            heuristic_factor = 0.75 if str(analysis.parse_status).startswith("heuristic") else 1.0
            direction = 1.0 if analysis.sentiment == "bullish" else -1.0 if analysis.sentiment == "bearish" else 0.0
            weight = relevance * confidence * impact * recency * heuristic_factor
            weighted_sum += direction * weight
            total_weight += weight
            signed_weights.append(direction * weight)
        if total_weight <= 0:
            return SignalComponentV2("news", True, 0.0, 0.0, self.config.news_weight, 0.0, 0.2, "News was available but did not contain directional evidence.", {"agreement": 1.0})
        normalized = clamp(weighted_sum / total_weight)
        agreement = abs(weighted_sum) / total_weight if total_weight > 0 else 0.0
        reliability = max(0.0, min((total_weight / max(len(signal_input.news_items), 1)) * (0.5 + 0.5 * agreement), 1.0))
        return SignalComponentV2(
            "news",
            True,
            weighted_sum / total_weight,
            normalized,
            self.config.news_weight,
            normalized * self.config.news_weight,
            reliability,
            "Recent, relevant news was aggregated by sentiment, confidence, impact, relevance, and recency.",
            {"agreement": agreement, "weighted_items": len(signal_input.news_items), "total_weight": total_weight},
        )

    def momentum_component(self, signal_input: SignalInputV2) -> SignalComponentV2:
        frame = self._valid_bars(signal_input.price_bars)
        if frame is None or len(frame) < 2:
            return SignalComponentV2("price_momentum", False, None, 0.0, self.config.momentum_weight, 0.0, 0.0, "Insufficient valid OHLCV bars for price momentum.")
        closes = frame["Close"].astype(float)
        horizons = self._momentum_horizons(len(closes))
        weighted_score = 0.0
        total_weight = 0.0
        abs_weighted = 0.0
        details: list[dict[str, float]] = []
        horizon_weights = [0.5, 0.3, 0.2]
        for idx, horizon in enumerate(horizons):
            old = float(closes.iloc[-horizon - 1])
            new = float(closes.iloc[-1])
            if old <= 0:
                continue
            raw_return = (new - old) / old
            normalized = clamp(raw_return / self.config.momentum_return_scale)
            weight = horizon_weights[min(idx, len(horizon_weights) - 1)]
            weighted_score += normalized * weight
            abs_weighted += abs(normalized * weight)
            total_weight += weight
            details.append({"horizon_bars": float(horizon), "return": raw_return, "normalized": normalized, "weight": weight})
        if total_weight <= 0:
            return SignalComponentV2("price_momentum", False, None, 0.0, self.config.momentum_weight, 0.0, 0.0, "No valid momentum horizon could be calculated.")
        normalized = clamp(weighted_score / total_weight)
        agreement = abs(weighted_score) / abs_weighted if abs_weighted > 0 else 1.0
        reliability = max(0.2, min(0.65 + 0.35 * agreement, 1.0))
        return SignalComponentV2(
            "price_momentum",
            True,
            details[0]["return"] if details else None,
            normalized,
            self.config.momentum_weight,
            normalized * self.config.momentum_weight,
            reliability,
            "Recent close-to-close returns were combined across available short horizons.",
            {"horizons": details, "agreement": agreement},
        )

    def volume_component(self, signal_input: SignalInputV2, news: SignalComponentV2, momentum: SignalComponentV2) -> SignalComponentV2:
        frame = self._valid_bars(signal_input.price_bars)
        base_direction = self._base_direction(news, momentum)
        if frame is None or "Volume" not in frame.columns or len(frame) < 3:
            return SignalComponentV2("volume_confirmation", False, None, 0.0, self.config.volume_confirmation_weight, 0.0, 0.0, "Insufficient volume history for confirmation.")
        volumes = pd.to_numeric(frame["Volume"], errors="coerce").dropna()
        if len(volumes) < 3:
            return SignalComponentV2("volume_confirmation", False, None, 0.0, self.config.volume_confirmation_weight, 0.0, 0.0, "Volume values are missing or malformed.")
        recent = float(volumes.iloc[-1])
        baseline = float(volumes.iloc[:-1].tail(20).median())
        if recent < 0 or baseline <= 0:
            return SignalComponentV2("volume_confirmation", False, None, 0.0, self.config.volume_confirmation_weight, 0.0, 0.0, "Volume baseline is invalid.")
        relative = recent / baseline
        if abs(base_direction) < 0.05:
            normalized = 0.0
            reason = "Volume was high/low but there was no directional move to confirm."
        else:
            confirmation = clamp((relative - 1.0) / 2.0, -0.5, 0.5)
            normalized = clamp(math.copysign(abs(confirmation), base_direction))
            reason = "Volume confirms or weakens the existing directional evidence; it does not create direction by itself."
        reliability = max(0.2, min(0.5 + min(abs(relative - 1.0), 1.0) * 0.5, 1.0))
        return SignalComponentV2(
            "volume_confirmation",
            True,
            relative,
            normalized,
            self.config.volume_confirmation_weight,
            normalized * self.config.volume_confirmation_weight,
            reliability,
            reason,
            {"recent_volume": recent, "baseline_volume": baseline, "relative_volume": relative, "base_direction": base_direction},
        )

    def liquidity_component(self, signal_input: SignalInputV2) -> SignalComponentV2:
        quote = signal_input.quote
        if quote is None:
            return SignalComponentV2("liquidity", False, None, 0.0, 0.0, 0.0, 0.5, "No quote was available for liquidity/spread assessment.")
        spread_pct = quote.spread_percentage
        if spread_pct is None and quote.bid is not None and quote.ask is not None and quote.bid > 0 and quote.ask > 0:
            midpoint = (quote.bid + quote.ask) / 2.0
            spread_pct = (quote.ask - quote.bid) / midpoint if midpoint > 0 else None
        if spread_pct is None:
            return SignalComponentV2("liquidity", False, None, 0.0, 0.0, 0.0, 0.50, "Bid/ask spread is unavailable; confidence is reduced.")
        reliability = 1.0 - max(min(float(spread_pct) / self.config.wide_spread_threshold, 1.0), 0.0) * 0.45
        return SignalComponentV2("liquidity", True, float(spread_pct), 0.0, 0.0, 0.0, reliability, "Spread affects confidence and attenuation, not direction.", {"spread_percentage": float(spread_pct)})

    def freshness_component(self, signal_input: SignalInputV2) -> SignalComponentV2:
        freshness = signal_input.quote_quality.freshness if signal_input.quote_quality is not None else None
        if freshness is None and signal_input.quote is not None and signal_input.quote.freshness_seconds is not None:
            seconds = signal_input.quote.freshness_seconds
            if seconds <= 60:
                freshness = FreshnessLabel.FRESH
            elif seconds <= 900:
                freshness = FreshnessLabel.AGING
            else:
                freshness = FreshnessLabel.STALE
        mapping = {FreshnessLabel.FRESH: 1.0, FreshnessLabel.AGING: 0.78, FreshnessLabel.STALE: 0.45, FreshnessLabel.UNKNOWN: 0.60}
        reliability = mapping.get(freshness, 0.60)
        reason = f"Freshness is {freshness.value if freshness else 'UNKNOWN'}; it affects trust, not direction."
        return SignalComponentV2("freshness", freshness is not None, None, 0.0, 0.0, 0.0, reliability, reason, {"freshness": freshness.value if freshness else "UNKNOWN"})

    def data_quality_component(self, signal_input: SignalInputV2) -> SignalComponentV2:
        assessments = [item for item in [signal_input.quote_quality, signal_input.bars_quality, signal_input.news_quality] if item is not None]
        if not assessments:
            return SignalComponentV2("data_quality", False, None, 0.0, 0.0, 0.0, 0.65, "No explicit data-quality assessment was supplied.")
        score = sum(item.score for item in assessments) / len(assessments)
        return SignalComponentV2("data_quality", True, score, 0.0, 0.0, 0.0, max(0.15, min(score, 1.0)), "Data quality attenuates score and confidence without changing direction.", {"labels": [item.label.value for item in assessments]})

    def _weighted_directional_score(self, components: list[SignalComponentV2]) -> float:
        if not components:
            return 0.0
        total = sum(component.weight for component in components)
        if total <= 0:
            return 0.0
        return clamp(sum(component.normalized_value * component.weight for component in components) / total)

    def _attenuation(self, reliability_components: list[SignalComponentV2]) -> float:
        if not reliability_components:
            return 1.0
        reliabilities = [component.reliability for component in reliability_components]
        return max(0.25, min(sum(reliabilities) / len(reliabilities), 1.0))

    def _confidence(self, final_score: float, directional: list[SignalComponentV2], reliability: list[SignalComponentV2]) -> float:
        if not directional:
            return 0.0
        availability = len(directional) / 3.0
        component_reliability = sum(component.reliability for component in directional + reliability) / max(len(directional + reliability), 1)
        agreement = self._component_agreement(directional)
        strength = abs(final_score)
        return max(0.0, min((0.35 * strength) + (0.30 * component_reliability) + (0.20 * agreement) + (0.15 * availability), 1.0))

    def _component_agreement(self, components: list[SignalComponentV2]) -> float:
        directional = [component for component in components if component.available and abs(component.normalized_value) > 0.05]
        if len(directional) <= 1:
            return 1.0
        weighted = sum(component.normalized_value * component.weight for component in directional)
        absolute = sum(abs(component.normalized_value * component.weight) for component in directional)
        return abs(weighted) / absolute if absolute > 0 else 1.0

    def _news_recency_weight(self, published_at: datetime, now: datetime) -> float:
        age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
        decay = 1.0 - min(age_hours / self.config.max_news_age_hours, 1.0) * (1.0 - self.config.min_news_recency_weight)
        return max(self.config.min_news_recency_weight, decay)

    def _valid_bars(self, frame: pd.DataFrame | None) -> pd.DataFrame | None:
        if frame is None or frame.empty or "Close" not in frame.columns:
            return None
        required = [column for column in ["Open", "High", "Low", "Close", "Volume"] if column in frame.columns]
        result = frame.copy()
        result = result.sort_index()
        for column in required:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        result = result.dropna(subset=["Close"])
        result = result[result["Close"] > 0]
        return result if len(result) >= 2 else None

    @staticmethod
    def _momentum_horizons(length: int) -> list[int]:
        candidates = [1, min(4, length - 1), min(16, length - 1)]
        seen: list[int] = []
        for candidate in candidates:
            if candidate >= 1 and candidate not in seen:
                seen.append(candidate)
        return seen

    @staticmethod
    def _base_direction(news: SignalComponentV2, momentum: SignalComponentV2) -> float:
        values = [component.normalized_value for component in [news, momentum] if component.available]
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _mode(news: SignalComponentV2, momentum: SignalComponentV2) -> str:
        if news.available and momentum.available:
            return "NEWS_PLUS_MARKET"
        if news.available:
            return "NEWS_ONLY"
        if momentum.available:
            return "MARKET_ONLY"
        return "INSUFFICIENT_DATA"

    def _warnings(self, signal_input: SignalInputV2, reliability: list[SignalComponentV2], missing: list[str]) -> list[str]:
        warnings: list[str] = []
        if missing:
            warnings.append(f"Missing components: {', '.join(missing)}.")
        for component in reliability:
            if component.reliability < 0.55:
                warnings.append(component.reason)
        if signal_input.quote is not None and signal_input.quote.quality_status in {"stale", "unavailable", "unconfigured"}:
            warnings.append(f"Quote quality is {signal_input.quote.quality_status}.")
        return warnings

    def _explain(
        self,
        final_score: float,
        components: list[SignalComponentV2],
        warnings: list[str],
        missing: list[str],
    ) -> tuple[str, list[str], list[str]]:
        directional = [component for component in components if component.weight > 0 and component.available]
        supporting = sorted(
            [component for component in directional if component.contribution * (1 if final_score >= 0 else -1) > 0],
            key=lambda item: abs(item.contribution),
            reverse=True,
        )
        opposing = sorted(
            [component for component in directional if component.contribution * (1 if final_score >= 0 else -1) < 0],
            key=lambda item: abs(item.contribution),
            reverse=True,
        )
        support_reasons = [component.reason for component in supporting[:2]]
        oppose_reasons = [component.reason for component in opposing[:2]]
        label = score_label(final_score, self.config).replace("_", " ")
        pieces = [f"{label.title()} analytical signal."]
        if support_reasons:
            pieces.append(support_reasons[0])
        if oppose_reasons:
            pieces.append(f"Opposing evidence exists: {oppose_reasons[0]}")
        if warnings:
            pieces.append(warnings[0])
        elif missing:
            pieces.append(f"Missing inputs: {', '.join(missing)}.")
        return " ".join(pieces), support_reasons, oppose_reasons

    @staticmethod
    def _quality_summary(signal_input: SignalInputV2) -> dict[str, Any]:
        def item(assessment: DataQualityAssessment | None) -> dict[str, Any] | None:
            if assessment is None:
                return None
            return {
                "score": assessment.score,
                "label": assessment.label.value,
                "freshness": assessment.freshness.value,
                "provider": assessment.provider,
                "mode": assessment.mode.value,
                "reasons": assessment.reasons,
            }
        return {"quote": item(signal_input.quote_quality), "bars": item(signal_input.bars_quality), "news": item(signal_input.news_quality)}


def component_to_dict(component: SignalComponentV2) -> dict[str, Any]:
    return {
        "name": component.name,
        "available": component.available,
        "raw_value": component.raw_value,
        "normalized_value": component.normalized_value,
        "weight": component.weight,
        "contribution": component.contribution,
        "reliability": component.reliability,
        "reason": component.reason,
        "metadata": component.metadata,
    }


def result_metadata(result: SignalResultV2) -> dict[str, Any]:
    return {
        "components": [component_to_dict(component) for component in result.components],
        "confidence_label": result.confidence_label,
        "top_supporting_factors": result.top_supporting_factors,
        "top_opposing_factors": result.top_opposing_factors,
        "warnings": result.warnings,
        "missing_inputs": result.missing_inputs,
        "data_quality": result.data_quality,
    }
