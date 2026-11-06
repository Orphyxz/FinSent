"""Callbacks for the intelligence modules: ticker tape, executive overview, stock
research workbench, news intelligence, explainable signals, compare and the research lab."""

from __future__ import annotations

from functools import lru_cache

from dash import ALL, MATCH, Input, Output, State, ctx, html
import pandas as pd
from dash.exceptions import PreventUpdate

from finsent.app.analysis.technicals import risk_stats, technical_snapshot
from finsent.app.dashboard import charts
from finsent.app.dashboard import intelligence as intel
from finsent.app.dashboard import view_model as vm
from finsent.app.dashboard import widgets as w
from finsent.app.dashboard.selection import resolve_date_window, selection as workspace_selection
from finsent.app.dashboard.view_model import build_dashboard_state, detect_data_mode, format_age_from_timestamp, get_market_filter_for_ticker
from finsent.app.services import market_overview
from finsent.app.services.benchmarks import benchmark_stats, rolling_beta_series
from finsent.app.services.entity_extraction import extract_entities
from finsent.app.services.event_explorer import load_event_explorer
from finsent.app.services.market_map import market_map, sector_breadth
from finsent.app.services.sentiment_explainer import explain_headline
from finsent.app.services.runtime_diagnostics import runtime_diagnostics


def _market(selection_data: dict | None) -> str:
    market = str((selection_data or {}).get("exchange_filter") or "US").upper()
    return "INDIA" if market in {"NSE", "BSE"} else market


def provider_strip() -> list:
    snapshot = runtime_diagnostics.snapshot(app_mode=detect_data_mode())
    market_provider = snapshot.active_market_provider or "—"
    news_provider = snapshot.active_news_provider or "—"
    last_refresh = format_age_from_timestamp(snapshot.last_refresh.completed_at) if snapshot.last_refresh else "—"
    healthy = snapshot.db_health.state == "HEALTHY"
    return [
        html.Span([html.Span(className=f"status-dot status-dot-{'open' if healthy else 'closed'}"), "Live" if healthy else "Limited"], className="provider-chip"),
        html.Span(["Market ", html.B(market_provider)], className="provider-chip"),
        html.Span(["News ", html.B(news_provider)], className="provider-chip"),
        html.Span(["Refreshed ", html.B(last_refresh)], className="provider-chip"),
    ]


MAX_WATCHLIST = 12


def _custom_watchlist(watchlists: dict | None, market: str) -> list[str] | None:
    tickers = (watchlists or {}).get(market)
    return [str(t) for t in tickers][:MAX_WATCHLIST] if tickers else None


