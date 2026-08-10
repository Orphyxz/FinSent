from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import EventStudyResult, NewsArticle, SentimentAnalysisRun
from finsent.app.database.repository import PriceRepository
from finsent.app.database.research_repository import InstrumentRepository, ResearchResultRepository, json_loads
from finsent.app.services.model_comparison import (
    ArticleSelectionService,
    ExclusionReason,
    GeminiFinBertExperimentRunner,
    ModelComparisonConfig,
    agreement_summary,
    build_analysis_input,
    classification_metrics,
    comparison_fingerprint,
    confidence_bucket_summaries,
    direction_from_score,
    disagreement_summaries,
    export_experiment,
    paired_rows_dataframe,
    realized_direction,
    summary_to_dict,
    wilson_interval,
)
from finsent.app.services.sentiment_v2 import ModelExecutionStatus, SentimentAnalysisResult, utc_now
from finsent.app.services.symbol_registry import registry


AAPL = registry.get("US", "AAPL")
NOW = datetime(2026, 3, 27, 14, 0)


class FakeAnalyzer:
    configured = True

    def __init__(self, name: str, score: float, confidence: float = 0.8, *, status: ModelExecutionStatus = ModelExecutionStatus.SUCCESS, catalyst: str = "earnings") -> None:
        self.analyzer_name = name
        self.model_family = name
        self.model_name = f"{name}-test"
        self.model_version = "test-v1"
        self.analysis_method = "fake"
        self.score = score
        self.confidence = confidence
        self.status = status
        self.catalyst = catalyst
        self.calls: list[str] = []

    def analyze(self, analysis_input):
        self.calls.append(analysis_input.text)
        return _result(self.analyzer_name, self.score, self.confidence, self.status, catalyst=self.catalyst)


class UnconfiguredAnalyzer(FakeAnalyzer):
    configured = False


def _result(name: str, score: float, confidence: float, status: ModelExecutionStatus = ModelExecutionStatus.SUCCESS, *, catalyst: str = "earnings") -> SentimentAnalysisResult:
    label = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return SentimentAnalysisResult(
        requested_analyzer=name,
        actual_analyzer=name,
        provider=name,
        model_family=name,
        model_name=f"{name}-test",
        model_version="test-v1",
        analysis_method="fake",
        sentiment_label=label,
        sentiment_score=score,
        confidence=confidence,
        relevance=1.0,
        impact_strength=0.7,
        time_horizon="intraday",
        catalyst_tag=catalyst if name == "gemini" else "not_applicable",
        short_reason="fake deterministic test result",
        parse_status="ok" if status == ModelExecutionStatus.SUCCESS else "failed",
        fallback_used=False,
        fallback_reason=None,
        schema_version="sentiment_analysis_result_v2_1",
        prompt_version="prompt-test" if name == "gemini" else None,
        latency_ms=100 if name == "gemini" else 20,
        created_at=utc_now(),
        status=status,
        metadata={"test": True},
    )


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session()


def _add_article(session, *, idx: int = 1, ticker: str = "AAPL", exchange: str = "US", published_at: datetime = NOW, dedupe_hash: str | None = None, title: str | None = None) -> NewsArticle:
    article = NewsArticle(
        ticker=ticker,
        exchange=exchange,
        source="Reuters",
        provider="polygon",
        title=title or f"Apple earnings beat expectations {idx}",
        summary="Apple reports stronger growth and guidance.",
        url=f"https://example.com/{idx}",
        published_at=published_at,
        ingested_at=published_at + timedelta(minutes=1),
        dedupe_hash=dedupe_hash or f"hash-{idx}",
        relevance_score=0.9,
    )
    session.add(article)
    session.flush()
    symbol = registry.get(exchange, ticker)
    if symbol is not None:
        instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)
        article.instrument_id = instrument.id
    session.flush()
    return article


def _add_bars(session, ticker: str = "AAPL") -> None:
    frame = pd.DataFrame(
        [
            {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1000},
            {"Open": 102.0, "High": 102.0, "Low": 102.0, "Close": 102.0, "Volume": 1000},
            {"Open": 104.0, "High": 104.0, "Low": 104.0, "Close": 104.0, "Volume": 1000},
            {"Open": 106.0, "High": 106.0, "Low": 106.0, "Close": 106.0, "Volume": 1000},
        ],
        index=[
            datetime(2026, 3, 27, 14, 0),
            datetime(2026, 3, 27, 15, 0),
            datetime(2026, 3, 27, 18, 0),
            datetime(2026, 3, 30, 14, 0),
        ],
    )
    PriceRepository(session).upsert_price_bars(ticker, frame)


