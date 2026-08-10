from __future__ import annotations

from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.analysis.event_study_v2 import EventStudyStatus
from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import NewsArticle, PriceBar
from finsent.app.database.repository import PriceRepository
from finsent.app.services.historical_news_acquisition import (
    FNSPIDAcquisitionConfig,
    FNSPIDAdapter,
    FNSPIDPartialAcquirer,
    ResearchSubsetImporter,
    SourceDecision,
    evaluate_source_candidates,
    export_normalized_articles,
    file_sha256,
    normalize_yfinance_frame,
    readiness_report,
    write_manifest,
)
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig, ResearchCohortExclusion


HEADER = "Unnamed: 0,Date,Article_title,Stock_symbol,Url,Publisher,Author,Article,Lsa_summary,Luhn_summary,Textrank_summary,Lexrank_summary\n"
ROW_AAPL = '1,2023-01-03 14:00:00 UTC,Apple supplier demand improves,AAPL,https://example.test/aapl,Reuters,,Full body text,Short Apple summary,,,\n'
ROW_AMZN = '2,2023-01-04 14:00:00 UTC,Amazon cloud growth steadies,AMZN,https://example.test/amzn,Benzinga,,Full body text,Short Amazon summary,,,\n'
ROW_UNSUPPORTED = '3,2023-01-04 14:00:00 UTC,Unknown company item,NOPE,https://example.test/nope,Wire,,Body,Summary,,,\n'
ROW_MISSING_TITLE = '4,2023-01-04 14:00:00 UTC,,AAPL,https://example.test/missing,Wire,,Body,Summary,,,\n'
ROW_OLD = '5,2022-01-04 14:00:00 UTC,Old Apple item,AAPL,https://example.test/old,Wire,,Body,Summary,,,\n'


class FakeResponse:
    def __init__(self, text: str):
        self.raw = io.BytesIO(text.encode("utf-8"))
        self.headers = {"content-length": str(len(text.encode("utf-8")))}

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0
        self.headers = {}

    def get(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(self.text)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session()


def test_fnspid_adapter_maps_valid_row_and_rejects_malformed_rows() -> None:
    adapter = FNSPIDAdapter()
    valid, reason = adapter.normalize_row(
        {
            "Unnamed: 0": "42",
            "Date": "2023-01-03 14:00:00 UTC",
            "Article_title": "Apple raises guidance",
            "Stock_symbol": "AAPL",
            "Url": "https://example.test/aapl",
            "Publisher": "Reuters",
            "Lsa_summary": "Guidance summary",
        },
        row_number=1,
    )

    assert reason is None
    assert valid is not None
    assert valid.symbol == "AAPL"
    assert valid.publisher == "Reuters"
    assert valid.canonical_text_hash
    assert valid.dedupe_hash

    assert adapter.normalize_row({"Date": "bad", "Article_title": "x", "Stock_symbol": "AAPL"}, row_number=1)[1] == "MISSING_TIMESTAMP"
    assert adapter.normalize_row({"Date": "2023-01-03", "Article_title": "x"}, row_number=1)[1] == "MISSING_SYMBOL"
    assert adapter.normalize_row({"Date": "2023-01-03", "Stock_symbol": "AAPL"}, row_number=1)[1] == "MISSING_TEXT"
    assert adapter.normalize_row({"Date": "2023-01-03", "Article_title": "x", "Stock_symbol": "NOPE"}, row_number=1)[1] == "UNSUPPORTED_SYMBOL"


def test_partial_acquisition_filters_symbols_dates_limit_and_dry_run(tmp_path: Path) -> None:
    csv_text = HEADER + ROW_OLD + ROW_AAPL + ROW_AMZN + ROW_UNSUPPORTED + ROW_MISSING_TITLE
    summary = FNSPIDPartialAcquirer(session_factory=FakeSession(csv_text)).acquire(
        FNSPIDAcquisitionConfig(
            symbols=["AAPL", "AMZN"],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31),
            limit=1,
            cache_dir=tmp_path,
            dry_run=True,
        )
    )

    assert summary.dry_run is True
    assert summary.scanned_rows == 2
    assert summary.matched_rows == 1
    assert summary.records[0].symbol == "AAPL"
    assert summary.subset_path is None
    assert not list(tmp_path.rglob("*"))


def test_partial_acquisition_execute_writes_subset_and_manifest(tmp_path: Path) -> None:
    csv_text = HEADER + ROW_AAPL + ROW_AMZN
    summary = FNSPIDPartialAcquirer(session_factory=FakeSession(csv_text)).acquire(
        FNSPIDAcquisitionConfig(
            symbols=["AAPL", "AMZN"],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31),
            limit=5,
            cache_dir=tmp_path,
            batch_id="test_batch",
            dry_run=False,
        )
    )

    subset = Path(summary.subset_path or "")
    manifest = Path(summary.manifest_path or "")
    assert subset.exists()
    assert manifest.exists()
    assert summary.checksum_sha256 == file_sha256(subset)
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))[-1]
    assert manifest_payload["local_relative_path"].endswith("test_batch.csv")
    assert manifest_payload["filters"]["symbols"] == ["AAPL", "AMZN"]
    assert "api_key" not in manifest.read_text(encoding="utf-8").lower()


