from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from finsent.app.database import entities  # noqa: F401
from finsent.app.database.base import Base, SCHEMA_VERSION, apply_sqlite_migrations
from finsent.app.database.entities import (
    ArticleInstrument,
    DataQualityAssessmentEntity,
    DatasetMetadata,
    NewsArticle,
    ProviderAuditRun,
    SchemaMetadata,
    SentimentAnalysisRun,
)
from finsent.app.database.repository import NewsRepository
from finsent.app.database.research_repository import (
    DataQualityRepository,
    ExperimentRepository,
    InstrumentRepository,
    ProviderAuditRepository,
    ResearchResultRepository,
    canonicalize_url,
    commit_or_rollback,
    json_loads,
)
from finsent.app.models.schemas import ScrapedNewsItem, SentimentResult
from finsent.app.services.dataset_registry import DatasetScanner, DatasetSpec, register_scan_results
from finsent.app.services.llm_analyzers import ArticleAnalysis
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_contracts import ProviderFailureCategory
from finsent.app.services.provider_reliability import DataMode, DataQualityAssessment, DataQualityLabel, FreshnessLabel
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


def _article(url: str = "https://example.com/news?utm_source=x&id=1") -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id="a1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple research storage",
        summary="Storage test article.",
        url=url,
        published_at=NOW,
        ingested_at=NOW + timedelta(minutes=1),
        provider="polygon",
        dedupe_hash="hash-a1",
        relevance_score=0.9,
    )


def _analysis(provider: str = "gemini", parse_status: str = "ok") -> ArticleAnalysis:
    return ArticleAnalysis(
        relevant=True,
        sentiment="bullish",
        confidence=0.7,
        impact_strength=0.6,
        time_horizon="1-3d",
        catalyst_tag="earnings",
        short_reason="Clear catalyst.",
        provider=provider,
        parse_status=parse_status,
    )


def test_fresh_db_creates_v2_tables_and_schema_version() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)

    tables = set(inspect(engine).get_table_names())

    assert {
        "schema_metadata",
        "instruments",
        "article_instruments",
        "sentiment_analysis_runs",
        "signal_runs",
        "event_study_results",
        "experiment_runs",
        "provider_audit_runs",
        "data_quality_assessments",
        "dataset_metadata",
    }.issubset(tables)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT value FROM schema_metadata WHERE key='schema_version'")).scalar_one()
    assert version == SCHEMA_VERSION


def test_migration_is_idempotent_and_v1_record_survives(tmp_path: Path) -> None:
    db_path = tmp_path / "v1.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE news_articles (
                id INTEGER PRIMARY KEY,
                ticker VARCHAR(16) NOT NULL,
                source VARCHAR(64) NOT NULL,
                title VARCHAR(512) NOT NULL,
                summary TEXT,
                url VARCHAR(1024) NOT NULL,
                published_at DATETIME NOT NULL,
                sentiment_label VARCHAR(32),
                sentiment_score FLOAT
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO news_articles (ticker, source, title, summary, url, published_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("AAPL", "Reuters", "Old row", "still here", "https://example.com/old", NOW),
        )

    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    apply_sqlite_migrations(engine)

    with engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM news_articles")).scalar_one()
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(news_articles)").fetchall()}
        version = connection.execute(text("SELECT value FROM schema_metadata WHERE key='schema_version'")).scalar_one()

    assert count == 1
    assert {"instrument_id", "dedupe_hash", "canonical_url", "leaf_provider", "data_mode"}.issubset(columns)
    assert version == SCHEMA_VERSION


def test_canonical_instrument_insert_query_and_duplicate_handling(session) -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    repo = InstrumentRepository(session)

    first = repo.get_or_create_from_symbol(symbol)
    second = repo.get_or_create_from_symbol(symbol)

    assert first.id == second.id
    assert first.canonical_symbol == "US:AAPL"
    assert first.currency == "USD"
    assert json_loads(first.provider_symbols_json)["polygon"] == "AAPL"


def test_article_dedupe_preserves_provenance_and_canonical_url(session) -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    repo = NewsRepository(session)

    first = repo.upsert_normalized_news(symbol, _article(), _analysis())
    second = repo.upsert_normalized_news(symbol, _article("https://example.com/news?id=1&utm_campaign=y"), _analysis())

    assert first.id == second.id
    assert second.instrument_id is not None
    assert second.source_provider == "polygon"
    assert second.publisher == "Reuters"
    assert second.canonical_url == "https://example.com/news?id=1"
    links = session.execute(select(ArticleInstrument)).scalars().all()
    assert len(links) == 1


