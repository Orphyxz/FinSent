"""HTML building blocks shared by the intelligence pages."""

from __future__ import annotations

from datetime import datetime

from dash import dcc, html
import pandas as pd

from finsent.app.dashboard.charts import sparkline_svg
from finsent.app.services.market_overview import PriceSummary


def currency_symbol(currency: str | None) -> str:
    return "₹" if (currency or "").upper() == "INR" else "$"


def fmt_price(value: float | None, currency: str | None = "USD", *, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{currency_symbol(currency)}{value:,.{digits}f}"


def fmt_level(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def fmt_pct(value: float | None, *, digits: int = 2, signed: bool = True) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:{'+' if signed else ''}.{digits}f}%"


def tone_of(value: float | None, *, threshold: float = 0.0) -> str:
    if value is None or pd.isna(value):
        return "neutral"
    return "positive" if value > threshold else "negative" if value < -threshold else "neutral"


def change_chip(value: float | None) -> html.Span:
    tone = tone_of(value)
    arrow = "▲" if tone == "positive" else "▼" if tone == "negative" else "•"
    return html.Span([html.Span(arrow, className="chip-arrow"), fmt_pct(value)], className=f"change-chip tone-bg-{tone}")


def signal_pill(label: str | None, *, prefix: str | None = None) -> html.Span:
    text = (label or "No signal").strip()
    tone = {"bullish": "positive", "bearish": "negative", "neutral": "neutral"}.get(text.lower(), "muted")
    children = [html.Span(prefix, className="pill-prefix")] if prefix else []
    children.append(text)
    return html.Span(children, className=f"signal-pill signal-pill-{tone}")


def sentiment_pill(label: str | None) -> html.Span:
    normalized = (label or "").lower()
    if normalized in {"bullish", "positive"}:
        return html.Span("Positive", className="signal-pill signal-pill-positive")
    if normalized in {"bearish", "negative"}:
        return html.Span("Negative", className="signal-pill signal-pill-negative")
    return html.Span("Neutral", className="signal-pill signal-pill-neutral")


def sparkline(values: tuple[float, ...] | list[float], *, width: int = 120, height: int = 36, class_name: str = "sparkline") -> html.Img | html.Span:
    src = sparkline_svg(values, width=width, height=height)
    return html.Img(src=src, className=class_name, alt="") if src else html.Span(className=class_name)


def panel(kicker: str, title: str, body, *, class_name: str = "", action=None, body_id: str | None = None) -> html.Div:
    header = [html.Div([html.Div(kicker, className="section-kicker"), html.H3(title, className="section-title")])]
    if action is not None:
        header.append(action)
    body_div = html.Div(body, id=body_id) if body_id else body
    return html.Div([html.Div(header, className="panel-head"), body_div], className=f"section-shell intel-panel {class_name}".strip())


def index_card(item: PriceSummary) -> html.Div:
    tone = tone_of(item.change_pct)
    level = fmt_level(item.last) if item.region == "INDIA" else fmt_price(item.last, item.currency)
    return html.Div(
        [
            html.Div([html.Span(item.label, className="index-name"), html.Span(item.note, className="index-note")], className="index-head"),
            html.Div(level, className="index-level"),
            html.Div(
                [change_chip(item.change_pct), html.Span("" if item.change is None else f"{item.change:+,.2f}", className=f"index-delta tone-{tone}")],
                className="index-change",
            ),
            sparkline(item.sparkline, width=160, height=38, class_name="index-spark"),
        ],
        className=f"index-card index-{tone}",
    )


def mood_card(label: str, score: float | None, articles: int, market: str) -> html.Div:
    tone = {"Bullish": "positive", "Bearish": "negative"}.get(label, "neutral")
    position = 50 if score is None else max(2, min(98, 50 + score * 100))
    return html.Div(
        [
            html.Div("Market sentiment", className="section-kicker"),
            html.Div(label, className=f"mood-label tone-{tone}"),
            html.Div(
                [
                    html.Div(className="mood-track"),
                    html.Div(className="mood-marker", style={"left": f"{position:.0f}%"}),
                ],
                className="mood-gauge",
                title="Article-weighted FinBERT sentiment across the watchlist, from −1 to +1",
            ),
            html.Div([html.Span("Bearish"), html.Span("Neutral"), html.Span("Bullish")], className="mood-scale"),
            html.Div(
                [
                    html.Div([html.Span("Score", className="mini-label"), html.Span("—" if score is None else f"{score:+.2f}", className="mini-value")]),
                    html.Div([html.Span("Articles", className="mini-label"), html.Span(f"{articles:,}", className="mini-value")]),
                    html.Div([html.Span("Watchlist", className="mini-label"), html.Span(market.title() if market != "US" else "US", className="mini-value")]),
                ],
                className="mood-stats",
            ),
        ],
        className=f"section-shell mood-card mood-{tone}",
    )


def ticker_tape(items: list[PriceSummary]) -> list:
    """Two identical runs so the CSS marquee loops without a visible seam."""
    available = [item for item in items if item.available]
    if not available:
        return []

    def run(suffix: str) -> html.Div:
        return html.Div(
            [
                html.Span(
                    [
                        html.Span(item.key if item.region != "INDIA" or item.key in {"NIFTY50", "SENSEX", "BANKNIFTY"} else item.key, className="tape-symbol"),
                        html.Span(fmt_level(item.last) if item.key in {"NIFTY50", "SENSEX", "BANKNIFTY"} else fmt_price(item.last, item.currency), className="tape-price"),
                        html.Span(fmt_pct(item.change_pct), className=f"tape-change tone-{tone_of(item.change_pct)}"),
                    ],
                    className="tape-item",
                )
                for item in available
            ],
            className="tape-run",
            **({"aria-hidden": "true"} if suffix else {}),
        )

    return [run(""), run("copy")]


def focus_button(ticker: str, children, *, class_name: str = "") -> html.Button:
    return html.Button(children, id={"type": "focus-ticker", "ticker": ticker}, n_clicks=0, className=f"focus-button {class_name}".strip(), title=f"Open {ticker} in Stock Research")


def watchlist_table(rows) -> html.Div:
    header = html.Div(
        [
            html.Span("Symbol"), html.Span("Price"), html.Span("Day"), html.Span("Trend"),
            html.Span("Signal", className="simple-cell"),
            *[html.Span(label, className="analyst-cell") for label in ("Sentiment", "News 24h", "1M", "RSI", "Vol", "V1", "V2")],
        ],
        className="watch-row watch-head",
    )
    body = []
    for row in rows:
        sentiment = row.sentiment
        body.append(
            focus_button(
                row.ticker,
                [
                    html.Span([html.Span(row.ticker, className="watch-symbol"), html.Span(row.name, className="watch-name")], className="watch-id"),
                    html.Span(fmt_price(row.price.last, row.currency), className="watch-price"),
                    html.Span(change_chip(row.price.change_pct)),
                    html.Span(sparkline(row.price.sparkline, width=96, height=28)),
                    html.Span(signal_pill(row.v1_label), className="simple-cell"),
                    html.Span(
                        [
                            html.Span("—" if sentiment is None else f"{sentiment:+.2f}", className=f"tone-{tone_of(sentiment, threshold=0.05)}"),
                            html.Span(className="sent-bar", style={"--fill": f"{0 if sentiment is None else min(abs(sentiment), 1) * 100:.0f}%"}, **{"data-tone": tone_of(sentiment, threshold=0.05)}),
                        ],
                        className="watch-sentiment analyst-cell",
                    ),
                    html.Span(str(row.articles_24h), className="watch-count analyst-cell"),
                    html.Span(fmt_pct(row.return_1m, digits=1), className=f"analyst-cell tone-{tone_of(row.return_1m)}"),
                    html.Span("—" if row.rsi is None else f"{row.rsi:.0f}", className="analyst-cell"),
                    html.Span(fmt_pct(row.volatility, digits=0, signed=False), className="analyst-cell"),
                    html.Span(signal_pill(row.v1_label), className="analyst-cell"),
                    html.Span(signal_pill(row.v2_label), className="analyst-cell"),
                ],
                class_name="watch-row",
            )
        )
    return html.Div([header, *body], className="watch-table", role="table")


def _age(value) -> str:
    stamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(stamp):
        return ""
    minutes = max(0, int((pd.Timestamp.utcnow().tz_localize(None) - stamp).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes}m ago"
    if minutes < 60 * 48:
        return f"{minutes // 60}h ago"
    return f"{minutes // 1440}d ago"


def _catalyst_label(value: object) -> str:
    text = str(value or "other").replace("_", " ").title()
    return {"M And A": "M&A"}.get(text, text)


def catalyst_list(frame: pd.DataFrame, *, empty: str) -> html.Div:
    if frame is None or frame.empty:
        return html.Div(empty, className="empty-inline")
    items = []
    for _, row in frame.iterrows():
        tone = {"BULLISH": "positive", "BEARISH": "negative"}.get(str(row.get("catalyst_direction")), "neutral")
        ticker = str(row.get("primary_symbol") or "")
        title = str(row.get("event_title") or "")
        link = html.A(title, href=row.get("url"), target="_blank", rel="noopener noreferrer", className="catalyst-title") if row.get("url") else html.Span(title, className="catalyst-title")
        items.append(
            html.Div(
                [
                    html.Div(className=f"catalyst-rail rail-{tone}"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(ticker, className="catalyst-ticker"),
                                    html.Span(_catalyst_label(row.get("catalyst_type")), className="catalyst-type"),
                                    html.Span(str(row.get("catalyst_impact_label") or "").replace("_", " ").title(), className="catalyst-impact"),
                                    html.Span(_age(row.get("published_at")), className="catalyst-age"),
                                ],
                                className="catalyst-meta",
                            ),
                            link,
                        ],
                        className="catalyst-body",
                    ),
                ],
                className="catalyst-item",
            )
        )
    return html.Div(items, className="catalyst-stack")


