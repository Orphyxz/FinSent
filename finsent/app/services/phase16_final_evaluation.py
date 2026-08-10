from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import csv
import importlib.metadata
import json
import math
import platform
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.analysis.event_study_v2 import ENGINE_VERSION_EVENT_STUDY_V2, EventStudyHorizon, EventStudyStatus
from finsent.app.config.settings import settings
from finsent.app.database.base import SCHEMA_VERSION
from finsent.app.database.entities import ExperimentRun, NewsArticle, SentimentAnalysisRun
from finsent.app.database.repository import PriceRepository
from finsent.app.database.research_repository import ExperimentRepository, InstrumentRepository, ResearchResultRepository, json_loads
from finsent.app.services.event_study_service_v2 import EventStudyServiceV2
from finsent.app.services.historical_signal_evaluation import SIGNAL_V1_ENGINE_NAME, SIGNAL_V1_ENGINE_VERSION, signal_direction
from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.model_comparison import classification_metrics, realized_direction, wilson_interval
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.phase13_research import macro_f1, to_jsonable
from finsent.app.services.phase14_research import CALIBRATOR_VERSION, IdentityCalibrator, calibration_metrics
from finsent.app.services.phase15_research import FINAL_HOLDOUT_V3_DATASET_ID, FINAL_HOLDOUT_V3_STATUS
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig, ResearchCohortSample
from finsent.app.services.sentiment_intelligence import SentimentIntelligenceService
from finsent.app.services.sentiment_v2 import (
    FinBERTSentimentAnalyzer,
    ModelExecutionStatus,
    SentimentAnalysisInput,
    SentimentAnalysisResult,
)
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_engine_v2 import (
    ENGINE_NAME_V2,
    ENGINE_VERSION_V2,
    ENGINE_VERSION_V2_1_RESEARCH,
    SignalEngineV2,
    SignalEngineV2Config,
    SignalInputV2,
    SignalNewsItemV2,
    result_metadata,
)


PHASE16_OUTPUT_DIR = Path("output") / "research" / "phase16"
FINAL_EXPERIMENT_NAME = "FINAL_HOLDOUT_EVALUATION_V1"
FINAL_EXPERIMENT_TYPE = "final_holdout_evaluation"
FINAL_PROTOCOL_VERSION = "final_evaluation_protocol_v1"
FINAL_HOLDOUT_V3_EVALUATED_STATUS = "FINAL_HOLDOUT_V3_EVALUATED_LOCKED"
EXPECTED_HOLDOUT_FINGERPRINT = "8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e"
REALIZED_RETURN_THRESHOLD = 0.001
LABELS = ("BULLISH", "NEUTRAL", "BEARISH")


@dataclass(frozen=True, slots=True)
class FinalEvaluationConfig:
    protocol_version: str
    holdout_dataset_id: str
    holdout_fingerprint: str
    article_cohort_identifier: str
    eligible_article_ids: list[int]
    sentiment_analyzer: str = "finbert"
    sentiment_model: str = settings.model_name
    sentiment_version: str = settings.model_name
    sentiment_text_policy: str = "title + summary; body omitted for normalized FNSPID rows"
    signal_v1_engine: str = SIGNAL_V1_ENGINE_NAME
    signal_v1_version: str = SIGNAL_V1_ENGINE_VERSION
    signal_v2_engine: str = ENGINE_NAME_V2
    signal_v2_version: str = ENGINE_VERSION_V2
    signal_v2_1_version: str | None = ENGINE_VERSION_V2_1_RESEARCH
    event_study_version: str = ENGINE_VERSION_EVENT_STUDY_V2
    horizon: str = "1D"
    price_source: str = "yahoo_chart_daily"
    price_basis: str = "unadjusted quote.close"
    realized_neutral_threshold: float = REALIZED_RETURN_THRESHOLD
    metrics: list[str] = field(default_factory=lambda: [
        "strict_accuracy",
        "directional_accuracy",
        "balanced_accuracy",
        "macro_f1",
        "precision",
        "recall",
        "confusion_matrix",
        "coverage",
        "wilson_interval",
        "paired_correctness",
    ])
    baselines: list[str] = field(default_factory=lambda: ["majority_class", "always_neutral", "news_direction"])
    confidence_interval_method: str = "Wilson score interval for strict and directional simple proportions only"
    paired_test_policy: str = "Two-sided exact McNemar/binomial only if discordant N >= 25; otherwise insufficient."
    confidence_calibrator: str = CALIBRATOR_VERSION
    confidence_calibrator_method: str = "identity"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EnginePrediction:
    engine: str
    engine_version: str
    score: float | None
    label: str
    canonical_direction: str
    confidence: float | None
    calibrated_reliability: float | None
    mode: str | None
    signal_run_id: int | None
    component_summary: dict[str, Any]


@dataclass(slots=True)
class FinalObservation:
    article_id: int
    instrument: str
    published_at: datetime
    finbert_run_id: int | None
    finbert_score: float
    finbert_label: str
    finbert_direction: str
    finbert_confidence: float | None
    event_status: str
    raw_return_1d: float | None
    realized_direction: str | None
    predictions: dict[str, EnginePrediction]
    exclusion_reason: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def stable_hash(value: Any) -> str:
    return sha256(json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path


def hash_files(paths: list[Path]) -> dict[str, str | None]:
    output: dict[str, str | None] = {}
    for path in paths:
        output[path.as_posix()] = file_sha256(path) if path.exists() else None
    return output


def build_final_cohort_config() -> ResearchCohortConfig:
    return ResearchCohortConfig(
        symbols=["AAPL", "AMZN", "NVDA", "TSLA"],
        markets=["US"],
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 3, 31, 23, 59, 59),
        horizons=["1d"],
        limit=10_000,
        seed=42,
        dataset_id=FINAL_HOLDOUT_V3_DATASET_ID,
    )


def load_lock(lock_path: Path = PHASE16_OUTPUT_DIR.parent / "phase15" / "final_holdout_v3_lock.json") -> dict[str, Any]:
    return json.loads(lock_path.read_text(encoding="utf-8"))


