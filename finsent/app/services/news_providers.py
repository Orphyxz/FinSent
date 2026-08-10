from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Protocol

import requests

from finsent.app.config.settings import settings
from finsent.app.scrapers.yahoo_finance import YahooFinanceScraper
from finsent.app.services.provider_status import ProviderStatus
from finsent.app.services.symbol_registry import SymbolRecord


MAX_NEWS_LIMIT = 50
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(slots=True)
class NormalizedNewsArticle:
    article_id: str
    ticker: str
    exchange: str
    source: str
    title: str
    summary: str | None
    url: str
    published_at: datetime
    ingested_at: datetime
    provider: str
    dedupe_hash: str
    relevance_score: float | None = None
    provider_status: ProviderStatus | None = None


class NewsProvider(Protocol):
    provider_name: str

    def fetch_news(self, symbol: SymbolRecord, limit: int = 20) -> list[NormalizedNewsArticle]:
        ...


class AlpacaNewsProvider:
    provider_name = "alpaca"
    provider_tier = "provider-grade"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_news(self, symbol: SymbolRecord, limit: int = 20) -> list[NormalizedNewsArticle]:
        if symbol.exchange != "US" or not settings.alpaca_api_key or not settings.alpaca_api_secret:
            return []
        limit = normalize_news_limit(limit)
        if limit == 0:
            return []
        response = self.session.get(
            f"{settings.alpaca_data_base_url.rstrip('/')}/v1beta1/news",
            params={"symbols": symbol.ticker, "limit": limit, "sort": "desc"},
            headers={
                "accept": "application/json",
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json() or {}
        results = payload.get("news") or []
        return [self._normalize(symbol, item) for item in results if isinstance(item, dict)]

    def _normalize(self, symbol: SymbolRecord, item: dict[str, object]) -> NormalizedNewsArticle:
        title = str(item.get("headline") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        published_at = _coerce_datetime(item.get("created_at") or item.get("updated_at")) or datetime.now(timezone.utc).replace(tzinfo=None)
        source = str(item.get("source") or "Benzinga").strip() or "Benzinga"
        summary = str(item.get("summary") or "").strip() or None
        dedupe_hash = build_article_dedupe_hash(title=title, url=url, source=source, published_at=published_at)
        provider_status = ProviderStatus.available_status(self.provider_name, "news", "Alpaca/Benzinga news article normalized", source_timestamp=published_at)
        return NormalizedNewsArticle(
            article_id=str(item.get("id") or dedupe_hash),
            ticker=symbol.ticker,
            exchange=symbol.exchange,
            source=source,
            title=title,
            summary=summary,
            url=url,
            published_at=published_at,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            dedupe_hash=dedupe_hash,
            relevance_score=1.0,
            provider_status=provider_status,
        )


class PolygonNewsProvider:
    provider_name = "polygon"
    provider_tier = "provider-grade"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_news(self, symbol: SymbolRecord, limit: int = 20) -> list[NormalizedNewsArticle]:
        if symbol.exchange != "US" or not settings.polygon_api_key:
            return []
        limit = normalize_news_limit(limit)
        if limit == 0:
            return []
        response = self.session.get(
            f"{settings.polygon_base_url.rstrip('/')}/v2/reference/news",
            params={
                "ticker": symbol.polygon_symbol or symbol.ticker,
                "limit": limit,
                "order": "desc",
                "sort": "published_utc",
                "apiKey": settings.polygon_api_key,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        return [self._normalize(symbol, item) for item in results if isinstance(item, dict)]

    def _normalize(self, symbol: SymbolRecord, item: dict[str, object]) -> NormalizedNewsArticle:
        title = str(item.get("title", "")).strip()
        url = str(item.get("article_url", "")).strip()
        published_at = self._coerce_datetime(item.get("published_utc")) or datetime.now(timezone.utc).replace(tzinfo=None)
        provider_status = ProviderStatus.available_status(self.provider_name, "news", "Polygon news article normalized", source_timestamp=published_at)
        dedupe_hash = build_article_dedupe_hash(title=title, url=url, source="Polygon", published_at=published_at)
        return NormalizedNewsArticle(
            article_id=str(item.get("id") or dedupe_hash),
            ticker=symbol.ticker,
            exchange=symbol.exchange,
            source=str(item.get("publisher", {}).get("name", "Polygon")) if isinstance(item.get("publisher"), dict) else "Polygon",
            title=title,
            summary=str(item.get("description", "")).strip() or None,
            url=url,
            published_at=published_at,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            dedupe_hash=dedupe_hash,
            relevance_score=1.0,
            provider_status=provider_status,
        )

    @staticmethod
    def _coerce_datetime(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)


class CuratedWebNewsProvider:
    provider_name = "fallback_web"
    provider_tier = "fallback-quality"

    def __init__(self) -> None:
        self.scraper = YahooFinanceScraper()
        self.leaf_provider = "unavailable"
        self.data_mode = "UNKNOWN"

    def fetch_news(self, symbol: SymbolRecord, limit: int = 20) -> list[NormalizedNewsArticle]:
        limit = normalize_news_limit(limit)
        if limit == 0:
            return []
        # Fallback provider for markets without a stronger direct news integration yet.
        raw_articles = self.scraper.fetch_latest(
            ticker=f"{symbol.ticker}.NS" if symbol.exchange == "NSE" else f"{symbol.ticker}.BO" if symbol.exchange == "BSE" else symbol.ticker,
            limit=limit,
        )
        self.leaf_provider = self.scraper.last_leaf_provider
        self.data_mode = self.scraper.last_data_mode
        articles: list[NormalizedNewsArticle] = []
        for item in raw_articles:
            provider_status = ProviderStatus.degraded(
                self.provider_name,
                "news",
                "Fallback web news article normalized",
                source_timestamp=item.published_at,
            )
            dedupe_hash = build_article_dedupe_hash(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=item.published_at,
            )
            articles.append(
                NormalizedNewsArticle(
                    article_id=dedupe_hash,
                    ticker=symbol.ticker,
                    exchange=symbol.exchange,
                    source=item.source,
                    title=item.title,
                    summary=item.summary,
                    url=item.url,
                    published_at=item.published_at,
                    ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    provider=self.provider_name,
                    dedupe_hash=dedupe_hash,
                    relevance_score=None,
                    provider_status=provider_status,
                )
            )
        return articles


class MarketauxNewsProvider:
    provider_name = "marketaux"
    provider_tier = "provider-grade"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_news(self, symbol: SymbolRecord, limit: int = 20) -> list[NormalizedNewsArticle]:
        if symbol.exchange not in {"US", "NSE", "BSE"} or not settings.marketaux_api_token:
            return []
        limit = normalize_news_limit(limit)
        if limit == 0:
            return []

        articles = self._fetch_by_symbols(symbol, limit=limit)
        if articles:
            return articles
        return self._fetch_by_company_name(symbol, limit=limit)

    def _fetch_by_symbols(self, symbol: SymbolRecord, limit: int) -> list[NormalizedNewsArticle]:
        candidates = self._symbol_candidates(symbol)
        response = self.session.get(
            f"{settings.marketaux_base_url.rstrip('/')}/news/all",
            params={
                "api_token": settings.marketaux_api_token,
                "symbols": ",".join(candidates),
                "filter_entities": "true",
                "language": "en",
                "limit": limit,
                "must_have_entities": "true",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("data") or []
        return self._normalize_articles(symbol, results)

    def _fetch_by_company_name(self, symbol: SymbolRecord, limit: int) -> list[NormalizedNewsArticle]:
        country = "us" if symbol.exchange == "US" else "in"
        response = self.session.get(
            f"{settings.marketaux_base_url.rstrip('/')}/news/all",
            params={
                "api_token": settings.marketaux_api_token,
                "search": symbol.display_name,
                "countries": country,
                "language": "en",
                "limit": limit,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("data") or []
        return self._normalize_articles(symbol, results)

    def _normalize_articles(self, symbol: SymbolRecord, results: list[object]) -> list[NormalizedNewsArticle]:
        articles: list[NormalizedNewsArticle] = []
        seen: set[str] = set()
        candidates = set(self._symbol_candidates(symbol))

        for item in results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            if not title or not url:
                continue
            published_at = self._coerce_datetime(item.get("published_at")) or datetime.now(timezone.utc).replace(tzinfo=None)
            source = str(item.get("source", "Marketaux")).strip() or "Marketaux"
            dedupe_hash = build_article_dedupe_hash(title=title, url=url, source=source, published_at=published_at)
            if dedupe_hash in seen:
                continue
            entities = item.get("entities") or []
            relevance = self._relevance_for_symbol(symbol, entities, candidates)
            if relevance <= 0:
                continue
            provider_status = ProviderStatus.available_status(self.provider_name, "news", "Marketaux news article normalized", source_timestamp=published_at)
            articles.append(
                NormalizedNewsArticle(
                    article_id=str(item.get("uuid") or dedupe_hash),
                    ticker=symbol.ticker,
                    exchange=symbol.exchange,
                    source=source,
                    title=title,
                    summary=str(item.get("description", "")).strip() or None,
                    url=url,
                    published_at=published_at,
                    ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    provider=self.provider_name,
                    dedupe_hash=dedupe_hash,
                    relevance_score=relevance,
                    provider_status=provider_status,
                )
            )
            seen.add(dedupe_hash)
        return articles

    @staticmethod
    def _symbol_candidates(symbol: SymbolRecord) -> list[str]:
        if symbol.exchange == "US":
            return [symbol.ticker]
        if symbol.exchange == "NSE":
            return [f"{symbol.ticker}.NS", symbol.ticker]
        if symbol.exchange == "BSE":
            return [f"{symbol.ticker}.BO", symbol.ticker]
        return [symbol.ticker]

    @staticmethod
    def _coerce_datetime(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _relevance_for_symbol(symbol: SymbolRecord, entities: list[object], candidates: set[str]) -> float:
        best = 0.0
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_symbol = str(entity.get("symbol", "")).strip().upper()
            entity_name = str(entity.get("name", "")).strip().lower()
            if entity_symbol and entity_symbol in {candidate.upper() for candidate in candidates}:
                return 1.0
            if entity_name and entity_name == symbol.display_name.strip().lower():
                best = max(best, 0.8)
        return best


def build_news_provider(symbol: SymbolRecord) -> NewsProvider:
    """Legacy convenience factory; active runtime uses provider_routers.NewsProviderRouter."""
    provider, _statuses = build_news_provider_with_status(symbol)
    return provider


def build_news_provider_with_status(symbol: SymbolRecord) -> tuple[NewsProvider, list[ProviderStatus]]:
    """Legacy compatibility selection helper retained for direct tests/imports."""
    if symbol.exchange == "US":
        if settings.polygon_api_key:
            return PolygonNewsProvider(), [
                ProviderStatus.available_status("polygon", "news", "POLYGON_API_KEY is configured; Polygon news selected.")
            ]
        return CuratedWebNewsProvider(), [
            ProviderStatus.unconfigured("polygon", "news", "POLYGON_API_KEY is not configured; fallback web news selected."),
            ProviderStatus.degraded("fallback_web", "news", "Fallback web news selected because Polygon news is unconfigured."),
        ]
    if symbol.exchange in {"NSE", "BSE"}:
        if settings.marketaux_api_token:
            return MarketauxNewsProvider(), [
                ProviderStatus.available_status("marketaux", "news", "MARKETAUX_API_TOKEN is configured; Marketaux news selected.")
            ]
        return CuratedWebNewsProvider(), [
            ProviderStatus.unconfigured("marketaux", "news", "MARKETAUX_API_TOKEN is not configured; fallback web news selected."),
            ProviderStatus.degraded("fallback_web", "news", "Fallback web news selected because Marketaux is unconfigured."),
        ]
    return CuratedWebNewsProvider(), [
        ProviderStatus.degraded("fallback_web", "news", "Fallback web news selected for unsupported exchange.")
    ]


def normalize_news_limit(limit: int | None, *, default: int = 20, max_limit: int = MAX_NEWS_LIMIT) -> int:
    if limit is None:
        limit = default
    try:
        parsed = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("News limit must be an integer") from exc
    if parsed < 0:
        raise ValueError("News limit must be zero or greater")
    return min(parsed, max_limit)


def build_article_dedupe_hash(
    *,
    title: str,
    url: str,
    source: str | None,
    published_at: datetime | None,
) -> str:
    normalized_title = " ".join((title or "").strip().lower().split())
    normalized_source = " ".join((source or "").strip().lower().split())
    normalized_url = _normalize_url_for_dedupe(url)
    published_bucket = ""
    if published_at is not None:
        published_bucket = pd_timestamp_hour(published_at)
    return hashlib.sha256(
        f"{normalized_title}|{normalized_source}|{published_bucket}|{normalized_url}".encode()
    ).hexdigest()


def pd_timestamp_hour(value: datetime) -> str:
    parsed = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
    return parsed.replace(minute=0, second=0, microsecond=0).isoformat()


def _normalize_url_for_dedupe(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(sorted(query_pairs)),
            "",
        )
    )


def _coerce_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)
