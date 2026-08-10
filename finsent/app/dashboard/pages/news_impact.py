from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Live News Intelligence", className="section-kicker"),
                    html.H1("Current Financial News", className="page-title"),
                    html.P(
                        "Newest provider-backed headlines first, with FinBERT sentiment, confidence, provenance, catalyst, and impact context.",
                        className="page-subtitle",
                    ),
                ],
                className="section-shell page-header-shell compact-page-header mb-2",
            ),
            html.Div(id="news-impact-status-banner", className="mb-2"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Impact Map", className="section-kicker"),
                                html.H3("Sentiment vs Estimated Impact", className="section-title"),
                                dcc.Graph(id="news-impact-scatter"),
                            ],
                            className="chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Div("Impact Summary", className="section-kicker"),
                                html.H3("Current Window", className="section-title"),
                                html.Div(id="news-impact-summary", className="summary-stack"),
                            ],
                            className="section-shell",
                        ),
                        lg=4,
                    ),
                ],
                className="g-3 mb-3",
            ),
            dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            dash_table.DataTable(
                                id="news-impact-table",
                                page_size=8,
                                sort_action="native",
                                filter_action="native",
                                style_table={"overflowX": "auto"},
                                style_cell={
                                    "textAlign": "left",
                                    "padding": "7px 9px",
                                    "fontFamily": "Segoe UI, Arial, sans-serif",
                                    "backgroundColor": "#111418",
                                    "color": "#f4f7fa",
                                    "border": "1px solid #272d35",
                                    "whiteSpace": "normal",
                                    "height": "auto",
                                    "fontSize": "12px",
                                },
                                style_header={
                                    "backgroundColor": "#171c22",
                                    "fontWeight": "700",
                                    "color": "#f4f7fa",
                                    "border": "1px solid #303843",
                                },
                            ),
                        ],
                        title="Headline table",
                        item_id="headline-table",
                    )
                ],
                start_collapsed=False,
                always_open=False,
                className="page-accordion mb-4",
            ),
        ],
        className="analysis-page",
    )