def verify_holdout(lock: dict[str, Any], cohort_samples: list[ResearchCohortSample]) -> dict[str, Any]:
    eligible = [sample for sample in cohort_samples if sample.coverage.get("1D") and sample.coverage["1D"].valid]
    eligible_counts: dict[str, int] = {}
    for sample in eligible:
        eligible_counts[sample.instrument.ticker] = eligible_counts.get(sample.instrument.ticker, 0) + 1
    expected_ids = [int(value) for value in lock.get("article_ids", [])]
    actual_ids = [int(sample.article_id) for sample in cohort_samples]
    checks = {
        "status": lock.get("status"),
        "fingerprint": lock.get("fingerprint"),
        "candidate_n": len(cohort_samples),
        "technically_eligible_n": len(eligible),
        "eligible_per_symbol": dict(sorted(eligible_counts.items())),
        "article_ids_match": sorted(expected_ids) == sorted(actual_ids),
        "expected_article_ids_sha256": stable_hash(sorted(expected_ids)),
        "actual_article_ids_sha256": stable_hash(sorted(actual_ids)),
    }
    if checks["status"] != FINAL_HOLDOUT_V3_STATUS:
        raise RuntimeError(f"Final holdout status is {checks['status']}, expected {FINAL_HOLDOUT_V3_STATUS}.")
    if checks["fingerprint"] != EXPECTED_HOLDOUT_FINGERPRINT:
        raise RuntimeError("Final holdout fingerprint differs from the locked Phase 15 value.")
    if checks["candidate_n"] != 157 or checks["technically_eligible_n"] != 111:
        raise RuntimeError(f"Final holdout N changed: {checks}.")
    if checks["eligible_per_symbol"] != {"AMZN": 39, "NVDA": 37, "TSLA": 35}:
        raise RuntimeError(f"Final eligible symbol counts changed: {checks['eligible_per_symbol']}.")
    if not checks["article_ids_match"]:
        raise RuntimeError("Final article IDs differ from the locked manifest.")
    return checks


def existing_final_experiments(session: Session) -> list[ExperimentRun]:
    return session.execute(
        select(ExperimentRun).where(
            (ExperimentRun.name == FINAL_EXPERIMENT_NAME)
            | (ExperimentRun.experiment_type == FINAL_EXPERIMENT_TYPE)
            | (ExperimentRun.dataset_id == FINAL_HOLDOUT_V3_DATASET_ID) & (ExperimentRun.experiment_type == FINAL_EXPERIMENT_TYPE)
        )
    ).scalars().all()


def verify_no_prior_final_runs(session: Session, article_ids: list[int]) -> dict[str, Any]:
    experiments = existing_final_experiments(session)
    finbert_rows = session.execute(
        select(SentimentAnalysisRun).where(
            SentimentAnalysisRun.article_id.in_(article_ids),
            SentimentAnalysisRun.model_family == "finbert",
        )
    ).scalars().all()
    if experiments:
        raise RuntimeError("Existing final holdout evaluation experiment found; refusing to overwrite one-shot final evaluation.")
    if finbert_rows:
        raise RuntimeError("Existing FinBERT runs on locked final articles found before Phase 16.")
    return {"final_experiments": 0, "finbert_final_article_runs": 0}


def environment_manifest(holdout_fingerprint: str) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in ["torch", "transformers", "pandas", "sqlalchemy", "numpy", "scikit-learn", "pytest", "dash"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    device = "cpu"
    try:
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        device = "unavailable"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "finbert_model_identifier": settings.model_name,
        "finbert_model_revision": settings.model_name,
        "device": device,
        "database_schema_version": SCHEMA_VERSION,
        "holdout_fingerprint": holdout_fingerprint,
        "timezone": str(datetime.now().astimezone().tzinfo),
        "created_at": utc_now().isoformat(),
    }


def write_pre_execution_manifest(config: FinalEvaluationConfig, config_hash: str, protocol_hash: str) -> dict[str, Any]:
    frozen_files = [
        Path("output/research/phase15/FINAL_HOLDOUT_V3_MANIFEST.json"),
        Path("output/research/phase15/final_holdout_v3_lock.json"),
        Path("docs/FINAL_EVALUATION_PROTOCOL.md"),
        Path("finsent/app/services/signal_engine.py"),
        Path("finsent/app/services/signal_engine_v2.py"),
        Path("finsent/app/services/sentiment_v2.py"),
        Path("finsent/app/services/historical_signal_evaluation.py"),
        Path("finsent/app/analysis/event_study_v2.py"),
        Path("finsent/app/services/model_comparison.py"),
        Path("docs/CONFIDENCE_CALIBRATION.md"),
        Path("docs/SIGNAL_V2_1_RESEARCH_CANDIDATE.md"),
        Path("data/research_sources/fnspid/MANIFEST.json"),
        Path("data/research_sources/yahoo_chart_daily/MANIFEST.json"),
    ]
    manifest = {
        "phase": 16,
        "purpose": "pre-execution reproducibility manifest before one-shot final holdout evaluation",
        "execution_config_hash": config_hash,
        "protocol_hash": protocol_hash,
        "environment": environment_manifest(config.holdout_fingerprint),
        "frozen_file_hashes": hash_files(frozen_files),
        "config": config.to_dict(),
        "created_at": utc_now().isoformat(),
    }
    write_json(PHASE16_OUTPUT_DIR / "PRE_EXECUTION_MANIFEST.json", manifest)
    return manifest


def build_analysis_input(article: NewsArticle) -> SentimentAnalysisInput:
    return SentimentAnalysisInput(
        article_id=article.id,
        instrument_id=article.instrument_id,
        symbol=article.ticker,
        company_name=article.ticker,
        exchange=article.exchange or "US",
        title=article.title,
        summary=article.summary,
        body=None,
        publisher=article.publisher or article.source,
        published_at=article.published_at,
        source_provider=article.provider,
        leaf_provider=article.leaf_provider,
        data_mode=article.data_mode,
        context={"dedupe_hash": article.dedupe_hash, "final_holdout": FINAL_HOLDOUT_V3_DATASET_ID},
    )


