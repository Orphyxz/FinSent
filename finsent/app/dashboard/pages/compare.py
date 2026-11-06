from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from finsent.app.dashboard.widgets import segmented

GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Compare", className="section-kicker"),
                    html.H1("Live Market Compare", className="page-title"),
                    html.P(
                        "Compare normalized movement, sentiment, FinSent signals, relative strength, and major catalysts.",
                        className="page-subtitle simple-only",
                    ),
                    html.P(
                        "Compare 2-5 symbols across normalized price movement, current sentiment, live V1/V2 signals, news coverage, and freshness.",
                        className="page-subtitle analyst-only",
                    ),
                ],
                className="section-shell page-header-shell terminal-page-header",
            ),
            html.Div(id="compare-empty-state"),
            html.Div(
                [
                    html.Div(id="compare-selection-summary", className="compare-selection-summary"),
                    html.Div(id="compare-cards", className="compare-cards"),
                    dbc.Row(
                        [
                            dbc.Col(
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Div([html.Div("Price Performance", className="section-kicker"), html.H3("Normalized daily performance", className="section-title")]),
                                                segmented("compare-period", [("30", "1M"), ("90", "3M"), ("180", "6M"), ("365", "1Y")], "90"),
                                            ],
                                            className="panel-head",
                                        ),
                                        dcc.Graph(id="compare-perf-chart", config=GRAPH_CONFIG),
                                    ],
                                    className="chart-card",
                                ),
                                lg=8,
                            ),
                            dbc.Col(
                                html.Div(
                                    [
                                        html.Div("Comparison Brief", className="section-kicker"),
                                        html.H3("What Actually Matters", className="section-title"),
                                        html.P(
                                            "A short read on leadership, weakness, and model confidence across the selected names.",
                                            className="section-helper",
                                        ),
                                        html.Div(id="compare-ai-summary", className="explanation-box"),
                                    ],
                                    className="section-shell explanation-shell",
                                ),
                                lg=4,
                            )
                        ],
                        className="g-3",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([html.Div("News Sentiment", className="section-kicker"), html.H3("Sentiment mix and news volume", className="section-title"), dcc.Graph(id="compare-sentiment-chart", config=GRAPH_CONFIG)], className="chart-card"), lg=6),
                            dbc.Col(html.Div([html.Div("Catalyst Distribution", className="section-kicker"), html.H3("What is driving each stock", className="section-title"), dcc.Graph(id="compare-catalyst-chart", config=GRAPH_CONFIG)], className="chart-card"), lg=6),
                        ],
                        className="g-3 analyst-only",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(html.Div([html.Div("Risk", className="section-kicker"), html.H3("Annualized volatility", className="section-title"), dcc.Graph(id="compare-volatility-chart", config=GRAPH_CONFIG)], className="chart-card"), lg=5),
                            dbc.Col(html.Div([html.Div("Signals", className="section-kicker"), html.H3("Signal V1 vs V2 matrix", className="section-title"), html.Div(id="compare-signal-table")], className="section-shell"), lg=7),
                        ],
                        className="g-3 analyst-only",
                    ),
                    html.Div(
                        [
                            html.Div("Correlation", className="section-kicker"),
                            html.H3("Daily-return correlation", className="section-title"),
                            dcc.Graph(id="compare-correlation", config=GRAPH_CONFIG),
                        ],
                        className="chart-card analyst-only",
                    ),
                    dbc.Row(id="compare-metric-row", className="g-2 metric-strip analyst-only"),
                    html.Div(
                        [
                            html.Div("Intraday", className="section-kicker"),
                            html.H3("Indexed stored price bars", className="section-title"),
                            dcc.Graph(id="compare-main-chart", config=GRAPH_CONFIG),
                        ],
                        className="chart-card analyst-only",
                    ),
                    html.Div(
                        [
                            html.Div("Signal Snapshot", className="section-kicker"),
                            html.H3("Market and Sector Relative Return", className="section-title"),
                            html.P(
                                "US symbols use SPY and mapped sector ETFs. Indian benchmark context is shown as unavailable rather than using a US proxy.",
                                className="section-helper",
                            ),
                            dcc.Graph(id="compare-secondary-chart", config={"displayModeBar": False, "responsive": True}),
                        ],
                        className="chart-card compact-chart-card analyst-only",
                    ),
                    html.Div(
                        [
                            html.Div("Market Context", className="section-kicker"),
                            html.H3("Relative Context", className="section-title"),
                            html.Div(id="compare-market-context-table", className="summary-stack market-context-grid"),
                        ],
                        className="section-shell analyst-only",
                    ),
                    html.Div(
                        [
                            html.Div("Catalyst Intelligence", className="section-kicker"),
                            html.H3("Strongest Recent Catalysts", className="section-title"),
                            html.Div(id="compare-catalyst-table", className="summary-stack catalyst-list"),
                        ],
                        className="section-shell analyst-only",
                    ),
                ],
                id="compare-content",
                className="page-grid",
            ),
        ],
        className="analysis-page",
    )
