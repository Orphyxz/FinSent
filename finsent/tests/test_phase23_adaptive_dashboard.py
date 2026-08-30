from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dash.development.base_component import Component

from finsent.app.config.settings import settings
from finsent.app.dashboard import view_model as dashboard_view_model
from finsent.app.dashboard.app import create_app
from finsent.app.dashboard.layout import build_app_layout
from finsent.app.dashboard.pages import alerts, compare, news_impact, research, stock_detail, summary
from finsent.app.dashboard.view_model import (
    filter_symbols_for_exchange,
    format_currency,
    get_default_ticker_for_exchange,
    get_ticker_options,
)
from finsent.app.services.market_context import MarketContextService
from finsent.app.services.market_providers import KiteMarketDataProvider, classify_india_market_status
from finsent.app.services.symbol_registry import registry


def _walk(component: object):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                yield from _walk(child)
        elif children is not None:
            yield from _walk(children)


def _ids(component: object) -> set[str]:
    return {str(item.id) for item in _walk(component) if getattr(item, "id", None)}


def _text(component: object) -> str:
    values: list[str] = []
    for item in _walk(component):
        children = getattr(item, "children", None)
        if isinstance(children, (str, int, float)):
            values.append(str(children))
    return " ".join(values)


def test_phase23_layout_has_persistent_simple_analyst_mode() -> None:
    layout = build_app_layout("AAPL", ["NVDA", "TSLA"])
    ids = _ids(layout)
    mode_store = next(item for item in _walk(layout) if getattr(item, "id", None) == "display-mode-store")
    mode_toggle = next(item for item in _walk(layout) if getattr(item, "id", None) == "display-mode-toggle")

    assert {"display-mode-store", "display-mode-toggle", "dashboard-shell"}.issubset(ids)
    assert mode_store.storage_type == "local"
    assert mode_store.data == "simple"
    assert mode_toggle.persistence is True
    assert {option["value"] for option in mode_toggle.options} == {"simple", "analyst"}


def test_phase23_mode_callbacks_are_registered() -> None:
    app = create_app()
    assert "display-mode-store.data" in app.callback_map
    assert "dashboard-shell.className" in app.callback_map


def test_phase23_pages_expose_progressive_disclosure_content() -> None:
    for page in [summary.layout(), stock_detail.layout(), news_impact.layout(), compare.layout(), alerts.layout(), research.layout()]:
        classes = " ".join(str(getattr(item, "className", "")) for item in _walk(page))
        assert "simple-only" in classes
        assert "analyst-only" in classes

    assert "summary-recent-headlines" in _ids(summary.layout())
    assert "stock-recent-headlines" in _ids(stock_detail.layout())
    assert "news-simple-table" in _ids(news_impact.layout())


def test_phase23_registry_materially_expands_us_and_india() -> None:
    us = registry.list_symbols("US")
    india = registry.list_symbols("INDIA")

    assert 75 <= len(us) <= 150
    assert 50 <= len(india) <= 100
    assert {"Technology", "Financials", "Health Care", "Energy", "Industrials", "Utilities", "Real Estate", "Materials"}.issubset(
        {item.sector for item in us}
    )
    assert {"RELIANCE", "TCS", "HDFCBANK", "INFY", "SBIN"}.issubset({item.ticker for item in india})


def test_phase23_registry_searches_ticker_and_company_name() -> None:
    assert registry.search("AAPL", "US")[0].display_name == "Apple"
    assert registry.search("Microsoft", "US")[0].ticker == "MSFT"
    assert registry.search("Reliance Industries", "INDIA")[0].ticker == "RELIANCE"
    assert registry.search("HDFC Bank", "INDIA")[0].ticker == "HDFCBANK"


