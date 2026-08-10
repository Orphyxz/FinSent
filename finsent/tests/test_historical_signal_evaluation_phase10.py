from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import subprocess
import sys

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import ArticleInstrument, EventStudyResult, NewsArticle, SignalRun
from finsent.app.database.repository import PriceRepository
from finsent.app.database.research_repository import InstrumentRepository
from finsent.app.services.historical_signal_evaluation import (
    HistoricalSignalEvaluationConfig,
    HistoricalSignalEvaluator,
    conditional_returns,
    data_quality_segmentation,
    disagreement_analysis,
    export_signal_evaluation,
    metrics_by_engine_horizon,
    mode_segmentation,
    signal_direction,
)
from finsent.app.services.research_dataset import (
    LocalResearchArticleImporter,
    ResearchArticleImportConfig,
    ResearchCohortBuilder,
    ResearchCohortConfig,
    ResearchCohortExclusion,
)
from finsent.app.services.symbol_registry import registry


T0 = datetime(2026, 3, 25, 14, 0)
AAPL = registry.get("US", "AAPL")


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session()


def _add_article(
    session,
    *,
    idx: int = 1,
    published_at: datetime = T0,
    sentiment_label: str = "neutral",
    confidence: float = 0.8,
    impact: float = 0.8,
    dedupe_hash: str | None = None,
    ticker: str = "AAPL",
    exchange: str = "US",
) -> NewsArticle:
    article = NewsArticle(
        ticker=ticker,
        exchange=exchange,
        source="ResearchWire",
        provider="local_import",
        source_provider="phase10_fixture",
        leaf_provider="local_import",
        data_mode="HISTORICAL_IMPORT",
        publisher="ResearchWire",
        original_url=f"https://example.test/article-{idx}",
        canonical_url=f"https://example.test/article-{idx}",
        raw_symbol=ticker,
        title=f"{ticker} historical article {idx}",
        summary=f"Stored {sentiment_label} test item.",
        url=f"https://example.test/article-{idx}",
        published_at=published_at,
        ingested_at=published_at + timedelta(minutes=2),
        dedupe_hash=dedupe_hash or f"phase10-hash-{idx}",
        relevance_score=1.0,
        sentiment_label=sentiment_label,
        sentiment_score=confidence if sentiment_label == "bullish" else -confidence if sentiment_label == "bearish" else 0.0,
        model_confidence=confidence,
        signal_confidence=confidence,
        relevant=1,
        impact_strength=impact,
        analysis_provider="stored_fixture",
        parse_status="ok",
    )
    session.add(article)
    session.flush()
    symbol = registry.get(exchange, ticker)
    if symbol is not None:
        instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)
        article.instrument_id = instrument.id
    session.flush()
    return article


def _add_intraday_bars(session, *, ticker: str = "AAPL") -> None:
    frame = pd.DataFrame(
        [
            {"Open": 102.0, "High": 102.0, "Low": 102.0, "Close": 102.0, "Volume": 1000},
            {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1200},
            {"Open": 150.0, "High": 150.0, "Low": 150.0, "Close": 150.0, "Volume": 5000},
            {"Open": 151.0, "High": 151.0, "Low": 151.0, "Close": 151.0, "Volume": 5100},
            {"Open": 152.0, "High": 152.0, "Low": 152.0, "Close": 152.0, "Volume": 5200},
        ],
        index=[
            T0 - timedelta(hours=1),
            T0,
            T0 + timedelta(hours=1),
            T0 + timedelta(hours=4),
            T0 + timedelta(days=1),
        ],
    )
    PriceRepository(session).upsert_price_bars(ticker, frame)


