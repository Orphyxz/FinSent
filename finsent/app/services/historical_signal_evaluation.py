from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.analysis.event_study_v2 import ENGINE_VERSION_EVENT_STUDY_V2, EventStudyHorizon, EventStudyStatus
from finsent.app.database.entities import NewsArticle
from finsent.app.database.repository import PriceRepository
from finsent.app.database.research_repository import ExperimentRepository, InstrumentRepository, ResearchResultRepository
from finsent.app.services.event_study_service_v2 import EventStudyServiceV2
from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.model_comparison import classification_metrics, realized_direction
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.research_dataset import ResearchCohort, ResearchCohortBuilder, ResearchCohortConfig, ResearchCohortSample
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_engine_v2 import ENGINE_NAME_V2, ENGINE_VERSION_V2, SignalEngineV2, SignalInputV2, SignalNewsItemV2, result_metadata


SIGNAL_EVALUATION_VERSION = "historical_signal_evaluation_v1"
SIGNAL_V1_ENGINE_NAME = "finsent_signal_v1"
SIGNAL_V1_ENGINE_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class HistoricalSignalEvaluationConfig:
    experiment_name: str = "Historical Signal Evaluation"
    engines: list[str] = field(default_factory=lambda: ["v1", "v2"])
    horizons: list[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    cohort: ResearchCohortConfig = field(default_factory=ResearchCohortConfig)
    news_lookback_hours: int = 72
    sentiment_source: str = "ACTIVE_STORED_SENTIMENT"
    realized_return_threshold: float = 0.001
    export: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "engines": self.engines,
            "horizons": self.horizons,
            "cohort": self.cohort.to_dict(),
            "news_lookback_hours": self.news_lookback_hours,
            "sentiment_source": self.sentiment_source,
            "realized_return_threshold": self.realized_return_threshold,
            "event_study_engine_version": ENGINE_VERSION_EVENT_STUDY_V2,
            "signal_v1_version": SIGNAL_V1_ENGINE_VERSION,
            "signal_v2_version": ENGINE_VERSION_V2,
            "evaluation_version": SIGNAL_EVALUATION_VERSION,
        }


@dataclass(slots=True)
class SignalOutcomeRecord:
    article_id: int
    instrument: str
    evaluation_timestamp: datetime
    split: str
    engine: str
    engine_version: str
    original_label: str
    canonical_direction: str
    signal_score: float | None
    signal_confidence: float | None
    signal_mode: str | None
    data_quality: str | None
    signal_run_id: int | None
    outcomes: dict[str, dict[str, Any]]
    component_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HistoricalSignalEvaluationSummary:
    experiment_id: int | None
    cohort_fingerprint: str
    config: dict[str, Any]
    coverage: dict[str, Any]
    metrics_by_engine_horizon: list[dict[str, Any]]
    disagreement: list[dict[str, Any]]
    conditional_returns: list[dict[str, Any]]
    mode_segmentation: list[dict[str, Any]]
    data_quality_segmentation: list[dict[str, Any]]
    component_analysis: dict[str, Any]
    rows: list[SignalOutcomeRecord]


