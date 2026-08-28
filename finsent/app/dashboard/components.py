from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from finsent.app.dashboard.view_model import get_exchange_options, get_ticker_options


ANALYSIS_NAV_ITEMS = [
    ("Overview", "/summary"),
    ("Stock Research", "/stock-detail"),
    ("News Intelligence", "/news-impact"),
    ("Compare", "/compare"),
    ("Research", "/research"),
    ("Alerts", "/alerts"),
]


def build_navbar() -> html.Div:
    return html.Div(
        [
            dcc.Link(
                [
                    html.Img(src="/assets/finsent-logo.svg", className="brand-logo", alt="FinSent logo"),
                    html.Div(
                        [
                            html.Div("FinSent", className="brand-mark"),
                            html.Div("Financial Intelligence", className="brand-submark"),
                        ],
                        className="brand-copy",
                    ),
                ],
                href="/",
                className="brand-wrap",
                title="FinSent Overview",
            ),
            html.Div(id="nav-links", className="nav-links"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("View", className="visually-hidden"),
                            dcc.RadioItems(
                                id="display-mode-toggle",
                                options=[
                                    {"label": "Simple", "value": "simple"},
                                    {"label": "Analyst", "value": "analyst"},
                                ],
                                value="simple",
                                inline=True,
                                persistence=True,
                                persistence_type="local",
                                className="mode-segmented-control",
                                inputClassName="mode-segmented-input",
                                labelClassName="mode-segmented-label",
                            ),
                        ],
                        className="mode-control-wrap",
                        title="Choose a simplified or detailed dashboard view",
                    ),
                    dcc.Link("Home", href="/", id="nav-home-link", className="nav-home-link", title="Return to overview"),
                    html.Div(id="nav-mode-badge", className="nav-mode-badge"),
                ],
                className="nav-actions",
            ),
        ],
        className="top-nav",
    )


def build_nav_links(pathname: str | None, analysis_ready: bool) -> list[dcc.Link]:
    if not analysis_ready:
        return []

    active_path = "/summary" if (pathname or "/") == "/" else pathname or "/summary"
    links: list[dcc.Link] = []
    for label, path in ANALYSIS_NAV_ITEMS:
        class_name = "nav-link-item is-active" if active_path == path else "nav-link-item"
        links.append(dcc.Link(label, href=path, className=class_name, title=label))
    return links


