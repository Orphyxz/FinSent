from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from finsent.app.analysis.event_study_v2 import EventStudyEngineV2, EventStudyHorizon, EventStudyInputV2, EventStudyStatus
from finsent.app.analysis.market_impact import align_news_with_prices
from finsent.app.services.symbol_registry import registry


NY = ZoneInfo("America/New_York")


def _news(published_at: datetime) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": 1,
                "ticker": "AAPL",
                "title": "Apple headline",
                "published_at": published_at,
                "sentiment_score": 0.5,
            }
        ]
    )


def _prices(rows: list[tuple[datetime, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"timestamp": timestamp, "close": close} for timestamp, close in rows])


def test_event_study_market_hours_exact_target_bar() -> None:
    event_df = align_news_with_prices(
        _news(datetime(2026, 3, 27, 10, 0)),
        _prices(
            [
                (datetime(2026, 3, 27, 10, 0), 100.0),
                (datetime(2026, 3, 27, 11, 0), 102.0),
            ]
        ),
        return_window_minutes=60,
    )

    assert len(event_df) == 1
    assert event_df.iloc[0]["market_timestamp"] == pd.Timestamp("2026-03-27 10:00:00")
    assert event_df.iloc[0]["future_timestamp"] == pd.Timestamp("2026-03-27 11:00:00")


def test_event_study_uses_forward_bar_after_target_not_nearest_prior_bar() -> None:
    event_df = align_news_with_prices(
        _news(datetime(2026, 3, 27, 10, 0)),
        _prices(
            [
                (datetime(2026, 3, 27, 10, 0), 100.0),
                (datetime(2026, 3, 27, 10, 59), 101.0),
                (datetime(2026, 3, 27, 11, 5), 103.0),
            ]
        ),
        return_window_minutes=60,
    )

    assert len(event_df) == 1
    assert event_df.iloc[0]["future_timestamp"] == pd.Timestamp("2026-03-27 11:05:00")


def test_event_study_missing_future_bar_returns_empty() -> None:
    event_df = align_news_with_prices(
        _news(datetime(2026, 3, 27, 10, 0)),
        _prices([(datetime(2026, 3, 27, 10, 0), 100.0)]),
        return_window_minutes=60,
    )

    assert event_df.empty


def test_event_study_friday_after_hours_too_distant_future_price_is_empty_current_behavior() -> None:
    event_df = align_news_with_prices(
        _news(datetime(2026, 3, 27, 17, 0)),
        _prices(
            [
                (datetime(2026, 3, 27, 15, 45), 100.0),
                (datetime(2026, 3, 30, 9, 15), 102.0),
            ]
        ),
        return_window_minutes=60,
    )

    assert event_df.empty


def test_event_study_timezone_aware_inputs_with_common_timezone() -> None:
    event_df = align_news_with_prices(
        _news(datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc)),
        _prices(
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=timezone.utc), 100.0),
                (datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc), 101.0),
            ]
        ),
        return_window_minutes=60,
    )

    assert len(event_df) == 1


def test_event_study_weekend_article_should_not_use_friday_entry_price() -> None:
    result = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=registry.get("US", "AAPL"),
            event_timestamp=datetime(2026, 3, 28, 12, 0, tzinfo=NY),
            price_bars=_prices(
                [
                    (datetime(2026, 3, 27, 15, 45, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 28, 13, 0, tzinfo=NY), 102.0),
                ]
            ),
            horizons=[EventStudyHorizon.parse("1h")],
        )
    )[0]

    assert result.status == EventStudyStatus.NO_ENTRY_BAR


def test_event_study_after_close_article_should_not_use_next_day_exit_as_60_minute_return() -> None:
    result = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=registry.get("US", "AAPL"),
            event_timestamp=datetime(2026, 3, 26, 16, 30, tzinfo=NY),
            price_bars=_prices(
                [
                    (datetime(2026, 3, 26, 15, 45, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 27, 9, 30, tzinfo=NY), 103.0),
                    (datetime(2026, 3, 27, 10, 30, tzinfo=NY), 104.0),
                ]
            ),
            horizons=[EventStudyHorizon.parse("1h")],
        )
    )[0]

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == pd.Timestamp("2026-03-27 13:30:00")
    assert result.target_timestamp == pd.Timestamp("2026-03-27 14:30:00")


def test_event_study_future_bar_much_later_than_horizon_should_not_match() -> None:
    result = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=registry.get("US", "AAPL"),
            event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            price_bars=_prices(
                [
                    (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 28, 10, 0, tzinfo=NY), 110.0),
                ]
            ),
            horizons=[EventStudyHorizon.parse("1h")],
        )
    )[0]

    assert result.status == EventStudyStatus.OUT_OF_TOLERANCE
    assert result.raw_return is None
