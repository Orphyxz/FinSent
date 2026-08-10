from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Protocol

import pandas as pd

from finsent.app.services.model_comparison import classification_metrics
from finsent.app.services.phase13_research import (
    DEFAULT_PHASE12_ROWS,
    FINAL_HOLDOUT_DATASET_ID,
    FinalHoldoutEvaluationError,
    build_temporal_folds,
    to_jsonable,
)
from finsent.app.services.research_dataset import ResearchCohort, ResearchCohortConfig


PHASE14_OUTPUT_DIR = Path("output") / "research" / "phase14"
CALIBRATOR_VERSION = "signal_confidence_calibration_v1"
FINAL_HOLDOUT_V2_DATASET_ID = "phase14_final_holdout_v2"
FINAL_HOLDOUT_V2_STATUS = "FINAL_HOLDOUT_V2_LOCKED"
RETIRED_HOLDOUT_STATUS = "FINAL_HOLDOUT_RETIRED_UNEVALUATED"
DIRECTIONS = ("BULLISH", "NEUTRAL", "BEARISH")


@dataclass(frozen=True, slots=True)
class FinalHoldoutAdequacyPolicy:
    min_symbols: int = 3
    target_symbols: list[str] = field(default_factory=lambda: ["AAPL", "AMZN", "GOOGL", "NVDA", "TSLA"])
    min_eligible_per_represented_symbol: int = 20
    min_total_eligible: int = 90
    min_calendar_days: int = 14
    status: str = "preregistered_before_replacement_outcome_inspection"

    def evaluate(self, *, symbol_counts: dict[str, int], date_start: datetime | None, date_end: datetime | None) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        represented = {symbol: count for symbol, count in symbol_counts.items() if count > 0}
        if len(represented) < self.min_symbols:
            reasons.append("INSUFFICIENT_SYMBOL_DIVERSITY")
        if sum(represented.values()) < self.min_total_eligible:
            reasons.append("INSUFFICIENT_TOTAL_TECHNICAL_COVERAGE")
        too_small = {symbol: count for symbol, count in represented.items() if count < self.min_eligible_per_represented_symbol}
        if too_small:
            reasons.append("INSUFFICIENT_PER_SYMBOL_TECHNICAL_COVERAGE")
        if date_start is None or date_end is None:
            reasons.append("MISSING_DATE_WINDOW")
        elif (date_end.date() - date_start.date()).days + 1 < self.min_calendar_days:
            reasons.append("DATE_WINDOW_TOO_CLUSTERED")
        return not reasons, reasons


@dataclass(frozen=True, slots=True)
class FinalHoldoutV2Preregistration:
    dataset_id: str = FINAL_HOLDOUT_V2_DATASET_ID
    status: str = "PREREGISTERED_REPLACEMENT_CANDIDATE"
    source_name: str = "FNSPID"
    source_file: str = "Stock_news/nasdaq_exteral_data.csv"
    source_url: str = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv"
    sentiment_source: str = "Same FinBERT model/text policy used in Phase 12/13"
    price_source: str = "yahoo_chart_daily"
    price_basis: str = "Unadjusted Yahoo Finance chart quote.close"
    horizon: str = "1d"
    symbols: list[str] = field(default_factory=lambda: ["AAPL", "AMZN", "GOOGL", "NVDA", "TSLA"])
    start_date: datetime = datetime(2023, 1, 1)
    end_date: datetime = datetime(2023, 12, 31, 23, 59, 59)
    per_symbol_target: int = 30
    max_scan_rows: int = 30_000
    selection: str = "Bounded stratified per-symbol FNSPID scan using article, symbol, date, and price availability only."
    article_text_policy: str = "Identical to previous research; no fabricated summaries or changed FinBERT inputs."
    dedupe_policy: str = "Existing deterministic FNSPID source id/symbol/date/url/title hash and database URL uniqueness."
    event_study: str = "Event Study V2 unchanged; 1D technical eligibility only in Phase 14."
    realized_neutral_threshold: float = 0.001

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start_date"] = self.start_date.isoformat()
        payload["end_date"] = self.end_date.isoformat()
        payload["fingerprint"] = stable_fingerprint(payload)
        return payload


