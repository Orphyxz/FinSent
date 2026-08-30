from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
from threading import RLock
from time import perf_counter

import pandas as pd

from finsent.app.config.settings import settings
from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.repository import (
    AnalysisRepository,
    NewsRepository,
    PriceRepository,
    QuoteSnapshotRepository,
    SignalSnapshotRepository,
)
from finsent.app.database.research_repository import (
    DataQualityRepository,
    InstrumentRepository,
    ProviderAuditRepository,
    ResearchResultRepository,
)
from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis, build_llm_analyzer, heuristic_article_analysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle, normalize_news_limit
from finsent.app.services.provider_contracts import ProviderAttempt
from finsent.app.services.runtime_diagnostics import runtime_diagnostics
from finsent.app.services.provider_routers import MarketDataRouter, NewsProviderRouter
from finsent.app.services.provider_status import ProviderStatus
from finsent.app.services.signal_engine import CompositeSignal, CompositeSignalEngine
from finsent.app.services.signal_service_v2 import SignalEngineV2Service, SignalRunRecordV2
from finsent.app.services.symbol_registry import SymbolRecord, registry


logger = logging.getLogger(__name__)
_live_persistence_lock = RLock()


@dataclass(slots=True)
class IntelligenceSnapshot:
    symbol: SymbolRecord
    quote: QuoteSnapshot
    articles: list[NormalizedNewsArticle]
    analyses: list[ArticleAnalysis]
    aggregate: AggregateAnalysis
    signal: CompositeSignal
    signal_v2: SignalRunRecordV2 | None
    price_history: pd.DataFrame
    provider_statuses: list[ProviderStatus]
    provider_attempts: list[ProviderAttempt]


