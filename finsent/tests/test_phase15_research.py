from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from finsent.app.services.historical_news_acquisition import HistoricalArticleRecord
from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluationConfig, HistoricalSignalEvaluator
from finsent.app.services.phase15_research import (
    FINAL_HOLDOUT_V3_DATASET_ID,
    FinalHoldoutV3Preregistration,
    assert_not_final_holdout_v3,
    evenly_spaced,
    select_records_for_window,
    select_window,
    stable_fingerprint,
)
from finsent.app.services.research_dataset import CoverageByHorizon, ResearchCohort, ResearchCohortConfig, ResearchCohortSample
from finsent.app.services.symbol_registry import registry


def test_grouped_source_old_global_cap_monopolizes_but_stratified_selection_balances() -> None:
    records = {
        "AAPL": _records("AAPL", 30),
        "AMZN": _records("AMZN", 30),
        "NVDA": _records("NVDA", 30),
        "TSLA": _records("TSLA", 30),
    }
    grouped = records["AAPL"] + records["AMZN"] + records["NVDA"] + records["TSLA"]
    old_first_n = grouped[:40]
    assert _counts(old_first_n) == {"AAPL": 30, "AMZN": 10}

    prereg = FinalHoldoutV3Preregistration(per_symbol_quota=10, minimum_total_eligible=30)
    selection = select_window(records, prereg)
    selected = select_records_for_window(records, selection, prereg)
    assert _counts(selected) == {"AAPL": 10, "AMZN": 10, "NVDA": 10, "TSLA": 10}


def test_window_selection_chooses_earliest_adequate_window_not_later_larger_one() -> None:
    prereg = FinalHoldoutV3Preregistration(
        availability_start=datetime(2023, 1, 1),
        availability_end=datetime(2023, 6, 30, 23, 59, 59),
        window_days=30,
        minimum_symbols=3,
        minimum_per_symbol_eligible=20,
        minimum_total_eligible=60,
    )
    records = {
        "AAPL": _records("AAPL", 30, start=datetime(2023, 1, 1)),
        "AMZN": _records("AMZN", 30, start=datetime(2023, 1, 1)),
        "NVDA": _records("NVDA", 30, start=datetime(2023, 1, 1)),
        "TSLA": _records("TSLA", 80, start=datetime(2023, 4, 1)),
    }
    selection = select_window(records, prereg)
    assert selection.adequate is True
    assert selection.start_date == datetime(2023, 1, 1)


def test_one_scarce_symbol_does_not_block_three_symbol_adequacy() -> None:
    prereg = FinalHoldoutV3Preregistration(minimum_symbols=3, minimum_per_symbol_eligible=20, minimum_total_eligible=60)
    records = {
        "AAPL": _records("AAPL", 5),
        "AMZN": _records("AMZN", 25),
        "NVDA": _records("NVDA", 25),
        "TSLA": _records("TSLA", 25),
    }
    selection = select_window(records, prereg)
    assert selection.adequate is True
    assert selection.represented_symbols == ["AMZN", "NVDA", "TSLA"]


def test_evenly_spaced_selection_is_deterministic() -> None:
    records = _records("AAPL", 11)
    selected = evenly_spaced(records, 4)
    assert [record.source_record_id for record in selected] == ["AAPL-0", "AAPL-3", "AAPL-7", "AAPL-10"]
    assert selected == evenly_spaced(records, 4)


def test_fingerprint_is_stable_without_machine_paths() -> None:
    payload = {"dataset_id": FINAL_HOLDOUT_V3_DATASET_ID, "article_ids": [3, 1, 2], "symbols": ["AMZN"]}
    assert stable_fingerprint(payload) == stable_fingerprint(payload)


def test_locked_final_holdout_v3_guard_blocks_historical_evaluator() -> None:
    with pytest.raises(Exception, match="Phase 15"):
        assert_not_final_holdout_v3(FINAL_HOLDOUT_V3_DATASET_ID, purpose="signal evaluation")

    evaluator = HistoricalSignalEvaluator(session=None)  # type: ignore[arg-type]
    config = HistoricalSignalEvaluationConfig(cohort=ResearchCohortConfig(dataset_id=FINAL_HOLDOUT_V3_DATASET_ID))
    with pytest.raises(RuntimeError, match="FINAL_HOLDOUT_LOCKED"):
        evaluator.dry_run(config)


def test_technical_coverage_fixture_contains_no_performance_summary() -> None:
    sample = ResearchCohortSample(
        article_id=1,
        instrument=registry.get("US", "AMZN"),
        published_at=datetime(2023, 1, 3),
        title="title",
        dedupe_key="d",
        split="DEVELOPMENT",
        coverage={"1D": CoverageByHorizon("1D", True, "VALID")},
        status="ELIGIBLE",
    )
    cohort = ResearchCohort(
        config=ResearchCohortConfig(dataset_id=FINAL_HOLDOUT_V3_DATASET_ID),
        samples=[sample],
        excluded_count=0,
        exclusion_counts={},
        coverage_summary={"horizons": {"1D": {"eligible": 1}}},
        fingerprint="abc",
    )
    assert cohort.coverage_summary["horizons"]["1D"]["eligible"] == 1
    assert "raw_return" not in cohort.coverage_summary
    assert "realized_direction" not in cohort.coverage_summary


def _records(symbol: str, count: int, *, start: datetime = datetime(2023, 1, 1)) -> list[HistoricalArticleRecord]:
    rows = []
    for index in range(count):
        dt = start + timedelta(days=index % 30)
        rows.append(
            HistoricalArticleRecord(
                source_record_id=f"{symbol}-{index}",
                published_at=dt,
                symbol=symbol,
                title=f"{symbol} headline {index}",
                summary=None,
                url=f"https://example.com/{symbol}/{index}",
                publisher="FNSPID",
                source_dataset="fnspid",
                source_file="Stock_news/nasdaq_exteral_data.csv",
                dedupe_hash=f"{symbol}-{index}",
                canonical_text_hash=f"text-{symbol}-{index}",
            )
        )
    return rows


def _counts(records: list[HistoricalArticleRecord]) -> dict[str, int]:
    counts = {}
    for record in records:
        counts[record.symbol] = counts.get(record.symbol, 0) + 1
    return counts