@dataclass(slots=True)
class CalibrationObservation:
    article_id: int
    timestamp: datetime
    raw_confidence: float
    correct: int
    split: str


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower: float
    upper: float
    n: int
    mean_confidence: float | None
    empirical_correctness: float | None
    calibration_gap: float | None


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    n: int
    brier: float | None
    ece: float | None
    mce: float | None
    reliability_bins: list[ReliabilityBin]


@dataclass(slots=True)
class CalibratorResult:
    method: str
    fold_metrics: list[dict[str, Any]]
    median_brier: float | None
    mean_brier: float | None
    median_ece: float | None
    median_mce: float | None
    selected: bool = False
    justified: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)


class SignalConfidenceCalibrator(Protocol):
    method: str

    def fit(self, observations: list[CalibrationObservation]) -> "SignalConfidenceCalibrator":
        ...

    def transform(self, raw_confidence: float) -> float:
        ...

    def parameters(self) -> dict[str, Any]:
        ...


class IdentityCalibrator:
    method = "identity"

    def fit(self, observations: list[CalibrationObservation]) -> "IdentityCalibrator":
        return self

    def transform(self, raw_confidence: float) -> float:
        return _clamp01(raw_confidence)

    def parameters(self) -> dict[str, Any]:
        return {"mapping": "raw_confidence"}


