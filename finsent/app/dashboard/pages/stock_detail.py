from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Live Stock Intelligence", className="section-kicker"),
                    html.H1(id="stock-page-title", className="page-title"),
                    html.P(
                        "Price, sentiment, signals, catalysts, market context, and the latest important news in one view.",
                        className="page-subtitle simple-only",
                    ),
                    html.P(
                        "Current/latest price, financial news, FinBERT sentiment, live Signal V1, and live Signal V2 components.",
                        className="page-subtitle analyst-only",
                    ),
                    html.Div(id="stock-badge-row", className="badge-row"),
                ],
                className="section-shell page-header-shell stock-terminal-header mb-2",
            ),
            dbc.Row(id="stock-metric-row", className="g-2 metric-strip mb-2"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Market Chart", className="section-kicker"),
                                html.Div(
                                    [
                                        html.H3("Price and News Overlay", className="section-title mb-0"),
                                        dcc.Dropdown(
                                            id="stock-chart-mode",
                                            options=[
                                                {"label": "Price Timeline", "value": "price"},
                                                {"label": "Price vs Sentiment", "value": "overlay"},
                                            ],
                                            value="price",
                                            clearable=False,
                                            searchable=False,
                                            className="finsent-dropdown chart-mode-dropdown analyst-only",
                                        ),
                                    ],
                                    className="chart-card-header",
                                ),
                                dcc.Graph(id="stock-main-chart", config={"displayModeBar": False, "responsive": True}),
                            ],
                            className="chart-card primary-chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div("Instrument", className="section-kicker"),
                                        html.H3("Market Header", className="section-title"),
                                        html.Div(id="stock-summary-panel", className="summary-stack"),
                                    ],
                                    className="section-shell compact-panel mb-3",
                                ),
                                html.Div(
                                    [
                                        html.Div("Signal Intelligence", className="section-kicker"),
                                        html.H3("V1 / V2 / FinBERT", className="section-title"),
                                        html.Div("Live/latest analysis only. Locked validation remains under Research.", className="research-note compact-note"),
                                        html.Div(id="stock-ai-explanation", className="explanation-box compact"),
                                    ],
                                    className="section-shell explanation-shell",
                                ),
                                html.Div(
                                    [
                                        html.Div("Catalyst Intelligence", className="section-kicker"),
                                        html.H3("Catalyst Summary", className="section-title"),
                                        html.Div(id="stock-catalyst-summary", className="summary-stack"),
                                    ],
                                    className="section-shell mt-3",
                                ),
                            ],
                            className="stack-shell",
                        ),
                        lg=4,
                    ),
                ],
                className="g-3 mb-4",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Market Context", className="section-kicker"),
                                html.H3("Relative Performance", className="section-title"),
                                dcc.Graph(id="stock-relative-chart", config={"displayModeBar": False, "responsive": True}),
                            ],
                            className="chart-card",
                        ),
                        lg=8,
                        className="analyst-only",
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Benchmark Intelligence", className="section-kicker"),
                                html.H3("Market Context", className="section-title"),
                                html.Div(id="stock-market-context-panel", className="summary-stack market-context-grid"),
                            ],
                            className="section-shell",
                        ),
                        lg=4,
                        className="stock-market-context-col",
                    ),
                ],
                className="g-3 mb-4",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Catalyst Intelligence", className="section-kicker"),
                                html.H3("Key Catalysts", className="section-title"),
                                html.Div(id="stock-key-catalysts", className="summary-stack catalyst-list"),
                            ],
                            className="section-shell",
                        ),
                        lg=5,
                        className="stock-key-catalyst-col",
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Event Timeline", className="section-kicker"),
                                html.H3("Recent Catalyst Events", className="section-title"),
                                html.Div(id="stock-catalyst-timeline", className="summary-stack catalyst-timeline"),
                            ],
                            className="section-shell",
                        ),
                        lg=7,
                        className="analyst-only",
                    ),
                ],
                className="g-3 mb-4",
            ),
            html.Div(
                [
                    html.Div("Recent News", className="section-kicker"),
                    html.H3("Important Headlines", className="section-title"),
                    html.Div(id="stock-recent-headlines", className="headline-list"),
                ],
                className="section-shell simple-only",
            ),
        ],
        className="analysis-page",
    )