class HistoricalSignalEvaluator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_service = EventStudyServiceV2(session=session)

    def dry_run(self, config: HistoricalSignalEvaluationConfig) -> HistoricalSignalEvaluationSummary:
        if config.cohort.dataset_id in {"phase13_final_holdout_v1", "phase14_final_holdout_v2", "phase15_final_holdout_v3"}:
            raise RuntimeError("Refusing to evaluate FINAL_HOLDOUT_LOCKED without a future explicit final-evaluation mode.")
        cohort = ResearchCohortBuilder(self.session).build(config.cohort)
        return self._summary(None, config, cohort, [])

    def run(self, config: HistoricalSignalEvaluationConfig, *, persist: bool = True, export_dir: Path | None = None) -> HistoricalSignalEvaluationSummary:
        if config.cohort.dataset_id in {"phase13_final_holdout_v1", "phase14_final_holdout_v2", "phase15_final_holdout_v3"}:
            raise RuntimeError("Refusing to evaluate FINAL_HOLDOUT_LOCKED without a future explicit final-evaluation mode.")
        cohort = ResearchCohortBuilder(self.session).build(config.cohort)
        experiment_id = None
        if persist:
            experiment = ExperimentRepository(self.session).create(
                name=config.experiment_name,
                experiment_type="historical_signal_evaluation",
                configuration={**config.to_dict(), "cohort_fingerprint": cohort.fingerprint},
                dataset_id=config.cohort.dataset_id,
                notes="Phase 10 historical signal evaluation.",
            )
            experiment_id = experiment.id
        rows: list[SignalOutcomeRecord] = []
        for sample in cohort.samples:
            if sample.status == "INELIGIBLE":
                continue
            if "v1" in config.engines:
                rows.append(self._evaluate_v1(sample, config, experiment_id, persist))
            if "v2" in config.engines:
                rows.append(self._evaluate_v2(sample, config, experiment_id, persist))
        if persist and experiment_id is not None:
            ExperimentRepository(self.session).complete(experiment_id, status="COMPLETED", notes=f"Signal evaluation rows: {len(rows)}")
        summary = self._summary(experiment_id, config, cohort, rows)
        if export_dir is not None:
            export_signal_evaluation(summary, export_dir)
        return summary

    def _evaluate_v1(self, sample: ResearchCohortSample, config: HistoricalSignalEvaluationConfig, experiment_id: int | None, persist: bool) -> SignalOutcomeRecord:
        pairs = self._past_article_pairs(sample, config)
        aggregate = self._aggregate(pairs)
        signal = CompositeSignalEngine().compute(None, pairs, aggregate)
        signal_run_id = None
        if persist:
            instrument = InstrumentRepository(self.session).get_or_create_from_symbol(sample.instrument)
            row = ResearchResultRepository(self.session).store_signal_run(
                instrument_id=instrument.id,
                experiment_id=experiment_id,
                generated_at=sample.published_at,
                engine_name=SIGNAL_V1_ENGINE_NAME,
                engine_version=SIGNAL_V1_ENGINE_VERSION,
                final_score=signal.composite_score,
                label=signal.composite_label,
                confidence=signal.signal_confidence,
                signal_mode=signal.mode,
                input_quality={"sentiment_source": config.sentiment_source},
                future_component={"lookback_articles": len(pairs), "no_lookahead": True},
                explanation="Historical V1 signal evaluation.",
            )
            signal_run_id = row.id
        return self._record(sample, "v1", SIGNAL_V1_ENGINE_VERSION, signal.composite_label, signal.composite_score, signal.signal_confidence, signal.mode, "UNASSESSED", signal_run_id, {}, config, persist, experiment_id)

    def _evaluate_v2(self, sample: ResearchCohortSample, config: HistoricalSignalEvaluationConfig, experiment_id: int | None, persist: bool) -> SignalOutcomeRecord:
        pairs = self._past_article_pairs(sample, config)
        price_df = self._past_price_bars(sample)
        signal_input = SignalInputV2(
            instrument=sample.instrument,
            evaluation_timestamp=sample.published_at,
            news_items=[SignalNewsItemV2(article, analysis) for article, analysis in pairs],
            quote=None,
            price_bars=price_df,
            provider_metadata={"sentiment_source": config.sentiment_source, "no_lookahead": True},
        )
        result = SignalEngineV2().evaluate(signal_input)
        signal_run_id = None
        metadata = result_metadata(result)
        if persist:
            instrument = InstrumentRepository(self.session).get_or_create_from_symbol(sample.instrument)
            row = ResearchResultRepository(self.session).store_signal_run(
                instrument_id=instrument.id,
                experiment_id=experiment_id,
                generated_at=sample.published_at,
                engine_name=ENGINE_NAME_V2,
                engine_version=ENGINE_VERSION_V2,
                final_score=result.final_score,
                label=result.label,
                confidence=result.confidence,
                signal_mode=result.signal_mode,
                input_quality=result.data_quality,
                provider_metadata=signal_input.provider_metadata,
                news_component=_component_value(metadata, "news"),
                market_component=_component_value(metadata, "price_momentum"),
                future_component=metadata,
                explanation=result.explanation,
            )
            signal_run_id = row.id
        quality_label = "UNASSESSED" if all(value is None for value in result.data_quality.values()) else "ASSESSED"
        return self._record(sample, "v2", ENGINE_VERSION_V2, result.label, result.final_score, result.confidence, result.signal_mode, quality_label, signal_run_id, metadata, config, persist, experiment_id)

    def _record(
        self,
        sample: ResearchCohortSample,
        engine: str,
        engine_version: str,
        label: str,
        score: float | None,
        confidence: float | None,
        mode: str | None,
        data_quality: str | None,
        signal_run_id: int | None,
        components: dict[str, Any],
        config: HistoricalSignalEvaluationConfig,
        persist: bool,
        experiment_id: int | None,
    ) -> SignalOutcomeRecord:
        outcomes: dict[str, dict[str, Any]] = {}
        price_df = PriceRepository(self.session).list_price_df(sample.instrument.ticker)
        if not price_df.empty:
            study_input = self.event_service.build_input(
                instrument=sample.instrument,
                event_timestamp=sample.published_at,
                price_bars=price_df,
                horizons=[EventStudyHorizon.parse(value) for value in config.horizons],
                article_id=sample.article_id,
                signal_run_id=signal_run_id,
                experiment_id=experiment_id,
            )
            for event_record in self.event_service.evaluate(study_input, persist=persist):
                result = event_record.result
                direction = realized_direction(result.raw_return, config.realized_return_threshold)
                canonical = signal_direction(label)
                outcomes[result.horizon.label] = {
                    "status": result.status.value,
                    "raw_return": result.raw_return,
                    "realized_direction": direction,
                    "correct": canonical == direction if direction is not None and result.status == EventStudyStatus.VALID else None,
                }
        return SignalOutcomeRecord(
            article_id=sample.article_id,
            instrument=f"{sample.instrument.exchange}:{sample.instrument.ticker}",
            evaluation_timestamp=sample.published_at,
            split=sample.split,
            engine=engine,
            engine_version=engine_version,
            original_label=label,
            canonical_direction=signal_direction(label),
            signal_score=score,
            signal_confidence=confidence,
            signal_mode=mode,
            data_quality=data_quality,
            signal_run_id=signal_run_id,
            outcomes=outcomes,
            component_summary=components,
        )

    def _past_article_pairs(self, sample: ResearchCohortSample, config: HistoricalSignalEvaluationConfig) -> list[tuple[NormalizedNewsArticle, ArticleAnalysis]]:
        start = sample.published_at - timedelta(hours=config.news_lookback_hours)
        rows = self.session.execute(
            select(NewsArticle)
            .where(
                NewsArticle.ticker == sample.instrument.ticker,
                NewsArticle.exchange == sample.instrument.exchange,
                NewsArticle.published_at <= sample.published_at,
                NewsArticle.published_at >= start,
            )
            .order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
        ).scalars().all()
        return [(article_to_normalized(row), article_to_analysis(row, config.sentiment_source)) for row in rows]

    def _past_price_bars(self, sample: ResearchCohortSample) -> pd.DataFrame:
        price_df = PriceRepository(self.session).list_price_df(sample.instrument.ticker)
        if price_df.empty:
            return price_df
        work = price_df.copy()
        work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
        work = work[work["timestamp"] <= sample.published_at]
        return work.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}).set_index("timestamp")

    @staticmethod
    def _aggregate(pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]]) -> AggregateAnalysis:
        if not pairs:
            return AggregateAnalysis("neutral", 0.0, "no strong edge", "watch", "No past-known articles available.", "historical")
        confidence = sum(analysis.confidence for _, analysis in pairs) / len(pairs)
        score = sum((1 if analysis.sentiment == "bullish" else -1 if analysis.sentiment == "bearish" else 0) * analysis.confidence for _, analysis in pairs)
        sentiment = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
        return AggregateAnalysis(sentiment, confidence, f"{sentiment} historical stored sentiment", "watch", "Stored historical sentiment aggregation.", "historical")

    def _summary(self, experiment_id: int | None, config: HistoricalSignalEvaluationConfig, cohort: ResearchCohort, rows: list[SignalOutcomeRecord]) -> HistoricalSignalEvaluationSummary:
        return HistoricalSignalEvaluationSummary(
            experiment_id=experiment_id,
            cohort_fingerprint=cohort.fingerprint,
            config={**config.to_dict(), "cohort_fingerprint": cohort.fingerprint},
            coverage=cohort.coverage_summary,
            metrics_by_engine_horizon=metrics_by_engine_horizon(rows, config),
            disagreement=disagreement_analysis(rows, config),
            conditional_returns=conditional_returns(rows, config),
            mode_segmentation=mode_segmentation(rows, config),
            data_quality_segmentation=data_quality_segmentation(rows, config),
            component_analysis=component_analysis(rows, config),
            rows=rows,
        )


