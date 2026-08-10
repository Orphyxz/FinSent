from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import NewsArticle
from finsent.app.database.research_repository import ExperimentRepository, InstrumentRepository
from finsent.app.services.phase16_final_evaluation import (
    EXPECTED_HOLDOUT_FINGERPRINT,
    FINAL_PROTOCOL_VERSION,
    FinalEvaluationConfig,
    assert_final_holdout_not_tunable,
    class_distribution,
    exact_binomial_two_sided,
    metrics_payload,
    paired_correctness,
    run_finbert,
    stable_hash,
)
from finsent.app.services.phase15_research import FINAL_HOLDOUT_V3_DATASET_ID
from finsent.app.services.sentiment_v2 import (
    ModelExecutionStatus,
    ModelFailureCategory,
    SentimentAnalysisResult,
    SentimentLabel,
    TimeHorizon,
    utc_now,
)
from finsent.app.services.symbol_registry import registry


NOW = datetime(2023, 1, 3, 10, 0, 0)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as db:
        yield db


def test_final_execution_config_hash_is_stable_and_contains_locked_fingerprint() -> None:
    config = FinalEvaluationConfig(
        protocol_version=FINAL_PROTOCOL_VERSION,
        holdout_dataset_id=FINAL_HOLDOUT_V3_DATASET_ID,
        holdout_fingerprint=EXPECTED_HOLDOUT_FINGERPRINT,
        article_cohort_identifier="locked",
        eligible_article_ids=[3, 1, 2],
    )

    assert config.holdout_fingerprint == EXPECTED_HOLDOUT_FINGERPRINT
    assert stable_hash(config.to_dict()) == stable_hash(config.to_dict())
    assert "strict_accuracy" in config.metrics
    assert "majority_class" in config.baselines


def test_metric_payload_reports_strict_directional_balanced_macro_and_confusion() -> None:
    payload = metrics_payload(
        [
            ("BULLISH", "BULLISH"),
            ("BEARISH", "BULLISH"),
            ("NEUTRAL", "NEUTRAL"),
            ("BEARISH", "BEARISH"),
        ]
    )

    assert payload["total"] == 4
    assert payload["correct"] == 3
    assert payload["strict_accuracy"] == pytest.approx(0.75)
    assert payload["directional_eligible"] == 3
    assert payload["directional_accuracy"] == pytest.approx(2 / 3)
    assert payload["balanced_accuracy"] == pytest.approx((0.5 + 1.0 + 1.0) / 3)
    assert payload["macro_f1"] is not None
    assert payload["confusion_matrix"]["BULLISH"]["BEARISH"] == 1
    assert payload["strict_wilson_interval"] is not None
    assert payload["directional_wilson_interval"] is not None


def test_paired_correctness_and_mcnemar_policy() -> None:
    rows = []
    for idx in range(5):
        rows.append(_observation(idx, v1="BULLISH", v2="BEARISH", realized="BULLISH"))
    for idx in range(5, 8):
        rows.append(_observation(idx, v1="BEARISH", v2="BULLISH", realized="BULLISH"))

    result = paired_correctness(rows)

    assert result["v1_correct_v2_wrong"] == 5
    assert result["v1_wrong_v2_correct"] == 3
    assert result["discordant_n"] == 8
    assert result["mcnemar"]["method"] == "not_run"
    assert exact_binomial_two_sided(0, 25) < 0.001


def test_post_evaluation_guard_blocks_final_holdout_from_tuning() -> None:
    with pytest.raises(RuntimeError, match="evaluated final holdout"):
        assert_final_holdout_not_tunable(FINAL_HOLDOUT_V3_DATASET_ID, purpose="parameter search")


def test_class_distribution_uses_canonical_labels() -> None:
    assert class_distribution(["BULLISH", "BULLISH", "BEARISH", "NEUTRAL"]) == {
        "BULLISH": 2,
        "NEUTRAL": 1,
        "BEARISH": 1,
    }


def test_run_finbert_persists_success_without_heuristic_substitution(session) -> None:
    article = _stored_article(session)
    experiment = ExperimentRepository(session).create(name="phase16-test", experiment_type="unit", configuration={})
    analyzer = FakeAnalyzer(status=ModelExecutionStatus.SUCCESS)

    rows, summary = run_finbert(session, [article], analyzer, experiment.id)

    assert summary["requested"] == 1
    assert summary["successful"] == 1
    assert summary["failed"] == 0
    assert rows[article.id].model_family == "finbert"
    assert rows[article.id].fallback_used == 0


