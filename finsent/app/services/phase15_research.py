from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import csv
import io
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd
import requests

from finsent.app.services.historical_news_acquisition import (
    DEFAULT_RESEARCH_SOURCE_DIR,
    FNSPIDAdapter,
    FNSPID_NEWS_URL,
    HistoricalArticleRecord,
    file_sha256,
    relative_path,
    write_manifest,
)
from finsent.app.services.phase13_research import FinalHoldoutEvaluationError, to_jsonable
from finsent.app.services.phase14_research import FINAL_HOLDOUT_V2_DATASET_ID
from finsent.app.services.research_dataset import ResearchCohort, ResearchCohortConfig


PHASE15_OUTPUT_DIR = Path("output") / "research" / "phase15"
FINAL_HOLDOUT_V3_DATASET_ID = "phase15_final_holdout_v3"
FINAL_HOLDOUT_V3_STATUS = "FINAL_HOLDOUT_V3_LOCKED"
FNSPID_NASDAQ_SIZE_BYTES = 23_232_979_597
FNSPID_LAYOUT_VERSION = "fnspid_alphabetic_ticker_ranges_v1"
TARGET_SYMBOLS = ["AAPL", "AMZN", "GOOGL", "NVDA", "TSLA"]
SUPPORTED_SOURCE_SYMBOLS = ["AAPL", "AMZN", "NVDA", "TSLA"]
SOURCE_SYMBOL_NOTE = "FNSPID Nasdaq source uses GOOG in the Alphabet region; local registry supports GOOGL, so GOOG is documented but not forced into the final holdout."


TICKER_BYTE_WINDOWS: dict[str, tuple[int, int]] = {
    "AAPL": (80_000_000, 170_000_000),
    "AMZN": (1_430_000_000, 1_520_000_000),
    "NVDA": (11_330_000_000, 11_410_000_000),
    "TSLA": (15_040_000_000, 15_100_000_000),
}


@dataclass(frozen=True, slots=True)
class FinalHoldoutV3Preregistration:
    dataset_id: str = FINAL_HOLDOUT_V3_DATASET_ID
    source_name: str = "FNSPID"
    source_file: str = "Stock_news/nasdaq_exteral_data.csv"
    source_url: str = FNSPID_NEWS_URL
    cutoff_after: datetime = datetime(2020, 6, 15, 23, 59, 59)
    availability_start: datetime = datetime(2023, 1, 1)
    availability_end: datetime = datetime(2023, 12, 31, 23, 59, 59)
    window_days: int = 90
    per_symbol_quota: int = 40
    target_symbols: list[str] = field(default_factory=lambda: TARGET_SYMBOLS.copy())
    acquisition_symbols: list[str] = field(default_factory=lambda: SUPPORTED_SOURCE_SYMBOLS.copy())
    minimum_symbols: int = 3
    minimum_total_eligible: int = 90
    minimum_per_symbol_eligible: int = 20
    price_source: str = "yahoo_chart_daily"
    price_basis: str = "unadjusted quote.close"
    price_buffer_days_before: int = 30
    price_buffer_days_after: int = 10
    sentiment_model_for_phase16: str = "FinBERT, same frozen model/text policy as development"
    event_horizon: str = "1d"
    realized_neutral_threshold: float = 0.001
    selection_rule: str = "Earliest 90-day future window with >=3 supported symbols, >=20 candidate articles per represented symbol, and >=90 total candidate articles; tie-break by represented symbol count then balance."
    within_symbol_sampling: str = "Chronological evenly spaced sample across the selected window if records exceed quota."
    dedupe_policy: str = "FNSPID source id/symbol/date/url/title hash plus database URL uniqueness."

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("cutoff_after", "availability_start", "availability_end"):
            payload[key] = getattr(self, key).isoformat()
        payload["fingerprint"] = stable_fingerprint(payload)
        return payload


@dataclass(slots=True)
class AvailabilitySummary:
    by_symbol_month: dict[str, dict[str, int]]
    source_records_by_symbol: dict[str, int]
    source_windows: dict[str, tuple[int, int]]
    notes: list[str]


