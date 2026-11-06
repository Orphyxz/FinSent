from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from finsent.app.dashboard.widgets import panel, segmented


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Market Map", className="section-kicker"),
                            html.H1("Every stock, one picture", className="page-title"),
                            html.P("All supported stocks grouped by sector and coloured by today's move. Click a sector to zoom in.", className="page-subtitle simple-only"),
                            html.P("Day change versus previous close from one batch snapshot per market (Alpaca for US, Yahoo Chart spark for NSE); colour clipped at ±4%.", className="page-subtitle analyst-only"),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span("Tile size", className="mini-label"),
                            segmented("map-size", [("equal", "Equal"), ("liquidity", "Dollar volume")], "equal"),
                        ],
                        className="map-controls analyst-only",
                    ),
                ],
                className="section-shell page-header-shell exec-header",
            ),
            html.Div(id="map-breadth-strip", className="breadth-strip analyst-only"),
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                dcc.Loading(dcc.Graph(id="market-treemap", config={"displayModeBar": False, "responsive": True}), type="dot", color="#22c55e"),
                                html.Div([html.Span("−4%"), html.Div(className="map-scale-bar"), html.Span("+4%")], className="map-scale"),
                            ],
                            className="chart-card map-card",
                        ),
                        lg=9,
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                panel("Leaders", "Top gainers", html.Div(id="map-gainers"), class_name="accent-positive"),
                                panel("Laggards", "Top losers", html.Div(id="map-losers"), class_name="accent-negative"),
                            ],
                            className="stack-shell",
                        ),
                        lg=3,
                    ),
                ],
                className="g-3",
            ),
            panel("Sector Breadth", "Advancers vs decliners", html.Div(id="map-sector-breadth", className="sector-breadth"), class_name="analyst-only"),
        ],
        className="analysis-page",
    )