def register(app) -> None:
    @app.callback(
        Output("ticker-tape", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
        Input("watchlist-store", "data"),
    )
    def refresh_ticker_tape(selection_data: dict | None, _refresh: dict | None, watchlists: dict | None):
        market = _market(selection_data)
        indices = [item for item in market_overview.index_summaries() if market == "ALL" or item.region == market]
        tickers = _custom_watchlist(watchlists, market) or intel.watchlist_for_market(market)
        return w.ticker_tape([*indices, *market_overview.watchlist_summaries(tickers)])

    @app.callback(
        Output("watchlist-editor", "options"),
        Output("watchlist-editor", "value"),
        Input("selection-store", "data"),
        Input("watchlist-reset", "n_clicks"),
        State("watchlist-store", "data"),
    )
    def load_watchlist_editor(selection_data, _reset, watchlists):
        market = _market(selection_data)
        options = vm.get_ticker_options(market)
        if ctx.triggered_id == "watchlist-reset":
            return options, intel.watchlist_for_market(market)
        return options, _custom_watchlist(watchlists, market) or intel.watchlist_for_market(market)

    @app.callback(
        Output("watchlist-store", "data"),
        Input("watchlist-editor", "value"),
        State("watchlist-store", "data"),
        State("selection-store", "data"),
        prevent_initial_call=True,
    )
    def save_watchlist(tickers, watchlists, selection_data):
        if not tickers:
            raise PreventUpdate
        market = _market(selection_data)
        updated = dict(watchlists or {})
        default = intel.watchlist_for_market(market)
        cleaned = [str(t) for t in tickers][:MAX_WATCHLIST]
        if cleaned == default:
            updated.pop(market, None)
        else:
            updated[market] = cleaned
        if updated == (watchlists or {}):
            raise PreventUpdate
        return updated

    @app.callback(
        Output("exec-provider-strip", "children"),
        Output("exec-mood", "children"),
        Output("exec-indices", "children"),
        Output("exec-watchlist", "children"),
        Output("exec-signal-dist", "children"),
        Output("exec-movers", "children"),
        Output("exec-positive", "children"),
        Output("exec-negative", "children"),
        Output("exec-events", "children"),
        Output("exec-brief", "children"),
        Output("exec-correlation", "figure"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
        Input("watchlist-store", "data"),
    )
    def refresh_executive(selection_data: dict | None, _refresh: dict | None, watchlists: dict | None):
        market = _market(selection_data)
        snapshot = intel.executive_snapshot(market, _custom_watchlist(watchlists, market))
        indices = [w.index_card(item) for item in snapshot.indices] or [html.Div("Index data unavailable right now.", className="empty-inline")]
        return (
            provider_strip(),
            w.mood_card(snapshot.mood_label, snapshot.mood_score, snapshot.articles_analyzed, snapshot.market),
            indices,
            w.watchlist_table(snapshot.rows),
            w.distribution_bars(snapshot.signal_counts),
            w.movers_list(snapshot.rows),
            w.catalyst_list(snapshot.positive_catalysts, empty="No bullish catalysts in stored news yet."),
            w.catalyst_list(snapshot.negative_catalysts, empty="No bearish catalysts in stored news yet."),
            w.catalyst_list(snapshot.todays_events, empty="No high-impact events on the latest news day."),
            w.market_brief(snapshot),
            charts.correlation_heatmap({row.ticker: market_overview.daily_history(row.ticker) for row in snapshot.rows}),
        )

    @app.callback(
        Output("selection-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input({"type": "focus-ticker", "ticker": ALL}, "n_clicks"),
        State("selection-store", "data"),
        prevent_initial_call=True,
    )
    def open_focus_ticker(clicks: list[int | None], selection_data: dict | None):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or not any(clicks or []):
            raise PreventUpdate
        triggered_clicks = next((item["value"] for item in ctx.triggered if item.get("value")), None)
        if not triggered_clicks:
            raise PreventUpdate
        ticker = str(trigger["ticker"])
        selection = dict(selection_data or {})
        selection["focus_ticker"] = ticker
        selection["exchange_filter"] = get_market_filter_for_ticker(ticker)
        selection["compare_tickers"] = [t for t in selection.get("compare_tickers", []) if t != ticker]
        return selection, "/stock-detail"

    # Module-specific callbacks register below as each module lands.
    _register_stock_workbench(app)
    _register_news_intelligence(app)
    _register_compare(app)
    _register_research_lab(app)
    _register_market_map(app)


V2_DIRECTIONAL = (("news", "News sentiment", 0.55), ("price_momentum", "Price momentum", 0.35), ("volume_confirmation", "Volume confirmation", 0.10))
V2_MODIFIERS = (("liquidity", "Liquidity"), ("freshness", "Freshness"), ("data_quality", "Data quality"))


def _workspace_state(selection_data: dict | None):
    selection = workspace_selection(selection_data)
    start_date, end_date = resolve_date_window(selection)
    state = build_dashboard_state(selection["focus_ticker"], selection["compare_tickers"], selection["horizon"], start_date, end_date)
    return selection, state


def _quote_header(ticker: str, history, quote_meta: dict, symbol) -> list:
    currency = symbol.currency if symbol else "USD"
    last = quote_meta.get("current_price") if quote_meta.get("usable_market_data") else None
    closes = history["close"].dropna() if not history.empty else None
    if last is None and closes is not None and not closes.empty:
        last = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if closes is not None and len(closes) >= 2 else None
    change = None if last is None or previous is None else last - previous
    change_pct = None if change is None or not previous else change / previous
    day = history.iloc[-1] if not history.empty else None
    year = history.tail(252)
    low_52, high_52 = (float(year["low"].min()), float(year["high"].max())) if not year.empty else (None, None)
    position = None
    if last is not None and low_52 is not None and high_52 and high_52 > low_52:
        position = max(0.0, min(1.0, (last - low_52) / (high_52 - low_52)))
    chips = [
        symbol.sector if symbol else None,
        f"{symbol.listing_exchange or symbol.exchange}" if symbol else None,
        currency,
        str(quote_meta.get("market_status") or "").title() or None,
    ]
    return [
        html.Div(
            [
                html.Div(w.fmt_price(last, currency), className="quote-price"),
                html.Div(
                    [w.change_chip(change_pct), html.Span("" if change is None else f"{change:+,.2f} today", className=f"tone-{w.tone_of(change)}")],
                    className="quote-change",
                ),
            ],
            className="quote-main",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Span("Day range", className="mini-label"),
                        html.Span("—" if day is None else f"{w.fmt_price(day['low'], currency)} – {w.fmt_price(day['high'], currency)}", className="mini-value"),
                    ],
                    className="mini-stack",
                ),
                html.Div(
                    [
                        html.Span("52-week range", className="mini-label"),
                        html.Div(
                            [
                                html.Span(w.fmt_price(low_52, currency), className="range-end"),
                                html.Div(html.Div(className="range-marker", style={"left": f"{(position or 0) * 100:.0f}%"}), className="range-track"),
                                html.Span(w.fmt_price(high_52, currency), className="range-end"),
                            ],
                            className="range-bar",
                        ),
                    ],
                    className="mini-stack range-stack",
                ),
                html.Div([html.Span(chip, className="meta-chip") for chip in chips if chip], className="meta-chips"),
            ],
            className="quote-side",
        ),
    ]


