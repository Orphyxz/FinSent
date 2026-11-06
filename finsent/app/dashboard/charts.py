"""Plotly figures and lightweight SVG sparklines for the intelligence dashboard."""

from __future__ import annotations

from urllib.parse import quote

import numpy as np
import pandas as pd
from plotly import graph_objects as go
from plotly.subplots import make_subplots

from finsent.app.analysis.technicals import bollinger, ema, macd, normalize_ohlcv, rsi, sma


COLORS = {
    "paper": "#101315",
    "ink": "#eef2f3",
    "muted": "#7d888e",
    "grid": "rgba(255,255,255,0.06)",
    "bull": "#22c55e",
    "bear": "#ef4444",
    "neutral": "#94a3b8",
    "accent": "#22c55e",
    "blue": "#60a5fa",
    "violet": "#a78bfa",
    "amber": "#f59e0b",
    "cyan": "#22d3ee",
    "pink": "#f472b6",
}
SERIES_COLORS = [COLORS["blue"], COLORS["bull"], COLORS["amber"], COLORS["pink"], COLORS["violet"], COLORS["cyan"]]
SENTIMENT_COLORS = {"Positive": COLORS["bull"], "Neutral": COLORS["neutral"], "Negative": COLORS["bear"]}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Arial, sans-serif"

PERIOD_BARS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}


def themed(fig: go.Figure, *, height: int | None = None, revision: str = "finsent", legend: bool = False) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=COLORS["paper"],
        plot_bgcolor=COLORS["paper"],
        font={"family": FONT, "color": COLORS["ink"], "size": 12},
        margin={"l": 48, "r": 16, "t": 16, "b": 32},
        hoverlabel={"bgcolor": "#1a1f22", "bordercolor": "#2a3034", "font": {"family": FONT, "color": COLORS["ink"]}},
        showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "bgcolor": "rgba(0,0,0,0)", "font": {"color": COLORS["muted"]}},
        uirevision=revision,
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], zeroline=False, showline=False, tickfont={"color": COLORS["muted"]})
    fig.update_yaxes(gridcolor=COLORS["grid"], zeroline=False, showline=False, tickfont={"color": COLORS["muted"]})
    if height:
        fig.update_layout(height=height)
    return fig


def empty_figure(message: str, *, height: int = 280) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font={"color": COLORS["muted"], "size": 13}, xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return themed(fig, height=height)


