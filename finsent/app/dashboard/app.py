from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from finsent.app.dashboard.components import build_empty_state, build_nav_links
from finsent.app.dashboard.layout import build_app_layout
from finsent.app.dashboard.pages import alerts, compare, news_impact, research, stock_detail, summary
from finsent.app.dashboard.view_model import (
    buy_sell_ratio_series,
    build_ai_explanation,
    build_simple_signal_explanation,
    build_alert_panel,
    build_alerts,
    build_active_catalysts,
    build_catalyst_summary,
    build_compare_catalyst_table,
    build_compare_market_context_table,
    build_compare_relative_chart,
    build_compare_chart,
    build_dashboard_state,
    build_empty_figure,
    build_focus_status_banner,
    build_impact_scatter,
    build_metric_grid,
    build_news_table,
    build_key_catalysts,
    build_market_context_explanation,
    build_market_context_panel,
    build_overlay_chart,
    build_overview_market_context,
    build_recent_price_histogram,
    build_recent_headlines,
    build_runtime_status_panel,
    build_price_timeline,
    build_relative_performance_chart,
    build_buy_readout,
    build_sector_heatmap,
    build_sentiment_timeline_with_title,
    build_summary_list,
    build_simple_news_table,
    build_catalyst_timeline,
    DATA_MODE_LOCAL,
    confidence_series,
    ensure_live_data,
    get_default_compare_tickers,
    get_default_ticker_for_exchange,
    get_exchange_for_ticker,
    get_market_filter_for_ticker,
    get_company_name,
    get_instrument_metadata,
    get_display_symbol,
    get_assets_folder,
    latest_recent_close,
    get_price_status_note,
    get_ticker_options,
    get_catalyst_direction_options,
    get_catalyst_type_options,
    format_currency,
    label_for_signal,
    spread_pct_series,
    volume_ratio_series,
)


def _selection(data: dict | None) -> dict:
    default_ticker = get_default_ticker_for_exchange("US")
    base = {
        "focus_ticker": default_ticker,
        "exchange_filter": "US",
        "compare_tickers": get_default_compare_tickers(default_ticker, "US"),
        "horizon": "medium",
        "date_window": "30d",
        "alert_threshold": 40,
        "analysis_ready": True,
    }
    if data:
        base.update(data)
    if base.get("exchange_filter") in {"NSE", "BSE"}:
        base["exchange_filter"] = "INDIA"
    return base