def test_run_finbert_failure_stops_instead_of_using_heuristic(session) -> None:
    article = _stored_article(session, url="https://example.com/fail")
    experiment = ExperimentRepository(session).create(name="phase16-test-fail", experiment_type="unit", configuration={})
    analyzer = FakeAnalyzer(status=ModelExecutionStatus.UNAVAILABLE)

    with pytest.raises(RuntimeError, match="FinBERT failed"):
        run_finbert(session, [article], analyzer, experiment.id)


class FakeAnalyzer:
    analyzer_name = "finbert"
    model_family = "finbert"
    model_name = "ProsusAI/finbert"
    model_version = "ProsusAI/finbert"
    analysis_method = "classifier"
    configured = True

    def __init__(self, status: ModelExecutionStatus) -> None:
        self.status = status

    def analyze(self, _analysis_input):
        if self.status == ModelExecutionStatus.SUCCESS:
            return SentimentAnalysisResult(
                requested_analyzer="finbert",
                actual_analyzer="finbert",
                provider="finbert",
                model_family="finbert",
                model_name=self.model_name,
                model_version=self.model_version,
                analysis_method=self.analysis_method,
                sentiment_label=SentimentLabel.BULLISH.value,
                sentiment_score=0.55,
                confidence=0.7,
                relevance=None,
                impact_strength=None,
                time_horizon=TimeHorizon.NOT_APPLICABLE.value,
                catalyst_tag="not_applicable",
                short_reason=None,
                parse_status="ok",
                fallback_used=False,
                fallback_reason=None,
                schema_version="sentiment_analysis_result_v2_1",
                prompt_version=None,
                latency_ms=1,
                created_at=utc_now(),
                status=ModelExecutionStatus.SUCCESS,
                metadata={"probabilities": {"positive": 0.7, "negative": 0.15, "neutral": 0.15}},
            )
        return SentimentAnalysisResult(
            requested_analyzer="finbert",
            actual_analyzer="finbert",
            provider="finbert",
            model_family="finbert",
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=SentimentLabel.NEUTRAL.value,
            sentiment_score=0.0,
            confidence=0.0,
            relevance=None,
            impact_strength=None,
            time_horizon=TimeHorizon.NOT_APPLICABLE.value,
            catalyst_tag="not_applicable",
            short_reason="planned failure",
            parse_status="dependency_missing",
            fallback_used=False,
            fallback_reason="planned failure",
            schema_version="sentiment_analysis_result_v2_1",
            prompt_version=None,
            latency_ms=1,
            created_at=utc_now(),
            status=ModelExecutionStatus.UNAVAILABLE,
            failure_category=ModelFailureCategory.DEPENDENCY_MISSING,
        )


def _stored_article(session, *, url: str = "https://example.com/a") -> NewsArticle:
    symbol = registry.get("US", "AMZN")
    assert symbol is not None
    instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)
    article = NewsArticle(
        instrument_id=instrument.id,
        ticker="AMZN",
        exchange="US",
        source="FNSPID",
        provider="fnspid",
        title="Amazon reports cloud revenue growth",
        summary="AWS growth remains strong.",
        url=url,
        published_at=NOW,
        dedupe_hash=url,
        relevance_score=1.0,
    )
    session.add(article)
    session.flush()
    return article


def _observation(article_id: int, *, v1: str, v2: str, realized: str):
    from finsent.app.services.phase16_final_evaluation import EnginePrediction, FinalObservation

    return FinalObservation(
        article_id=article_id,
        instrument="US:AMZN",
        published_at=NOW,
        finbert_run_id=1,
        finbert_score=0.0,
        finbert_label="neutral",
        finbert_direction="NEUTRAL",
        finbert_confidence=0.5,
        event_status="VALID",
        raw_return_1d=0.01,
        realized_direction=realized,
        predictions={
            "v1": EnginePrediction("v1", "1.0", 0.0, v1.lower(), v1, 0.5, 0.5, None, None, {}),
            "v2": EnginePrediction("v2", "2.0", 0.0, v2.lower(), v2, 0.5, 0.5, None, None, {}),
        },
    )