def test_article_selection_filters_symbol_market_date_limit_and_dedupes() -> None:
    with _session() as session:
        _add_article(session, idx=1, published_at=datetime(2026, 3, 25, 14, 0))
        _add_article(session, idx=2, dedupe_hash="dup")
        _add_article(session, idx=3, dedupe_hash="dup")
        _add_article(session, idx=4, ticker="TCS", exchange="NSE")

        summary = ArticleSelectionService(session).select_articles(
            ModelComparisonConfig(symbols=["AAPL"], markets=["US"], start_date=datetime(2026, 3, 26), max_articles=1, random_seed=7)
        )

        assert summary.selected_count == 1
        assert summary.exclusion_counts[ExclusionReason.DUPLICATE_SAMPLE] == 1
        assert ExclusionReason.SAMPLE_LIMIT not in summary.exclusion_counts
        assert summary.selected[0].instrument.ticker == "AAPL"


def test_seeded_selection_is_reproducible() -> None:
    with _session() as session:
        for idx in range(10):
            _add_article(session, idx=idx + 1, published_at=NOW + timedelta(minutes=idx))

        config = ModelComparisonConfig(max_articles=3, random_seed=99)
        one = [item.article_id for item in ArticleSelectionService(session).select_articles(config).selected]
        two = [item.article_id for item in ArticleSelectionService(session).select_articles(config).selected]

        assert one == two


def test_direction_and_realized_direction_normalization() -> None:
    assert direction_from_score(0.16) == "BULLISH"
    assert direction_from_score(-0.16) == "BEARISH"
    assert direction_from_score(0.01) == "NEUTRAL"
    assert realized_direction(0.002) == "BULLISH"
    assert realized_direction(-0.002) == "BEARISH"
    assert realized_direction(0.0001) == "NEUTRAL"


def test_metric_calculations_are_deterministic() -> None:
    metrics = classification_metrics(
        [
            ("BULLISH", "BULLISH"),
            ("BULLISH", "BEARISH"),
            ("NEUTRAL", "NEUTRAL"),
            ("BEARISH", "BEARISH"),
        ]
    )

    assert metrics.total == 4
    assert metrics.correct == 3
    assert metrics.strict_accuracy == 0.75
    assert metrics.directional_eligible == 3
    assert round(metrics.directional_accuracy or 0, 6) == round(2 / 3, 6)
    assert metrics.precision["BULLISH"] == 0.5
    assert metrics.recall["BEARISH"] == 0.5
    assert metrics.f1["NEUTRAL"] == 1.0
    assert metrics.balanced_accuracy is not None


def test_wilson_interval_bounds() -> None:
    low, high = wilson_interval(3, 4)
    assert 0.0 <= low <= high <= 1.0


def test_runner_executes_paired_models_and_event_studies() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        runner = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        )

        summary = runner.run(ModelComparisonConfig(max_articles=1, horizons=["1h", "4h", "1d"]), persist=True)

        assert summary.selected_count == 1
        assert summary.gemini_calls_new == 1
        assert summary.finbert_runs_new == 1
        assert summary.agreement.agreements == 1
        assert {item.horizon for item in summary.horizons} == {"1H", "4H", "1D"}
        assert session.execute(select(SentimentAnalysisRun)).scalars().all()
        assert session.execute(select(EventStudyResult)).scalars().all()


def test_same_canonical_input_is_given_to_both_models() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        gemini = FakeAnalyzer("gemini", 0.8)
        finbert = FakeAnalyzer("finbert", -0.8)
        GeminiFinBertExperimentRunner(session=session, gemini_analyzer=gemini, finbert_analyzer=finbert).run(
            ModelComparisonConfig(max_articles=1, horizons=["1h"]),
            persist=False,
        )

        assert gemini.calls == finbert.calls
        assert "Apple earnings beat" in gemini.calls[0]


def test_gemini_failure_is_tracked_without_heuristic_substitution() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.0, status=ModelExecutionStatus.FAILED),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"]), persist=False)

        assert summary.gemini_calls_failed == 1
        assert ExclusionReason.GEMINI_FAILED in summary.paired_rows[0].exclusion_reasons


def test_finbert_failure_is_tracked() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", 0.0, status=ModelExecutionStatus.FAILED),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"]), persist=False)

        assert summary.finbert_runs_failed == 1
        assert ExclusionReason.FINBERT_FAILED in summary.paired_rows[0].exclusion_reasons


def test_existing_run_reuse_uses_exact_fingerprint() -> None:
    with _session() as session:
        article = _add_article(session)
        _add_bars(session)
        selection = ArticleSelectionService(session).select_articles(ModelComparisonConfig(max_articles=1))
        selected = selection.selected[0]
        analyzer = FakeAnalyzer("gemini", 0.8)
        fp = comparison_fingerprint(build_analysis_input(selected), analyzer, ModelComparisonConfig(max_articles=1))
        ResearchResultRepository(session).store_sentiment_run(
            article_id=article.id,
            instrument_id=article.instrument_id,
            provider="gemini",
            model_family="gemini",
            model_name="gemini-test",
            model_version="test-v1",
            analysis_method="fake",
            prompt_version="prompt-test",
            schema_version="sentiment_analysis_result_v2_1",
            sentiment_label="bullish",
            sentiment_score=0.8,
            confidence=0.9,
            parse_status="ok",
            metadata={"comparison_fingerprint": fp, "latency_ms": 5},
        )

        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=analyzer,
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"]), persist=False)

        assert summary.gemini_calls_reused == 1
        assert analyzer.calls == []


