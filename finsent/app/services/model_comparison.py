from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
from enum import Enum
import importlib.util
import json
import math
from pathlib import Path
import random
from statistics import median
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.analysis.event_study_v2 import (
    ENGINE_NAME_EVENT_STUDY_V2,
    ENGINE_VERSION_EVENT_STUDY_V2,
    EventStudyHorizon,
    EventStudyResultV2,
    EventStudyStatus,
)
from finsent.app.database.entities import EventStudyResult, NewsArticle, SentimentAnalysisRun
from finsent.app.database.repository import PriceRepository
from finsent.app.database.research_repository import ExperimentRepository, InstrumentRepository, json_loads
from finsent.app.services.event_study_service_v2 import EventStudyServiceV2
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.sentiment_intelligence import SentimentExecutionRecord, SentimentIntelligenceService
from finsent.app.services.sentiment_v2 import (
    CatalystTag,
    FinBERTSentimentAnalyzer,
    GeminiSentimentAnalyzer,
    ModelExecutionStatus,
    SentimentAnalysisInput,
    SentimentAnalysisResult,
    SentimentAnalyzer,
)
from finsent.app.services.symbol_registry import SymbolRecord, registry


EXPERIMENT_TYPE = "gemini_finbert_comparison"
COMPARISON_VERSION = "gemini_finbert_comparison_v1"
NORMALIZATION_VERSION = "direction_v1_score_0_15_return_0_001"
DEFAULT_MODEL_THRESHOLD = 0.15
DEFAULT_RETURN_THRESHOLD = 0.001
DEFAULT_CONFIDENCE_BUCKETS = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0000001)


class ExclusionReason:
    GEMINI_FAILED = "GEMINI_FAILED"
    FINBERT_FAILED = "FINBERT_FAILED"
    NO_MARKET_DATA = "NO_MARKET_DATA"
    INVALID_EVENT_STUDY = "INVALID_EVENT_STUDY"
    UNSUPPORTED_HORIZON = "UNSUPPORTED_HORIZON"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    DUPLICATE_SAMPLE = "DUPLICATE_SAMPLE"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    MISSING_INSTRUMENT = "MISSING_INSTRUMENT"
    MISSING_CONTENT = "MISSING_CONTENT"
    SAMPLE_LIMIT = "SAMPLE_LIMIT"


