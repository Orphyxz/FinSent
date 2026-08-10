from __future__ import annotations

from dash import dcc, html

from finsent.app.config.settings import settings
from finsent.app.dashboard.components import build_footer, build_landing_search, build_navbar, build_workspace_bar


def build_app_layout(default_ticker: str) -> html.Div:
    return html.Div(
        [
            dcc.Location(id="url", refresh=False),
            dcc.Interval(id="live-refresh-interval", interval=settings.live_refresh_interval_ms, n_intervals=0),
            dcc.Store(
                id="selection-store",
                storage_type="session",
                data={
                    "focus_ticker": default_ticker,
                    "exchange_filter": "US",
                    "compare_tickers": [],
                    "horizon": "medium",
                    "date_window": "30d",
                    "alert_threshold": 40,
                    "analysis_ready": True,
                },
            ),
            dcc.Store(id="live-refresh-store", storage_type="memory"),
            build_navbar(),
            html.Div(build_landing_search(default_ticker), id="landing-controls-container"),
            html.Div(
                build_workspace_bar(
                    focus_ticker=default_ticker,
                    exchange_filter="US",
                    compare_tickers=[],
                    horizon="medium",
                    date_window="30d",
                    alert_threshold=40,
                ),
                id="top-controls-container",
            ),
            html.Div(id="page-container"),
            build_footer(),
        ],
        className="dashboard-shell",
    )