def finbert_smoke(session: Session, analyzer: FinBERTSentimentAnalyzer, final_ids: set[int]) -> dict[str, Any]:
    article = session.execute(
        select(NewsArticle)
        .where(~NewsArticle.id.in_(final_ids), NewsArticle.title.is_not(None))
        .order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    smoke_input = (
        build_analysis_input(article)
        if article is not None
        else SentimentAnalysisInput(
            article_id=None,
            instrument_id=None,
            symbol="AAPL",
            company_name="Apple",
            exchange="US",
            title="Apple reports quarterly revenue growth",
            summary=None,
            body=None,
            publisher="test_fixture",
            published_at=datetime(2022, 1, 3),
            source_provider="test_fixture",
            leaf_provider="test_fixture",
            data_mode="SMOKE_TEST",
        )
    )
    result = analyzer.analyze(smoke_input)
    if result.status != ModelExecutionStatus.SUCCESS:
        raise RuntimeError(f"FinBERT non-holdout smoke failed: {result.failure_category} {result.short_reason}")
    return {
        "article_id": smoke_input.article_id,
        "final_holdout_article": smoke_input.article_id in final_ids if isinstance(smoke_input.article_id, int) else False,
        "status": result.status.value,
        "model": result.model_name,
        "normalization": {"score": result.sentiment_score, "label": result.sentiment_label},
        "persistence_verified_by": "phase16 unit tests and final persisted run path; smoke itself is not persisted",
    }


def run_finbert(
    session: Session,
    articles: list[NewsArticle],
    analyzer: FinBERTSentimentAnalyzer,
    experiment_id: int,
) -> tuple[dict[int, SentimentAnalysisRun], dict[str, Any]]:
    service = SentimentIntelligenceService(session=session, analyzer=analyzer, fallback_to_heuristic=False)
    rows: dict[int, SentimentAnalysisRun] = {}
    requested = len(articles)
    failed = 0
    for article in articles:
        record = service.analyze(build_analysis_input(article), experiment_id=experiment_id, persist=True)
        if record.result.status != ModelExecutionStatus.SUCCESS or record.result.fallback_used:
            failed += 1
        if record.persisted_run_id is not None:
            row = session.get(SentimentAnalysisRun, record.persisted_run_id)
            if row is not None:
                metadata = json_loads(row.metadata_json, {})
                metadata["phase16_final_holdout"] = True
                metadata["input_text_sha256"] = sha256(build_analysis_input(article).text.encode("utf-8")).hexdigest()
                row.metadata_json = json.dumps(to_jsonable(metadata), sort_keys=True)
                rows[article.id] = row
    if failed:
        raise RuntimeError(f"FinBERT failed for {failed} final holdout rows; stopping before final metrics.")
    return rows, {"requested": requested, "successful": len(rows), "failed": failed, "reused": 0}


def article_to_normalized(article: NewsArticle) -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id=str(article.id),
        ticker=article.ticker,
        exchange=article.exchange or "US",
        source=article.source,
        title=article.title,
        summary=article.summary,
        url=article.url,
        published_at=article.published_at,
        ingested_at=article.ingested_at or article.published_at,
        provider=article.provider or article.source,
        dedupe_hash=article.dedupe_hash or str(article.id),
        relevance_score=article.relevance_score,
    )


def run_to_analysis(row: SentimentAnalysisRun) -> ArticleAnalysis:
    label = (row.sentiment_label or "neutral").lower()
    return ArticleAnalysis(
        relevant=True,
        sentiment=label if label in {"bullish", "bearish", "neutral"} else "neutral",
        confidence=float(row.confidence or 0.0),
        impact_strength=float(row.impact_strength if row.impact_strength is not None else 0.5),
        time_horizon=row.time_horizon or "not_applicable",
        catalyst_tag=row.catalyst_tag or "not_applicable",
        short_reason=row.short_reason or "FinBERT final holdout sentiment.",
        provider=row.model_family,
        parse_status=row.parse_status or "ok",
    )


def past_article_pairs(
    session: Session,
    sample: ResearchCohortSample,
    articles_by_id: dict[int, NewsArticle],
    finbert_by_article: dict[int, SentimentAnalysisRun],
    locked_ids: set[int],
    *,
    lookback_hours: int = 72,
) -> list[tuple[NormalizedNewsArticle, ArticleAnalysis]]:
    start = sample.published_at - timedelta(hours=lookback_hours)
    rows = session.execute(
        select(NewsArticle)
        .where(
            NewsArticle.id.in_(locked_ids),
            NewsArticle.ticker == sample.instrument.ticker,
            NewsArticle.exchange == sample.instrument.exchange,
            NewsArticle.published_at <= sample.published_at,
            NewsArticle.published_at >= start,
        )
        .order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
    ).scalars().all()
    pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]] = []
    for article in rows:
        run = finbert_by_article.get(article.id)
        if run is None:
            continue
        pairs.append((article_to_normalized(articles_by_id[article.id]), run_to_analysis(run)))
    return pairs


def aggregate_finbert_pairs(pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]]) -> AggregateAnalysis:
    if not pairs:
        return AggregateAnalysis("neutral", 0.0, "no strong edge", "watch", "No past-known FinBERT articles available.", "finbert")
    confidence = sum(analysis.confidence for _, analysis in pairs) / len(pairs)
    score = sum((1 if analysis.sentiment == "bullish" else -1 if analysis.sentiment == "bearish" else 0) * analysis.confidence for _, analysis in pairs)
    sentiment = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return AggregateAnalysis(sentiment, confidence, f"{sentiment} FinBERT historical sentiment", "watch", "Stored final FinBERT aggregation.", "finbert")


def past_price_bars(session: Session, sample: ResearchCohortSample) -> pd.DataFrame:
    frame = PriceRepository(session).list_price_df(sample.instrument.ticker)
    if frame.empty:
        return frame
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    work = work[work["timestamp"] <= sample.published_at]
    return work.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}).set_index("timestamp")


def persist_v1(session: Session, sample: ResearchCohortSample, pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]], experiment_id: int) -> EnginePrediction:
    aggregate = aggregate_finbert_pairs(pairs)
    signal = CompositeSignalEngine().compute(None, pairs, aggregate)
    instrument = InstrumentRepository(session).get_or_create_from_symbol(sample.instrument)
    row = ResearchResultRepository(session).store_signal_run(
        instrument_id=instrument.id,
        experiment_id=experiment_id,
        generated_at=sample.published_at,
        engine_name=SIGNAL_V1_ENGINE_NAME,
        engine_version=SIGNAL_V1_ENGINE_VERSION,
        final_score=signal.composite_score,
        label=signal.composite_label,
        confidence=signal.signal_confidence,
        signal_mode=signal.mode,
        input_quality={"sentiment_source": "final_holdout_finbert", "no_lookahead": True},
        future_component={"lookback_articles": len(pairs), "final_evaluation": True},
        explanation="Phase 16 final V1 signal.",
    )
    return EnginePrediction("v1", SIGNAL_V1_ENGINE_VERSION, signal.composite_score, signal.composite_label, signal_direction(signal.composite_label), signal.signal_confidence, signal.signal_confidence, signal.mode, row.id, {"lookback_articles": len(pairs)})


