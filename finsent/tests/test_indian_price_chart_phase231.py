from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from finsent.app.config.settings import settings
from finsent.app.dashboard.app import _selection
from finsent.app.dashboard.view_model import (
    build_empty_figure,
    build_price_timeline,
    build_snapshot_map,
    get_default_ticker_for_exchange,
    get_ticker_options,
)
from finsent.app.services.market_providers import YahooHistoricalMarketDataProvider
from finsent.app.services.provider_contracts import ProviderCandidate
from finsent.app.services.provider_routers import MarketDataRouter
from finsent.app.services.symbol_registry import registry


def _provider_frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(["2026-08-27 03:45:00", "2026-08-27 04:00:00", "2026-08-27 04:15:00"])
    return pd.DataFrame(
        [
            [1400.0, 1408.0, 1398.0, 1405.0, 1000.0],
            [1405.0, 1415.0, 1402.0, 1412.0, 1200.0],
            [1412.0, 1414.0, 1404.0, 1407.0, 900.0],
        ],
        index=index,
        columns=["Open", "High", "Low", "Close", "Volume"],
    )


@pytest.mark.parametrize(("ticker", "provider_symbol"), [("RELIANCE", "RELIANCE.NS"), ("TCS", "TCS.NS")])
def test_yahoo_chart_indian_history_uses_registry_ns_symbol_and_preserves_variation(ticker: str, provider_symbol: str) -> None:
    requested: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1777251900, 1777252800, 1777253700],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [1400.0, 1405.0, 1412.0],
                                        "high": [1408.0, 1415.0, 1414.0],
                                        "low": [1398.0, 1402.0, 1404.0],
                                        "close": [1405.0, 1412.0, 1407.0],
                                        "volume": [1000.0, 1200.0, 900.0],
                                    }
                                ]
                            },
                        }
                    ]
                }
            }

    class FakeSession:
        def get(self, url, **kwargs):
            requested["url"] = url
            requested.update(kwargs)
            return FakeResponse()

    symbol = registry.get("NSE", ticker)
    assert symbol is not None
    provider = YahooHistoricalMarketDataProvider()
    provider.session = FakeSession()
    frame = provider.fetch_price_bars(
        symbol,
        datetime(2026, 8, 20),
        datetime(2026, 8, 28),
        "15m",
    )

    assert str(requested["url"]).endswith(f"/{provider_symbol}")
    assert requested["params"]["interval"] == "15m"  # type: ignore[index]
    assert len(frame) == 3
    assert frame.index.nunique() == 3
    assert frame["Close"].nunique() == 3
    assert frame.index.tz is None


def test_indian_router_falls_back_to_yahoo_chart_without_using_us_providers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kite_api_key", "")
    monkeypatch.setattr(settings, "kite_access_token", "")
    monkeypatch.setattr(YahooHistoricalMarketDataProvider, "fetch_price_bars", lambda self, symbol, start, end, interval: _provider_frame())
    symbol = registry.get("NSE", "RELIANCE")
    assert symbol is not None

    result = MarketDataRouter().fetch_price_bars(
        symbol,
        start=datetime(2026, 8, 20),
        end=datetime(2026, 8, 28),
        interval="15m",
    )

    assert result.provider == "yahoo_chart"
    assert result.data is not None and result.data["Close"].nunique() == 3
    assert symbol.symbol_for(result.provider) == "RELIANCE.NS"
    assert [attempt.provider for attempt in result.attempts] == ["kite", "yahoo_chart"]
    assert not {"alpaca", "polygon"}.intersection(attempt.provider for attempt in result.attempts)


def test_indian_canonical_values_remain_bare_in_ui() -> None:
    options = get_ticker_options("INDIA")
    values = {option["value"] for option in options}

    assert {"RELIANCE", "TCS", "HDFCBANK", "INFY", "SBIN"}.issubset(values)
    assert not any(value.startswith("NSE:") for value in values)
    assert registry.resolve_any("RELIANCE").symbol_for("kite") == "NSE:RELIANCE"  # type: ignore[union-attr]


def test_indian_default_and_existing_selection_normalize_to_canonical_ui_values(monkeypatch) -> None:
    monkeypatch.setattr("finsent.app.dashboard.view_model.get_local_research_symbols", lambda _market: [])

    assert get_default_ticker_for_exchange("INDIA") == "RELIANCE"
    selection = _selection(
        {
            "focus_ticker": "NSE:RELIANCE",
            "compare_tickers": ["NSE:TCS"],
            "exchange_filter": "INDIA",
        }
    )
    assert selection["focus_ticker"] == "RELIANCE"
    assert selection["compare_tickers"] == ["TCS"]


def test_varying_indian_history_reaches_plotly_without_flattening() -> None:
    frame = _provider_frame().copy()
    frame = frame.reset_index(names="timestamp").rename(columns=str.lower)
    frame["ticker"] = "RELIANCE"

    figure = build_price_timeline(frame, focus_ticker="RELIANCE")

    assert len(figure.data) == 1
    assert len(set(figure.data[0].x)) == 3
    assert len(set(figure.data[0].y)) == 3


def test_missing_indian_history_is_an_honest_empty_chart() -> None:
    figure = build_empty_figure("RELIANCE Price Timeline", "Historical price data unavailable")

    assert len(figure.data) == 0
    assert figure.layout.annotations[0].text == "Historical price data unavailable"


def test_current_quote_remains_available_when_indian_history_is_missing() -> None:
    quote_meta = {
        "RELIANCE": {
            "current_price": 1405.0,
            "currency": "INR",
            "provider": "kite",
            "market_timestamp": datetime(2026, 8, 27, 10, 0),
            "quality_status": "live",
        }
    }

    snapshot = build_snapshot_map(["RELIANCE"], quote_meta, {})["RELIANCE"]
    figure = build_empty_figure("RELIANCE Price Timeline", "Historical price data unavailable")

    assert snapshot.last_price == 1405.0
    assert len(figure.data) == 0


def test_indian_bar_cache_is_isolated_by_canonical_instrument() -> None:
    calls: list[str] = []

    class SymbolAwareProvider:
        provider_name = "test_history"

        def fetch_price_bars(self, symbol, start, end, interval):
            calls.append(symbol.ticker)
            frame = _provider_frame().copy()
            if symbol.ticker == "TCS":
                frame[["Open", "High", "Low", "Close"]] = frame[["Open", "High", "Low", "Close"]] + 1000.0
            return frame

    candidate = ProviderCandidate(
        provider="test_history",
        service="market_bars",
        supports_exchange=lambda exchange: exchange == "NSE",
        configured=lambda: True,
        factory=SymbolAwareProvider,
        unconfigured_message="",
    )
    router = MarketDataRouter(candidates=[candidate])
    reliance = registry.get("NSE", "RELIANCE")
    tcs = registry.get("NSE", "TCS")
    assert reliance is not None and tcs is not None

    reliance_result = router.fetch_price_bars(reliance, start=datetime(2026, 8, 20), end=datetime(2026, 8, 28), interval="15m")
    tcs_result = router.fetch_price_bars(tcs, start=datetime(2026, 8, 20), end=datetime(2026, 8, 28), interval="15m")

    assert calls == ["RELIANCE", "TCS"]
    assert reliance_result.data is not None and tcs_result.data is not None
    assert float(reliance_result.data["Close"].iloc[0]) != float(tcs_result.data["Close"].iloc[0])