@dataclass(slots=True)
class WindowSelection:
    start_date: datetime | None
    end_date: datetime | None
    represented_symbols: list[str]
    candidate_counts: dict[str, int]
    adequate: bool
    blockers: list[str]
    algorithm: str


@dataclass(slots=True)
class AcquisitionSummaryV3:
    selected_window: WindowSelection
    requested_symbols: list[str]
    acquired_counts: dict[str, int]
    source_candidate_counts: dict[str, int]
    duplicate_rows: int
    written_rows: int
    subset_path: str | None
    checksum_sha256: str | None
    source_bytes_requested: int


@dataclass(slots=True)
class LockSummaryV3:
    dataset_id: str
    status: str
    adequate: bool
    blockers: list[str]
    fingerprint: str
    candidate_n: int
    technically_eligible_n: int
    eligible_per_symbol: dict[str, int]
    article_ids: list[int]
    date_start: str | None
    date_end: str | None
    manifest_path: str | None


def assert_not_final_holdout_v3(dataset_id: str | None, *, purpose: str, final_evaluation_mode: bool = False) -> None:
    if final_evaluation_mode:
        return
    if (dataset_id or "").strip() in {FINAL_HOLDOUT_V2_DATASET_ID, FINAL_HOLDOUT_V3_DATASET_ID}:
        raise FinalHoldoutEvaluationError(f"Refusing {purpose} for {dataset_id}; Phase 15 has no final evaluation path.")


class RemoteRangeFNSPIDReader:
    header = "Unnamed: 0,Date,Article_title,Stock_symbol,Url,Publisher,Author,Article,Lsa_summary,Luhn_summary,Textrank_summary,Lexrank_summary\n"
    record_start = re.compile(r"(?:^|\n)(\d+\.0,\d{4}-\d{2}-\d{2} [^,]* UTC,)")

    def __init__(self, *, source_url: str = FNSPID_NEWS_URL, chunk_bytes: int = 5_000_000, timeout_seconds: int = 45) -> None:
        csv.field_size_limit(sys.maxsize)
        self.source_url = source_url
        self.chunk_bytes = chunk_bytes
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FinSent/Phase15 remote range acquisition"})
        self.bytes_requested = 0

    def records_for_symbol(self, symbol: str, start_byte: int, end_byte: int) -> list[HistoricalArticleRecord]:
        adapter = FNSPIDAdapter()
        records: list[HistoricalArticleRecord] = []
        seen: set[str] = set()
        original_source_file = adapter.source_file
        adapter.source_file = "Stock_news/nasdaq_exteral_data.csv"
        try:
            for offset in range(start_byte, end_byte, self.chunk_bytes):
                upper = min(end_byte - 1, offset + self.chunk_bytes - 1)
                response = self.session.get(self.source_url, headers={"Range": f"bytes={offset}-{upper}"}, timeout=self.timeout_seconds)
                response.raise_for_status()
                self.bytes_requested += len(response.content)
                text = response.content.decode("utf-8", errors="ignore")
                starts = [match.start(1) for match in self.record_start.finditer(text)]
                for left, right in zip(starts[1:], starts[2:]):
                    row = self._parse_record(text[left:right])
                    if not row or (row.get("Stock_symbol") or "").upper() != symbol:
                        continue
                    record, reason = adapter.normalize_row(row, row_number=_safe_int(row.get("Unnamed: 0")) or 0)
                    if reason is not None or record is None:
                        continue
                    if record.dedupe_hash in seen:
                        continue
                    seen.add(record.dedupe_hash)
                    records.append(record)
        finally:
            adapter.source_file = original_source_file
        return sorted(records, key=lambda item: (item.symbol, item.published_at, item.source_record_id))

    def _parse_record(self, raw_record: str) -> dict[str, Any] | None:
        try:
            return next(csv.DictReader(io.StringIO(self.header + raw_record)))
        except Exception:
            return None