class IntelligenceService:
    def __init__(
        self,
        market_router: MarketDataRouter | None = None,
        news_router: NewsProviderRouter | None = None,
    ) -> None:
        self.signal_engine = CompositeSignalEngine()
        self.llm = build_llm_analyzer()
        self.market_router = market_router or MarketDataRouter()
        self.news_router = news_router or NewsProviderRouter()

    def run(self, symbol: SymbolRecord, *, news_limit: int | None = None) -> IntelligenceSnapshot:
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        started = perf_counter()
        requested_news_limit = normalize_news_limit(news_limit, default=settings.default_news_limit)
        init_db()
        provider_statuses: list[ProviderStatus] = []
        provider_attempts: list[ProviderAttempt] = []
        provider_statuses.append(self._sentiment_status())
        logger.info(
            "Running intelligence refresh for %s through consolidated provider routers",
            symbol.provider_symbol,
        )
        quote_result = self.market_router.fetch_quote(symbol)
        provider_statuses.append(quote_result.status)
        provider_attempts.extend(quote_result.attempts)
        quote = quote_result.data
        if quote is None:
            raise RuntimeError("MarketDataRouter returned no quote snapshot object")
        if not quote_result.available:
            logger.warning(
                "Market quote unavailable for %s after provider routing: %s",
                symbol.provider_symbol,
                quote_result.message,
            )
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        start = end - timedelta(days=30)
        price_result = self.market_router.fetch_price_bars(
            symbol,
            start=start,
            end=end,
            interval=settings.default_price_interval,
        )
        provider_statuses.append(price_result.status)
        provider_attempts.extend(price_result.attempts)
        price_history = price_result.data if price_result.data is not None else pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        news_result = self.news_router.fetch_news(symbol, limit=requested_news_limit)
        provider_statuses.append(news_result.status)
        provider_attempts.extend(news_result.attempts)
        fetched_articles = news_result.data or []
        articles = self._dedupe(fetched_articles)
        if fetched_articles and len(articles) < len(fetched_articles):
            logger.info(
                "News provider %s returned %s articles for %s; %s remained after dedupe",
                news_result.provider,
                len(fetched_articles),
                symbol.provider_symbol,
                len(articles),
            )
        if not news_result.available:
            logger.warning(
                "News unavailable for %s after provider routing: %s",
                symbol.provider_symbol,
                news_result.message,
            )
        analyses: list[ArticleAnalysis] = []
        uncached_remote_analyses = 0

        # Read the analysis cache in a short, read-only session. In particular,
        # do not keep a SQLite write transaction open while FinBERT downloads or
        # performs inference on first use.
        with SessionLocal() as cache_session:
            analysis_repo = AnalysisRepository(cache_session)
            cached_analyses = {
                article.dedupe_hash: analysis_repo.get_by_article_hash(article.dedupe_hash)
                for article in articles
            }

        analysis_cache_hits: list[bool] = []
        for article in articles:
            cached = cached_analyses.get(article.dedupe_hash)
            analysis_from_cache = cached is not None
            if cached is not None:
                analysis = cached
            elif uncached_remote_analyses < settings.llm_analysis_limit:
                analysis = self.llm.analyze_article(symbol, article)
                uncached_remote_analyses += 1
            else:
                analysis = heuristic_article_analysis(
                    symbol,
                    article,
                    provider=self.llm.provider_name,
                    parse_status="heuristic_budget_fallback",
                    reason="LLM analysis budget reached for this refresh; local heuristic analysis used.",
                )
            analyses.append(analysis)
            analysis_cache_hits.append(analysis_from_cache)

        article_pairs = list(zip(articles, analyses))
        aggregate = self.llm.aggregate(symbol, article_pairs)
        signal = self.signal_engine.compute(quote, article_pairs, aggregate)
        v2_input = SignalEngineV2Service().build_input(
            instrument=symbol,
            news_pairs=article_pairs,
            quote=quote,
            price_bars=price_history,
            quote_quality=quote_result.quality,
            bars_quality=price_result.quality,
            news_quality=news_result.quality,
            provider_metadata={
                "run_type": "APPLICATION_LIVE_RUN",
                "market_provider": quote_result.provider,
                "news_provider": news_result.provider,
                "feed": getattr(quote, "feed", None) or settings.alpaca_feed,
                "input_fingerprint": _live_input_fingerprint(quote, articles, price_history),
            },
        )

        # SQLite has a single writer. Keep this section small and serialize it
        # across live ticker refreshes so Dash callback concurrency cannot make
        # an otherwise healthy refresh fail with "database is locked".
        with _live_persistence_lock:
            with SessionLocal() as session:
                try:
                    news_repo = NewsRepository(session)
                    price_repo = PriceRepository(session)
                    quote_repo = QuoteSnapshotRepository(session)
                    signal_repo = SignalSnapshotRepository(session)
                    instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)
                    audit_repo = ProviderAuditRepository(session)
                    quality_repo = DataQualityRepository(session)
                    research_repo = ResearchResultRepository(session)

                    quote_repo.upsert_quote_snapshot(symbol, quote)
                    if not quote_result.from_cache:
                        quote_audit = audit_repo.record_provider_result(
                            result=quote_result,
                            operation="fetch_quote",
                            instrument_id=instrument.id,
                            record_count=1 if quote_result.data is not None else 0,
                        )
                        if quote_result.quality is not None:
                            quality_repo.store_assessment(
                                subject_type="provider_audit",
                                subject_id=quote_audit.id,
                                assessment=quote_result.quality,
                            )
                    if not price_result.from_cache:
                        bars_audit = audit_repo.record_provider_result(
                            result=price_result,
                            operation="fetch_price_bars",
                            instrument_id=instrument.id,
                            record_count=0 if price_history is None else int(len(price_history)),
                        )
                        if price_result.quality is not None:
                            quality_repo.store_assessment(
                                subject_type="provider_audit",
                                subject_id=bars_audit.id,
                                assessment=price_result.quality,
                            )
                    if not news_result.from_cache:
                        news_audit = audit_repo.record_provider_result(
                            result=news_result,
                            operation="fetch_news",
                            instrument_id=instrument.id,
                            record_count=len(fetched_articles),
                        )
                        if news_result.quality is not None:
                            quality_repo.store_assessment(
                                subject_type="provider_audit",
                                subject_id=news_audit.id,
                                assessment=news_result.quality,
                            )
                    for article, analysis, analysis_from_cache in zip(
                        articles, analyses, analysis_cache_hits, strict=True
                    ):
                        row = news_repo.upsert_normalized_news(symbol, article, analysis)
                        if not analysis_from_cache and analysis.provider == "finbert":
                            research_repo.store_sentiment_run(
                                article_id=row.id,
                                instrument_id=instrument.id,
                                experiment_id=None,
                                provider="finbert",
                                model_family="finbert",
                                model_name=settings.model_name,
                                model_version=settings.model_name,
                                analysis_method="classifier",
                                schema_version="live_sentiment_analysis_v1",
                                sentiment_label=analysis.sentiment,
                                sentiment_score=_analysis_score(analysis.sentiment, analysis.confidence),
                                confidence=analysis.confidence,
                                relevance=1.0 if analysis.relevant else 0.0,
                                impact_strength=analysis.impact_strength,
                                time_horizon=analysis.time_horizon,
                                catalyst_tag=analysis.catalyst_tag,
                                short_reason=analysis.short_reason,
                                parse_status=analysis.parse_status,
                                fallback_used=False,
                                metadata={"run_type": "APPLICATION_LIVE_RUN", "article_hash": article.dedupe_hash},
                            )

                    signal_v2 = SignalEngineV2Service(session=session).evaluate(
                        v2_input, persist=True, experiment_id=None
                    )
                    if not price_history.empty:
                        price_repo.upsert_price_bars(self.storage_ticker(symbol), price_history)
                    signal_repo.upsert_signal_snapshot(symbol, quote, aggregate, signal)
                    session.commit()
                except Exception:
                    session.rollback()
                    raise

        runtime_diagnostics.record_refresh(
            key=f"intelligence:{symbol.provider_symbol}",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            duration_ms=int((perf_counter() - started) * 1000),
            cache_status="SERVICE",
            symbols=[symbol.provider_symbol],
        )

        return IntelligenceSnapshot(
            symbol,
            quote,
            articles,
            analyses,
            aggregate,
            signal,
            signal_v2,
            price_history,
            provider_statuses,
            provider_attempts,
        )

    def _sentiment_status(self) -> ProviderStatus:
        provider = self.llm.provider_name
        client = getattr(self.llm, "client", None)
        if provider == "gemini" and client is not None and not getattr(client, "configured", False):
            return ProviderStatus.unconfigured("gemini", "sentiment", "GEMINI_API_KEY is not configured; heuristic analysis will be used.")
        if provider == "openai" and not settings.openai_api_key:
            return ProviderStatus.unconfigured("openai", "sentiment", "OPENAI_API_KEY is not configured; OpenAI analyzer is a stub.")
        return ProviderStatus.available_status(provider, "sentiment", f"{provider} sentiment analyzer selected.")

    @staticmethod
    def _dedupe(articles: list[NormalizedNewsArticle]) -> list[NormalizedNewsArticle]:
        seen: set[str] = set()
        ordered: list[NormalizedNewsArticle] = []
        for article in sorted(articles, key=lambda item: item.published_at, reverse=True):
            if article.dedupe_hash in seen:
                continue
            ordered.append(article)
            seen.add(article.dedupe_hash)
        return ordered

    @staticmethod
    def article_hash(title: str, url: str) -> str:
        return sha256(f"{title}|{url}".encode()).hexdigest()

    @staticmethod
    def storage_ticker(symbol: SymbolRecord) -> str:
        return symbol.yahoo_symbol


def _analysis_score(sentiment: str, confidence: float) -> float:
    direction = 1.0 if sentiment == "bullish" else -1.0 if sentiment == "bearish" else 0.0
    return direction * max(0.0, min(float(confidence or 0.0), 1.0))


def _live_input_fingerprint(
    quote: QuoteSnapshot,
    articles: list[NormalizedNewsArticle],
    price_history: pd.DataFrame,
) -> str:
    article_part = ",".join(sorted(article.dedupe_hash for article in articles))
    latest_bar = ""
    latest_close = ""
    if price_history is not None and not price_history.empty:
        latest_ts = pd.to_datetime(price_history.index, errors="coerce").max()
        if pd.notna(latest_ts):
            latest_bar = latest_ts.isoformat()
            try:
                latest_close = str(float(price_history.loc[latest_ts, "Close"]))
            except Exception:
                latest_close = ""
    raw = "|".join(
        [
            quote.provider,
            str(quote.market_timestamp or ""),
            str(quote.current_price or ""),
            latest_bar,
            latest_close,
            article_part,
        ]
    )
    return sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


intelligence_service = IntelligenceService()
