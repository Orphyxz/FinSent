from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
import csv
import io
import json
import math
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.database.entities import EventStudyResult, NewsArticle
from finsent.app.database.repository import PriceRepository
from finsent.app.services.historical_news_acquisition import (
    DEFAULT_RESEARCH_SOURCE_DIR,
    FNSPIDAdapter,
    HistoricalArticleRecord,
    clean_text,
    file_sha256,
    relative_path,
    utc_now,
    write_manifest,
)
from finsent.app.services.historical_signal_evaluation import signal_direction
from finsent.app.services.model_comparison import classification_metrics, realized_direction, wilson_interval
from finsent.app.services.research_dataset import ResearchCohortConfig, ResearchCohortSample
from finsent.app.services.signal_engine_v2 import SignalEngineV2Config
from finsent.app.services.symbol_registry import registry


FNSPID_ALL_EXTERNAL_URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/All_external.csv"
PHASE12_SELECTION_VERSION = "phase12_stratified_fnspid_v1"
PHASE12_EVALUATION_VERSION = "phase12_locked_baseline_v1"
DEFAULT_PHASE12_BATCH_ID = "phase12_locked_multisymbol_v1"
DIRECTIONS = ("BULLISH", "NEUTRAL", "BEARISH")


@dataclass(frozen=True, slots=True)
class Phase12Preregistration:
    dataset_id: str
    source_name: str
    source_url: str
    source_file: str
    symbols: list[str]
    markets: list[str]
    start_date: datetime
    end_date: datetime
    per_symbol_target: int
    article_cap: int
    max_scan_rows: int
    sampling_method: str
    horizon: str
    price_source: str
    price_basis: str
    sentiment_source: str
    eligibility_rules: list[str]
    dedupe_rules: list[str]
    realized_direction_threshold: float
    development_fraction: float
    holdout_fraction: float
    holdout_start: datetime
    minimum_data_quality_policy: str
    exclusion_rules: list[str]
    selection_version: str = PHASE12_SELECTION_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start_date"] = self.start_date.isoformat()
        payload["end_date"] = self.end_date.isoformat()
        payload["holdout_start"] = self.holdout_start.isoformat()
        payload["fingerprint"] = preregistration_fingerprint(self)
        return payload