def movers_list(rows) -> html.Div:
    ranked = sorted((row for row in rows if row.sentiment_change is not None), key=lambda row: abs(row.sentiment_change), reverse=True)[:5]
    if not ranked:
        return html.Div("Sentiment changes appear once each stock has a few days of analyzed news.", className="empty-inline")
    scale = max(abs(row.sentiment_change) for row in ranked) or 1.0
    return html.Div(
        [
            html.Div(
                [
                    html.Span(row.ticker, className="mover-symbol"),
                    html.Div(
                        html.Div(className=f"mover-fill tone-bg-{tone_of(row.sentiment_change)}", style={"width": f"{abs(row.sentiment_change) / scale * 100:.0f}%"}),
                        className=f"mover-track mover-{tone_of(row.sentiment_change)}",
                    ),
                    html.Span(f"{row.sentiment_change:+.2f}", className=f"mover-value tone-{tone_of(row.sentiment_change)}"),
                ],
                className="mover-row",
            )
            for row in ranked
        ],
        className="mover-stack",
    )


def distribution_bars(counts: dict[str, dict[str, int]]) -> html.Div:
    order = ["Bullish", "Neutral", "Bearish", "No signal"]
    blocks = []
    for engine, values in counts.items():
        total = sum(values.values()) or 1
        segments = [
            html.Div(className=f"dist-seg dist-{label.lower().replace(' ', '-')}", style={"width": f"{values.get(label, 0) / total * 100:.1f}%"}, title=f"{label}: {values.get(label, 0)}")
            for label in order
            if values.get(label)
        ]
        legend = [html.Span([html.I(className=f"dot dist-{label.lower().replace(' ', '-')}"), f"{label} {values.get(label, 0)}"]) for label in order if values.get(label)]
        blocks.append(html.Div([html.Div(engine, className="dist-engine"), html.Div(segments, className="dist-bar"), html.Div(legend, className="dist-legend")], className="dist-block"))
    return html.Div(blocks, className="dist-stack")