def test_force_rerun_ignores_reusable_run() -> None:
    with _session() as session:
        article = _add_article(session)
        _add_bars(session)
        selection = ArticleSelectionService(session).select_articles(ModelComparisonConfig(max_articles=1))
        analyzer = FakeAnalyzer("gemini", 0.8)
        fp = comparison_fingerprint(build_analysis_input(selection.selected[0]), analyzer, ModelComparisonConfig(max_articles=1))
        ResearchResultRepository(session).store_sentiment_run(
            article_id=article.id,
            model_family="gemini",
            model_name="gemini-test",
            analysis_method="fake",
            sentiment_score=0.8,
            metadata={"comparison_fingerprint": fp},
        )

        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=analyzer,
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"], force_rerun=True), persist=False)

        assert summary.gemini_calls_new == 1
        assert analyzer.calls


def test_invalid_event_study_horizon_is_excluded_separately() -> None:
    with _session() as session:
        _add_article(session)
        # No bars intentionally.
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h", "4h"]), persist=False)

        assert ExclusionReason.NO_MARKET_DATA in summary.paired_rows[0].exclusion_reasons
        assert any(reason.startswith(ExclusionReason.UNSUPPORTED_HORIZON) for reason in summary.paired_rows[0].exclusion_reasons)


def test_agreement_and_disagreement_summaries() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", -0.8),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"]), persist=False)

        assert summary.agreement.disagreements == 1
        assert summary.agreement.matrix["BULLISH"]["BEARISH"] == 1
        assert summary.disagreements[0].sample_count == 1
        assert summary.disagreements[0].gemini_correct == 1


def test_confidence_bucket_and_catalyst_summaries() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8, confidence=0.85, catalyst="product"),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7, confidence=0.55),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"]), persist=False)

        assert any(bucket.model == "gemini" and bucket.bucket == "0.8-0.9" and bucket.count == 1 for bucket in summary.confidence_buckets)
        assert summary.catalysts[0].catalyst == "product"
        assert summary.catalysts[0].sentiment_distribution["BULLISH"] == 1


def test_latency_and_market_symbol_counts_are_reported() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"]), persist=False)

        assert summary.latency[0].model == "gemini"
        assert summary.latency[0].mean_ms == 100.0
        assert summary.market_counts["US"] == 1
        assert summary.symbol_counts["US:AAPL"] == 1


def test_export_writes_csv_and_json_without_article_body_or_secrets(tmp_path: Path) -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h"], experiment_name="Export test"), persist=False)

        csv_path, json_path = export_experiment(summary, tmp_path)
        csv_text = csv_path.read_text(encoding="utf-8")
        json_text = json_path.read_text(encoding="utf-8")
        assert "article_id" in csv_text
        assert "gemini_score" in csv_text
        assert "body" not in csv_text.lower()
        assert "api_key" not in json_text.lower()
        assert "Export test" in json_text


def test_row_level_dataframe_has_stable_research_columns() -> None:
    with _session() as session:
        _add_article(session)
        _add_bars(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=FakeAnalyzer("gemini", 0.8),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).run(ModelComparisonConfig(max_articles=1, horizons=["1h", "4h"]), persist=False)

        frame = paired_rows_dataframe(summary.paired_rows, ModelComparisonConfig(max_articles=1, horizons=["1h", "4h"]))
        assert {"article_id", "gemini_score", "finbert_score", "1H_return", "4H_status", "model_agreement"}.issubset(frame.columns)


def test_dry_run_makes_no_model_calls_or_writes() -> None:
    with _session() as session:
        _add_article(session)
        gemini = FakeAnalyzer("gemini", 0.8)
        finbert = FakeAnalyzer("finbert", 0.7)
        summary = GeminiFinBertExperimentRunner(session=session, gemini_analyzer=gemini, finbert_analyzer=finbert).dry_run(
            ModelComparisonConfig(max_articles=1)
        )

        assert summary.selected_count == 1
        assert gemini.calls == []
        assert finbert.calls == []
        assert session.execute(select(SentimentAnalysisRun)).scalars().all() == []


def test_unconfigured_gemini_is_reported_in_dry_run() -> None:
    with _session() as session:
        _add_article(session)
        summary = GeminiFinBertExperimentRunner(
            session=session,
            gemini_analyzer=UnconfiguredAnalyzer("gemini", 0.0),
            finbert_analyzer=FakeAnalyzer("finbert", 0.7),
        ).dry_run(ModelComparisonConfig(max_articles=1))

        assert summary.gemini_calls_failed == 1


def test_summary_serialization_excludes_rows_by_default() -> None:
    assert "paired_rows" not in summary_to_dict(
        GeminiFinBertExperimentRunner(session=_session(), gemini_analyzer=FakeAnalyzer("gemini", 0.8), finbert_analyzer=FakeAnalyzer("finbert", 0.7)).dry_run(
            ModelComparisonConfig(max_articles=0)
        ),
        include_rows=False,
    )
