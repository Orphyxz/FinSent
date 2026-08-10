from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from finsent.app.config.settings import settings
from finsent.app.services.gemini_client import GeminiClient
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.sentiment_v2 import (
    CatalystTag,
    GeminiSentimentAnalyzer,
    ModelFailureCategory,
    ModelExecutionStatus,
    normalize_article_input,
)
from finsent.app.services.symbol_registry import SymbolRecord


@dataclass(slots=True)
class ArticleAnalysis:
    relevant: bool
    sentiment: str
    confidence: float
    impact_strength: float
    time_horizon: str
    catalyst_tag: str
    short_reason: str
    provider: str
    parse_status: str


@dataclass(slots=True)
class AggregateAnalysis:
    overall_sentiment: str
    overall_confidence: float
    net_short_term_view: str
    action_bias: str
    final_reason: str
    provider: str


class LLMAnalyzer(Protocol):
    provider_name: str

    def analyze_article(self, symbol: SymbolRecord, article: NormalizedNewsArticle) -> ArticleAnalysis:
        ...

    def aggregate(self, symbol: SymbolRecord, articles: list[tuple[NormalizedNewsArticle, ArticleAnalysis]]) -> AggregateAnalysis:
        ...


class GeminiNewsAnalyzer:
    provider_name = "gemini"

    def __init__(self) -> None:
        self.client = GeminiClient()
        self.v2_analyzer = GeminiSentimentAnalyzer(self.client)

    def analyze_article(self, symbol: SymbolRecord, article: NormalizedNewsArticle) -> ArticleAnalysis:
        if not self.client.configured:
            return heuristic_article_analysis(
                symbol,
                article,
                provider=self.provider_name,
                parse_status="heuristic_unconfigured",
                reason="Gemini is not configured; local heuristic analysis used.",
            )
        self.v2_analyzer.client = self.client
        self.v2_analyzer.model_name = getattr(self.client, "model", self.v2_analyzer.model_name)
        self.v2_analyzer.model_version = self.v2_analyzer.model_name
        result = self.v2_analyzer.analyze(normalize_article_input(symbol, article))
        if result.status == ModelExecutionStatus.SUCCESS:
            return ArticleAnalysis(
                relevant=bool((result.relevance or 0.0) >= 0.5),
                sentiment=result.sentiment_label,
                confidence=float(result.confidence or 0.0),
                impact_strength=float(result.impact_strength or 0.0),
                time_horizon=result.time_horizon or "1-3d",
                catalyst_tag=self._legacy_catalyst(result.catalyst_tag),
                short_reason=result.short_reason or "No explanation generated",
                provider=self.provider_name,
                parse_status="ok",
            )

        reason = result.short_reason or result.fallback_reason or "Gemini analysis failed; local heuristic analysis used."
        if result.failure_category == ModelFailureCategory.PARSE_FAILURE:
            return heuristic_article_analysis(
                symbol,
                article,
                provider=self.provider_name,
                parse_status="heuristic_parse_fallback",
                reason=reason,
            )
        status = "heuristic_quota_fallback" if "quota" in reason.lower() or "rate limit" in reason.lower() else "heuristic_request_fallback"
        return heuristic_article_analysis(symbol, article, provider=self.provider_name, parse_status=status, reason=reason)

    def aggregate(self, symbol: SymbolRecord, articles: list[tuple[NormalizedNewsArticle, ArticleAnalysis]]) -> AggregateAnalysis:
        if not articles:
            return AggregateAnalysis("neutral", 0.0, "no strong edge", "watch", "No relevant fresh news was available for aggregation.", self.provider_name)
        strongest = sorted(articles, key=lambda item: (item[1].impact_strength, item[1].confidence), reverse=True)[0][1]
        bullish = sum(item[1].confidence * item[1].impact_strength for item in articles if item[1].sentiment == "bullish" and item[1].relevant)
        bearish = sum(item[1].confidence * item[1].impact_strength for item in articles if item[1].sentiment == "bearish" and item[1].relevant)
        net = bullish - bearish
        if net > 0.15:
            overall = "bullish"
            action = "buy"
            view = "bullish short-term signal"
        elif net < -0.15:
            overall = "bearish"
            action = "avoid"
            view = "bearish short-term signal"
        else:
            overall = "neutral"
            action = "watch"
            view = "no strong edge"
        return AggregateAnalysis(
            overall_sentiment=overall,
            overall_confidence=max(0.0, min(sum(item[1].confidence for item in articles) / max(len(articles), 1), 1.0)),
            net_short_term_view=view,
            action_bias=action,
            final_reason=strongest.short_reason,
            provider=self.provider_name,
        )

    @staticmethod
    def _safe_score(value: object) -> float:
        try:
            parsed = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(parsed, 1.0))

    @staticmethod
    def _reason_from_exception(exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
            if message:
                return str(message).strip()
        return str(exc).strip() or "LLM request failed; local heuristic analysis used."

    @staticmethod
    def _legacy_catalyst(value: str | None) -> str:
        mapping = {
            CatalystTag.ANALYST_RATING.value: "analyst",
            CatalystTag.LITIGATION.value: "lawsuit",
            CatalystTag.M_AND_A.value: "other",
            CatalystTag.PARTNERSHIP.value: "product",
        }
        return mapping.get(value or "", value or "other")


class OpenAIAnalyzerStub:
    provider_name = "openai"

    def analyze_article(self, symbol: SymbolRecord, article: NormalizedNewsArticle) -> ArticleAnalysis:
        return ArticleAnalysis(False, "neutral", 0.0, 0.0, "1-3d", "other", "OPENAI_API_KEY not configured or analyzer not implemented yet.", self.provider_name, "unconfigured")

    def aggregate(self, symbol: SymbolRecord, articles: list[tuple[NormalizedNewsArticle, ArticleAnalysis]]) -> AggregateAnalysis:
        return AggregateAnalysis("neutral", 0.0, "watch", "watch", "OpenAI analyzer stub only.", self.provider_name)


def build_llm_analyzer() -> LLMAnalyzer:
    provider = settings.sentiment_provider.strip().lower()
    if provider == "openai":
        return OpenAIAnalyzerStub()
    return GeminiNewsAnalyzer()


def heuristic_article_analysis(
    symbol: SymbolRecord,
    article: NormalizedNewsArticle,
    *,
    provider: str,
    parse_status: str,
    reason: str,
) -> ArticleAnalysis:
    text = f"{article.title}. {article.summary or ''}".lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    age_hours = max((now - article.published_at).total_seconds() / 3600.0, 0.0)

    positive_terms = {
        "beat",
        "beats",
        "surge",
        "growth",
        "record",
        "strong",
        "upgrade",
        "raises",
        "raised",
        "buyback",
        "profit",
        "expands",
        "wins",
        "partnership",
        "launch",
        "approval",
    }
    negative_terms = {
        "miss",
        "misses",
        "cut",
        "cuts",
        "downgrade",
        "lawsuit",
        "probe",
        "investigation",
        "fall",
        "drops",
        "drop",
        "slump",
        "warning",
        "weak",
        "decline",
        "layoffs",
        "selloff",
    }
    high_impact_terms = {
        "earnings",
        "guidance",
        "forecast",
        "outlook",
        "regulation",
        "lawsuit",
        "investigation",
        "upgrade",
        "downgrade",
        "merger",
        "acquisition",
        "buyback",
        "dividend",
        "ceo",
        "management",
        "launch",
        "approval",
    }
    low_relevance_terms = {
        "best stocks",
        "worst stocks",
        "most attractive",
        "least attractive",
        "etf",
        "portfolio",
        "magnificent seven",
        "dividend stocks",
        "top stocks",
    }

    positive_hits = sum(1 for term in positive_terms if term in text)
    negative_hits = sum(1 for term in negative_terms if term in text)
    impact_hits = sum(1 for term in high_impact_terms if term in text)
    low_relevance_hits = sum(1 for term in low_relevance_terms if term in text)

    company_name = symbol.display_name.lower()
    ticker = symbol.ticker.lower()
    symbol_match = ticker in text or company_name in text
    provider_relevance = float(article.relevance_score or 0.0)
    relevant = symbol_match or provider_relevance >= 0.5
    if low_relevance_hits and not symbol_match:
        relevant = False

    if positive_hits > negative_hits:
        sentiment = "bullish"
    elif negative_hits > positive_hits:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    confidence = 0.22
    if relevant:
        confidence += 0.14
    confidence += min(abs(positive_hits - negative_hits) * 0.12, 0.28)
    confidence += min(provider_relevance * 0.18, 0.18)
    confidence -= min(age_hours / 240.0, 0.18)
    if sentiment == "neutral" and positive_hits == negative_hits == 0:
        confidence = min(confidence, 0.34)
    confidence = max(0.12, min(confidence, 0.82))

    impact_strength = 0.16
    if relevant:
        impact_strength += 0.10
    impact_strength += min(impact_hits * 0.12, 0.36)
    impact_strength += min(provider_relevance * 0.12, 0.12)
    impact_strength -= min(age_hours / 168.0, 0.12)
    if not relevant:
        impact_strength = min(impact_strength, 0.18)
    impact_strength = max(0.08, min(impact_strength, 0.86))

    if any(term in text for term in {"earnings", "guidance", "forecast", "outlook"}):
        catalyst_tag = "earnings" if "earnings" in text else "guidance"
    elif any(term in text for term in {"upgrade", "downgrade", "analyst"}):
        catalyst_tag = "analyst"
    elif any(term in text for term in {"regulation", "regulator", "policy"}):
        catalyst_tag = "regulation"
    elif any(term in text for term in {"lawsuit", "probe", "investigation"}):
        catalyst_tag = "lawsuit"
    elif any(term in text for term in {"ceo", "management", "executive"}):
        catalyst_tag = "management"
    elif any(term in text for term in {"launch", "product", "device", "chip"}):
        catalyst_tag = "product"
    elif any(term in text for term in {"macro", "inflation", "rates", "fed", "tariff"}):
        catalyst_tag = "macro"
    else:
        catalyst_tag = "other"

    if impact_strength >= 0.58 or any(term in text for term in {"today", "after hours", "guidance", "upgrade", "downgrade"}):
        time_horizon = "intraday"
    elif impact_strength >= 0.34:
        time_horizon = "1-3d"
    else:
        time_horizon = "1-2w"

    if not relevant:
        short_reason = f"{reason} Headline appears weakly tied to {symbol.display_name}, so confidence is capped."
    elif sentiment == "bullish":
        short_reason = f"{reason} Local heuristic detected positive catalyst language around {symbol.display_name}."
    elif sentiment == "bearish":
        short_reason = f"{reason} Local heuristic detected negative catalyst language around {symbol.display_name}."
    else:
        short_reason = f"{reason} Headline reads mixed or informational, so the signal stays neutral."

    return ArticleAnalysis(
        relevant=relevant,
        sentiment=sentiment,
        confidence=confidence,
        impact_strength=impact_strength,
        time_horizon=time_horizon,
        catalyst_tag=catalyst_tag,
        short_reason=short_reason,
        provider=provider,
        parse_status=parse_status,
    )
