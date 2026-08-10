from __future__ import annotations

from dataclasses import dataclass, field
from itertools import islice
from typing import Iterable

from sqlalchemy.orm import Session

from finsent.app.database.research_repository import ResearchResultRepository
from finsent.app.services.sentiment_v2 import (
    HeuristicSentimentAnalyzer,
    ModelExecutionStatus,
    ModelHealthRegistry,
    SentimentAnalysisInput,
    SentimentAnalysisResult,
    SentimentAnalyzer,
    build_sentiment_analyzer,
    run_fingerprint,
)


@dataclass(slots=True)
class SentimentExecutionRecord:
    input: SentimentAnalysisInput
    result: SentimentAnalysisResult
    persisted_run_id: int | None = None
    error: str | None = None


@dataclass(slots=True)
class BatchSentimentSummary:
    requested_analyzer: str
    attempted: int
    succeeded: int
    failed: int
    persisted: int
    records: list[SentimentExecutionRecord] = field(default_factory=list)


class SentimentIntelligenceService:
    def __init__(
        self,
        *,
        session: Session | None = None,
        analyzer: SentimentAnalyzer | None = None,
        fallback_to_heuristic: bool = True,
        persist_policy: str = "explicit",
        health: ModelHealthRegistry | None = None,
    ) -> None:
        self.session = session
        self.analyzer = analyzer
        self.fallback_to_heuristic = fallback_to_heuristic
        self.persist_policy = persist_policy
        self.health = health or ModelHealthRegistry()

    def analyze(
        self,
        analysis_input: SentimentAnalysisInput,
        *,
        analyzer_name: str | None = None,
        experiment_id: int | None = None,
        persist: bool | None = None,
    ) -> SentimentExecutionRecord:
        analyzer = self.analyzer or build_sentiment_analyzer(analyzer_name)
        result = analyzer.analyze(analysis_input)
        if self.fallback_to_heuristic and analyzer.analyzer_name == "gemini" and result.status not in {ModelExecutionStatus.SUCCESS}:
            fallback = HeuristicSentimentAnalyzer(
                requested_analyzer="gemini",
                fallback_reason=result.short_reason or result.fallback_reason or "Gemini analysis failed.",
            )
            result = fallback.analyze(analysis_input)
        self.health.record(result)

        should_persist = bool(persist) if persist is not None else self.persist_policy == "always" or experiment_id is not None
        persisted_id = None
        if should_persist:
            if self.session is None:
                raise ValueError("A SQLAlchemy session is required to persist sentiment analysis runs.")
            persisted_id = self.persist_result(analysis_input, result, experiment_id=experiment_id)
        return SentimentExecutionRecord(input=analysis_input, result=result, persisted_run_id=persisted_id)

    def persist_result(
        self,
        analysis_input: SentimentAnalysisInput,
        result: SentimentAnalysisResult,
        *,
        experiment_id: int | None = None,
    ) -> int:
        if self.session is None:
            raise ValueError("A SQLAlchemy session is required to persist sentiment analysis runs.")
        if not isinstance(analysis_input.article_id, int):
            raise ValueError("Persisting a sentiment run requires a database article id.")
        metadata = dict(result.metadata)
        metadata["requested_analyzer"] = result.requested_analyzer
        metadata["actual_analyzer"] = result.actual_analyzer
        metadata["fallback_reason"] = result.fallback_reason
        metadata["failure_category"] = result.failure_category.value if result.failure_category else None
        metadata["status"] = result.status.value
        metadata["latency_ms"] = result.latency_ms
        metadata["run_fingerprint"] = run_fingerprint(analysis_input, result)
        row = ResearchResultRepository(self.session).store_sentiment_run(
            article_id=analysis_input.article_id,
            instrument_id=analysis_input.instrument_id,
            experiment_id=experiment_id,
            provider=result.provider,
            model_family=result.model_family,
            model_name=result.model_name,
            model_version=result.model_version,
            analysis_method=result.analysis_method,
            prompt_version=result.prompt_version,
            schema_version=result.schema_version,
            sentiment_label=result.sentiment_label,
            sentiment_score=result.sentiment_score,
            confidence=result.confidence,
            relevance=result.relevance,
            impact_strength=result.impact_strength,
            time_horizon=result.time_horizon,
            catalyst_tag=result.catalyst_tag,
            short_reason=result.short_reason,
            parse_status=result.parse_status,
            fallback_used=result.fallback_used,
            metadata=metadata,
        )
        return row.id

    def analyze_articles(
        self,
        inputs: Iterable[SentimentAnalysisInput],
        *,
        analyzer_name: str,
        experiment_id: int | None = None,
        limit: int = 10,
        persist: bool = True,
    ) -> BatchSentimentSummary:
        bounded_limit = max(0, min(int(limit), 50))
        records: list[SentimentExecutionRecord] = []
        attempted = 0
        succeeded = 0
        failed = 0
        persisted_count = 0
        for analysis_input in islice(inputs, bounded_limit):
            attempted += 1
            try:
                record = self.analyze(
                    analysis_input,
                    analyzer_name=analyzer_name,
                    experiment_id=experiment_id,
                    persist=persist,
                )
            except Exception as exc:
                failed += 1
                records.append(
                    SentimentExecutionRecord(
                        input=analysis_input,
                        result=_failed_batch_result(analyzer_name, str(exc)),
                        error=str(exc),
                    )
                )
                continue
            if record.result.status in {ModelExecutionStatus.SUCCESS, ModelExecutionStatus.FALLBACK_USED}:
                succeeded += 1
            else:
                failed += 1
            if record.persisted_run_id is not None:
                persisted_count += 1
            records.append(record)
        return BatchSentimentSummary(
            requested_analyzer=analyzer_name,
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            persisted=persisted_count,
            records=records,
        )


def _failed_batch_result(analyzer_name: str, reason: str) -> SentimentAnalysisResult:
    from finsent.app.services.sentiment_v2 import (
        CatalystTag,
        ModelFailureCategory,
        SentimentLabel,
        TimeHorizon,
        utc_now,
    )

    return SentimentAnalysisResult(
        requested_analyzer=analyzer_name,
        actual_analyzer=analyzer_name,
        provider=analyzer_name,
        model_family=analyzer_name,
        model_name=analyzer_name,
        model_version=None,
        analysis_method="batch_error",
        sentiment_label=SentimentLabel.NEUTRAL.value,
        sentiment_score=0.0,
        confidence=0.0,
        relevance=None,
        impact_strength=None,
        time_horizon=TimeHorizon.UNKNOWN.value,
        catalyst_tag=CatalystTag.UNKNOWN.value,
        short_reason=reason,
        parse_status="batch_error",
        fallback_used=False,
        fallback_reason=reason,
        schema_version="sentiment_analysis_result_v2_1",
        prompt_version=None,
        latency_ms=None,
        created_at=utc_now(),
        status=ModelExecutionStatus.FAILED,
        failure_category=ModelFailureCategory.UNKNOWN,
        metadata={"error": reason},
    )