@dataclass(frozen=True, slots=True)
class ModelComparisonConfig:
    experiment_name: str = "Gemini vs FinBERT controlled comparison"
    experiment_type: str = EXPERIMENT_TYPE
    dataset_id: str | None = None
    symbols: list[str] = field(default_factory=list)
    markets: list[str] = field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    providers: list[str] = field(default_factory=list)
    max_articles: int = 5
    random_seed: int = 42
    horizons: list[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    reuse_existing: bool = True
    force_rerun: bool = False
    model_threshold: float = DEFAULT_MODEL_THRESHOLD
    return_threshold: float = DEFAULT_RETURN_THRESHOLD
    minimum_data_quality_label: str | None = None
    gemini_model: str | None = None
    gemini_prompt_version: str | None = None
    finbert_model: str | None = None
    sentiment_normalization_version: str = NORMALIZATION_VERSION
    event_study_engine_version: str = ENGINE_VERSION_EVENT_STUDY_V2

    def to_repository_config(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start_date"] = self.start_date.isoformat() if self.start_date else None
        payload["end_date"] = self.end_date.isoformat() if self.end_date else None
        payload["comparison_version"] = COMPARISON_VERSION
        payload["event_study_engine"] = ENGINE_NAME_EVENT_STUDY_V2
        return payload


@dataclass(slots=True)
class SelectedArticle:
    article_id: int
    instrument: SymbolRecord
    published_at: datetime
    title: str
    summary: str | None
    body: str | None
    publisher: str | None
    provider: str | None
    leaf_provider: str | None
    data_mode: str | None
    dedupe_key: str
    exclusion_reason: str | None = None


@dataclass(slots=True)
class SelectionSummary:
    selected: list[SelectedArticle]
    selected_count: int
    excluded_count: int
    exclusion_counts: dict[str, int]
    metadata: dict[str, Any]


@dataclass(slots=True)
class ModelRunView:
    run_id: int | None
    source: str
    result: SentimentAnalysisResult


@dataclass(slots=True)
class PairedObservation:
    article_id: int
    instrument: str
    market: str
    published_at: datetime
    gemini: ModelRunView | None
    finbert: ModelRunView | None
    event_results: dict[str, EventStudyResultV2]
    gemini_direction: str | None
    finbert_direction: str | None
    agreement: bool | None
    catalyst_tag: str | None
    exclusion_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgreementSummary:
    eligible: int
    agreements: int
    disagreements: int
    agreement_rate: float | None
    matrix: dict[str, dict[str, int]]


@dataclass(slots=True)
class ClassificationMetrics:
    total: int
    correct: int
    incorrect: int
    neutral_prediction_count: int
    neutral_outcome_count: int
    strict_accuracy: float | None
    directional_eligible: int
    directional_correct: int
    directional_accuracy: float | None
    precision: dict[str, float | None]
    recall: dict[str, float | None]
    f1: dict[str, float | None]
    balanced_accuracy: float | None
    wilson_interval: tuple[float, float] | None


@dataclass(slots=True)
class HorizonEvaluationSummary:
    horizon: str
    model: str
    eligible_observations: int
    valid_event_studies: int
    metrics: ClassificationMetrics
    average_return_predicted_bullish: float | None
    average_return_predicted_bearish: float | None


@dataclass(slots=True)
class ConfidenceBucketSummary:
    model: str
    bucket: str
    count: int
    directional_accuracy: float | None
    average_absolute_return: float | None


@dataclass(slots=True)
class DisagreementSummary:
    horizon: str
    sample_count: int
    gemini_correct: int
    finbert_correct: int
    both_wrong: int
    realized_neutral: int


@dataclass(slots=True)
class CatalystSummary:
    catalyst: str
    count: int
    sentiment_distribution: dict[str, int]
    directional_accuracy: dict[str, float | None]
    average_realized_return_by_prediction: dict[str, float | None]


@dataclass(slots=True)
class LatencySummary:
    model: str
    count: int
    mean_ms: float | None
    median_ms: float | None
    p95_ms: float | None


@dataclass(slots=True)
class ExperimentSummary:
    experiment_id: int | None
    config: dict[str, Any]
    selected_count: int
    excluded_count: int
    exclusion_counts: dict[str, int]
    gemini_calls_new: int
    gemini_calls_reused: int
    gemini_calls_failed: int
    finbert_runs_new: int
    finbert_runs_reused: int
    finbert_runs_failed: int
    agreement: AgreementSummary
    horizons: list[HorizonEvaluationSummary]
    confidence_buckets: list[ConfidenceBucketSummary]
    disagreements: list[DisagreementSummary]
    catalysts: list[CatalystSummary]
    latency: list[LatencySummary]
    market_counts: dict[str, int]
    symbol_counts: dict[str, int]
    paired_rows: list[PairedObservation] = field(default_factory=list)


class ArticleSelectionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def select_articles(self, config: ModelComparisonConfig) -> SelectionSummary:
        stmt = select(NewsArticle).order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
        if config.start_date is not None:
            stmt = stmt.where(NewsArticle.published_at >= config.start_date)
        if config.end_date is not None:
            stmt = stmt.where(NewsArticle.published_at <= config.end_date)
        if config.markets:
            stmt = stmt.where(NewsArticle.exchange.in_([market.upper() for market in config.markets]))
        if config.providers:
            stmt = stmt.where(NewsArticle.provider.in_(config.providers))
        if config.symbols:
            requested = {value.upper() for value in config.symbols}
            tickers = {value.split(":", 1)[-1].replace(".NS", "").replace(".BO", "") for value in requested}
            stmt = stmt.where(NewsArticle.ticker.in_(tickers))
        rows = self.session.execute(stmt).scalars().all()
        selected: list[SelectedArticle] = []
        excluded: dict[str, int] = {}
        seen: set[str] = set()
        instruments = InstrumentRepository(self.session)
        for row in rows:
            reason = self._exclusion_reason(row, seen)
            symbol = self._symbol_for_row(row)
            if symbol is None and reason is None:
                reason = ExclusionReason.MISSING_INSTRUMENT
            if reason is not None:
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
            assert symbol is not None
            instrument = instruments.get_or_create_from_symbol(symbol)
            row.instrument_id = row.instrument_id or instrument.id
            key = self._dedupe_key(row)
            seen.add(key)
            selected.append(
                SelectedArticle(
                    article_id=row.id,
                    instrument=symbol,
                    published_at=row.published_at,
                    title=row.title,
                    summary=row.summary,
                    body=None,
                    publisher=row.publisher or row.source,
                    provider=row.provider or row.source_provider,
                    leaf_provider=row.leaf_provider,
                    data_mode=row.data_mode,
                    dedupe_key=key,
                )
            )
        capped = self._sample(selected, config.max_articles, config.random_seed)
        capped_out = max(0, len(selected) - len(capped))
        if capped_out:
            excluded[ExclusionReason.SAMPLE_LIMIT] = excluded.get(ExclusionReason.SAMPLE_LIMIT, 0) + capped_out
        return SelectionSummary(
            selected=capped,
            selected_count=len(capped),
            excluded_count=sum(excluded.values()),
            exclusion_counts=excluded,
            metadata={
                "candidate_count": len(rows),
                "eligible_before_cap": len(selected),
                "limit": config.max_articles,
                "random_seed": config.random_seed,
                "dedupe_method": "dedupe_hash else canonical article id/url/title/time key",
            },
        )

    def _exclusion_reason(self, row: NewsArticle, seen: set[str]) -> str | None:
        if row.published_at is None:
            return ExclusionReason.MISSING_TIMESTAMP
        if not (row.title or "").strip():
            return ExclusionReason.MISSING_CONTENT
        key = self._dedupe_key(row)
        if key in seen:
            return ExclusionReason.DUPLICATE_SAMPLE
        return None

    @staticmethod
    def _dedupe_key(row: NewsArticle) -> str:
        if row.dedupe_hash:
            return f"hash:{row.dedupe_hash}"
        if row.url:
            return f"url:{row.url.strip().lower()}"
        return f"title:{row.ticker}:{row.exchange}:{row.title.strip().lower()}:{row.published_at}"

    @staticmethod
    def _sample(articles: list[SelectedArticle], limit: int, seed: int) -> list[SelectedArticle]:
        bounded = max(0, int(limit))
        if len(articles) <= bounded:
            return articles
        rng = random.Random(seed)
        sampled = rng.sample(articles, bounded)
        return sorted(sampled, key=lambda item: (item.published_at, item.article_id))

    @staticmethod
    def _symbol_for_row(row: NewsArticle) -> SymbolRecord | None:
        if row.exchange and row.ticker:
            symbol = registry.get(row.exchange, row.ticker)
            if symbol is not None:
                return symbol
        if row.raw_symbol:
            return registry.resolve_any(row.raw_symbol)
        return None


class GeminiFinBertExperimentRunner:
    def __init__(
        self,
        *,
        session: Session,
        gemini_analyzer: SentimentAnalyzer | None = None,
        finbert_analyzer: SentimentAnalyzer | None = None,
        event_service: EventStudyServiceV2 | None = None,
    ) -> None:
        self.session = session
        self.gemini_analyzer = gemini_analyzer or GeminiSentimentAnalyzer()
        self.finbert_analyzer = finbert_analyzer or FinBERTSentimentAnalyzer()
        self.event_service = event_service or EventStudyServiceV2(session=session)

    def dry_run(self, config: ModelComparisonConfig) -> ExperimentSummary:
        selection = ArticleSelectionService(self.session).select_articles(config)
        summary = build_experiment_summary(None, config, selection, [], {})
        summary.gemini_calls_failed = 0 if getattr(self.gemini_analyzer, "configured", False) else selection.selected_count
        summary.finbert_runs_failed = 0 if finbert_dependencies_available() else selection.selected_count
        summary.config["dry_run_readiness"] = {
            "gemini_configured": bool(getattr(self.gemini_analyzer, "configured", False)),
            "finbert_dependencies_available": finbert_dependencies_available(),
            "event_study_coverage": self._dry_run_event_coverage(selection.selected, config),
        }
        return summary

    def run(self, config: ModelComparisonConfig, *, persist: bool = True, export_dir: Path | None = None) -> ExperimentSummary:
        selection = ArticleSelectionService(self.session).select_articles(config)
        experiment_id = None
        if persist:
            experiment = ExperimentRepository(self.session).create(
                name=config.experiment_name,
                experiment_type=config.experiment_type,
                configuration=config.to_repository_config(),
                dataset_id=config.dataset_id,
                notes="Phase 9 controlled Gemini vs FinBERT comparison framework.",
            )
            experiment_id = experiment.id
        observations: list[PairedObservation] = []
        counters = {"gemini_new": 0, "gemini_reused": 0, "gemini_failed": 0, "finbert_new": 0, "finbert_reused": 0, "finbert_failed": 0}
        for article in selection.selected:
            analysis_input = build_analysis_input(article)
            gemini_view = self._run_or_reuse("gemini", self.gemini_analyzer, analysis_input, config, experiment_id, counters, persist)
            finbert_view = self._run_or_reuse("finbert", self.finbert_analyzer, analysis_input, config, experiment_id, counters, persist)
            event_results = self._event_results(article, config, experiment_id, persist)
            exclusions = self._observation_exclusions(gemini_view, finbert_view, event_results, config)
            gemini_direction = direction_from_score(gemini_view.result.sentiment_score, config.model_threshold) if gemini_view else None
            finbert_direction = direction_from_score(finbert_view.result.sentiment_score, config.model_threshold) if finbert_view else None
            observations.append(
                PairedObservation(
                    article_id=article.article_id,
                    instrument=article.instrument.ticker,
                    market=article.instrument.exchange,
                    published_at=article.published_at,
                    gemini=gemini_view,
                    finbert=finbert_view,
                    event_results=event_results,
                    gemini_direction=gemini_direction,
                    finbert_direction=finbert_direction,
                    agreement=(gemini_direction == finbert_direction) if gemini_direction and finbert_direction else None,
                    catalyst_tag=gemini_view.result.catalyst_tag if gemini_view else None,
                    exclusion_reasons=exclusions,
                )
            )
        if persist and experiment_id is not None:
            ExperimentRepository(self.session).complete(experiment_id, status="COMPLETED", notes=f"Paired observations: {len(observations)}")
        summary = build_experiment_summary(experiment_id, config, selection, observations, counters)
        if export_dir is not None:
            export_experiment(summary, export_dir)
        return summary

    def _run_or_reuse(
        self,
        key: str,
        analyzer: SentimentAnalyzer,
        analysis_input: SentimentAnalysisInput,
        config: ModelComparisonConfig,
        experiment_id: int | None,
        counters: dict[str, int],
        persist: bool,
    ) -> ModelRunView | None:
        fingerprint = comparison_fingerprint(analysis_input, analyzer, config)
        if config.reuse_existing and not config.force_rerun:
            existing = self._find_existing_run(analysis_input, analyzer, fingerprint)
            if existing is not None:
                counters[f"{key}_reused"] += 1
                return ModelRunView(run_id=existing.id, source="REUSED", result=result_from_run(existing))
        if not getattr(analyzer, "configured", False):
            counters[f"{key}_failed"] += 1
            return None
        record = SentimentIntelligenceService(session=self.session, analyzer=analyzer, fallback_to_heuristic=False).analyze(
            analysis_input,
            experiment_id=experiment_id,
            persist=persist,
        )
        record.result.metadata["comparison_fingerprint"] = fingerprint
        if record.persisted_run_id is not None:
            row = self.session.get(SentimentAnalysisRun, record.persisted_run_id)
            if row is not None:
                metadata = json_loads(row.metadata_json, {})
                metadata["comparison_fingerprint"] = fingerprint
                row.metadata_json = json.dumps(metadata, sort_keys=True)
        if record.result.status == ModelExecutionStatus.SUCCESS:
            counters[f"{key}_new"] += 1
            return ModelRunView(run_id=record.persisted_run_id, source="NEW_RUN", result=record.result)
        counters[f"{key}_failed"] += 1
        return ModelRunView(run_id=record.persisted_run_id, source="NEW_RUN", result=record.result)

    def _find_existing_run(self, analysis_input: SentimentAnalysisInput, analyzer: SentimentAnalyzer, fingerprint: str) -> SentimentAnalysisRun | None:
        if not isinstance(analysis_input.article_id, int):
            return None
        rows = self.session.execute(
            select(SentimentAnalysisRun)
            .where(
                SentimentAnalysisRun.article_id == analysis_input.article_id,
                SentimentAnalysisRun.model_family == analyzer.model_family,
                SentimentAnalysisRun.model_name == analyzer.model_name,
            )
            .order_by(SentimentAnalysisRun.created_at.desc(), SentimentAnalysisRun.id.desc())
        ).scalars().all()
        for row in rows:
            metadata = json_loads(row.metadata_json, {})
            if metadata.get("comparison_fingerprint") == fingerprint or metadata.get("run_fingerprint") == fingerprint:
                return row
        return None

    def _event_results(self, article: SelectedArticle, config: ModelComparisonConfig, experiment_id: int | None, persist: bool) -> dict[str, EventStudyResultV2]:
        price_df = PriceRepository(self.session).list_price_df(article.instrument.ticker)
        if price_df.empty:
            return {}
        study_input = self.event_service.build_input(
            instrument=article.instrument,
            event_timestamp=article.published_at,
            price_bars=price_df,
            horizons=[EventStudyHorizon.parse(value) for value in config.horizons],
            article_id=article.article_id,
            experiment_id=experiment_id,
            provider=article.provider,
            source=article.publisher,
        )
        return {record.result.horizon.label: record.result for record in self.event_service.evaluate(study_input, persist=persist)}

    def _dry_run_event_coverage(self, articles: list[SelectedArticle], config: ModelComparisonConfig) -> dict[str, Any]:
        coverage = {EventStudyHorizon.parse(value).label: {"valid": 0, "invalid": 0, "missing_market_data": 0} for value in config.horizons}
        for article in articles:
            price_df = PriceRepository(self.session).list_price_df(article.instrument.ticker)
            if price_df.empty:
                for item in coverage.values():
                    item["missing_market_data"] += 1
                continue
            study_input = self.event_service.build_input(
                instrument=article.instrument,
                event_timestamp=article.published_at,
                price_bars=price_df,
                horizons=[EventStudyHorizon.parse(value) for value in config.horizons],
                article_id=article.article_id,
                provider=article.provider,
                source=article.publisher,
            )
            for record in self.event_service.evaluate(study_input, persist=False):
                bucket = coverage[record.result.horizon.label]
                if record.result.status == EventStudyStatus.VALID:
                    bucket["valid"] += 1
                else:
                    bucket["invalid"] += 1
        return coverage

    @staticmethod
    def _observation_exclusions(gemini: ModelRunView | None, finbert: ModelRunView | None, events: dict[str, EventStudyResultV2], config: ModelComparisonConfig) -> list[str]:
        reasons: list[str] = []
        if gemini is None or gemini.result.status != ModelExecutionStatus.SUCCESS:
            reasons.append(ExclusionReason.GEMINI_FAILED)
        if finbert is None or finbert.result.status != ModelExecutionStatus.SUCCESS:
            reasons.append(ExclusionReason.FINBERT_FAILED)
        if not events:
            reasons.append(ExclusionReason.NO_MARKET_DATA)
        for horizon in config.horizons:
            label = EventStudyHorizon.parse(horizon).label
            if label not in events:
                reasons.append(f"{ExclusionReason.UNSUPPORTED_HORIZON}:{label}")
            elif events[label].status != EventStudyStatus.VALID:
                reasons.append(f"{ExclusionReason.INVALID_EVENT_STUDY}:{label}:{events[label].status.value}")
        return reasons


def build_analysis_input(article: SelectedArticle) -> SentimentAnalysisInput:
    return SentimentAnalysisInput(
        article_id=article.article_id,
        instrument_id=None,
        symbol=article.instrument.ticker,
        company_name=article.instrument.display_name,
        exchange=article.instrument.exchange,
        title=article.title,
        summary=article.summary,
        body=article.body,
        publisher=article.publisher,
        published_at=article.published_at,
        source_provider=article.provider,
        leaf_provider=article.leaf_provider,
        data_mode=article.data_mode,
        context={"dedupe_key": article.dedupe_key},
    )


def comparison_fingerprint(analysis_input: SentimentAnalysisInput, analyzer: SentimentAnalyzer, config: ModelComparisonConfig) -> str:
    raw = {
        "article_id": analysis_input.article_id,
        "text_hash": sha256(analysis_input.text.encode("utf-8")).hexdigest(),
        "model_family": analyzer.model_family,
        "model_name": analyzer.model_name,
        "model_version": analyzer.model_version,
        "analysis_method": analyzer.analysis_method,
        "normalization_version": config.sentiment_normalization_version,
        "gemini_prompt_version": config.gemini_prompt_version,
    }
    return sha256(json.dumps(raw, sort_keys=True).encode("utf-8")).hexdigest()


def result_from_run(row: SentimentAnalysisRun) -> SentimentAnalysisResult:
    from finsent.app.services.sentiment_v2 import ModelExecutionStatus, utc_now

    metadata = json_loads(row.metadata_json, {})
    return SentimentAnalysisResult(
        requested_analyzer=str(metadata.get("requested_analyzer") or row.model_family),
        actual_analyzer=str(metadata.get("actual_analyzer") or row.model_family),
        provider=row.provider or row.model_family,
        model_family=row.model_family,
        model_name=row.model_name,
        model_version=row.model_version,
        analysis_method=row.analysis_method,
        sentiment_label=row.sentiment_label or "neutral",
        sentiment_score=float(row.sentiment_score or 0.0),
        confidence=row.confidence,
        relevance=row.relevance,
        impact_strength=row.impact_strength,
        time_horizon=row.time_horizon,
        catalyst_tag=row.catalyst_tag,
        short_reason=row.short_reason,
        parse_status=row.parse_status or "stored",
        fallback_used=bool(row.fallback_used),
        fallback_reason=metadata.get("fallback_reason"),
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        latency_ms=metadata.get("latency_ms"),
        created_at=row.created_at or utc_now(),
        status=ModelExecutionStatus.SUCCESS if (row.parse_status or "ok") not in {"failed", "unconfigured"} else ModelExecutionStatus.FAILED,
        metadata=metadata,
    )


def direction_from_score(score: float | None, threshold: float = DEFAULT_MODEL_THRESHOLD) -> str:
    value = float(score or 0.0)
    if value > threshold:
        return "BULLISH"
    if value < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def realized_direction(raw_return: float | None, threshold: float = DEFAULT_RETURN_THRESHOLD) -> str | None:
    if raw_return is None:
        return None
    if raw_return > threshold:
        return "BULLISH"
    if raw_return < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def build_experiment_summary(
    experiment_id: int | None,
    config: ModelComparisonConfig,
    selection: SelectionSummary,
    observations: list[PairedObservation],
    counters: dict[str, int],
) -> ExperimentSummary:
    return ExperimentSummary(
        experiment_id=experiment_id,
        config=config.to_repository_config(),
        selected_count=selection.selected_count,
        excluded_count=selection.excluded_count,
        exclusion_counts=selection.exclusion_counts,
        gemini_calls_new=counters.get("gemini_new", 0),
        gemini_calls_reused=counters.get("gemini_reused", 0),
        gemini_calls_failed=counters.get("gemini_failed", 0),
        finbert_runs_new=counters.get("finbert_new", 0),
        finbert_runs_reused=counters.get("finbert_reused", 0),
        finbert_runs_failed=counters.get("finbert_failed", 0),
        agreement=agreement_summary(observations),
        horizons=horizon_summaries(observations, config),
        confidence_buckets=confidence_bucket_summaries(observations, config),
        disagreements=disagreement_summaries(observations, config),
        catalysts=catalyst_summaries(observations, config),
        latency=[latency_summary("gemini", [obs.gemini for obs in observations]), latency_summary("finbert", [obs.finbert for obs in observations])],
        market_counts=count_by(observations, lambda obs: obs.market),
        symbol_counts=count_by(observations, lambda obs: f"{obs.market}:{obs.instrument}"),
        paired_rows=observations,
    )


def agreement_summary(observations: list[PairedObservation]) -> AgreementSummary:
    labels = ["BULLISH", "NEUTRAL", "BEARISH"]
    matrix = {left: {right: 0 for right in labels} for left in labels}
    eligible = 0
    agreements = 0
    for obs in observations:
        if obs.gemini_direction is None or obs.finbert_direction is None:
            continue
        eligible += 1
        matrix[obs.gemini_direction][obs.finbert_direction] += 1
        if obs.gemini_direction == obs.finbert_direction:
            agreements += 1
    disagreements = eligible - agreements
    return AgreementSummary(eligible, agreements, disagreements, safe_div(agreements, eligible), matrix)


def horizon_summaries(observations: list[PairedObservation], config: ModelComparisonConfig) -> list[HorizonEvaluationSummary]:
    summaries: list[HorizonEvaluationSummary] = []
    for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
        for model in ["gemini", "finbert"]:
            pairs: list[tuple[str, str, float]] = []
            for obs in observations:
                model_view = obs.gemini if model == "gemini" else obs.finbert
                prediction = obs.gemini_direction if model == "gemini" else obs.finbert_direction
                event = obs.event_results.get(horizon)
                if model_view is None or prediction is None or event is None or event.status != EventStudyStatus.VALID:
                    continue
                outcome = realized_direction(event.raw_return, config.return_threshold)
                if outcome is not None:
                    pairs.append((prediction, outcome, float(event.raw_return or 0.0)))
            metrics = classification_metrics([(prediction, outcome) for prediction, outcome, _ in pairs])
            summaries.append(
                HorizonEvaluationSummary(
                    horizon=horizon,
                    model=model,
                    eligible_observations=len(pairs),
                    valid_event_studies=len(pairs),
                    metrics=metrics,
                    average_return_predicted_bullish=mean([ret for pred, _, ret in pairs if pred == "BULLISH"]),
                    average_return_predicted_bearish=mean([ret for pred, _, ret in pairs if pred == "BEARISH"]),
                )
            )
    return summaries


def classification_metrics(pairs: list[tuple[str, str]]) -> ClassificationMetrics:
    labels = ["BULLISH", "NEUTRAL", "BEARISH"]
    total = len(pairs)
    correct = sum(1 for prediction, outcome in pairs if prediction == outcome)
    neutral_prediction = sum(1 for prediction, _ in pairs if prediction == "NEUTRAL")
    neutral_outcome = sum(1 for _, outcome in pairs if outcome == "NEUTRAL")
    directional = [(p, o) for p, o in pairs if p != "NEUTRAL" and o != "NEUTRAL"]
    directional_correct = sum(1 for prediction, outcome in directional if prediction == outcome)
    precision: dict[str, float | None] = {}
    recall: dict[str, float | None] = {}
    f1: dict[str, float | None] = {}
    recalls_for_balance: list[float] = []
    for label in labels:
        tp = sum(1 for p, o in pairs if p == label and o == label)
        fp = sum(1 for p, o in pairs if p == label and o != label)
        fn = sum(1 for p, o in pairs if p != label and o == label)
        precision[label] = safe_div(tp, tp + fp)
        recall[label] = safe_div(tp, tp + fn)
        f1[label] = safe_div(2 * precision[label] * recall[label], precision[label] + recall[label]) if precision[label] is not None and recall[label] is not None and (precision[label] + recall[label]) > 0 else None
        if recall[label] is not None:
            recalls_for_balance.append(recall[label])
    strict_accuracy = safe_div(correct, total)
    return ClassificationMetrics(
        total=total,
        correct=correct,
        incorrect=total - correct,
        neutral_prediction_count=neutral_prediction,
        neutral_outcome_count=neutral_outcome,
        strict_accuracy=strict_accuracy,
        directional_eligible=len(directional),
        directional_correct=directional_correct,
        directional_accuracy=safe_div(directional_correct, len(directional)),
        precision=precision,
        recall=recall,
        f1=f1,
        balanced_accuracy=mean(recalls_for_balance),
        wilson_interval=wilson_interval(correct, total) if total else None,
    )


def confidence_bucket_summaries(observations: list[PairedObservation], config: ModelComparisonConfig) -> list[ConfidenceBucketSummary]:
    summaries: list[ConfidenceBucketSummary] = []
    first_horizon = EventStudyHorizon.parse(config.horizons[0]).label if config.horizons else "1H"
    for model in ["gemini", "finbert"]:
        for lower, upper in zip(DEFAULT_CONFIDENCE_BUCKETS[:-1], DEFAULT_CONFIDENCE_BUCKETS[1:], strict=True):
            pairs: list[tuple[str, str, float]] = []
            for obs in observations:
                view = obs.gemini if model == "gemini" else obs.finbert
                prediction = obs.gemini_direction if model == "gemini" else obs.finbert_direction
                event = obs.event_results.get(first_horizon)
                if view is None or prediction is None or view.result.confidence is None or event is None or event.status != EventStudyStatus.VALID:
                    continue
                if lower <= float(view.result.confidence) < upper:
                    outcome = realized_direction(event.raw_return, config.return_threshold)
                    if outcome is not None:
                        pairs.append((prediction, outcome, abs(float(event.raw_return or 0.0))))
            metrics = classification_metrics([(prediction, outcome) for prediction, outcome, _ in pairs])
            label = f"{lower:.1f}-{min(upper, 1.0):.1f}"
            summaries.append(ConfidenceBucketSummary(model, label, len(pairs), metrics.directional_accuracy, mean([item[2] for item in pairs])))
    return summaries


def disagreement_summaries(observations: list[PairedObservation], config: ModelComparisonConfig) -> list[DisagreementSummary]:
    summaries: list[DisagreementSummary] = []
    for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
        gemini_correct = finbert_correct = both_wrong = realized_neutral_count = count = 0
        for obs in observations:
            if obs.gemini_direction is None or obs.finbert_direction is None or obs.gemini_direction == obs.finbert_direction:
                continue
            event = obs.event_results.get(horizon)
            if event is None or event.status != EventStudyStatus.VALID:
                continue
            outcome = realized_direction(event.raw_return, config.return_threshold)
            if outcome is None:
                continue
            count += 1
            if outcome == "NEUTRAL":
                realized_neutral_count += 1
            g_ok = obs.gemini_direction == outcome
            f_ok = obs.finbert_direction == outcome
            gemini_correct += 1 if g_ok else 0
            finbert_correct += 1 if f_ok else 0
            both_wrong += 1 if not g_ok and not f_ok and outcome != "NEUTRAL" else 0
        summaries.append(DisagreementSummary(horizon, count, gemini_correct, finbert_correct, both_wrong, realized_neutral_count))
    return summaries


def catalyst_summaries(observations: list[PairedObservation], config: ModelComparisonConfig) -> list[CatalystSummary]:
    first_horizon = EventStudyHorizon.parse(config.horizons[0]).label if config.horizons else "1H"
    groups: dict[str, list[PairedObservation]] = {}
    for obs in observations:
        catalyst = obs.catalyst_tag or CatalystTag.UNKNOWN.value
        groups.setdefault(catalyst, []).append(obs)
    summaries: list[CatalystSummary] = []
    for catalyst, rows in sorted(groups.items()):
        distribution: dict[str, int] = {}
        pairs_by_prediction: dict[str, list[tuple[str, str, float]]] = {}
        for obs in rows:
            pred = obs.gemini_direction or "UNKNOWN"
            distribution[pred] = distribution.get(pred, 0) + 1
            event = obs.event_results.get(first_horizon)
            if event is not None and event.status == EventStudyStatus.VALID and obs.gemini_direction:
                outcome = realized_direction(event.raw_return, config.return_threshold)
                if outcome:
                    pairs_by_prediction.setdefault(obs.gemini_direction, []).append((obs.gemini_direction, outcome, float(event.raw_return or 0.0)))
        summaries.append(
            CatalystSummary(
                catalyst=catalyst,
                count=len(rows),
                sentiment_distribution=distribution,
                directional_accuracy={label: classification_metrics([(p, o) for p, o, _ in pairs]).directional_accuracy for label, pairs in pairs_by_prediction.items()},
                average_realized_return_by_prediction={label: mean([ret for _, _, ret in pairs]) for label, pairs in pairs_by_prediction.items()},
            )
        )
    return summaries


def latency_summary(model: str, views: list[ModelRunView | None]) -> LatencySummary:
    values = sorted(float(view.result.latency_ms) for view in views if view is not None and view.result.latency_ms is not None)
    if not values:
        return LatencySummary(model, 0, None, None, None)
    p95_index = min(len(values) - 1, math.ceil(len(values) * 0.95) - 1)
    return LatencySummary(model, len(values), mean(values), float(median(values)), values[p95_index])


def paired_rows_dataframe(observations: list[PairedObservation], config: ModelComparisonConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    horizons = [EventStudyHorizon.parse(value).label for value in config.horizons]
    for obs in observations:
        row = {
            "article_id": obs.article_id,
            "instrument": obs.instrument,
            "market": obs.market,
            "published_at": obs.published_at,
            "gemini_score": obs.gemini.result.sentiment_score if obs.gemini else None,
            "gemini_label": obs.gemini_direction,
            "gemini_confidence": obs.gemini.result.confidence if obs.gemini else None,
            "gemini_model": obs.gemini.result.model_name if obs.gemini else None,
            "gemini_version": obs.gemini.result.model_version if obs.gemini else None,
            "gemini_latency_ms": obs.gemini.result.latency_ms if obs.gemini else None,
            "finbert_score": obs.finbert.result.sentiment_score if obs.finbert else None,
            "finbert_label": obs.finbert_direction,
            "finbert_confidence": obs.finbert.result.confidence if obs.finbert else None,
            "finbert_model": obs.finbert.result.model_name if obs.finbert else None,
            "finbert_version": obs.finbert.result.model_version if obs.finbert else None,
            "finbert_latency_ms": obs.finbert.result.latency_ms if obs.finbert else None,
            "model_agreement": obs.agreement,
            "catalyst": obs.catalyst_tag,
            "exclusion_status": ";".join(obs.exclusion_reasons),
        }
        for horizon in horizons:
            event = obs.event_results.get(horizon)
            row[f"{horizon}_return"] = event.raw_return if event else None
            row[f"{horizon}_status"] = event.status.value if event else "MISSING"
        rows.append(row)
    return pd.DataFrame(rows)


def export_experiment(summary: ExperimentSummary, output_dir: Path) -> tuple[Path, Path]:
    target = output_dir / str(summary.experiment_id or "dry_run")
    target.mkdir(parents=True, exist_ok=True)
    csv_path = target / "paired_results.csv"
    json_path = target / "summary.json"
    paired_rows_dataframe(summary.paired_rows, ModelComparisonConfig(**_config_kwargs(summary.config))).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(to_jsonable(summary_to_dict(summary, include_rows=False)), indent=2, sort_keys=True), encoding="utf-8")
    return csv_path, json_path


def summary_to_dict(summary: ExperimentSummary, *, include_rows: bool = False) -> dict[str, Any]:
    payload = asdict(summary)
    if not include_rows:
        payload.pop("paired_rows", None)
    return payload


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def _config_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    allowed = {field_name for field_name in ModelComparisonConfig.__dataclass_fields__}
    cleaned = {key: value for key, value in config.items() if key in allowed}
    for key in ("start_date", "end_date"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = datetime.fromisoformat(cleaned[key])
    return cleaned


def safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    if total <= 0:
        return None
    phat = successes / total
    denominator = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denominator
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - spread), min(1.0, center + spread)


def count_by(observations: list[PairedObservation], key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obs in observations:
        key = str(key_fn(obs))
        counts[key] = counts.get(key, 0) + 1
    return counts


def finbert_dependencies_available() -> bool:
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("transformers") is not None
