from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Alerts", className="section-kicker"),
                    html.H1("Operational Watchlist", className="page-title"),
                    html.P(
                        "Compact monitoring for weak sentiment, coverage shifts, and notable movement in the current workspace.",
                        className="page-subtitle",
                    ),
                ],
                className="section-shell page-header-shell compact-page-header mb-2",
            ),
            html.Div(id="alerts-status-banner", className="mb-3"),
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
                                dcc.Graph(id="alerts-shift-chart"),
                            ],
                            className="chart-card",
                        ),
                        lg=12,
                    ),
                ],
                className="g-3 mb-3",
            ),
            dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            html.Div(
                                [
                                    html.Div("Sector Mood", className="section-kicker"),
                                    html.H3("Optional Macro View", className="section-title"),
                                    dcc.Graph(id="alerts-sector-heatmap"),
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
                className="page-accordion mb-4",
            ),
        ],
        className="analysis-page",
    )
