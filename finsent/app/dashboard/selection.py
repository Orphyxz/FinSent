"""Workspace selection defaults shared by the page callbacks."""

from __future__ import annotations

import pandas as pd

from finsent.app.dashboard.view_model import get_default_compare_tickers, get_default_ticker_for_exchange, get_display_symbol


def selection(data: dict | None) -> dict:
    default_ticker = get_default_ticker_for_exchange("US")
    base = {
        "focus_ticker": default_ticker,
        "exchange_filter": "US",
        "compare_tickers": get_default_compare_tickers(default_ticker, "US"),
        "horizon": "medium",
        "date_window": "30d",
        "alert_threshold": 40,
        "analysis_ready": True,
    }
    if data:
        base.update(data)
    base["focus_ticker"] = get_display_symbol(str(base.get("focus_ticker") or default_ticker))
    base["compare_tickers"] = [get_display_symbol(str(ticker)) for ticker in base.get("compare_tickers", []) if ticker]
    if base.get("exchange_filter") in {"NSE", "BSE"}:
        base["exchange_filter"] = "INDIA"
    return base


def resolve_date_window(selection: dict) -> tuple[str | None, str | None]:
    today = pd.Timestamp.now().normalize()
    date_window = selection.get("date_window", "30d")
    if date_window == "7d":
        return (today - pd.Timedelta(days=7)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if date_window == "30d":
        return (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if date_window == "90d":
        return (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    return None, None
