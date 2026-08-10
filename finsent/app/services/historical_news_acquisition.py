from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from finsent.app.database.entities import NewsArticle, PriceBar
from finsent.app.database.repository import PriceRepository
from finsent.app.database.research_repository import DatasetRegistryRepository, InstrumentRepository
from finsent.app.services.research_dataset import LocalResearchArticleImporter, ResearchArticleImportConfig
from finsent.app.services.sentiment_v2 import GeminiSentimentAnalyzer
from finsent.app.services.symbol_registry import registry


FNSPID_NEWS_URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv"
FNSPID_REPO_ID = "Zihan1004/FNSPID"
FNSPID_ADAPTER_VERSION = "fnspid_adapter_v1"
DEFAULT_RESEARCH_SOURCE_DIR = Path("data") / "research_sources"
DEFAULT_NORMALIZED_DIR = Path("data") / "research"
DEFAULT_USER_AGENT = "FinSent/Phase11 research cohort preparation"


class SourceDecision:
    PREFERRED = "PREFERRED"
    SECONDARY = "SECONDARY"
    DEFERRED = "DEFERRED"
    REJECTED = "REJECTED"


class SourceReadiness:
    READY = "READY"
    UNCONFIGURED = "UNCONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True, slots=True)
class FNSPIDAcquisitionConfig:
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    limit: int = 100
    max_scan_rows: int = 200_000
    cache_dir: Path = DEFAULT_RESEARCH_SOURCE_DIR
    batch_id: str | None = None
    dry_run: bool = True
    source_url: str = FNSPID_NEWS_URL
    request_timeout_seconds: int = 30

    def normalized_symbols(self) -> list[str]:
        return sorted({symbol.upper().strip() for symbol in self.symbols if symbol.strip()})

    def to_manifest_filters(self) -> dict[str, Any]:
        return {
            "symbols": self.normalized_symbols(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "limit": self.limit,
            "max_scan_rows": self.max_scan_rows,
        }


@dataclass(slots=True)
class HistoricalArticleRecord:
    source_record_id: str
    published_at: datetime
    symbol: str
    title: str
    summary: str | None
    url: str | None
    publisher: str
    source_dataset: str
    source_file: str
    dedupe_hash: str
    canonical_text_hash: str

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "source_record_id": self.source_record_id,
            "published_at": self.published_at.isoformat(),
            "symbol": self.symbol,
            "exchange": "US",
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "source": self.publisher,
            "publisher": self.publisher,
            "dataset_source": self.source_dataset,
            "source_file": self.source_file,
            "dedupe_hash": self.dedupe_hash,
            "canonical_text_hash": self.canonical_text_hash,
        }


@dataclass(slots=True)
class AcquisitionSummary:
    source_name: str
    dry_run: bool
    requested_symbols: list[str]
    start_date: datetime
    end_date: datetime
    scanned_rows: int
    matched_rows: int
    written_rows: int
    invalid_rows: int
    invalid_reasons: dict[str, int]
    duplicate_rows: int
    scan_limit_reached: bool
    subset_path: str | None
    manifest_path: str | None
    checksum_sha256: str | None
    estimated_disk_bytes: int | None
    records: list[HistoricalArticleRecord] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PriceAcquisitionConfig:
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    source_name: str = "yfinance_daily"
    cache_dir: Path = DEFAULT_RESEARCH_SOURCE_DIR
    batch_id: str | None = None
    dry_run: bool = True


@dataclass(slots=True)
class PriceAcquisitionSummary:
    source_name: str
    dry_run: bool
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    imported_rows: dict[str, int]
    written_files: list[str]
    manifest_path: str | None
    failures: dict[str, str]


@dataclass(slots=True)
class SourceCandidateEvaluation:
    source: str
    decision: str
    readiness: str
    rationale: str
    credential_required: bool
    supports_historical_dates: bool
    supported_markets: list[str]
    compatible_horizons: list[str]
    notes: list[str] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def default_batch_id(prefix: str) -> str:
    return f"{prefix}_{utc_now().strftime('%Y%m%dT%H%M%SZ')}"


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def text_hash(title: str, summary: str | None) -> str:
    return sha256("\n".join(part for part in [title, summary] if part).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path, root: Path | None = None) -> str:
    root = root or Path.cwd()
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