def persist_v2(
    session: Session,
    sample: ResearchCohortSample,
    pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]],
    experiment_id: int,
    *,
    version: str,
    config: SignalEngineV2Config | None = None,
) -> EnginePrediction:
    price_df = past_price_bars(session, sample)
    signal_input = SignalInputV2(
        instrument=sample.instrument,
        evaluation_timestamp=sample.published_at,
        news_items=[SignalNewsItemV2(article, analysis) for article, analysis in pairs],
        quote=None,
        price_bars=price_df,
        provider_metadata={"sentiment_source": "final_holdout_finbert", "no_lookahead": True, "phase16_final_evaluation": True},
    )
    result = SignalEngineV2(config=config).evaluate(signal_input)
    metadata = result_metadata(result)
    metadata["engine_version_override"] = version
    metadata["identity_calibrated_reliability"] = result.confidence
    instrument = InstrumentRepository(session).get_or_create_from_symbol(sample.instrument)
    row = ResearchResultRepository(session).store_signal_run(
        instrument_id=instrument.id,
        experiment_id=experiment_id,
        generated_at=sample.published_at,
        engine_name=ENGINE_NAME_V2,
        engine_version=version,
        final_score=result.final_score,
        label=result.label,
        confidence=result.confidence,
        signal_mode=result.signal_mode,
        input_quality=result.data_quality,
        provider_metadata=signal_input.provider_metadata,
        news_component=component_value(metadata, "news"),
        market_component=component_value(metadata, "price_momentum"),
        future_component=metadata,
        explanation=result.explanation,
    )
    return EnginePrediction("v2_1" if version == ENGINE_VERSION_V2_1_RESEARCH else "v2", version, result.final_score, result.label, signal_direction(result.label), result.confidence, IdentityCalibrator().transform(result.confidence), result.signal_mode, row.id, metadata)


def evaluate_event(session: Session, sample: ResearchCohortSample, experiment_id: int, signal_run_id: int | None) -> dict[str, Any]:
    price_df = PriceRepository(session).list_price_df(sample.instrument.ticker)
    event_service = EventStudyServiceV2(session=session)
    study_input = event_service.build_input(
        instrument=sample.instrument,
        event_timestamp=sample.published_at,
        price_bars=price_df,
        horizons=[EventStudyHorizon.parse("1d")],
        article_id=sample.article_id,
        signal_run_id=signal_run_id,
        experiment_id=experiment_id,
        provider="yahoo_chart_daily",
        source="phase16_final_evaluation",
    )
    record = event_service.evaluate(study_input, persist=True)[0]
    result = record.result
    return {
        "status": result.status.value,
        "raw_return": result.raw_return,
        "realized_direction": realized_direction(result.raw_return, REALIZED_RETURN_THRESHOLD) if result.status == EventStudyStatus.VALID else None,
    }


def run_final_predictions(
    session: Session,
    eligible_samples: list[ResearchCohortSample],
    articles_by_id: dict[int, NewsArticle],
    finbert_by_article: dict[int, SentimentAnalysisRun],
    experiment_id: int,
    *,
    include_v2_1: bool,
) -> list[FinalObservation]:
    locked_ids = set(articles_by_id)
    observations: list[FinalObservation] = []
    v2_1_config = SignalEngineV2Config(news_weight=0.55, momentum_weight=0.45, volume_confirmation_weight=0.0, directional_threshold=0.15)
    for sample in eligible_samples:
        pairs = past_article_pairs(session, sample, articles_by_id, finbert_by_article, locked_ids)
        finbert_run = finbert_by_article[sample.article_id]
        predictions: dict[str, EnginePrediction] = {}
        predictions["v1"] = persist_v1(session, sample, pairs, experiment_id)
        predictions["v2"] = persist_v2(session, sample, pairs, experiment_id, version=ENGINE_VERSION_V2)
        if include_v2_1:
            predictions["v2_1"] = persist_v2(session, sample, pairs, experiment_id, version=ENGINE_VERSION_V2_1_RESEARCH, config=v2_1_config)
        event = evaluate_event(session, sample, experiment_id, predictions["v2"].signal_run_id)
        if event["status"] != EventStudyStatus.VALID.value:
            observations.append(
                FinalObservation(
                    article_id=sample.article_id,
                    instrument=f"{sample.instrument.exchange}:{sample.instrument.ticker}",
                    published_at=sample.published_at,
                    finbert_run_id=finbert_run.id,
                    finbert_score=float(finbert_run.sentiment_score or 0.0),
                    finbert_label=finbert_run.sentiment_label or "neutral",
                    finbert_direction=signal_direction(finbert_run.sentiment_label),
                    finbert_confidence=finbert_run.confidence,
                    event_status=event["status"],
                    raw_return_1d=event["raw_return"],
                    realized_direction=event["realized_direction"],
                    predictions=predictions,
                    exclusion_reason="EVENT_STUDY_EXECUTION_FAILURE",
                )
            )
            continue
        observations.append(
            FinalObservation(
                article_id=sample.article_id,
                instrument=f"{sample.instrument.exchange}:{sample.instrument.ticker}",
                published_at=sample.published_at,
                finbert_run_id=finbert_run.id,
                finbert_score=float(finbert_run.sentiment_score or 0.0),
                finbert_label=finbert_run.sentiment_label or "neutral",
                finbert_direction=signal_direction(finbert_run.sentiment_label),
                finbert_confidence=finbert_run.confidence,
                event_status=event["status"],
                raw_return_1d=event["raw_return"],
                realized_direction=event["realized_direction"],
                predictions=predictions,
            )
        )
    return observations


def final_pairs(observations: list[FinalObservation], engine: str) -> list[tuple[str, str]]:
    return [
        (obs.predictions[engine].canonical_direction, obs.realized_direction)
        for obs in observations
        if obs.exclusion_reason is None and obs.realized_direction is not None and engine in obs.predictions
    ]


