from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.analysis.event_study_v2 import EventStudyHorizon, EventStudyStatus
from finsent.app.database.entities import NewsArticle
from finsent.app.database.research_repository import ArticleRelationshipRepository, InstrumentRepository
from finsent.app.services.event_study_service_v2 import EventStudyServiceV2
from finsent.app.services.news_providers import build_article_dedupe_hash
from finsent.app.services.symbol_registry import SymbolRecord, registry


class ResearchArticleStatus:
    ELIGIBLE = "ELIGIBLE"
    PARTIALLY_ELIGIBLE = "PARTIALLY_ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class ResearchCohortExclusion:
    MISSING_TITLE = "MISSING_TITLE"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    MISSING_INSTRUMENT = "MISSING_INSTRUMENT"
    DUPLICATE_ARTICLE = "DUPLICATE_ARTICLE"
    NO_PRICE_COVERAGE = "NO_PRICE_COVERAGE"
    INVALID_EVENT_STUDY = "INVALID_EVENT_STUDY"
    UNSUPPORTED_GRANULARITY = "UNSUPPORTED_GRANULARITY"
    SAMPLE_LIMIT = "SAMPLE_LIMIT"
    BELOW_MINIMUM_QUALITY = "BELOW_MINIMUM_QUALITY"


@dataclass(frozen=True, slots=True)
class ResearchArticleImportConfig:
    source_file: Path
    dataset_id: str
    source_name: str = "local_csv"
    default_provider: str = "local_import"
    default_exchange: str | None = None
    limit: int = 25
    dry_run: bool = True


@dataclass(slots=True)
class ResearchArticleImportSummary:
    source_file: str
    dataset_id: str
    parsed: int
    valid: int
    imported: int
    duplicates: int
    invalid: int
    invalid_reasons: dict[str, int]
    dry_run: bool


