from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluationConfig, HistoricalSignalEvaluator
from finsent.app.services.phase13_research import (
    DEFAULT_PHASE12_ROWS,
    FINAL_HOLDOUT_DATASET_ID,
    FinalHoldoutEvaluationError,
    SignalV2Candidate,
    SignalV2ParameterSearch,
    assert_not_final_holdout,
    build_temporal_folds,
    degeneracy_status,
    generate_candidate_grid,
    load_development_rows,
    recompute_candidate,
    write_final_holdout_preregistration,
    FinalHoldoutPreregistration,
)
from finsent.app.services.research_dataset import ResearchCohortConfig
from finsent.app.services.signal_engine_v2 import SignalEngineV2Config, V2_0_CONFIG, validate_signal_v2_config


def test_v2_0_cached_recombination_matches_phase12_rows() -> None:
    rows = load_development_rows(DEFAULT_PHASE12_ROWS)
    candidate = SignalV2Candidate(
        "v2_0_reference",
        V2_0_CONFIG.news_weight,
        V2_0_CONFIG.momentum_weight,
        V2_0_CONFIG.volume_confirmation_weight,
        V2_0_CONFIG.directional_threshold,
    )

    for _, row in rows.iterrows():
        score, direction = recompute_candidate(row, candidate)
        assert score == pytest.approx(float(row["signal_score"]), abs=1e-12)
        assert direction == row["canonical_direction"]


def test_v2_config_validation_accepts_v2_0_and_rejects_invalid_values() -> None:
    validate_signal_v2_config(V2_0_CONFIG)
    validate_signal_v2_config(SignalEngineV2Config(news_weight=0.55, momentum_weight=0.45, volume_confirmation_weight=0.0, directional_threshold=0.15))

    with pytest.raises(ValueError):
        validate_signal_v2_config(SignalEngineV2Config(news_weight=0.8, momentum_weight=0.3, volume_confirmation_weight=0.0))
    with pytest.raises(ValueError):
        validate_signal_v2_config(SignalEngineV2Config(news_weight=0.5, momentum_weight=0.3, volume_confirmation_weight=0.2))
    with pytest.raises(ValueError):
        validate_signal_v2_config(SignalEngineV2Config(news_weight=0.5, momentum_weight=0.4, volume_confirmation_weight=0.1, directional_threshold=0.6))


def test_candidate_grid_is_modest_and_preserves_v2_0_reference() -> None:
    grid = generate_candidate_grid()
    assert 10 < len(grid) < 150
    assert any(candidate.candidate_id == "v2_0_reference" for candidate in grid)
    for candidate in grid:
        validate_signal_v2_config(candidate.config())
        assert candidate.volume_weight <= 0.15


def test_temporal_folds_are_chronological_non_overlapping_and_deterministic() -> None:
    frame = _synthetic_rows(32)
    folds = build_temporal_folds(frame)
    assert folds == build_temporal_folds(frame)
    for fold in folds:
        assert set(fold.train_article_ids).isdisjoint(fold.validation_article_ids)
        assert fold.train_end_index == fold.validation_start_index
        assert fold.train_end_index <= fold.validation_start_index
        assert fold.validation_start_index < fold.validation_end_index


def test_parameter_search_selects_known_best_candidate() -> None:
    frame = _synthetic_rows(32)
    low_threshold = SignalV2Candidate("known_best", 1.0, 0.0, 0.0, 0.10)
    high_threshold = SignalV2Candidate("known_worse", 1.0, 0.0, 0.0, 0.30)

    results = SignalV2ParameterSearch(frame, candidates=[high_threshold, low_threshold]).run()
    selected = next(result for result in results if result.selected)

    assert selected.candidate.candidate_id == "known_best"
    assert selected.median_balanced_accuracy == pytest.approx(1.0)
    assert selected.degenerate is False


def test_degenerate_candidate_rejection() -> None:
    degenerate, reason = degeneracy_status(["NEUTRAL"] * 20, ["BULLISH", "BEARISH"] * 10)
    assert degenerate is True
    assert reason == "DIRECTIONAL_PREDICTION_RATE_BELOW_20_PERCENT"


def test_final_holdout_guard_rejects_normal_evaluation() -> None:
    with pytest.raises(FinalHoldoutEvaluationError):
        assert_not_final_holdout(FINAL_HOLDOUT_DATASET_ID, purpose="grid search")

    evaluator = HistoricalSignalEvaluator(session=None)  # type: ignore[arg-type]
    config = HistoricalSignalEvaluationConfig(cohort=ResearchCohortConfig(dataset_id=FINAL_HOLDOUT_DATASET_ID))
    with pytest.raises(RuntimeError, match="FINAL_HOLDOUT_LOCKED"):
        evaluator.dry_run(config)


def test_final_holdout_preregistration_marks_unevaluated(tmp_path: Path) -> None:
    path = write_final_holdout_preregistration(tmp_path / "FINAL_HOLDOUT_PREREGISTRATION.md", FinalHoldoutPreregistration())
    text = path.read_text(encoding="utf-8")
    assert "FINAL_HOLDOUT_LOCKED" in text
    assert "Forbidden in Phase 13" in text
    assert "accuracy" in text
    assert "api_key" not in text.lower()
    assert "secret" not in text.lower()


def _synthetic_rows(count: int) -> pd.DataFrame:
    start = datetime(2020, 1, 1)
    rows = []
    for index in range(count):
        direction = "BULLISH" if index % 2 == 0 else "BEARISH"
        value = 0.25 if direction == "BULLISH" else -0.25
        rows.append(
            {
                "article_id": index + 1,
                "evaluation_timestamp": start + timedelta(days=index),
                "1D_realized_direction": direction,
                "original_label": "neutral",
                "canonical_direction": "NEUTRAL",
                "signal_score": 0.0,
                "news_available": True,
                "news_normalized": value,
                "price_momentum_available": False,
                "price_momentum_normalized": 0.0,
                "volume_confirmation_available": False,
                "volume_confirmation_normalized": 0.0,
                "liquidity_reliability": 1.0,
                "freshness_reliability": 1.0,
                "data_quality_reliability": 1.0,
            }
        )
    return pd.DataFrame(rows)
