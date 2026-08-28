from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Monitoring", className="section-kicker"),
                    html.H1("Stocks That Deserve Attention", className="page-title simple-only"),
                    html.H1("Contextual Alerts", className="page-title analyst-only"),
                    html.P(
                        "Current attention signals for strong catalysts, large moves, sentiment shifts, and unusual relative performance. These are not persistent notification subscriptions.",
                        className="page-subtitle simple-only",
                    ),
                    html.P(
                        "Compact monitoring for weak sentiment, coverage shifts, and notable movement in the current workspace. These are not persistent push or email subscriptions.",
                        className="page-subtitle analyst-only",
                    ),
                ],
                className="section-shell page-header-shell terminal-page-header mb-2",
            ),
            html.Div(id="alerts-status-banner", className="mb-3 market-status-strip"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Alert Feed", className="section-kicker"),
                                html.H3("Active Signals", className="section-title"),
                                dbc.ListGroup(id="alerts-feed", flush=True),
                            ],
                            className="section-shell",
                        ),
                        lg=7,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Watchlist Summary", className="section-kicker"),
                                html.H3("At A Glance", className="section-title"),
                                html.Div(id="alerts-summary-panel", className="summary-stack"),
                            ],
                            className="section-shell",
                        ),
                        lg=5,
                    ),
                ],
                className="g-3 mb-3",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Sentiment Trend", className="section-kicker"),
                                html.H3("Recent Shifts", className="section-title"),
                                dcc.Graph(id="alerts-shift-chart", config={"displayModeBar": False, "responsive": True}),
                            ],
                            className="chart-card",
                        ),
                        lg=12,
                    ),
                ],
                className="g-3 mb-3 analyst-only",
            ),
            dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            html.Div(
                                [
                                    html.Div("Sector Mood", className="section-kicker"),
                                    html.H3("Optional Macro View", className="section-title"),
                                    dcc.Graph(id="alerts-sector-heatmap", config={"displayModeBar": False, "responsive": True}),
                                ],
                                className="chart-card compact-chart-card",
                            )
                        ],
                        title="Open sector heatmap",
                        item_id="alerts-sector",
                    )
                ],
                start_collapsed=True,
                always_open=False,
                className="page-accordion mb-4 analyst-only",
            ),
        ],
        className="analysis-page",
    )
