from __future__ import annotations

from dash import html


def section_header(kicker: str, title: str, subtitle: str | None = None) -> html.Div:
    children: list = [html.Div(kicker, className="section-kicker"), html.H2(title, className="section-title")]
    if subtitle:
        children.append(html.P(subtitle, className="section-helper"))
    return html.Div(children, className="panel-header section-header")


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


def metadata_row(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label, className="metadata-label"), html.Span(value, className="metadata-value")], className="metadata-row")


def compact_empty(title: str, message: str) -> html.Div:
    return html.Div([html.Div(title, className="empty-state-title"), html.Div(message, className="empty-state-copy")], className="empty-state-card compact-empty")
