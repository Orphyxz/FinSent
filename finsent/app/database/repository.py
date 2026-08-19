from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from finsent.app.database.entities import NewsArticle, PriceBar, QuoteSnapshotEntity, SignalSnapshotEntity
from finsent.app.database.research_repository import (
    ArticleRelationshipRepository,
    InstrumentRepository,
    canonicalize_url,
)
from finsent.app.models.schemas import ScrapedNewsItem, SentimentResult
from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.signal_engine import CompositeSignal
from finsent.app.services.symbol_registry import SymbolRecord


def _analysis_score(label: str, confidence: float) -> float:
    normalized = (label or "neutral").strip().lower()
    if normalized == "bullish":
        return float(confidence or 0.0)
    if normalized == "bearish":
        return -float(confidence or 0.0)
    return 0.0


class NewsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_news_with_sentiment(
        self,
        item: ScrapedNewsItem,
        sentiment: SentimentResult,
    ) -> NewsArticle:
        article = None
        if item.dedupe_hash:
            article = self.session.execute(
                select(NewsArticle)
                .where(NewsArticle.dedupe_hash == item.dedupe_hash)
                .order_by(NewsArticle.ingested_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if article is None:
            article = self.session.execute(
                select(NewsArticle).where(NewsArticle.url == item.url)
            ).scalar_one_or_none()

        if article is None:
            article = NewsArticle(
                ticker=item.ticker,
                exchange=item.exchange,
                source=item.source,
                title=item.title,
                summary=item.summary,
                url=item.url,
                published_at=item.published_at,
            )
            self.session.add(article)

        article.ticker = item.ticker
        article.exchange = item.exchange
        article.source = item.source
        article.provider = item.provider
        article.title = item.title
        article.summary = item.summary
        article.published_at = item.published_at
        article.ingested_at = item.ingested_at
        article.dedupe_hash = item.dedupe_hash
        article.relevance_score = item.relevance_score
        article.sentiment_label = sentiment.label
        article.sentiment_score = sentiment.score
        article.model_label = sentiment.model_label
        article.model_confidence = sentiment.model_confidence
        article.text_score = sentiment.text_score
        article.signal_confidence = sentiment.signal_confidence
        article.positive_score = sentiment.positive
        article.negative_score = sentiment.negative
        article.neutral_score = sentiment.neutral
        article.bid_ask_spread = sentiment.bid_ask_spread
        article.spread_pct = sentiment.spread_pct
        article.volume_ratio = sentiment.volume_ratio
        article.buy_sell_ratio = sentiment.buy_sell_ratio
        article.buy_pressure = sentiment.buy_pressure
        article.market_signal = sentiment.market_signal
        article.relevant = 1 if sentiment.relevant else 0
        article.impact_strength = sentiment.impact_strength
        article.time_horizon = sentiment.time_horizon
        article.catalyst_tag = sentiment.catalyst_tag
        article.short_reason = sentiment.short_reason
        article.analysis_provider = sentiment.analysis_provider
        article.parse_status = sentiment.parse_status
        self.session.flush()
        return article

    def upsert_normalized_news(
        self,
        symbol: SymbolRecord,
        article: NormalizedNewsArticle,
        analysis: ArticleAnalysis,
    ) -> NewsArticle:
        instrument = InstrumentRepository(self.session).get_or_create_from_symbol(symbol)
        sentiment_score = _analysis_score(analysis.sentiment, analysis.confidence)
        item = ScrapedNewsItem(
            ticker=symbol.ticker,
            source=article.source,
            title=article.title,
            url=article.url,
            published_at=article.published_at,
            summary=article.summary,
            exchange=symbol.exchange,
            provider=article.provider,
            ingested_at=article.ingested_at,
            dedupe_hash=article.dedupe_hash,
            relevance_score=article.relevance_score,
        )
        sentiment = SentimentResult(
            label=analysis.sentiment,
            score=sentiment_score,
            positive=float(analysis.confidence) if analysis.sentiment == "bullish" else 0.0,
            negative=float(analysis.confidence) if analysis.sentiment == "bearish" else 0.0,
            neutral=max(0.0, 1.0 - float(analysis.confidence)) if analysis.sentiment == "neutral" else 0.0,
            model_label=analysis.sentiment,
            model_confidence=analysis.confidence,
            text_score=sentiment_score,
            signal_confidence=analysis.confidence,
            relevant=analysis.relevant,
            impact_strength=analysis.impact_strength,
            time_horizon=analysis.time_horizon,
            catalyst_tag=analysis.catalyst_tag,
            short_reason=analysis.short_reason,
            analysis_provider=analysis.provider,
            parse_status=analysis.parse_status,
        )
        row = self.upsert_news_with_sentiment(item, sentiment)
        row.instrument_id = instrument.id
        row.source_provider = article.provider
        row.leaf_provider = article.provider
        row.publisher = article.source
        row.original_url = article.url
        row.canonical_url = canonicalize_url(article.url)
        row.raw_symbol = getattr(symbol, "provider_symbol", f"{symbol.exchange}:{symbol.ticker}" if symbol.exchange != "US" else symbol.ticker)
        ArticleRelationshipRepository(self.session).link_article_to_instrument(
            article_id=row.id,
            instrument_id=instrument.id,
            relevance_score=article.relevance_score,
            association_source="provider_symbol_query",
        )
        self.session.flush()
        return row

    def list_news_df(self, ticker: str | None = None, exchange: str | None = None) -> pd.DataFrame:
        stmt = select(NewsArticle).order_by(NewsArticle.published_at.asc())
        if ticker:
            raw = ticker.upper()
            inferred_exchange = exchange.upper() if exchange else None
            inferred_ticker = raw
            if raw.endswith(".NS"):
                inferred_exchange = inferred_exchange or "NSE"
                inferred_ticker = raw[:-3]
            elif raw.endswith(".BO"):
                inferred_exchange = inferred_exchange or "BSE"
                inferred_ticker = raw[:-3]
            stmt = stmt.where(NewsArticle.ticker == inferred_ticker)
            if inferred_exchange:
                stmt = stmt.where(NewsArticle.exchange == inferred_exchange)
        rows = self.session.execute(stmt).scalars().all()
        return pd.DataFrame(
            [
                {
                    "id": row.id,
                    "ticker": row.ticker,
                    "exchange": row.exchange,
                    "source": row.source,
                    "provider": row.provider,
                    "title": row.title,
                    "summary": row.summary,
                    "url": row.url,
                    "published_at": row.published_at,
                    "ingested_at": row.ingested_at,
                    "dedupe_hash": row.dedupe_hash,
                    "relevance_score": row.relevance_score,
                    "sentiment_label": row.sentiment_label,
                    "sentiment_score": row.sentiment_score,
                    "model_label": row.model_label,
                    "model_confidence": row.model_confidence,
                    "text_score": row.text_score,
                    "signal_confidence": row.signal_confidence,
                    "positive_score": row.positive_score,
                    "negative_score": row.negative_score,
                    "neutral_score": row.neutral_score,
                    "bid_ask_spread": row.bid_ask_spread,
                    "spread_pct": row.spread_pct,
                    "volume_ratio": row.volume_ratio,
                    "buy_sell_ratio": row.buy_sell_ratio,
                    "buy_pressure": row.buy_pressure,
                    "market_signal": row.market_signal,
                    "relevant": row.relevant,
                    "impact_strength": row.impact_strength,
                    "time_horizon": row.time_horizon,
                    "catalyst_tag": row.catalyst_tag,
                    "short_reason": row.short_reason,
                    "analysis_provider": row.analysis_provider,
                    "parse_status": row.parse_status,
                }
                for row in rows
            ]
        )


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_price_bars(
        self,
        ticker: str,
        price_frame: pd.DataFrame,
        *,
        provider: str | None = None,
        dataset_id: str | None = None,
        data_mode: str | None = None,
        quality_status: str | None = None,
    ) -> None:
        ticker = ticker.upper()
        timestamps = [timestamp.to_pydatetime() for timestamp in price_frame.index]
        existing_rows = self.session.execute(
            select(PriceBar).where(
                PriceBar.ticker == ticker,
                PriceBar.timestamp.in_(timestamps),
            )
        ).scalars().all()
        existing_by_timestamp = {row.timestamp: row for row in existing_rows}

        for timestamp, row in price_frame.iterrows():
            dt = timestamp.to_pydatetime()
            price_bar = existing_by_timestamp.get(dt)
            if price_bar is None:
                price_bar = PriceBar(ticker=ticker, timestamp=dt)
                self.session.add(price_bar)
                existing_by_timestamp[dt] = price_bar

            price_bar.open = float(row["Open"])
            price_bar.high = float(row["High"])
            price_bar.low = float(row["Low"])
            price_bar.close = float(row["Close"])
            price_bar.volume = float(row["Volume"])
            if provider is not None:
                price_bar.provider = provider
            if dataset_id is not None:
                price_bar.dataset_id = dataset_id
            if data_mode is not None:
                price_bar.data_mode = data_mode
            if quality_status is not None:
                price_bar.quality_status = quality_status

        self.session.flush()

    def list_price_df(self, ticker: str) -> pd.DataFrame:
        rows = self.session.execute(
            select(PriceBar)
            .where(PriceBar.ticker == ticker.upper())
            .order_by(PriceBar.timestamp.asc())
        ).scalars().all()
        return pd.DataFrame(
            [
                {
                    "ticker": row.ticker,
                    "timestamp": row.timestamp,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                }
                for row in rows
            ]
        )


class QuoteSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_quote_snapshot(self, symbol: SymbolRecord, snapshot: QuoteSnapshot) -> QuoteSnapshotEntity:
        instrument = InstrumentRepository(self.session).get_or_create_from_symbol(symbol)
        entity = None
        if snapshot.market_timestamp is not None:
            entity = self.session.execute(
                select(QuoteSnapshotEntity)
                .where(
                    QuoteSnapshotEntity.ticker == symbol.ticker,
                    QuoteSnapshotEntity.exchange == symbol.exchange,
                    QuoteSnapshotEntity.provider == snapshot.provider,
                    QuoteSnapshotEntity.market_timestamp == snapshot.market_timestamp,
                )
                .limit(1)
            ).scalar_one_or_none()
        if entity is None:
            entity = QuoteSnapshotEntity(
                ticker=symbol.ticker,
                exchange=symbol.exchange,
                provider=snapshot.provider,
                market_timestamp=snapshot.market_timestamp,
            )
            self.session.add(entity)
        entity.instrument_id = instrument.id
        entity.provider_symbol = snapshot.provider_symbol
        entity.current_price = snapshot.current_price
        entity.currency = snapshot.currency
        entity.bid = snapshot.bid
        entity.ask = snapshot.ask
        entity.spread_absolute = snapshot.spread_absolute
        entity.spread_percentage = snapshot.spread_percentage
        entity.volume = snapshot.volume
        entity.ingested_at = snapshot.ingested_at
        entity.leaf_provider = snapshot.provider
        entity.freshness_seconds = snapshot.freshness_seconds
        entity.quality_status = snapshot.quality_status
        entity.note = snapshot.note
        self.session.flush()
        return entity

    def latest_for_symbol(self, ticker: str, exchange: str) -> QuoteSnapshotEntity | None:
        return self.session.execute(
            select(QuoteSnapshotEntity)
            .where(QuoteSnapshotEntity.ticker == ticker.upper(), QuoteSnapshotEntity.exchange == exchange.upper())
            .order_by(
                case(
                    (
                        (QuoteSnapshotEntity.current_price.is_not(None))
                        & (QuoteSnapshotEntity.quality_status.in_(["live", "delayed", "stale"])),
                        0,
                    ),
                    else_=1,
                ),
                QuoteSnapshotEntity.ingested_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()


class AnalysisRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_article_hash(self, article_hash: str) -> ArticleAnalysis | None:
        row = self.session.execute(
            select(NewsArticle).where(NewsArticle.dedupe_hash == article_hash).order_by(NewsArticle.ingested_at.desc()).limit(1)
        ).scalar_one_or_none()
        if row is None or row.analysis_provider is None:
            return None
        parse_status = (row.parse_status or "ok").strip().lower()
        if parse_status in {"request_failed", "parse_failed"}:
            return None
        return ArticleAnalysis(
            relevant=bool(row.relevant),
            sentiment=(row.sentiment_label or "neutral").replace("positive", "bullish").replace("negative", "bearish"),
            confidence=float(row.model_confidence or 0.0),
            impact_strength=float(row.impact_strength or 0.0),
            time_horizon=row.time_horizon or "1-3d",
            catalyst_tag=row.catalyst_tag or "other",
            short_reason=row.short_reason or "",
            provider=row.analysis_provider,
            parse_status=parse_status,
        )

    def upsert_article_analysis(self, symbol: SymbolRecord, article: NormalizedNewsArticle, analysis: ArticleAnalysis) -> None:
        # persisted through news upsert path; kept as explicit repository hook for cache ownership
        return None


class SignalSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_signal_snapshot(
        self,
        symbol: SymbolRecord,
        quote: QuoteSnapshot,
        aggregate: AggregateAnalysis,
        signal: CompositeSignal,
    ) -> SignalSnapshotEntity:
        instrument = InstrumentRepository(self.session).get_or_create_from_symbol(symbol)
        entity = self.session.execute(
            select(SignalSnapshotEntity)
            .where(
                SignalSnapshotEntity.instrument_id == instrument.id,
                SignalSnapshotEntity.ticker == symbol.ticker,
                SignalSnapshotEntity.exchange == symbol.exchange,
                SignalSnapshotEntity.ingested_at == quote.ingested_at,
                SignalSnapshotEntity.engine_name == "Signal Engine",
                SignalSnapshotEntity.engine_version == "V1",
            )
            .limit(1)
        ).scalar_one_or_none()
        if entity is None:
            entity = SignalSnapshotEntity(
                instrument_id=instrument.id,
                ticker=symbol.ticker,
                exchange=symbol.exchange,
                ingested_at=quote.ingested_at,
                engine_name="Signal Engine",
                engine_version="V1",
            )
            self.session.add(entity)
        entity.quote_provider = quote.provider
        entity.analysis_provider = aggregate.provider
        entity.composite_score = signal.composite_score
        entity.composite_label = signal.composite_label
        entity.signal_confidence = signal.signal_confidence
        entity.mode = signal.mode
        entity.overall_sentiment = aggregate.overall_sentiment
        entity.overall_confidence = aggregate.overall_confidence
        entity.action_bias = aggregate.action_bias
        entity.net_short_term_view = aggregate.net_short_term_view
        entity.final_reason = aggregate.final_reason
        entity.explanation_bullets = "\n".join(signal.explanation_bullets)
        self.session.flush()
        return entity

    def latest_for_symbol(self, ticker: str, exchange: str) -> SignalSnapshotEntity | None:
        return self.session.execute(
            select(SignalSnapshotEntity)
            .where(
                SignalSnapshotEntity.ticker == ticker.upper(),
                SignalSnapshotEntity.exchange == exchange.upper(),
            )
            .order_by(SignalSnapshotEntity.ingested_at.desc())
            .limit(1)
        ).scalar_one_or_none()
