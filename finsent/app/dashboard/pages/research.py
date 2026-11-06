from __future__ import annotations

from dash import dash_table, dcc, html
from plotly import graph_objects as go

from finsent.app.dashboard.research_results import FinalResearchResultsService, pct
from finsent.app.dashboard.ui_components import compact_empty, metadata_row, research_metric, section_header, status_badge
from finsent.app.dashboard.view_model import PALETTE
from finsent.app.dashboard.widgets import segmented, stat_tile


LABELS = ["BULLISH", "NEUTRAL", "BEARISH"]


def layout() -> html.Div:
    artifact = FinalResearchResultsService().load()
    if not artifact.available:
        return html.Div(
            [
                section_header("Research", "Research & Validation", "Historical evaluation of FinSent's sentiment and signal methodologies."),
                compact_empty("Final evaluation artifact unavailable", artifact.warning or "Run Phase 16 to create locked final artifacts."),
            ],
            className="analysis-page research-page",
        )

    summary = artifact.summary
    warning = artifact.warning
    v1 = summary["metrics"]["v1"]
    v2 = summary["metrics"]["v2"]
    v21 = summary["metrics"].get("v2_1", {})
    baselines = summary["metrics"]["baselines"]
    calibration = summary["confidence_reliability"]["calibration_metrics_secondary"]

    return html.Div(
        [
            html.Div(
                [
                    section_header("Locked Research", "Phase 16 Final Evaluation", "Historical 1D evaluation of FinSent's sentiment and signal methodologies."),
                    html.Div(
                        "Locked historical research: 111 final observations. Signal V1 performed better than V2.0 on the primary balanced metrics; these results are not trading-performance claims.",
                        className="explanation-line simple-only",
                    ),
                    html.Div(
                        [
                            status_badge("Locked research", "PHASE_16"),
                            status_badge("Final experiment", "COMPLETED_LOCKED"),
                            status_badge("Holdout", "FINAL_HOLDOUT_V3_EVALUATED_LOCKED" if artifact.locked else "WARNING"),
                            status_badge("Fingerprint", "verified" if artifact.locked else "warning"),
                        ],
                        className="badge-row",
                    ),
                    html.Div(warning, className="research-warning") if warning else html.Div(
                        "Locked final results apply only to the 1D FNSPID/Yahoo cohort and are not trading-performance claims.",
                        className="research-note compact-note",
                    ),
                ],
                className="section-shell page-header-shell research-header-shell locked-research-banner",
            ),
            html.Div(
                [
                    html.Div("In plain English", className="section-kicker"),
                    html.H3("What the evaluation found", className="section-title"),
                    html.Div(
                        [
                            stat_tile("What we tested", f"{summary['final_evaluated_n']} articles", "Could FinBERT-based signals call the next day's move on news they had never seen?"),
                            stat_tile("Signal V1 accuracy", pct(v1["strict_accuracy"]), "The simpler signal did better than V2.", tone="positive"),
                            stat_tile("Signal V2 accuracy", pct(v2["strict_accuracy"]), "The more complex signal did not beat V1.", tone="negative"),
                            stat_tile("Always guessing the most common move", pct(baselines["majority_class"]["strict_accuracy"]), "Neither signal beat this baseline."),
                        ],
                        className="stat-grid",
                    ),
                    html.P(
                        "News sentiment alone did not predict next-day moves reliably. The value of FinSent is an honest, reproducible test and a clear view of current news, not a trading edge.",
                        className="plain-brief-text research-plain",
                    ),
                ],
                className="section-shell plain-brief simple-only",
            ),
            html.Div(
                [
                    metadata_row("Final N", str(summary["final_evaluated_n"])),
                    metadata_row("Eligible symbols", "AMZN 39 / NVDA 37 / TSLA 35"),
                    metadata_row("Horizon", "1D"),
                    metadata_row("News", "FNSPID"),
                    metadata_row("Sentiment", "FinBERT"),
                    metadata_row("Prices", "Yahoo Chart Daily"),
                ],
                className="metadata-grid research-metadata-grid analyst-only",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Primary Systems", className="section-kicker"),
                            html.H3("Signal V1 vs Signal V2.0", className="section-title"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div("Signal V1", className="research-engine-title"),
                                            research_metric("Strict Accuracy", pct(v1["strict_accuracy"]), v1["total"], "36/111 correct", tone="positive"),
                                            research_metric("Directional Accuracy", pct(v1["directional_accuracy"]), v1["directional_eligible"], "29/58 directional", tone="neutral"),
                                            research_metric("Balanced Accuracy", pct(v1["balanced_accuracy"]), v1["total"], "Best primary balanced result", tone="positive"),
                                            research_metric("Macro F1", pct(v1["macro_f1"]), v1["total"], "31.5%", tone="positive"),
                                        ],
                                        className="research-engine-panel",
                                    ),
                                    html.Div(
                                        [
                                            html.Div("Signal V2.0", className="research-engine-title"),
                                            research_metric("Strict Accuracy", pct(v2["strict_accuracy"]), v2["total"], "25/111 correct", tone="negative"),
                                            research_metric("Directional Accuracy", pct(v2["directional_accuracy"]), v2["directional_eligible"], "19/35 directional", tone="neutral"),
                                            research_metric("Balanced Accuracy", pct(v2["balanced_accuracy"]), v2["total"], "Lower than V1", tone="negative"),
                                            research_metric("Macro F1", pct(v2["macro_f1"]), v2["total"], "Neutral-heavy behavior", tone="negative"),
                                        ],
                                        className="research-engine-panel",
                                    ),
                                ],
                                className="research-engine-grid",
                            ),
                            html.Div("On the locked final cohort, V1 outperformed V2.0 on strict accuracy, balanced accuracy, and macro F1.", className="research-finding"),
                        ],
                        className="section-shell",
                    ),
                    html.Div(
                        [
                            html.Div("Baselines", className="section-kicker"),
                            html.H3("Context, Not Hype", className="section-title"),
                            research_metric("Majority Strict", pct(baselines["majority_class"]["strict_accuracy"]), 111, "Descriptive class-imbalance reference"),
                            research_metric("Majority Balanced", pct(baselines["majority_class"]["balanced_accuracy"]), 111),
                            research_metric("Always Neutral", pct(baselines["always_neutral"]["strict_accuracy"]), 111),
                            research_metric("News Direction", pct(baselines["news_direction"]["strict_accuracy"]), 111),
                        ],
                        className="section-shell",
                    ),
                ],
                className="research-two-column analyst-only",
            ),
            html.Div(
                [
                    html.Div("Classification Metrics", className="section-kicker"),
                    html.H3("Precision, recall and F1 by class", className="section-title"),
                    classification_table({"Signal V1": v1, "Signal V2.0": v2}),
                    html.Div("Each class is scored one-vs-rest on the locked 111-article cohort. Strict accuracy counts NEUTRAL predictions; balanced accuracy averages per-class recall.", className="research-note"),
                ],
                className="section-shell analyst-only",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Historical Research Laboratory", className="section-kicker"),
                                    html.H3("Event study explorer: 1D, 3D and 5D reactions", className="section-title"),
                                ]
                            ),
                            segmented("research-window", [("1D", "1D"), ("3D", "3D"), ("5D", "5D")], "1D"),
                        ],
                        className="panel-head",
                    ),
                    html.Div(
                        "Exploratory and descriptive: Event Study V2 re-measures each locked holdout article at three windows, with abnormal return = stock return − SPY return over the same sessions. Nothing here feeds back into the locked 1D evaluation or the signal engines.",
                        className="research-note",
                    ),
                    dcc.Loading(
                        html.Div(
                            [
                                html.Div(id="research-event-stats", className="stat-grid"),
                                html.Div(
                                    [
                                        html.Div([html.Div("Mean abnormal return by Signal V1 direction (95% CI)", className="sub-title"), dcc.Graph(id="research-event-chart", config={"displayModeBar": False, "responsive": True})]),
                                        html.Div([html.Div("FinBERT score vs abnormal return", className="sub-title"), dcc.Graph(id="research-event-scatter", config={"displayModeBar": False, "responsive": True})]),
                                    ],
                                    className="research-two-column",
                                ),
                                dash_table.DataTable(
                                    id="research-event-table",
                                    page_size=12,
                                    export_format="csv",
                                    export_headers="display",
                                    sort_action="native",
                                    filter_action="native",
                                    style_as_list_view=True,
                                    style_table={"overflowX": "auto"},
                                    style_cell={"backgroundColor": "#101315", "color": "#eef2f3", "border": "0", "borderBottom": "1px solid #1b2023", "fontFamily": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif", "fontSize": "12.5px", "padding": "8px 10px", "textAlign": "left"},
                                    style_header={"backgroundColor": "#101315", "color": "#7d888e", "fontWeight": "600", "fontSize": "11px", "textTransform": "uppercase", "borderBottom": "1px solid #242a2e"},
                                    style_filter={"backgroundColor": "#0a0c0e", "color": "#eef2f3"},
                                    style_data_conditional=[
                                        {"if": {"filter_query": "{AR} > 0", "column_id": "AR"}, "color": "#22c55e"},
                                        {"if": {"filter_query": "{AR} < 0", "column_id": "AR"}, "color": "#ef4444"},
                                        {"if": {"filter_query": "{Hit} = 'Yes'", "column_id": "Hit"}, "color": "#22c55e"},
                                    ],
                                ),
                            ],
                            className="event-lab",
                        ),
                        type="dot",
                        color="#22c55e",
                    ),
                ],
                className="section-shell event-lab-shell analyst-only",
            ),
            html.Div(
                [
                    html.Div([html.Div("Confusion", className="section-kicker"), html.H3("V1 vs Realized", className="section-title"), dcc.Graph(figure=confusion_figure(v1["confusion_matrix"], "Signal V1"), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                    html.Div([html.Div("Confusion", className="section-kicker"), html.H3("V2.0 vs Realized", className="section-title"), dcc.Graph(figure=confusion_figure(v2["confusion_matrix"], "Signal V2.0"), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                ],
                className="research-two-column analyst-only",
            ),
            html.Div(
                [
                    html.Div([html.Div("Class Distribution", className="section-kicker"), html.H3("Signal and Outcome Mix", className="section-title"), dcc.Graph(figure=distribution_figure(summary["class_distributions"]), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                    html.Div([html.Div("Paired Result", className="section-kicker"), html.H3("Identical Observations", className="section-title"), dcc.Graph(figure=paired_figure(summary["paired_analysis"]), config={"displayModeBar": False, "responsive": True}), html.Div("McNemar not run: discordant N=19 was insufficient for meaningful inference.", className="research-note")], className="chart-card"),
                ],
                className="research-two-column analyst-only",
            ),
            html.Div(
                [
                    html.Div([html.Div("Per Symbol", className="section-kicker"), html.H3("AMZN / NVDA / TSLA", className="section-title"), dcc.Graph(figure=per_symbol_figure(summary["symbol_results"]), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                    html.Div(
                        [
                            html.Div("Research Candidate", className="section-kicker"),
                            html.H3("V2.1 Unpromoted", className="section-title"),
                            html.Div("UNPROMOTED RESEARCH CANDIDATE", className="research-warning small-warning"),
                            research_metric("Strict", pct(v21.get("strict_accuracy")), v21.get("total")),
                            research_metric("Directional", pct(v21.get("directional_accuracy")), v21.get("directional_eligible")),
                            research_metric("Balanced", pct(v21.get("balanced_accuracy")), v21.get("total")),
                            research_metric("Macro F1", pct(v21.get("macro_f1")), v21.get("total")),
                        ],
                        className="section-shell",
                    ),
                ],
                className="research-two-column analyst-only",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("V2 Components", className="section-kicker"),
                            html.H3("Descriptive Component Findings", className="section-title"),
                            component_line("News mean, correct", summary["v2_component_analysis"]["news"]["correct_value"]["mean"]),
                            component_line("News mean, incorrect", summary["v2_component_analysis"]["news"]["incorrect_value"]["mean"]),
                            component_line("Momentum mean, correct", summary["v2_component_analysis"]["price_momentum"]["correct_value"]["mean"]),
                            component_line("Volume mean, correct", summary["v2_component_analysis"]["volume_confirmation"]["correct_value"]["mean"]),
                            html.Div("Correct V2 rows had higher mean news contribution and confidence than incorrect rows. This is descriptive only; no tuning follows.", className="research-note"),
                        ],
                        className="section-shell",
                    ),
                    html.Div(
                        [
                            html.Div("Confidence", className="section-kicker"),
                            html.H3("Identity Calibration", className="section-title"),
                            html.Div("NO CALIBRATION JUSTIFIED", className="research-warning small-warning"),
                            research_metric("Raw Mean", f"{summary['confidence_reliability']['raw_confidence']['mean']:.3f}", 111),
                            research_metric("Correct Mean", f"{summary['confidence_reliability']['correct_mean_confidence']['mean']:.3f}", 25),
                            research_metric("Incorrect Mean", f"{summary['confidence_reliability']['incorrect_mean_confidence']['mean']:.3f}", 86),
                            research_metric(
                                "Brier / ECE / MCE",
                                f"{calibration['brier']:.3f} / {calibration['ece']:.3f} / {calibration['mce']:.3f}",
                                111,
                                "Secondary descriptive calibration metrics",
                            ),
                        ],
                        className="section-shell",
                    ),
                ],
                className="research-two-column analyst-only",
            ),
        ],
        className="analysis-page research-page",
    )


def confusion_figure(matrix: dict, title: str) -> go.Figure:
    z = [[matrix[actual][pred] for pred in LABELS] for actual in LABELS]
    fig = go.Figure(go.Heatmap(z=z, x=LABELS, y=LABELS, colorscale=[[0, "#101820"], [1, "#2dd4bf"]], text=z, texttemplate="%{text}", showscale=False))
    fig.update_layout(title=title, xaxis_title="Predicted", yaxis_title="Realized", **plot_layout())
    return fig


def distribution_figure(distributions: dict) -> go.Figure:
    fig = go.Figure()
    for name in ["realized", "finbert", "v1", "v2"]:
        values = distributions[name]
        fig.add_trace(go.Bar(name=name.upper(), x=LABELS, y=[values[label] for label in LABELS]))
    fig.update_layout(title="Class Distributions", barmode="group", **plot_layout())
    return fig


def paired_figure(paired: dict) -> go.Figure:
    labels = ["Both correct", "V1 only", "V2 only", "Both wrong"]
    values = [paired["both_correct"], paired["v1_correct_v2_wrong"], paired["v1_wrong_v2_correct"], paired["both_wrong"]]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=["#2dd4bf", "#34d399", "#fbbf24", "#f87171"]))
    fig.update_layout(title="Paired Correctness", **plot_layout())
    return fig


def per_symbol_figure(symbol_results: dict) -> go.Figure:
    symbols = ["AMZN", "NVDA", "TSLA"]
    v1 = [symbol_results["v1"][symbol]["metrics"]["strict_accuracy"] * 100 for symbol in symbols]
    v2 = [symbol_results["v2"][symbol]["metrics"]["strict_accuracy"] * 100 for symbol in symbols]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="V1 strict", x=symbols, y=v1, marker_color="#34d399"))
    fig.add_trace(go.Bar(name="V2 strict", x=symbols, y=v2, marker_color="#f87171"))
    fig.update_layout(title="Per-Symbol Strict Accuracy", barmode="group", yaxis_title="Accuracy %", **plot_layout())
    return fig


def component_line(label: str, value: float | None) -> html.Div:
    text = "n/a" if value is None else f"{value:+.3f}"
    return html.Div([html.Span(label, className="metadata-label"), html.Span(text, className="metadata-value")], className="metadata-row")


def plot_layout() -> dict:
    return {
        "paper_bgcolor": PALETTE["paper"],
        "plot_bgcolor": PALETTE["paper"],
        "font": {"color": PALETTE["ink"], "family": "Segoe UI, Arial, sans-serif"},
        "margin": {"l": 44, "r": 20, "t": 46, "b": 38},
        "xaxis": {"gridcolor": PALETTE["grid"]},
        "yaxis": {"gridcolor": PALETTE["grid"]},
        "legend": {"orientation": "h", "y": 1.12},
    }


def classification_table(engines: dict[str, dict]) -> html.Div:
    header = html.Div([html.Span("Engine"), html.Span("Class"), html.Span("Precision"), html.Span("Recall"), html.Span("F1")], className="metric-table-row metric-table-head")
    rows = [header]
    for engine, metrics in engines.items():
        for label in LABELS:
            rows.append(
                html.Div(
                    [
                        html.Span(engine, className="metric-engine"),
                        html.Span(label.title()),
                        _metric_bar(metrics["precision"].get(label)),
                        _metric_bar(metrics["recall"].get(label)),
                        _metric_bar(metrics["f1"].get(label)),
                    ],
                    className="metric-table-row",
                )
            )
        rows.append(
            html.Div(
                [html.Span(engine, className="metric-engine"), html.Span("Macro / strict / balanced"), html.B(pct(metrics["macro_f1"])), html.B(pct(metrics["strict_accuracy"])), html.B(pct(metrics["balanced_accuracy"]))],
                className="metric-table-row metric-table-total",
            )
        )
    return html.Div(rows, className="metric-table")


def _metric_bar(value: float | None) -> html.Span:
    if value is None:
        return html.Span("—")
    return html.Span(
        [html.Span(className="metric-bar", style={"width": f"{value * 100:.0f}%"}), html.Span(pct(value), className="metric-bar-value")],
        className="metric-bar-cell",
    )