def article_to_normalized(row: NewsArticle) -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id=str(row.id),
        ticker=row.ticker,
        exchange=row.exchange or "",
        source=row.source,
        title=row.title,
        summary=row.summary,
        url=row.url,
        published_at=row.published_at,
        ingested_at=row.ingested_at or row.published_at,
        provider=row.provider or "stored",
        dedupe_hash=row.dedupe_hash or str(row.id),
        relevance_score=row.relevance_score,
    )


def article_to_analysis(row: NewsArticle, sentiment_source: str) -> ArticleAnalysis:
    label = (row.sentiment_label or "neutral").lower()
    return ArticleAnalysis(
        relevant=bool(row.relevant if row.relevant is not None else True),
        sentiment=label if label in {"bullish", "bearish", "neutral"} else "neutral",
        confidence=float(row.model_confidence or row.signal_confidence or abs(row.sentiment_score or 0.0) or 0.5),
        impact_strength=float(row.impact_strength or 0.5),
        time_horizon=row.time_horizon or "1-3d",
        catalyst_tag=row.catalyst_tag or "unknown",
        short_reason=row.short_reason or f"Stored sentiment source: {sentiment_source}",
        provider=row.analysis_provider or sentiment_source,
        parse_status=row.parse_status or "stored",
    )


def signal_direction(label: str | None) -> str:
    text = str(label or "").lower()
    if "bullish" in text:
        return "BULLISH"
    if "bearish" in text:
        return "BEARISH"
    return "NEUTRAL"