def _benchmark_tiles(bench) -> list:
    def pct(value):
        return w.fmt_pct(value, digits=1)

    market = bench.market_label.split(" (")[0]
    return [
        w.stat_tile("Beta", "—" if bench.beta is None else f"{bench.beta:.2f}", f"vs {market}, 6 months daily"),
        w.stat_tile("Correlation", "—" if bench.correlation is None else f"{bench.correlation:.2f}", f"Daily returns vs {market}"),
        w.stat_tile("1M excess", pct(bench.excess_1m), f"Return minus {market}", tone=w.tone_of(bench.excess_1m)),
        w.stat_tile("3M excess", pct(bench.excess_3m), f"Return minus {market}", tone=w.tone_of(bench.excess_3m)),
        w.stat_tile("3M vs sector", pct(bench.sector_excess_3m), bench.sector_label or "No sector index", tone=w.tone_of(bench.sector_excess_3m)),
        w.stat_tile("Volatility ratio", "—" if bench.volatility_ratio is None else f"{bench.volatility_ratio:.2f}×", f"Stock vs {market} volatility"),
    ]


def _technical_tiles(snapshot, beta: float | None, market_label: str = "SPY") -> list:
    def pct(value):
        return w.fmt_pct(value, digits=1)

    rsi_tone = "negative" if snapshot.rsi_zone == "Overbought" else "positive" if snapshot.rsi_zone == "Oversold" else "neutral"
    trend_tone = "positive" if snapshot.trend in {"Uptrend", "Above 50-day"} else "negative" if snapshot.trend in {"Downtrend", "Below 50-day"} else "neutral"
    macd_tone = "positive" if snapshot.macd_state.startswith("Bullish") else "negative" if snapshot.macd_state.startswith("Bearish") else "neutral"
    return [
        w.stat_tile("RSI 14", "—" if snapshot.rsi_14 is None else f"{snapshot.rsi_14:.0f}", snapshot.rsi_zone, tone=rsi_tone),
        w.stat_tile("MACD", "—" if snapshot.macd is None else f"{snapshot.macd:+.2f}", snapshot.macd_state, tone=macd_tone),
        w.stat_tile("Trend", snapshot.trend, "Price vs 50/200-day", tone=trend_tone),
        w.stat_tile("Volatility", pct(snapshot.volatility_30d).lstrip("+"), "30-day, annualized"),
        w.stat_tile("1M return", pct(snapshot.return_1m), f"1W {pct(snapshot.return_1w)}", tone=w.tone_of(snapshot.return_1m)),
        w.stat_tile("1Y return", pct(snapshot.return_1y), f"3M {pct(snapshot.return_3m)}", tone=w.tone_of(snapshot.return_1y)),
        w.stat_tile("Beta", "—" if beta is None else f"{beta:.2f}", f"vs {market_label.split(' (')[0]}, daily"),
        w.stat_tile("Avg volume", "—" if snapshot.avg_volume_20d is None else f"{snapshot.avg_volume_20d / 1e6:,.2f}M", "20-day"),
    ]


