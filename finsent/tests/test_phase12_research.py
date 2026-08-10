from __future__ import annotations

from datetime import datetime
import io
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import NewsArticle
from finsent.app.database.entities import PriceBar
from finsent.app.database.repository import PriceRepository
from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluator, article_to_analysis, article_to_normalized
from finsent.app.services.phase12_research import (
    StratifiedFNSPIDAcquisitionConfig,
    StratifiedFNSPIDAcquirer,
    YahooChartDailyPriceAcquirer,
    YahooChartDailyPriceConfig,
    baseline_payload,
    cohort_selection_config,
    evaluate_rows_by_split,
    export_v2_diagnostic_from_rows,
    mcnemar_result,
    paired_correctness_table,
    phase12_preregistration,
    preregistration_fingerprint,
    systematic_disagreement_cases,
    v2_parameter_registry,
    write_preregistration,
)
from finsent.app.services.signal_engine_v2 import SignalEngineV2, SignalInputV2, SignalNewsItemV2
from finsent.app.services.symbol_registry import registry


HEADER = "Date,Article_title,Stock_symbol,Url,Publisher,Author,Article,Lsa_summary,Luhn_summary,Textrank_summary,Lexrank_summary\n"


def _row(idx: int, symbol: str, day: int) -> str:
    return f"2020-06-{day:02d} 14:00:00 UTC,{symbol} real news {idx},{symbol},https://example.test/{symbol.lower()}/{idx},Wire,,body,summary,,,\n"


class FakeResponse:
    def __init__(self, text: str, payload: dict | None = None) -> None:
        self.raw = io.BytesIO(text.encode("utf-8"))
        self.headers = {"content-length": str(len(text.encode("utf-8")))}
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload or {}


class FakeSession:
    headers: dict[str, str]

    def __init__(self, text: str) -> None:
        self.text = text
        self.headers = {}

    def get(self, *args, **kwargs) -> FakeResponse:
        return FakeResponse(self.text)


class FakeYahooSession:
    headers: dict[str, str]

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.headers = {}

    def get(self, *args, **kwargs) -> FakeResponse:
        return FakeResponse("", self.payload)


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session()


def test_stratified_fnspid_acquisition_enforces_per_symbol_quota(tmp_path: Path) -> None:
    csv_text = HEADER + "".join(_row(i, "AAPL", 1) for i in range(5)) + "".join(_row(i, "AMZN", 2) for i in range(5)) + "".join(_row(i, "GOOGL", 3) for i in range(5))

    summary = StratifiedFNSPIDAcquirer(session_factory=FakeSession(csv_text)).acquire(
        StratifiedFNSPIDAcquisitionConfig(
            symbols=["AAPL", "AMZN", "GOOGL"],
            start_date=datetime(2020, 6, 1),
            end_date=datetime(2020, 6, 30),
            per_symbol_limit=2,
            cache_dir=tmp_path,
            dry_run=True,
        )
    )

    assert summary.per_symbol_counts == {"AAPL": 2, "AMZN": 2, "GOOGL": 2}
    assert [record.symbol for record in summary.records].count("AAPL") == 2
    assert summary.quota_satisfied is True


def test_stratified_execute_writes_manifest_with_counts(tmp_path: Path) -> None:
    csv_text = HEADER + _row(1, "AAPL", 1) + _row(2, "AMZN", 2)

    summary = StratifiedFNSPIDAcquirer(session_factory=FakeSession(csv_text)).acquire(
        StratifiedFNSPIDAcquisitionConfig(
            symbols=["AAPL", "AMZN"],
            start_date=datetime(2020, 6, 1),
            end_date=datetime(2020, 6, 30),
            per_symbol_limit=1,
            cache_dir=tmp_path,
            batch_id="phase12_test",
            dry_run=False,
        )
    )

    assert Path(summary.subset_path or "").exists()
    manifest = json.loads(Path(summary.manifest_path or "").read_text(encoding="utf-8"))[-1]
    assert manifest["per_symbol_counts"] == {"AAPL": 1, "AMZN": 1}
    assert manifest["selection_version"] == "phase12_stratified_fnspid_v1"
    assert "api_key" not in json.dumps(manifest).lower()


