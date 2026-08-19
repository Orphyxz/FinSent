from __future__ import annotations

from dash import dcc, html
from plotly import graph_objects as go
from plotly.subplots import make_subplots

from finsent.app.dashboard.research_results import FinalResearchResultsService, pct
from finsent.app.dashboard.ui_components import compact_empty, metadata_row, research_metric, section_header, status_badge
from finsent.app.dashboard.view_model import PALETTE


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
                    metadata_row("Final N", str(summary["final_evaluated_n"])),
                    metadata_row("Eligible symbols", "AMZN 39 / NVDA 37 / TSLA 35"),
                    metadata_row("Horizon", "1D"),
                    metadata_row("News", "FNSPID"),
                    metadata_row("Sentiment", "FinBERT"),
                    metadata_row("Prices", "Yahoo Chart Daily"),
                ],
                className="metadata-grid research-metadata-grid",
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
                className="research-two-column",
            ),
            html.Div(
                [
                    html.Div([html.Div("Confusion", className="section-kicker"), html.H3("V1 vs Realized", className="section-title"), dcc.Graph(figure=confusion_figure(v1["confusion_matrix"], "Signal V1"), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                    html.Div([html.Div("Confusion", className="section-kicker"), html.H3("V2.0 vs Realized", className="section-title"), dcc.Graph(figure=confusion_figure(v2["confusion_matrix"], "Signal V2.0"), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                ],
                className="research-two-column",
            ),
            html.Div(
                [
                    html.Div([html.Div("Class Distribution", className="section-kicker"), html.H3("Signal and Outcome Mix", className="section-title"), dcc.Graph(figure=distribution_figure(summary["class_distributions"]), config={"displayModeBar": False, "responsive": True})], className="chart-card"),
                    html.Div([html.Div("Paired Result", className="section-kicker"), html.H3("Identical Observations", className="section-title"), dcc.Graph(figure=paired_figure(summary["paired_analysis"]), config={"displayModeBar": False, "responsive": True}), html.Div("McNemar not run: discordant N=19 was insufficient for meaningful inference.", className="research-note")], className="chart-card"),
                ],
                className="research-two-column",
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
                className="research-two-column",
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
                className="research-two-column",
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