@dataclass(frozen=True, slots=True)
class ResearchCohortConfig:
    symbols: list[str] = field(default_factory=list)
    markets: list[str] = field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    horizons: list[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    limit: int = 25
    seed: int = 42
    minimum_data_quality_label: str | None = None
    holdout_start: datetime | None = None
    dataset_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["start_date"] = self.start_date.isoformat() if self.start_date else None
        payload["end_date"] = self.end_date.isoformat() if self.end_date else None
        payload["holdout_start"] = self.holdout_start.isoformat() if self.holdout_start else None
        return payload


@dataclass(slots=True)
class CoverageByHorizon:
    horizon: str
    valid: bool
    status: str
    raw_return: float | None = None


@dataclass(slots=True)
class ResearchCohortSample:
    article_id: int
    instrument: SymbolRecord
    published_at: datetime
    title: str
    dedupe_key: str
    split: str
    coverage: dict[str, CoverageByHorizon]
    status: str
    exclusion_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResearchCohort:
    config: ResearchCohortConfig
    samples: list[ResearchCohortSample]
    excluded_count: int
    exclusion_counts: dict[str, int]
    coverage_summary: dict[str, Any]
    fingerprint: str


class LocalResearchArticleImporter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_file(self, config: ResearchArticleImportConfig) -> ResearchArticleImportSummary:
        frame = pd.read_csv(config.source_file)
        invalid: dict[str, int] = {}
        parsed = 0
        valid_rows: list[dict[str, Any]] = []
        for _, row in frame.head(max(config.limit, 0)).iterrows():
            parsed += 1
            normalized, reason = self._normalize_row(row, config)
            if reason is not None:
                invalid[reason] = invalid.get(reason, 0) + 1
                continue
            assert normalized is not None
            valid_rows.append(normalized)
        duplicates = 0
        imported = 0
        if not config.dry_run:
            for item in valid_rows:
                if self._existing(item["dedupe_hash"], item["url"]) is not None:
                    duplicates += 1
                    continue
                article = NewsArticle(**item)
                self.session.add(article)
                self.session.flush()
                symbol = registry.get(article.exchange or "", article.ticker)
                if symbol is not None:
                    instrument = InstrumentRepository(self.session).get_or_create_from_symbol(symbol)
                    article.instrument_id = instrument.id
                    ArticleRelationshipRepository(self.session).link_article_to_instrument(
                        article_id=article.id,
                        instrument_id=instrument.id,
                        relevance_score=article.relevance_score,
                        association_source="research_article_import",
                    )
                imported += 1
        return ResearchArticleImportSummary(
            source_file=str(config.source_file),
            dataset_id=config.dataset_id,
            parsed=parsed,
            valid=len(valid_rows),
            imported=imported,
            duplicates=duplicates,
            invalid=sum(invalid.values()),
            invalid_reasons=invalid,
            dry_run=config.dry_run,
        )

    def _normalize_row(self, row: pd.Series, config: ResearchArticleImportConfig) -> tuple[dict[str, Any] | None, str | None]:
        title = _clean_text(row.get("title")) or _clean_text(row.get("headline")) or ""
        if not title:
            return None, ResearchCohortExclusion.MISSING_TITLE
        timestamp_raw = row.get("published_at") if "published_at" in row else row.get("timestamp")
        published_at = pd.to_datetime(timestamp_raw, utc=True, errors="coerce")
        if pd.isna(published_at):
            return None, ResearchCohortExclusion.MISSING_TIMESTAMP
        raw_symbol = _clean_text(row.get("symbol")) or _clean_text(row.get("ticker")) or ""
        exchange = (_clean_text(row.get("exchange")) or config.default_exchange or "").strip().upper()
        symbol = registry.resolve_any(raw_symbol) if raw_symbol else None
        if symbol is None and exchange and raw_symbol:
            symbol = registry.get(exchange, raw_symbol.replace(".NS", "").replace(".BO", ""))
        if symbol is None:
            return None, ResearchCohortExclusion.MISSING_INSTRUMENT
        source = _clean_text(row.get("source")) or _clean_text(row.get("publisher")) or config.source_name
        url = _clean_text(row.get("url")) or f"local://{config.dataset_id}/{sha256((title + str(published_at)).encode()).hexdigest()}"
        summary = _clean_text(row.get("summary")) or _clean_text(row.get("description"))
        dt = published_at.to_pydatetime().replace(tzinfo=None)
        dedupe_hash = _clean_text(row.get("dedupe_hash")) or build_article_dedupe_hash(title=title, url=url, source=source, published_at=dt)
        return {
            "ticker": symbol.ticker,
            "exchange": symbol.exchange,
            "source": source,
            "provider": config.default_provider,
            "source_provider": config.source_name,
            "leaf_provider": config.default_provider,
            "data_mode": "HISTORICAL_IMPORT",
            "publisher": source,
            "original_url": url,
            "canonical_url": url.lower(),
            "raw_symbol": raw_symbol or symbol.provider_symbol,
            "title": title,
            "summary": summary,
            "url": url,
            "published_at": dt,
            "ingested_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "dedupe_hash": dedupe_hash,
            "relevance_score": _clean_float(row.get("relevance_score"), 1.0),
            "sentiment_label": (_clean_text(row.get("sentiment_label")) or "neutral").lower(),
            "sentiment_score": _clean_float(row.get("sentiment_score"), 0.0),
            "model_confidence": _clean_float(row.get("model_confidence"), 0.0),
            "signal_confidence": _clean_float(row.get("signal_confidence"), 0.0),
            "impact_strength": _clean_float(row.get("impact_strength"), 0.5),
            "relevant": 1,
            "analysis_provider": _clean_text(row.get("analysis_provider")) or "imported_stored_sentiment",
            "parse_status": _clean_text(row.get("parse_status")) or "imported",
        }, None

    def _existing(self, dedupe_hash: str, url: str) -> NewsArticle | None:
        return self.session.execute(
            select(NewsArticle)
            .where((NewsArticle.dedupe_hash == dedupe_hash) | (NewsArticle.url == url))
            .limit(1)
        ).scalar_one_or_none()


class ResearchCoverageAnalyzer:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.event_service = EventStudyServiceV2(session=session)

    def coverage_for_article(self, article: NewsArticle, symbol: SymbolRecord, horizons: list[str]) -> dict[str, CoverageByHorizon]:
        from finsent.app.database.repository import PriceRepository

        price_df = PriceRepository(self.session).list_price_df(symbol.ticker)
        if price_df.empty:
            return {EventStudyHorizon.parse(h).label: CoverageByHorizon(EventStudyHorizon.parse(h).label, False, "NO_PRICE_COVERAGE") for h in horizons}
        study_input = self.event_service.build_input(
            instrument=symbol,
            event_timestamp=article.published_at,
            price_bars=price_df,
            horizons=[EventStudyHorizon.parse(value) for value in horizons],
            article_id=article.id,
            provider=article.provider,
            source=article.source,
        )
        coverage: dict[str, CoverageByHorizon] = {}
        for record in self.event_service.evaluate(study_input, persist=False):
            result = record.result
            coverage[result.horizon.label] = CoverageByHorizon(
                horizon=result.horizon.label,
                valid=result.status == EventStudyStatus.VALID,
                status=result.status.value,
                raw_return=result.raw_return,
            )
        return coverage


class ResearchCohortBuilder:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.coverage = ResearchCoverageAnalyzer(session)

    def build(self, config: ResearchCohortConfig) -> ResearchCohort:
        rows = self._candidate_articles(config)
        samples: list[ResearchCohortSample] = []
        exclusions: dict[str, int] = {}
        seen: set[str] = set()
        for article in rows:
            symbol = self._symbol(article)
            reasons: list[str] = []
            key = article.dedupe_hash or article.url or f"{article.ticker}:{article.published_at}:{article.title}"
            if key in seen:
                reasons.append(ResearchCohortExclusion.DUPLICATE_ARTICLE)
            if symbol is None:
                reasons.append(ResearchCohortExclusion.MISSING_INSTRUMENT)
            if not article.title:
                reasons.append(ResearchCohortExclusion.MISSING_TITLE)
            if article.published_at is None:
                reasons.append(ResearchCohortExclusion.MISSING_TIMESTAMP)
            if reasons:
                for reason in reasons:
                    exclusions[reason] = exclusions.get(reason, 0) + 1
                continue
            assert symbol is not None
            seen.add(key)
            coverage = self.coverage.coverage_for_article(article, symbol, config.horizons)
            valid_any = any(item.valid for item in coverage.values())
            if not valid_any:
                reason = ResearchCohortExclusion.NO_PRICE_COVERAGE if all(item.status == "NO_PRICE_COVERAGE" for item in coverage.values()) else ResearchCohortExclusion.INVALID_EVENT_STUDY
                exclusions[reason] = exclusions.get(reason, 0) + 1
            split = "HOLDOUT" if config.holdout_start and article.published_at >= config.holdout_start else "DEVELOPMENT"
            status = ResearchArticleStatus.ELIGIBLE if valid_any else ResearchArticleStatus.PARTIALLY_ELIGIBLE
            samples.append(
                ResearchCohortSample(
                    article_id=article.id,
                    instrument=symbol,
                    published_at=article.published_at,
                    title=article.title,
                    dedupe_key=key,
                    split=split,
                    coverage=coverage,
                    status=status,
                    exclusion_reasons=[] if valid_any else [reason],
                )
            )
        capped = self._sample(samples, config.limit, config.seed)
        if len(samples) > len(capped):
            exclusions[ResearchCohortExclusion.SAMPLE_LIMIT] = exclusions.get(ResearchCohortExclusion.SAMPLE_LIMIT, 0) + len(samples) - len(capped)
        cohort = ResearchCohort(
            config=config,
            samples=capped,
            excluded_count=sum(exclusions.values()),
            exclusion_counts=exclusions,
            coverage_summary=self._coverage_summary(capped, config.horizons),
            fingerprint="",
        )
        cohort.fingerprint = cohort_fingerprint(cohort)
        return cohort

    def _candidate_articles(self, config: ResearchCohortConfig) -> list[NewsArticle]:
        stmt = select(NewsArticle).order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
        if config.start_date:
            stmt = stmt.where(NewsArticle.published_at >= config.start_date)
        if config.end_date:
            stmt = stmt.where(NewsArticle.published_at <= config.end_date)
        if config.markets:
            stmt = stmt.where(NewsArticle.exchange.in_([item.upper() for item in config.markets]))
        if config.symbols:
            tickers = [item.upper().replace(".NS", "").replace(".BO", "").split(":")[-1] for item in config.symbols]
            stmt = stmt.where(NewsArticle.ticker.in_(tickers))
        return self.session.execute(stmt).scalars().all()

    @staticmethod
    def _symbol(article: NewsArticle) -> SymbolRecord | None:
        if article.exchange and article.ticker:
            symbol = registry.get(article.exchange, article.ticker)
            if symbol is not None:
                return symbol
        return registry.resolve_any(article.raw_symbol or article.ticker or "")

    @staticmethod
    def _sample(samples: list[ResearchCohortSample], limit: int, seed: int) -> list[ResearchCohortSample]:
        if len(samples) <= max(limit, 0):
            return samples
        selected = random.Random(seed).sample(samples, max(limit, 0))
        return sorted(selected, key=lambda item: (item.published_at, item.article_id))

    @staticmethod
    def _coverage_summary(samples: list[ResearchCohortSample], horizons: list[str]) -> dict[str, Any]:
        summary = {"articles": len(samples), "with_instrument": len(samples), "with_historical_bars": 0, "horizons": {}}
        for horizon in [EventStudyHorizon.parse(value).label for value in horizons]:
            valid = sum(1 for sample in samples if sample.coverage.get(horizon) and sample.coverage[horizon].valid)
            no_coverage = sum(1 for sample in samples if sample.coverage.get(horizon) and sample.coverage[horizon].status == "NO_PRICE_COVERAGE")
            unsupported = sum(1 for sample in samples if sample.coverage.get(horizon) and sample.coverage[horizon].status == "UNSUPPORTED_GRANULARITY")
            summary["horizons"][horizon] = {"eligible": valid, "no_coverage": no_coverage, "unsupported_granularity": unsupported}
        summary["with_historical_bars"] = sum(1 for sample in samples if any(item.status != "NO_PRICE_COVERAGE" for item in sample.coverage.values()))
        return summary


def cohort_fingerprint(cohort: ResearchCohort) -> str:
    payload = {
        "config": cohort.config.to_dict(),
        "samples": [
            {
                "article_id": sample.article_id,
                "dedupe_key": sample.dedupe_key,
                "instrument": f"{sample.instrument.exchange}:{sample.instrument.ticker}",
                "horizons": sorted(sample.coverage),
            }
            for sample in cohort.samples
        ],
    }
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _clean_float(value: Any, default: float) -> float:
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