def stat_tile(label: str, value: str, note: str = "", *, tone: str = "neutral") -> html.Div:
    return html.Div(
        [html.Div(label, className="stat-label"), html.Div(value, className=f"stat-value tone-{tone}"), html.Div(note, className="stat-note")],
        className="stat-tile",
    )


def segmented(component_id: str, options: list[tuple[str, str]], value: str, *, class_name: str = "") -> dcc.RadioItems:
    return dcc.RadioItems(
        id=component_id,
        options=[{"label": label, "value": key} for key, label in options],
        value=value,
        inline=True,
        className=f"pill-toggle {class_name}".strip(),
        inputClassName="pill-toggle-input",
        labelClassName="pill-toggle-label",
    )


def updated_stamp(when: float | datetime | None) -> str:
    if when is None:
        return ""
    stamp = datetime.fromtimestamp(when) if isinstance(when, (int, float)) else when
    return f"Updated {stamp:%H:%M:%S}"


def _entity_chips(entities) -> list:
    chips = []
    for kind, values in (("company", entities.companies), ("person", entities.people), ("org", entities.organizations)):
        for value in values:
            chips.append(html.Span(value, className=f"entity-chip entity-{kind}", title={"company": "Company", "person": "Person", "org": "Organization"}[kind]))
    return chips


