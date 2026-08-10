from __future__ import annotations

from datetime import datetime

import pytest

from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluationConfig, HistoricalSignalEvaluator
from finsent.app.services.phase14_research import (
    BinnedCalibrator,
    CalibrationObservation,
    FINAL_HOLDOUT_V2_DATASET_ID,
    FinalHoldoutAdequacyPolicy,
    IdentityCalibrator,
    PlattCalibrator,
    assert_not_final_holdout_v2,
    calibration_metrics,
    load_calibration_observations,
    raw_calibration_analysis,
    retire_holdout_if_inadequate,
    temporal_calibration_validation,
)
from finsent.app.services.research_dataset import ResearchCohortConfig


def test_calibration_metrics_perfect_and_miscalibrated_examples() -> None:
    perfect = calibration_metrics([0.0, 1.0], [0, 1])
    assert perfect.brier == pytest.approx(0.0)
    assert perfect.ece == pytest.approx(0.0)
    assert perfect.mce == pytest.approx(0.0)

    overconfident = calibration_metrics([0.9, 0.9], [0, 0])
    assert overconfident.brier == pytest.approx(0.81)
    assert overconfident.ece == pytest.approx(0.9)
    assert overconfident.mce == pytest.approx(0.9)

    empty = calibration_metrics([], [])
    assert empty.n == 0
    assert empty.brier is None


def test_identity_and_binned_calibrators_are_bounded_and_stable() -> None:
    observations = _observations()
    identity = IdentityCalibrator().fit(observations)
    assert identity.transform(1.5) == 1.0
    assert identity.transform(-1.0) == 0.0

    binned = BinnedCalibrator(min_bin_n=2).fit(observations)
    values = [binned.transform(value / 10) for value in range(11)]
    assert all(0.0 <= value <= 1.0 for value in values)
    assert values == sorted(values)


def test_platt_calibrator_handles_small_sample_and_bounds_values() -> None:
    calibrator = PlattCalibrator(iterations=20).fit(_observations())
    assert 0.0 <= calibrator.transform(0.25) <= 1.0
    assert 0.0 <= calibrator.transform(0.75) <= 1.0


def test_temporal_calibration_uses_development_only_and_no_future_leakage() -> None:
    observations = load_calibration_observations()
    folds, results = temporal_calibration_validation(observations)

    assert len(observations) == 118
    assert all(item.split == "DEVELOPMENT" for item in observations)
    for fold in folds:
        assert fold["train_end_index"] == fold["validation_start_index"]
        assert set(fold["train_article_ids"]).isdisjoint(fold["validation_article_ids"])
    assert {result.method for result in results} == {"identity", "monotonic_binned_laplace", "platt_logistic_l2"}


def test_raw_calibration_does_not_change_direction_outputs() -> None:
    observations = load_calibration_observations()
    raw = raw_calibration_analysis(observations)
    transformed = [IdentityCalibrator().transform(item.raw_confidence) for item in observations]

    assert raw.n == 118
    assert transformed == [item.raw_confidence for item in observations]


def test_holdout_adequacy_retire_aapl_only_without_evaluation(tmp_path) -> None:
    policy = FinalHoldoutAdequacyPolicy()
    lock = {
        "dataset_id": "phase13_final_holdout_v1",
        "status": "FINAL_HOLDOUT_LOCKED",
        "cohort_fingerprint": "abc",
        "article_ids": list(range(30)),
        "instruments": ["US:AAPL"],
        "date_start": "2023-12-12T00:00:00",
        "date_end": "2023-12-13T00:00:00",
        "coverage_summary": {"horizons": {"1D": {"eligible": 30}}},
    }

    retired = retire_holdout_if_inadequate(lock, policy, tmp_path / "retired.json")

    assert retired["adequate"] is False
    assert retired["status"] == "FINAL_HOLDOUT_RETIRED_UNEVALUATED"
    assert "INSUFFICIENT_SYMBOL_DIVERSITY" in retired["retirement_reason"]
    assert retired["performance_evaluated"] is False


def test_holdout_adequacy_passes_multisymbol_sufficient_window() -> None:
    policy = FinalHoldoutAdequacyPolicy()
    adequate, reasons = policy.evaluate(
        symbol_counts={"AAPL": 30, "AMZN": 30, "GOOGL": 30},
        date_start=datetime(2023, 1, 1),
        date_end=datetime(2023, 2, 1),
    )
    assert adequate is True
    assert reasons == []


def test_final_holdout_v2_guard_blocks_normal_evaluation() -> None:
    with pytest.raises(Exception, match="final holdout"):
        assert_not_final_holdout_v2(FINAL_HOLDOUT_V2_DATASET_ID, purpose="calibration check")

    evaluator = HistoricalSignalEvaluator(session=None)  # type: ignore[arg-type]
    config = HistoricalSignalEvaluationConfig(cohort=ResearchCohortConfig(dataset_id=FINAL_HOLDOUT_V2_DATASET_ID))
    with pytest.raises(RuntimeError, match="FINAL_HOLDOUT_LOCKED"):
        evaluator.dry_run(config)


def _observations() -> list[CalibrationObservation]:
    return [
        CalibrationObservation(1, datetime(2020, 1, 1), 0.1, 0, "DEVELOPMENT"),
        CalibrationObservation(2, datetime(2020, 1, 2), 0.2, 0, "DEVELOPMENT"),
        CalibrationObservation(3, datetime(2020, 1, 3), 0.8, 1, "DEVELOPMENT"),
        CalibrationObservation(4, datetime(2020, 1, 4), 0.9, 1, "DEVELOPMENT"),
    ]
