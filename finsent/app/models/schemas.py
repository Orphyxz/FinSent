from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ScrapedNewsItem:
    ticker: str
    source: str
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
    exchange: str | None = None
    provider: str | None = None
    ingested_at: datetime | None = None
    dedupe_hash: str | None = None
    relevance_score: float | None = None


@dataclass(slots=True)
class MarketSignalSnapshot:
    bid: float | None
    ask: float | None
    bid_ask_spread: float | None
    spread_pct: float
    volume_ratio: float
    buy_sell_ratio: float
    buy_pressure: float
    market_signal: float
    last_price: float | None = None
    price_timestamp: datetime | None = None


@dataclass(slots=True)
class SentimentResult:
    label: str
    score: float
    positive: float
    negative: float
    neutral: float
    model_label: str
    model_confidence: float
    text_score: float
    signal_confidence: float
    bid_ask_spread: float | None = None
    spread_pct: float = 0.0
    volume_ratio: float = 1.0
    buy_sell_ratio: float = 1.0
    buy_pressure: float = 0.0
    market_signal: float = 0.0
    relevant: bool = True
    impact_strength: float = 0.0
    time_horizon: str = "1-3d"
    catalyst_tag: str = "other"
    short_reason: str = ""
    analysis_provider: str | None = None
    parse_status: str | None = None