def test_yahoo_chart_daily_price_acquirer_imports_unadjusted_close_with_manifest(tmp_path: Path) -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1591032600, 1591119000],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0],
                                "high": [102.0, 103.0],
                                "low": [99.0, 100.0],
                                "close": [101.0, 102.0],
                                "volume": [1000, 1200],
                            }
                        ],
                        "adjclose": [{"adjclose": [99.5, 100.5]}],
                    },
                }
            ]
        }
    }
    with _session() as session:
        summary = YahooChartDailyPriceAcquirer(session_factory=FakeYahooSession(payload)).acquire(
            YahooChartDailyPriceConfig(
                symbols=["AAPL"],
                start_date=datetime(2020, 6, 1),
                end_date=datetime(2020, 6, 3),
                batch_id="phase12_prices",
                cache_dir=tmp_path,
                dry_run=False,
            ),
            db_session=session,
        )
        row = session.execute(select(PriceBar)).scalars().first()

        assert summary.imported_rows == {"AAPL": 2}
        assert row is not None
        assert row.close == 101.0
        assert row.provider == "yahoo_chart_daily"
        manifest = json.loads(Path(summary.manifest_path or "").read_text(encoding="utf-8"))[-1]
        assert "Unadjusted OHLC quote.close" in manifest["price_basis"]


def test_preregistration_is_fingerprinted_and_saved_before_evaluation(tmp_path: Path) -> None:
    prereg = phase12_preregistration()
    path = write_preregistration(tmp_path / "PHASE12_COHORT_PREREGISTRATION.md", prereg)

    text = path.read_text(encoding="utf-8")
    assert preregistration_fingerprint(prereg) in text
    assert "Rule-change policy" in text
    assert "2020-06-05T00:00:00" in text


def test_cohort_selection_config_is_chronological_and_uses_locked_boundary() -> None:
    prereg = phase12_preregistration()
    config = cohort_selection_config(prereg)

    assert config.holdout_start == datetime(2020, 6, 5)
    assert config.horizons == ["1d"]
    assert config.limit == 200


def test_finbert_missing_gemini_fields_do_not_zero_v2_news_component() -> None:
    article = NewsArticle(
        ticker="AAPL",
        exchange="US",
        source="FNSPID",
        provider="fnspid",
        title="Apple raises guidance",
        summary="FinBERT only article",
        url="https://example.test/aapl",
        published_at=datetime(2020, 6, 1, 14, 0),
        sentiment_label="bullish",
        sentiment_score=0.8,
        model_confidence=0.8,
        relevance_score=None,
        impact_strength=None,
        relevant=None,
        analysis_provider="finbert",
        parse_status="ok",
    )

    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    result = SignalEngineV2().evaluate(
        SignalInputV2(
            instrument=symbol,
            evaluation_timestamp=datetime(2020, 6, 1, 14, 30),
            news_items=[SignalNewsItemV2(article_to_normalized(article), article_to_analysis(article, "finbert"))],
        )
    )

    news = next(component for component in result.components if component.name == "news")
    assert news.available is True
    assert news.normalized_value > 0
    assert news.metadata["total_weight"] > 0


def test_historical_v2_price_input_excludes_future_bars() -> None:
    with _session() as session:
        frame = pd.DataFrame(
            [
                {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000},
                {"Open": 101.0, "High": 102.0, "Low": 100.0, "Close": 101.0, "Volume": 1200},
                {"Open": 110.0, "High": 111.0, "Low": 109.0, "Close": 110.0, "Volume": 9999},
            ],
            index=[datetime(2020, 6, 1, 21), datetime(2020, 6, 2, 21), datetime(2020, 6, 4, 21)],
        )
        PriceRepository(session).upsert_price_bars("AAPL", frame)
        symbol = registry.get("US", "AAPL")
        sample = type("Sample", (), {"instrument": symbol, "published_at": datetime(2020, 6, 3, 12)})()

        past = HistoricalSignalEvaluator(session)._past_price_bars(sample)

        assert past.index.max().to_pydatetime() == datetime(2020, 6, 2, 21)


def test_split_metrics_keep_development_and_holdout_separate(tmp_path: Path) -> None:
    rows = pd.DataFrame(
        [
            {"article_id": 1, "split": "DEVELOPMENT", "engine": "v1", "original_label": "bullish", "canonical_direction": "BULLISH", "1D_realized_direction": "BULLISH"},
            {"article_id": 1, "split": "DEVELOPMENT", "engine": "v2", "original_label": "neutral", "canonical_direction": "NEUTRAL", "1D_realized_direction": "BULLISH"},
            {"article_id": 2, "split": "HOLDOUT", "engine": "v1", "original_label": "bearish", "canonical_direction": "BEARISH", "1D_realized_direction": "BULLISH"},
            {"article_id": 2, "split": "HOLDOUT", "engine": "v2", "original_label": "bullish", "canonical_direction": "BULLISH", "1D_realized_direction": "BULLISH"},
        ]
    )
    path = tmp_path / "rows.csv"
    rows.to_csv(path, index=False)

    metrics = evaluate_rows_by_split(path)

    assert set(metrics["engines"]) == {"DEVELOPMENT", "HOLDOUT"}
    assert metrics["engines"]["DEVELOPMENT"]["v1"]["strict_accuracy"] == 1.0
    assert metrics["engines"]["HOLDOUT"]["v2"]["strict_accuracy"] == 1.0