@dataclass(frozen=True, slots=True)
class StratifiedFNSPIDAcquisitionConfig:
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    per_symbol_limit: int = 40
    max_scan_rows: int = 1_500_000
    cache_dir: Path = DEFAULT_RESEARCH_SOURCE_DIR
    batch_id: str = DEFAULT_PHASE12_BATCH_ID
    dry_run: bool = True
    source_url: str = FNSPID_ALL_EXTERNAL_URL
    source_file: str = "Stock_news/All_external.csv"
    request_timeout_seconds: int = 60
    selection_version: str = PHASE12_SELECTION_VERSION

    def normalized_symbols(self) -> list[str]:
        return [symbol.upper().strip() for symbol in self.symbols if symbol.strip()]

    @property
    def article_cap(self) -> int:
        return len(self.normalized_symbols()) * max(self.per_symbol_limit, 0)

    def to_manifest_filters(self) -> dict[str, Any]:
        return {
            "symbols": self.normalized_symbols(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "per_symbol_limit": self.per_symbol_limit,
            "article_cap": self.article_cap,
            "max_scan_rows": self.max_scan_rows,
            "selection_version": self.selection_version,
        }


@dataclass(slots=True)
class StratifiedAcquisitionSummary:
    source_name: str
    dry_run: bool
    requested_symbols: list[str]
    start_date: datetime
    end_date: datetime
    scanned_rows: int
    per_symbol_counts: dict[str, int]
    written_rows: int
    invalid_rows: int
    invalid_reasons: dict[str, int]
    duplicate_rows: int
    scan_limit_reached: bool
    quota_satisfied: bool
    subset_path: str | None
    manifest_path: str | None
    checksum_sha256: str | None
    estimated_disk_bytes: int | None
    records: list[HistoricalArticleRecord] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class YahooChartDailyPriceConfig:
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    batch_id: str = DEFAULT_PHASE12_BATCH_ID
    cache_dir: Path = DEFAULT_RESEARCH_SOURCE_DIR
    dry_run: bool = True
    source_name: str = "yahoo_chart_daily"
    request_timeout_seconds: int = 30


@dataclass(slots=True)
class YahooChartDailyPriceSummary:
    source_name: str
    dry_run: bool
    symbols: list[str]
    imported_rows: dict[str, int]
    written_files: list[str]
    failures: dict[str, str]
    manifest_path: str | None


def preregistration_fingerprint(preregistration: Phase12Preregistration) -> str:
    payload = asdict(preregistration)
    payload["start_date"] = preregistration.start_date.isoformat()
    payload["end_date"] = preregistration.end_date.isoformat()
    payload["holdout_start"] = preregistration.holdout_start.isoformat()
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def write_preregistration(path: Path, preregistration: Phase12Preregistration) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = preregistration.to_dict()
    lines = [
        "# Phase 12 Cohort Preregistration",
        "",
        "This document locks the expanded cohort rules before performance metrics are generated.",
        "",
        f"Fingerprint: `{data['fingerprint']}`",
        "",
        "```json",
        json.dumps(data, indent=2, sort_keys=True),
        "```",
        "",
        "Rule-change policy: after evaluation begins, changes require a new dataset id/version.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class StratifiedFNSPIDAcquirer:
    def __init__(self, *, session_factory: requests.Session | None = None, adapter: FNSPIDAdapter | None = None) -> None:
        self.session = session_factory or requests.Session()
        self.session.headers.update({"User-Agent": "FinSent/Phase12 locked cohort acquisition"})
        self.adapter = adapter or FNSPIDAdapter()

    def acquire(self, config: StratifiedFNSPIDAcquisitionConfig) -> StratifiedAcquisitionSummary:
        csv.field_size_limit(sys.maxsize)
        requested = config.normalized_symbols()
        requested_set = set(requested)
        counts = {symbol: 0 for symbol in requested}
        invalid: dict[str, int] = {}
        seen: set[str] = set()
        records: list[HistoricalArticleRecord] = []
        duplicate_rows = 0
        scanned = 0
        response = self.session.get(config.source_url, stream=True, timeout=config.request_timeout_seconds)
        response.raise_for_status()
        estimated_disk = _safe_int(response.headers.get("content-length"))
        response.raw.decode_content = True
        reader = csv.DictReader(io.TextIOWrapper(response.raw, encoding="utf-8", errors="replace", newline=""))
        original_source_file = self.adapter.source_file
        self.adapter.source_file = config.source_file
        try:
            for scanned, row in enumerate(reader, start=1):
                if scanned > max(config.max_scan_rows, 0):
                    break
                symbol = (clean_text(row.get("Stock_symbol")) or "").upper()
                if symbol not in requested_set or counts.get(symbol, 0) >= config.per_symbol_limit:
                    continue
                timestamp = pd.to_datetime(row.get("Date"), utc=True, errors="coerce")
                if pd.isna(timestamp):
                    invalid["MISSING_TIMESTAMP"] = invalid.get("MISSING_TIMESTAMP", 0) + 1
                    continue
                dt = timestamp.to_pydatetime().replace(tzinfo=None)
                if dt < config.start_date or dt > config.end_date:
                    continue
                record, reason = self.adapter.normalize_row(row, row_number=scanned)
                if reason is not None:
                    invalid[reason] = invalid.get(reason, 0) + 1
                    continue
                assert record is not None
                if record.dedupe_hash in seen:
                    duplicate_rows += 1
                    continue
                seen.add(record.dedupe_hash)
                records.append(record)
                counts[symbol] = counts.get(symbol, 0) + 1
                if all(counts[symbol] >= config.per_symbol_limit for symbol in requested):
                    break
        finally:
            self.adapter.source_file = original_source_file
        records = sorted(records, key=lambda item: (item.symbol, item.published_at, item.source_record_id))
        quota_satisfied = all(counts[symbol] >= config.per_symbol_limit for symbol in requested)
        subset_path = manifest_path = checksum = None
        if not config.dry_run:
            subset_dir = config.cache_dir / "fnspid" / "subsets"
            subset_dir.mkdir(parents=True, exist_ok=True)
            target = subset_dir / f"{config.batch_id}.csv"
            _write_subset(target, records)
            checksum = file_sha256(target)
            manifest = write_manifest(
                config.cache_dir / "fnspid" / "MANIFEST.json",
                {
                    "source_name": "FNSPID",
                    "source_identifier": "Zihan1004/FNSPID",
                    "source_url": config.source_url,
                    "source_file": config.source_file,
                    "dataset_version": "Hugging Face dataset repo current main at acquisition time",
                    "acquired_at": utc_now().isoformat(),
                    "adapter_version": "fnspid_adapter_v1",
                    "selection_version": config.selection_version,
                    "filters": config.to_manifest_filters(),
                    "record_count": len(records),
                    "per_symbol_counts": counts,
                    "scanned_rows": scanned,
                    "checksum_sha256": checksum,
                    "local_relative_path": relative_path(target),
                    "dry_run": False,
                },
            )
            subset_path = str(target)
            manifest_path = str(manifest)
        return StratifiedAcquisitionSummary(
            source_name="FNSPID",
            dry_run=config.dry_run,
            requested_symbols=requested,
            start_date=config.start_date,
            end_date=config.end_date,
            scanned_rows=scanned,
            per_symbol_counts=counts,
            written_rows=0 if config.dry_run else len(records),
            invalid_rows=sum(invalid.values()),
            invalid_reasons=invalid,
            duplicate_rows=duplicate_rows,
            scan_limit_reached=scanned >= max(config.max_scan_rows, 0) and not quota_satisfied,
            quota_satisfied=quota_satisfied,
            subset_path=subset_path,
            manifest_path=manifest_path,
            checksum_sha256=checksum,
            estimated_disk_bytes=estimated_disk,
            records=records,
        )


def phase12_preregistration() -> Phase12Preregistration:
    symbols = ["AAPL", "AMZN", "GOOGL", "NVDA", "TSLA"]
    return Phase12Preregistration(
        dataset_id=DEFAULT_PHASE12_BATCH_ID,
        source_name="FNSPID",
        source_url=FNSPID_ALL_EXTERNAL_URL,
        source_file="Stock_news/All_external.csv",
        symbols=symbols,
        markets=["US"],
        start_date=datetime(2020, 5, 1),
        end_date=datetime(2020, 6, 15, 23, 59, 59),
        per_symbol_target=40,
        article_cap=200,
        max_scan_rows=1_500_000,
        sampling_method="Bounded deterministic per-symbol quota from FNSPID source order; no performance filtering.",
        horizon="1d",
        price_source="yahoo_chart_daily",
        price_basis="Unadjusted Yahoo Finance chart quote.close; adjclose is fetched for audit but not used by Event Study V2",
        sentiment_source="FinBERT only",
        eligibility_rules=[
            "supported FinSent US symbol",
            "valid timestamp/title/url",
            "dedupe hash unique",
            "daily price bars support a valid 1D Event Study V2 outcome",
        ],
        dedupe_rules=["FNSPID source id/symbol/date/url/title hash", "database URL uniqueness"],
        realized_direction_threshold=0.001,
        development_fraction=0.75,
        holdout_fraction=0.25,
        holdout_start=datetime(2020, 6, 5),
        minimum_data_quality_policy="No project-owned fabricated articles/prices; missing summaries allowed only when title exists.",
        exclusion_rules=[
            "unsupported symbol",
            "invalid timestamp",
            "missing title",
            "duplicate article",
            "no valid 1D price coverage",
            "sentiment analyzer failure",
        ],
    )


class YahooChartDailyPriceAcquirer:
    def __init__(self, *, session_factory: requests.Session | None = None) -> None:
        self.session = session_factory or requests.Session()
        self.session.headers.update({"User-Agent": "FinSent/Phase12 Yahoo chart daily price acquisition"})

    def acquire(self, config: YahooChartDailyPriceConfig, *, db_session: Session | None = None) -> YahooChartDailyPriceSummary:
        failures: dict[str, str] = {}
        imported: dict[str, int] = {}
        written_files: list[str] = []
        target_dir = config.cache_dir / config.source_name / "prices" / config.batch_id
        if not config.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        for symbol in sorted({item.upper().strip() for item in config.symbols if item.strip()}):
            try:
                frame = self._download(symbol, config)
            except Exception as exc:
                failures[symbol] = str(exc)
                continue
            if frame.empty:
                failures[symbol] = "No daily price rows returned."
                continue
            imported[symbol] = len(frame)
            if not config.dry_run:
                path = target_dir / f"{symbol}.csv"
                frame.to_csv(path)
                written_files.append(relative_path(path))
                if db_session is not None:
                    PriceRepository(db_session).upsert_price_bars(
                        symbol,
                        frame[["Open", "High", "Low", "Close", "Volume"]],
                        provider=config.source_name,
                        dataset_id=config.batch_id,
                        data_mode="HISTORICAL_RESEARCH",
                        quality_status="RESEARCH_DAILY",
                    )
        manifest_path = None
        if not config.dry_run:
            manifest_path = write_manifest(
                config.cache_dir / config.source_name / "MANIFEST.json",
                {
                    "source_name": config.source_name,
                    "source_identifier": "Yahoo Finance chart API",
                    "acquired_at": utc_now().isoformat(),
                    "adapter_version": "yahoo_chart_daily_price_adapter_v1",
                    "filters": {
                        "symbols": sorted({item.upper().strip() for item in config.symbols if item.strip()}),
                        "start_date": config.start_date.isoformat(),
                        "end_date": config.end_date.isoformat(),
                        "frequency": "1d",
                    },
                    "price_basis": "Unadjusted OHLC quote.close imported; adjclose retained in CSV for audit only.",
                    "record_count": sum(imported.values()),
                    "local_relative_path": relative_path(target_dir),
                    "written_files": written_files,
                    "failures": failures,
                    "dry_run": False,
                },
            )
        return YahooChartDailyPriceSummary(
            source_name=config.source_name,
            dry_run=config.dry_run,
            symbols=sorted({item.upper().strip() for item in config.symbols if item.strip()}),
            imported_rows=imported,
            written_files=written_files,
            failures=failures,
            manifest_path=str(manifest_path) if manifest_path else None,
        )

    def _download(self, symbol: str, config: YahooChartDailyPriceConfig) -> pd.DataFrame:
        period1 = int(pd.Timestamp(config.start_date, tz="UTC").timestamp())
        period2 = int(pd.Timestamp(config.end_date + pd.Timedelta(days=5), tz="UTC").timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        response = self.session.get(
            url,
            params={"period1": period1, "period2": period2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"},
            timeout=config.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result:
            error = (payload.get("chart") or {}).get("error")
            raise ValueError(f"Yahoo chart returned no result: {error}")
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
        rows: list[dict[str, Any]] = []
        for index, raw_ts in enumerate(timestamps):
            close = _list_get(quote.get("close"), index)
            if close is None:
                continue
            ts = pd.to_datetime(raw_ts, unit="s", utc=True).to_pydatetime().replace(tzinfo=None)
            rows.append(
                {
                    "timestamp": ts,
                    "Open": _list_get(quote.get("open"), index),
                    "High": _list_get(quote.get("high"), index),
                    "Low": _list_get(quote.get("low"), index),
                    "Close": close,
                    "Volume": _list_get(quote.get("volume"), index) or 0,
                    "Adj Close": _list_get(adj, index),
                }
            )
        frame = pd.DataFrame(rows)
        if frame.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Adj Close"])
        frame = frame.dropna(subset=["Open", "High", "Low", "Close"]).set_index("timestamp").sort_index()
        return frame


def holdout_start_from_records(records: list[HistoricalArticleRecord], *, fraction: float = 0.25) -> datetime | None:
    if not records:
        return None
    ordered = sorted(records, key=lambda item: (item.published_at, item.symbol, item.source_record_id))
    index = max(0, min(len(ordered) - 1, math.floor(len(ordered) * (1.0 - fraction))))
    return ordered[index].published_at


def holdout_start_from_samples(samples: list[ResearchCohortSample], *, fraction: float = 0.25) -> datetime | None:
    if not samples:
        return None
    ordered = sorted(samples, key=lambda item: (item.published_at, item.article_id))
    index = max(0, min(len(ordered) - 1, math.floor(len(ordered) * (1.0 - fraction))))
    return ordered[index].published_at


def cohort_selection_config(preregistration: Phase12Preregistration, *, holdout_start: datetime | None = None) -> ResearchCohortConfig:
    return ResearchCohortConfig(
        symbols=preregistration.symbols,
        markets=preregistration.markets,
        start_date=preregistration.start_date,
        end_date=preregistration.end_date,
        horizons=[preregistration.horizon],
        limit=preregistration.article_cap,
        seed=42,
        holdout_start=holdout_start or preregistration.holdout_start,
        dataset_id=preregistration.dataset_id,
    )


def export_v2_diagnostic_from_rows(session: Session, rows_csv: Path, output_path: Path) -> Path:
    frame = pd.read_csv(rows_csv)
    v2 = frame[frame["engine"] == "v2"].copy()
    rows: list[dict[str, Any]] = []
    for _, row in v2.iterrows():
        article = session.get(NewsArticle, int(row["article_id"]))
        event = _event_for_signal(session, _optional_int(row.get("signal_run_id")))
        components = _components_by_name(row.get("component_summary"))
        news = components.get("news", {})
        momentum = components.get("price_momentum", {})
        volume = components.get("volume_confirmation", {})
        liquidity = components.get("liquidity", {})
        freshness = components.get("freshness", {})
        quality = components.get("data_quality", {})
        payload = {
            "article_id": int(row["article_id"]),
            "published_at": row["evaluation_timestamp"],
            "finbert_label": article.sentiment_label if article else None,
            "finbert_score": article.sentiment_score if article else None,
            "finbert_confidence": article.model_confidence if article else None,
            "finbert_relevance": article.relevance_score if article else None,
            "finbert_impact_strength": article.impact_strength if article else None,
            "v2_final_score": row.get("signal_score"),
            "v2_original_label": row.get("original_label"),
            "v2_canonical_direction": row.get("canonical_direction"),
            "v2_confidence": row.get("signal_confidence"),
            "v2_signal_mode": row.get("signal_mode"),
            "news_available": news.get("available"),
            "news_normalized_value": news.get("normalized_value"),
            "news_contribution": news.get("contribution"),
            "news_weighted_items": (news.get("metadata") or {}).get("weighted_items") if news else None,
            "news_total_weight": (news.get("metadata") or {}).get("total_weight") if news else None,
            "news_agreement": (news.get("metadata") or {}).get("agreement") if news else None,
            "momentum_available": momentum.get("available"),
            "momentum_normalized_value": momentum.get("normalized_value"),
            "momentum_contribution": momentum.get("contribution"),
            "momentum_horizons": json.dumps((momentum.get("metadata") or {}).get("horizons", []), sort_keys=True),
            "volume_available": volume.get("available"),
            "volume_contribution": volume.get("contribution"),
            "volume_recent": (volume.get("metadata") or {}).get("recent_volume") if volume else None,
            "volume_baseline_median": (volume.get("metadata") or {}).get("baseline_volume") if volume else None,
            "volume_relative": (volume.get("metadata") or {}).get("relative_volume") if volume else None,
            "reliability_liquidity": liquidity.get("reliability"),
            "reliability_freshness": freshness.get("reliability"),
            "reliability_data_quality": quality.get("reliability"),
            "data_quality": row.get("data_quality"),
            "warnings_missing_inputs": _warnings_and_missing(row.get("component_summary")),
            "entry_price_1d": event.entry_price if event else None,
            "exit_price_1d": event.exit_price if event else None,
            "return_1d": row.get("1D_return"),
            "realized_direction_1d": row.get("1D_realized_direction"),
            "correct_1d": row.get("1D_correct"),
            "event_status_1d": row.get("1D_status"),
            "event_entry_timestamp": _event_metadata_value(event, "entry_timestamp"),
            "event_exit_timestamp": event.matched_market_timestamp.isoformat() if event and event.matched_market_timestamp else None,
            "signal_run_id": _optional_int(row.get("signal_run_id")),
        }
        rows.append(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def summarize_v2_diagnostic(diagnostic_csv: Path) -> dict[str, Any]:
    frame = pd.read_csv(diagnostic_csv)
    if frame.empty:
        return {"n": 0}
    return {
        "n": int(len(frame)),
        "signal_modes": frame["v2_signal_mode"].value_counts(dropna=False).to_dict(),
        "labels": frame["v2_original_label"].value_counts(dropna=False).to_dict(),
        "directions": frame["v2_canonical_direction"].value_counts(dropna=False).to_dict(),
        "realized": frame["realized_direction_1d"].value_counts(dropna=False).to_dict(),
        "news_available": int(frame["news_available"].fillna(False).astype(bool).sum()),
        "momentum_available": int(frame["momentum_available"].fillna(False).astype(bool).sum()),
        "volume_available": int(frame["volume_available"].fillna(False).astype(bool).sum()),
        "score_min": _float_or_none(frame["v2_final_score"].min()),
        "score_max": _float_or_none(frame["v2_final_score"].max()),
        "score_mean": _float_or_none(frame["v2_final_score"].mean()),
    }


def evaluate_rows_by_split(rows_csv: Path, *, horizon: str = "1D") -> dict[str, Any]:
    frame = pd.read_csv(rows_csv)
    output: dict[str, Any] = {"version": PHASE12_EVALUATION_VERSION, "horizon": horizon, "engines": {}, "baselines": {}, "paired": {}}
    for split in sorted(frame["split"].dropna().unique()):
        split_frame = frame[frame["split"] == split]
        output["engines"][split] = {}
        for engine in sorted(split_frame["engine"].unique()):
            pairs = _pairs(split_frame[split_frame["engine"] == engine], horizon)
            output["engines"][split][engine] = metric_payload(pairs)
        output["baselines"][split] = baseline_payload(split_frame, horizon)
        output["paired"][split] = paired_correctness_table(split_frame, horizon)
    return output


def metric_payload(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    metrics = classification_metrics(pairs)
    payload = asdict(metrics)
    payload["wilson_interval"] = list(metrics.wilson_interval) if metrics.wilson_interval else None
    return payload


def baseline_payload(split_frame: pd.DataFrame, horizon: str) -> dict[str, Any]:
    article_rows = split_frame.drop_duplicates(subset=["article_id"])
    outcomes = [str(item) for item in article_rows[f"{horizon}_realized_direction"].dropna().tolist()]
    majority = _majority(outcomes) or "NEUTRAL"
    baselines = {
        "ALWAYS_NEUTRAL": [( "NEUTRAL", outcome) for outcome in outcomes],
        "MAJORITY_CLASS": [(majority, outcome) for outcome in outcomes],
        "NEWS_DIRECTION_ONLY": [
            (signal_direction(row["original_label"]), str(row[f"{horizon}_realized_direction"]))
            for _, row in article_rows.iterrows()
            if pd.notna(row.get(f"{horizon}_realized_direction"))
        ],
    }
    return {name: metric_payload(pairs) | {"prediction_rule": name, "majority_class": majority if name == "MAJORITY_CLASS" else None} for name, pairs in baselines.items()}


def paired_correctness_table(split_frame: pd.DataFrame, horizon: str) -> dict[str, Any]:
    by_article: dict[int, dict[str, pd.Series]] = {}
    for _, row in split_frame.iterrows():
        by_article.setdefault(int(row["article_id"]), {})[str(row["engine"])] = row
    counts = {"both_correct": 0, "v1_correct_v2_wrong": 0, "v1_wrong_v2_correct": 0, "both_wrong": 0, "n": 0}
    for engines in by_article.values():
        v1 = engines.get("v1")
        v2 = engines.get("v2")
        if v1 is None or v2 is None:
            continue
        outcome = v1.get(f"{horizon}_realized_direction")
        if pd.isna(outcome):
            continue
        counts["n"] += 1
        v1_ok = signal_direction(v1.get("original_label")) == outcome
        v2_ok = signal_direction(v2.get("original_label")) == outcome
        if v1_ok and v2_ok:
            counts["both_correct"] += 1
        elif v1_ok and not v2_ok:
            counts["v1_correct_v2_wrong"] += 1
        elif not v1_ok and v2_ok:
            counts["v1_wrong_v2_correct"] += 1
        else:
            counts["both_wrong"] += 1
    counts["mcnemar"] = mcnemar_result(counts["v1_correct_v2_wrong"], counts["v1_wrong_v2_correct"])
    return counts


def mcnemar_result(v1_only: int, v2_only: int) -> dict[str, Any]:
    discordant = v1_only + v2_only
    if discordant == 0:
        return {"applicable": False, "reason": "No discordant pairs."}
    statistic = ((abs(v1_only - v2_only) - 1) ** 2) / discordant if discordant else None
    p_approx = math.erfc(math.sqrt(float(statistic or 0.0) / 2.0)) if statistic is not None else None
    return {"applicable": discordant >= 10, "discordant": discordant, "statistic": statistic, "p_value_chi_square_approx": p_approx}


def class_distribution(rows_csv: Path, *, horizon: str = "1D") -> dict[str, Any]:
    frame = pd.read_csv(rows_csv)
    output: dict[str, Any] = {}
    for split in sorted(frame["split"].dropna().unique()):
        split_frame = frame[frame["split"] == split]
        output[split] = {
            "finbert": split_frame.drop_duplicates("article_id")["original_label"].map(signal_direction).value_counts().to_dict(),
            "v1": split_frame[split_frame["engine"] == "v1"]["canonical_direction"].value_counts().to_dict(),
            "v2": split_frame[split_frame["engine"] == "v2"]["canonical_direction"].value_counts().to_dict(),
            "realized": split_frame.drop_duplicates("article_id")[f"{horizon}_realized_direction"].value_counts().to_dict(),
        }
    return output


def v2_component_summary(rows_csv: Path) -> dict[str, Any]:
    frame = pd.read_csv(rows_csv)
    v2 = frame[frame["engine"] == "v2"]
    groups: dict[str, list[float]] = {}
    correctness: dict[str, dict[str, list[float]]] = {}
    for _, row in v2.iterrows():
        components = _components_by_name(row.get("component_summary"))
        correct = str(row.get("1D_correct")).lower() == "true"
        bucket = "correct" if correct else "incorrect"
        for name, component in components.items():
            if component.get("available") and component.get("weight", 0) > 0:
                value = float(component.get("normalized_value") or 0.0)
                groups.setdefault(name, []).append(value)
                correctness.setdefault(name, {}).setdefault(bucket, []).append(value)
    return {
        name: {
            "n": len(values),
            "mean": sum(values) / len(values) if values else None,
            "correct_mean": _mean(correctness.get(name, {}).get("correct", [])),
            "incorrect_mean": _mean(correctness.get(name, {}).get("incorrect", [])),
        }
        for name, values in sorted(groups.items())
    }


def systematic_disagreement_cases(rows_csv: Path, output_path: Path, *, horizon: str = "1D", limit_per_group: int = 10) -> Path:
    frame = pd.read_csv(rows_csv)
    rows: list[dict[str, Any]] = []
    by_article = {article_id: group for article_id, group in frame.groupby("article_id")}
    for article_id, group in by_article.items():
        v1 = group[group["engine"] == "v1"]
        v2 = group[group["engine"] == "v2"]
        if v1.empty or v2.empty:
            continue
        left = v1.iloc[0]
        right = v2.iloc[0]
        outcome = left.get(f"{horizon}_realized_direction")
        v1_ok = signal_direction(left.get("original_label")) == outcome
        v2_ok = signal_direction(right.get("original_label")) == outcome
        if v1_ok == v2_ok:
            continue
        rows.append(
            {
                "article_id": int(article_id),
                "case_type": "V1_CORRECT_V2_WRONG" if v1_ok else "V1_WRONG_V2_CORRECT",
                "published_at": left.get("evaluation_timestamp"),
                "instrument": left.get("instrument"),
                "v1_score": left.get("signal_score"),
                "v1_label": left.get("original_label"),
                "v2_score": right.get("signal_score"),
                "v2_label": right.get("original_label"),
                "score_gap_abs": abs(float(left.get("signal_score") or 0.0) - float(right.get("signal_score") or 0.0)),
                "realized_direction": outcome,
                "realized_return": left.get(f"{horizon}_return"),
                "v2_components": right.get("component_summary"),
            }
        )
    selected: list[dict[str, Any]] = []
    for case_type in ("V1_CORRECT_V2_WRONG", "V1_WRONG_V2_CORRECT"):
        bucket = sorted([row for row in rows if row["case_type"] == case_type], key=lambda item: (-item["score_gap_abs"], item["article_id"]))
        selected.extend(bucket[:limit_per_group])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(selected).to_csv(output_path, index=False)
    return output_path


def render_locked_baseline_report(
    *,
    preregistration: Phase12Preregistration,
    cohort_fingerprint: str,
    rows_csv: Path,
    metrics: dict[str, Any],
    output_path: Path,
    diagnostic_summary: dict[str, Any],
) -> Path:
    distributions = class_distribution(rows_csv)
    components = v2_component_summary(rows_csv)
    lines = [
        "# Phase 12 Locked-Cohort Baseline",
        "",
        "## Preregistration",
        f"Dataset id: `{preregistration.dataset_id}`",
        f"Preregistration fingerprint: `{preregistration_fingerprint(preregistration)}`",
        "",
        "## Dataset",
        f"Source: {preregistration.source_name} / {preregistration.source_file}",
        f"Cohort fingerprint: `{cohort_fingerprint}`",
        "",
        "## Symbols",
        ", ".join(preregistration.symbols),
        "",
        "## Dates",
        f"{preregistration.start_date.isoformat()} to {preregistration.end_date.isoformat()}",
        "",
        "## Price Source",
        f"{preregistration.price_source}; basis: {preregistration.price_basis}",
        "",
        "## Sentiment Model",
        preregistration.sentiment_source,
        "",
        "## Development Split",
        json.dumps(metrics.get("engines", {}).get("DEVELOPMENT", {}), indent=2, sort_keys=True),
        "",
        "## Holdout Split",
        json.dumps(metrics.get("engines", {}).get("HOLDOUT", {}), indent=2, sort_keys=True),
        "",
        "## Class Distribution",
        json.dumps(distributions, indent=2, sort_keys=True),
        "",
        "## Baselines",
        json.dumps(metrics.get("baselines", {}), indent=2, sort_keys=True),
        "",
        "## Signal V1",
        "Metrics are split above. Interpret every percentage with its N.",
        "",
        "## Signal V2",
        "Metrics are split above. Signal V2 weights, thresholds, confidence, news decay, momentum, and volume behavior were not changed.",
        "",
        "## Paired Comparison",
        json.dumps(metrics.get("paired", {}), indent=2, sort_keys=True),
        "",
        "## Component Diagnostics",
        json.dumps(components, indent=2, sort_keys=True),
        "",
        "## Data Quality",
        json.dumps(_stringify_keys(diagnostic_summary), indent=2, sort_keys=True),
        "",
        "## Limitations",
        "Daily bars support 1D only. Gemini remains unconfigured. This is a bounded FNSPID/yfinance cohort, not a final market-wide claim.",
        "",
        "## Conclusions Allowed",
        "On this locked cohort, the exported metrics describe baseline behavior for the unchanged engines.",
        "",
        "## Conclusions NOT Allowed",
        "Do not claim a universal winner, tune V2 against these results, or infer profitability.",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def v2_parameter_registry() -> dict[str, Any]:
    config = SignalEngineV2Config()
    return {
        "news_weight": config.news_weight,
        "momentum_weight": config.momentum_weight,
        "volume_confirmation_weight": config.volume_confirmation_weight,
        "label_thresholds": {
            "strong_threshold": config.strong_threshold,
            "directional_threshold": config.directional_threshold,
        },
        "confidence_coefficients": {
            "strength": 0.35,
            "component_reliability": 0.30,
            "agreement": 0.20,
            "availability": 0.15,
        },
        "news_decay": {
            "max_news_age_hours": config.max_news_age_hours,
            "min_news_recency_weight": config.min_news_recency_weight,
        },
        "momentum_normalization": {
            "momentum_return_scale": config.momentum_return_scale,
            "horizon_weights": [0.5, 0.3, 0.2],
        },
        "volume_behavior": "confirmation-only; volume does not create independent direction",
        "read_only": True,
    }


def _write_subset(path: Path, records: list[HistoricalArticleRecord]) -> None:
    fieldnames = list(HistoricalArticleRecord("", utc_now(), "", "", None, None, "", "", "", "", "").to_csv_row())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_row())


def _components_by_name(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None or pd.isna(raw):
        return {}
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return {component.get("name"): component for component in payload.get("components", []) if component.get("name")}


def _warnings_and_missing(raw: Any) -> str:
    if raw is None or pd.isna(raw):
        return ""
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError:
        return ""
    parts = list(payload.get("warnings", []))
    missing = payload.get("missing_inputs", [])
    if missing:
        parts.append(f"missing_inputs={missing}")
    return "; ".join(str(part) for part in parts)


def _event_for_signal(session: Session, signal_run_id: int | None) -> EventStudyResult | None:
    if signal_run_id is None:
        return None
    return session.execute(
        select(EventStudyResult)
        .where(EventStudyResult.signal_run_id == signal_run_id, EventStudyResult.horizon_minutes == 1440)
        .order_by(EventStudyResult.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _event_metadata_value(event: EventStudyResult | None, key: str) -> Any:
    if event is None or not event.metadata_json:
        return None
    try:
        payload = json.loads(event.metadata_json)
    except json.JSONDecodeError:
        return None
    return payload.get(key)


def _pairs(frame: pd.DataFrame, horizon: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for _, row in frame.iterrows():
        outcome = row.get(f"{horizon}_realized_direction")
        if pd.isna(outcome):
            continue
        pairs.append((signal_direction(row.get("original_label")), str(outcome)))
    return pairs


def _majority(values: list[str]) -> str | None:
    if not values:
        return None
    counts = {value: values.count(value) for value in set(values)}
    return sorted(counts, key=lambda item: (-counts[item], DIRECTIONS.index(item) if item in DIRECTIONS else 99))[0]


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _list_get(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _stringify_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stringify_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_keys(item) for item in value]
    return value


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
