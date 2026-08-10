from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Generic, Protocol, TypeVar

import pandas as pd
import requests

from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.symbol_registry import SymbolRecord
from finsent.app.utils.logging import safe_log_message


T = TypeVar("T")


class ProviderFailureCategory(str, Enum):
    UNCONFIGURED = "UNCONFIGURED"
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NO_DATA = "NO_DATA"
    STALE_DATA = "STALE_DATA"
    UNSUPPORTED_SYMBOL = "UNSUPPORTED_SYMBOL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider: str
    service: str
    status: DataSourceState
    category: ProviderFailureCategory | None
    message: str
    selected: bool = False
    duration_ms: int | None = None


@dataclass(slots=True)
class ProviderResult(Generic[T]):
    data: T | None
    status: ProviderStatus
    provider: str
    service: str
    source_timestamp: datetime | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    from_cache: bool = False
    fallback_used: bool = False
    attempts: list[ProviderAttempt] = field(default_factory=list)
    message: str = ""
    leaf_provider: str | None = None
    data_mode: object | None = None
    freshness: object | None = None
    quality: object | None = None
    retry_after_seconds: int | None = None

    @property
    def available(self) -> bool:
        return self.status.available


class ActiveMarketDataProvider(Protocol):
    provider_name: str

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        ...


class ActiveHistoricalDataProvider(Protocol):
    provider_name: str

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        ...


class ActiveNewsProvider(Protocol):
    provider_name: str

    def fetch_news(self, symbol: SymbolRecord, limit: int = 20) -> list[NormalizedNewsArticle]:
        ...


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    provider: str
    service: str
    supports_exchange: Callable[[str], bool]
    configured: Callable[[], bool]
    factory: Callable[[], object]
    unconfigured_message: str


def classify_exception(exc: Exception) -> ProviderFailureCategory:
    if isinstance(exc, requests.Timeout):
        return ProviderFailureCategory.TIMEOUT
    if isinstance(exc, requests.ConnectionError):
        return ProviderFailureCategory.NETWORK
    if isinstance(exc, requests.HTTPError):
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {401, 403}:
            return ProviderFailureCategory.AUTHENTICATION
        if status_code == 429:
            return ProviderFailureCategory.RATE_LIMIT
        if isinstance(status_code, int) and 500 <= status_code <= 599:
            return ProviderFailureCategory.NETWORK
        return ProviderFailureCategory.INVALID_RESPONSE
    if isinstance(exc, requests.RequestException):
        return ProviderFailureCategory.NETWORK
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return ProviderFailureCategory.INVALID_RESPONSE
    return ProviderFailureCategory.UNKNOWN


def status_from_category(
    provider: str,
    service: str,
    category: ProviderFailureCategory,
    message: str,
) -> ProviderStatus:
    safe_message = safe_log_message(message)
    if category == ProviderFailureCategory.UNCONFIGURED:
        return ProviderStatus.unconfigured(provider, service, safe_message)
    if category in {ProviderFailureCategory.STALE_DATA, ProviderFailureCategory.RATE_LIMIT}:
        return ProviderStatus(
            provider=provider,
            service=service,
            status=DataSourceState.DEGRADED,
            message=safe_message,
            configured=True,
            available=False,
        )
    return ProviderStatus.unavailable(provider, service, safe_message)


def attempt_from_status(
    status: ProviderStatus,
    *,
    category: ProviderFailureCategory | None = None,
    selected: bool = False,
    duration_ms: int | None = None,
) -> ProviderAttempt:
    return ProviderAttempt(
        provider=status.provider,
        service=status.service,
        status=status.status,
        category=category,
        message=status.message,
        selected=selected,
        duration_ms=duration_ms,
    )
