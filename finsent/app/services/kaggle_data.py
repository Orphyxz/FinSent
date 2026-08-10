from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import csv

import pandas as pd

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.repository import PriceRepository


ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_INDIA_COMPANY_FILE = ROOT_DIR / "All_Indian_Stocks_listed_in_nifty500.csv"
DEFAULT_US_COMPANY_FILE = ROOT_DIR / "6000 Largest Companies ranked by Market Cap.csv"
DEFAULT_INDIA_ARCHIVE_DIR = ROOT_DIR / "archive" / "v1"
DEFAULT_US_PRICE_FILE = ROOT_DIR / "SnP_daily_update.csv"
GIT_LFS_POINTER_HEADER = "version https://git-lfs.github.com/spec/v1"


@dataclass(slots=True)
class CompanyUniverse:
    ticker: str
    name: str
    sector: str
    market: str


def is_git_lfs_pointer(csv_path: Path) -> bool:
    if not csv_path.exists() or not csv_path.is_file():
        return False
    try:
        with csv_path.open("r", encoding="utf-8", errors="ignore") as handle:
            first_line = handle.readline().strip()
    except OSError:
        return False
    return first_line == GIT_LFS_POINTER_HEADER


def ensure_real_csv_data(csv_path: Path, label: str) -> None:
    if is_git_lfs_pointer(csv_path):
        raise ValueError(
            f"{label} at {csv_path} is a Git LFS pointer, not the actual CSV data. "
            "Fetch the LFS asset or provide the real dataset before importing."
        )


