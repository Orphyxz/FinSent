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
                        "Current/latest price, financial news, FinBERT sentiment, live Signal V1, and live Signal V2 components.",
                        className="page-subtitle",
                    ),
                    html.Div(id="stock-badge-row", className="badge-row"),
                ],
                className="section-shell page-header-shell compact-page-header mb-2",
            ),
            dbc.Row(id="stock-metric-row", className="g-2 mb-2"),
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
                                            className="finsent-dropdown chart-mode-dropdown",
                                        ),
                                    ],
                                    className="chart-card-header",
                                ),
                                dcc.Graph(id="stock-main-chart"),
                            ],
                            className="chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div("Instrument", className="section-kicker"),
                                        html.H3("Market Metadata", className="section-title"),
                                        html.Div(id="stock-summary-panel", className="summary-stack"),
                                    ],
                                    className="section-shell mb-3",
                                ),
                                html.Div(
                                    [
                                        html.Div("Signal Transparency", className="section-kicker"),
                                        html.H3("Why This Signal", className="section-title"),
                                        html.Div("LIVE SIGNAL V1 + LIVE SIGNAL V2. Locked research remains separate under Research.", className="research-note compact-note"),
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
                                html.Div("Catalyst Intelligence", className="section-kicker"),
                                html.H3("Key Catalysts", className="section-title"),
                                html.Div(id="stock-key-catalysts", className="summary-stack"),
                            ],
                            className="section-shell",
                        ),
                        lg=5,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Event Timeline", className="section-kicker"),
                                html.H3("Recent Catalyst Events", className="section-title"),
                                html.Div(id="stock-catalyst-timeline", className="summary-stack"),
                            ],
                            className="section-shell",
                        ),
                        lg=7,
                    ),
                ],
                className="g-3 mb-4",
            ),
        ],
        className="analysis-page",
    )