def test_baselines_and_paired_metrics_are_explicit() -> None:
    frame = pd.DataFrame(
        [
            {"article_id": 1, "engine": "v1", "original_label": "bullish", "1D_realized_direction": "BULLISH"},
            {"article_id": 1, "engine": "v2", "original_label": "neutral", "1D_realized_direction": "BULLISH"},
            {"article_id": 2, "engine": "v1", "original_label": "bearish", "1D_realized_direction": "BEARISH"},
            {"article_id": 2, "engine": "v2", "original_label": "bearish", "1D_realized_direction": "BEARISH"},
        ]
    )

    baselines = baseline_payload(frame, "1D")
    paired = paired_correctness_table(frame, "1D")

    assert {"ALWAYS_NEUTRAL", "MAJORITY_CLASS", "NEWS_DIRECTION_ONLY"}.issubset(baselines)
    assert paired["v1_correct_v2_wrong"] == 1
    assert paired["both_correct"] == 1


def test_mcnemar_reports_when_assumptions_are_weak() -> None:
    small = mcnemar_result(1, 0)
    large = mcnemar_result(12, 1)

    assert small["applicable"] is False
    assert large["applicable"] is True
    assert large["p_value_chi_square_approx"] is not None


def test_v2_parameter_registry_is_read_only() -> None:
    registry_payload = v2_parameter_registry()

    assert registry_payload["read_only"] is True
    assert registry_payload["news_weight"] == 0.55
    assert registry_payload["volume_behavior"].startswith("confirmation-only")


def test_diagnostic_and_case_exports_display_n_without_secrets(tmp_path: Path) -> None:
    with _session() as session:
        article = NewsArticle(
            ticker="AAPL",
            exchange="US",
            source="FNSPID",
            provider="fnspid",
            title="Apple item",
            summary="summary",
            url="https://example.test/aapl",
            published_at=datetime(2020, 6, 1),
            sentiment_label="bullish",
            sentiment_score=0.8,
            model_confidence=0.8,
            relevance_score=1.0,
            impact_strength=0.5,
            relevant=1,
            analysis_provider="finbert",
        )
        session.add(article)
        session.flush()
        rows = pd.DataFrame(
            [
                {"article_id": article.id, "instrument": "US:AAPL", "evaluation_timestamp": "2020-06-01", "split": "DEVELOPMENT", "engine": "v1", "engine_version": "1.0", "original_label": "bullish", "canonical_direction": "BULLISH", "signal_score": 0.6, "signal_confidence": 0.8, "signal_mode": "News-only signal", "data_quality": "UNASSESSED", "signal_run_id": None, "1D_return": 0.01, "1D_realized_direction": "BULLISH", "1D_correct": True, "1D_status": "VALID", "component_summary": None},
                {"article_id": article.id, "instrument": "US:AAPL", "evaluation_timestamp": "2020-06-01", "split": "DEVELOPMENT", "engine": "v2", "engine_version": "2.0", "original_label": "neutral", "canonical_direction": "NEUTRAL", "signal_score": 0.1, "signal_confidence": 0.5, "signal_mode": "NEWS_PLUS_MARKET", "data_quality": "UNASSESSED", "signal_run_id": None, "1D_return": 0.01, "1D_realized_direction": "BULLISH", "1D_correct": False, "1D_status": "VALID", "component_summary": json.dumps({"components": [], "warnings": [], "missing_inputs": []})},
            ]
        )
        rows_path = tmp_path / "rows.csv"
        rows.to_csv(rows_path, index=False)

        diagnostic = export_v2_diagnostic_from_rows(session, rows_path, tmp_path / "diagnostic.csv")
        cases = systematic_disagreement_cases(rows_path, tmp_path / "cases.csv")

        assert "finbert_label" in diagnostic.read_text(encoding="utf-8")
        assert "V1_CORRECT_V2_WRONG" in cases.read_text(encoding="utf-8")
        assert "api_key" not in diagnostic.read_text(encoding="utf-8").lower()