def _normalize_sector(value: object, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


@lru_cache(maxsize=1)
def load_company_universe(
    india_company_file: Path | None = None,
    us_company_file: Path | None = None,
    max_us_companies: int = 250,
) -> list[CompanyUniverse]:
    india_company_file = india_company_file or DEFAULT_INDIA_COMPANY_FILE
    us_company_file = us_company_file or DEFAULT_US_COMPANY_FILE

    companies: list[CompanyUniverse] = []
    seen: set[str] = set()

    if india_company_file.exists():
        india_df = pd.read_csv(india_company_file)
        for _, row in india_df.iterrows():
            symbol = str(row.get("Symbol", "")).strip().upper()
            if not symbol:
                continue
            ticker = f"{symbol}.NS"
            if ticker in seen:
                continue
            companies.append(
                CompanyUniverse(
                    ticker=ticker,
                    name=str(row.get("Company Name", ticker)).strip(),
                    sector=_normalize_sector(row.get("Industry"), "India"),
                    market="India",
                )
            )
            seen.add(ticker)

    if us_company_file.exists():
        us_df = pd.read_csv(us_company_file)
        if "country" in us_df.columns:
            us_df = us_df[us_df["country"].fillna("").str.lower() == "united states"]
        if "Rank" in us_df.columns:
            us_df = us_df.sort_values("Rank", ascending=True)
        us_df = us_df.head(max_us_companies)

        for _, row in us_df.iterrows():
            ticker = str(row.get("Symbol", "")).strip().upper()
            if not ticker or ticker in seen:
                continue
            companies.append(
                CompanyUniverse(
                    ticker=ticker,
                    name=str(row.get("Name", ticker)).strip(),
                    sector="United States",
                    market="US",
                )
            )
            seen.add(ticker)

    return companies


def load_nse_price_frame(csv_path: Path) -> tuple[str, pd.DataFrame]:
    df = pd.read_csv(csv_path)
    required = {"Date", "Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path.name} is missing required columns: {sorted(missing)}")

    df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce").dt.tz_convert(None)
    df = df.dropna(subset=["Date"]).copy()
    df = df.rename(columns={"Date": "timestamp"})
    df = df[["timestamp", "Open", "High", "Low", "Close", "Volume"]]
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df = df.set_index("timestamp")

    ticker = csv_path.stem.upper()
    return ticker, df


def import_nse_archive(
    archive_dir: Path | None = None,
    tickers: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    archive_dir = archive_dir or DEFAULT_INDIA_ARCHIVE_DIR
    if not archive_dir.exists():
        raise FileNotFoundError(f"NSE archive directory not found: {archive_dir}")

    requested = {ticker.upper() for ticker in (tickers or [])}
    imported_rows: dict[str, int] = {}
    csv_paths = sorted(archive_dir.glob("*.csv"))

    if limit is not None:
        csv_paths = csv_paths[:limit]

    init_db()
    with SessionLocal() as session:
        price_repo = PriceRepository(session)
        for csv_path in csv_paths:
            ticker = csv_path.stem.upper()
            if requested and ticker not in requested:
                continue
            symbol, price_frame = load_nse_price_frame(csv_path)
            if price_frame.empty:
                continue
            price_repo.upsert_price_bars(symbol, price_frame)
            imported_rows[symbol] = len(price_frame)
            session.commit()
            session.expire_all()

    return imported_rows


def _load_us_header_map(csv_path: Path) -> tuple[list[str], list[str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        metric_row = next(reader)
        ticker_row = next(reader)
    return metric_row, ticker_row


def _resolve_us_usecols(
    csv_path: Path,
    tickers: list[str] | None = None,
) -> tuple[list[int], dict[str, dict[str, int]]]:
    metric_row, ticker_row = _load_us_header_map(csv_path)
    requested = {ticker.upper() for ticker in (tickers or [])}
    metrics_needed = {"Open", "High", "Low", "Close", "Volume"}

    selected_indices = [0]
    ticker_metric_map: dict[str, dict[str, int]] = {}

    for idx in range(1, min(len(metric_row), len(ticker_row))):
        metric = str(metric_row[idx]).strip()
        ticker = str(ticker_row[idx]).strip().upper()
        if not ticker or metric not in metrics_needed:
            continue
        if requested and ticker not in requested:
            continue
        selected_indices.append(idx)
        ticker_metric_map.setdefault(ticker, {})[metric] = idx

    if not ticker_metric_map:
        return [0], {}

    selected_indices = sorted(set(selected_indices))
    return selected_indices, ticker_metric_map


def load_us_price_frames(
    csv_path: Path | None = None,
    tickers: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    csv_path = csv_path or DEFAULT_US_PRICE_FILE
    if not csv_path.exists():
        raise FileNotFoundError(f"US price file not found: {csv_path}")
    ensure_real_csv_data(csv_path, "US price file")

    usecols, ticker_metric_map = _resolve_us_usecols(csv_path, tickers=tickers)
    if not ticker_metric_map:
        return {}

    raw = pd.read_csv(csv_path, skiprows=3, header=None, usecols=usecols)
    raw = raw.rename(columns={0: "Date"})
    raw["Date"] = pd.to_datetime(raw["Date"], utc=True, errors="coerce").dt.tz_convert(None)
    raw = raw.dropna(subset=["Date"]).copy()

    frames: dict[str, pd.DataFrame] = {}
    for ticker, metric_map in ticker_metric_map.items():
        if not {"Open", "High", "Low", "Close", "Volume"}.issubset(metric_map):
            continue

        frame = pd.DataFrame(
            {
                "timestamp": raw["Date"],
                "Open": pd.to_numeric(raw[metric_map["Open"]], errors="coerce"),
                "High": pd.to_numeric(raw[metric_map["High"]], errors="coerce"),
                "Low": pd.to_numeric(raw[metric_map["Low"]], errors="coerce"),
                "Close": pd.to_numeric(raw[metric_map["Close"]], errors="coerce"),
                "Volume": pd.to_numeric(raw[metric_map["Volume"]], errors="coerce"),
            }
        )
        frame = frame.dropna(subset=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        frame = frame.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").set_index("timestamp")
        if not frame.empty:
            frames[ticker] = frame

    return frames


def import_us_daily_update(
    csv_path: Path | None = None,
    tickers: list[str] | None = None,
) -> dict[str, int]:
    frames = load_us_price_frames(csv_path=csv_path, tickers=tickers)
    if not frames:
        return {}

    imported_rows: dict[str, int] = {}
    init_db()
    with SessionLocal() as session:
        price_repo = PriceRepository(session)
        for ticker, frame in sorted(frames.items()):
            price_repo.upsert_price_bars(ticker, frame)
            imported_rows[ticker] = len(frame)
            session.commit()
            session.expire_all()
    return imported_rows