# Headline text by card key, so the explain callback needs no hidden State component.
_HEADLINES: dict[str, str] = {}


def headline_for_key(key: str) -> str | None:
    return _HEADLINES.get(key)


def news_card(row: pd.Series, entities) -> html.Article:
    label = str(row.get("sentiment_label") or "neutral")
    confidence = row.get("model_confidence")
    confidence_text = "" if confidence is None or pd.isna(confidence) else f"{float(confidence) * 100:.0f}% confidence"
    title = str(row.get("title") or "")
    url = row.get("url")
    summary = str(row.get("summary") or "").strip()
    if len(summary) > 260:
        summary = summary[:257].rsplit(" ", 1)[0] + "…"
    direction = str(row.get("catalyst_direction") or "")
    catalyst_type = row.get("catalyst_type")
    has_catalyst = isinstance(catalyst_type, str) and catalyst_type and catalyst_type.upper() != "OTHER"
    tone = {"BULLISH": "positive", "BEARISH": "negative"}.get(direction, "neutral")
    meta = [
        sentiment_pill(label),
        html.Span(confidence_text, className="news-confidence") if confidence_text else None,
        html.Span(str(row.get("ticker") or ""), className="news-ticker"),
        html.Span(str(row.get("source") or row.get("provider") or "").replace("_", " ").title(), className="news-source"),
        html.Span(_age(row.get("published_at")), className="news-age"),
    ]
    footer = _entity_chips(entities)
    key = str(row.get("id") if row.get("id") is not None and not pd.isna(row.get("id")) else abs(hash(title)))
    _HEADLINES[key] = title
    if has_catalyst:
        footer.insert(
            0,
            html.Span(
                [_catalyst_label(catalyst_type), html.Span(" · " + str(row.get("catalyst_impact_label") or "").replace("_", " ").title(), className="catalyst-chip-impact")],
                className=f"catalyst-chip catalyst-chip-{tone}",
                title=f"Catalyst: {_catalyst_label(catalyst_type)}, {direction.title() or 'no'} direction",
            ),
        )
    return html.Article(
        [
            html.Div([item for item in meta if item is not None], className="news-meta"),
            html.A(title, href=url, target="_blank", rel="noopener noreferrer", className="news-title") if url else html.Div(title, className="news-title"),
            html.P(summary, className="news-summary") if summary and summary.lower() != title.lower() else None,
            html.Div(
                [
                    html.Div(footer, className="news-tags"),
                    html.Button("Explain sentiment", id={"type": "explain-btn", "index": key}, n_clicks=0, className="explain-button", title="Show which words drove FinBERT's score"),
                ],
                className="news-foot",
            ),
            html.Div(id={"type": "explain-out", "index": key}, className="explain-out"),
        ],
        className=f"news-card news-{tone}",
    )


def sentiment_explanation(explanation) -> html.Div:
    if not explanation.available:
        return html.Div(explanation.message, className="empty-inline")
    scale = max((abs(item.weight) for item in explanation.words), default=0.0) or 1.0
    spans = []
    for item in explanation.words:
        strength = min(abs(item.weight) / scale, 1.0)
        if abs(item.weight) < 0.01:
            style = {}
        elif item.weight > 0:
            style = {"background": f"rgba(34,197,94,{0.12 + 0.5 * strength:.2f})"}
        else:
            style = {"background": f"rgba(239,68,68,{0.12 + 0.5 * strength:.2f})"}
        spans.append(html.Span(item.word, className="explain-word", style=style, title=f"{item.weight:+.2f}"))
        spans.append(" ")
    drivers = [
        *[html.Span(f"{item.word} {item.weight:+.2f}", className="explain-driver tone-positive") for item in explanation.top(positive=True)],
        *[html.Span(f"{item.word} {item.weight:+.2f}", className="explain-driver tone-negative") for item in explanation.top(positive=False)],
    ]
    return html.Div(
        [
            html.Div(spans, className="explain-text"),
            html.Div(
                [html.Span(f"FinBERT {explanation.label} {explanation.score:+.2f}", className="mini-label"), *drivers],
                className="explain-drivers",
            ),
            html.Div("Leave-one-word-out: each word's weight is how far the score moves when it is removed.", className="explain-note"),
        ],
        className="explain-panel",
    )