def metrics_by_engine_horizon(rows: list[SignalOutcomeRecord], config: HistoricalSignalEvaluationConfig) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for engine in sorted({row.engine for row in rows}):
        for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
            pairs = []
            for row in rows:
                outcome = row.outcomes.get(horizon)
                if row.engine == engine and outcome and outcome["realized_direction"] is not None:
                    pairs.append((row.canonical_direction, outcome["realized_direction"]))
            metrics = classification_metrics(pairs)
            output.append({"engine": engine, "horizon": horizon, **asdict(metrics)})
    return output


def conditional_returns(rows: list[SignalOutcomeRecord], config: HistoricalSignalEvaluationConfig) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for engine in sorted({row.engine for row in rows}):
        for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
            for direction in ["BULLISH", "BEARISH"]:
                returns = [row.outcomes[horizon]["raw_return"] for row in rows if row.engine == engine and row.canonical_direction == direction and horizon in row.outcomes and row.outcomes[horizon]["raw_return"] is not None]
                output.append({"engine": engine, "horizon": horizon, "direction": direction, "n": len(returns), "mean_return": _mean(returns), "median_return": float(median(returns)) if returns else None, "mean_abs_return": _mean([abs(item) for item in returns])})
    return output


def disagreement_analysis(rows: list[SignalOutcomeRecord], config: HistoricalSignalEvaluationConfig) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    by_article: dict[int, dict[str, SignalOutcomeRecord]] = {}
    for row in rows:
        by_article.setdefault(row.article_id, {})[row.engine] = row
    for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
        stats = {"horizon": horizon, "n": 0, "v1_correct": 0, "v2_correct": 0, "both_wrong": 0, "realized_neutral": 0}
        for engines in by_article.values():
            v1 = engines.get("v1")
            v2 = engines.get("v2")
            if not v1 or not v2 or v1.canonical_direction == v2.canonical_direction:
                continue
            outcome = v1.outcomes.get(horizon) or v2.outcomes.get(horizon)
            if not outcome or outcome["realized_direction"] is None:
                continue
            stats["n"] += 1
            stats["realized_neutral"] += 1 if outcome["realized_direction"] == "NEUTRAL" else 0
            v1_ok = v1.canonical_direction == outcome["realized_direction"]
            v2_ok = v2.canonical_direction == outcome["realized_direction"]
            stats["v1_correct"] += 1 if v1_ok else 0
            stats["v2_correct"] += 1 if v2_ok else 0
            stats["both_wrong"] += 1 if not v1_ok and not v2_ok and outcome["realized_direction"] != "NEUTRAL" else 0
        output.append(stats)
    return output


def mode_segmentation(rows: list[SignalOutcomeRecord], config: HistoricalSignalEvaluationConfig) -> list[dict[str, Any]]:
    output = []
    for mode in sorted({row.signal_mode or "UNKNOWN" for row in rows}):
        for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
            pairs = [(row.canonical_direction, row.outcomes[horizon]["realized_direction"]) for row in rows if (row.signal_mode or "UNKNOWN") == mode and horizon in row.outcomes and row.outcomes[horizon]["realized_direction"] is not None]
            output.append({"mode": mode, "horizon": horizon, "n": len(pairs), "metrics": asdict(classification_metrics(pairs))})
    return output