def sparkline_svg(values: tuple[float, ...] | list[float], *, width: int = 120, height: int = 36, color: str | None = None) -> str:
    """A data-URI SVG sparkline: far cheaper than a Plotly graph per card."""
    points = [float(v) for v in values if v is not None and np.isfinite(v)]
    if len(points) < 2:
        return ""
    low, high = min(points), max(points)
    span = (high - low) or 1.0
    step = width / (len(points) - 1)
    coords = [(i * step, height - 3 - (value - low) / span * (height - 6)) for i, value in enumerate(points)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    stroke = color or (COLORS["bull"] if points[-1] >= points[0] else COLORS["bear"])
    area = f"0,{height} " + line + f" {width},{height}"
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{stroke}' stop-opacity='0.28'/>"
        f"<stop offset='1' stop-color='{stroke}' stop-opacity='0'/></linearGradient></defs>"
        f"<polygon points='{area}' fill='url(#g)'/>"
        f"<polyline points='{line}' fill='none' stroke='{stroke}' stroke-width='1.6' stroke-linejoin='round' stroke-linecap='round'/></svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg)


def price_chart(
    bars: pd.DataFrame,
    *,
    period: str = "3M",
    style: str = "candle",
    overlays: list[str] | None = None,
    panels: list[str] | None = None,
    currency_symbol: str = "$",
    revision: str = "price",
) -> go.Figure:
    """Price with optional SMA/EMA/Bollinger overlays and volume, RSI and MACD panels.

    Indicators are computed on the full history and then trimmed to the period, so the
    first visible bars already have warmed-up values.
    """
    data = normalize_ohlcv(bars)
    if data.empty:
        return empty_figure("No price history available for this instrument yet.", height=460)
    overlays = overlays or []
    panels = panels if panels is not None else ["volume"]
    close = data["close"]
    indicators = pd.DataFrame({"timestamp": data["timestamp"]})
    indicators["sma20"], indicators["sma50"], indicators["sma200"] = sma(close, 20), sma(close, 50), sma(close, 200)
    indicators["ema20"] = ema(close, 20)
    bands = bollinger(close)
    indicators[["bb_mid", "bb_up", "bb_low"]] = bands[["middle", "upper", "lower"]].to_numpy()
    indicators["rsi"] = rsi(close)
    macd_frame = macd(close)
    indicators[["macd", "macd_signal", "macd_hist"]] = macd_frame.to_numpy()

    bars_to_show = PERIOD_BARS.get(period, len(data))
    view = data.tail(bars_to_show)
    ind = indicators.loc[view.index]

    rows = 1 + len(panels)
    heights = [0.62] + [round(0.38 / len(panels), 3)] * len(panels) if panels else [1.0]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.035, row_heights=heights)
    x = view["timestamp"]

    if style == "line":
        fig.add_trace(go.Scatter(x=x, y=view["close"], mode="lines", name="Close", line={"color": COLORS["blue"], "width": 2}, fill="tozeroy", fillcolor="rgba(96,165,250,0.08)"), row=1, col=1)
        fig.update_yaxes(range=[view["low"].min() * 0.985, view["high"].max() * 1.015], row=1, col=1)
    else:
        fig.add_trace(
            go.Candlestick(
                x=x, open=view["open"], high=view["high"], low=view["low"], close=view["close"], name="OHLC", showlegend=False,
                increasing={"line": {"color": COLORS["bull"], "width": 1}, "fillcolor": COLORS["bull"]},
                decreasing={"line": {"color": COLORS["bear"], "width": 1}, "fillcolor": COLORS["bear"]},
            ),
            row=1, col=1,
        )

    overlay_specs = {
        "sma20": ("SMA 20", COLORS["amber"]),
        "sma50": ("SMA 50", COLORS["violet"]),
        "sma200": ("SMA 200", COLORS["pink"]),
        "ema20": ("EMA 20", COLORS["cyan"]),
    }
    for key in overlays:
        if key in overlay_specs and ind[key].notna().any():
            label, color = overlay_specs[key]
            fig.add_trace(go.Scatter(x=x, y=ind[key], mode="lines", name=label, line={"color": color, "width": 1.4}), row=1, col=1)
    if "bollinger" in overlays and ind["bb_up"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=ind["bb_up"], mode="lines", name="Bollinger", line={"color": "rgba(148,163,184,0.5)", "width": 1}), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=ind["bb_low"], mode="lines", name="Bollinger low", line={"color": "rgba(148,163,184,0.5)", "width": 1}, fill="tonexty", fillcolor="rgba(148,163,184,0.06)", showlegend=False), row=1, col=1)

    row = 2
    for panel in panels:
        if panel == "volume":
            colors = np.where(view["close"] >= view["open"], "rgba(34,197,94,0.55)", "rgba(239,68,68,0.55)")
            fig.add_trace(go.Bar(x=x, y=view["volume"], name="Volume", showlegend=False, marker={"color": colors, "line": {"width": 0}}), row=row, col=1)
            fig.update_yaxes(title_text="Vol", title_font={"size": 10, "color": COLORS["muted"]}, row=row, col=1)
        elif panel == "rsi":
            fig.add_trace(go.Scatter(x=x, y=ind["rsi"], mode="lines", name="RSI 14", showlegend=False, line={"color": COLORS["violet"], "width": 1.5}), row=row, col=1)
            for level, color in ((70, COLORS["bear"]), (30, COLORS["bull"])):
                fig.add_hline(y=level, line={"color": color, "width": 1, "dash": "dot"}, opacity=0.6, row=row, col=1)
            fig.update_yaxes(range=[0, 100], tickvals=[30, 70], title_text="RSI", title_font={"size": 10, "color": COLORS["muted"]}, row=row, col=1)
        elif panel == "macd":
            hist_colors = np.where(ind["macd_hist"].fillna(0) >= 0, "rgba(34,197,94,0.6)", "rgba(239,68,68,0.6)")
            fig.add_trace(go.Bar(x=x, y=ind["macd_hist"], name="MACD hist", showlegend=False, marker={"color": hist_colors, "line": {"width": 0}}), row=row, col=1)
            fig.add_trace(go.Scatter(x=x, y=ind["macd"], mode="lines", name="MACD", showlegend=False, line={"color": COLORS["blue"], "width": 1.4}), row=row, col=1)
            fig.add_trace(go.Scatter(x=x, y=ind["macd_signal"], mode="lines", name="Signal", showlegend=False, line={"color": COLORS["amber"], "width": 1.2}), row=row, col=1)
            fig.update_yaxes(title_text="MACD", title_font={"size": 10, "color": COLORS["muted"]}, row=row, col=1)
        row += 1

    fig.update_xaxes(rangeslider_visible=False, rangebreaks=[{"bounds": ["sat", "mon"]}])
    fig.update_yaxes(tickprefix=currency_symbol, row=1, col=1)
    themed(fig, height=340 + 110 * len(panels), revision=revision, legend=bool(overlays))
    fig.update_layout(margin={"l": 56, "r": 16, "t": 24, "b": 28})
    return fig