def _resolve_date_window(selection: dict) -> tuple[str | None, str | None]:
    today = pd.Timestamp.now().normalize()
    date_window = selection.get("date_window", "30d")
    if date_window == "7d":
        return (today - pd.Timedelta(days=7)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if date_window == "30d":
        return (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if date_window == "90d":
        return (today - pd.Timedelta(days=90)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    return None, None


def _format_price(value: float | None, currency: str | None) -> str:
    return format_currency(value, currency)


def create_app(default_ticker: str | None = None) -> dash.Dash:
    default_ticker = default_ticker or get_default_ticker_for_exchange("US")
    default_compare_tickers = get_default_compare_tickers(default_ticker, "US")
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        assets_folder=get_assets_folder(),
        suppress_callback_exceptions=True,
    )
    app.layout = build_app_layout(default_ticker, default_compare_tickers)

    app.clientside_callback(
        """
        function(mode) {
            return mode === "analyst" ? "analyst" : "simple";
        }
        """,
        Output("display-mode-store", "data"),
        Input("display-mode-toggle", "value"),
    )

    app.clientside_callback(
        """
        function(mode) {
            const selected = mode === "analyst" ? "analyst" : "simple";
            return "dashboard-shell mode-" + selected;
        }
        """,
        Output("dashboard-shell", "className"),
        Input("display-mode-store", "data"),
    )

    @app.callback(
        Output("page-container", "children"),
        Input("url", "pathname"),
        Input("selection-store", "data"),
    )
    def render_page(pathname: str | None, selection_data: dict | None):
        selection = _selection(selection_data)
        routes = {
            "/": summary.layout,
            "/summary": summary.layout,
            "/stock-detail": stock_detail.layout,
            "/news-impact": news_impact.layout,
            "/compare": compare.layout,
            "/research": research.layout,
            "/alerts": alerts.layout,
        }
        current_path = pathname or "/"
        if not selection["analysis_ready"] and current_path != "/research":
            return build_empty_state(
                "Select a symbol",
                "Choose a supported ticker from the top bar to populate the research workspace.",
            )
        return routes.get(current_path, summary.layout)()

    @app.callback(
        Output("live-refresh-store", "data"),
        Input("live-refresh-interval", "n_intervals"),
        State("selection-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_live_workspace(_: int | None, selection_data: dict | None):
        selection = _selection(selection_data)
        if not selection["analysis_ready"] or not selection["focus_ticker"]:
            raise PreventUpdate
        ensure_live_data([selection["focus_ticker"], *selection["compare_tickers"]])
        return {"refreshed_at": pd.Timestamp.utcnow().isoformat()}

    @app.callback(
        Output("top-controls-container", "style"),
        Output("landing-controls-container", "style"),
        Output("horizon-toolbar-control", "style"),
        Output("date-toolbar-control", "style"),
        Output("compare-toolbar-control", "style"),
        Output("alert-toolbar-control", "style"),
        Input("url", "pathname"),
        Input("selection-store", "data"),
    )
    def toggle_top_controls(pathname: str | None, selection_data: dict | None):
        selection = _selection(selection_data)
        current_path = pathname or "/"
        if not selection["analysis_ready"]:
            return {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}

        horizon_style = {"display": "block"} if current_path in {"/", "/summary", "/stock-detail", "/compare", "/alerts"} else {"display": "none"}
        date_style = {"display": "block"} if current_path in {"/", "/summary", "/news-impact"} else {"display": "none"}
        compare_style = {"display": "block"} if current_path in {"/", "/summary", "/stock-detail", "/news-impact", "/compare", "/alerts"} else {"display": "none"}
        alert_style = {"display": "block"} if current_path == "/alerts" else {"display": "none"}
        top_style = {"display": "none"} if current_path == "/research" else {"display": "block"}
        return top_style, {"display": "none"}, horizon_style, date_style, compare_style, alert_style

    @app.callback(
        Output("landing-ticker-search", "value"),
        Output("landing-exchange-filter", "value"),
        Output("global-focus-ticker", "value"),
        Output("global-exchange-filter", "value"),
        Output("global-compare-tickers", "value"),
        Output("global-horizon-toggle", "value"),
        Output("global-date-window", "value"),
        Output("global-alert-threshold", "value"),
        Input("selection-store", "data"),
    )
    def sync_controls_from_selection(selection_data: dict | None):
        selection = _selection(selection_data)
        return (
            selection["focus_ticker"],
            selection["exchange_filter"],
            selection["focus_ticker"],
            selection["exchange_filter"],
            selection["compare_tickers"],
            selection["horizon"],
            selection["date_window"],
            selection["alert_threshold"],
        )

    @app.callback(
        Output("landing-ticker-search", "options"),
        Output("landing-ticker-search", "value", allow_duplicate=True),
        Input("landing-exchange-filter", "value"),
        State("landing-ticker-search", "value"),
        prevent_initial_call=True,
    )
    def sync_landing_tickers(exchange_filter: str | None, current_ticker: str | None):
        options = get_ticker_options(exchange_filter)
        valid_values = {option["value"] for option in options}
        value = current_ticker if current_ticker in valid_values else get_default_ticker_for_exchange(exchange_filter)
        return options, value

    @app.callback(
        Output("global-focus-ticker", "options"),
        Output("global-focus-ticker", "value", allow_duplicate=True),
        Output("global-compare-tickers", "options"),
        Output("global-compare-tickers", "value", allow_duplicate=True),
        Input("global-exchange-filter", "value"),
        State("global-focus-ticker", "value"),
        State("global-compare-tickers", "value"),
        prevent_initial_call=True,
    )
    def sync_workspace_tickers(
        exchange_filter: str | None,
        current_focus: str | None,
        current_compare: list[str] | None,
    ):
        options = get_ticker_options(exchange_filter)
        valid_values = {option["value"] for option in options}
        focus_value = current_focus if current_focus in valid_values else get_default_ticker_for_exchange(exchange_filter)
        compare_values = [ticker for ticker in (current_compare or []) if ticker in valid_values and ticker != focus_value][:4]
        return options, focus_value, options, compare_values

    @app.callback(
        Output("selection-store", "data", allow_duplicate=True),
        Output("url", "pathname"),
        Input("landing-search-button", "n_clicks"),
        State("landing-ticker-search", "value"),
        State("landing-exchange-filter", "value"),
        State("selection-store", "data"),
        prevent_initial_call=True,
    )
    def update_selection_from_landing(
        landing_clicks: int | None,
        landing_ticker: str | None,
        landing_exchange: str | None,
        selection_data: dict | None,
    ):
        if not landing_clicks:
            raise PreventUpdate

        selection = _selection(selection_data)
        if not landing_ticker:
            return no_update, no_update

        selection["focus_ticker"] = landing_ticker
        selection["exchange_filter"] = landing_exchange or get_market_filter_for_ticker(landing_ticker)
        selection["analysis_ready"] = True
        ensure_live_data([landing_ticker])
        return selection, "/summary"

    @app.callback(
        Output("selection-store", "data", allow_duplicate=True),
        Input("global-exchange-filter", "value"),
        Input("global-focus-ticker", "value"),
        Input("global-horizon-toggle", "value"),
        Input("global-date-window", "value"),
        Input("global-alert-threshold", "value"),
        State("selection-store", "data"),
        prevent_initial_call=True,
    )
    def update_selection_from_filters(
        global_exchange_filter: str | None,
        global_focus_ticker: str | None,
        global_horizon: str | None,
        global_date_window: str | None,
        global_alert_threshold: int | None,
        selection_data: dict | None,
    ):
        trigger = ctx.triggered_id
        if trigger is None:
            raise PreventUpdate

        selection = _selection(selection_data)

        if trigger == "global-exchange-filter" and global_exchange_filter:
            selection["exchange_filter"] = global_exchange_filter
            selection["focus_ticker"] = get_default_ticker_for_exchange(global_exchange_filter)
            selection["compare_tickers"] = []
            ensure_live_data([selection["focus_ticker"]])
        elif trigger == "global-focus-ticker" and global_focus_ticker:
            selection["focus_ticker"] = global_focus_ticker
            if selection["exchange_filter"] != "ALL":
                selection["exchange_filter"] = get_market_filter_for_ticker(global_focus_ticker)
            ensure_live_data([global_focus_ticker])
        elif trigger == "global-horizon-toggle" and global_horizon:
            selection["horizon"] = global_horizon
        elif trigger == "global-date-window" and global_date_window:
            selection["date_window"] = global_date_window
        elif trigger == "global-alert-threshold" and global_alert_threshold is not None:
            selection["alert_threshold"] = global_alert_threshold
        else:
            raise PreventUpdate

        return selection

    @app.callback(
        Output("selection-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input("global-compare-apply", "n_clicks"),
        State("global-compare-tickers", "value"),
        State("selection-store", "data"),
        prevent_initial_call=True,
    )
    def apply_compare_selection(
        compare_apply_clicks: int | None,
        global_compare_tickers: list[str] | None,
        selection_data: dict | None,
    ):
        if not compare_apply_clicks:
            raise PreventUpdate

        selection = _selection(selection_data)
        compare_values = [ticker for ticker in (global_compare_tickers or []) if ticker and ticker != selection["focus_ticker"]]
        selection["compare_tickers"] = compare_values[:4]
        return selection, "/compare"

    @app.callback(
        Output("nav-home-link", "style"),
        Output("nav-links", "children"),
        Output("nav-mode-badge", "children"),
        Input("selection-store", "data"),
        Input("url", "pathname"),
        Input("live-refresh-store", "data"),
    )
    def update_nav_badge(selection_data: dict | None, pathname: str | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        current_path = pathname or "/"
        nav_links = build_nav_links(pathname, selection["analysis_ready"])
        home_style = {"display": "inline-flex"} if current_path != "/" else {"display": "none"}
        if not selection["analysis_ready"]:
            return home_style, nav_links, "Select a ticker"
        if current_path == "/research":
            return home_style, nav_links, "Research results locked"

        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(
            selection["focus_ticker"],
            selection["compare_tickers"],
            selection["horizon"],
            start_date,
            end_date,
        )
        company_name = get_company_name(selection["focus_ticker"])
        focus_row = state.compare_df[state.compare_df["ticker"] == selection["focus_ticker"]]
        mode_label = focus_row["mode"].iloc[0] if not focus_row.empty else "Unavailable"
        refresh_label = "Local research mode" if state.data_mode == DATA_MODE_LOCAL else "Auto-refresh on"
        data_label = f"{mode_label} | {refresh_label}"
        return home_style, nav_links, f'{get_display_symbol(selection["focus_ticker"])} | {company_name} | {data_label}'

    @app.callback(
        Output("system-status-panel", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_system_status(_selection_data: dict | None, _refresh_data: dict | None):
        return build_runtime_status_panel()

    @app.callback(
        Output("summary-page-title", "children"),
        Output("summary-badge-row", "children"),
        Output("summary-status-banner", "children"),
        Output("summary-market-context", "children"),
        Output("summary-metric-row", "children"),
        Output("summary-active-catalysts", "children"),
        Output("summary-price-chart", "figure"),
        Output("summary-ai-explanation", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_summary(selection_data: dict | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        if not selection["analysis_ready"] or not focus_ticker:
            raise PreventUpdate

        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(
            focus_ticker,
            selection["compare_tickers"],
            selection["horizon"],
            start_date,
            end_date,
        )
        company_name = get_company_name(focus_ticker)
        ticker_news = state.news_df[state.news_df["ticker"] == focus_ticker]
        ticker_prices = state.price_df[state.price_df["ticker"] == focus_ticker]
        compare_row = state.compare_df[state.compare_df["ticker"] == focus_ticker]
        snapshot = state.snapshot_map.get(focus_ticker)
        quote_meta = state.quote_meta_map.get(focus_ticker)
        avg_sentiment = float(ticker_news["sentiment_score"].mean()) if not ticker_news.empty else float(snapshot.market_signal if snapshot is not None else 0.0)
        avg_confidence = float(confidence_series(ticker_news).mean() * 100.0) if not ticker_news.empty else float("nan")
        avg_buy_sell_ratio = float(buy_sell_ratio_series(ticker_news).mean()) if not ticker_news.empty else float(snapshot.buy_sell_ratio if snapshot is not None else 1.0)
        latest_label = (
            ticker_news["sentiment_label"].iloc[-1].title()
            if not ticker_news.empty
            else str(compare_row["signal_label"].iloc[0]).title() if not compare_row.empty
            else label_for_signal(avg_sentiment).title()
        )
        fallback_close = latest_recent_close(ticker_prices)
        current_price = float(snapshot.last_price) if snapshot is not None and snapshot.last_price is not None else fallback_close or 0.0
        currency = compare_row["currency"].iloc[0] if not compare_row.empty else (quote_meta or {}).get("currency")
        price_note = get_price_status_note(focus_ticker, bool(current_price), quote_meta)
        price_change = 0.0
        if len(ticker_prices) >= 2:
            first_close = float(ticker_prices["close"].iloc[0])
            last_close = float(ticker_prices["close"].iloc[-1])
            price_change = ((last_close - first_close) / first_close) * 100.0 if first_close else 0.0

        market_status = compare_row["market_status"].iloc[0] if not compare_row.empty and "market_status" in compare_row.columns else "UNKNOWN"
        feed = compare_row["feed"].iloc[0] if not compare_row.empty and "feed" in compare_row.columns else ""
        badges = [
            html.Div(f"{latest_label} LIVE SIGNAL V1", className="pill-badge"),
            html.Div(market_status, className="pill-badge"),
            html.Div(f"Feed {feed or 'n/a'}", className="pill-badge analyst-only"),
        ]
        confidence_value = f"{avg_confidence:.0f}%" if pd.notna(avg_confidence) else "n/a"
        confidence_note = "Average article/model confidence" if pd.notna(avg_confidence) else "Awaiting fresh headlines; quote-quality only"
        local_summary = state.local_summary or {}
        local_symbols = ", ".join(local_summary.get("symbols", [])[:5]) if local_summary.get("symbols") else "n/a"
        analyst_metrics = build_metric_grid(
            [
                ("Price", _format_price(current_price if current_price else None, currency), price_note),
                ("Window Move", f"{price_change:+.2f}%", "Computed from available live/recent bars"),
                ("Live News", str(len(ticker_news)), f"Research dataset secondary: {local_summary.get('articles', 0)} archived articles across {local_symbols}"),
                ("FinBERT Signal", confidence_value, confidence_note),
            ],
            column_size=3,
            class_name="analyst-only",
        )
        v1_label = str(compare_row["signal_label"].iloc[0]).replace("_", " ").title() if not compare_row.empty else latest_label
        v2_label = str(compare_row["v2_label"].iloc[0]).replace("_", " ").title() if not compare_row.empty else "Unavailable"
        freshness = str(compare_row["freshness_label"].iloc[0]).replace("_", " ").title() if not compare_row.empty else "Unavailable"
        simple_metrics = build_metric_grid(
            [
                ("Price", _format_price(current_price if current_price else None, currency), price_note),
                ("Price Change", f"{price_change:+.2f}%", "Selected recent window"),
                ("FinBERT", latest_label, "Recent headline sentiment"),
                ("Signal V1", v1_label, "News and quote-quality signal"),
                ("Signal V2", v2_label, "News, momentum, and volume signal"),
                ("Freshness", freshness, f"Market status: {market_status.replace('_', ' ').title()}"),
            ],
            column_size=2,
            class_name="simple-only",
        )
        metrics = [*simple_metrics, *analyst_metrics]
        figure = (
            build_recent_price_histogram(
                ticker_prices,
                title=f"{focus_ticker} Last 7 Trading Days",
            )
            if not ticker_prices.empty
            else build_empty_figure(
                f"{focus_ticker} Last 7 Trading Days",
                "No live market price history is available for the current window.",
            )
        )
        explanation_lines = build_ai_explanation(focus_ticker, state.news_df, state.compare_df)[:3]
        simple_explanation = build_simple_signal_explanation(focus_ticker, state.news_df, state.compare_df)
        return (
            f"{get_display_symbol(focus_ticker)} | {company_name}",
            badges,
            build_focus_status_banner(focus_ticker, state),
            build_overview_market_context(state.market_context_df, state.compare_df),
            metrics,
            build_active_catalysts(state.catalyst_df),
            figure,
            [
                html.Div([html.Div(line, className="explanation-line") for line in simple_explanation], className="simple-only"),
                html.Div([html.Div(line, className="explanation-line") for line in explanation_lines], className="analyst-only"),
            ],
        )

    @app.callback(
        Output("summary-recent-headlines", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_summary_headlines(selection_data: dict | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(focus_ticker, selection["compare_tickers"], selection["horizon"], start_date, end_date)
        return build_recent_headlines(state.news_df, focus_ticker)

    @app.callback(
        Output("stock-page-title", "children"),
        Output("stock-badge-row", "children"),
        Output("stock-metric-row", "children"),
        Output("stock-main-chart", "figure"),
        Output("stock-ai-explanation", "children"),
        Output("stock-summary-panel", "children"),
        Output("stock-relative-chart", "figure"),
        Output("stock-market-context-panel", "children"),
        Output("stock-catalyst-summary", "children"),
        Output("stock-key-catalysts", "children"),
        Output("stock-catalyst-timeline", "children"),
        Input("stock-chart-mode", "value"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_stock_detail(chart_mode: str | None, selection_data: dict | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        if not selection["analysis_ready"] or not focus_ticker:
            raise PreventUpdate
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(
            focus_ticker,
            selection["compare_tickers"],
            selection["horizon"],
            start_date,
            end_date,
        )
        ticker_news = state.news_df[state.news_df["ticker"] == focus_ticker]
        ticker_prices = state.price_df[state.price_df["ticker"] == focus_ticker]
        ticker_events = state.event_df[state.event_df["ticker"] == focus_ticker] if not state.event_df.empty else pd.DataFrame()
        compare_row = state.compare_df[state.compare_df["ticker"] == focus_ticker]
        snapshot = state.snapshot_map.get(focus_ticker)
        quote_meta = state.quote_meta_map.get(focus_ticker)
        company_name = get_company_name(focus_ticker)
        avg_sentiment = float(ticker_news["sentiment_score"].mean()) if not ticker_news.empty else float(snapshot.market_signal if snapshot is not None else 0.0)
        avg_confidence = float(confidence_series(ticker_news).mean() * 100.0) if not ticker_news.empty else float("nan")
        avg_spread_pct = float(spread_pct_series(ticker_news).mean() * 100.0) if not ticker_news.empty else float((snapshot.spread_pct * 100.0) if snapshot is not None else 0.0)
        avg_buy_sell_ratio = float(buy_sell_ratio_series(ticker_news).mean()) if not ticker_news.empty else float(snapshot.buy_sell_ratio if snapshot is not None else 1.0)
        avg_volume_ratio = float(volume_ratio_series(ticker_news).mean()) if not ticker_news.empty else float(snapshot.volume_ratio if snapshot is not None else 1.0)
        price_change = 0.0
        if len(ticker_prices) >= 2:
            first_close = float(ticker_prices["close"].iloc[0])
            last_close = float(ticker_prices["close"].iloc[-1])
            price_change = ((last_close - first_close) / first_close) * 100.0 if first_close else 0.0
        latest_label = (
            ticker_news["sentiment_label"].iloc[-1].title()
            if not ticker_news.empty
            else str(compare_row["signal_label"].iloc[0]).title() if not compare_row.empty
            else label_for_signal(avg_sentiment).title()
        )
        avg_impact = float(ticker_events["impact_pct"].mean()) if not ticker_events.empty else 0.0
        fallback_close = latest_recent_close(ticker_prices)
        current_price = float(snapshot.last_price) if snapshot is not None and snapshot.last_price is not None else fallback_close or 0.0
        currency = compare_row["currency"].iloc[0] if not compare_row.empty else (quote_meta or {}).get("currency")
        price_note = get_price_status_note(focus_ticker, bool(current_price), quote_meta)
        badges = [
            html.Div(f"{latest_label} FINBERT", className="pill-badge"),
            html.Div("LIVE SIGNAL V1", className="pill-badge"),
            html.Div("LIVE SIGNAL V2", className="pill-badge"),
            html.Div(f"Estimated impact {avg_impact:.2f}%", className="pill-badge analyst-only"),
        ]
        confidence_value = f"{avg_confidence:.0f}%" if pd.notna(avg_confidence) else "n/a"
        confidence_note = "Average article/model confidence" if pd.notna(avg_confidence) else "Awaiting fresh headlines; quote-quality only"
        analyst_metrics = build_metric_grid(
            [
                ("Price", "Unavailable" if state.data_mode == DATA_MODE_LOCAL else _format_price(current_price if current_price else None, currency), price_note),
                ("Window Move", f"{price_change:+.2f}%", "Selected live/recent price window"),
                ("Signal V1", f"{avg_sentiment:+.2f}", compare_row["mode"].iloc[0] if not compare_row.empty else latest_label),
                ("Signal Confidence", confidence_value, confidence_note),
            ],
            column_size=3,
            class_name="analyst-only",
        )
        v1_label = str(compare_row["signal_label"].iloc[0]).replace("_", " ").title() if not compare_row.empty else latest_label
        v2_label = str(compare_row["v2_label"].iloc[0]).replace("_", " ").title() if not compare_row.empty else "Unavailable"
        freshness = str(compare_row["freshness_label"].iloc[0]).replace("_", " ").title() if not compare_row.empty else "Unavailable"
        simple_metrics = build_metric_grid(
            [
                ("Price", "Unavailable" if state.data_mode == DATA_MODE_LOCAL else _format_price(current_price if current_price else None, currency), price_note),
                ("Price Change", f"{price_change:+.2f}%", "Selected recent window"),
                ("FinBERT", latest_label, "Current headline sentiment"),
                ("Signal V1", v1_label, "Primary analytical signal"),
                ("Signal V2", v2_label, "News, momentum, and volume"),
                ("Freshness", freshness, "Latest provider-backed state"),
            ],
            column_size=2,
            class_name="simple-only",
        )
        metrics = [*simple_metrics, *analyst_metrics]
        analyst_summary = build_summary_list(
            [
                (
                    "Sector",
                    compare_row["sector"].iloc[0]
                    if not compare_row.empty
                    else "n/a",
                ),
                ("Company", company_name),
                ("Exchange", compare_row["exchange"].iloc[0] if not compare_row.empty else "n/a"),
                ("Quote Quality", compare_row["quote_quality"].iloc[0] if not compare_row.empty else "n/a"),
                ("Market Status", compare_row["market_status"].iloc[0] if not compare_row.empty and "market_status" in compare_row.columns else "UNKNOWN"),
                ("Data Feed", compare_row["feed"].iloc[0] if not compare_row.empty and "feed" in compare_row.columns else "n/a"),
                ("Data Mode", state.data_mode),
                ("News Volume", str(len(ticker_news))),
                ("Articles", str(len(ticker_news))),
                ("Last Update", ticker_news["published_at"].max().strftime("%Y-%m-%d %H:%M") if not ticker_news.empty else "n/a"),
                ("Average Impact", f"{avg_impact:.2f}%"),
                ("Avg Spread", f"{avg_spread_pct:.2f}%"),
                ("Liquidity Proxy", f"{avg_buy_sell_ratio:.2f}x"),
                ("Stored Volume Context", f"{avg_volume_ratio:.2f}x"),
                ("Correlation", f'{ticker_events["sentiment_score"].corr(ticker_events["forward_return"]):.2f}' if len(ticker_events) >= 2 else "n/a"),
            ]
        )
        simple_summary = build_summary_list(
            [
                ("Company", company_name),
                ("Market", get_market_filter_for_ticker(focus_ticker).title()),
                ("Exchange", compare_row["exchange"].iloc[0] if not compare_row.empty else "n/a"),
                ("Currency", str(currency or "n/a")),
                ("Market Status", compare_row["market_status"].iloc[0] if not compare_row.empty else "UNKNOWN"),
                ("Information Age", freshness),
            ]
        )
        summary = [html.Div(simple_summary, className="simple-only"), html.Div(analyst_summary, className="analyst-only")]
        if chart_mode == "overlay":
            main_chart = build_overlay_chart(focus_ticker, state.price_df, state.news_df)
        else:
            main_chart = (
                build_price_timeline(
                    ticker_prices if not ticker_prices.empty else state.price_df.head(0),
                    title=f"{focus_ticker} Price Timeline",
                )
                if not ticker_prices.empty
                else build_empty_figure(f"{focus_ticker} Price Timeline", "Live quote unavailable. No stored historical price bars were found for this selected symbol.")
            )
        signal_lines = build_ai_explanation(focus_ticker, state.news_df, state.compare_df)
        simple_signal_lines = build_simple_signal_explanation(focus_ticker, state.news_df, state.compare_df)
        for line in build_market_context_explanation(focus_ticker, state.market_context_df, state.catalyst_df):
            if line and line not in signal_lines:
                signal_lines.append(line)
        signal_meta = state.signal_meta_map.get(focus_ticker, {})
        for line in signal_meta.get("explanation_bullets", [])[:5]:
            if line and line not in signal_lines:
                signal_lines.append(str(line))
        return (
            f"{get_display_symbol(focus_ticker)} | {company_name}",
            badges,
            metrics,
            main_chart,
            [
                html.Div([html.Div(line, className="explanation-line") for line in simple_signal_lines], className="simple-only"),
                html.Div([html.Div(line, className="explanation-line") for line in signal_lines], className="analyst-only"),
            ],
            summary,
            build_relative_performance_chart(focus_ticker, state.price_df, state.market_context_df),
            build_market_context_panel(state.market_context_df, focus_ticker),
            build_catalyst_summary(state.catalyst_df, focus_ticker),
            build_key_catalysts(state.catalyst_df, focus_ticker),
            build_catalyst_timeline(state.catalyst_df, focus_ticker),
        )

    @app.callback(
        Output("stock-recent-headlines", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_stock_headlines(selection_data: dict | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(focus_ticker, selection["compare_tickers"], selection["horizon"], start_date, end_date)
        return build_recent_headlines(state.news_df, focus_ticker)

    @app.callback(
        Output("news-impact-status-banner", "children"),
        Output("news-impact-scatter", "figure"),
        Output("news-impact-summary", "children"),
        Output("news-impact-table", "data"),
        Output("news-impact-table", "columns"),
        Output("news-symbol-filter", "options"),
        Output("news-catalyst-filter", "options"),
        Output("news-direction-filter", "options"),
        Input("news-symbol-filter", "value"),
        Input("news-catalyst-filter", "value"),
        Input("news-direction-filter", "value"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_news_impact(
        symbol_filter: list[str] | None,
        catalyst_filter: list[str] | None,
        direction_filter: list[str] | None,
        selection_data: dict | None,
        _refresh_data: dict | None,
    ):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        if not selection["analysis_ready"] or not focus_ticker:
            raise PreventUpdate
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(
            focus_ticker,
            selection["compare_tickers"],
            selection["horizon"],
            start_date,
            end_date,
        )
        filtered_news = state.news_df.copy()
        selected_symbols = symbol_filter or [focus_ticker]
        if selected_symbols:
            filtered_news = filtered_news[filtered_news["ticker"].isin(selected_symbols)]
        if catalyst_filter and "catalyst_type" in filtered_news.columns:
            filtered_news = filtered_news[filtered_news["catalyst_type"].isin(catalyst_filter)]
        if direction_filter and "catalyst_direction" in filtered_news.columns:
            filtered_news = filtered_news[filtered_news["catalyst_direction"].isin(direction_filter)]
        filtered_events = state.event_df[state.event_df["ticker"].isin(selected_symbols)] if not state.event_df.empty and selected_symbols else state.event_df
        table_df = build_news_table(filtered_events, filtered_news)
        impact_source = filtered_events if not filtered_events.empty else filtered_news
        average_impact = (
            float(filtered_events["impact_pct"].mean())
            if not filtered_events.empty
            else float(pd.to_numeric(filtered_news.get("impact_strength"), errors="coerce").fillna(0.0).mean() * 100.0)
            if not filtered_news.empty
            else None
        )
        highest_positive = (
            float(filtered_events["impact_pct"].max())
            if not filtered_events.empty
            else float((pd.to_numeric(filtered_news.get("impact_strength"), errors="coerce").fillna(0.0) * 100.0).max())
            if not filtered_news.empty
            else None
        )
        highest_negative = (
            float(filtered_events["impact_pct"].min())
            if not filtered_events.empty
            else None
        )
        average_confidence = (
            float(filtered_events["confidence_pct"].mean())
            if not filtered_events.empty
            else float(confidence_series(filtered_news).mean() * 100.0)
            if not filtered_news.empty
            else None
        )
        summary = build_summary_list(
            [
                ("Headlines", str(len(table_df))),
                ("Average Impact", f"{average_impact:.2f}%" if average_impact is not None else "n/a"),
                ("Highest Positive", f"{highest_positive:.2f}%" if highest_positive is not None else "n/a"),
                ("Highest Negative", f"{highest_negative:.2f}%" if highest_negative is not None else "n/a"),
                ("Average Confidence", f"{average_confidence:.0f}%" if average_confidence is not None else "n/a"),
            ]
        )
        return (
            build_focus_status_banner(focus_ticker, state),
            build_impact_scatter(filtered_events, filtered_news)
            if not impact_source.empty
            else build_empty_figure(
                "Sentiment vs Estimated Impact",
                f"No recent headlines or usable impact estimates are available for {focus_ticker} in this window.",
            ),
            summary,
            table_df.to_dict("records"),
            [{"name": col, "id": col} for col in table_df.columns],
            [{"label": symbol, "value": symbol} for symbol in sorted(state.news_df.get("ticker", pd.Series(dtype=str)).dropna().unique().tolist())],
            get_catalyst_type_options(),
            get_catalyst_direction_options(),
        )

    @app.callback(
        Output("news-simple-table", "children"),
        Input("news-symbol-filter", "value"),
        Input("news-catalyst-filter", "value"),
        Input("news-direction-filter", "value"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_simple_news_table(
        symbol_filter: list[str] | None,
        catalyst_filter: list[str] | None,
        direction_filter: list[str] | None,
        selection_data: dict | None,
        _refresh_data: dict | None,
    ):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(focus_ticker, selection["compare_tickers"], selection["horizon"], start_date, end_date)
        selected_symbols = symbol_filter or [focus_ticker]
        filtered_news = state.news_df[state.news_df["ticker"].isin(selected_symbols)].copy()
        if catalyst_filter and "catalyst_type" in filtered_news.columns:
            filtered_news = filtered_news[filtered_news["catalyst_type"].isin(catalyst_filter)]
        if direction_filter and "catalyst_direction" in filtered_news.columns:
            filtered_news = filtered_news[filtered_news["catalyst_direction"].isin(direction_filter)]
        filtered_events = state.event_df[state.event_df["ticker"].isin(selected_symbols)] if not state.event_df.empty else state.event_df
        table = build_simple_news_table(filtered_events, filtered_news)
        if table.empty:
            return build_empty_state("No recent news", "No matching headlines are available for the selected symbol and filters.")
        columns = list(table.columns)
        return html.Table(
            [
                html.Thead(html.Tr([html.Th(column) for column in columns])),
                html.Tbody(
                    [
                        html.Tr([html.Td(str(row[column])) for column in columns])
                        for _, row in table.head(10).iterrows()
                    ]
                ),
            ],
            className="simple-news-table",
        )

    @app.callback(
        Output("compare-selection-summary", "children"),
        Output("compare-empty-state", "children"),
        Output("compare-empty-state", "style"),
        Output("compare-content", "style"),
        Output("compare-metric-row", "children"),
        Output("compare-main-chart", "figure"),
        Output("compare-secondary-chart", "figure"),
        Output("compare-ai-summary", "children"),
        Output("compare-market-context-table", "children"),
        Output("compare-catalyst-table", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_compare(selection_data: dict | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        if not selection["analysis_ready"] or not focus_ticker:
            raise PreventUpdate
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(
            focus_ticker,
            selection["compare_tickers"],
            selection["horizon"],
            start_date,
            end_date,
        )
        compare_df = state.compare_df.copy()
        applied_peers = selection["compare_tickers"][:4]
        focus_display = get_instrument_metadata(focus_ticker)
        peer_labels = [
            f'{get_instrument_metadata(value)["symbol"]} ({get_instrument_metadata(value)["market"]})'
            for value in applied_peers
        ]
        selection_summary = (
            html.Div(
                [
                    html.Div("Applied Comparison", className="section-kicker"),
                    html.Div(
                        f'{focus_display["symbol"]} ({focus_display["market"]}) vs ' + " | ".join(peer_labels),
                        className="compare-selection-value",
                    ),
                ],
                className="section-shell compare-selection-shell",
            )
            if applied_peers
            else html.Div()
        )
        if len(compare_df) < 2:
            return (
                selection_summary,
                build_empty_state(
                    "Add peer tickers to compare",
                    f"Use More filters to choose 2-5 symbols, then press Compare. The page will then rank live/latest price, sentiment, signals, and freshness against {focus_ticker}.",
                ),
                {"display": "block"},
                {"display": "none"},
                [],
                build_empty_figure("Peer Comparison", "Peer comparison will appear after you select additional tickers."),
                build_empty_figure("Relative Price Performance", "Choose peer tickers to unlock the secondary comparison view."),
                [html.Div("Comparison insights will appear here once at least two tickers are loaded.", className="explanation-line")],
                [],
                [],
            )

        analyst_metrics = build_metric_grid(
            [
                ("Top Sentiment", compare_df.sort_values("avg_sentiment", ascending=False)["ticker"].iloc[0] if not compare_df.empty else "n/a", "Highest average headline tone"),
                ("Leading Return", compare_df.sort_values("pct_change", ascending=False)["ticker"].iloc[0] if not compare_df.empty else "n/a", "Strongest move in the selected live/latest window"),
                ("News Volume", compare_df.sort_values("news_volume", ascending=False)["ticker"].iloc[0] if not compare_df.empty else "n/a", "Most headline coverage"),
                ("Confidence", compare_df.sort_values("avg_confidence", ascending=False)["ticker"].iloc[0] if not compare_df.empty else "n/a", "Highest average model confidence"),
            ],
            column_size=3,
            class_name="analyst-only",
        )
        strongest = compare_df.sort_values("catalyst_count", ascending=False).iloc[0]
        relative_rows = compare_df.dropna(subset=["market_relative_return"]) if "market_relative_return" in compare_df.columns else pd.DataFrame()
        relative_leader_label = relative_rows.sort_values("market_relative_return", ascending=False)["ticker"].iloc[0] if not relative_rows.empty else "Unavailable"
        v1_leader = compare_df.sort_values("avg_sentiment", ascending=False).iloc[0]
        v2_rows = compare_df[pd.to_numeric(compare_df["v2_score"], errors="coerce").notna()]
        v2_leader_label = v2_rows.sort_values("v2_score", ascending=False)["ticker"].iloc[0] if not v2_rows.empty else "Unavailable"
        simple_metrics = build_metric_grid(
            [
                ("Price Move", get_display_symbol(str(compare_df.sort_values("pct_change", ascending=False)["ticker"].iloc[0])), "Strongest normalized window move"),
                ("FinBERT", get_display_symbol(str(v1_leader["ticker"])), f'{float(v1_leader["avg_sentiment"]):+.2f} sentiment score'),
                ("Signal V1", get_display_symbol(str(v1_leader["ticker"])), str(v1_leader.get("signal_label") or "neutral").replace("_", " ").title()),
                ("Signal V2", get_display_symbol(str(v2_leader_label)), "Highest available V2 score"),
                ("Market-relative", get_display_symbol(str(relative_leader_label)) if relative_leader_label != "Unavailable" else "Unavailable", "US benchmark context where supported"),
                ("Strongest Catalyst", get_display_symbol(str(strongest["ticker"])), str(strongest.get("top_catalyst") or "Unknown").replace("_", " ").title()),
            ],
            column_size=2,
            class_name="simple-only",
        )
        metrics = [*simple_metrics, *analyst_metrics]
        summary_lines: list[html.Div] = []
        if not compare_df.empty:
            leader = compare_df.sort_values("avg_sentiment", ascending=False).iloc[0]
            winner = compare_df.sort_values("pct_change", ascending=False).iloc[0]
            laggard = compare_df.sort_values("pct_change", ascending=True).iloc[0]
            reliable = compare_df.sort_values("avg_confidence", ascending=False).iloc[0]
            summary_lines = [
                html.Div(f'{winner["ticker"]} is leading on relative performance at {winner["pct_change"]:.2f}% in the selected live/latest comparison window.', className="explanation-line"),
                html.Div(f'{leader["ticker"]} has the strongest sentiment signal with an average score of {leader["avg_sentiment"]:.2f}.', className="explanation-line"),
                html.Div(f'{reliable["ticker"]} has the highest average model confidence at {reliable["avg_confidence"]:.0f}%, while {laggard["ticker"]} is the weakest price mover.', className="explanation-line"),
            ]
            relative_rows = compare_df.dropna(subset=["market_relative_return"]) if "market_relative_return" in compare_df.columns else pd.DataFrame()
            if not relative_rows.empty:
                relative_leader = relative_rows.sort_values("market_relative_return", ascending=False).iloc[0]
                summary_lines.append(
                    html.Div(
                        f'{relative_leader["ticker"]} leads the relative strength ranking versus SPY in the selected window.',
                        className="explanation-line",
                    )
                )
            catalyst_rows = compare_df[compare_df["catalyst_count"] > 0] if "catalyst_count" in compare_df.columns else pd.DataFrame()
            if not catalyst_rows.empty:
                top = catalyst_rows.sort_values("catalyst_count", ascending=False).iloc[0]
                summary_lines.append(
                    html.Div(
                        f'{top["ticker"]} has the broadest recent catalyst coverage: {int(top["catalyst_count"])} event group(s), led by {str(top["top_catalyst"]).replace("_", " ").title()}.',
                        className="explanation-line",
                    )
                )
        return (
            selection_summary,
            [],
            {"display": "none"},
            {"display": "block"},
            metrics,
            build_price_timeline(state.price_df, title="Indexed Price Performance", normalize=True),
            build_compare_relative_chart(compare_df),
            summary_lines,
            build_compare_market_context_table(compare_df),
            build_compare_catalyst_table(compare_df),
        )

    @app.callback(
        Output("alerts-status-banner", "children"),
        Output("alerts-feed", "children"),
        Output("alerts-summary-panel", "children"),
        Output("alerts-sector-heatmap", "figure"),
        Output("alerts-shift-chart", "figure"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_alerts(selection_data: dict | None, _refresh_data: dict | None):
        selection = _selection(selection_data)
        focus_ticker = selection["focus_ticker"]
        if not selection["analysis_ready"] or not focus_ticker:
            raise PreventUpdate
        start_date, end_date = _resolve_date_window(selection)
        state = build_dashboard_state(
            focus_ticker,
            selection["compare_tickers"],
            selection["horizon"],
            start_date,
            end_date,
        )
        alerts_data = build_alerts(state.compare_df, state.event_df, selection["alert_threshold"])
        bearish = int((state.compare_df["avg_sentiment"] < 0).sum()) if not state.compare_df.empty else 0
        summary = build_summary_list(
            [
                ("Active Alerts", str(len(alerts_data))),
                ("Bearish Tickers", str(bearish)),
                ("Strongest Mover", state.compare_df.sort_values("pct_change", ascending=False)["ticker"].iloc[0] if not state.compare_df.empty else "n/a"),
                ("Latest Shift", state.news_df.sort_values("published_at", ascending=False)["ticker"].iloc[0] if not state.news_df.empty else "n/a"),
            ]
        )
        summary = [
            html.Div(
                "Attention signals are generated from current catalysts, price movement, sentiment changes, and market-relative behavior. They are not notification subscriptions.",
                className="explanation-line simple-only",
            ),
            html.Div(build_buy_readout(focus_ticker, state.compare_df), className="analyst-only"),
            *summary,
        ]
        return (
            build_focus_status_banner(focus_ticker, state),
            build_alert_panel(alerts_data, state.demo_mode),
            summary,
            build_sector_heatmap(state.sector_df)
            if not state.sector_df.empty
            else build_empty_figure("Sector Mood", "Sector-level mood appears when peer data is available."),
            build_sentiment_timeline_with_title(state.news_df, "Recent Sentiment Trend")
            if not state.news_df.empty
            else build_empty_figure("Recent Sentiment Trend", "No recent sentiment series is available in the selected window."),
        )

    return app