def data_quality_segmentation(rows: list[SignalOutcomeRecord], config: HistoricalSignalEvaluationConfig) -> list[dict[str, Any]]:
    output = []
    for quality in sorted({row.data_quality or "UNKNOWN" for row in rows}):
        for horizon in [EventStudyHorizon.parse(value).label for value in config.horizons]:
            pairs = [(row.canonical_direction, row.outcomes[horizon]["realized_direction"]) for row in rows if (row.data_quality or "UNKNOWN") == quality and horizon in row.outcomes and row.outcomes[horizon]["realized_direction"] is not None]
            output.append({"data_quality": quality, "horizon": horizon, "n": len(pairs), "metrics": asdict(classification_metrics(pairs))})
    return output


def component_analysis(rows: list[SignalOutcomeRecord], config: HistoricalSignalEvaluationConfig) -> dict[str, Any]:
    values: dict[str, list[float]] = {}
    for row in rows:
        if row.engine != "v2":
            continue
        for component in row.component_summary.get("components", []):
            if component.get("available"):
                values.setdefault(component["name"], []).append(float(component.get("normalized_value") or 0.0))
    return {name: {"n": len(items), "mean": _mean(items)} for name, items in values.items()}


def export_signal_evaluation(summary: HistoricalSignalEvaluationSummary, output_dir: Path) -> tuple[Path, Path, Path]:
    target = output_dir / str(summary.experiment_id or "dry_run")
    target.mkdir(parents=True, exist_ok=True)
    rows_path = target / "signal_evaluation_rows.csv"
    summary_path = target / "signal_evaluation_summary.json"
    report_path = target / "REPORT.md"
    pd.DataFrame([row_to_export(row) for row in summary.rows]).to_csv(rows_path, index=False)
    summary_path.write_text(json.dumps(to_jsonable(asdict(summary) | {"rows": []}), indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(render_report(summary), encoding="utf-8")
    return rows_path, summary_path, report_path


def row_to_export(row: SignalOutcomeRecord) -> dict[str, Any]:
    payload = {key: value for key, value in asdict(row).items() if key not in {"outcomes", "component_summary"}}
    for horizon, outcome in row.outcomes.items():
        payload[f"{horizon}_return"] = outcome["raw_return"]
        payload[f"{horizon}_realized_direction"] = outcome["realized_direction"]
        payload[f"{horizon}_correct"] = outcome["correct"]
        payload[f"{horizon}_status"] = outcome["status"]
    if row.component_summary:
        payload["component_summary"] = json.dumps(row.component_summary, sort_keys=True)
    return payload


def render_report(summary: HistoricalSignalEvaluationSummary) -> str:
    lines = [
        "# FinSent Historical Signal Evaluation",
        "",
        "## Experiment Configuration",
        f"Experiment ID: {summary.experiment_id}",
        f"Cohort fingerprint: {summary.cohort_fingerprint}",
        "",
        "## Dataset / Cohort",
        f"Rows evaluated: {len(summary.rows)}",
        f"Coverage: {summary.coverage}",
        "",
        "## Signal V1 Results",
        "See horizon-specific summary JSON. Interpret all percentages with N.",
        "",
        "## Signal V2 Results",
        "See horizon-specific summary JSON. V2 weights were not optimized.",
        "",
        "## V1 vs V2",
        f"Disagreement analysis: {summary.disagreement}",
        "",
        "## Horizon Analysis",
        "1H, 4H, and 1D are reported separately.",
        "",
        "## Data Quality Analysis",
        f"Data-quality segmentation: {summary.data_quality_segmentation}",
        "",
        "## V2 Component Analysis",
        f"Components: {summary.component_analysis}",
        "",
        "## Limitations",
        "This is signal-direction evaluation, not a trading simulator. No profitability, calibration, or statistical significance is claimed.",
        "",
        "## Interpretation",
        "In this cohort, use the exported metrics as descriptive evidence only.",
    ]
    return "\n".join(lines)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def _component_value(metadata: dict[str, Any], name: str) -> float | None:
    for component in metadata.get("components", []):
        if component.get("name") == name and component.get("available"):
            return component.get("normalized_value")
    return None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