class FNSPIDAdapter:
    source_dataset = "fnspid"
    source_file = "Stock_news/nasdaq_exteral_data.csv"

    def normalize_row(self, row: dict[str, Any], *, row_number: int) -> tuple[HistoricalArticleRecord | None, str | None]:
        title = clean_text(row.get("Article_title"))
        if title is None:
            return None, "MISSING_TEXT"
        symbol = clean_text(row.get("Stock_symbol"))
        if symbol is None:
            return None, "MISSING_SYMBOL"
        symbol = symbol.upper()
        if registry.get("US", symbol) is None:
            return None, "UNSUPPORTED_SYMBOL"
        timestamp = pd.to_datetime(row.get("Date"), utc=True, errors="coerce")
        if pd.isna(timestamp):
            return None, "MISSING_TIMESTAMP"
        published_at = timestamp.to_pydatetime().replace(tzinfo=None)
        summary = self._summary(row)
        if summary is None and title is None:
            return None, "MISSING_TEXT"
        url = clean_text(row.get("Url"))
        publisher = clean_text(row.get("Publisher")) or "FNSPID"
        source_record_id = clean_text(row.get("Unnamed: 0")) or str(row_number)
        canonical_hash = text_hash(title, summary)
        dedupe = sha256(
            "|".join(
                [
                    self.source_dataset,
                    self.source_file,
                    source_record_id,
                    symbol,
                    published_at.isoformat(),
                    url or "",
                    title,
                ]
            ).encode("utf-8")
        ).hexdigest()
        return (
            HistoricalArticleRecord(
                source_record_id=source_record_id,
                published_at=published_at,
                symbol=symbol,
                title=title,
                summary=summary,
                url=url,
                publisher=publisher,
                source_dataset=self.source_dataset,
                source_file=self.source_file,
                dedupe_hash=dedupe,
                canonical_text_hash=canonical_hash,
            ),
            None,
        )

    @staticmethod
    def _summary(row: dict[str, Any]) -> str | None:
        for column in ("Lsa_summary", "Luhn_summary", "Textrank_summary", "Lexrank_summary"):
            text = clean_text(row.get(column))
            if text:
                return text[:2_000]
        article = clean_text(row.get("Article"))
        return article[:1_000] if article else None