def test_url_is_not_the_only_article_identity(session) -> None:
    item = ScrapedNewsItem(
        ticker="AAPL",
        source="Reuters",
        title="Same URL first",
        url="https://example.com/shared",
        published_at=NOW,
        summary="one",
        exchange="US",
        provider="polygon",
        ingested_at=NOW,
        dedupe_hash="hash-one",
        relevance_score=1.0,
    )
    sentiment = SentimentResult(
        label="bullish",
        score=0.5,
        positive=0.5,
        negative=0.0,
        neutral=0.5,
        model_label="bullish",
        model_confidence=0.5,
        text_score=0.5,
        signal_confidence=0.5,
    )
    repo = NewsRepository(session)

    row1 = repo.upsert_news_with_sentiment(item, sentiment)
    item.title = "Same URL updated"
    item.dedupe_hash = "hash-two"
    row2 = repo.upsert_news_with_sentiment(item, sentiment)

    assert row1.id == row2.id
    assert row2.dedupe_hash == "hash-two"


def test_same_article_supports_multiple_model_runs_and_repeated_experiments(session) -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    article = NewsRepository(session).upsert_normalized_news(symbol, _article(), _analysis())
    instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)
    experiments = ExperimentRepository(session)
    research = ResearchResultRepository(session)

    exp1 = experiments.create(name="gemini-vs-finbert-a", experiment_type="MODEL_COMPARISON", configuration={"limit": 5})
    exp2 = experiments.create(name="gemini-vs-finbert-b", experiment_type="MODEL_COMPARISON", configuration={"limit": 5})
    gemini = research.store_sentiment_run(
        article_id=article.id,
        instrument_id=instrument.id,
        experiment_id=exp1.id,
        provider="gemini",
        model_family="gemini",
        model_name="gemini-2.0-flash",
        analysis_method="llm_json",
        sentiment_label="bullish",
        confidence=0.8,
        fallback_used=False,
    )
    finbert = research.store_sentiment_run(
        article_id=article.id,
        instrument_id=instrument.id,
        experiment_id=exp2.id,
        provider="finbert",
        model_family="finbert",
        model_name="ProsusAI/finbert",
        analysis_method="classifier",
        sentiment_label="positive",
        confidence=0.75,
        fallback_used=True,
        parse_status="heuristic_budget_fallback",
    )

    rows = session.execute(select(SentimentAnalysisRun).where(SentimentAnalysisRun.article_id == article.id)).scalars().all()
    assert {row.model_family for row in rows} == {"gemini", "finbert"}
    assert gemini.experiment_id != finbert.experiment_id
    assert finbert.fallback_used == 1


def test_signal_v1_run_persists_without_fake_v2_fields(session) -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)

    signal = ResearchResultRepository(session).store_signal_run(
        instrument_id=instrument.id,
        generated_at=NOW,
        engine_name="Signal Engine",
        engine_version="V1",
        final_score=0.22,
        label="bullish",
        confidence=0.66,
        signal_mode="News + Quote Quality",
        input_quality={"quote": "HIGH"},
        provider_metadata={"quote_provider": "polygon"},
        explanation="V1 fields only.",
    )

    assert signal.engine_version == "V1"
    assert signal.future_component_json is None
    assert signal.news_component is None
    assert signal.market_component is None


def test_event_study_result_preserves_matching_details_and_invalid_status(session) -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    instrument = InstrumentRepository(session).get_or_create_from_symbol(symbol)

    result = ResearchResultRepository(session).store_event_study_result(
        instrument_id=instrument.id,
        event_timestamp=NOW,
        horizon_minutes=60,
        target_timestamp=NOW + timedelta(minutes=60),
        matched_market_timestamp=NOW + timedelta(minutes=75),
        entry_price=100.0,
        exit_price=101.0,
        raw_return=0.01,
        matching_method="nearest_forward_bar_current_v1",
        elapsed_minutes=75,
        data_quality_label="LOW",
        status="INVALID",
        validity_reason="Known V1 matching issue preserved for audit.",
    )

    assert result.matched_market_timestamp == NOW + timedelta(minutes=75)
    assert result.elapsed_minutes == 75
    assert result.status == "INVALID"


def test_experiment_create_complete_configuration_round_trip(session) -> None:
    repo = ExperimentRepository(session)
    experiment = repo.create(
        name="calibration dry run",
        experiment_type="CONFIDENCE_CALIBRATION",
        configuration={"horizons": [60, 1440], "model": "gemini"},
        dataset_id="archive_v1_nse",
    )
    repo.complete(experiment.id, status="COMPLETED", notes="No algorithms executed.")

    assert experiment.completed_at is not None
    assert repo.configuration(experiment)["horizons"] == [60, 1440]


