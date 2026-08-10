from __future__ import annotations

from dash import html


def section_header(kicker: str, title: str, subtitle: str | None = None) -> html.Div:
    children: list = [html.Div(kicker, className="section-kicker"), html.H2(title, className="section-title")]
    if subtitle:
        children.append(html.P(subtitle, className="section-helper"))
    return html.Div(children, className="panel-header")


def metric_cell(label: str, value: str, note: str | None = None, *, tone: str = "neutral") -> html.Div:
    return html.Div(
        [
            html.Div(label, className="metric-label"),
            html.Div(value, className=f"metric-value tone-{tone}"),
            html.Div(note or "", className="metric-note"),
        ],
        className="metric-card compact-metric",
    )


def research_metric(label: str, value: str, n: int | None = None, note: str | None = None, *, tone: str = "neutral") -> html.Div:
    n_text = f"N={n}" if n is not None else ""
    return html.Div(
        [
            html.Div([html.Span(label), html.Span(n_text, className="metric-n")], className="metric-row-label"),
            html.Div(value, className=f"research-metric-value tone-{tone}"),
            html.Div(note or "", className="metric-note"),
        ],
        className="research-metric",
    )


def status_badge(label: str, status: str | None) -> html.Span:
    normalized = (status or "unavailable").strip().lower().replace("_", "-")
    return html.Span(f"{label}: {(status or 'unavailable').upper()}", className=f"status-badge status-{normalized}")


def signal_badge(label: str | None, *, prefix: str = "Signal") -> html.Span:
    normalized = (label or "neutral").strip().lower()
    if normalized in {"positive", "bullish", "strong_bullish"}:
        tone = "positive"
        text = "Bullish"
    elif normalized in {"negative", "bearish", "strong_bearish"}:
        tone = "negative"
        text = "Bearish"
    else:
        tone = "neutral"
        text = "Neutral"
    return html.Span(f"{prefix}: {text}", className=f"signal-badge signal-{tone}")


def quality_badge(value: str | None) -> html.Span:
    text = (value or "unavailable").upper()
    return html.Span(f"Quality: {text}", className=f"quality-badge quality-{text.lower()}")


def metadata_row(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label, className="metadata-label"), html.Span(value, className="metadata-value")], className="metadata-row")


def component_bar(label: str, value: float | None, note: str | None = None) -> html.Div:
    if value is None:
        width = 0
        tone = "neutral"
        display = "n/a"
    else:
        width = min(abs(float(value)), 1.0) * 100
        tone = "positive" if value > 0.05 else "negative" if value < -0.05 else "neutral"
        display = f"{float(value):+.2f}"
    return html.Div(
        [
            html.Div([html.Span(label), html.Span(display, className=f"component-value tone-{tone}")], className="component-row-top"),
            html.Div(html.Div(className=f"component-fill tone-{tone}", style={"width": f"{width:.0f}%"}), className="component-track"),
            html.Div(note or "", className="component-note"),
        ],
        className="component-row",
    )


def compact_empty(title: str, message: str) -> html.Div:
    return html.Div([html.Div(title, className="empty-state-title"), html.Div(message, className="empty-state-copy")], className="empty-state-card compact-empty")