def intraday_chart(price_df: pd.DataFrame, *, currency_symbol: str = "$", revision: str = "intraday") -> go.Figure:
    data = normalize_ohlcv(price_df)
    if data.empty:
        return empty_figure("No intraday bars stored for this session yet.", height=400)
    last_day = data["timestamp"].dt.date.max()
    day = data[data["timestamp"].dt.date == last_day]
    if len(day) < 2:
        day = data.tail(40)
    color = COLORS["bull"] if day["close"].iloc[-1] >= day["close"].iloc[0] else COLORS["bear"]
    fill = "rgba(34,197,94,0.10)" if color == COLORS["bull"] else "rgba(239,68,68,0.10)"
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.75, 0.25])
    fig.add_trace(go.Scatter(x=day["timestamp"], y=day["close"], mode="lines", name="Price", line={"color": color, "width": 2}, fill="tozeroy", fillcolor=fill), row=1, col=1)
    fig.add_trace(go.Bar(x=day["timestamp"], y=day["volume"], name="Volume", marker={"color": "rgba(148,163,184,0.45)"}), row=2, col=1)
    fig.update_yaxes(range=[day["low"].min() * 0.997, day["high"].max() * 1.003], tickprefix=currency_symbol, row=1, col=1)
    return themed(fig, height=420, revision=revision)


def donut(labels: list[str], values: list[float], colors: list[str], *, center: str = "", height: int = 220) -> go.Figure:
    if not any(values):
        return empty_figure("No data in this window.", height=height)
    fig = go.Figure(
        go.Pie(
            labels=labels, values=values, hole=0.68, sort=False, direction="clockwise",
            marker={"colors": colors, "line": {"color": COLORS["paper"], "width": 3}},
            textinfo="none", hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    fig.add_annotation(text=center, showarrow=False, font={"size": 18, "color": COLORS["ink"]})
    themed(fig, height=height)
    fig.update_layout(margin={"l": 8, "r": 8, "t": 8, "b": 8}, hovermode="closest")
    return fig


def contribution_chart(components: list[dict[str, object]], *, height: int = 240) -> go.Figure:
    """Horizontal diverging bars: each component's signed contribution to the final score."""
    rows = [c for c in components if c.get("contribution") is not None]
    if not rows:
        return empty_figure("No component breakdown stored for this signal yet.", height=height)
    names = [str(c["name"]).replace("_", " ").title() for c in rows]
    values = [float(c["contribution"]) for c in rows]
    colors = [COLORS["bull"] if v > 0.0005 else COLORS["bear"] if v < -0.0005 else COLORS["neutral"] for v in values]
    fig = go.Figure(
        go.Bar(
            x=values, y=names, orientation="h", marker={"color": colors, "line": {"width": 0}},
            text=[f"{v:+.3f}" for v in values], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}: %{x:+.3f}<extra></extra>",
        )
    )
    limit = max(0.05, max(abs(v) for v in values) * 1.35)
    fig.add_vline(x=0, line={"color": COLORS["muted"], "width": 1})
    fig.update_xaxes(range=[-limit, limit], zeroline=False)
    fig.update_yaxes(autorange="reversed")
    themed(fig, height=height)
    fig.update_layout(margin={"l": 110, "r": 40, "t": 8, "b": 28}, hovermode="closest")
    return fig


def normalized_performance(series: dict[str, pd.DataFrame], *, height: int = 360) -> go.Figure:
    fig = go.Figure()
    for index, (ticker, frame) in enumerate(series.items()):
        data = normalize_ohlcv(frame)
        if len(data) < 2:
            continue
        base = float(data["close"].iloc[0])
        fig.add_trace(
            go.Scatter(
                x=data["timestamp"], y=data["close"] / base * 100.0, mode="lines", name=ticker,
                line={"color": SERIES_COLORS[index % len(SERIES_COLORS)], "width": 2},
                hovertemplate=f"{ticker}: %{{y:.1f}}<extra></extra>",
            )
        )
    if not fig.data:
        return empty_figure("Not enough daily history to compare.", height=height)
    fig.add_hline(y=100, line={"color": COLORS["muted"], "width": 1, "dash": "dot"})
    fig.update_yaxes(title_text="Indexed (start = 100)", title_font={"size": 11, "color": COLORS["muted"]})
    fig.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])
    return themed(fig, height=height, legend=True, revision="compare")