def news_summary_band(ticker_label: str, total: int, counts: dict[str, int], bias: str) -> list:
    tone = {"Bullish": "positive", "Bearish": "negative"}.get(bias, "neutral")
    segments = [
        html.Div(className=f"dist-seg dist-{key}", style={"width": f"{counts.get(label, 0) / max(total, 1) * 100:.1f}%"})
        for key, label in (("bullish", "Positive"), ("neutral", "Neutral"), ("bearish", "Negative"))
        if counts.get(label)
    ]
    return [
        html.Div([html.Span("Ticker", className="mini-label"), html.Span(ticker_label, className="band-value")], className="band-cell"),
        html.Div([html.Span("Articles", className="mini-label"), html.Span(f"{total:,}", className="band-value")], className="band-cell"),
        html.Div([html.Span("Bias", className="mini-label"), html.Span(bias, className=f"band-value tone-{tone}")], className="band-cell"),
        html.Div([html.Span("Positive", className="mini-label tone-positive"), html.Span(str(counts.get("Positive", 0)), className="band-value tone-positive")], className="band-cell"),
        html.Div([html.Span("Neutral", className="mini-label"), html.Span(str(counts.get("Neutral", 0)), className="band-value")], className="band-cell"),
        html.Div([html.Span("Negative", className="mini-label tone-negative"), html.Span(str(counts.get("Negative", 0)), className="band-value tone-negative")], className="band-cell"),
        html.Div([html.Span("Distribution", className="mini-label"), html.Div(segments, className="dist-bar")], className="band-cell band-wide"),
    ]


def breakdown_bars(counts: dict[str, int], *, limit: int = 8) -> html.Div:
    if not counts:
        return html.Div("No classified catalysts in this selection.", className="empty-inline")
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    top = ordered[0][1] or 1
    return html.Div(
        [
            html.Div(
                [
                    html.Span(name, className="breakdown-name"),
                    html.Div(html.Div(className="breakdown-fill", style={"width": f"{value / top * 100:.0f}%"}), className="breakdown-track"),
                    html.Span(str(value), className="breakdown-value"),
                ],
                className="breakdown-row",
            )
            for name, value in ordered
        ]
    )


def compare_card(profile, color: str) -> html.Div:
    price = profile.price
    period_return = None
    if not profile.history.empty and len(profile.history) >= 2:
        first = float(profile.history["close"].iloc[0])
        period_return = None if not first else float(profile.history["close"].iloc[-1]) / first - 1.0
    return focus_button(
        profile.ticker,
        [
            html.Div([html.Span(className="series-dot", style={"background": color}), html.Span(profile.ticker, className="compare-ticker"), html.Span(profile.name, className="compare-name")], className="compare-head"),
            html.Div(fmt_price(price.last, profile.currency), className="compare-price"),
            html.Div([change_chip(price.change_pct), html.Span(f"Period {fmt_pct(period_return, digits=1)}", className=f"tone-{tone_of(period_return)}")], className="compare-change"),
            html.Div([signal_pill(profile.v1_label, prefix="V1"), signal_pill(profile.v2_label, prefix="V2")], className="compare-signals"),
            html.Div(
                [
                    html.Span(["Sentiment ", html.B("—" if profile.sentiment is None else f"{profile.sentiment:+.2f}", className=f"tone-{tone_of(profile.sentiment, threshold=0.05)}")]),
                    html.Span(["News ", html.B(f"{profile.articles}")]),
                    html.Span(["Vol ", html.B(fmt_pct(profile.volatility, digits=0, signed=False))]),
                ],
                className="compare-foot",
            ),
        ],
        class_name="compare-card",
    )


