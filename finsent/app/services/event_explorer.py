"""Exploratory multi-window event study over the locked Phase 16 holdout articles.

This reads the locked prediction rows (never writes them) and re-measures each article's
market reaction at 1, 3 and 5 trading days with Event Study V2, plus the abnormal return
against SPY over the same entry and exit sessions. Results are descriptive and separate
from the preregistered 1D evaluation; they must not be used to tune the signal engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
import logging
import math
from pathlib import Path

import pandas as pd

from finsent.app.analysis.event_study_v2 import EventStudyEngineV2, EventStudyHorizon, EventStudyInputV2, EventStudyStatus
from finsent.app.services import market_overview


logger = logging.getLogger(__name__)

PREDICTIONS_PATH = Path(__file__).resolve().parents[3] / "output" / "research" / "phase16" / "final_holdout_predictions.csv"
BENCHMARK = "SPY"
WINDOWS = (("1D", 1), ("3D", 3), ("5D", 5))


@dataclass(frozen=True, slots=True)
class EventExplorerResult:
    events: pd.DataFrame
    summary: pd.DataFrame
    available: bool
    message: str


def _horizons() -> list[EventStudyHorizon]:
    return [EventStudyHorizon(label, trading_days=days) for label, days in WINDOWS]


def _returns(engine: EventStudyEngineV2, ticker: str, published_at, bars: pd.DataFrame) -> dict[str, float | None]:
    symbol = market_overview.resolve_symbol(ticker)
    if symbol is None or bars.empty:
        return {}
    study = EventStudyInputV2(
        instrument=symbol,
        event_timestamp=pd.Timestamp(published_at).to_pydatetime(),
        price_bars=bars,
        horizons=_horizons(),
        event_timezone="UTC",
        bars_timezone="UTC",
    )
    return {
        result.horizon.label: result.raw_return if result.status == EventStudyStatus.VALID else None
        for result in engine.evaluate(study)
    }


def _summarize(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label in ("BULLISH", "BEARISH", "NEUTRAL"):
        group = events[events["v1_direction"] == label]
        for window, _ in WINDOWS:
            values = pd.to_numeric(group[f"ar_{window}"], errors="coerce").dropna()
            if values.empty:
                continue
            n = len(values)
            std = float(values.std()) if n > 1 else 0.0
            rows.append({"group": label, "window": window, "mean": float(values.mean()), "ci": 1.96 * std / math.sqrt(n) if n > 1 else 0.0, "n": n})
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def load_event_explorer() -> EventExplorerResult:
    if not PREDICTIONS_PATH.exists():
        return EventExplorerResult(pd.DataFrame(), pd.DataFrame(), False, "Locked Phase 16 prediction rows are not available.")
    predictions = pd.read_csv(PREDICTIONS_PATH, parse_dates=["published_at"])
    predictions["ticker"] = predictions["instrument"].astype(str).str.split(":").str[-1]
    start = predictions["published_at"].min() - timedelta(days=10)
    end = predictions["published_at"].max() + timedelta(days=20)

    bars = {ticker: market_overview.history_between(ticker, start, end) for ticker in [*predictions["ticker"].unique(), BENCHMARK]}
    if bars[BENCHMARK].empty or all(frame.empty for key, frame in bars.items() if key != BENCHMARK):
        return EventExplorerResult(pd.DataFrame(), pd.DataFrame(), False, "Historical daily prices could not be fetched for the holdout period.")

    engine = EventStudyEngineV2()
    rows = []
    for record in predictions.itertuples(index=False):
        stock = _returns(engine, record.ticker, record.published_at, bars.get(record.ticker, pd.DataFrame()))
        market = _returns(engine, BENCHMARK, record.published_at, bars[BENCHMARK])
        row = {
            "article_id": record.article_id,
            "ticker": record.ticker,
            "published_at": record.published_at,
            "finbert_label": str(record.finbert_label).title(),
            "finbert_score": record.finbert_score,
            "v1_direction": str(record.v1_canonical_direction).upper(),
            "v2_direction": str(record.v2_canonical_direction).upper(),
            "realized": str(record.realized_direction).upper(),
            "locked_1d_return": record.event_1d_raw_return,
        }
        for window, _ in WINDOWS:
            raw = stock.get(window)
            bench = market.get(window)
            row[f"ret_{window}"] = raw
            row[f"ar_{window}"] = None if raw is None or bench is None else raw - bench
        rows.append(row)
    events = pd.DataFrame(rows).sort_values("published_at", ascending=False).reset_index(drop=True)
    return EventExplorerResult(events, _summarize(events), True, "")