def grouped_bars(categories: list[str], groups: dict[str, list[float]], *, height: int = 300, percent: bool = False, stacked: bool = False) -> go.Figure:
    fig = go.Figure()
    for index, (name, values) in enumerate(groups.items()):
        color = SENTIMENT_COLORS.get(name) or SERIES_COLORS[index % len(SERIES_COLORS)]
        fig.add_trace(
            go.Bar(
                x=categories, y=values, name=name, marker={"color": color, "line": {"width": 0}},
                hovertemplate=f"{name}: %{{y:{'.1%' if percent else '.2f'}}}<extra></extra>",
            )
        )
    if not fig.data:
        return empty_figure("No data.", height=height)
    fig.update_layout(barmode="stack" if stacked else "group", bargap=0.28, bargroupgap=0.08)
    if percent:
        fig.update_yaxes(tickformat=".0%")
    themed(fig, height=height, legend=len(groups) > 1)
    fig.update_layout(hovermode="x unified")
    return fig


def event_reaction_chart(summary: pd.DataFrame, *, height: int = 320) -> go.Figure:
    """Mean abnormal return by event window for each predicted direction, with 95% CI whiskers."""
    if summary.empty:
        return empty_figure("Event windows could not be computed from available prices.", height=height)
    fig = go.Figure()
    palette = {"BULLISH": COLORS["bull"], "BEARISH": COLORS["bear"], "NEUTRAL": COLORS["neutral"]}
    for label, group in summary.groupby("group", sort=False):
        fig.add_trace(
            go.Scatter(
                x=group["window"], y=group["mean"], mode="lines+markers", name=f"{label.title()} (n={int(group['n'].max())})",
                line={"color": palette.get(label, COLORS["blue"]), "width": 2}, marker={"size": 8},
                error_y={"type": "data", "array": group["ci"], "visible": True, "thickness": 1, "width": 4, "color": palette.get(label, COLORS["blue"])},
                hovertemplate="%{x}: %{y:+.2%}<extra>" + label.title() + "</extra>",
            )
        )
    fig.add_hline(y=0, line={"color": COLORS["muted"], "width": 1, "dash": "dot"})
    fig.update_yaxes(tickformat="+.1%", title_text="Mean abnormal return vs SPY", title_font={"size": 11, "color": COLORS["muted"]})
    return themed(fig, height=height, legend=True, revision="events")