class FNSPIDPartialAcquirer:
    def __init__(self, *, session_factory: requests.Session | None = None, adapter: FNSPIDAdapter | None = None) -> None:
        self.session = session_factory or requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
        self.adapter = adapter or FNSPIDAdapter()

    def acquire(self, config: FNSPIDAcquisitionConfig) -> AcquisitionSummary:
        requested = set(config.normalized_symbols())
        invalid: dict[str, int] = {}
        seen: set[str] = set()
        records: list[HistoricalArticleRecord] = []
        scanned = 0
        duplicate_rows = 0
        response = self.session.get(config.source_url, stream=True, timeout=config.request_timeout_seconds)
        response.raise_for_status()
        estimated_disk = _safe_int(response.headers.get("content-length"))
        response.raw.decode_content = True
        text_stream = io.TextIOWrapper(response.raw, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text_stream)
        for scanned, row in enumerate(reader, start=1):
            if scanned > max(config.max_scan_rows, 0):
                break
            symbol = clean_text(row.get("Stock_symbol"))
            if requested and (symbol or "").upper() not in requested:
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
            if len(records) >= max(config.limit, 0):
                break
        scan_limit_reached = scanned >= max(config.max_scan_rows, 0) and len(records) < max(config.limit, 0)
        subset_path = None
        manifest_path = None
        checksum = None
        if not config.dry_run:
            batch_id = config.batch_id or default_batch_id("fnspid")
            subset_dir = config.cache_dir / "fnspid" / "subsets"
            subset_dir.mkdir(parents=True, exist_ok=True)
            target = subset_dir / f"{batch_id}.csv"
            self._write_subset(target, records)
            checksum = file_sha256(target)
            manifest_path = write_manifest(
                config.cache_dir / "fnspid" / "MANIFEST.json",
                {
                    "source_name": "FNSPID",
                    "source_identifier": FNSPID_REPO_ID,
                    "source_url": config.source_url,
                    "source_file": self.adapter.source_file,
                    "dataset_version": "Hugging Face dataset repo current main at acquisition time",
                    "acquired_at": utc_now().isoformat(),
                    "adapter_version": FNSPID_ADAPTER_VERSION,
                    "license_citation_note": "FNSPID dataset card lists CC BY-NC-4.0; GitHub README says commercial/research rights were released in 2025. Cite Dong, Fan, Peng (2024).",
                    "filters": config.to_manifest_filters(),
                    "record_count": len(records),
                    "scanned_rows": scanned,
                    "checksum_sha256": checksum,
                    "local_relative_path": relative_path(target),
                    "dry_run": False,
                },
            )
            subset_path = str(target)
        return AcquisitionSummary(
            source_name="FNSPID",
            dry_run=config.dry_run,
            requested_symbols=config.normalized_symbols(),
            start_date=config.start_date,
            end_date=config.end_date,
            scanned_rows=scanned,
            matched_rows=len(records),
            written_rows=0 if config.dry_run else len(records),
            invalid_rows=sum(invalid.values()),
            invalid_reasons=invalid,
            duplicate_rows=duplicate_rows,
            scan_limit_reached=scan_limit_reached,
            subset_path=subset_path,
            manifest_path=str(manifest_path) if manifest_path else None,
            checksum_sha256=checksum,
            estimated_disk_bytes=estimated_disk,
            records=records,
        )

    @staticmethod
    def _write_subset(path: Path, records: list[HistoricalArticleRecord]) -> None:
        fieldnames = list(HistoricalArticleRecord("", utc_now(), "", "", None, None, "", "", "", "", "").to_csv_row())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record.to_csv_row())


class ResearchSubsetImporter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_fnspid_subset(self, subset_path: Path, *, dataset_id: str, dry_run: bool) -> Any:
        summary = LocalResearchArticleImporter(self.session).import_file(
            ResearchArticleImportConfig(
                source_file=subset_path,
                dataset_id=dataset_id,
                source_name="fnspid",
                default_provider="fnspid",
                default_exchange="US",
                limit=10_000,
                dry_run=dry_run,
            )
        )
        if not dry_run:
            subset_row_count = len(pd.read_csv(subset_path))
            DatasetRegistryRepository(self.session).upsert_metadata(
                dataset_id=dataset_id,
                name="FNSPID bounded historical news subset",
                path=relative_path(subset_path),
                dataset_type="historical_news_subset",
                status="ACTIVE",
                market="US",
                frequency="event",
                row_count=subset_row_count,
                file_size_bytes=subset_path.stat().st_size if subset_path.exists() else None,
                source="FNSPID",
                checksum=file_sha256(subset_path) if subset_path.exists() else None,
                columns=list(pd.read_csv(subset_path, nrows=0).columns),
                issues=summary.invalid_reasons,
                notes="Bounded FNSPID historical-news import. Full FNSPID dataset was not downloaded.",
            )
        return summary