def _signal_card(engine: str, label: str | None, score: float | None, confidence: float | None, formula: str) -> html.Div:
    confidence_pct = None if confidence is None else max(0.0, min(1.0, float(confidence)))
    return html.Div(
        [
            html.Div([html.Span(engine, className="engine-name"), w.signal_pill((label or "No signal").replace("_", " ").title())], className="engine-head"),
            html.Div("—" if score is None else f"{float(score):+.3f}", className=f"engine-score tone-{w.tone_of(score, threshold=0.02)}"),
            html.Div(
                [
                    html.Span("Confidence", className="mini-label"),
                    html.Div(html.Div(className="conf-fill", style={"width": f"{(confidence_pct or 0) * 100:.0f}%"}), className="conf-track"),
                    html.Span("—" if confidence_pct is None else f"{confidence_pct * 100:.0f}%", className="mini-value"),
                ],
                className="conf-row",
            ),
            html.Div(formula, className="engine-formula"),
        ],
        className="engine-card",
    )


def _weights_table(components: list[dict], v2: dict) -> html.Div:
    by_name = {str(c.get("name")): c for c in components}
    rows = [html.Div([html.Span("Component"), html.Span("Weight"), html.Span("Value"), html.Span("Contribution"), html.Span("Reliability")], className="weight-row weight-head")]
    total = 0.0
    for key, label, weight in V2_DIRECTIONAL:
        component = by_name.get(key, {})
        value = component.get("normalized_value")
        contribution = component.get("contribution")
        total += float(contribution or 0.0)
        rows.append(
            html.Div(
                [
                    html.Span(label),
                    html.Span(f"{weight:.0%}", className="weight-chip"),
                    html.Span("—" if value is None else f"{float(value):+.2f}"),
                    html.Span("—" if contribution is None else f"{float(contribution):+.3f}", className=f"tone-{w.tone_of(contribution, threshold=0.0005)}"),
                    html.Span("—" if component.get("reliability") is None else f"{float(component['reliability']):.0%}"),
                ],
                className="weight-row",
            )
        )
    final = v2.get("score")
    rows.append(
        html.Div(
            [
                html.Span("Weighted sum"),
                html.Span(""),
                html.Span(""),
                html.Span(f"{total:+.3f}"),
                html.Span(""),
            ],
            className="weight-row weight-total",
        )
    )
    modifiers = [
        html.Li([html.B(label), " ", str(by_name.get(key, {}).get("reason") or "Not reported.")])
        for key, label in V2_MODIFIERS
    ]
    return html.Div(
        [
            html.Div(rows, className="weight-table"),
            html.Div(
                [
                    html.Span("Final V2 score ", className="mini-label"),
                    html.B("—" if final is None else f"{float(final):+.3f}"),
                    html.Span(" after reliability and data-quality attenuation. Directional at |score| ≥ 0.20, strong at ≥ 0.55.", className="weight-note"),
                ],
                className="weight-final",
            ),
            html.Ul(modifiers, className="modifier-list"),
        ]
    )


