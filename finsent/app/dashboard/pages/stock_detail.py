from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from finsent.app.dashboard.widgets import panel, segmented


GRAPH_CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}


def _workbench_toolbar() -> html.Div:
    return html.Div(
        [
            segmented("stock-period", [("1D", "1D"), ("1W", "1W"), ("1M", "1M"), ("3M", "3M"), ("6M", "6M"), ("1Y", "1Y")], "3M"),
            segmented("stock-chart-style", [("candle", "Candles"), ("line", "Line")], "candle", class_name="analyst-only"),
            dcc.Checklist(
                id="stock-overlays",
                options=[
                    {"label": "SMA 20", "value": "sma20"},
                    {"label": "SMA 50", "value": "sma50"},
                    {"label": "SMA 200", "value": "sma200"},
                    {"label": "EMA 20", "value": "ema20"},
                    {"label": "Bollinger", "value": "bollinger"},
                ],
                value=["sma20", "sma50"],
                inline=True,
                className="chip-check analyst-only",
                inputClassName="chip-check-input",
                labelClassName="chip-check-label",
            ),
            dcc.Checklist(
                id="stock-panels",
                options=[{"label": "Volume", "value": "volume"}, {"label": "RSI", "value": "rsi"}, {"label": "MACD", "value": "macd"}],
                value=["volume", "rsi", "macd"],
                inline=True,
                className="chip-check analyst-only",
                inputClassName="chip-check-input",
                labelClassName="chip-check-label",
            ),
        ],
        className="workbench-toolbar",
    )


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Stock Intelligence", className="section-kicker"),
                            html.H1(id="stock-page-title", className="page-title"),
                            html.P("Price, technicals, signals, catalysts and news for one stock.", className="page-subtitle simple-only"),
                            html.P("Daily OHLCV with RSI 14, MACD 12/26/9 and moving averages; live V1/V2 with component contributions.", className="page-subtitle analyst-only"),
                            html.Div(id="stock-badge-row", className="badge-row analyst-only"),
                        ],
                        className="quote-identity",
                    ),
                    html.Div(
                        [
                            html.Div(id="stock-quote-header", className="quote-header"),
                            html.Button("Print / Save PDF", id="stock-print", n_clicks=0, className="ghost-button print-button", title="Print this stock report or save it as a PDF (P)"),
                        ],
                        className="quote-actions",
                    ),
                ],
                className="section-shell page-header-shell stock-hero",
            ),
            html.Div(id="stock-verdict", className="section-shell plain-brief simple-only"),
            dbc.Row(id="stock-metric-row", className="g-2 metric-strip analyst-only"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div([html.Div("Price", className="section-kicker simple-only"), html.Div("Price Workbench", className="section-kicker analyst-only"), html.H3("OHLCV and Indicators", className="section-title analyst-only")]),
                                        html.Span("Indicators computed from daily OHLCV", className="panel-hint analyst-only"),
                                    ],
                                    className="panel-head",
                                ),
                                _workbench_toolbar(),
                                dcc.Loading(dcc.Graph(id="stock-main-chart", config=GRAPH_CONFIG), type="dot", color="#22c55e", delay_show=400),
                            ],
                            className="chart-card workbench-card",
                        ),
                        lg=8,
                        className="simple-full-col",
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                panel("Technicals", "Snapshot", html.Div(id="stock-technicals", className="stat-grid")),
                                html.Div(
                                    [
                                        html.Div("Instrument", className="section-kicker"),
                                        html.H3("Market Header", className="section-title"),
                                        html.Div(id="stock-summary-panel", className="summary-stack"),
                                    ],
                                    className="section-shell compact-panel",
                                ),
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
                    html.Div(
                        [
                            html.Div([html.Div("Explainable Signal Engine", className="section-kicker"), html.H3("Why the signal says what it says", className="section-title")]),
                            html.Span("Research signals, not trading advice", className="panel-hint"),
                        ],
                        className="panel-head",
                    ),
                    html.Div(
                        [
                            html.Div(id="stock-signal-compare", className="signal-compare"),
                            html.Div(
                                [
                                    html.Div("V2 contribution by component", className="sub-title"),
                                    dcc.Graph(id="stock-contrib-chart", config=GRAPH_CONFIG),
                                ],
                                className="contrib-wrap",
                            ),
                            html.Div(id="stock-signal-weights", className="weight-table-wrap"),
                        ],
                        className="explainer-grid",
                    ),
                    html.Details(
                        [
                            html.Summary("Full reasoning", className="details-summary"),
                            html.Div(id="stock-ai-explanation", className="explanation-box compact"),
                        ],
                        className="reasoning-details",
                    ),
                ],
                className="section-shell explainer-shell analyst-only",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.Div("Risk Profile", className="section-kicker"), html.H3("Return and risk, last 12 months", className="section-title")]),
                            html.Span("Daily closes; risk-free rate assumed zero", className="panel-hint"),
                        ],
                        className="panel-head",
                    ),
                    html.Div(id="stock-risk-stats", className="stat-grid"),
                    html.Div(
                        [
                            html.Div([html.Div("Rolling 60-day beta", className="sub-title"), dcc.Graph(id="stock-rolling-beta", config=GRAPH_CONFIG)]),
                            html.Div([html.Div("Daily return distribution", className="sub-title"), dcc.Graph(id="stock-return-dist", config=GRAPH_CONFIG)]),
                        ],
                        className="research-two-column",
                    ),
                ],
                className="section-shell risk-shell analyst-only",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Sentiment History", className="section-kicker"),
                                html.H3("Daily FinBERT sentiment and news volume", className="section-title"),
                                dcc.Graph(id="stock-sentiment-history", config=GRAPH_CONFIG),
                            ],
                            className="chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Benchmark Intelligence", className="section-kicker"),
                                html.H3("Market and Sector Context", className="section-title"),
                                html.Div(id="stock-market-context-panel", className="summary-stack market-context-grid"),
                            ],
                            className="section-shell",
                        ),
                        lg=4,
                        className="stock-market-context-col",
                    ),
                ],
                className="g-3 analyst-only",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.Div("Relative Strength", className="section-kicker"), html.H3(id="stock-benchmark-title", className="section-title")]),
                            html.Span("Daily closes, last 6 months, rebased to 100", className="panel-hint"),
                        ],
                        className="panel-head",
                    ),
                    html.Div(
                        [
                            dcc.Graph(id="stock-benchmark-chart", config=GRAPH_CONFIG),
                            html.Div(id="stock-benchmark-stats", className="stat-grid benchmark-stats"),
                        ],
                        className="benchmark-grid",
                    ),
                ],
                className="section-shell analyst-only",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Intraday Context", className="section-kicker"),
                                html.H3("Relative performance on stored bars", className="section-title"),
                                dcc.Graph(id="stock-relative-chart", config=GRAPH_CONFIG),
                            ],
                            className="chart-card",
                        ),
                        lg=7,
                        className="analyst-only",
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Catalyst Intelligence", className="section-kicker"),
                                html.H3("Key Catalysts", className="section-title"),
                                html.Div(id="stock-catalyst-summary", className="summary-stack catalyst-summary-grid analyst-only"),
                                html.Div(id="stock-key-catalysts", className="summary-stack catalyst-list"),
                            ],
                            className="section-shell",
                        ),
                        lg=5,
                        className="stock-key-catalyst-col",
                    ),
                ],
                className="g-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Event Timeline", className="section-kicker"),
                                html.H3("Recent Catalyst Events", className="section-title"),
                                html.Div(id="stock-catalyst-timeline", className="summary-stack catalyst-timeline"),
                            ],
                            className="section-shell",
                        ),
                        lg=6,
                        className="analyst-only",
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Recent News", className="section-kicker"),
                                html.H3("Important Headlines", className="section-title"),
                                html.Div(id="stock-recent-headlines", className="headline-list"),
                            ],
                            className="section-shell",
                        ),
                        lg=6,
                        className="simple-full-col",
                    ),
                ],
                className="g-3",
            ),
        ],
        className="analysis-page",
    )