def test_phase23_market_filter_options_are_compact_and_searchable(monkeypatch) -> None:
    assert len(filter_symbols_for_exchange("ALL")) > len(filter_symbols_for_exchange("US"))
    assert all(item.exchange == "US" for item in filter_symbols_for_exchange("US"))
    assert all(item.exchange == "NSE" for item in filter_symbols_for_exchange("INDIA"))
    india_options = get_ticker_options("INDIA")
    assert any(option["value"] == "RELIANCE" and "Reliance" in option["search"] for option in india_options)
    monkeypatch.setattr(dashboard_view_model, "get_local_research_symbols", lambda _market: ["RELIANCE"])
    default = get_default_ticker_for_exchange("INDIA")
    symbol = registry.resolve_any(default)
    assert default == "RELIANCE"
    assert symbol is not None
    assert symbol.market == "INDIA"
    assert symbol.exchange == "NSE"
    assert symbol.symbol_for("kite") == "NSE:RELIANCE"


def test_phase23_provider_symbol_normalization_is_centralized() -> None:
    reliance = registry.resolve_any("RELIANCE")
    assert reliance is not None
    assert reliance.provider_symbol == "NSE:RELIANCE"
    assert reliance.symbol_for("kite") == "NSE:RELIANCE"
    assert reliance.symbol_for("yahoo") == "RELIANCE.NS"
    assert registry.resolve_any("RELIANCE.NS") == reliance

    apple = registry.resolve_any("AAPL")
    assert apple is not None
    assert apple.symbol_for("alpaca") == "AAPL"
    assert apple.symbol_for("polygon") == "AAPL"


def test_phase23_currency_formatting_is_market_aware() -> None:
    assert format_currency(1234.5, "USD") == "$1,234.50"
    assert format_currency(1234.5, "INR") == "\u20b91,234.50"
    assert format_currency(None, "INR") == "n/a"


def test_phase23_kite_unconfigured_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "kite_api_key", "")
    monkeypatch.setattr(settings, "kite_access_token", "")
    reliance = registry.resolve_any("NSE:RELIANCE")
    assert reliance is not None

    quote = KiteMarketDataProvider().fetch_quote_snapshot(reliance)

    assert quote.current_price is None
    assert quote.quality_status == "unconfigured"
    assert "not configured" in quote.note.lower()


def test_phase23_india_context_never_fetches_or_uses_spy() -> None:
    class NoFetchRouter:
        def fetch_price_bars(self, *args, **kwargs):  # pragma: no cover - failure assertion
            raise AssertionError("Indian context must not fetch US benchmark bars")

    service = MarketContextService(router=NoFetchRouter())
    result = service.build_contexts(["NSE:RELIANCE"], price_df=pd.DataFrame())

    assert len(result) == 1
    assert result[0].benchmark_symbol is None
    assert result[0].provider == "unavailable"
    assert "not configured" in result[0].warnings[0].lower()


def test_phase23_india_market_state_handles_open_and_closed_sessions() -> None:
    monday_open_utc = datetime(2026, 8, 24, 5, 0, tzinfo=timezone.utc)
    monday_closed_utc = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    assert classify_india_market_status(monday_open_utc) == "MARKET OPEN"
    assert classify_india_market_status(monday_closed_utc) == "MARKET CLOSED"


def test_phase23_simple_language_avoids_investment_ctas() -> None:
    rendered = " ".join(_text(page) for page in [summary.layout(), stock_detail.layout(), news_impact.layout(), compare.layout(), alerts.layout()])
    lowered = rendered.lower()
    assert "buy now" not in lowered
    assert "strong buy" not in lowered
    assert "guaranteed" not in lowered
    assert "notification subscriptions" in lowered


def test_phase23_responsive_and_accessibility_css_contract() -> None:
    css = Path("finsent/app/dashboard/assets/dashboard.css").read_text(encoding="utf-8")
    for token in ["--space-1: 4px", "--space-2: 8px", "--space-3: 12px", "--space-4: 16px", "--space-5: 24px", "--space-6: 32px"]:
        assert token in css
    for breakpoint in ["1366px", "1100px", "680px"]:
        assert breakpoint in css
    assert ":focus-visible" in css
    assert ".mode-simple .analyst-only" in css
    assert ".mode-analyst .simple-only" in css
