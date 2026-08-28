from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Overview", className="section-kicker"),
                    html.H1(id="summary-page-title", className="page-title"),
                    html.P(
                        "A clear view of price, news sentiment, FinSent signals, major catalysts, and market context.",
                        className="page-subtitle simple-only",
                    ),
                    html.P(
                        "Financial news intelligence, provider status, and short-term signal context for the selected instrument.",
                        className="page-subtitle analyst-only",
                    ),
                    html.Div(id="summary-badge-row", className="badge-row"),
                ],
                className="section-shell page-header-shell terminal-page-header mb-2",
            ),
            html.Div(id="summary-status-banner", className="mb-2 market-status-strip"),
            dbc.Row(id="summary-metric-row", className="g-2 metric-strip mb-2"),
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
                className="g-3 mb-3",
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
                className="g-3 mb-3",
            ),
            html.Div(
                [
                    html.Div("Recent News", className="section-kicker"),
                    html.H3("Important Headlines", className="section-title"),
                    html.Div(id="summary-recent-headlines", className="headline-list"),
                ],
                className="section-shell simple-only",
            ),
        ],
        className="analysis-page",
    )