def build_availability(reader: RemoteRangeFNSPIDReader, prereg: FinalHoldoutV3Preregistration) -> tuple[AvailabilitySummary, dict[str, list[HistoricalArticleRecord]]]:
    records_by_symbol: dict[str, list[HistoricalArticleRecord]] = {}
    by_month: dict[str, dict[str, int]] = {}
    for symbol in prereg.acquisition_symbols:
        start, end = TICKER_BYTE_WINDOWS[symbol]
        records = [
            record
            for record in reader.records_for_symbol(symbol, start, end)
            if prereg.availability_start <= record.published_at <= prereg.availability_end
        ]
        records_by_symbol[symbol] = records
        month_counts: dict[str, int] = {}
        for record in records:
            key = record.published_at.strftime("%Y-%m")
            month_counts[key] = month_counts.get(key, 0) + 1
        by_month[symbol] = dict(sorted(month_counts.items()))
    return (
        AvailabilitySummary(
            by_symbol_month=by_month,
            source_records_by_symbol={symbol: len(records) for symbol, records in records_by_symbol.items()},
            source_windows=TICKER_BYTE_WINDOWS,
            notes=[SOURCE_SYMBOL_NOTE, "No full 23GB source download; bounded byte ranges only."],
        ),
        records_by_symbol,
    )


def select_window(records_by_symbol: dict[str, list[HistoricalArticleRecord]], prereg: FinalHoldoutV3Preregistration) -> WindowSelection:
    start = prereg.availability_start
    latest_start = prereg.availability_end - timedelta(days=prereg.window_days - 1)
    best_failed: WindowSelection | None = None
    while start <= latest_start:
        end = start + timedelta(days=prereg.window_days - 1, hours=23, minutes=59, seconds=59)
        counts = {
            symbol: sum(1 for record in records if start <= record.published_at <= end)
            for symbol, records in records_by_symbol.items()
        }
        represented = [symbol for symbol, count in counts.items() if count >= prereg.minimum_per_symbol_eligible]
        total = sum(counts[symbol] for symbol in represented)
        blockers: list[str] = []
        if len(represented) < prereg.minimum_symbols:
            blockers.append("INSUFFICIENT_SYMBOL_DIVERSITY")
        if total < prereg.minimum_total_eligible:
            blockers.append("INSUFFICIENT_TOTAL_CANDIDATE_ARTICLES")
        candidate = WindowSelection(start, end, represented, counts, not blockers, blockers, prereg.selection_rule)
        if candidate.adequate:
            return candidate
        if best_failed is None or (len(represented), total) > (len(best_failed.represented_symbols), sum(best_failed.candidate_counts.values())):
            best_failed = candidate
        start += timedelta(days=1)
    return best_failed or WindowSelection(None, None, [], {}, False, ["NO_WINDOWS_AVAILABLE"], prereg.selection_rule)


def select_records_for_window(records_by_symbol: dict[str, list[HistoricalArticleRecord]], selection: WindowSelection, prereg: FinalHoldoutV3Preregistration) -> list[HistoricalArticleRecord]:
    if selection.start_date is None or selection.end_date is None:
        return []
    selected: list[HistoricalArticleRecord] = []
    for symbol in prereg.acquisition_symbols:
        pool = [
            record
            for record in records_by_symbol.get(symbol, [])
            if selection.start_date <= record.published_at <= selection.end_date
        ]
        selected.extend(evenly_spaced(pool, prereg.per_symbol_quota))
    return sorted(selected, key=lambda item: (item.symbol, item.published_at, item.source_record_id))


def evenly_spaced(records: list[HistoricalArticleRecord], limit: int) -> list[HistoricalArticleRecord]:
    ordered = sorted(records, key=lambda item: (item.published_at, item.source_record_id))
    if len(ordered) <= limit:
        return ordered
    if limit <= 0:
        return []
    if limit == 1:
        return [ordered[0]]
    indexes = sorted({round(index * (len(ordered) - 1) / (limit - 1)) for index in range(limit)})
    while len(indexes) < limit:
        for candidate in range(len(ordered)):
            if candidate not in indexes:
                indexes.append(candidate)
                if len(indexes) == limit:
                    break
    return [ordered[index] for index in sorted(indexes[:limit])]