def test_provider_audit_success_fallback_failure_and_safe_message(session) -> None:
    repo = ProviderAuditRepository(session)

    success = repo.record_manual(provider="polygon", service="market_quote", operation="fetch_quote", status="AVAILABLE", record_count=1)
    fallback = repo.record_manual(provider="fallback_web", leaf_provider="yahoo_html", service="news", operation="fetch_news", status="AVAILABLE", fallback_used=True, record_count=3)
    failure = repo.record_manual(
        provider="marketaux",
        service="news",
        operation="fetch_news",
        status="DEGRADED",
        failure_category=ProviderFailureCategory.RATE_LIMIT,
        safe_message="request failed api_key=SECRET123 token=TOKEN123",
    )

    assert success.record_count == 1
    assert fallback.fallback_used == 1
    assert failure.failure_category == "RATE_LIMIT"
    assert "SECRET123" not in failure.safe_message
    assert "TOKEN123" not in failure.safe_message
    assert "[redacted]" in failure.safe_message


def test_data_quality_assessment_persistence_is_not_confidence(session) -> None:
    assessment = DataQualityAssessment(
        score=0.55,
        label=DataQualityLabel.MEDIUM,
        reasons=["scraped fallback"],
        freshness=FreshnessLabel.AGING,
        provider="fallback_web",
        mode=DataMode.SCRAPED,
        evaluated_at=NOW,
    )

    row = DataQualityRepository(session).store_assessment(subject_type="provider_audit", subject_id=10, assessment=assessment)

    assert row.score == 0.55
    assert row.label == "MEDIUM"
    assert json_loads(row.reasons_json) == ["scraped fallback"]
    assert not hasattr(row, "confidence")


def test_dataset_scanner_classifies_lfs_pointer_broken_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "SnP_daily_update.csv"
    original = "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 100\n"
    path.write_text(original, encoding="utf-8")
    spec = DatasetSpec("sp_daily_update", "S&P daily update", path, "HISTORICAL_PRICE_FILE", "US", "daily", "local")

    result = DatasetScanner().scan(spec)

    assert result.status == "BROKEN"
    assert "Git LFS pointer" in result.issues[0]
    assert path.read_text(encoding="utf-8") == original


def test_dataset_scanner_archive_and_reference_metadata(tmp_path: Path) -> None:
    archive = tmp_path / "archive" / "v1"
    archive.mkdir(parents=True)
    (archive / "TCS.csv").write_text("Date,Open,High,Low,Close,Volume\n2026-08-07,100,110,90,105,1000\n", encoding="utf-8")
    universe = tmp_path / "All_Indian_Stocks_listed_in_nifty500.csv"
    universe.write_text("Symbol,Company Name,Industry\nTCS,Tata Consultancy Services,Technology\n", encoding="utf-8")
    scanner = DatasetScanner()

    archive_result = scanner.scan(DatasetSpec("archive", "Archive", archive, "HISTORICAL_PRICE_ARCHIVE", "India", "daily", "local"), deep=True)
    universe_result = scanner.scan(DatasetSpec("india_universe", "India universe", universe, "REFERENCE_UNIVERSE", "India", None, "local"))

    assert archive_result.status == "USABLE"
    assert archive_result.symbol_count == 1
    assert archive_result.row_count == 1
    assert universe_result.status == "REFERENCE"
    assert universe_result.symbol_count == 1


def test_dataset_registry_round_trip(session, tmp_path: Path) -> None:
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text("Symbol,Company Name\nAAPL,Apple\n", encoding="utf-8")
    result = DatasetScanner().scan(DatasetSpec("companies", "Companies", csv_path, "REFERENCE_UNIVERSE", "US", None, "local"))

    row = register_scan_results(session, [result])[0]

    assert row.dataset_id == "companies"
    assert row.status == "REFERENCE"
    assert json_loads(row.columns_json) == ["Symbol", "Company Name"]


def test_timestamp_policy_round_trip_is_naive_utc_representation(session) -> None:
    run = ExperimentRepository(session).create(name="time", experiment_type="TIMESTAMP_TEST", configuration={})

    assert run.created_at.tzinfo is None
    assert run.created_at <= datetime.now().replace(tzinfo=None)


def test_transaction_rollback_on_duplicate_instrument(session) -> None:
    repo = InstrumentRepository(session)
    repo.get_or_create(
        canonical_symbol_value="US:ABC",
        display_symbol="ABC",
        exchange="US",
        company_name="ABC Inc",
    )
    session.commit()

    duplicate = entities.Instrument(
        canonical_symbol="US:ABC",
        display_symbol="ABC2",
        exchange="US",
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        commit_or_rollback(session)

    assert session.execute(select(entities.Instrument)).scalars().all()[0].canonical_symbol == "US:ABC"


def test_signal_v1_numerical_behavior_unchanged() -> None:
    engine = CompositeSignalEngine()

    assert engine.compute(None, [], _Aggregate()).composite_score == 0.0


class _Aggregate:
    overall_sentiment = "neutral"
    overall_confidence = 0.0
    action_bias = "neutral"
    net_short_term_view = "No data"
    final_reason = "No data"
    provider = "test"