def signal_matrix(profiles) -> html.Div:
    header = html.Div([html.Span("Symbol"), html.Span("Signal V1"), html.Span("Signal V2"), html.Span("V2 score"), html.Span("Agreement")], className="matrix-row matrix-head")
    rows = [header]
    for profile in profiles:
        agree = profile.v1_label == profile.v2_label and profile.v1_label != "No signal"
        rows.append(
            html.Div(
                [
                    html.Span(profile.ticker, className="watch-symbol"),
                    html.Span(signal_pill(profile.v1_label)),
                    html.Span(signal_pill(profile.v2_label)),
                    html.Span("—" if profile.v2_score is None else f"{float(profile.v2_score):+.3f}", className=f"tone-{tone_of(profile.v2_score, threshold=0.02)}"),
                    html.Span("Agree" if agree else "Differ" if profile.v1_label != "No signal" else "—", className=f"agree-tag agree-{'yes' if agree else 'no'}"),
                ],
                className="matrix-row",
            )
        )
    return html.Div(rows, className="matrix-table")


def price_movers(frame: pd.DataFrame, *, ascending: bool, limit: int = 6) -> html.Div:
    data = frame.dropna(subset=["change_pct"]).sort_values("change_pct", ascending=ascending).head(limit) if not frame.empty else frame
    if data is None or data.empty:
        return html.Div("No quotes yet.", className="empty-inline")
    return html.Div(
        [
            focus_button(
                row["ticker"],
                [
                    html.Span([html.Span(row["ticker"], className="watch-symbol"), html.Span(row["name"], className="watch-name")], className="watch-id"),
                    change_chip(row["change_pct"]),
                ],
                class_name="mover-button",
            )
            for _, row in data.iterrows()
        ],
        className="mover-buttons",
    )


def breadth_strip(frame: pd.DataFrame) -> list:
    changes = frame["change_pct"].dropna() if not frame.empty else pd.Series(dtype=float)
    if changes.empty:
        return []
    advancers, decliners = int((changes > 0).sum()), int((changes < 0).sum())
    unchanged = len(changes) - advancers - decliners
    total = len(changes)
    return [
        html.Div([html.Span("Stocks", className="mini-label"), html.Span(f"{total}", className="band-value")], className="band-cell"),
        html.Div([html.Span("Advancing", className="mini-label tone-positive"), html.Span(f"{advancers}", className="band-value tone-positive")], className="band-cell"),
        html.Div([html.Span("Declining", className="mini-label tone-negative"), html.Span(f"{decliners}", className="band-value tone-negative")], className="band-cell"),
        html.Div([html.Span("Median move", className="mini-label"), html.Span(fmt_pct(float(changes.median())), className=f"band-value tone-{tone_of(float(changes.median()))}")], className="band-cell"),
        html.Div(
            [
                html.Span("Breadth", className="mini-label"),
                html.Div(
                    [
                        html.Div(className="dist-seg dist-bullish", style={"width": f"{advancers / total * 100:.1f}%"}),
                        html.Div(className="dist-seg dist-neutral", style={"width": f"{unchanged / total * 100:.1f}%"}),
                        html.Div(className="dist-seg dist-bearish", style={"width": f"{decliners / total * 100:.1f}%"}),
                    ],
                    className="dist-bar",
                ),
            ],
            className="band-cell band-wide",
        ),
    ]


def sector_breadth_rows(breadth: pd.DataFrame) -> html.Div:
    if breadth.empty:
        return html.Div("No sector data.", className="empty-inline")
    rows = []
    for _, row in breadth.iterrows():
        total = max(int(row["stocks"]), 1)
        rows.append(
            html.Div(
                [
                    html.Span(row["sector"], className="breadth-sector"),
                    html.Div(
                        [
                            html.Div(className="dist-seg dist-bullish", style={"width": f"{row['advancers'] / total * 100:.1f}%"}),
                            html.Div(className="dist-seg dist-bearish", style={"width": f"{row['decliners'] / total * 100:.1f}%"}),
                        ],
                        className="dist-bar breadth-bar",
                    ),
                    html.Span(f"{int(row['advancers'])}↑ {int(row['decliners'])}↓", className="breadth-count"),
                    html.Span(fmt_pct(row["median_change"]), className=f"breadth-median tone-{tone_of(row['median_change'])}"),
                ],
                className="breadth-row",
            )
        )
    return html.Div(rows, className="breadth-rows")