def test_subset_import_preserves_provenance_and_is_idempotent(tmp_path: Path) -> None:
    csv_text = HEADER + ROW_AAPL
    summary = FNSPIDPartialAcquirer(session_factory=FakeSession(csv_text)).acquire(
        FNSPIDAcquisitionConfig(
            symbols=["AAPL"],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 31),
            cache_dir=tmp_path,
            batch_id="import_batch",
            dry_run=False,
        )
    )
    with _session() as session:
        importer = ResearchSubsetImporter(session)
        first = importer.import_fnspid_subset(Path(summary.subset_path or ""), dataset_id="phase11_test", dry_run=False)
        second = importer.import_fnspid_subset(Path(summary.subset_path or ""), dataset_id="phase11_test", dry_run=False)
        article = session.execute(select(NewsArticle)).scalar_one()

        assert first.imported == 1
        assert second.duplicates == 1
        assert article.provider == "fnspid"
        assert article.source_provider == "fnspid"
        assert article.data_mode == "HISTORICAL_IMPORT"
        assert article.instrument_id is not None


def test_daily_price_coverage_supports_1d_but_not_intraday() -> None:
    with _session() as session:
        article = NewsArticle(
            ticker="AAPL",
            exchange="US",
            source="FNSPID",
            provider="fnspid",
            title="Apple daily coverage item",
            summary="summary",
            url="https://example.test/aapl-daily",
            published_at=datetime(2023, 1, 3, 14, 0),
            ingested_at=datetime(2023, 1, 3, 14, 1),
            dedupe_hash="daily-hash",
            relevance_score=1.0,
            sentiment_label="neutral",
            model_confidence=0.5,
            impact_strength=0.5,
            relevant=1,
        )
        session.add(article)
        frame = pd.DataFrame(
            [
                {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000},
                {"Open": 101.0, "High": 102.0, "Low": 100.0, "Close": 102.0, "Volume": 1200},
                {"Open": 103.0, "High": 104.0, "Low": 102.0, "Close": 104.0, "Volume": 1300},
            ],
            index=[datetime(2023, 1, 3, 21, 0), datetime(2023, 1, 4, 21, 0), datetime(2023, 1, 5, 21, 0)],
        )
        PriceRepository(session).upsert_price_bars("AAPL", frame, provider="test_daily", dataset_id="daily_fixture")

        cohort = ResearchCohortBuilder(session).build(
            ResearchCohortConfig(symbols=["AAPL"], markets=["US"], horizons=["1h", "4h", "1d"])
        )

        coverage = cohort.samples[0].coverage
        assert coverage["1D"].valid is True
        assert coverage["1D"].status == EventStudyStatus.VALID.value
        assert coverage["1H"].status == EventStudyStatus.UNSUPPORTED_GRANULARITY.value
        assert coverage["4H"].status == EventStudyStatus.UNSUPPORTED_GRANULARITY.value


def test_price_repository_can_store_research_provenance() -> None:
    with _session() as session:
        frame = pd.DataFrame(
            [{"Open": 1.0, "High": 2.0, "Low": 1.0, "Close": 2.0, "Volume": 10}],
            index=[datetime(2023, 1, 3)],
        )
        PriceRepository(session).upsert_price_bars(
            "AAPL",
            frame,
            provider="yfinance_daily",
            dataset_id="batch-1",
            data_mode="HISTORICAL_RESEARCH",
            quality_status="RESEARCH_DAILY",
        )
        row = session.execute(select(PriceBar)).scalar_one()

        assert row.provider == "yfinance_daily"
        assert row.dataset_id == "batch-1"
        assert row.data_mode == "HISTORICAL_RESEARCH"
        assert row.quality_status == "RESEARCH_DAILY"


def test_yfinance_daily_normalization_uses_us_close_timestamps() -> None:
    frame = pd.DataFrame(
        [{"Open": 1.0, "High": 2.0, "Low": 1.0, "Close": 2.0, "Volume": 10}],
        index=[datetime(2023, 1, 3)],
    )

    normalized = normalize_yfinance_frame(frame)

    assert normalized.index[0].to_pydatetime() == datetime(2023, 1, 3, 21, 0)


def test_manifest_and_normalized_export_are_relative_and_secret_free(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path / "fnspid" / "MANIFEST.json",
        {
            "source_name": "FNSPID",
            "local_relative_path": "data/research_sources/fnspid/subsets/test.csv",
            "filters": {"symbols": ["AAPL"]},
        },
    )
    record = FNSPIDAdapter().normalize_row(
        {
            "Unnamed: 0": "1",
            "Date": "2023-01-03 14:00:00 UTC",
            "Article_title": "Apple item",
            "Stock_symbol": "AAPL",
            "Url": "https://example.test/aapl",
            "Publisher": "Reuters",
            "Lsa_summary": "summary",
        },
        row_number=1,
    )[0]
    assert record is not None
    export_path = export_normalized_articles([record], tmp_path / "normalized.csv")

    assert path.exists()
    assert export_path.exists()
    assert "api_key" not in path.read_text(encoding="utf-8").lower()
    assert "canonical_text_hash" in export_path.read_text(encoding="utf-8")


def test_source_candidate_evaluation_and_readiness_report_are_explicit() -> None:
    evaluations = evaluate_source_candidates()
    decisions = {item.source: item.decision for item in evaluations}

    assert decisions["FNSPID"] == SourceDecision.PREFERRED
    assert decisions["Yahoo HTML scraping"] == SourceDecision.REJECTED
    report = readiness_report()
    assert {"finbert_dependencies_available", "gemini_configured"}.issubset(report)


def test_prepare_research_cohort_help_is_safe(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'cli.db'}"
    result = subprocess.run(
        [sys.executable, "-m", "finsent.scripts.prepare_research_cohort", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "--execute" in result.stdout
    assert "--analyze-finbert" in result.stdout
    assert "--evaluate" in result.stdout