def write_subset(records: list[HistoricalArticleRecord], target: Path, prereg: FinalHoldoutV3Preregistration, *, source_bytes_requested: int) -> tuple[Path, Path, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(HistoricalArticleRecord("", utc_now(), "", "", None, None, "", "", "", "", "").to_csv_row())
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_csv_row())
    checksum = file_sha256(target)
    manifest = write_manifest(
        DEFAULT_RESEARCH_SOURCE_DIR / "fnspid" / "MANIFEST.json",
        {
            "source_name": "FNSPID",
            "source_identifier": "Zihan1004/FNSPID",
            "source_url": prereg.source_url,
            "source_file": prereg.source_file,
            "dataset_version": "Hugging Face dataset repo current main at acquisition time",
            "acquired_at": utc_now().isoformat(),
            "adapter_version": "fnspid_phase15_remote_range_adapter_v1",
            "selection_version": FNSPID_LAYOUT_VERSION,
            "filters": prereg.to_dict(),
            "record_count": len(records),
            "per_symbol_counts": count_records(records),
            "checksum_sha256": checksum,
            "local_relative_path": relative_path(target),
            "source_bytes_requested": source_bytes_requested,
            "full_source_downloaded": False,
            "dry_run": False,
        },
    )
    return target, manifest, checksum


def count_records(records: list[HistoricalArticleRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.symbol] = counts.get(record.symbol, 0) + 1
    return dict(sorted(counts.items()))


def build_acquisition_summary(selection: WindowSelection, records: list[HistoricalArticleRecord], records_by_symbol: dict[str, list[HistoricalArticleRecord]], prereg: FinalHoldoutV3Preregistration, *, subset_path: Path | None, checksum: str | None, source_bytes_requested: int) -> AcquisitionSummaryV3:
    selected_hashes: set[str] = set()
    duplicates = 0
    for record in records:
        if record.dedupe_hash in selected_hashes:
            duplicates += 1
        selected_hashes.add(record.dedupe_hash)
    return AcquisitionSummaryV3(
        selected_window=selection,
        requested_symbols=prereg.target_symbols,
        acquired_counts=count_records(records),
        source_candidate_counts={symbol: len(items) for symbol, items in records_by_symbol.items()},
        duplicate_rows=duplicates,
        written_rows=len(records) if subset_path else 0,
        subset_path=str(subset_path) if subset_path else None,
        checksum_sha256=checksum,
        source_bytes_requested=source_bytes_requested,
    )


def lock_summary_from_cohort(cohort: ResearchCohort, prereg: FinalHoldoutV3Preregistration, *, manifest_path: str | None) -> LockSummaryV3:
    eligible_per_symbol: dict[str, int] = {}
    eligible_articles: list[int] = []
    eligible_dates: list[datetime] = []
    for sample in cohort.samples:
        coverage = sample.coverage.get("1D")
        if coverage and coverage.valid:
            eligible_per_symbol[sample.instrument.ticker] = eligible_per_symbol.get(sample.instrument.ticker, 0) + 1
            eligible_articles.append(sample.article_id)
            eligible_dates.append(sample.published_at)
    blockers: list[str] = []
    represented = [symbol for symbol, count in eligible_per_symbol.items() if count >= prereg.minimum_per_symbol_eligible]
    if len(represented) < prereg.minimum_symbols:
        blockers.append("INSUFFICIENT_SYMBOL_DIVERSITY")
    if sum(eligible_per_symbol.values()) < prereg.minimum_total_eligible:
        blockers.append("INSUFFICIENT_TOTAL_TECHNICAL_COVERAGE")
    adequate = not blockers
    fingerprint_payload = {
        "dataset_id": prereg.dataset_id,
        "config": prereg.to_dict(),
        "cohort_fingerprint": cohort.fingerprint,
        "eligible_article_ids": sorted(eligible_articles),
        "eligible_per_symbol": eligible_per_symbol,
        "price_source": prereg.price_source,
        "price_basis": prereg.price_basis,
        "event_horizon": prereg.event_horizon,
    }
    return LockSummaryV3(
        dataset_id=prereg.dataset_id,
        status=FINAL_HOLDOUT_V3_STATUS if adequate else "FINAL_HOLDOUT_NOT_READY",
        adequate=adequate,
        blockers=blockers,
        fingerprint=stable_fingerprint(fingerprint_payload),
        candidate_n=len(cohort.samples),
        technically_eligible_n=sum(eligible_per_symbol.values()),
        eligible_per_symbol=dict(sorted(eligible_per_symbol.items())),
        article_ids=[sample.article_id for sample in cohort.samples],
        date_start=min(eligible_dates).isoformat() if eligible_dates else None,
        date_end=max(eligible_dates).isoformat() if eligible_dates else None,
        manifest_path=manifest_path,
    )


def write_lock_manifest(path: Path, lock: LockSummaryV3, acquisition: AcquisitionSummaryV3, availability: AvailabilitySummary, prereg: FinalHoldoutV3Preregistration) -> Path:
    payload = {
        "holdout_version": "v3",
        "status": lock.status,
        "performance_evaluated": False,
        "finbert_run": False,
        "signal_runs_created": False,
        "lock": asdict(lock),
        "acquisition": asdict(acquisition),
        "availability": asdict(availability),
        "preregistration": prereg.to_dict(),
        "created_at": utc_now().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True), encoding="utf-8")
    return path