def market_brief(snapshot) -> list:
    """One plain-English paragraph for Simple view: market, sentiment, biggest mover."""
    lead = next((item for item in snapshot.indices if item.available), None)
    sentences = []
    if lead is not None and lead.change_pct is not None:
        direction = "up" if lead.change_pct > 0 else "down" if lead.change_pct < 0 else "flat"
        sentences.append(f"The {lead.label} is {direction} {abs(lead.change_pct) * 100:.1f}% on the latest session.")
    sentences.append(
        {
            "Bullish": "News across your watchlist is mostly positive.",
            "Bearish": "News across your watchlist is mostly negative.",
            "Neutral": "News across your watchlist is mixed, with no clear direction.",
        }.get(snapshot.mood_label, "There is not enough analyzed news yet to read the mood.")
    )
    movers = [row for row in snapshot.rows if row.price.change_pct is not None]
    if movers:
        biggest = max(movers, key=lambda row: abs(row.price.change_pct))
        verb = "rose" if biggest.price.change_pct > 0 else "fell"
        sentences.append(f"Biggest move: {biggest.name} {verb} {abs(biggest.price.change_pct) * 100:.1f}%.")
    tone = {"Bullish": "positive", "Bearish": "negative"}.get(snapshot.mood_label, "neutral")
    return [
        html.Div("Today in brief", className="section-kicker"),
        html.P(" ".join(sentences), className=f"plain-brief-text brief-{tone}"),
    ]


def _lean(value: float | None, *, up: str, down: str, flat: str, threshold: float = 0.05) -> str:
    if value is None:
        return flat
    return up if value > threshold else down if value < -threshold else flat


def stock_verdict(ticker: str, name: str, label: str | None, components: dict[str, float | None], return_1m: float | None) -> list:
    """Plain-English reading of the signal for Simple view."""
    verdict = (label or "No signal").replace("_", " ").title()
    news = _lean(components.get("news"), up="Recent news is positive", down="Recent news is negative", flat="Recent news is mixed")
    momentum = _lean(components.get("price_momentum"), up="the price has been rising", down="the price has been falling", flat="the price has been steady")
    joiner = " and " if (news.endswith("positive") and "rising" in momentum) or (news.endswith("negative") and "falling" in momentum) else ", while "
    month = "" if return_1m is None else f" Over the past month the stock is {'up' if return_1m >= 0 else 'down'} {abs(return_1m) * 100:.1f}%."
    tone = {"Bullish": "positive", "Bearish": "negative"}.get(verdict, "neutral")
    return [
        html.Div("FinSent's read", className="section-kicker"),
        html.Div([html.Span(f"{name} looks ", className="verdict-lead"), html.Span(verdict, className=f"verdict-word tone-{tone}")], className="verdict-line"),
        html.P(f"{news}{joiner}{momentum}.{month}", className="plain-brief-text"),
        html.Div("Research signal only, not investment advice.", className="research-note compact-note"),
    ]


def risk_tiles(stats) -> list:
    def pct(value):
        return fmt_pct(value, digits=1)

    def ratio(value):
        return "—" if value is None else f"{value:.2f}"

    return [
        stat_tile("Annual return", pct(stats.annual_return), "Compounded", tone=tone_of(stats.annual_return)),
        stat_tile("Volatility", fmt_pct(stats.annual_volatility, digits=1, signed=False), "Annualized"),
        stat_tile("Sharpe", ratio(stats.sharpe), "Return per unit of risk", tone=tone_of(stats.sharpe)),
        stat_tile("Sortino", ratio(stats.sortino), "Downside risk only", tone=tone_of(stats.sortino)),
        stat_tile("Max drawdown", pct(stats.max_drawdown), "Peak to trough", tone="negative"),
        stat_tile("Best day", pct(stats.best_day), "Largest daily gain", tone="positive"),
        stat_tile("Worst day", pct(stats.worst_day), "Largest daily loss", tone="negative"),
        stat_tile("Up days", fmt_pct(stats.up_day_ratio, digits=0, signed=False), f"{stats.observations} sessions"),
    ]


def news_brief(tickers: str, total: int, counts: dict[str, int], bias: str) -> list:
    if not total:
        return []
    return [
        html.Div("News in brief", className="section-kicker"),
        html.P(
            f"Coverage of {tickers} reads {bias.lower()}: {counts.get('Positive', 0)} positive, "
            f"{counts.get('Neutral', 0)} neutral and {counts.get('Negative', 0)} negative articles.",
            className="plain-brief-text",
        ),
    ]