def sentiment_history(news_df: pd.DataFrame, *, height: int = 300) -> go.Figure:
    """Daily mean FinBERT sentiment (bars) with article count (line, right axis)."""
    if news_df is None or news_df.empty:
        return empty_figure("No analyzed headlines stored for this instrument yet.", height=height)
    work = news_df.copy()
    work["day"] = pd.to_datetime(work["published_at"], errors="coerce").dt.normalize()
    work["score"] = pd.to_numeric(work["sentiment_score"], errors="coerce")
    daily = work.dropna(subset=["day"]).groupby("day").agg(sentiment=("score", "mean"), articles=("score", "size")).reset_index()
    if daily.empty:
        return empty_figure("No dated headlines to chart.", height=height)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    colors = np.where(daily["sentiment"].fillna(0) >= 0, "rgba(34,197,94,0.75)", "rgba(239,68,68,0.75)")
    fig.add_trace(go.Bar(x=daily["day"], y=daily["sentiment"], name="Mean sentiment", marker={"color": colors, "line": {"width": 0}}, hovertemplate="%{x|%d %b}: %{y:+.2f}<extra>Sentiment</extra>"), secondary_y=False)
    fig.add_trace(go.Scatter(x=daily["day"], y=daily["articles"], name="Articles", mode="lines+markers", line={"color": COLORS["blue"], "width": 1.6}, marker={"size": 5}, hovertemplate="%{y} articles<extra></extra>"), secondary_y=True)
    fig.update_yaxes(range=[-1, 1], title_text="Sentiment", title_font={"size": 11, "color": COLORS["muted"]}, secondary_y=False)
    fig.update_yaxes(title_text="Articles", title_font={"size": 11, "color": COLORS["muted"]}, showgrid=False, rangemode="tozero", secondary_y=True)
    return themed(fig, height=height, legend=True, revision="sentiment")


