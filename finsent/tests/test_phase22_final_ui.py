from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from finsent.app.dashboard import components
from finsent.app.dashboard.app import create_app
from finsent.app.dashboard.layout import build_app_layout
from finsent.app.dashboard.pages import alerts, compare, news_impact, research, stock_detail, summary
from finsent.app.dashboard.ui_components import metric_cell, section_header
from finsent.app.dashboard.view_model import PALETTE, build_empty_figure, build_relative_performance_chart
from finsent.app.dashboard.research_results import FinalResearchResultsService


def test_phase22_layout_keeps_callback_targets_and_places_status_as_utility() -> None:
    layout = build_app_layout("AAPL", ["NVDA", "TSLA"])
    ids = _ids(layout)

    expected = {
        "url",
        "selection-store",
        "top-controls-container",
        "system-status-panel",
        "page-container",
        "global-focus-ticker",
        "global-compare-tickers",
        "global-compare-apply",
    }
    assert expected.issubset(ids)
    direct_ids = [child.id for child in layout.children if hasattr(child, "id") and child.id]
    assert direct_ids.index("system-status-panel") < direct_ids.index("page-container")


def test_phase22_pages_expose_presentation_grade_sections_without_new_features() -> None:
    rendered_pages = [
        summary.layout(),
        stock_detail.layout(),
        news_impact.layout(),
        compare.layout(),
        research.layout(),
        alerts.layout(),
    ]
    all_ids = set()
    for rendered in rendered_pages:
        all_ids.update(_ids(rendered))

    assert {
        "summary-status-banner",
        "summary-price-chart",
        "stock-main-chart",
        "stock-market-context-panel",
        "news-impact-table",
        "compare-market-context-table",
        "alerts-feed",
    }.issubset(all_ids)


def test_phase22_news_terminal_hides_low_priority_metadata() -> None:
    rendered = news_impact.layout()
    tables = _instances(rendered, type_name="DataTable")

    assert len(tables) == 1
    table = tables[0]
    assert table.page_size == 10
    assert "Explanation" in table.hidden_columns
    assert "Event Group" in table.hidden_columns


def test_phase22_research_page_keeps_locked_banner_and_phase16_values() -> None:
    artifact = FinalResearchResultsService().load()
    rendered = research.layout()
    text = " ".join(str(item) for item in _text(rendered))

    assert artifact.available
    assert artifact.summary["final_evaluated_n"] == 111
    assert "Phase 16 Final Evaluation" in text
    assert "Majority Strict" in text
    assert "V2.1 Unpromoted" in text


def test_phase22_design_tokens_and_chart_theme_are_graphite_not_neon() -> None:
    assert PALETTE["paper"] == "#101315"
    assert PALETTE["bull"] == "#22c55e"
    assert PALETTE["bear"] == "#ef4444"

    figure = build_empty_figure("No benchmark", "Market benchmark context unavailable.")
    layout = figure.to_plotly_json()["layout"]
    assert layout["paper_bgcolor"] == PALETTE["paper"]
    assert layout["plot_bgcolor"] == PALETTE["paper"]


def test_phase22_shared_components_use_consistent_section_and_metric_classes() -> None:
    header = section_header("Market Context", "Relative Strength")
    metric = metric_cell("V1", "Bullish", "Research signal; not advice.", tone="positive")

    assert "section-header" in header.className
    assert "metric-positive" in metric.className


def test_phase22_app_callback_map_still_contains_required_outputs() -> None:
    app = create_app()
    callback_keys = "\n".join(app.callback_map)

    for output_id in [
        "summary-metric-row",
        "stock-ai-explanation",
        "news-impact-table",
        "compare-secondary-chart",
        "alerts-sector-heatmap",
        "system-status-panel",
    ]:
        assert output_id in callback_keys


def test_phase22_css_documents_terminal_system_without_external_dependencies() -> None:
    css = Path("finsent/app/dashboard/assets/dashboard.css").read_text(encoding="utf-8")

    assert "--bg-primary: #0a0c0e;" in css
    assert "--surface-hover:" in css
    assert ".terminal-page-header" in css
    assert ".modebar" in css
    assert "@media (min-width: 1200px) and (max-height: 820px)" in css


def _ids(component) -> set[str]:
    ids: set[str] = set()
    if hasattr(component, "id") and component.id:
        ids.add(component.id)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            ids.update(_ids(child))
    elif children is not None and not isinstance(children, (str, int, float)):
        ids.update(_ids(children))
    return ids


def _instances(component, *, type_name: str) -> list[object]:
    found: list[object] = []
    if component.__class__.__name__ == type_name:
        found.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            found.extend(_instances(child, type_name=type_name))
    elif children is not None and not isinstance(children, (str, int, float)):
        found.extend(_instances(children, type_name=type_name))
    return found


def _text(component) -> list[str]:
    if isinstance(component, str):
        return [component]
    children = getattr(component, "children", None)
    values: list[str] = []
    if isinstance(children, str):
        values.append(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            values.extend(_text(child))
    elif children is not None:
        values.extend(_text(children))
    return values