def metrics_payload(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    metrics = classification_metrics(pairs)
    return {
        **asdict(metrics),
        "macro_f1": macro_f1(metrics.f1),
        "confusion_matrix": confusion_matrix(pairs),
        "strict_wilson_interval": metrics.wilson_interval,
        "directional_wilson_interval": wilson_interval(metrics.directional_correct, metrics.directional_eligible) if metrics.directional_eligible else None,
    }


def confusion_matrix(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    matrix = {actual: {predicted: 0 for predicted in LABELS} for actual in LABELS}
    for predicted, actual in pairs:
        if actual in matrix and predicted in matrix[actual]:
            matrix[actual][predicted] += 1
    return matrix


def class_distribution(values: list[str | None]) -> dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for value in values:
        key = str(value or "NEUTRAL").upper()
        counts[key] = counts.get(key, 0) + 1
    return counts


def majority_label(outcomes: list[str]) -> str:
    counts = class_distribution(outcomes)
    return sorted(LABELS, key=lambda label: (-counts[label], LABELS.index(label)))[0]


def paired_correctness(observations: list[FinalObservation]) -> dict[str, Any]:
    counts = {"both_correct": 0, "v1_correct_v2_wrong": 0, "v1_wrong_v2_correct": 0, "both_wrong": 0}
    for obs in observations:
        if obs.exclusion_reason is not None or obs.realized_direction is None:
            continue
        v1_ok = obs.predictions["v1"].canonical_direction == obs.realized_direction
        v2_ok = obs.predictions["v2"].canonical_direction == obs.realized_direction
        if v1_ok and v2_ok:
            counts["both_correct"] += 1
        elif v1_ok and not v2_ok:
            counts["v1_correct_v2_wrong"] += 1
        elif not v1_ok and v2_ok:
            counts["v1_wrong_v2_correct"] += 1
        else:
            counts["both_wrong"] += 1
    discordant = counts["v1_correct_v2_wrong"] + counts["v1_wrong_v2_correct"]
    result: dict[str, Any] = {**counts, "discordant_n": discordant}
    if discordant >= 25:
        b = counts["v1_correct_v2_wrong"]
        c = counts["v1_wrong_v2_correct"]
        result["mcnemar"] = {"method": "two_sided_exact_binomial", "p_value": exact_binomial_two_sided(min(b, c), discordant)}
    else:
        result["mcnemar"] = {
            "method": "not_run",
            "reason": "INSUFFICIENT_DISCORDANT_SAMPLE_FOR_MEANINGFUL_MCNEMAR_INFERENCE",
        }
    return result


def exact_binomial_two_sided(k: int, n: int) -> float:
    if n <= 0:
        return 1.0
    observed = math.comb(n, k) * (0.5 ** n)
    probability = 0.0
    for i in range(n + 1):
        p = math.comb(n, i) * (0.5 ** n)
        if p <= observed + 1e-15:
            probability += p
    return min(1.0, probability)


def per_symbol_results(observations: list[FinalObservation], engine: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for symbol in ["AMZN", "NVDA", "TSLA", "AAPL", "GOOGL"]:
        rows = [obs for obs in observations if obs.instrument.endswith(f":{symbol}") and obs.exclusion_reason is None and obs.realized_direction is not None and engine in obs.predictions]
        pairs = [(obs.predictions[engine].canonical_direction, str(obs.realized_direction)) for obs in rows]
        output[symbol] = {
            "n": len(rows),
            "metrics": metrics_payload(pairs) if pairs else None,
            "realized_distribution": class_distribution([obs.realized_direction for obs in rows]),
            "signal_distribution": class_distribution([obs.predictions[engine].canonical_direction for obs in rows]) if rows else class_distribution([]),
        }
    return output


def component_descriptives(observations: list[FinalObservation]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for obs in observations:
        pred = obs.predictions.get("v2")
        if pred is None:
            continue
        correct = obs.realized_direction is not None and pred.canonical_direction == obs.realized_direction
        for component in pred.component_summary.get("components", []):
            rows.append(
                {
                    "name": component.get("name"),
                    "available": bool(component.get("available")),
                    "normalized_value": component.get("normalized_value"),
                    "reliability": component.get("reliability"),
                    "correct": correct,
                }
            )
    output: dict[str, Any] = {}
    for name in sorted({str(row["name"]) for row in rows}):
        values = [float(row["normalized_value"] or 0.0) for row in rows if row["name"] == name and row["available"]]
        rel = [float(row["reliability"] or 0.0) for row in rows if row["name"] == name and row["available"]]
        correct_values = [float(row["normalized_value"] or 0.0) for row in rows if row["name"] == name and row["available"] and row["correct"]]
        incorrect_values = [float(row["normalized_value"] or 0.0) for row in rows if row["name"] == name and row["available"] and not row["correct"]]
        output[name] = {
            "value": describe(values),
            "reliability": describe(rel),
            "correct_value": describe(correct_values),
            "incorrect_value": describe(incorrect_values),
        }
    return output


def confidence_characterization(observations: list[FinalObservation]) -> dict[str, Any]:
    rows = [
        (float(obs.predictions["v2"].confidence or 0.0), 1 if obs.predictions["v2"].canonical_direction == obs.realized_direction else 0)
        for obs in observations
        if obs.exclusion_reason is None and obs.realized_direction is not None and "v2" in obs.predictions
    ]
    if not rows:
        return {"n": 0}
    predictions = [item[0] for item in rows]
    targets = [item[1] for item in rows]
    metrics = calibration_metrics(predictions, targets)
    return {
        "identity_calibrator": True,
        "raw_confidence": describe(predictions),
        "correct_mean_confidence": describe([pred for pred, ok in rows if ok]),
        "incorrect_mean_confidence": describe([pred for pred, ok in rows if not ok]),
        "calibration_metrics_secondary": {
            "n": metrics.n,
            "brier": metrics.brier,
            "ece": metrics.ece,
            "mce": metrics.mce,
            "reliability_bins": [asdict(item) for item in metrics.reliability_bins],
        },
    }


def describe(values: list[float]) -> dict[str, float | int | None]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {"n": len(clean), "mean": mean(clean), "median": median(clean), "min": min(clean), "max": max(clean)}


def build_summary(
    config: FinalEvaluationConfig,
    config_hash: str,
    protocol_hash: str,
    manifest_hash: str,
    holdout_checks: dict[str, Any],
    finbert_summary: dict[str, Any],
    observations: list[FinalObservation],
    include_v2_1: bool,
) -> dict[str, Any]:
    evaluated = [obs for obs in observations if obs.exclusion_reason is None and obs.realized_direction is not None]
    realized = [str(obs.realized_direction) for obs in evaluated]
    majority = majority_label(realized)
    baseline_pairs = {
        "majority_class": [(majority, outcome) for outcome in realized],
        "always_neutral": [("NEUTRAL", outcome) for outcome in realized],
        "news_direction": [(obs.finbert_direction, str(obs.realized_direction)) for obs in evaluated],
    }
    metrics = {
        "v1": metrics_payload(final_pairs(evaluated, "v1")),
        "v2": metrics_payload(final_pairs(evaluated, "v2")),
        "baselines": {name: metrics_payload(pairs) for name, pairs in baseline_pairs.items()},
    }
    if include_v2_1:
        metrics["v2_1"] = metrics_payload(final_pairs(evaluated, "v2_1"))
    return {
        "protocol": config.protocol_version,
        "protocol_hash": protocol_hash,
        "execution_config_hash": config_hash,
        "pre_execution_manifest_hash": manifest_hash,
        "holdout_fingerprint": config.holdout_fingerprint,
        "candidate_n": holdout_checks["candidate_n"],
        "technical_eligible_n": holdout_checks["technically_eligible_n"],
        "final_evaluated_n": len(evaluated),
        "final_evaluated_per_symbol": dict(sorted({symbol: sum(1 for obs in evaluated if obs.instrument.endswith(f':{symbol}')) for symbol in ["AMZN", "NVDA", "TSLA", "AAPL", "GOOGL"]}.items())),
        "finbert_execution": finbert_summary,
        "metrics": metrics,
        "paired_analysis": paired_correctness(evaluated),
        "class_distributions": {
            "realized": class_distribution(realized),
            "finbert": class_distribution([obs.finbert_direction for obs in evaluated]),
            "v1": class_distribution([obs.predictions["v1"].canonical_direction for obs in evaluated]),
            "v2": class_distribution([obs.predictions["v2"].canonical_direction for obs in evaluated]),
            "v2_1": class_distribution([obs.predictions["v2_1"].canonical_direction for obs in evaluated]) if include_v2_1 else None,
        },
        "symbol_results": {
            "v1": per_symbol_results(evaluated, "v1"),
            "v2": per_symbol_results(evaluated, "v2"),
            "v2_1": per_symbol_results(evaluated, "v2_1") if include_v2_1 else None,
        },
        "v2_component_analysis": component_descriptives(evaluated),
        "confidence_reliability": confidence_characterization(evaluated),
        "coverage": {
            "locked_candidate_n": holdout_checks["candidate_n"],
            "technical_eligible_n": holdout_checks["technically_eligible_n"],
            "finbert_successful_n": finbert_summary["successful"],
            "v1_evaluated_n": len(final_pairs(evaluated, "v1")),
            "v2_evaluated_n": len(final_pairs(evaluated, "v2")),
            "v2_1_evaluated_n": len(final_pairs(evaluated, "v2_1")) if include_v2_1 else None,
            "exclusions": class_distribution([obs.exclusion_reason for obs in observations if obs.exclusion_reason]),
        },
        "limitations": [
            "Three represented technical-eligible symbols in final metrics.",
            "AAPL had acquired rows but zero technical-eligible final observations.",
            "GOOGL had zero acquired rows from the supported source symbol set.",
            "FNSPID rows are title-heavy and daily horizon only.",
            "No Gemini and no trading simulation.",
        ],
    }


def export_rows(observations: list[FinalObservation], path: Path, include_v2_1: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "article_id",
        "instrument",
        "published_at",
        "finbert_score",
        "finbert_label",
        "finbert_confidence",
        "v1_score",
        "v1_label",
        "v1_canonical_direction",
        "v1_confidence",
        "v2_score",
        "v2_label",
        "v2_canonical_direction",
        "v2_confidence",
        "v2_mode",
        "v2_component_summary",
        "event_1d_raw_return",
        "realized_direction",
        "event_status",
        "v1_correct",
        "v2_correct",
        "exclusion_reason",
    ]
    if include_v2_1:
        fields.extend(["v2_1_score", "v2_1_label", "v2_1_canonical_direction", "v2_1_confidence", "v2_1_correct"])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for obs in observations:
            row = {
                "article_id": obs.article_id,
                "instrument": obs.instrument,
                "published_at": obs.published_at.isoformat(),
                "finbert_score": obs.finbert_score,
                "finbert_label": obs.finbert_label,
                "finbert_confidence": obs.finbert_confidence,
                "event_1d_raw_return": obs.raw_return_1d,
                "realized_direction": obs.realized_direction,
                "event_status": obs.event_status,
                "exclusion_reason": obs.exclusion_reason,
            }
            for key in ["v1", "v2"]:
                pred = obs.predictions[key]
                row[f"{key}_score"] = pred.score
                row[f"{key}_label"] = pred.label
                row[f"{key}_canonical_direction"] = pred.canonical_direction
                row[f"{key}_confidence"] = pred.confidence
                row[f"{key}_correct"] = pred.canonical_direction == obs.realized_direction if obs.realized_direction else None
            row["v2_mode"] = obs.predictions["v2"].mode
            row["v2_component_summary"] = json.dumps(to_jsonable(obs.predictions["v2"].component_summary), sort_keys=True)
            if include_v2_1:
                pred = obs.predictions["v2_1"]
                row["v2_1_score"] = pred.score
                row["v2_1_label"] = pred.label
                row["v2_1_canonical_direction"] = pred.canonical_direction
                row["v2_1_confidence"] = pred.confidence
                row["v2_1_correct"] = pred.canonical_direction == obs.realized_direction if obs.realized_direction else None
            writer.writerow(row)
    return path


def render_final_report(summary: dict[str, Any]) -> str:
    def pct(value: float | None, n: int | None = None) -> str:
        base = "n/a" if value is None else f"{value * 100:.1f}%"
        return f"{base} (N={n})" if n is not None else base

    v1 = summary["metrics"]["v1"]
    v2 = summary["metrics"]["v2"]
    lines = [
        "# FinSent Final Holdout Evaluation",
        "",
        "## Executive Research Summary",
        f"On the locked final cohort, the final evaluated N was {summary['final_evaluated_n']}. Signal V2.0 results are descriptive and cannot be used for tuning.",
        "",
        "## Frozen Protocol",
        f"Protocol hash: `{summary['protocol_hash']}`. Execution config hash: `{summary['execution_config_hash']}`.",
        "",
        "## Final Holdout",
        f"Fingerprint: `{summary['holdout_fingerprint']}`. Candidate N={summary['candidate_n']}; technical eligible N={summary['technical_eligible_n']}.",
        "",
        "## Data Provenance",
        "Articles: FNSPID. Prices: Yahoo chart daily, unadjusted quote.close.",
        "",
        "## Cohort and Coverage",
        json.dumps(to_jsonable(summary["coverage"]), indent=2, sort_keys=True),
        "",
        "## FinBERT Execution",
        json.dumps(to_jsonable(summary["finbert_execution"]), indent=2, sort_keys=True),
        "",
        "## Outcome Distribution",
        json.dumps(summary["class_distributions"], indent=2, sort_keys=True),
        "",
        "## Baselines",
        json.dumps(to_jsonable(summary["metrics"]["baselines"]), indent=2, sort_keys=True),
        "",
        "## Signal V1 Results",
        f"Strict accuracy: {pct(v1['strict_accuracy'], v1['total'])}. Directional accuracy: {pct(v1['directional_accuracy'], v1['directional_eligible'])}. Balanced accuracy: {pct(v1['balanced_accuracy'], v1['total'])}. Macro F1: {pct(v1['macro_f1'], v1['total'])}.",
        "",
        "## Signal V2.0 Results",
        f"Strict accuracy: {pct(v2['strict_accuracy'], v2['total'])}. Directional accuracy: {pct(v2['directional_accuracy'], v2['directional_eligible'])}. Balanced accuracy: {pct(v2['balanced_accuracy'], v2['total'])}. Macro F1: {pct(v2['macro_f1'], v2['total'])}.",
        "",
        "## V1 vs V2.0 Paired Comparison",
        json.dumps(to_jsonable(summary["paired_analysis"]), indent=2, sort_keys=True),
        "",
        "## V2.1 Research Candidate",
        "V2.1 is reported only as an unpromoted frozen research candidate.",
        json.dumps(to_jsonable(summary["metrics"].get("v2_1")), indent=2, sort_keys=True),
        "",
        "## Per-Symbol Results",
        json.dumps(to_jsonable(summary["symbol_results"]), indent=2, sort_keys=True),
        "",
        "## Confidence / Reliability",
        json.dumps(to_jsonable(summary["confidence_reliability"]), indent=2, sort_keys=True),
        "",
        "## V2 Component Analysis",
        json.dumps(to_jsonable(summary["v2_component_analysis"]), indent=2, sort_keys=True),
        "",
        "## Statistical Uncertainty",
        "Wilson intervals are attached only to strict and directional simple proportions. Balanced accuracy and macro F1 are not given Wilson intervals.",
        "",
        "## Limitations",
        "\n".join(f"- {item}" for item in summary["limitations"]),
        "",
        "## Conclusions Supported by the Data",
        "The reported metrics describe this locked FNSPID/Yahoo daily 1D cohort only.",
        "",
        "## Conclusions NOT Supported by the Data",
        "No profitability, market-beating, production generalization, or trading recommendation conclusion is supported.",
        "",
        "## Reproducibility Manifest",
        f"Pre-execution manifest hash: `{summary['pre_execution_manifest_hash']}`.",
    ]
    return "\n".join(lines)


def final_results_manifest(paths: dict[str, Path], extra: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "phase": 16,
        "status": "COMPLETED_LOCKED",
        "holdout_status": FINAL_HOLDOUT_V3_EVALUATED_STATUS,
        "artifact_paths": {name: path.as_posix() for name, path in paths.items()},
        "artifact_hashes": {name: file_sha256(path) for name, path in paths.items()},
        **extra,
        "created_at": utc_now().isoformat(),
    }
    write_json(PHASE16_OUTPUT_DIR / "FINAL_RESULTS_MANIFEST.json", payload)
    return payload


def write_docs(summary: dict[str, Any], result_manifest: dict[str, Any]) -> list[Path]:
    docs: dict[Path, str] = {
        Path("docs/FINAL_HOLDOUT_RESULTS.md"): render_final_report(summary),
        Path("docs/PHASE16_FINAL_EVALUATION.md"): render_final_report(summary),
    }
    append_notes = {
        Path("docs/FINAL_EVALUATION_PROTOCOL.md"): "\n\n## Post-Evaluation Note\n\nPhase 16 executed this preregistered protocol once on `phase15_final_holdout_v3`. This note records execution only and does not revise methodology.\n",
        Path("docs/LOCKED_COHORT_EVALUATION.md"): f"\n\n## Phase 16 Final Status\n\n`phase15_final_holdout_v3` transitioned to `{FINAL_HOLDOUT_V3_EVALUATED_STATUS}` after the one-shot final evaluation. It is permanently blocked from tuning.\n",
        Path("docs/HISTORICAL_SIGNAL_EVALUATION.md"): "\n\n## Phase 16 Final Holdout Boundary\n\nNormal historical evaluation remains blocked for final holdout cohorts. Phase 16 used an explicit final-evaluation path with a sealed config hash.\n",
        Path("docs/RESEARCH_REPRODUCIBILITY.md"): f"\n\n## Phase 16 Final Evaluation\n\nFinal result manifest: `output/research/phase16/FINAL_RESULTS_MANIFEST.json`. Results hash set: `{result_manifest.get('artifact_hashes')}`.\n",
        Path("docs/SIGNAL_V2_1_RESEARCH_CANDIDATE.md"): "\n\n## Phase 16 Final Note\n\nV2.1 remained an unpromoted secondary research candidate during final evaluation.\n",
        Path("docs/CONFIDENCE_CALIBRATION.md"): "\n\n## Phase 16 Final Note\n\nThe identity calibrator remained frozen. No final-data calibration fitting was performed.\n",
        Path("docs/LOCAL_CHANGELOG.md"): "\n\n## Phase 16 - One-Shot Final Holdout Evaluation\n\n- Executed the frozen final protocol once on `phase15_final_holdout_v3`.\n- Preserved FinBERT, Signal V1, Signal V2.0, V2.1 research-only, identity confidence calibration, and Event Study V2.\n- Created Phase 16 row export, summary JSON, report, reproducibility manifest, and result manifest.\n- Marked the final holdout as evaluated-locked and blocked from future tuning.\n",
        Path("README.md"): "\n\n## Phase 16 Final Evaluation\n\nThe locked final holdout has been evaluated once under the preregistered protocol. Artifacts are under `output/research/phase16/`; the cohort is not available for future tuning.\n",
    }
    written: list[Path] = []
    for path, text in docs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    for path, text in append_notes.items():
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        marker = text.strip().splitlines()[0]
        if marker not in existing:
            path.write_text(existing.rstrip() + text, encoding="utf-8")
        written.append(path)
    return written


def assert_final_holdout_not_tunable(dataset_id: str | None, *, purpose: str) -> None:
    if (dataset_id or "").strip() == FINAL_HOLDOUT_V3_DATASET_ID:
        raise RuntimeError(f"Refusing {purpose} on evaluated final holdout {FINAL_HOLDOUT_V3_DATASET_ID}.")


def run_phase16_final_evaluation(session: Session, *, include_v2_1: bool = True) -> dict[str, Any]:
    PHASE16_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lock = load_lock()
    cohort = ResearchCohortBuilder(session).build(build_final_cohort_config())
    holdout_checks = verify_holdout(lock, cohort.samples)
    verify_no_prior_final_runs(session, [sample.article_id for sample in cohort.samples])
    eligible_samples = [sample for sample in cohort.samples if sample.coverage.get("1D") and sample.coverage["1D"].valid]
    config = FinalEvaluationConfig(
        protocol_version=FINAL_PROTOCOL_VERSION,
        holdout_dataset_id=FINAL_HOLDOUT_V3_DATASET_ID,
        holdout_fingerprint=EXPECTED_HOLDOUT_FINGERPRINT,
        article_cohort_identifier="phase15_final_holdout_v3_locked_article_ids",
        eligible_article_ids=sorted(sample.article_id for sample in eligible_samples),
        signal_v2_1_version=ENGINE_VERSION_V2_1_RESEARCH if include_v2_1 else None,
    )
    write_json(PHASE16_OUTPUT_DIR / "FINAL_EXECUTION_CONFIG.json", config.to_dict())
    config_hash = stable_hash(config.to_dict())
    protocol_hash = file_sha256(Path("docs/FINAL_EVALUATION_PROTOCOL.md"))
    pre_manifest = write_pre_execution_manifest(config, config_hash, protocol_hash)
    pre_manifest_hash = file_sha256(PHASE16_OUTPUT_DIR / "PRE_EXECUTION_MANIFEST.json")

    analyzer = FinBERTSentimentAnalyzer()
    smoke = finbert_smoke(session, analyzer, set(lock["article_ids"]))
    experiment = ExperimentRepository(session).create(
        name=FINAL_EXPERIMENT_NAME,
        experiment_type=FINAL_EXPERIMENT_TYPE,
        configuration={
            "execution_config_hash": config_hash,
            "protocol_hash": protocol_hash,
            "holdout_fingerprint": EXPECTED_HOLDOUT_FINGERPRINT,
            "pre_execution_manifest_hash": pre_manifest_hash,
        },
        dataset_id=FINAL_HOLDOUT_V3_DATASET_ID,
        notes="Phase 16 one-shot final holdout evaluation. Status PREPARED before execution.",
    )
    experiment.status = "PREPARED"
    session.flush()
    experiment.status = "RUNNING"
    session.flush()

    articles = session.execute(
        select(NewsArticle).where(NewsArticle.id.in_(lock["article_ids"])).order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
    ).scalars().all()
    articles_by_id = {article.id: article for article in articles}
    finbert_by_article, finbert_summary = run_finbert(session, articles, analyzer, experiment.id)
    finbert_summary["smoke"] = smoke
    observations = run_final_predictions(session, eligible_samples, articles_by_id, finbert_by_article, experiment.id, include_v2_1=include_v2_1)
    summary = build_summary(config, config_hash, protocol_hash, pre_manifest_hash, holdout_checks, finbert_summary, observations, include_v2_1)
    row_path = export_rows(observations, PHASE16_OUTPUT_DIR / "final_holdout_predictions.csv", include_v2_1)
    summary_path = write_json(PHASE16_OUTPUT_DIR / "FINAL_EVALUATION_SUMMARY.json", summary)
    report_path = PHASE16_OUTPUT_DIR / "FINAL_EVALUATION_REPORT.md"
    report_path.write_text(render_final_report(summary), encoding="utf-8")
    holdout_status_path = write_json(
        PHASE16_OUTPUT_DIR / "final_holdout_v3_evaluated_lock.json",
        {
            "dataset_id": FINAL_HOLDOUT_V3_DATASET_ID,
            "previous_status": FINAL_HOLDOUT_V3_STATUS,
            "status": FINAL_HOLDOUT_V3_EVALUATED_STATUS,
            "fingerprint": EXPECTED_HOLDOUT_FINGERPRINT,
            "candidate_n": summary["candidate_n"],
            "technical_eligible_n": summary["technical_eligible_n"],
            "final_evaluated_n": summary["final_evaluated_n"],
            "permanently_blocked_from_tuning": True,
            "experiment_id": experiment.id,
            "execution_config_hash": config_hash,
            "protocol_hash": protocol_hash,
            "evaluated_at": utc_now().isoformat(),
        },
    )
    result_manifest = final_results_manifest(
        {
            "row_export": row_path,
            "summary_json": summary_path,
            "final_report": report_path,
            "pre_execution_manifest": PHASE16_OUTPUT_DIR / "PRE_EXECUTION_MANIFEST.json",
            "execution_config": PHASE16_OUTPUT_DIR / "FINAL_EXECUTION_CONFIG.json",
            "holdout_status": holdout_status_path,
        },
        {
            "experiment_id": experiment.id,
            "execution_config_hash": config_hash,
            "protocol_hash": protocol_hash,
            "holdout_fingerprint": EXPECTED_HOLDOUT_FINGERPRINT,
            "results_hash": stable_hash(summary),
        },
    )
    docs_written = write_docs(summary, result_manifest)
    result_manifest = final_results_manifest(
        {
            "row_export": row_path,
            "summary_json": summary_path,
            "final_report": report_path,
            "pre_execution_manifest": PHASE16_OUTPUT_DIR / "PRE_EXECUTION_MANIFEST.json",
            "execution_config": PHASE16_OUTPUT_DIR / "FINAL_EXECUTION_CONFIG.json",
            "holdout_status": holdout_status_path,
            **{f"doc_{idx}": path for idx, path in enumerate(docs_written, start=1)},
        },
        {
            "experiment_id": experiment.id,
            "execution_config_hash": config_hash,
            "protocol_hash": protocol_hash,
            "holdout_fingerprint": EXPECTED_HOLDOUT_FINGERPRINT,
            "results_hash": stable_hash(summary),
        },
    )
    experiment.configuration_json = json.dumps(
        {
            "execution_config_hash": config_hash,
            "protocol_hash": protocol_hash,
            "holdout_fingerprint": EXPECTED_HOLDOUT_FINGERPRINT,
            "pre_execution_manifest_hash": pre_manifest_hash,
            "results_hash": result_manifest["results_hash"],
        },
        sort_keys=True,
    )
    ExperimentRepository(session).complete(
        experiment.id,
        status="COMPLETED_LOCKED",
        notes=f"Final evaluated N={summary['final_evaluated_n']}; results hash={result_manifest['results_hash']}",
    )
    session.commit()
    return {
        "summary": summary,
        "result_manifest": result_manifest,
        "pre_execution_manifest": pre_manifest,
        "experiment_id": experiment.id,
        "files": {
            "created": [
                str(PHASE16_OUTPUT_DIR / "PRE_EXECUTION_MANIFEST.json"),
                str(PHASE16_OUTPUT_DIR / "FINAL_EXECUTION_CONFIG.json"),
                str(PHASE16_OUTPUT_DIR / "final_holdout_predictions.csv"),
                str(PHASE16_OUTPUT_DIR / "FINAL_EVALUATION_SUMMARY.json"),
                str(PHASE16_OUTPUT_DIR / "FINAL_EVALUATION_REPORT.md"),
                str(PHASE16_OUTPUT_DIR / "FINAL_RESULTS_MANIFEST.json"),
                str(PHASE16_OUTPUT_DIR / "final_holdout_v3_evaluated_lock.json"),
                "docs/FINAL_HOLDOUT_RESULTS.md",
                "docs/PHASE16_FINAL_EVALUATION.md",
            ],
            "modified": [str(path) for path in docs_written if path.name not in {"FINAL_HOLDOUT_RESULTS.md", "PHASE16_FINAL_EVALUATION.md"}] + ["data/finsent.db"],
        },
    }


def component_value(metadata: dict[str, Any], name: str) -> float | None:
    for component in metadata.get("components", []):
        if component.get("name") == name and component.get("available"):
            return component.get("normalized_value")
    return None