def score_scatter(frame: pd.DataFrame, x: str, y: str, color_by: str, *, height: int = 320) -> go.Figure:
    data = frame.dropna(subset=[x, y])
    if data.empty:
        return empty_figure("No events with both values.", height=height)
    palette = {"BULLISH": COLORS["bull"], "BEARISH": COLORS["bear"], "NEUTRAL": COLORS["neutral"]}
    fig = go.Figure()
    for label, group in data.groupby(color_by):
        fig.add_trace(
            go.Scatter(
                x=group[x], y=group[y], mode="markers", name=f"V1 {str(label).title()}",
                marker={"color": palette.get(str(label), COLORS["blue"]), "size": 8, "opacity": 0.8, "line": {"width": 0}},
                customdata=group[["ticker", "published_at"]].astype(str).to_numpy(),
                hovertemplate="%{customdata[0]} %{customdata[1]}<br>FinBERT %{x:+.2f}<br>AR %{y:+.2%}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line={"color": COLORS["muted"], "width": 1, "dash": "dot"})
    fig.add_vline(x=0, line={"color": COLORS["muted"], "width": 1, "dash": "dot"})
    fig.update_yaxes(tickformat="+.0%")
    fig.update_xaxes(title_text="FinBERT score", title_font={"size": 11, "color": COLORS["muted"]})
    themed(fig, height=height, legend=True, revision="scatter")
    fig.update_layout(hovermode="closest")
    return fig


MAP_COLORSCALE = [
    [0.0, "#b91c1c"], [0.3, "#7f1d1d"], [0.47, "#3a1f22"], [0.5, "#262b2f"],
    [0.53, "#1d3a28"], [0.7, "#166534"], [1.0, "#16a34a"],
]


def market_treemap(frame: pd.DataFrame, *, size_by: str = "equal", limit_pct: float = 0.04, height: int = 640) -> go.Figure:
    """Sector → stock treemap coloured by day change (clipped at ±limit_pct)."""
    data = frame.dropna(subset=["change_pct"]).copy()
    if data.empty:
        return empty_figure("Market map quotes are unavailable right now.", height=height)
    if size_by == "liquidity" and data["dollar_volume"].notna().any():
        floor = float(data["dollar_volume"].dropna().quantile(0.05) or 1.0)
        data["size"] = data["dollar_volume"].fillna(floor).clip(lower=floor)
    else:
        data["size"] = 1.0
    data["color"] = data["change_pct"].clip(-limit_pct, limit_pct)
    sectors = data.groupby("sector").agg(size=("size", "sum"), change=("change_pct", "median")).reset_index()
    ids = list(sectors["sector"]) + list(data["sector"] + "/" + data["ticker"])
    labels = list(sectors["sector"]) + list(data["ticker"])
    parents = [""] * len(sectors) + list(data["sector"])
    values = list(sectors["size"]) + list(data["size"])
    colors = list(sectors["change"].clip(-limit_pct, limit_pct)) + list(data["color"])
    custom = [[sector, "", change] for sector, change in zip(sectors["sector"], sectors["change"], strict=False)] + [
        [name, f"{price:,.2f}" if price else "—", change]
        for name, price, change in zip(data["name"], data["price"], data["change_pct"], strict=False)
    ]
    fig = go.Figure(
        go.Treemap(
            ids=ids, labels=labels, parents=parents, values=values, branchvalues="total",
            marker={"colors": colors, "colorscale": MAP_COLORSCALE, "cmin": -limit_pct, "cmax": limit_pct, "line": {"color": COLORS["paper"], "width": 1.5}, "pad": {"t": 22, "l": 2, "r": 2, "b": 2}},
            customdata=custom,
            texttemplate="<b>%{label}</b><br>%{customdata[2]:+.2%}",
            textfont={"family": FONT, "color": "#f8fafc"},
            hovertemplate="<b>%{label}</b> %{customdata[0]}<br>Price %{customdata[1]}<br>Day %{customdata[2]:+.2%}<extra></extra>",
            tiling={"pad": 2},
            pathbar={"visible": True, "thickness": 22, "textfont": {"color": COLORS["muted"]}},
        )
    )
    themed(fig, height=height, revision="market-map")
    fig.update_layout(margin={"l": 4, "r": 4, "t": 28, "b": 4}, hovermode="closest")
    return fig


def correlation_heatmap(series: dict[str, pd.DataFrame], *, height: int = 340) -> go.Figure:
    """Pairwise correlation of daily returns on common trading days."""
    closes = {
        ticker: frame.assign(day=frame["timestamp"].dt.normalize()).groupby("day")["close"].last()
        for ticker, frame in series.items()
        if frame is not None and not frame.empty
    }
    if len(closes) < 2:
        return empty_figure("Correlation needs at least two stocks with history.", height=height)
    matrix = pd.DataFrame(closes).pct_change().corr(min_periods=20)
    names = list(matrix.columns)
    fig = go.Figure(
        go.Heatmap(
            z=matrix.to_numpy(), x=names, y=names, zmin=-1, zmax=1,
            colorscale=[[0, "#b91c1c"], [0.5, "#1a1f22"], [1, "#16a34a"]],
            text=matrix.round(2).to_numpy(), texttemplate="%{text}", textfont={"size": 11},
            hovertemplate="%{y} / %{x}: %{z:.2f}<extra></extra>", showscale=False, xgap=2, ygap=2,
        )
    )
    fig.update_yaxes(autorange="reversed")
    themed(fig, height=height)
    fig.update_layout(hovermode="closest", margin={"l": 64, "r": 12, "t": 12, "b": 36})
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def rolling_beta_chart(beta: pd.Series, dates: pd.Series, label: str, *, height: int = 260) -> go.Figure:
    data = pd.DataFrame({"date": dates, "beta": beta}).dropna()
    if data.empty:
        return empty_figure("Rolling beta needs about three months of shared history.", height=height)
    fig = go.Figure(go.Scatter(x=data["date"], y=data["beta"], mode="lines", line={"color": COLORS["violet"], "width": 2}, hovertemplate="%{x|%d %b %Y}: %{y:.2f}<extra>60-day beta</extra>"))
    fig.add_hline(y=1, line={"color": COLORS["muted"], "width": 1, "dash": "dot"})
    fig.update_yaxes(title_text=f"Beta vs {label}", title_font={"size": 11, "color": COLORS["muted"]})
    return themed(fig, height=height, revision="rolling-beta")


def return_histogram(frame: pd.DataFrame, *, height: int = 260) -> go.Figure:
    returns = normalize_ohlcv(frame)["close"].pct_change().dropna().tail(252)
    if len(returns) < 20:
        return empty_figure("Not enough daily history for a distribution.", height=height)
    fig = go.Figure(go.Histogram(x=returns, nbinsx=40, marker={"color": COLORS["blue"], "line": {"width": 0}}, hovertemplate="%{x}: %{y} days<extra></extra>"))
    fig.add_vline(x=0, line={"color": COLORS["muted"], "width": 1, "dash": "dot"})
    fig.add_vline(x=float(returns.mean()), line={"color": COLORS["amber"], "width": 1.5})
    fig.update_xaxes(tickformat="+.0%", title_text="Daily return, last year (amber = mean)", title_font={"size": 11, "color": COLORS["muted"]})
    fig.update_yaxes(title_text="Days", title_font={"size": 11, "color": COLORS["muted"]})
    themed(fig, height=height, revision="returns")
    fig.update_layout(hovermode="closest", bargap=0.04)
    return fig