class YFinanceDailyPriceAcquirer:
    def acquire(self, config: PriceAcquisitionConfig, *, session: Session | None = None) -> PriceAcquisitionSummary:
        import yfinance as yf

        failures: dict[str, str] = {}
        imported: dict[str, int] = {}
        written_files: list[str] = []
        batch_id = config.batch_id or default_batch_id("yfinance_daily")
        target_dir = config.cache_dir / "yfinance_daily" / "prices" / batch_id
        if not config.dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        for symbol in sorted({item.upper().strip() for item in config.symbols if item.strip()}):
            try:
                frame = yf.download(
                    tickers=symbol,
                    start=config.start_date.date().isoformat(),
                    end=(config.end_date + pd.Timedelta(days=3)).date().isoformat(),
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
            except Exception as exc:
                failures[symbol] = str(exc)
                continue
            frame = normalize_yfinance_frame(frame)
            if frame.empty:
                failures[symbol] = "No daily price rows returned."
                continue
            if not config.dry_run:
                path = target_dir / f"{symbol}.csv"
                frame.to_csv(path)
                written_files.append(relative_path(path))
                if session is not None:
                    session.execute(
                        delete(PriceBar).where(
                            PriceBar.ticker == symbol,
                            PriceBar.provider == config.source_name,
                            PriceBar.dataset_id == batch_id,
                        )
                    )
                    PriceRepository(session).upsert_price_bars(
                        symbol,
                        frame,
                        provider=config.source_name,
                        dataset_id=batch_id,
                        data_mode="HISTORICAL_RESEARCH",
                        quality_status="RESEARCH_DAILY",
                    )
            imported[symbol] = len(frame)
        manifest_path = None
        if not config.dry_run:
            manifest_path = write_manifest(
                config.cache_dir / "yfinance_daily" / "MANIFEST.json",
                {
                    "source_name": "yfinance_daily",
                    "source_identifier": "Yahoo Finance via yfinance",
                    "acquired_at": utc_now().isoformat(),
                    "adapter_version": "yfinance_daily_price_adapter_v1",
                    "filters": {
                        "symbols": sorted({item.upper().strip() for item in config.symbols if item.strip()}),
                        "start_date": config.start_date.isoformat(),
                        "end_date": config.end_date.isoformat(),
                        "frequency": "1d",
                    },
                    "record_count": sum(imported.values()),
                    "local_relative_path": relative_path(target_dir),
                    "written_files": written_files,
                    "failures": failures,
                    "dry_run": False,
                },
            )
        return PriceAcquisitionSummary(
            source_name=config.source_name,
            dry_run=config.dry_run,
            symbols=sorted({item.upper().strip() for item in config.symbols if item.strip()}),
            start_date=config.start_date,
            end_date=config.end_date,
            imported_rows=imported,
            written_files=written_files,
            manifest_path=str(manifest_path) if manifest_path else None,
            failures=failures,
        )


def normalize_yfinance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    work = frame.copy()
    if isinstance(work.columns, pd.MultiIndex):
        work.columns = work.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in work.columns]
    if missing:
        return pd.DataFrame(columns=required)
    work.index = pd.to_datetime(work.index, errors="coerce")
    if getattr(work.index, "tz", None) is not None:
        work.index = work.index.tz_localize(None)
    work = work.dropna(subset=required)
    work = work[required].drop_duplicates().sort_index()
    close_timestamps: list[datetime] = []
    ny = ZoneInfo("America/New_York")
    for timestamp in pd.to_datetime(work.index, errors="coerce"):
        local_close = datetime.combine(timestamp.date(), datetime.min.time().replace(hour=16), ny)
        close_timestamps.append(local_close.astimezone(timezone.utc).replace(tzinfo=None))
    work.index = pd.DatetimeIndex(close_timestamps)
    return work


def write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            existing = raw if isinstance(raw, list) else [raw]
        except json.JSONDecodeError:
            existing = []
    existing.append(to_jsonable(payload))
    path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
    return path


