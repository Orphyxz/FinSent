from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.database.entities import EventStudyResult, NewsArticle, SentimentAnalysisRun
from finsent.app.services.historical_signal_evaluation import signal_direction
from finsent.app.services.model_comparison import classification_metrics
from finsent.app.services.research_dataset import ResearchCohort, ResearchCohortConfig
from finsent.app.services.signal_engine_v2 import (
    ENGINE_NAME_V2,
    ENGINE_VERSION_V2,
    ENGINE_VERSION_V2_1_RESEARCH,
    SignalEngineV2Config,
    V2_0_CONFIG,
    clamp,
    score_label,
    validate_signal_v2_config,
)


PHASE13_EXPERIMENT_ID = "phase13_development_tuning_v1"
FINAL_HOLDOUT_DATASET_ID = "phase13_final_holdout_v1"
FINAL_HOLDOUT_STATUS = "FINAL_HOLDOUT_LOCKED"
OBSERVED_VALIDATION_LABEL = "OBSERVED_VALIDATION"
PHASE12_FINGERPRINT = "b6299de35bd8bbd6ab88b2d071329e1dba227f356f07597c9081489fbe217db2"
DEFAULT_PHASE12_ROWS = Path("output") / "research" / "phase12" / "5" / "signal_evaluation_rows.csv"
DEFAULT_PHASE13_DIR = Path("output") / "research" / "phase13" / PHASE13_EXPERIMENT_ID
DIRECTIONS = ("BULLISH", "NEUTRAL", "BEARISH")


class FinalHoldoutEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FinalHoldoutPreregistration:
    dataset_id: str = FINAL_HOLDOUT_DATASET_ID
    status: str = FINAL_HOLDOUT_STATUS
    requested_symbols: list[str] = field(default_factory=lambda: ["AAPL", "AMZN", "GOOGL", "NVDA", "TSLA"])
    locked_symbols: list[str] = field(default_factory=lambda: ["AAPL"])
    markets: list[str] = field(default_factory=lambda: ["US"])
    start_date: datetime = datetime(2023, 11, 1)
    end_date: datetime = datetime(2023, 12, 13, 23, 59, 59)
    source_name: str = "FNSPID"
    source_file: str = "Stock_news/nasdaq_exteral_data.csv"
    source_url: str = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv"
    per_symbol_target: int = 30
    article_cap: int = 150
    max_scan_rows: int = 100_000
    price_source: str = "yahoo_chart_daily"
    price_basis: str = "Unadjusted Yahoo Finance chart quote.close"
    sentiment_source: str = "FinBERT only; not run on the final holdout in Phase 13"
    horizon: str = "1d"
    selection_method: str = "Bounded deterministic FNSPID scan using article and price availability only; no model-performance criteria."
    data_availability_note: str = (
        "The same five Phase 12 symbols were requested. The smaller All_external.csv source yielded no post-2020-06-15 rows "
        "in a bounded scan, and the larger Nasdaq FNSPID source is too large to exhaustively scan for all five symbols in Phase 13. "
        "AAPL-only locking is therefore a documented data-availability/feasibility limitation, not symbol cherry-picking."
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start_date"] = self.start_date.isoformat()
        payload["end_date"] = self.end_date.isoformat()
        payload["fingerprint"] = stable_fingerprint(payload)
        return payload


@dataclass(frozen=True, slots=True)
class SignalV2Candidate:
    candidate_id: str
    news_weight: float
    momentum_weight: float
    volume_weight: float
    directional_threshold: float

    def config(self) -> SignalEngineV2Config:
        config = SignalEngineV2Config(
            news_weight=self.news_weight,
            momentum_weight=self.momentum_weight,
            volume_confirmation_weight=self.volume_weight,
            directional_threshold=self.directional_threshold,
        )
        validate_signal_v2_config(config)
        return config

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def distance_from_v2_0(self) -> float:
        return (
            abs(self.news_weight - V2_0_CONFIG.news_weight)
            + abs(self.momentum_weight - V2_0_CONFIG.momentum_weight)
            + abs(self.volume_weight - V2_0_CONFIG.volume_confirmation_weight)
            + abs(self.directional_threshold - V2_0_CONFIG.directional_threshold)
        )


@dataclass(frozen=True, slots=True)
class TemporalFold:
    fold_id: str
    train_start_index: int
    train_end_index: int
    validation_start_index: int
    validation_end_index: int
    train_article_ids: list[int]
    validation_article_ids: list[int]
    validation_start: str
    validation_end: str


@dataclass(slots=True)
class CandidateFoldResult:
    candidate_id: str
    fold_id: str
    n: int
    balanced_accuracy: float | None
    macro_f1: float | None
    strict_accuracy: float | None
    directional_accuracy: float | None
    coverage: float
    prediction_distribution: dict[str, int]
    realized_distribution: dict[str, int]


@dataclass(slots=True)
class CandidateSearchResult:
    candidate: SignalV2Candidate
    folds: list[CandidateFoldResult]
    median_balanced_accuracy: float | None
    mean_balanced_accuracy: float | None
    worst_fold_balanced_accuracy: float | None
    std_balanced_accuracy: float | None
    mean_macro_f1: float | None
    degenerate: bool
    degeneracy_reason: str | None
    selected: bool = False
    justified: bool = False


def stable_fingerprint(payload: Any) -> str:
    return sha256(json.dumps(to_jsonable(payload), sort_keys=True).encode("utf-8")).hexdigest()


def assert_not_final_holdout(dataset_id: str | None, *, purpose: str, final_evaluation_mode: bool = False) -> None:
    if final_evaluation_mode:
        return
    if (dataset_id or "").strip() == FINAL_HOLDOUT_DATASET_ID:
        raise FinalHoldoutEvaluationError(
            f"Refusing to use {FINAL_HOLDOUT_DATASET_ID} for {purpose}. "
            "It is FINAL_HOLDOUT_LOCKED and requires an explicit future final-evaluation mode."
        )


def guard_cohort(config: ResearchCohortConfig, *, purpose: str, final_evaluation_mode: bool = False) -> None:
    assert_not_final_holdout(config.dataset_id, purpose=purpose, final_evaluation_mode=final_evaluation_mode)


def write_final_holdout_preregistration(path: Path, preregistration: FinalHoldoutPreregistration) -> Path:
    data = preregistration.to_dict()
    lines = [
        "# Final Holdout Preregistration",
        "",
        "Status: `FINAL_HOLDOUT_LOCKED`",
        "",
        f"Dataset id: `{data['dataset_id']}`",
        f"Fingerprint: `{data['fingerprint']}`",
        "",
        "This cohort is reserved for a later explicit final evaluation. Phase 13 may check technical price coverage only.",
        "",
        "```json",
        json.dumps(data, indent=2, sort_keys=True),
        "```",
        "",
        "Forbidden in Phase 13: Signal V1/V2/V2.1 accuracy, balanced accuracy, confusion matrices, realized-direction summaries, and candidate filtering.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def freeze_phase12_artifact_reference(rows_csv: Path, output_path: Path) -> dict[str, Any]:
    frame = pd.read_csv(rows_csv)
    valid = frame[frame["1D_realized_direction"].notna()].copy()
    development = valid[valid["split"] == "DEVELOPMENT"]
    observed = valid[valid["split"] == "HOLDOUT"]
    payload = {
        "phase": 13,
        "phase12_conceptual_rename": {"HOLDOUT": OBSERVED_VALIDATION_LABEL},
        "phase12_cohort_fingerprint": PHASE12_FINGERPRINT,
        "source_rows_csv": str(rows_csv),
        "source_rows_sha256": file_sha256(rows_csv),
        "valid_1d_observations": int(valid.drop_duplicates("article_id").shape[0]),
        "development_article_ids": sorted(int(value) for value in development["article_id"].drop_duplicates()),
        "observed_validation_article_ids": sorted(int(value) for value in observed["article_id"].drop_duplicates()),
        "signal_v1_run_ids": sorted(_int_values(frame[(frame["engine"] == "v1")]["signal_run_id"])),
        "signal_v2_0_run_ids": sorted(_int_values(frame[(frame["engine"] == "v2")]["signal_run_id"])),
        "frozen_at": datetime.utcnow().isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def freeze_phase12_database_reference(session: Session, article_ids: list[int], output_path: Path) -> dict[str, Any]:
    finbert_rows = session.execute(
        select(SentimentAnalysisRun).where(SentimentAnalysisRun.article_id.in_(article_ids), SentimentAnalysisRun.model_family == "finbert")
    ).scalars().all()
    event_rows = session.execute(
        select(EventStudyResult).where(EventStudyResult.article_id.in_(article_ids), EventStudyResult.horizon_minutes == 1440)
    ).scalars().all()
    payload = {
        "article_ids": sorted(article_ids),
        "finbert_run_ids": sorted(int(row.id) for row in finbert_rows),
        "event_study_v2_result_ids": sorted(int(row.id) for row in event_rows),
        "event_study_rows": len(event_rows),
        "finbert_rows": len(finbert_rows),
        "frozen_at": datetime.utcnow().isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def lock_final_holdout(cohort: ResearchCohort, *, preregistration: FinalHoldoutPreregistration, output_path: Path, source_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "dataset_id": preregistration.dataset_id,
        "status": FINAL_HOLDOUT_STATUS,
        "lock_rule": "No Phase 13 performance evaluation. Technical coverage only.",
        "cohort_fingerprint": cohort.fingerprint,
        "article_ids": [sample.article_id for sample in cohort.samples],
        "instruments": sorted({f"{sample.instrument.exchange}:{sample.instrument.ticker}" for sample in cohort.samples}),
        "date_start": min((sample.published_at for sample in cohort.samples), default=preregistration.start_date).isoformat(),
        "date_end": max((sample.published_at for sample in cohort.samples), default=preregistration.end_date).isoformat(),
        "coverage_summary": cohort.coverage_summary,
        "excluded_count": cohort.excluded_count,
        "exclusion_counts": cohort.exclusion_counts,
        "source_manifest": source_manifest or {},
        "locked_at": datetime.utcnow().isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    return payload


def load_development_rows(rows_csv: Path = DEFAULT_PHASE12_ROWS) -> pd.DataFrame:
    frame = pd.read_csv(rows_csv)
    v2 = frame[(frame["split"] == "DEVELOPMENT") & (frame["engine"] == "v2") & frame["1D_realized_direction"].notna()].copy()
    if len(v2) != 118:
        raise ValueError(f"Expected 118 Phase 12 development V2 rows; found {len(v2)}.")
    v2["evaluation_timestamp"] = pd.to_datetime(v2["evaluation_timestamp"], errors="coerce")
    v2 = v2.sort_values(["evaluation_timestamp", "article_id"]).reset_index(drop=True)
    parsed = v2["component_summary"].map(parse_component_summary)
    for name in ("news", "price_momentum", "volume_confirmation", "liquidity", "freshness", "data_quality"):
        v2[f"{name}_available"] = parsed.map(lambda item, n=name: bool(item.get(n, {}).get("available", False)))
        v2[f"{name}_normalized"] = parsed.map(lambda item, n=name: _float(item.get(n, {}).get("normalized_value"), 0.0))
        v2[f"{name}_reliability"] = parsed.map(lambda item, n=name: _float(item.get(n, {}).get("reliability"), 0.0))
    return v2


def load_v1_development_rows(rows_csv: Path = DEFAULT_PHASE12_ROWS) -> pd.DataFrame:
    frame = pd.read_csv(rows_csv)
    v1 = frame[(frame["split"] == "DEVELOPMENT") & (frame["engine"] == "v1") & frame["1D_realized_direction"].notna()].copy()
    v1["evaluation_timestamp"] = pd.to_datetime(v1["evaluation_timestamp"], errors="coerce")
    return v1.sort_values(["evaluation_timestamp", "article_id"]).reset_index(drop=True)


def parse_component_summary(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None or pd.isna(raw):
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return {str(component.get("name")): component for component in payload.get("components", []) if component.get("name")}


def recompute_candidate(row: pd.Series, candidate: SignalV2Candidate) -> tuple[float, str]:
    config = candidate.config()
    directional = [
        ("news", config.news_weight),
        ("price_momentum", config.momentum_weight),
        ("volume_confirmation", config.volume_confirmation_weight),
    ]
    total = 0.0
    score = 0.0
    for name, weight in directional:
        if bool(row.get(f"{name}_available")) and weight > 0:
            total += weight
            score += _float(row.get(f"{name}_normalized"), 0.0) * weight
    raw_score = clamp(score / total) if total > 0 else 0.0
    reliabilities = [
        _float(row.get("liquidity_reliability"), 0.5),
        _float(row.get("freshness_reliability"), 0.6),
        _float(row.get("data_quality_reliability"), 0.65),
    ]
    attenuation = max(0.25, min(sum(reliabilities) / len(reliabilities), 1.0))
    final_score = clamp(raw_score * attenuation)
    return final_score, signal_direction(score_label(final_score, config))


def generate_candidate_grid() -> list[SignalV2Candidate]:
    candidates: list[SignalV2Candidate] = [
        SignalV2Candidate(
            "v2_0_reference",
            V2_0_CONFIG.news_weight,
            V2_0_CONFIG.momentum_weight,
            V2_0_CONFIG.volume_confirmation_weight,
            V2_0_CONFIG.directional_threshold,
        )
    ]
    thresholds = [0.10, 0.15, 0.20, 0.25, 0.30]
    candidate_index = 0
    for news in [0.45, 0.50, 0.55, 0.60, 0.65]:
        for momentum in [0.25, 0.30, 0.35, 0.40, 0.45]:
            raw_volume = round(1.0 - news - momentum, 2)
            volume = max(0.0, raw_volume)
            if volume < -1e-9 or volume > 0.15:
                continue
            if raw_volume < -1e-9:
                continue
            for threshold in thresholds:
                candidate_index += 1
                candidates.append(SignalV2Candidate(f"v2_1_grid_{candidate_index:03d}", news, momentum, volume, threshold))
    unique: dict[tuple[float, float, float, float], SignalV2Candidate] = {}
    for candidate in candidates:
        key = (candidate.news_weight, candidate.momentum_weight, candidate.volume_weight, candidate.directional_threshold)
        unique.setdefault(key, candidate)
    return sorted(unique.values(), key=lambda item: (item.candidate_id != "v2_0_reference", item.candidate_id))


def build_temporal_folds(frame: pd.DataFrame, *, fold_count: int = 3) -> list[TemporalFold]:
    ordered = frame.sort_values(["evaluation_timestamp", "article_id"]).reset_index(drop=True)
    n = len(ordered)
    if n < 20:
        raise ValueError("Not enough development rows for temporal folds.")
    boundaries = [n // 4, n // 2, (3 * n) // 4, n]
    folds: list[TemporalFold] = []
    for idx in range(fold_count):
        train_start = 0
        train_end = boundaries[idx]
        validation_start = boundaries[idx]
        validation_end = boundaries[idx + 1]
        validation = ordered.iloc[validation_start:validation_end]
        train = ordered.iloc[train_start:train_end]
        folds.append(
            TemporalFold(
                fold_id=f"fold_{idx + 1}",
                train_start_index=train_start,
                train_end_index=train_end,
                validation_start_index=validation_start,
                validation_end_index=validation_end,
                train_article_ids=[int(value) for value in train["article_id"]],
                validation_article_ids=[int(value) for value in validation["article_id"]],
                validation_start=str(validation["evaluation_timestamp"].min()),
                validation_end=str(validation["evaluation_timestamp"].max()),
            )
        )
    return folds


class SignalV2ParameterSearch:
    def __init__(self, rows: pd.DataFrame, candidates: list[SignalV2Candidate] | None = None, folds: list[TemporalFold] | None = None) -> None:
        self.rows = rows.sort_values(["evaluation_timestamp", "article_id"]).reset_index(drop=True)
        self.candidates = candidates or generate_candidate_grid()
        self.folds = folds or build_temporal_folds(self.rows)

    def run(self) -> list[CandidateSearchResult]:
        results = [self._evaluate_candidate(candidate) for candidate in self.candidates]
        ranked = sorted(results, key=self._rank_key)
        selected = ranked[0]
        selected.selected = True
        v2_reference = next((item for item in results if item.candidate.candidate_id == "v2_0_reference"), None)
        if v2_reference is None:
            selected.justified = not selected.degenerate
        else:
            improvement = _none_to_neg(selected.median_balanced_accuracy) - _none_to_neg(v2_reference.median_balanced_accuracy)
            selected.justified = (not selected.degenerate) and improvement >= 0.02 and _none_to_neg(selected.worst_fold_balanced_accuracy) >= 0.20
        return sorted(results, key=lambda item: (not item.selected, item.candidate.candidate_id))

    def _evaluate_candidate(self, candidate: SignalV2Candidate) -> CandidateSearchResult:
        fold_results: list[CandidateFoldResult] = []
        all_predictions: list[str] = []
        all_realized: list[str] = []
        for fold in self.folds:
            validation = self.rows.iloc[fold.validation_start_index : fold.validation_end_index].copy()
            pairs: list[tuple[str, str]] = []
            predictions: list[str] = []
            realized: list[str] = []
            for _, row in validation.iterrows():
                _, prediction = recompute_candidate(row, candidate)
                outcome = str(row["1D_realized_direction"])
                pairs.append((prediction, outcome))
                predictions.append(prediction)
                realized.append(outcome)
            metrics = classification_metrics(pairs)
            fold_results.append(
                CandidateFoldResult(
                    candidate_id=candidate.candidate_id,
                    fold_id=fold.fold_id,
                    n=len(pairs),
                    balanced_accuracy=metrics.balanced_accuracy,
                    macro_f1=macro_f1(metrics.f1),
                    strict_accuracy=metrics.strict_accuracy,
                    directional_accuracy=metrics.directional_accuracy,
                    coverage=1.0 if pairs else 0.0,
                    prediction_distribution=count_values(predictions),
                    realized_distribution=count_values(realized),
                )
            )
            all_predictions.extend(predictions)
            all_realized.extend(realized)
        balances = [item.balanced_accuracy for item in fold_results if item.balanced_accuracy is not None]
        degenerate, reason = degeneracy_status(all_predictions, all_realized)
        return CandidateSearchResult(
            candidate=candidate,
            folds=fold_results,
            median_balanced_accuracy=float(median(balances)) if balances else None,
            mean_balanced_accuracy=float(mean(balances)) if balances else None,
            worst_fold_balanced_accuracy=min(balances) if balances else None,
            std_balanced_accuracy=float(pstdev(balances)) if len(balances) > 1 else 0.0 if balances else None,
            mean_macro_f1=_mean([item.macro_f1 for item in fold_results if item.macro_f1 is not None]),
            degenerate=degenerate,
            degeneracy_reason=reason,
        )

    @staticmethod
    def _rank_key(result: CandidateSearchResult) -> tuple[float, float, float, float, str]:
        return (
            1.0 if result.degenerate else 0.0,
            -_none_to_neg(result.median_balanced_accuracy),
            -_none_to_neg(result.worst_fold_balanced_accuracy),
            result.candidate.distance_from_v2_0,
            result.candidate.candidate_id,
        )


def degeneracy_status(predictions: list[str], realized: list[str]) -> tuple[bool, str | None]:
    total = len(predictions)
    if total == 0:
        return True, "NO_VALIDATION_ROWS"
    counts = count_values(predictions)
    directional = counts.get("BULLISH", 0) + counts.get("BEARISH", 0)
    if directional / total < 0.20:
        return True, "DIRECTIONAL_PREDICTION_RATE_BELOW_20_PERCENT"
    if max(counts.values()) / total > 0.90:
        return True, "SINGLE_CLASS_ABOVE_90_PERCENT"
    if len(set(realized)) >= 3 and len([key for key, value in counts.items() if value > 0]) < 2:
        return True, "LESS_THAN_TWO_PREDICTED_CLASSES_WITH_THREE_REALIZED_CLASSES"
    return False, None


def development_error_analysis(rows: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        correct = signal_direction(row.get("original_label")) == str(row["1D_realized_direction"])
        primary, secondary = classify_error(row) if not correct else ("CORRECT", None)
        items.append(
            {
                "article_id": int(row["article_id"]),
                "instrument": row["instrument"],
                "evaluation_timestamp": str(row["evaluation_timestamp"]),
                "prediction": signal_direction(row.get("original_label")),
                "realized": row["1D_realized_direction"],
                "score": row["signal_score"],
                "correct": correct,
                "primary_error_category": primary,
                "secondary_error_category": secondary,
                "news": row.get("news_normalized"),
                "momentum": row.get("price_momentum_normalized"),
                "volume": row.get("volume_confirmation_normalized"),
            }
        )
    frame = pd.DataFrame(items)
    summary = {
        "n": int(len(frame)),
        "incorrect": int((~frame["correct"]).sum()),
        "error_categories": frame[~frame["correct"]]["primary_error_category"].value_counts().to_dict(),
        "score_distribution": score_distribution(rows, "signal_score"),
        "component_distributions": {
            "news": score_distribution(rows, "news_normalized"),
            "momentum": score_distribution(rows, "price_momentum_normalized"),
            "volume": score_distribution(rows, "volume_confirmation_normalized"),
        },
        "prediction_distribution": rows["canonical_direction"].value_counts().to_dict(),
        "realized_distribution": rows["1D_realized_direction"].value_counts().to_dict(),
        "per_symbol": per_symbol_development(rows),
        "component_agreement": component_agreement(rows),
        "title_only_limitation": "Current FNSPID rows mostly lack usable summaries, so sentiment evidence is predominantly title-based.",
    }
    return frame, summary


def classify_error(row: pd.Series) -> tuple[str, str | None]:
    prediction = signal_direction(row.get("original_label"))
    realized = str(row["1D_realized_direction"])
    score = _float(row.get("signal_score"), 0.0)
    news = _float(row.get("news_normalized"), 0.0)
    momentum = _float(row.get("price_momentum_normalized"), 0.0)
    volume = _float(row.get("volume_confirmation_normalized"), 0.0)
    realized_sign = direction_sign(realized)
    news_sign = numeric_sign(news)
    momentum_sign = numeric_sign(momentum)
    if prediction == "NEUTRAL" and realized != "NEUTRAL" and abs(score) < V2_0_CONFIG.directional_threshold:
        return "NEUTRAL_BAND_MISS", "INSUFFICIENT_DIRECTIONAL_EVIDENCE"
    if abs(score) < 0.10:
        return "WEAK_SIGNAL_MISS", None
    if news_sign != 0 and momentum_sign != 0 and news_sign != momentum_sign:
        return "NEWS_MARKET_CONFLICT", None
    if news_sign == momentum_sign and news_sign != 0 and news_sign != realized_sign:
        return "NEWS_MARKET_AGREE_WRONG", None
    if news_sign == realized_sign and momentum_sign != realized_sign:
        return "NEWS_RIGHT_MARKET_WRONG", None
    if news_sign != realized_sign and momentum_sign == realized_sign:
        return "NEWS_WRONG_MARKET_RIGHT", None
    if abs(momentum * V2_0_CONFIG.momentum_weight) > abs(news * V2_0_CONFIG.news_weight) * 1.25:
        return "MOMENTUM_DOMINANCE", None
    if abs(news * V2_0_CONFIG.news_weight) > abs(momentum * V2_0_CONFIG.momentum_weight) * 1.25:
        return "NEWS_DOMINANCE", None
    if abs(volume) > 0.05 and numeric_sign(volume) != realized_sign:
        return "VOLUME_CONFIRMATION_MISS", None
    return "OTHER", None


def score_distribution(frame: pd.DataFrame, column: str) -> dict[str, float | int | None]:
    values = [_float(value, None) for value in frame[column].tolist() if _float(value, None) is not None]
    values = [float(value) for value in values if math.isfinite(float(value))]
    if not values:
        return {"n": 0}
    series = pd.Series(values)
    return {
        "n": int(len(values)),
        "mean": float(series.mean()),
        "median": float(series.median()),
        "q1": float(series.quantile(0.25)),
        "q3": float(series.quantile(0.75)),
        "std": float(series.std(ddof=0)),
        "min": float(series.min()),
        "max": float(series.max()),
    }


def per_symbol_development(rows: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for instrument, group in rows.groupby("instrument"):
        pairs = [(signal_direction(row["original_label"]), str(row["1D_realized_direction"])) for _, row in group.iterrows()]
        metrics = classification_metrics(pairs)
        output[str(instrument)] = {
            "n": int(len(group)),
            "strict_accuracy": metrics.strict_accuracy,
            "balanced_accuracy": metrics.balanced_accuracy,
            "signal_distribution": group["canonical_direction"].value_counts().to_dict(),
            "realized_distribution": group["1D_realized_direction"].value_counts().to_dict(),
        }
    return output


def component_agreement(rows: pd.DataFrame) -> dict[str, Any]:
    buckets: dict[str, list[tuple[str, str]]] = {}
    for _, row in rows.iterrows():
        news = numeric_sign(_float(row.get("news_normalized"), 0.0))
        momentum = numeric_sign(_float(row.get("price_momentum_normalized"), 0.0))
        if not bool(row.get("news_available")) or not bool(row.get("price_momentum_available")):
            bucket = "ONE_COMPONENT_UNAVAILABLE"
        elif news > 0 and momentum > 0:
            bucket = "NEWS_BULLISH_MARKET_BULLISH"
        elif news < 0 and momentum < 0:
            bucket = "NEWS_BEARISH_MARKET_BEARISH"
        elif news != 0 and momentum != 0 and news != momentum:
            bucket = "NEWS_MARKET_CONFLICT"
        else:
            bucket = "ONE_COMPONENT_NEUTRAL"
        buckets.setdefault(bucket, []).append((signal_direction(row["original_label"]), str(row["1D_realized_direction"])))
    return {
        bucket: {"n": len(pairs), "metrics": asdict_safe(classification_metrics(pairs))}
        for bucket, pairs in sorted(buckets.items())
    }


def baseline_fold_results(rows: pd.DataFrame, v1_rows: pd.DataFrame, folds: list[TemporalFold]) -> dict[str, list[dict[str, Any]]]:
    v1_by_article = {int(row["article_id"]): row for _, row in v1_rows.iterrows()}
    output: dict[str, list[dict[str, Any]]] = {"v2_0": [], "v1": [], "majority_class": [], "always_neutral": [], "news_direction": []}
    for fold in folds:
        train = rows.iloc[fold.train_start_index : fold.train_end_index]
        validation = rows.iloc[fold.validation_start_index : fold.validation_end_index]
        majority = _majority([str(value) for value in train["1D_realized_direction"].tolist()]) or "NEUTRAL"
        rules = {
            "v2_0": [(str(row["canonical_direction"]), str(row["1D_realized_direction"])) for _, row in validation.iterrows()],
            "v1": [(signal_direction(v1_by_article[int(row["article_id"])]["original_label"]), str(row["1D_realized_direction"])) for _, row in validation.iterrows() if int(row["article_id"]) in v1_by_article],
            "majority_class": [(majority, str(row["1D_realized_direction"])) for _, row in validation.iterrows()],
            "always_neutral": [("NEUTRAL", str(row["1D_realized_direction"])) for _, row in validation.iterrows()],
            "news_direction": [(signal_direction(v1_by_article[int(row["article_id"])]["original_label"]), str(row["1D_realized_direction"])) for _, row in validation.iterrows() if int(row["article_id"]) in v1_by_article],
        }
        for name, pairs in rules.items():
            metrics = classification_metrics(pairs)
            output[name].append({"fold_id": fold.fold_id, "n": len(pairs), **asdict_safe(metrics), "macro_f1": macro_f1(metrics.f1)})
    return output


def export_search_results(results: list[CandidateSearchResult], output_path: Path) -> Path:
    rows: list[dict[str, Any]] = []
    for result in results:
        base = {
            "candidate_id": result.candidate.candidate_id,
            "news_weight": result.candidate.news_weight,
            "momentum_weight": result.candidate.momentum_weight,
            "volume_weight": result.candidate.volume_weight,
            "threshold": result.candidate.directional_threshold,
            "median_balanced_accuracy": result.median_balanced_accuracy,
            "mean_balanced_accuracy": result.mean_balanced_accuracy,
            "worst_fold_balanced_accuracy": result.worst_fold_balanced_accuracy,
            "std_balanced_accuracy": result.std_balanced_accuracy,
            "mean_macro_f1": result.mean_macro_f1,
            "coverage": 1.0,
            "degeneracy_flag": result.degenerate,
            "degeneracy_reason": result.degeneracy_reason,
            "selected": result.selected,
            "justified": result.justified,
        }
        for fold in result.folds:
            rows.append(
                {
                    **base,
                    "fold_id": fold.fold_id,
                    "fold_n": fold.n,
                    "fold_balanced_accuracy": fold.balanced_accuracy,
                    "fold_macro_f1": fold.macro_f1,
                    "fold_strict_accuracy": fold.strict_accuracy,
                    "fold_directional_accuracy": fold.directional_accuracy,
                    "fold_prediction_distribution": json.dumps(fold.prediction_distribution, sort_keys=True),
                    "fold_realized_distribution": json.dumps(fold.realized_distribution, sort_keys=True),
                }
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def selected_candidate_config(result: CandidateSearchResult, *, tuning_fingerprint: str) -> dict[str, Any]:
    return {
        "engine_name": ENGINE_NAME_V2,
        "engine_version": ENGINE_VERSION_V2_1_RESEARCH,
        "status": "FROZEN_RESEARCH_CANDIDATE" if result.justified else "FROZEN_RESEARCH_CANDIDATE_NOT_JUSTIFIED",
        "parent_version": ENGINE_VERSION_V2,
        "candidate": result.candidate.to_dict(),
        "strong_threshold": V2_0_CONFIG.strong_threshold,
        "momentum_return_scale": V2_0_CONFIG.momentum_return_scale,
        "news_decay": {
            "max_news_age_hours": V2_0_CONFIG.max_news_age_hours,
            "min_news_recency_weight": V2_0_CONFIG.min_news_recency_weight,
        },
        "confidence_formula": "unchanged from V2.0: 0.35*abs(score)+0.30*reliability+0.20*agreement+0.15*availability",
        "tuning_dataset_fingerprint": tuning_fingerprint,
        "tuning_method": "Phase 12 DEVELOPMENT rows only; 3-fold chronological expanding-window validation; median balanced accuracy objective.",
        "created_at": datetime.utcnow().isoformat(),
    }


def render_phase13_report(
    *,
    rows: pd.DataFrame,
    folds: list[TemporalFold],
    candidates: list[SignalV2Candidate],
    search_results: list[CandidateSearchResult],
    baselines: dict[str, Any],
    error_summary: dict[str, Any],
    final_holdout_lock: dict[str, Any] | None,
    output_path: Path,
) -> Path:
    selected = next(result for result in search_results if result.selected)
    v2_reference = next(result for result in search_results if result.candidate.candidate_id == "v2_0_reference")
    lines = [
        "# Signal V2.1 Development-Only Tuning",
        "",
        "## Research Discipline",
        "Parameter selection used only Phase 12 DEVELOPMENT rows. Phase 12 HOLDOUT is renamed OBSERVED_VALIDATION and was not used for tuning. The new final holdout is locked and unevaluated.",
        "",
        "## Data Used",
        f"Development observations: {len(rows)} valid 1D V2 rows.",
        "",
        "## Data NOT Used",
        "- Phase 12 OBSERVED_VALIDATION metrics",
        "- New FINAL_HOLDOUT_LOCKED outcomes or accuracy",
        "",
        "## Temporal Folds",
        json.dumps([asdict(fold) for fold in folds], indent=2, sort_keys=True),
        "",
        "## Baselines",
        json.dumps(to_jsonable(baselines), indent=2, sort_keys=True),
        "",
        "## Candidate Space",
        f"Candidates evaluated: {len(candidates)}",
        "Tuned only news weight, momentum weight, volume-confirmation weight, and symmetric directional threshold.",
        "",
        "## Objective",
        "Primary objective: median temporal-fold balanced accuracy. Tie breakers: worst fold, closeness to V2.0, deterministic id.",
        "",
        "## Degeneracy Rules",
        "Reject candidates with <20% directional predictions, >90% one-class predictions, or fewer than two predicted classes when validation outcomes contain all three classes.",
        "",
        "## Results",
        f"V2.0 reference median balanced accuracy: {fmt(v2_reference.median_balanced_accuracy)}",
        f"Selected candidate median balanced accuracy: {fmt(selected.median_balanced_accuracy)}",
        f"Selected candidate worst-fold balanced accuracy: {fmt(selected.worst_fold_balanced_accuracy)}",
        f"Selected candidate justified: {selected.justified}",
        "",
        "## Selected Candidate",
        json.dumps(selected_candidate_config(selected, tuning_fingerprint=stable_fingerprint(rows[["article_id", "evaluation_timestamp", "1D_realized_direction"]].to_dict("records"))), indent=2, sort_keys=True),
        "",
        "## V2.0 vs V2.1 Development Comparison",
        json.dumps({"v2_0": search_result_payload(v2_reference), "selected": search_result_payload(selected)}, indent=2, sort_keys=True),
        "",
        "## Optional Observed-Validation Result",
        "Skipped in Phase 13 to avoid any risk of post-freeze tuning feedback.",
        "",
        "## New Final Holdout",
        json.dumps(to_jsonable(final_holdout_lock or {"status": "not_locked_in_this_run"}), indent=2, sort_keys=True),
        "",
        "## Final Holdout Status",
        "FINAL_HOLDOUT_LOCKED and UNEVALUATED. Only technical price coverage metadata was checked.",
        "",
        "## Error Analysis",
        json.dumps(to_jsonable(error_summary), indent=2, sort_keys=True),
        "",
        "## Limitations",
        "Small development sample, title-heavy FNSPID text, daily bars only, no confidence calibration, and final-holdout symbol coverage limited by bounded-source feasibility.",
        "",
        "## What Cannot Yet Be Claimed",
        "Do not claim production superiority, profitability, calibration, or final generalization until the locked final holdout is evaluated in a later explicit phase.",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_phase13_docs(*, output_dir: Path, final_lock: dict[str, Any] | None, selected_config: dict[str, Any], error_summary: dict[str, Any]) -> list[Path]:
    docs = {
        Path("docs") / "SIGNAL_V2_PARAMETER_SEARCH.md": [
            "# Signal V2 Parameter Search",
            "",
            "Phase 13 searches only V2 directional weights and the symmetric directional threshold on Phase 12 DEVELOPMENT rows.",
            f"Experiment artifacts: `{output_dir.as_posix()}`",
            f"Engine id: `{ENGINE_NAME_V2}` / `{ENGINE_VERSION_V2_1_RESEARCH}`",
        ],
        Path("docs") / "SIGNAL_V2_1_RESEARCH_CANDIDATE.md": [
            "# Signal V2.1 Research Candidate",
            "",
            "The candidate is frozen for research only and is not the dashboard default.",
            "",
            "```json",
            json.dumps(to_jsonable(selected_config), indent=2, sort_keys=True),
            "```",
        ],
        Path("docs") / "PHASE13_ERROR_ANALYSIS.md": [
            "# Phase 13 Error Analysis",
            "",
            "All findings use Phase 12 DEVELOPMENT rows only.",
            "",
            "```json",
            json.dumps(to_jsonable(error_summary), indent=2, sort_keys=True),
            "```",
        ],
    }
    if final_lock:
        docs[Path("docs") / "LOCKED_COHORT_EVALUATION.md"] = [
            "# Locked Cohort Evaluation",
            "",
            "Phase 12 HOLDOUT is now OBSERVED_VALIDATION. Phase 13 creates a new FINAL_HOLDOUT_LOCKED cohort.",
            "",
            f"Final holdout fingerprint: `{final_lock.get('cohort_fingerprint')}`",
            "Final holdout accuracy has not been evaluated.",
        ]
    written: list[Path] = []
    for path, lines in docs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(path)
    return written


def search_result_payload(result: CandidateSearchResult) -> dict[str, Any]:
    return {
        "candidate": result.candidate.to_dict(),
        "median_balanced_accuracy": result.median_balanced_accuracy,
        "mean_balanced_accuracy": result.mean_balanced_accuracy,
        "worst_fold_balanced_accuracy": result.worst_fold_balanced_accuracy,
        "std_balanced_accuracy": result.std_balanced_accuracy,
        "mean_macro_f1": result.mean_macro_f1,
        "degenerate": result.degenerate,
        "degeneracy_reason": result.degeneracy_reason,
        "selected": result.selected,
        "justified": result.justified,
        "folds": [asdict(fold) for fold in result.folds],
    }


def asdict_safe(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(value), default=str))


def macro_f1(values: dict[str, float | None]) -> float | None:
    usable = [value for value in values.values() if value is not None]
    return sum(usable) / len(usable) if usable else None


def count_values(values: list[str]) -> dict[str, int]:
    counts = {label: 0 for label in DIRECTIONS}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return {key: value for key, value in counts.items() if value}


def direction_sign(value: str) -> int:
    if value == "BULLISH":
        return 1
    if value == "BEARISH":
        return -1
    return 0


def numeric_sign(value: float) -> int:
    if value > 0.05:
        return 1
    if value < -0.05:
        return -1
    return 0


def _majority(values: list[str]) -> str | None:
    if not values:
        return None
    counts = count_values(values)
    return sorted(counts, key=lambda item: (-counts[item], DIRECTIONS.index(item) if item in DIRECTIONS else 99))[0]


def _int_values(values: pd.Series) -> list[int]:
    output: list[int] = []
    for value in values.dropna().tolist():
        try:
            output.append(int(value))
        except (TypeError, ValueError):
            continue
    return output


def _float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _none_to_neg(value: float | None) -> float:
    return value if value is not None else -1.0


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value