def build_workspace_bar(
    focus_ticker: str,
    exchange_filter: str,
    compare_tickers: list[str] | None,
    horizon: str,
    date_window: str,
    alert_threshold: int,
) -> html.Div:
    exchange_options = get_exchange_options()
    ticker_options = get_ticker_options(exchange_filter)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Market", className="control-label"),
                                    dcc.RadioItems(
                                        id="global-exchange-filter",
                                        options=exchange_options,
                                        value=exchange_filter,
                                        inline=True,
                                        className="market-segmented-control",
                                        inputClassName="market-segmented-input",
                                        labelClassName="market-segmented-label",
                                    ),
                                ],
                                className="workspace-primary-control",
                            ),
                            html.Div(
                                [
                                    html.Div("Search Company or Ticker", className="control-label"),
                                    dcc.Dropdown(
                                        id="global-focus-ticker",
                                        options=ticker_options,
                                        value=focus_ticker,
                                        clearable=False,
                                        searchable=True,
                                        placeholder="Search AAPL, Apple, RELIANCE...",
                                        optionHeight=42,
                                        maxHeight=300,
                                        className="finsent-dropdown workspace-dropdown",
                                    ),
                                ],
                                className="workspace-primary-control",
                            ),
                        ],
                        className="workspace-primary-block workspace-primary-control-grid",
                    ),
                    html.Div(
                        [
                            html.Div("Research boundary", className="workspace-disclosure-label"),
                            html.Div("Live/latest intelligence remains separate from the locked historical evaluation.", className="workspace-disclosure-copy"),
                        ],
                        className="workspace-disclosure-copy-wrap",
                    ),
                ],
                className="workspace-primary-row",
            ),
            dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div("Time Horizon", className="control-label"),
                                            dcc.Dropdown(
                                                id="global-horizon-toggle",
                                                options=[
                                                    {"label": "Short", "value": "short"},
                                                    {"label": "Medium", "value": "medium"},
                                                    {"label": "Long", "value": "long"},
                                                ],
                                                value=horizon,
                                                clearable=False,
                                                searchable=False,
                                                className="finsent-dropdown workspace-dropdown",
                                            ),
                                        ],
                                        id="horizon-toolbar-control",
                                        className="control-card workspace-filter-card analyst-only",
                                    ),
                                    html.Div(
                                        [
                                            html.Div("Date Window", className="control-label"),
                                            dcc.Dropdown(
                                                id="global-date-window",
                                                options=[
                                                    {"label": "Last 7 Days", "value": "7d"},
                                                    {"label": "Last 30 Days", "value": "30d"},
                                                    {"label": "Last 90 Days", "value": "90d"},
                                                    {"label": "All Live Data", "value": "all"},
                                                ],
                                                value=date_window,
                                                clearable=False,
                                                searchable=False,
                                                className="finsent-dropdown workspace-dropdown date-window-dropdown",
                                            ),
                                        ],
                                        id="date-toolbar-control",
                                        className="control-card workspace-filter-card analyst-only",
                                    ),
                                    html.Div(
                                        [
                                            html.Div("Peer Tickers", className="control-label"),
                                            dcc.Dropdown(
                                                id="global-compare-tickers",
                                                options=ticker_options,
                                                value=compare_tickers or [],
                                                multi=True,
                                                searchable=True,
                                                placeholder="Add 2-5 symbols",
                                                className="finsent-dropdown workspace-dropdown",
                                            ),
                                            html.Div(
                                                "Choose 2-5 symbols, then press Compare.",
                                                className="control-helper",
                                            ),
                                            html.Button(
                                                "Compare",
                                                id="global-compare-apply",
                                                n_clicks=0,
                                                className="workspace-action-button",
                                                title="Apply selected peer tickers",
                                            ),
                                        ],
                                        id="compare-toolbar-control",
                                        className="control-card workspace-filter-card",
                                    ),
                                    html.Div(
                                        [
                                            html.Div("Alert Threshold", className="control-label"),
                                            dcc.Dropdown(
                                                id="global-alert-threshold",
                                                options=[
                                                    {"label": "20", "value": 20},
                                                    {"label": "30", "value": 30},
                                                    {"label": "40", "value": 40},
                                                    {"label": "50", "value": 50},
                                                    {"label": "60", "value": 60},
                                                    {"label": "70", "value": 70},
                                                    {"label": "80", "value": 80},
                                                ],
                                                value=alert_threshold,
                                                clearable=False,
                                                searchable=False,
                                                className="finsent-dropdown workspace-dropdown",
                                            ),
                                        ],
                                        id="alert-toolbar-control",
                                        className="control-card workspace-filter-card analyst-only",
                                    ),
                                ],
                                className="workspace-filter-grid",
                            )
                        ],
                        title="More filters",
                        item_id="workspace-filters",
                    )
                ],
                start_collapsed=True,
                always_open=False,
                className="workspace-accordion",
            ),
        ],
        className="workspace-shell",
    )


def build_landing_search(default_ticker: str) -> html.Div:
    default_exchange = "US"
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Workspace", className="hero-kicker"),
                    html.H1("Select Symbol", className="hero-title landing-title"),
                    html.P(
                        "Choose a supported ticker to populate the analytics workspace with live provider-backed market/news intelligence.",
                        className="hero-copy landing-copy",
                    ),
                ],
                className="landing-copy-wrap",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Market", className="control-label"),
                            dcc.RadioItems(
                                id="landing-exchange-filter",
                                options=get_exchange_options(),
                                value=default_exchange,
                                inline=True,
                                className="market-segmented-control",
                                inputClassName="market-segmented-input",
                                labelClassName="market-segmented-label",
                            ),
                        ],
                        className="landing-search-field",
                    ),
                    html.Div(
                        [
                            html.Div("Search Company / Ticker", className="control-label"),
                            dcc.Dropdown(
                                id="landing-ticker-search",
                                options=get_ticker_options(default_exchange),
                                value=default_ticker,
                                clearable=False,
                                searchable=True,
                                optionHeight=42,
                                maxHeight=300,
                                className="finsent-dropdown landing-search-dropdown",
                            ),
                        ],
                        className="landing-search-field",
                    ),
                    dbc.Button("Load Analysis", id="landing-search-button", className="landing-search-button"),
                ],
                className="landing-search-shell",
            ),
            html.Div("No synthetic prices or fabricated provider status are used.", className="landing-footnote"),
        ],
        className="landing-page",
    )


def build_footer() -> html.Div:
    return html.Div(
        "FinSent Research Terminal | Dash | Plotly | Locked final evaluation read-only",
        className="footer-strip",
    )


def build_button_link(label: str, href: str, class_name: str = "page-link-button") -> dbc.Button:
    return dbc.Button(label, href=href, class_name=class_name, color="link")


def build_empty_state(title: str, message: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, className="empty-state-title"),
            html.Div(message, className="empty-state-copy"),
        ],
        className="empty-state-card",
    )