def _register_stock_workbench(app) -> None:
    @app.callback(
        Output("stock-main-chart", "figure"),
        Input("stock-period", "value"),
        Input("stock-chart-style", "value"),
        Input("stock-overlays", "value"),
        Input("stock-panels", "value"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
        Input("display-mode-store", "data"),
    )
    def refresh_price_chart(period, style, overlays, panels, selection_data, _refresh, mode):
        # Reads only cached bars, so toggling an indicator redraws immediately.
        if mode != "analyst":  # Simple view is a clean price line; indicators are Analyst-only.
            style, overlays, panels = "line", [], []
        ticker = workspace_selection(selection_data)["focus_ticker"]
        symbol = market_overview.resolve_symbol(ticker)
        currency = w.currency_symbol(symbol.currency if symbol else "USD")
        if period == "1D":
            return charts.intraday_chart(intel.stored_intraday(ticker), currency_symbol=currency, revision=f"{ticker}-1d")
        return charts.price_chart(
            market_overview.daily_history(ticker), period=period or "3M", style=style or "candle",
            overlays=overlays or [], panels=panels or [], currency_symbol=currency, revision=f"{ticker}-{period}",
        )

    @app.callback(
        Output("stock-quote-header", "children"),
        Output("stock-technicals", "children"),
        Output("stock-benchmark-title", "children"),
        Output("stock-benchmark-chart", "figure"),
        Output("stock-benchmark-stats", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_quote_and_technicals(selection_data, _refresh):
        selection, state = _workspace_state(selection_data)
        ticker = selection["focus_ticker"]
        symbol = market_overview.resolve_symbol(ticker)
        history = market_overview.daily_history(ticker)
        bench = benchmark_stats(ticker)
        title = f"{ticker} vs {bench.market_label}" + (f" and {bench.sector_label}" if bench.sector_label else "")
        return (
            _quote_header(ticker, history, state.quote_meta_map.get(ticker, {}), symbol),
            _technical_tiles(technical_snapshot(history), bench.beta, bench.market_label),
            title,
            charts.normalized_performance(bench.series, height=320),
            _benchmark_tiles(bench),
        )

    @app.callback(
        Output("stock-signal-compare", "children"),
        Output("stock-contrib-chart", "figure"),
        Output("stock-signal-weights", "children"),
        Output("stock-sentiment-history", "figure"),
        Output("stock-verdict", "children"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_signal_explainer(selection_data, _refresh):
        selection, state = _workspace_state(selection_data)
        ticker = selection["focus_ticker"]
        meta = state.signal_meta_map.get(ticker, {})
        v2 = meta.get("live_v2") or {}
        components = meta.get("live_v2_components") or []
        v1_label = meta.get("composite_label")
        v2_label = v2.get("label")
        agree = (v1_label or "").lower() == (v2_label or "").lower() and v1_label is not None
        cards = [
            _signal_card("Signal V1", v1_label, meta.get("composite_score"), meta.get("signal_confidence"), "0.75 × news sentiment + 0.25 × market quality − spread and staleness penalties. Directional at |score| > 0.18."),
            _signal_card("Signal V2", v2_label, v2.get("score"), v2.get("confidence"), "55% news + 35% momentum + 10% volume, attenuated by liquidity, freshness and data quality."),
            html.Div(
                [html.Span(className=f"status-dot status-dot-{'open' if agree else 'closed'}"), "Engines agree" if agree else "Engines disagree: read the components"],
                className="agreement-chip",
            ),
        ]
        news = intel.stored_news(ticker)
        directional = [c for c in components if c.get("name") in {key for key, _, _ in V2_DIRECTIONAL}]
        verdict = w.stock_verdict(
            ticker,
            vm.get_company_name(ticker),
            v1_label,
            {str(c.get("name")): c.get("normalized_value") for c in components},
            technical_snapshot(market_overview.daily_history(ticker)).return_1m,
        )
        return cards, charts.contribution_chart(directional, height=200), _weights_table(components, v2), charts.sentiment_history(news), verdict

    @app.callback(
        Output("stock-risk-stats", "children"),
        Output("stock-rolling-beta", "figure"),
        Output("stock-return-dist", "figure"),
        Input("selection-store", "data"),
    )
    def refresh_risk_profile(selection_data):
        ticker = workspace_selection(selection_data)["focus_ticker"]
        history = market_overview.daily_history(ticker)
        dates, beta, label = rolling_beta_series(ticker)
        return w.risk_tiles(risk_stats(history)), charts.rolling_beta_chart(beta, dates, label.split(" (")[0]), charts.return_histogram(history)


SENTIMENT_GROUPS = {
    "positive": {"bullish", "positive"},
    "neutral": {"neutral", "mixed"},
    "negative": {"bearish", "negative"},
}


@lru_cache(maxsize=4096)
def _entities_for(text: str):
    return extract_entities(text)


def _register_news_intelligence(app) -> None:
    @app.callback(
        Output({"type": "explain-out", "index": MATCH}, "children"),
        Output({"type": "explain-btn", "index": MATCH}, "children"),
        Input({"type": "explain-btn", "index": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    def explain_article(clicks):
        if not clicks or not isinstance(ctx.triggered_id, dict):
            raise PreventUpdate
        if clicks % 2 == 0:
            return None, "Explain sentiment"
        text = w.headline_for_key(str(ctx.triggered_id.get("index")))
        if not text:
            return html.Div("This article is no longer in the feed; refresh the page.", className="empty-inline"), "Explain sentiment"
        return w.sentiment_explanation(explain_headline(text)), "Hide explanation"

    @app.callback(
        Output("news-intel-summary", "children"),
        Output("news-feed", "children"),
        Output("news-donut", "figure"),
        Output("news-donut-legend", "children"),
        Output("news-catalyst-breakdown", "children"),
        Output("news-brief", "children"),
        Input("news-symbol-filter", "value"),
        Input("news-catalyst-filter", "value"),
        Input("news-direction-filter", "value"),
        Input("news-sentiment-filter", "value"),
        Input("selection-store", "data"),
    )
    def refresh_news_feed(symbols, catalysts, directions, sentiment, selection_data):
        # Not tied to the 15-second refresh tick: rebuilding the cards would close any open
        # explanation. The feed updates when the selection or filters change.
        selection = workspace_selection(selection_data)
        tickers = symbols or [selection["focus_ticker"]]
        frames = [intel.stored_news(ticker) for ticker in tickers]
        news = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
        if news.empty:
            empty = html.Div("No analyzed articles are stored for this selection yet. They appear after the next live refresh.", className="empty-inline")
            return w.news_summary_band(", ".join(tickers), 0, {}, "No data"), empty, charts.empty_figure("No articles yet.", height=220), [], w.breakdown_bars({}), []
        news = vm.enrich_news_with_catalysts(news, vm.build_catalyst_frame(news))
        if catalysts:
            news = news[news["catalyst_type"].isin(catalysts)]
        if directions:
            news = news[news["catalyst_direction"].isin(directions)]
        labels = news["sentiment_label"].astype(str).str.lower()
        counts = {name.title(): int(labels.isin(group).sum()) for name, group in SENTIMENT_GROUPS.items()}
        scores = pd.to_numeric(news["sentiment_score"], errors="coerce").dropna()
        bias = intel.mood_from_score(None if scores.empty else float(scores.mean()))
        if sentiment and sentiment != "all":
            news = news[labels.isin(SENTIMENT_GROUPS[sentiment])]
        news = news.sort_values("published_at", ascending=False).drop_duplicates("title").head(30)
        cards = [w.news_card(row, _entities_for(f"{row.get('title') or ''}. {row.get('summary') or ''}")) for _, row in news.iterrows()]
        total = sum(counts.values())
        donut = charts.donut(
            ["Positive", "Neutral", "Negative"],
            [counts["Positive"], counts["Neutral"], counts["Negative"]],
            [charts.COLORS["bull"], charts.COLORS["neutral"], charts.COLORS["bear"]],
            center=f"{counts['Positive'] / total:.0%}<br><span style='font-size:11px;color:#7d888e'>positive</span>" if total else "",
        )
        legend = [
            html.Div(
                [html.I(className=f"dot dist-{key}"), html.Span(label), html.Span(f"{counts[label]}", className="legend-count"), html.Span(f"{counts[label] / total:.0%}" if total else "—", className="legend-pct")],
                className="legend-row",
            )
            for key, label in (("bullish", "Positive"), ("neutral", "Neutral"), ("bearish", "Negative"))
        ]
        catalyst_counts = (
            news["catalyst_type"].dropna().astype(str).map(lambda value: w._catalyst_label(value)).value_counts().to_dict()
            if "catalyst_type" in news.columns else {}
        )
        catalyst_counts.pop("Other", None)
        feed = cards or [html.Div("No articles match these filters.", className="empty-inline")]
        return w.news_summary_band(", ".join(tickers), total, counts, bias), feed, donut, legend, w.breakdown_bars(catalyst_counts), w.news_brief(", ".join(tickers), total, counts, bias)


def _register_compare(app) -> None:
    @app.callback(
        Output("compare-cards", "children"),
        Output("compare-perf-chart", "figure"),
        Output("compare-sentiment-chart", "figure"),
        Output("compare-catalyst-chart", "figure"),
        Output("compare-volatility-chart", "figure"),
        Output("compare-signal-table", "children"),
        Output("compare-correlation", "figure"),
        Input("compare-period", "value"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_compare_intel(period, selection_data, _refresh):
        selection = workspace_selection(selection_data)
        tickers = [selection["focus_ticker"], *selection["compare_tickers"]]
        profiles = intel.compare_profiles(tickers, period_days=int(period or 90))
        if len(profiles) < 2:
            raise PreventUpdate
        colors = charts.SERIES_COLORS
        cards = [w.compare_card(profile, colors[index % len(colors)]) for index, profile in enumerate(profiles)]
        names = [profile.ticker for profile in profiles]
        performance = charts.normalized_performance({profile.ticker: profile.history for profile in profiles})
        sentiment = charts.grouped_bars(
            names,
            {label: [profile.sentiment_mix.get(label, 0) for profile in profiles] for label in ("Positive", "Neutral", "Negative")},
            stacked=True,
            height=300,
        )
        catalyst_types = sorted({key for profile in profiles for key in profile.catalyst_mix if key != "Other"})
        catalysts = (
            charts.grouped_bars(names, {key: [profile.catalyst_mix.get(key, 0) for profile in profiles] for key in catalyst_types}, stacked=True, height=300)
            if catalyst_types else charts.empty_figure("No classified catalysts for these stocks yet.", height=300)
        )
        volatility = charts.grouped_bars(names, {"Annualized volatility": [profile.volatility or 0.0 for profile in profiles]}, percent=True, height=280)
        correlation = charts.correlation_heatmap({profile.ticker: profile.history for profile in profiles}, height=300)
        return cards, performance, sentiment, catalysts, volatility, w.signal_matrix(profiles), correlation


def _hit_rate(events: pd.DataFrame, direction_column: str, window: str) -> tuple[float | None, int]:
    directional = events[events[direction_column].isin(["BULLISH", "BEARISH"])].dropna(subset=[f"ar_{window}"])
    if directional.empty:
        return None, 0
    expected = directional[direction_column].map({"BULLISH": 1, "BEARISH": -1})
    hits = (directional[f"ar_{window}"].apply(lambda v: 1 if v > 0 else -1) == expected).sum()
    return float(hits / len(directional)), len(directional)


def _register_research_lab(app) -> None:
    @app.callback(
        Output("research-event-stats", "children"),
        Output("research-event-chart", "figure"),
        Output("research-event-scatter", "figure"),
        Output("research-event-table", "data"),
        Output("research-event-table", "columns"),
        Input("research-window", "value"),
    )
    def refresh_event_lab(window):
        window = window or "1D"
        result = load_event_explorer()
        if not result.available:
            message = result.message or "Event explorer unavailable."
            return [html.Div(message, className="empty-inline")], charts.empty_figure(message), charts.empty_figure(message), [], []
        events = result.events
        ar = pd.to_numeric(events[f"ar_{window}"], errors="coerce")
        v1_hit, v1_n = _hit_rate(events, "v1_direction", window)
        v2_hit, v2_n = _hit_rate(events, "v2_direction", window)
        correlation = events["finbert_score"].corr(ar)
        bullish = ar[events["v1_direction"] == "BULLISH"].mean()
        bearish = ar[events["v1_direction"] == "BEARISH"].mean()
        stats = [
            w.stat_tile("Events", f"{ar.notna().sum()}", f"{window} window, valid prices"),
            w.stat_tile("Mean AR", w.fmt_pct(ar.mean()), "All articles vs SPY", tone=w.tone_of(ar.mean())),
            w.stat_tile("After V1 bullish", w.fmt_pct(bullish), "Mean abnormal return", tone=w.tone_of(bullish)),
            w.stat_tile("After V1 bearish", w.fmt_pct(bearish), "Expected below zero", tone=w.tone_of(bearish)),
            w.stat_tile("V1 hit rate", "—" if v1_hit is None else f"{v1_hit:.0%}", f"Sign of AR, {v1_n} directional calls"),
            w.stat_tile("V2 hit rate", "—" if v2_hit is None else f"{v2_hit:.0%}", f"Sign of AR, {v2_n} directional calls"),
            w.stat_tile("FinBERT ↔ AR", "—" if pd.isna(correlation) else f"{correlation:+.2f}", "Pearson correlation"),
        ]
        table = events.assign(
            Date=events["published_at"].dt.strftime("%Y-%m-%d"),
            Return=(pd.to_numeric(events[f"ret_{window}"], errors="coerce") * 100).round(2),
            AR=(ar * 100).round(2),
            Hit=[
                "—" if d not in {"BULLISH", "BEARISH"} or pd.isna(v) else ("Yes" if (v > 0) == (d == "BULLISH") else "No")
                for d, v in zip(events["v1_direction"], ar, strict=False)
            ],
        )[["Date", "ticker", "finbert_label", "v1_direction", "v2_direction", "realized", "Return", "AR", "Hit"]].rename(
            columns={"ticker": "Ticker", "finbert_label": "FinBERT", "v1_direction": "V1", "v2_direction": "V2", "realized": "Realized 1D"}
        )
        columns = [
            {"name": name if name not in {"Return", "AR"} else f"{window} {name} %", "id": name, "type": "numeric" if name in {"Return", "AR"} else "text"}
            for name in table.columns
        ]
        scatter = charts.score_scatter(events.assign(ar=ar), "finbert_score", "ar", "v1_direction")
        return stats, charts.event_reaction_chart(result.summary), scatter, table.to_dict("records"), columns


def _register_market_map(app) -> None:
    @app.callback(
        Output("market-treemap", "figure"),
        Output("map-breadth-strip", "children"),
        Output("map-gainers", "children"),
        Output("map-losers", "children"),
        Output("map-sector-breadth", "children"),
        Input("map-size", "value"),
        Input("selection-store", "data"),
        Input("live-refresh-store", "data"),
    )
    def refresh_market_map(size_by, selection_data, _refresh):
        frame = market_map(_market(selection_data))
        return (
            charts.market_treemap(frame, size_by=size_by or "equal"),
            w.breadth_strip(frame),
            w.price_movers(frame, ascending=False),
            w.price_movers(frame, ascending=True),
            w.sector_breadth_rows(sector_breadth(frame)),
        )
