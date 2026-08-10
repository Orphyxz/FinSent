from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd


def align_news_with_prices(
    news_df: pd.DataFrame,
    price_df: pd.DataFrame,
    return_window_minutes: int = 60,
) -> pd.DataFrame:
    if news_df.empty or price_df.empty:
        return pd.DataFrame()

    work_news = news_df.copy()
    work_prices = price_df.copy()

    work_news["published_at"] = pd.to_datetime(work_news["published_at"])
    work_prices["timestamp"] = pd.to_datetime(work_prices["timestamp"])
    work_prices = work_prices.sort_values("timestamp")

    merged = pd.merge_asof(
        work_news.sort_values("published_at"),
        work_prices[["timestamp", "close"]].rename(columns={"timestamp": "market_timestamp", "close": "entry_close"}),
        left_on="published_at",
        right_on="market_timestamp",
        direction="backward",
        tolerance=pd.Timedelta(days=2),
    )
    merged = merged.dropna(subset=["market_timestamp", "entry_close"]).copy()
    if merged.empty:
        return pd.DataFrame()

    future_prices = work_prices[["timestamp", "close"]].rename(
        columns={"timestamp": "future_timestamp", "close": "future_close"}
    )

    target_times = merged["market_timestamp"] + timedelta(minutes=return_window_minutes)
    merged["target_timestamp"] = target_times

    future_merged = pd.merge_asof(
        merged.sort_values("target_timestamp"),
        future_prices.sort_values("future_timestamp"),
        left_on="target_timestamp",
        right_on="future_timestamp",
        direction="forward",
        tolerance=max(pd.Timedelta(minutes=return_window_minutes), pd.Timedelta(days=2)),
    )

    future_merged = future_merged.dropna(
        subset=["market_timestamp", "entry_close", "future_timestamp", "future_close"]
    ).copy()

    future_merged["forward_return"] = (
        future_merged["future_close"] - future_merged["entry_close"]
    ) / future_merged["entry_close"]
    return future_merged


def build_daily_impact_summary(event_df: pd.DataFrame) -> pd.DataFrame:
    if event_df.empty:
        return pd.DataFrame()

    work = event_df.copy()
    work["event_date"] = pd.to_datetime(work["published_at"]).dt.date

    summary = (
        work.groupby("event_date")
        .agg(
            article_count=("id", "count"),
            mean_sentiment=("sentiment_score", "mean"),
            mean_forward_return=("forward_return", "mean"),
        )
        .reset_index()
    )

    if len(summary) >= 2:
        corr = summary["mean_sentiment"].corr(summary["mean_forward_return"])
    else:
        corr = np.nan
    summary["sentiment_return_correlation"] = corr
    return summary
