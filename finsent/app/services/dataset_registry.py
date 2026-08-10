from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy.orm import Session

from finsent.app.database.research_repository import DatasetRegistryRepository
from finsent.app.services.kaggle_data import (
    DEFAULT_INDIA_ARCHIVE_DIR,
    DEFAULT_INDIA_COMPANY_FILE,
    DEFAULT_US_COMPANY_FILE,
    DEFAULT_US_PRICE_FILE,
    is_git_lfs_pointer,
)


IMPORTANT_PRICE_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}


@dataclass(slots=True)
class DatasetScanResult:
    dataset_id: str
    name: str
    path: str
    dataset_type: str
    market: str | None
    frequency: str | None
    date_start: datetime | None
    date_end: datetime | None
    symbol_count: int | None
    row_count: int | None
    file_size_bytes: int | None
    status: str
    source: str | None
    checksum: str | None
    last_scanned_at: datetime
    columns: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    dataset_id: str
    name: str
    path: Path
    dataset_type: str
    market: str | None
    frequency: str | None
    source: str | None
    notes: str | None = None


DEFAULT_DATASET_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        "archive_v1_nse",
        "NSE archive v1",
        DEFAULT_INDIA_ARCHIVE_DIR,
        "HISTORICAL_PRICE_ARCHIVE",
        "India",
        "daily",
        "local_csv_archive",
        "Offline NSE historical/import/reference archive; not a live quote substitute.",
    ),
    DatasetSpec(
        "india_company_universe",
        "India company universe",
        DEFAULT_INDIA_COMPANY_FILE,
        "REFERENCE_UNIVERSE",
        "India",
        None,
        "local_csv_reference",
        "Reference company universe; not live price data.",
    ),
    DatasetSpec(
        "us_company_universe",
        "US company universe",
        DEFAULT_US_COMPANY_FILE,
        "REFERENCE_UNIVERSE",
        "US",
        None,
        "local_csv_reference",
        "Reference company universe; not live price data.",
    ),
    DatasetSpec(
        "sp_daily_update",
        "S&P daily update",
        DEFAULT_US_PRICE_FILE,
        "HISTORICAL_PRICE_FILE",
        "US",
        "daily",
        "local_csv",
        "Current local copy is expected to be a Git LFS pointer unless the real asset is supplied.",
    ),
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _checksum(path: Path, *, max_bytes: int = 1024 * 1024) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        remaining = max_bytes
        while remaining > 0:
            chunk = handle.read(min(65536, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _file_size(path: Path) -> int | None:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.glob("*.csv") if item.is_file())


def _missing_rates(df: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    issues: list[str] = []
    row_count = len(df)
    if row_count == 0:
        return issues
    for column in columns:
        if column not in df.columns:
            continue
        missing_rate = float(df[column].isna().sum()) / float(row_count)
        if missing_rate > 0:
            issues.append(f"{column} missing rate {missing_rate:.2%}")
    return issues


class DatasetScanner:
    def scan(self, spec: DatasetSpec, *, deep: bool = False, sample_files: int = 5) -> DatasetScanResult:
        path = spec.path
        issues: list[str] = []
        columns: list[str] = []
        date_start: datetime | None = None
        date_end: datetime | None = None
        symbol_count: int | None = None
        row_count: int | None = None
        checksum = _checksum(path)

        if not path.exists():
            return DatasetScanResult(
                dataset_id=spec.dataset_id,
                name=spec.name,
                path=str(path),
                dataset_type=spec.dataset_type,
                market=spec.market,
                frequency=spec.frequency,
                date_start=None,
                date_end=None,
                symbol_count=None,
                row_count=None,
                file_size_bytes=None,
                status="UNKNOWN",
                source=spec.source,
                checksum=None,
                last_scanned_at=_now(),
                issues=["dataset path does not exist"],
                notes=spec.notes,
            )

        if path.is_dir():
            csv_paths = sorted(path.glob("*.csv"))
            symbol_count = len(csv_paths)
            if not csv_paths:
                issues.append("directory contains no CSV files")
            inspected = csv_paths if deep else csv_paths[:sample_files]
            total_rows = 0
            for csv_path in inspected:
                try:
                    frame = pd.read_csv(csv_path)
                except Exception as exc:  # pragma: no cover - message content varies by pandas
                    issues.append(f"{csv_path.name}: read failed: {exc}")
                    continue
                total_rows += len(frame)
                if not columns:
                    columns = list(frame.columns)
                if "Date" in frame.columns:
                    parsed = pd.to_datetime(frame["Date"], utc=True, errors="coerce").dt.tz_convert(None)
                    if parsed.isna().any():
                        issues.append(f"{csv_path.name}: malformed timestamps")
                    valid = parsed.dropna()
                    if not valid.empty:
                        file_start = valid.min().to_pydatetime()
                        file_end = valid.max().to_pydatetime()
                        date_start = file_start if date_start is None else min(date_start, file_start)
                        date_end = file_end if date_end is None else max(date_end, file_end)
                    if parsed.duplicated().any():
                        issues.append(f"{csv_path.name}: duplicate dates")
                missing = IMPORTANT_PRICE_COLUMNS - set(frame.columns)
                if missing:
                    issues.append(f"{csv_path.name}: missing columns {sorted(missing)}")
                issues.extend(f"{csv_path.name}: {issue}" for issue in _missing_rates(frame, IMPORTANT_PRICE_COLUMNS))
            row_count = total_rows if deep else None
            status = "USABLE" if deep and csv_paths and not any("read failed" in issue for issue in issues) else "PARTIAL"
            if not deep and csv_paths:
                issues.append("directory scan sampled files only; run deep=True for full completeness")
            return DatasetScanResult(
                dataset_id=spec.dataset_id,
                name=spec.name,
                path=str(path),
                dataset_type=spec.dataset_type,
                market=spec.market,
                frequency=spec.frequency,
                date_start=date_start,
                date_end=date_end,
                symbol_count=symbol_count,
                row_count=row_count,
                file_size_bytes=_file_size(path),
                status=status,
                source=spec.source,
                checksum=None,
                last_scanned_at=_now(),
                columns=columns,
                issues=issues,
                notes=spec.notes,
            )

        if is_git_lfs_pointer(path):
            return DatasetScanResult(
                dataset_id=spec.dataset_id,
                name=spec.name,
                path=str(path),
                dataset_type=spec.dataset_type,
                market=spec.market,
                frequency=spec.frequency,
                date_start=None,
                date_end=None,
                symbol_count=None,
                row_count=None,
                file_size_bytes=_file_size(path),
                status="BROKEN",
                source=spec.source,
                checksum=checksum,
                last_scanned_at=_now(),
                issues=["Git LFS pointer detected; real CSV content is unavailable"],
                notes=spec.notes,
            )

        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            return DatasetScanResult(
                dataset_id=spec.dataset_id,
                name=spec.name,
                path=str(path),
                dataset_type=spec.dataset_type,
                market=spec.market,
                frequency=spec.frequency,
                date_start=None,
                date_end=None,
                symbol_count=None,
                row_count=None,
                file_size_bytes=_file_size(path),
                status="BROKEN",
                source=spec.source,
                checksum=checksum,
                last_scanned_at=_now(),
                issues=[f"CSV read failed: {exc}"],
                notes=spec.notes,
            )

        columns = list(frame.columns)
        row_count = len(frame)
        if "Date" in frame.columns:
            parsed = pd.to_datetime(frame["Date"], utc=True, errors="coerce").dt.tz_convert(None)
            if parsed.isna().any():
                issues.append("malformed timestamps")
            valid = parsed.dropna()
            if not valid.empty:
                date_start = valid.min().to_pydatetime()
                date_end = valid.max().to_pydatetime()
            if parsed.duplicated().any():
                issues.append("duplicate dates")
        if "Symbol" in frame.columns:
            symbol_count = int(frame["Symbol"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().nunique())
        elif spec.dataset_type == "REFERENCE_UNIVERSE" and "Name" in frame.columns:
            symbol_count = row_count
        missing_price_columns = IMPORTANT_PRICE_COLUMNS - set(frame.columns)
        if spec.dataset_type.startswith("HISTORICAL") and missing_price_columns:
            issues.append(f"missing columns {sorted(missing_price_columns)}")
        issues.extend(_missing_rates(frame, IMPORTANT_PRICE_COLUMNS))

        status = "REFERENCE" if spec.dataset_type == "REFERENCE_UNIVERSE" else "USABLE"
        if issues and status == "USABLE":
            status = "PARTIAL"
        return DatasetScanResult(
            dataset_id=spec.dataset_id,
            name=spec.name,
            path=str(path),
            dataset_type=spec.dataset_type,
            market=spec.market,
            frequency=spec.frequency,
            date_start=date_start,
            date_end=date_end,
            symbol_count=symbol_count,
            row_count=row_count,
            file_size_bytes=_file_size(path),
            status=status,
            source=spec.source,
            checksum=checksum,
            last_scanned_at=_now(),
            columns=columns,
            issues=issues,
            notes=spec.notes,
        )

    def scan_defaults(self, *, deep_archive: bool = False) -> list[DatasetScanResult]:
        results: list[DatasetScanResult] = []
        for spec in DEFAULT_DATASET_SPECS:
            results.append(self.scan(spec, deep=deep_archive if spec.path.is_dir() else False))
        return results


def register_scan_results(session: Session, results: Iterable[DatasetScanResult]) -> list[object]:
    repo = DatasetRegistryRepository(session)
    rows = []
    for result in results:
        rows.append(
            repo.upsert_metadata(
                dataset_id=result.dataset_id,
                name=result.name,
                path=result.path,
                dataset_type=result.dataset_type,
                market=result.market,
                frequency=result.frequency,
                date_start=result.date_start,
                date_end=result.date_end,
                symbol_count=result.symbol_count,
                row_count=result.row_count,
                file_size_bytes=result.file_size_bytes,
                status=result.status,
                source=result.source,
                checksum=result.checksum,
                columns=result.columns,
                issues=result.issues,
                notes=result.notes,
                last_scanned_at=result.last_scanned_at,
            )
        )
    return rows


def scan_and_register_defaults(session: Session, *, deep_archive: bool = False) -> list[object]:
    return register_scan_results(session, DatasetScanner().scan_defaults(deep_archive=deep_archive))
