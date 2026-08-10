from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.database import entities  # noqa: F401
from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import NewsArticle, SentimentAnalysisRun
from finsent.app.database.repository import NewsRepository
from finsent.app.database.research_repository import ExperimentRepository, InstrumentRepository, json_loads
from finsent.app.models.schemas import ScrapedNewsItem, SentimentResult
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.sentiment_intelligence import SentimentIntelligenceService
from finsent.app.services.sentiment_v2 import (
    CatalystTag,
    FinBERTSentimentAnalyzer,
    GeminiSentimentAnalyzer,
    HeuristicSentimentAnalyzer,
    ModelExecutionStatus,
    ModelFailureCategory,
    SentimentAnalysisInput,
    SentimentLabel,
    TimeHorizon,
    build_sentiment_analyzer,
    finbert_score,
    label_from_score,
    normalize_article_input,
    normalize_catalyst,
    normalize_sentiment_label,
    normalize_time_horizon,
    validate_gemini_payload,
)
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.symbol_registry import registry


NOW = datetime(2026, 8, 9, 10, 0, 0)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as db:
        yield db


def _article() -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id="article-1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple beats earnings expectations",
        summary="Apple raises guidance after a strong quarter.",
        url="https://example.com/aapl",
        published_at=NOW,
        ingested_at=NOW,
        provider="polygon",
        dedupe_hash="hash-aapl",
        relevance_score=1.0,
    )


def _input() -> SentimentAnalysisInput:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    return normalize_article_input(symbol, _article(), article_db_id=1, instrument_id=1)


def _input_with(**overrides) -> SentimentAnalysisInput:
    return replace(_input(), **overrides)


def _stored_article(session) -> tuple[NewsArticle, int]:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    repo = NewsRepository(session)
    row = repo.upsert_news_with_sentiment(
        ScrapedNewsItem(
            ticker="AAPL",
            source="Reuters",
            title="Apple beats earnings expectations",
            url="https://example.com/aapl",
            published_at=NOW,
            summary="Apple raises guidance after a strong quarter.",
            exchange="US",
            provider="polygon",
            ingested_at=NOW,
            dedupe_hash="hash-aapl",
            relevance_score=1.0,
        ),
        SentimentResult(
            label="bullish",
            score=0.8,
            positive=0.8,
            negative=0.0,
            neutral=0.2,
            model_label="bullish",
            model_confidence=0.8,
            text_score=0.8,
            signal_confidence=0.8,
            analysis_provider="gemini",
            parse_status="ok",
        ),
    )
    instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)
    row.instrument_id = instrument.id
    session.flush()
    return row, instrument.id


class StubGeminiClient:
    configured = True
    model = "gemini-test"

    def __init__(self, payload=None, exc: Exception | None = None) -> None:
        self.payload = payload
        self.exc = exc

    def generate_json(self, *args, **kwargs):
        if self.exc is not None:
            raise self.exc
        return self.payload


def test_normalized_analysis_input_missing_optional_body() -> None:
    item = _input()

    assert item.symbol == "AAPL"
    assert item.company_name == "Apple"
    assert item.body is None
    assert "earnings" in item.text.lower()


def test_canonical_result_validation_and_taxonomy_normalization() -> None:
    valid, errors = validate_gemini_payload(
        {
            "relevant": True,
            "sentiment": "positive",
            "confidence": 1.4,
            "impact_strength": "bad",
            "time_horizon": "short_term",
            "catalyst_tag": "analyst",
            "short_reason": "Reason",
        }
    )

    assert errors == []
    assert valid is not None
    assert valid["sentiment"] == SentimentLabel.BULLISH.value
    assert valid["confidence"] == 1.0
    assert valid["impact_strength"] == 0.0
    assert valid["time_horizon"] == TimeHorizon.ONE_TO_THREE_DAYS.value
    assert valid["catalyst_tag"] == CatalystTag.ANALYST_RATING.value
    assert normalize_sentiment_label("negative") == "bearish"
    assert normalize_catalyst("lawsuit") == "litigation"
    assert normalize_time_horizon("weird") == "1-3d"


def test_gemini_success_structured_output_prompt_version() -> None:
    analyzer = GeminiSentimentAnalyzer(
        StubGeminiClient(
            {
                "relevant": True,
                "sentiment": "bullish",
                "confidence": 0.81,
                "impact_strength": 0.7,
                "time_horizon": "1-3d",
                "catalyst_tag": "earnings",
                "short_reason": "Strong earnings catalyst.",
            }
        )
    )

    result = analyzer.analyze(_input())

    assert result.status == ModelExecutionStatus.SUCCESS
    assert result.prompt_version == "financial_sentiment_v2_1"
    assert result.schema_version == "sentiment_analysis_result_v2_1"
    assert result.sentiment_score == pytest.approx(0.81)
    assert result.actual_analyzer == "gemini"


