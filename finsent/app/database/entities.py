from __future__ import annotations

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from finsent.app.database.base import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("url", name="uq_news_articles_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    exchange: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    leaf_provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    data_mode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    publisher: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    canonical_url: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    original_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(1024))
    published_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    ingested_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    dedupe_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    model_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    neutral_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_ask_spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_sell_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impact_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_horizon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    catalyst_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    short_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("ticker", "timestamp", name="uq_price_bars_ticker_timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    timestamp: Mapped[DateTime] = mapped_column(DateTime, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    data_mode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    quality_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)


class QuoteSnapshotEntity(Base):
    __tablename__ = "quote_snapshots"
    __table_args__ = (UniqueConstraint("ticker", "exchange", "provider", "market_timestamp", name="uq_quote_snapshots_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    provider_symbol: Mapped[str] = mapped_column(String(64))
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8))
    bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_absolute: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_timestamp: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    ingested_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    leaf_provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    data_mode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    freshness_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    freshness_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    quality_status: Mapped[str] = mapped_column(String(32), index=True)
    data_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_quality_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    data_quality_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SignalSnapshotEntity(Base):
    __tablename__ = "signal_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    ingested_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    quote_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_runs.id"), nullable=True, index=True)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    composite_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    signal_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    overall_sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    action_bias: Mapped[str | None] = mapped_column(String(32), nullable=True)
    net_short_term_view: Mapped[str | None] = mapped_column(String(128), nullable=True)
    final_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_bullets: Mapped[str | None] = mapped_column(Text, nullable=True)


class SchemaMetadata(Base):
    __tablename__ = "schema_metadata"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))
    updated_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("canonical_symbol", name="uq_instruments_canonical_symbol"),
        UniqueConstraint("exchange", "display_symbol", name="uq_instruments_exchange_display_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_symbol: Mapped[str] = mapped_column(String(64), index=True)
    display_symbol: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    market: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider_symbols_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class ArticleInstrument(Base):
    __tablename__ = "article_instruments"
    __table_args__ = (
        UniqueConstraint("article_id", "instrument_id", "association_source", name="uq_article_instruments_scope"),
        Index("ix_article_instruments_instrument_relevance", "instrument_id", "relevance_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    association_source: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    experiment_type: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    configuration_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_version_label: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SentimentAnalysisRun(Base):
    __tablename__ = "sentiment_analysis_runs"
    __table_args__ = (
        Index("ix_sentiment_runs_article_model", "article_id", "model_family", "model_name"),
        Index("ix_sentiment_runs_experiment_model", "experiment_id", "model_family", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id"), index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_runs.id"), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_family: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    analysis_method: Mapped[str] = mapped_column(String(64), index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_horizon: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    catalyst_tag: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    short_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    fallback_used: Mapped[int] = mapped_column(Integer, default=0, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class SignalRun(Base):
    __tablename__ = "signal_runs"
    __table_args__ = (
        Index("ix_signal_runs_instrument_engine_time", "instrument_id", "engine_name", "generated_at"),
        Index("ix_signal_runs_experiment_engine", "experiment_id", "engine_name", "engine_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_runs.id"), nullable=True, index=True)
    legacy_signal_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("signal_snapshots.id"), nullable=True, index=True)
    generated_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    engine_name: Mapped[str] = mapped_column(String(64), index=True)
    engine_version: Mapped[str] = mapped_column(String(32), index=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_mode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_quality_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    news_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    future_component_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class EventStudyResult(Base):
    __tablename__ = "event_study_results"
    __table_args__ = (
        Index("ix_event_study_instrument_horizon", "instrument_id", "horizon_minutes", "event_timestamp"),
        Index("ix_event_study_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("news_articles.id"), nullable=True, index=True)
    sentiment_run_id: Mapped[int | None] = mapped_column(ForeignKey("sentiment_analysis_runs.id"), nullable=True, index=True)
    signal_run_id: Mapped[int | None] = mapped_column(ForeignKey("signal_runs.id"), nullable=True, index=True)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_runs.id"), nullable=True, index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    event_timestamp: Mapped[DateTime] = mapped_column(DateTime, index=True)
    horizon_minutes: Mapped[int] = mapped_column(Integer, index=True)
    target_timestamp: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    matched_market_timestamp: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_adjusted_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    matching_method: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    elapsed_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_quality_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    validity_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class ProviderAuditRun(Base):
    __tablename__ = "provider_audit_runs"
    __table_args__ = (
        Index("ix_provider_audit_provider_status_time", "provider", "status", "started_at"),
        Index("ix_provider_audit_service_time", "service", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    leaf_provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    service: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(64), index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    started_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    data_mode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    from_cache: Mapped[int] = mapped_column(Integer, default=0, index=True)
    fallback_used: Mapped[int] = mapped_column(Integer, default=0, index=True)
    source_timestamp: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    attempt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    freshness_label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    safe_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataQualityAssessmentEntity(Base):
    __tablename__ = "data_quality_assessments"
    __table_args__ = (
        Index("ix_data_quality_subject", "subject_type", "subject_id"),
        Index("ix_data_quality_label_time", "label", "evaluated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    freshness: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    evaluated_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class DatasetMetadata(Base):
    __tablename__ = "dataset_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    path: Mapped[str] = mapped_column(String(1024), index=True)
    dataset_type: Mapped[str] = mapped_column(String(64), index=True)
    market: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    frequency: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    date_start: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    date_end: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    symbol_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_scanned_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    columns_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
