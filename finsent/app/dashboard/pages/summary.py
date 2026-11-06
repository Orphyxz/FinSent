from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from finsent.app.dashboard.widgets import panel


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Executive Intelligence", className="section-kicker"),
                            html.H1("Market Overview", className="page-title"),
                            html.P(
                                "Market sentiment, index moves, watchlist signals and the catalysts driving them, in one view.",
                                className="page-subtitle simple-only",
                            ),
                            html.P(
                                "Article-weighted FinBERT sentiment, daily index bars (US via ETF proxies), stored V1/V2 signal runs and deterministic catalyst priority across the watchlist.",
                                className="page-subtitle analyst-only",
                            ),
                        ]
                    ),
                    html.Div(id="exec-provider-strip", className="provider-strip analyst-only"),
                ],
                className="section-shell page-header-shell exec-header",
            ),
            html.Div(id="exec-brief", className="section-shell plain-brief simple-only"),
            html.Div(
                [
                    html.Div(id="exec-mood", className="exec-mood-slot"),
                    html.Div(id="exec-indices", className="index-grid"),
                ],
                className="exec-hero",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        panel(
                            "Watchlist",
                            "Signals at a glance",
                            html.Div(id="exec-watchlist", className="fade-in"),
                            action=html.Details(
                                [
                                    html.Summary("Edit watchlist", className="edit-summary"),
                                    html.Div(
                                        [
                                            html.Div("Up to 12 stocks, saved in this browser", className="control-helper"),
                                            dcc.Dropdown(id="watchlist-editor", multi=True, searchable=True, placeholder="Add stocks", className="finsent-dropdown"),
                                            html.Button("Reset to default", id="watchlist-reset", n_clicks=0, className="ghost-button"),
                                        ],
                                        className="edit-popover",
                                    ),
                                ],
                                className="edit-details",
                            ),
                        ),
                        lg=8,
                        className="simple-full-col",
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                panel("Signal Distribution", "Across the watchlist", html.Div(id="exec-signal-dist")),
                                panel("Sentiment Movers", "Biggest 24h shifts", html.Div(id="exec-movers")),
                            ],
                            className="stack-shell",
                        ),
                        lg=4,
                        className="analyst-only",
                    ),
                ],
                className="g-3",
            ),
            html.Div(
                [
                    html.Div("Correlation", className="section-kicker"),
                    html.H3("Watchlist daily-return correlation", className="section-title"),
                    dcc.Graph(id="exec-correlation", config={"displayModeBar": False, "responsive": True}),
                ],
                className="chart-card analyst-only",
            ),
            dbc.Row(
                [
                    dbc.Col(panel("Positive Catalysts", "Top bullish events", html.Div(id="exec-positive"), class_name="accent-positive"), lg=4, className="simple-half-col"),
                    dbc.Col(panel("Negative Catalysts", "Top bearish events", html.Div(id="exec-negative"), class_name="accent-negative"), lg=4, className="simple-half-col"),
                    dbc.Col(panel("Today", "Significant financial events", html.Div(id="exec-events")), lg=4, className="analyst-only"),
                ],
                className="g-3",
            ),
            html.Div(
                [
                    html.Div("Focus Stock", className="section-kicker"),
                    html.H2(id="summary-page-title", className="focus-title"),
                    html.Div(id="summary-badge-row", className="badge-row"),
                ],
                className="focus-divider analyst-only",
            ),
            html.Div(id="summary-status-banner", className="market-status-strip analyst-only"),
            dbc.Row(id="summary-metric-row", className="g-2 metric-strip analyst-only"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Market Chart", className="section-kicker"),
                                html.H3("Recent Close", className="section-title"),
                                dcc.Graph(id="summary-price-chart", config={"displayModeBar": False, "responsive": True}),
                            ],
                            className="chart-card primary-chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Signal Intelligence", className="section-kicker"),
                                html.H3("Why This Signal", className="section-title"),
                                html.Div("Research signal context only; not trading advice.", className="research-note compact-note"),
                                html.Div(id="summary-ai-explanation", className="explanation-box compact"),
                            ],
                            className="section-shell explanation-shell",
                        ),
                        lg=4,
                    ),
                ],
                className="g-3 analyst-only",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Market Context", className="section-kicker"),
                                html.H3("Broad Market and Relative Strength", className="section-title"),
                                html.Div(id="summary-market-context", className="summary-stack market-context-grid"),
                            ],
                            className="section-shell",
                        ),
                        lg=5,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Catalyst Intelligence", className="section-kicker"),
                                html.H3("Active Catalysts", className="section-title"),
                                html.Div(id="summary-active-catalysts", className="summary-stack catalyst-list"),
                            ],
                            className="section-shell",
                        ),
                        lg=7,
                    ),
                ],
                className="g-3 analyst-only",
            ),
            html.Div(
                [
                    html.Div("Recent News", className="section-kicker"),
                    html.H3("Important Headlines", className="section-title"),
                    html.Div(id="summary-recent-headlines", className="headline-list"),
                ],
                className="section-shell analyst-only",
            ),
        ],
        className="analysis-page",
    )
