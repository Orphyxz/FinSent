from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Compare", className="section-kicker"),
                    html.H1("Cross-Symbol Research View", className="page-title"),
                    html.P(
                        "Dense peer comparison across price movement, signal state, sentiment, confidence, and coverage.",
                        className="page-subtitle",
                    ),
                ],
                className="section-shell page-header-shell compact-page-header mb-2",
            ),
            html.Div(id="compare-empty-state", className="mb-3"),
            html.Div(
                [
                    html.Div(id="compare-selection-summary", className="compare-selection-summary mb-3"),
                    dbc.Row(id="compare-metric-row", className="g-3 mb-3"),
                    dbc.Row(
                        [
                            dbc.Col(
                                html.Div(
                                    [
                                        html.Div("Relative Performance", className="section-kicker"),
                                        html.H3("Indexed Price Performance", className="section-title"),
                                        html.P(
                                            "All selected tickers are rebased to 100 so the price move is actually comparable.",
                                            className="section-helper",
                                        ),
                                        dcc.Graph(id="compare-main-chart"),
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
                        className="g-3 mb-3",
                    ),
                    html.Div(
                        [
                            html.Div("Signal Snapshot", className="section-kicker"),
                            html.H3("Sentiment, Return, and Confidence", className="section-title"),
                            html.P(
                                "Use this to compare sentiment, window returns, and model confidence without digging through tables.",
                                className="section-helper",
                            ),
                            dcc.Graph(id="compare-secondary-chart"),
                        ],
                        className="chart-card compact-chart-card mb-4",
                    ),
                ],
                id="compare-content",
            ),
        ],
        className="analysis-page",
    )
