from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from finsent.app.config.settings import settings
from finsent.app.models.schemas import ScrapedNewsItem
from finsent.app.services.gemini_client import GeminiClient
from finsent.app.utils.text import normalize_text
from finsent.app.utils.time import ensure_utc_naive, parse_rfc822_datetime


class YahooFinanceScraper:
    source_name = "Yahoo Finance"
    excluded_titles = {
        "today's news",
        "news",
        "us",
        "politics",
        "world",
        "science",
        "newsletters",
        "more topics",
        "more news",
        "tech news",
    }

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.gemini_client = GeminiClient(timeout=timeout)
        self.last_leaf_provider = "unavailable"
        self.last_data_mode = "UNKNOWN"
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                )
            }
        )

    def fetch_latest(self, ticker: str, limit: int = 20) -> list[ScrapedNewsItem]:
        ticker = ticker.upper()
        self.last_leaf_provider = "unavailable"
        self.last_data_mode = "UNKNOWN"
        gemini_articles = self._fetch_latest_from_gemini(ticker=ticker, limit=limit)
        if gemini_articles:
            self.last_leaf_provider = "gemini_search"
            self.last_data_mode = "SEARCH_DERIVED"
            return gemini_articles

        alpaca_articles = self._fetch_latest_from_alpaca(ticker=ticker, limit=limit)
        if alpaca_articles:
            self.last_leaf_provider = "alpaca_news"
            self.last_data_mode = "LIVE"
            return alpaca_articles

        yfinance_articles = self._fetch_latest_from_yfinance(ticker=ticker, limit=limit)
        if yfinance_articles:
            self.last_leaf_provider = "yfinance_news"
            self.last_data_mode = "SCRAPED"
            return yfinance_articles

        response = self._fetch_quote_page(ticker)

        soup = BeautifulSoup(response.text, "html.parser")
        articles: list[ScrapedNewsItem] = []
        seen_urls: set[str] = set()

        for link in soup.select("a[href*='/news/'], a[href*='https://finance.yahoo.com/news/']"):
            title = normalize_text(link.get_text(" ", strip=True))
            href = link.get("href")
            if not href or not title:
                continue

            article_url = urljoin(settings.news_source_base_url, href)
            if not self._is_valid_article_link(title=title, article_url=article_url):
                continue
            if article_url in seen_urls:
                continue

            container = link.find_parent(["li", "div", "section", "article"])
            summary = normalize_text(container.get_text(" ", strip=True)) if container else ""

            time_node = None
            if container:
                time_node = container.find("time")
            published_at = ensure_utc_naive(parse_rfc822_datetime(time_node.get("datetime") if time_node else None))

            articles.append(
                ScrapedNewsItem(
                    ticker=ticker,
                    source=self.source_name,
                    title=title,
                    url=article_url,
                    published_at=published_at,
                    summary=summary[:1200] if summary else None,
                )
            )
            seen_urls.add(article_url)

            if len(articles) >= limit:
                break

        if articles:
            self.last_leaf_provider = "yahoo_html"
            self.last_data_mode = "SCRAPED"
        return articles

    def _fetch_latest_from_gemini(self, ticker: str, limit: int) -> list[ScrapedNewsItem]:
        if not self._should_use_gemini():
            return []

        prompt = f"""
Find the most recent important stock-market news about ticker {ticker}.
Use live web search results and return strict JSON only.

Return this schema:
{{
  "articles": [
    {{
      "title": "headline",
      "source": "publisher",
      "url": "https://...",
      "published_at": "ISO-8601 UTC timestamp",
      "summary": "1-2 sentence summary"
    }}
  ]
}}

Rules:
- include at most {limit} articles
- only include items clearly related to ticker {ticker}
- prefer articles from the last 48 hours
- prefer Reuters, Bloomberg, exchange announcements, company press releases, CNBC, WSJ, FT, Moneycontrol, Economic Times, LiveMint, Business Standard, Yahoo Finance
- no duplicates
- no markdown
""".strip()
        payload = self.gemini_client.generate_json(
            prompt,
            use_search_grounding=settings.gemini_use_search_grounding,
            temperature=0.1,
            max_output_tokens=1400,
        )
        if not isinstance(payload, dict):
            return []
        raw_articles = payload.get("articles")
        if not isinstance(raw_articles, list):
            return []

        articles: list[ScrapedNewsItem] = []
        seen_urls: set[str] = set()
        for item in raw_articles:
            if not isinstance(item, dict):
                continue
            title = normalize_text(str(item.get("title", "")))
            article_url = normalize_text(str(item.get("url", "")))
            if not title or not article_url or article_url in seen_urls:
                continue
            published_at = self._coerce_datetime(item.get("published_at"))
            source = normalize_text(str(item.get("source", ""))) or "Gemini Search"
            summary = normalize_text(str(item.get("summary", ""))) or None
            articles.append(
                ScrapedNewsItem(
                    ticker=ticker,
                    source=source,
                    title=title,
                    url=article_url,
                    published_at=published_at,
                    summary=summary[:1200] if summary else None,
                )
            )
            seen_urls.add(article_url)
            if len(articles) >= limit:
                break
        return articles

    def _fetch_latest_from_alpaca(self, ticker: str, limit: int) -> list[ScrapedNewsItem]:
        if not self._should_use_alpaca():
            return []

        now = datetime.now(timezone.utc)
        window_minutes = max(settings.live_news_max_age_minutes * 2, 1440)
        params = {
            "symbols": ticker,
            "start": (now - timedelta(minutes=window_minutes)).isoformat().replace("+00:00", "Z"),
            "end": now.isoformat().replace("+00:00", "Z"),
            "sort": "desc",
            "limit": min(limit, 50),
        }
        try:
            response = self.session.get(
                f"{settings.alpaca_data_base_url.rstrip('/')}/v1beta1/news",
                params=params,
                headers={
                    "APCA-API-KEY-ID": settings.alpaca_api_key,
                    "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []

        payload = response.json()
        raw_articles = payload.get("news") if isinstance(payload, dict) else []
        if not isinstance(raw_articles, list):
            return []

        articles: list[ScrapedNewsItem] = []
        seen_urls: set[str] = set()
        for item in raw_articles:
            if not isinstance(item, dict):
                continue
            title = normalize_text(str(item.get("headline", "")))
            article_url = normalize_text(str(item.get("url", "")))
            if not title or not article_url or article_url in seen_urls:
                continue
            published_at = self._coerce_datetime(item.get("updated_at") or item.get("created_at"))
            source = normalize_text(str(item.get("source", ""))) or "Benzinga"
            summary = normalize_text(str(item.get("summary", ""))) or None
            articles.append(
                ScrapedNewsItem(
                    ticker=ticker,
                    source=source,
                    title=title,
                    url=article_url,
                    published_at=published_at,
                    summary=summary[:1200] if summary else None,
                )
            )
            seen_urls.add(article_url)
            if len(articles) >= limit:
                break
        return articles

    def _fetch_latest_from_yfinance(self, ticker: str, limit: int) -> list[ScrapedNewsItem]:
        try:
            raw_articles = yf.Ticker(ticker).news or []
        except Exception:
            return []

        articles: list[ScrapedNewsItem] = []
        seen_urls: set[str] = set()
        for item in raw_articles:
            title = normalize_text(str(item.get("title", "")))
            article_url = str(item.get("link", "")).strip()
            if not title or not article_url:
                continue
            if article_url in seen_urls:
                continue

            source = normalize_text(str(item.get("publisher", ""))) or self.source_name
            summary = normalize_text(str(item.get("summary", ""))) or None
            raw_published = item.get("providerPublishTime")
            published_at = self._coerce_timestamp(raw_published)
            if not self._is_valid_article_link(title=title, article_url=article_url):
                continue

            articles.append(
                ScrapedNewsItem(
                    ticker=ticker,
                    source=source,
                    title=title,
                    url=article_url,
                    published_at=published_at,
                    summary=summary[:1200] if summary else None,
                )
            )
            seen_urls.add(article_url)
            if len(articles) >= limit:
                break

        return articles

    def _is_valid_article_link(self, title: str, article_url: str) -> bool:
        normalized_title = title.lower().strip()
        if normalized_title in self.excluded_titles:
            return False
        if len(normalized_title) < 35:
            return False
        lowered_url = article_url.lower().rstrip("/")
        if lowered_url.endswith("/news"):
            return False
        if "/news/" not in lowered_url:
            return False
        return True

    def _fetch_quote_page(self, ticker: str) -> requests.Response:
        candidate_urls = [
            f"{settings.news_source_base_url}/quote/{ticker}?p={ticker}",
            f"{settings.news_source_base_url}/quote/{ticker}",
            f"{settings.news_source_base_url}/quote/{ticker}/news?p={ticker}",
        ]
        last_error: Exception | None = None
        for url in candidate_urls:
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                continue

        if last_error is not None:
            raise last_error
        raise requests.RequestException(f"Failed to fetch Yahoo Finance page for {ticker}")

    @staticmethod
    def _coerce_timestamp(raw_value: object) -> datetime:
        if isinstance(raw_value, (int, float)):
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc).replace(tzinfo=None)
        return ensure_utc_naive(datetime.now(timezone.utc))

    @staticmethod
    def _coerce_datetime(raw_value: object) -> datetime:
        if isinstance(raw_value, datetime):
            return ensure_utc_naive(raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=timezone.utc))
        if isinstance(raw_value, str) and raw_value:
            try:
                return ensure_utc_naive(datetime.fromisoformat(raw_value.replace("Z", "+00:00")))
            except ValueError:
                pass
        return ensure_utc_naive(datetime.now(timezone.utc))

    @staticmethod
    def _should_use_alpaca() -> bool:
        provider = settings.live_data_provider.strip().lower()
        has_keys = bool(settings.alpaca_api_key and settings.alpaca_api_secret)
        if provider == "alpaca":
            return has_keys
        if provider == "auto":
            return has_keys
        return False

    @staticmethod
    def _should_use_gemini() -> bool:
        provider = settings.news_discovery_provider.strip().lower()
        has_key = bool(settings.gemini_api_key)
        if provider == "gemini":
            return has_key
        if provider == "auto":
            return has_key
        return False
