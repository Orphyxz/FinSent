from __future__ import annotations

from datetime import datetime

import pandas as pd

from finsent.app.analysis.market_impact import align_news_with_prices, build_daily_impact_summary


def test_align_news_with_prices_computes_forward_return() -> None:
    news_df = pd.DataFrame(
        [
            {
                "id": 1,
                "ticker": "AAPL",
                "title": "Apple outlook improves",
                "published_at": datetime(2026, 3, 27, 10, 0),
                "sentiment_score": 0.8,
            }
        ]
    )
    price_df = pd.DataFrame(
        [
            {"timestamp": datetime(2026, 3, 27, 9, 45), "close": 100.0},
            {"timestamp": datetime(2026, 3, 27, 10, 0), "close": 101.0},
            {"timestamp": datetime(2026, 3, 27, 11, 0), "close": 103.0},
        ]
    )

    event_df = align_news_with_prices(news_df, price_df, return_window_minutes=60)

    assert len(event_df) == 1
    assert round(event_df.iloc[0]["forward_return"], 6) == round((103.0 - 101.0) / 101.0, 6)


def test_build_daily_impact_summary_returns_expected_columns() -> None:
    event_df = pd.DataFrame(
        [
            {
                "id": 1,
                "published_at": datetime(2026, 3, 27, 10, 0),
                "sentiment_score": 0.8,
                "forward_return": 0.01,
            },
            {
                "id": 2,
                "published_at": datetime(2026, 3, 27, 12, 0),
                "sentiment_score": -0.2,
                "forward_return": -0.005,
            },
        ]
    )

    summary_df = build_daily_impact_summary(event_df)

    assert list(summary_df.columns) == [
        "event_date",
        "article_count",
        "mean_sentiment",
        "mean_forward_return",
        "sentiment_return_correlation",
    ]
    assert int(summary_df.iloc[0]["article_count"]) == 2
