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
                        "Financial news intelligence, provider status, and short-term signal context for the selected instrument.",
                        className="page-subtitle",
                    ),
                    html.Div(id="summary-badge-row", className="badge-row"),
                ],
                className="section-shell page-header-shell compact-page-header mb-2",
            ),
            html.Div(id="summary-status-banner", className="mb-2"),
            dbc.Row(id="summary-metric-row", className="g-2 mb-2"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Market Chart", className="section-kicker"),
                                html.H3("Recent Close", className="section-title"),
                                dcc.Graph(id="summary-price-chart"),
                            ],
                            className="chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Signal Transparency", className="section-kicker"),
                                html.H3("Why This Signal", className="section-title"),
                                html.Div("LIVE / DEFAULT: Signal V1", className="research-note compact-note"),
                                html.Div(id="summary-ai-explanation", className="explanation-box compact"),
                            ],
                            className="section-shell explanation-shell",
                        ),
                        lg=4,
                    ),
                ],
                className="g-3 mb-3",
            ),
        ],
        className="analysis-page",
    )