def test_local_research_article_importer_dry_run_and_execute_preserve_provenance(tmp_path: Path) -> None:
    source = tmp_path / "articles.csv"
    pd.DataFrame(
        [
            {
                "headline": "Apple raises historical guidance",
                "timestamp": "2026-03-26T14:00:00Z",
                "symbol": "AAPL",
                "source": "Archive",
                "url": "https://example.test/apple-guidance",
                "sentiment_label": "bullish",
                "model_confidence": 0.91,
            },
            {"headline": "", "timestamp": "2026-03-26T14:00:00Z", "symbol": "AAPL"},
            {"headline": "Missing timestamp", "timestamp": "", "symbol": "AAPL"},
            {"headline": "Unknown symbol", "timestamp": "2026-03-26T14:00:00Z", "symbol": "NOPE"},
        ]
    ).to_csv(source, index=False)

    with _session() as session:
        dry = LocalResearchArticleImporter(session).import_file(
            ResearchArticleImportConfig(source_file=source, dataset_id="phase10_fixture", dry_run=True)
        )
        assert dry.parsed == 4
        assert dry.valid == 1
        assert dry.imported == 0
        assert dry.invalid_reasons[ResearchCohortExclusion.MISSING_TITLE] == 1
        assert dry.invalid_reasons[ResearchCohortExclusion.MISSING_TIMESTAMP] == 1
        assert dry.invalid_reasons[ResearchCohortExclusion.MISSING_INSTRUMENT] == 1
        assert session.execute(select(NewsArticle)).scalars().all() == []

        executed = LocalResearchArticleImporter(session).import_file(
            ResearchArticleImportConfig(source_file=source, dataset_id="phase10_fixture", dry_run=False)
        )
        assert executed.imported == 1
        article = session.execute(select(NewsArticle)).scalar_one()
        assert article.provider == "local_import"
        assert article.source_provider == "local_csv"
        assert article.data_mode == "HISTORICAL_IMPORT"
        assert article.sentiment_label == "bullish"
        assert session.execute(select(ArticleInstrument)).scalar_one().association_source == "research_article_import"

        duplicate = LocalResearchArticleImporter(session).import_file(
            ResearchArticleImportConfig(source_file=source, dataset_id="phase10_fixture", dry_run=False)
        )
        assert duplicate.duplicates == 1


def test_research_cohort_is_deterministic_and_records_coverage_and_splits() -> None:
    with _session() as session:
        first = _add_article(session, idx=1, published_at=T0, sentiment_label="bullish")
        _add_article(session, idx=2, published_at=T0 + timedelta(minutes=10), dedupe_hash=first.dedupe_hash)
        _add_article(session, idx=3, published_at=T0 + timedelta(days=1), ticker="TCS", exchange="NSE")
        _add_intraday_bars(session)

        config = ResearchCohortConfig(
            symbols=["AAPL"],
            markets=["US"],
            start_date=T0 - timedelta(minutes=1),
            end_date=T0 + timedelta(hours=1),
            horizons=["1h", "4h", "1d"],
            holdout_start=T0,
            seed=7,
        )
        one = ResearchCohortBuilder(session).build(config)
        two = ResearchCohortBuilder(session).build(config)

        assert one.fingerprint == two.fingerprint
        assert len(one.samples) == 1
        assert one.samples[0].article_id == first.id
        assert one.samples[0].split == "HOLDOUT"
        assert one.coverage_summary["articles"] == 1
        assert one.coverage_summary["horizons"]["1H"]["eligible"] == 1
        assert one.coverage_summary["horizons"]["4H"]["eligible"] == 1
        assert one.coverage_summary["horizons"]["1D"]["eligible"] == 1
        assert one.exclusion_counts[ResearchCohortExclusion.DUPLICATE_ARTICLE] == 1


def test_cohort_marks_missing_price_coverage_without_faking_results() -> None:
    with _session() as session:
        _add_article(session, idx=1, published_at=T0)

        cohort = ResearchCohortBuilder(session).build(ResearchCohortConfig(symbols=["AAPL"], markets=["US"], horizons=["1h"]))

        assert cohort.coverage_summary["horizons"]["1H"]["eligible"] == 0
        assert cohort.exclusion_counts[ResearchCohortExclusion.NO_PRICE_COVERAGE] == 1
        assert cohort.samples[0].exclusion_reasons == [ResearchCohortExclusion.NO_PRICE_COVERAGE]


def test_historical_evaluator_uses_only_past_known_news_and_signal_bars() -> None:
    with _session() as session:
        _add_article(session, idx=1, published_at=T0 - timedelta(minutes=30), sentiment_label="bearish", confidence=0.95)
        target = _add_article(session, idx=2, published_at=T0, sentiment_label="neutral", confidence=0.1)
        _add_article(session, idx=3, published_at=T0 + timedelta(minutes=30), sentiment_label="bullish", confidence=1.0)
        _add_intraday_bars(session)

        config = HistoricalSignalEvaluationConfig(
            engines=["v1", "v2"],
            horizons=["1h"],
            cohort=ResearchCohortConfig(symbols=["AAPL"], markets=["US"], start_date=T0, end_date=T0, horizons=["1h"], limit=1),
        )
        sample = ResearchCohortBuilder(session).build(config.cohort).samples[0]
        assert sample.article_id == target.id
        evaluator = HistoricalSignalEvaluator(session)

        pairs = evaluator._past_article_pairs(sample, config)
        assert {article.article_id for article, _ in pairs} == {str(target.id - 1), str(target.id)}
        assert all(article.published_at <= T0 for article, _ in pairs)
        past_bars = evaluator._past_price_bars(sample)
        assert past_bars.index.max().to_pydatetime() <= T0

        summary = evaluator.run(config, persist=False)
        assert {row.engine for row in summary.rows} == {"v1", "v2"}
        assert all(row.evaluation_timestamp == T0 for row in summary.rows)
        assert next(row for row in summary.rows if row.engine == "v2").canonical_direction != "BULLISH"