class BinnedCalibrator:
    method = "monotonic_binned_laplace"

    def __init__(self, *, bins: list[float] | None = None, min_bin_n: int = 10, prior: float = 0.5, prior_strength: float = 4.0) -> None:
        self.bins = bins or [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        self.min_bin_n = min_bin_n
        self.prior = prior
        self.prior_strength = prior_strength
        self.mapping: list[tuple[float, float, float]] = []
        self.global_rate = prior

    def fit(self, observations: list[CalibrationObservation]) -> "BinnedCalibrator":
        if not observations:
            self.mapping = [(self.bins[i], self.bins[i + 1], self.prior) for i in range(len(self.bins) - 1)]
            return self
        self.global_rate = sum(item.correct for item in observations) / len(observations)
        raw_values: list[float] = []
        for lower, upper in zip(self.bins[:-1], self.bins[1:], strict=True):
            bucket = [item for item in observations if lower <= item.raw_confidence < upper or (upper == 1.0 and item.raw_confidence == 1.0)]
            if len(bucket) < self.min_bin_n:
                value = (sum(item.correct for item in bucket) + self.global_rate * self.prior_strength) / (len(bucket) + self.prior_strength)
            else:
                value = (sum(item.correct for item in bucket) + self.prior * self.prior_strength) / (len(bucket) + self.prior_strength)
            raw_values.append(_clamp01(value))
        monotonic: list[float] = []
        current = 0.0
        for value in raw_values:
            current = max(current, value)
            monotonic.append(current)
        self.mapping = [(self.bins[i], self.bins[i + 1], monotonic[i]) for i in range(len(monotonic))]
        return self

    def transform(self, raw_confidence: float) -> float:
        value = _clamp01(raw_confidence)
        for lower, upper, calibrated in self.mapping:
            if lower <= value < upper or (upper == 1.0 and value == 1.0):
                return _clamp01(calibrated)
        return _clamp01(self.global_rate)

    def parameters(self) -> dict[str, Any]:
        return {"bins": self.bins, "min_bin_n": self.min_bin_n, "prior": self.prior, "prior_strength": self.prior_strength, "mapping": self.mapping}


class PlattCalibrator:
    method = "platt_logistic_l2"

    def __init__(self, *, iterations: int = 600, learning_rate: float = 0.05, l2: float = 1.0) -> None:
        self.iterations = iterations
        self.learning_rate = learning_rate
        self.l2 = l2
        self.a = 0.0
        self.b = 0.0
        self.fallback_rate = 0.5

    def fit(self, observations: list[CalibrationObservation]) -> "PlattCalibrator":
        if len(observations) < 20 or len({item.correct for item in observations}) < 2:
            self.fallback_rate = sum(item.correct for item in observations) / len(observations) if observations else 0.5
            self.a = 0.0
            self.b = _logit(self.fallback_rate)
            return self
        self.fallback_rate = sum(item.correct for item in observations) / len(observations)
        a = 0.0
        b = _logit(self.fallback_rate)
        n = len(observations)
        for _ in range(self.iterations):
            grad_a = self.l2 * a / n
            grad_b = 0.0
            for item in observations:
                x = _clamp01(item.raw_confidence)
                pred = _sigmoid(a * x + b)
                error = pred - item.correct
                grad_a += error * x / n
                grad_b += error / n
            a -= self.learning_rate * grad_a
            b -= self.learning_rate * grad_b
        self.a = a
        self.b = b
        return self

    def transform(self, raw_confidence: float) -> float:
        return _clamp01(_sigmoid(self.a * _clamp01(raw_confidence) + self.b))

    def parameters(self) -> dict[str, Any]:
        return {"a": self.a, "b": self.b, "iterations": self.iterations, "learning_rate": self.learning_rate, "l2": self.l2, "fallback_rate": self.fallback_rate}


def assert_not_final_holdout_v2(dataset_id: str | None, *, purpose: str, final_evaluation_mode: bool = False) -> None:
    if final_evaluation_mode:
        return
    if (dataset_id or "").strip() in {FINAL_HOLDOUT_DATASET_ID, FINAL_HOLDOUT_V2_DATASET_ID}:
        raise FinalHoldoutEvaluationError(f"Refusing to use {dataset_id} for {purpose}; final holdout performance is reserved for Phase 15.")


def load_calibration_observations(rows_csv: Path = DEFAULT_PHASE12_ROWS) -> list[CalibrationObservation]:
    frame = pd.read_csv(rows_csv)
    dev = frame[(frame["split"] == "DEVELOPMENT") & (frame["engine"] == "v2") & frame["1D_realized_direction"].notna()].copy()
    observations: list[CalibrationObservation] = []
    for _, row in dev.iterrows():
        observations.append(
            CalibrationObservation(
                article_id=int(row["article_id"]),
                timestamp=pd.to_datetime(row["evaluation_timestamp"]).to_pydatetime(),
                raw_confidence=_clamp01(float(row["signal_confidence"] or 0.0)),
                correct=1 if str(row["canonical_direction"]) == str(row["1D_realized_direction"]) else 0,
                split="DEVELOPMENT",
            )
        )
    observations.sort(key=lambda item: (item.timestamp, item.article_id))
    if len(observations) != 118:
        raise ValueError(f"Expected 118 development observations; found {len(observations)}.")
    return observations


def calibration_metrics(predictions: list[float], targets: list[int], *, bins: list[float] | None = None) -> CalibrationMetrics:
    if not predictions or not targets:
        return CalibrationMetrics(0, None, None, None, [])
    bins = bins or [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    pairs = [(_clamp01(pred), int(target)) for pred, target in zip(predictions, targets, strict=True)]
    brier = sum((pred - target) ** 2 for pred, target in pairs) / len(pairs)
    reliability: list[ReliabilityBin] = []
    ece = 0.0
    mce = 0.0
    for lower, upper in zip(bins[:-1], bins[1:], strict=True):
        bucket = [(pred, target) for pred, target in pairs if lower <= pred < upper or (upper == 1.0 and pred == 1.0)]
        if not bucket:
            reliability.append(ReliabilityBin(lower, upper, 0, None, None, None))
            continue
        mean_conf = sum(pred for pred, _ in bucket) / len(bucket)
        empirical = sum(target for _, target in bucket) / len(bucket)
        gap = abs(mean_conf - empirical)
        ece += (len(bucket) / len(pairs)) * gap
        mce = max(mce, gap)
        reliability.append(ReliabilityBin(lower, upper, len(bucket), mean_conf, empirical, gap))
    return CalibrationMetrics(len(pairs), brier, ece, mce, reliability)


def temporal_calibration_validation(observations: list[CalibrationObservation]) -> tuple[list[dict[str, Any]], list[CalibratorResult]]:
    frame = pd.DataFrame([asdict(item) for item in observations]).rename(columns={"timestamp": "evaluation_timestamp"})
    folds = build_temporal_folds(frame.assign(**{"1D_realized_direction": [item.correct for item in observations]}))
    calibrator_factories = [IdentityCalibrator, BinnedCalibrator, PlattCalibrator]
    results: list[CalibratorResult] = []
    for factory in calibrator_factories:
        fold_metrics: list[dict[str, Any]] = []
        last_parameters: dict[str, Any] = {}
        for fold in folds:
            train = observations[fold.train_start_index : fold.train_end_index]
            validation = observations[fold.validation_start_index : fold.validation_end_index]
            calibrator = factory().fit(train)
            predictions = [calibrator.transform(item.raw_confidence) for item in validation]
            targets = [item.correct for item in validation]
            metrics = calibration_metrics(predictions, targets)
            last_parameters = calibrator.parameters()
            fold_metrics.append({"fold_id": fold.fold_id, "n": len(validation), **metrics_to_dict(metrics)})
        briers = [item["brier"] for item in fold_metrics if item["brier"] is not None]
        eces = [item["ece"] for item in fold_metrics if item["ece"] is not None]
        mces = [item["mce"] for item in fold_metrics if item["mce"] is not None]
        results.append(
            CalibratorResult(
                method=factory().method,
                fold_metrics=fold_metrics,
                median_brier=float(median(briers)) if briers else None,
                mean_brier=float(mean(briers)) if briers else None,
                median_ece=float(median(eces)) if eces else None,
                median_mce=float(median(mces)) if mces else None,
                parameters=last_parameters,
            )
        )
    selected = select_calibrator(results)
    return [asdict(fold) for fold in folds], results


def select_calibrator(results: list[CalibratorResult]) -> CalibratorResult:
    identity = next(result for result in results if result.method == "identity")
    ranked = sorted(results, key=lambda item: (_none_to_large(item.median_brier), _none_to_large(item.median_ece), item.method != "identity", item.method))
    selected = ranked[0]
    selected.selected = True
    improvement = _none_to_large(identity.median_brier) - _none_to_large(selected.median_brier)
    selected.justified = selected.method != "identity" and improvement >= 0.005 and _none_to_large(selected.median_ece) <= _none_to_large(identity.median_ece)
    if not selected.justified:
        for result in results:
            result.selected = result.method == "identity"
            result.justified = False
        selected = identity
    return selected


def fit_selected_calibrator(method: str, observations: list[CalibrationObservation]) -> SignalConfidenceCalibrator:
    if method == "monotonic_binned_laplace":
        return BinnedCalibrator().fit(observations)
    if method == "platt_logistic_l2":
        return PlattCalibrator().fit(observations)
    return IdentityCalibrator().fit(observations)


def raw_calibration_analysis(observations: list[CalibrationObservation]) -> CalibrationMetrics:
    return calibration_metrics([item.raw_confidence for item in observations], [item.correct for item in observations])


def retire_holdout_if_inadequate(existing_lock: dict[str, Any], policy: FinalHoldoutAdequacyPolicy, output_path: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for instrument in existing_lock.get("instruments", []):
        symbol = str(instrument).split(":")[-1]
        counts[symbol] = int(existing_lock.get("coverage_summary", {}).get("horizons", {}).get("1D", {}).get("eligible", 0))
    date_start = _parse_dt(existing_lock.get("date_start"))
    date_end = _parse_dt(existing_lock.get("date_end"))
    adequate, reasons = policy.evaluate(symbol_counts=counts, date_start=date_start, date_end=date_end)
    payload = {
        "previous_dataset_id": existing_lock.get("dataset_id"),
        "previous_fingerprint": existing_lock.get("cohort_fingerprint"),
        "previous_article_ids": existing_lock.get("article_ids", []),
        "previous_instruments": existing_lock.get("instruments", []),
        "previous_date_start": existing_lock.get("date_start"),
        "previous_date_end": existing_lock.get("date_end"),
        "previous_coverage_summary": existing_lock.get("coverage_summary", {}),
        "adequate": adequate,
        "status": existing_lock.get("status") if adequate else RETIRED_HOLDOUT_STATUS,
        "retirement_reason": None if adequate else " / ".join(reasons),
        "performance_evaluated": False,
        "retired_at": utc_now().isoformat() if not adequate else None,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    return payload


def replacement_holdout_status(cohort: ResearchCohort, policy: FinalHoldoutAdequacyPolicy, output_path: Path, *, source_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for sample in cohort.samples:
        eligible = sample.coverage.get("1D").valid if sample.coverage.get("1D") else False
        if eligible:
            counts[sample.instrument.ticker] = counts.get(sample.instrument.ticker, 0) + 1
    dates = [sample.published_at for sample in cohort.samples if sample.coverage.get("1D") and sample.coverage["1D"].valid]
    adequate, reasons = policy.evaluate(symbol_counts=counts, date_start=min(dates) if dates else None, date_end=max(dates) if dates else None)
    payload = {
        "dataset_id": FINAL_HOLDOUT_V2_DATASET_ID,
        "status": FINAL_HOLDOUT_V2_STATUS if adequate else "FINAL_HOLDOUT_NOT_READY",
        "cohort_fingerprint": cohort.fingerprint,
        "performance_evaluated": False,
        "article_ids": [sample.article_id for sample in cohort.samples],
        "instruments": sorted({f"{sample.instrument.exchange}:{sample.instrument.ticker}" for sample in cohort.samples}),
        "symbol_eligible_counts": counts,
        "date_start": min(dates).isoformat() if dates else None,
        "date_end": max(dates).isoformat() if dates else None,
        "candidate_n": len(cohort.samples),
        "technically_eligible_n": sum(counts.values()),
        "adequacy_passed": adequate,
        "blockers": reasons,
        "coverage_summary": cohort.coverage_summary,
        "source_manifest": source_manifest or {},
        "locked_at": utc_now().isoformat() if adequate else None,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    return payload


def calibrator_config(method: str, calibrator: SignalConfidenceCalibrator, observations: list[CalibrationObservation], results: list[CalibratorResult]) -> dict[str, Any]:
    selected = next(result for result in results if result.selected)
    return {
        "version": CALIBRATOR_VERSION,
        "status": "FROZEN_RESEARCH_CALIBRATOR" if selected.justified else "NO_CALIBRATION_JUSTIFIED_IDENTITY_SELECTED",
        "parent_engine_name": "finsent_composite",
        "parent_engine_version": "2.0",
        "target": "strict empirical signal correctness on Phase 12 DEVELOPMENT rows",
        "training_cohort_fingerprint": stable_fingerprint([asdict(item) for item in observations]),
        "method": method,
        "parameters": calibrator.parameters(),
        "metrics": [asdict(result) for result in results],
        "created_at": utc_now().isoformat(),
    }


def render_calibration_report(path: Path, *, observations: list[CalibrationObservation], raw: CalibrationMetrics, folds: list[dict[str, Any]], results: list[CalibratorResult], config: dict[str, Any], final_status: dict[str, Any]) -> Path:
    lines = [
        "# Signal V2 Confidence Calibration",
        "",
        "## Confidence Semantics",
        "Raw confidence remains an engineering reliability score. Calibrated reliability, if justified, estimates empirical signal correctness on development data; it is not probability of price increase or profit.",
        "",
        "## Development Cohort",
        f"N = {len(observations)} Phase 12 DEVELOPMENT observations.",
        "",
        "## Temporal Folds",
        json.dumps(to_jsonable(folds), indent=2, sort_keys=True),
        "",
        "## Raw Calibration",
        json.dumps(metrics_to_dict(raw), indent=2, sort_keys=True),
        "",
        "## Candidate Methods",
        ", ".join(result.method for result in results),
        "",
        "## Brier Score",
        json.dumps({result.method: result.median_brier for result in results}, indent=2, sort_keys=True),
        "",
        "## ECE",
        json.dumps({result.method: result.median_ece for result in results}, indent=2, sort_keys=True),
        "",
        "## MCE",
        json.dumps({result.method: result.median_mce for result in results}, indent=2, sort_keys=True),
        "",
        "## Selected Method",
        json.dumps(to_jsonable(config), indent=2, sort_keys=True),
        "",
        "## Calibration Mapping",
        json.dumps(to_jsonable(config.get("parameters", {})), indent=2, sort_keys=True),
        "",
        "## Limitations",
        "N=118 is small. Calibration is not a true market probability and does not change direction scores or labels.",
        "",
        "## Observed Validation if used",
        "Skipped in Phase 14.",
        "",
        "## Final Holdout Status",
        json.dumps(to_jsonable(final_status), indent=2, sort_keys=True),
        "",
        "## What Cannot Yet Be Claimed",
        "Do not claim production calibration, profitability, or final generalization before Phase 15.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_holdout_report(path: Path, *, retired: dict[str, Any], preregistration: FinalHoldoutV2Preregistration, replacement: dict[str, Any]) -> Path:
    lines = [
        "# Final Holdout Preparation",
        "",
        "PERFORMANCE NOT EVALUATED.",
        "",
        "## Retired Holdout",
        json.dumps(to_jsonable(retired), indent=2, sort_keys=True),
        "",
        "## Replacement Preregistration",
        json.dumps(preregistration.to_dict(), indent=2, sort_keys=True),
        "",
        "## Replacement Candidate",
        json.dumps(to_jsonable(replacement), indent=2, sort_keys=True),
        "",
        "## Lock Status",
        replacement.get("status", "UNKNOWN"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_phase14_docs(policy: FinalHoldoutAdequacyPolicy, prereg: FinalHoldoutV2Preregistration, config: dict[str, Any]) -> list[Path]:
    docs = {
        Path("docs") / "FINAL_HOLDOUT_ADEQUACY_POLICY.md": ["# Final Holdout Adequacy Policy", "", json.dumps(asdict(policy), indent=2, sort_keys=True)],
        Path("docs") / "FINAL_HOLDOUT_V2_PREREGISTRATION.md": ["# Final Holdout V2 Preregistration", "", json.dumps(prereg.to_dict(), indent=2, sort_keys=True), "", "No performance values may influence this selection."],
        Path("docs") / "CONFIDENCE_CALIBRATION.md": ["# Confidence Calibration", "", json.dumps(to_jsonable(config), indent=2, sort_keys=True)],
        Path("docs") / "PHASE14_RESEARCH_PROTOCOL.md": ["# Phase 14 Research Protocol", "", "Use Phase 12 DEVELOPMENT only for calibration. Retire inadequate holdouts structurally. Do not evaluate final-holdout performance."],
    }
    written: list[Path] = []
    for path, lines in docs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)
    return written


def metrics_to_dict(metrics: CalibrationMetrics) -> dict[str, Any]:
    return {
        "n": metrics.n,
        "brier": metrics.brier,
        "ece": metrics.ece,
        "mce": metrics.mce,
        "reliability_bins": [asdict(item) for item in metrics.reliability_bins],
    }


def stable_fingerprint(payload: Any) -> str:
    return sha256(json.dumps(to_jsonable(payload), sort_keys=True).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _logit(value: float) -> float:
    value = max(1e-6, min(1 - 1e-6, value))
    return math.log(value / (1 - value))


def _none_to_large(value: float | None) -> float:
    return value if value is not None else 999.0


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