def test_gemini_malformed_json_and_missing_required_fields_are_failures() -> None:
    malformed = GeminiSentimentAnalyzer(StubGeminiClient(["not", "object"])).analyze(_input())
    missing = GeminiSentimentAnalyzer(StubGeminiClient({"sentiment": "bullish"})).analyze(_input())

    assert malformed.status == ModelExecutionStatus.FAILED
    assert malformed.failure_category == ModelFailureCategory.PARSE_FAILURE
    assert missing.parse_status == "parse_failure"


def test_gemini_unconfigured_and_provider_failure_fallback_to_heuristic() -> None:
    class UnconfiguredClient(StubGeminiClient):
        configured = False

    service = SentimentIntelligenceService(analyzer=GeminiSentimentAnalyzer(UnconfiguredClient()))
    record = service.analyze(_input(), persist=False)

    assert record.result.requested_analyzer == "gemini"
    assert record.result.actual_analyzer == "heuristic"
    assert record.result.fallback_used is True
    assert record.result.status == ModelExecutionStatus.FALLBACK_USED


def test_heuristic_positive_negative_neutral_outputs() -> None:
    positive = HeuristicSentimentAnalyzer().analyze(_input())
    negative_input = _input_with(title="Apple shares drop after weak guidance", summary="Analysts downgrade the stock.")
    neutral_input = _input_with(title="Apple files routine annual report", summary="No major change.")

    assert positive.sentiment_label == "bullish"
    assert HeuristicSentimentAnalyzer().analyze(negative_input).sentiment_label == "bearish"
    assert HeuristicSentimentAnalyzer().analyze(neutral_input).sentiment_label == "neutral"


def test_finbert_dependency_missing_is_structured(monkeypatch) -> None:
    analyzer = FinBERTSentimentAnalyzer()

    def missing(_text):
        raise ImportError("missing transformers")

    monkeypatch.setattr(analyzer, "_predict_probabilities", missing)
    result = analyzer.analyze(_input())

    assert result.status == ModelExecutionStatus.UNAVAILABLE
    assert result.failure_category == ModelFailureCategory.DEPENDENCY_MISSING
    assert result.parse_status == "dependency_missing"


def test_finbert_probability_normalization_and_non_gemini_fields(monkeypatch) -> None:
    analyzer = FinBERTSentimentAnalyzer(model_name="ProsusAI/finbert-test")
    monkeypatch.setattr(
        analyzer,
        "_predict_probabilities",
        lambda _text: ({"positive": 0.7, "negative": 0.1, "neutral": 0.2}, {"probabilities": {"positive": 0.7, "negative": 0.1, "neutral": 0.2}, "device": "cpu"}),
    )

    result = analyzer.analyze(_input())

    assert finbert_score({"positive": 0.7, "negative": 0.1, "neutral": 0.2}) == pytest.approx(0.6)
    assert label_from_score(result.sentiment_score) == "bullish"
    assert result.confidence == pytest.approx(0.7)
    assert result.catalyst_tag == "not_applicable"
    assert result.time_horizon == "not_applicable"
    assert result.short_reason is None
    assert result.metadata["probabilities"]["positive"] == pytest.approx(0.7)


def test_analyzer_factory_choices_and_invalid() -> None:
    assert build_sentiment_analyzer("gemini").analyzer_name == "gemini"
    assert build_sentiment_analyzer("finbert").analyzer_name == "finbert"
    assert build_sentiment_analyzer("heuristic").analyzer_name == "heuristic"
    assert build_sentiment_analyzer("openai").analyzer_name == "openai"
    with pytest.raises(ValueError):
        build_sentiment_analyzer("mystery")