def test_historical_evaluator_persists_signal_runs_and_event_studies_on_execute() -> None:
    with _session() as session:
        _add_article(session, idx=1, published_at=T0, sentiment_label="bullish", confidence=0.9)
        _add_intraday_bars(session)

        summary = HistoricalSignalEvaluator(session).run(
            HistoricalSignalEvaluationConfig(
                engines=["v1", "v2"],
                horizons=["1h", "4h"],
                cohort=ResearchCohortConfig(symbols=["AAPL"], markets=["US"], start_date=T0, end_date=T0, horizons=["1h", "4h"]),
            ),
            persist=True,
        )

        assert summary.experiment_id is not None
        assert len(summary.rows) == 2
        assert len(session.execute(select(SignalRun)).scalars().all()) == 2
        event_rows = session.execute(select(EventStudyResult)).scalars().all()
        assert len(event_rows) == 4
        assert {row.signal_run_id for row in event_rows} == {item.signal_run_id for item in summary.rows}


def test_metrics_disagreement_returns_and_segmentations_are_reported() -> None:
    with _session() as session:
        _add_article(session, idx=1, published_at=T0 - timedelta(minutes=30), sentiment_label="bearish", confidence=0.8)
        _add_article(session, idx=2, published_at=T0, sentiment_label="neutral", confidence=0.2)
        _add_intraday_bars(session)
        config = HistoricalSignalEvaluationConfig(
            engines=["v1", "v2"],
            horizons=["1h"],
            cohort=ResearchCohortConfig(symbols=["AAPL"], markets=["US"], start_date=T0, end_date=T0, horizons=["1h"]),
        )
        summary = HistoricalSignalEvaluator(session).run(config, persist=False)

        metrics = metrics_by_engine_horizon(summary.rows, config)
        assert {item["horizon"] for item in metrics} == {"1H"}
        assert all("strict_accuracy" in item for item in metrics)
        assert conditional_returns(summary.rows, config)
        assert disagreement_analysis(summary.rows, config)
        assert mode_segmentation(summary.rows, config)
        assert data_quality_segmentation(summary.rows, config)
        assert signal_direction("strong_bullish") == "BULLISH"
        assert signal_direction("bearish") == "BEARISH"


def test_export_writes_research_csv_json_and_markdown_without_secrets(tmp_path: Path) -> None:
    with _session() as session:
        _add_article(session, idx=1, published_at=T0, sentiment_label="bullish", confidence=0.9)
        _add_intraday_bars(session)
        summary = HistoricalSignalEvaluator(session).run(
            HistoricalSignalEvaluationConfig(
                engines=["v2"],
                horizons=["1h"],
                cohort=ResearchCohortConfig(symbols=["AAPL"], markets=["US"], start_date=T0, end_date=T0, horizons=["1h"]),
            ),
            persist=False,
        )

        rows_path, summary_path, report_path = export_signal_evaluation(summary, tmp_path)
        csv_text = rows_path.read_text(encoding="utf-8")
        summary_text = summary_path.read_text(encoding="utf-8")
        report_text = report_path.read_text(encoding="utf-8")

        assert "article_id" in csv_text
        assert "1H_return" in csv_text
        assert summary.cohort_fingerprint in summary_text
        assert json.loads(summary_text)["config"]["evaluation_version"] == "historical_signal_evaluation_v1"
        assert "api_key" not in summary_text.lower()
        assert "Signal V2 Results" in report_text
        assert "not a trading simulator" in report_text


def test_cli_help_and_signal_evaluation_default_dry_run_are_safe(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'phase10-cli.db'}"
    ingest_help = subprocess.run(
        [sys.executable, "-m", "finsent.scripts.ingest_research_articles", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    eval_help = subprocess.run(
        [sys.executable, "-m", "finsent.scripts.run_signal_evaluation", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    dry = subprocess.run(
        [sys.executable, "-m", "finsent.scripts.run_signal_evaluation", "--symbols", "AAPL", "--market", "US", "--limit", "1"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "--execute" in ingest_help.stdout
    assert "--dry-run" in eval_help.stdout
    assert "Mode: DRY_RUN" in dry.stdout
    assert "Rows expected: 0" in dry.stdout