def render_report(path: Path, *, layout: dict[str, Any], availability: AvailabilitySummary, acquisition: AcquisitionSummaryV3, lock: LockSummaryV3, prereg: FinalHoldoutV3Preregistration) -> Path:
    lines = [
        "# Phase 15 Final Holdout Acquisition",
        "",
        "FINAL PERFORMANCE NOT EVALUATED.",
        "",
        "## Why Phase 14 Holdout Failed",
        "Previous bounded prefix scans started at byte zero in an alphabetically ticker-sorted CSV, so early tickers consumed scan budget before later target symbols were reached.",
        "",
        "## FNSPID Physical Layout",
        json.dumps(to_jsonable(layout), indent=2, sort_keys=True),
        "",
        "## Previous Sampling Bug / Limitation",
        "Filtering occurred after source iteration, and acquisition stopped at global scan caps. In a ticker-grouped source, this is not a stratified sample.",
        "",
        "## New Acquisition Method",
        "Remote HTTP byte-range ticker-region extraction with independent per-symbol quotas and chronological evenly spaced within-symbol sampling.",
        "",
        "## Availability by Symbol",
        json.dumps(to_jsonable(asdict(availability)), indent=2, sort_keys=True),
        "",
        "## Window Selection Rule",
        prereg.selection_rule,
        "",
        "## Selected Window",
        json.dumps(to_jsonable(asdict(acquisition.selected_window)), indent=2, sort_keys=True),
        "",
        "## Article Acquisition",
        json.dumps(to_jsonable(asdict(acquisition)), indent=2, sort_keys=True),
        "",
        "## Price Coverage",
        f"Yahoo chart daily prices with {prereg.price_buffer_days_before} days before and {prereg.price_buffer_days_after} days after the selected window.",
        "",
        "## Adequacy",
        json.dumps(to_jsonable(asdict(lock)), indent=2, sort_keys=True),
        "",
        "## Fingerprint",
        lock.fingerprint,
        "",
        "## Lock Status",
        lock.status,
        "",
        "## Performance Status",
        "Predictive performance, realized directions, returns, FinBERT outputs, and Signal V1/V2 runs were not generated.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def source_layout_summary() -> dict[str, Any]:
    return {
        "source_file": "Stock_news/nasdaq_exteral_data.csv",
        "size_bytes": FNSPID_NASDAQ_SIZE_BYTES,
        "organization": "Rows are clustered/sorted by Stock_symbol alphabetically; dates within symbol are generally reverse chronological or mixed by source region.",
        "sampled_regions": {
            "0": "A",
            "80_000_000": "AAP/AAPL region",
            "1_450_000_000": "AMZN region",
            "8_200_000_000": "GOOG region; GOOGL not observed as supported source symbol",
            "11_350_000_000": "NVDA region",
            "15_050_000_000": "TSLA region",
        },
        "alternative_formats": "Hugging Face API exposes All_external.csv and nasdaq_exteral_data.csv only; no Parquet files reported.",
        "full_source_downloaded": False,
    }


def stable_fingerprint(payload: Any) -> str:
    return sha256(json.dumps(to_jsonable(payload), sort_keys=True).encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _safe_int(value: Any) -> int | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return int(parsed) if math.isfinite(parsed) else None