def test_persistence_same_article_gemini_and_finbert_coexist_experiment_metadata(session, monkeypatch) -> None:
    row, instrument_id = _stored_article(session)
    experiment = ExperimentRepository(session).create(name="phase6", experiment_type="MODEL_COMPARISON", configuration={"limit": 2})
    gemini = GeminiSentimentAnalyzer(
        StubGeminiClient(
            {
                "relevant": True,
                "sentiment": "bullish",
                "confidence": 0.8,
                "impact_strength": 0.6,
                "time_horizon": "1-3d",
                "catalyst_tag": "earnings",
                "short_reason": "Gemini reason",
            }
        )
    )
    finbert = FinBERTSentimentAnalyzer()
    monkeypatch.setattr(finbert, "_predict_probabilities", lambda _text: ({"positive": 0.2, "negative": 0.6, "neutral": 0.2}, {"probabilities": {"positive": 0.2, "negative": 0.6, "neutral": 0.2}}))
    analysis_input = _input_with(article_id=row.id, instrument_id=instrument_id)

    gemini_run = SentimentIntelligenceService(session=session, analyzer=gemini).analyze(analysis_input, experiment_id=experiment.id)
    finbert_run = SentimentIntelligenceService(session=session, analyzer=finbert).analyze(analysis_input, experiment_id=experiment.id)

    runs = session.execute(select(SentimentAnalysisRun).where(SentimentAnalysisRun.article_id == row.id)).scalars().all()
    assert {run.model_family for run in runs} == {"gemini", "finbert"}
    assert gemini_run.persisted_run_id != finbert_run.persisted_run_id
    assert all(run.experiment_id == experiment.id for run in runs)
    assert {run.prompt_version for run in runs} == {"financial_sentiment_v2_1", None}


def test_research_finbert_run_does_not_overwrite_article_compatibility_fields(session, monkeypatch) -> None:
    row, instrument_id = _stored_article(session)
    finbert = FinBERTSentimentAnalyzer()
    monkeypatch.setattr(finbert, "_predict_probabilities", lambda _text: ({"positive": 0.1, "negative": 0.8, "neutral": 0.1}, {"probabilities": {"positive": 0.1, "negative": 0.8, "neutral": 0.1}}))

    SentimentIntelligenceService(session=session, analyzer=finbert).analyze(
        _input_with(article_id=row.id, instrument_id=instrument_id),
        experiment_id=1,
    )
    stored = session.get(NewsArticle, row.id)

    assert stored.analysis_provider == "gemini"
    assert stored.sentiment_label == "bullish"


def test_gemini_requested_heuristic_actual_persisted_metadata(session) -> None:
    row, instrument_id = _stored_article(session)

    class UnconfiguredClient(StubGeminiClient):
        configured = False

    service = SentimentIntelligenceService(session=session, analyzer=GeminiSentimentAnalyzer(UnconfiguredClient()))
    record = service.analyze(_input_with(article_id=row.id, instrument_id=instrument_id), persist=True)
    run = session.get(SentimentAnalysisRun, record.persisted_run_id)
    metadata = json_loads(run.metadata_json)

    assert run.model_family == "heuristic"
    assert run.fallback_used == 1
    assert metadata["requested_analyzer"] == "gemini"
    assert metadata["actual_analyzer"] == "heuristic"


class FailingEverySecondAnalyzer(HeuristicSentimentAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def analyze(self, analysis_input):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("planned item failure")
        return super().analyze(analysis_input)


def test_batch_deterministic_order_partial_failure_and_limit(session) -> None:
    inputs = [_input_with(article_id=idx) for idx in [1, 2, 3]]
    service = SentimentIntelligenceService(session=session, analyzer=FailingEverySecondAnalyzer())

    summary = service.analyze_articles(inputs, analyzer_name="heuristic", limit=2, persist=False)

    assert summary.attempted == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert [record.input.article_id for record in summary.records] == [1, 2]


def test_no_secret_persisted_in_failure_metadata(session) -> None:
    row, instrument_id = _stored_article(session)

    class SecretClient(StubGeminiClient):
        def generate_json(self, *args, **kwargs):
            raise RuntimeError("api_key=SECRET123 token=TOKEN123")

    record = SentimentIntelligenceService(session=session, analyzer=GeminiSentimentAnalyzer(SecretClient())).analyze(
        _input_with(article_id=row.id, instrument_id=instrument_id),
        persist=True,
    )
    run = session.get(SentimentAnalysisRun, record.persisted_run_id)

    assert "SECRET123" not in run.short_reason
    assert "TOKEN123" not in run.short_reason


def test_signal_v1_output_unchanged_for_compatibility_shape() -> None:
    signal = CompositeSignalEngine().compute(None, [], type("Aggregate", (), {"overall_confidence": 0.0, "net_short_term_view": "none"})())

    assert signal.composite_score == 0.0
    assert signal.composite_label == "neutral"
    assert signal.mode == "Unavailable"