def export_normalized_articles(records: Iterable[HistoricalArticleRecord], path: Path) -> Path:
    rows = [record.to_csv_row() for record in records]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def evaluate_source_candidates() -> list[SourceCandidateEvaluation]:
    return [
        SourceCandidateEvaluation(
            source="FNSPID",
            decision=SourceDecision.PREFERRED,
            readiness=SourceReadiness.READY,
            rationale="Public research dataset with historical news, timestamps, tickers, source URLs, publisher metadata, and reproducible citation. Full download is large, so Phase 11 uses bounded streaming subsets only.",
            credential_required=False,
            supports_historical_dates=True,
            supported_markets=["US"],
            compatible_horizons=["1D with daily prices", "1H/4H only if separate intraday bars are available"],
            notes=["Hugging Face raw CSV is very large; do not download fully by default."],
        ),
        SourceCandidateEvaluation(
            source="Marketaux historical news",
            decision=SourceDecision.SECONDARY,
            readiness=SourceReadiness.UNCONFIGURED,
            rationale="Legitimate provider-grade API with entity/ticker linkage and date filters, but no local token is configured.",
            credential_required=True,
            supports_historical_dates=True,
            supported_markets=["US", "NSE", "BSE"],
            compatible_horizons=["Depends on paired price source"],
            notes=["Use only bounded date ranges and pagination when configured."],
        ),
        SourceCandidateEvaluation(
            source="Polygon News",
            decision=SourceDecision.SECONDARY,
            readiness=SourceReadiness.UNCONFIGURED,
            rationale="Legitimate provider-grade US news API with published_utc filters, but no local Polygon key is configured.",
            credential_required=True,
            supports_historical_dates=True,
            supported_markets=["US"],
            compatible_horizons=["Depends on paired price source"],
            notes=["Current app provider focuses latest fetches; Phase 11 would need bounded historical params."],
        ),
        SourceCandidateEvaluation(
            source="Alpaca News",
            decision=SourceDecision.SECONDARY,
            readiness=SourceReadiness.UNCONFIGURED,
            rationale="Alpaca documents historical news back to 2015 and symbol/date filters, but local Alpaca keys are absent.",
            credential_required=True,
            supports_historical_dates=True,
            supported_markets=["US"],
            compatible_horizons=["Depends on paired price source"],
            notes=["Bounded pagination required; default endpoint limit is small."],
        ),
        SourceCandidateEvaluation(
            source="Yahoo HTML scraping",
            decision=SourceDecision.REJECTED,
            readiness=SourceReadiness.DEFERRED,
            rationale="Useful runtime fallback but too brittle and insufficiently reproducible as the primary historical research corpus.",
            credential_required=False,
            supports_historical_dates=False,
            supported_markets=["US", "NSE", "BSE"],
            compatible_horizons=["Not suitable as primary source"],
            notes=["Keep as fallback only."],
        ),
    ]


def readiness_report() -> dict[str, Any]:
    import importlib.util

    return {
        "finbert_dependencies_available": importlib.util.find_spec("torch") is not None and importlib.util.find_spec("transformers") is not None,
        "gemini_configured": bool(GeminiSentimentAnalyzer().configured),
    }


def article_rows_for_sentiment(session: Session, *, symbols: list[str], start_date: datetime, end_date: datetime, provider: str = "fnspid", limit: int = 20) -> list[NewsArticle]:
    tickers = [symbol.upper().strip() for symbol in symbols]
    stmt = (
        select(NewsArticle)
        .where(
            NewsArticle.provider == provider,
            NewsArticle.ticker.in_(tickers),
            NewsArticle.published_at >= start_date,
            NewsArticle.published_at <= end_date,
        )
        .order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
        .limit(max(0, min(limit, 50)))
    )
    return session.execute(stmt).scalars().all()


def apply_sentiment_result_to_article(article: NewsArticle, result: Any) -> None:
    article.sentiment_label = result.sentiment_label
    article.sentiment_score = result.sentiment_score
    article.model_label = result.sentiment_label
    article.model_confidence = result.confidence
    article.signal_confidence = result.confidence
    article.relevant = 1 if result.relevance is None or result.relevance > 0 else 0
    article.impact_strength = result.impact_strength if result.impact_strength is not None else 0.5
    article.time_horizon = result.time_horizon
    article.catalyst_tag = result.catalyst_tag
    article.short_reason = result.short_reason
    article.analysis_provider = result.actual_analyzer
    article.parse_status = result.parse_status


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return relative_path(value)
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def _safe_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
