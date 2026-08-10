from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from finsent.app.config.settings import settings
from finsent.app.dashboard.view_model import _is_usable_quote_meta, get_price_status_note
from finsent.app.services.market_providers import (
    PolygonMarketDataProvider,
    QuoteSnapshot,
    is_usable_quote_snapshot,
)
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.symbol_registry import registry


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _quote(**overrides) -> QuoteSnapshot:
    now = _now()
    values = {
        "symbol": "AAPL",
        "exchange": "US",
        "provider_symbol": "AAPL",
        "current_price": 200.0,
        "currency": "USD",
        "bid": 199.9,
        "ask": 200.1,
        "spread_absolute": 0.2,
        "spread_percentage": 0.001,
        "volume": 1_000_000.0,
        "market_timestamp": now - timedelta(seconds=30),
        "ingested_at": now,
        "provider": "polygon",
        "freshness_seconds": 30,
        "quality_status": "live",
        "note": "test",
        "provider_status": ProviderStatus.available_status("polygon", "market_quote", "test"),
    }
    values.update(overrides)
    return QuoteSnapshot(**values)


def test_provider_status_is_machine_readable_and_sanitized() -> None:
    status = ProviderStatus.unavailable("polygon", "news", "request failed api_key=super-secret-token")

    assert status.status == DataSourceState.UNAVAILABLE
    assert status.configured is True
    assert status.available is False
    assert "super-secret-token" not in status.message
    assert status.as_dict()["status"] == "UNAVAILABLE"


def test_polygon_missing_key_returns_unconfigured_quote(monkeypatch) -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    monkeypatch.setattr(settings, "polygon_api_key", "")

    quote = PolygonMarketDataProvider().fetch_quote_snapshot(symbol)

    assert quote.quality_status == "unconfigured"
    assert quote.provider_status is not None
    assert quote.provider_status.status == DataSourceState.UNCONFIGURED
    assert quote.provider_status.configured is False
    assert not is_usable_quote_snapshot(quote)


def test_quote_usability_requires_price_timestamp_and_available_state() -> None:
    assert is_usable_quote_snapshot(_quote())
    assert not is_usable_quote_snapshot(_quote(current_price=None))
    assert not is_usable_quote_snapshot(_quote(current_price=0.0))
    assert not is_usable_quote_snapshot(_quote(market_timestamp=None))
    assert not is_usable_quote_snapshot(
        _quote(
            quality_status="unconfigured",
            provider_status=ProviderStatus.unconfigured("polygon", "market_quote", "missing key"),
        )
    )


def test_stale_quote_is_usable_but_explicitly_stale() -> None:
    quote = _quote(
        quality_status="stale",
        freshness_seconds=86_400,
        provider_status=ProviderStatus.stale_status("polygon", "market_quote", "previous close"),
    )

    assert is_usable_quote_snapshot(quote)
    assert quote.provider_status is not None
    assert quote.provider_status.stale is True


def test_view_model_quote_meta_does_not_treat_unconfigured_row_as_usable() -> None:
    quote_meta = {
        "provider": "polygon",
        "current_price": None,
        "market_timestamp": None,
        "quality_status": "unconfigured",
        "note": "POLYGON_API_KEY is not configured",
    }

    assert not _is_usable_quote_meta(quote_meta)
    assert "unconfigured" in get_price_status_note("AAPL", False, quote_meta).lower()


def test_view_model_quote_meta_accepts_valid_delayed_quote() -> None:
    quote_meta = {
        "provider": "polygon",
        "current_price": 201.0,
        "market_timestamp": pd.Timestamp("2026-08-09 10:00:00"),
        "quality_status": "delayed",
    }

    assert _is_usable_quote_meta(quote_meta)
