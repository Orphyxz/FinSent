from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.analysis.event_study_v2 import (
    ENGINE_NAME_EVENT_STUDY_V2,
    ENGINE_VERSION_EVENT_STUDY_V2,
    BarFrequency,
    EventStudyEngineV2,
    EventStudyHorizon,
    EventStudyInputV2,
    EventStudyStatus,
    MatchQuality,
    calendar_for_exchange,
)
from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import EventStudyResult
from finsent.app.database.research_repository import ResearchResultRepository, json_loads
from finsent.app.services.event_study_service_v2 import EventStudyBatchRunnerV2, EventStudyServiceV2
from finsent.app.services.symbol_registry import registry


NY = ZoneInfo("America/New_York")
IST = ZoneInfo("Asia/Kolkata")
AAPL = registry.get("US", "AAPL")
TCS = registry.get("NSE", "TCS")


def _bars(rows: list[tuple[datetime, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"timestamp": timestamp, "close": close} for timestamp, close in rows])


def _daily(rows: list[tuple[datetime, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"timestamp": timestamp, "close": close} for timestamp, close in rows])


def _input(
    event_timestamp: datetime,
    rows: list[tuple[datetime, float]],
    *,
    symbol=AAPL,
    horizons: list[str] | None = None,
    event_timezone: str | None = None,
    bars_timezone: str | None = None,
) -> EventStudyInputV2:
    assert symbol is not None
    return EventStudyInputV2(
        instrument=symbol,
        event_timestamp=event_timestamp,
        price_bars=_bars(rows),
        horizons=[EventStudyHorizon.parse(value) for value in (horizons or ["1h"])],
        event_timezone=event_timezone,
        bars_timezone=bars_timezone,
    )


def _evaluate(study_input: EventStudyInputV2):
    return EventStudyEngineV2().evaluate(study_input)[0]


def test_market_hours_event_exact_bar_and_target_is_valid() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 102.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.match_quality == MatchQuality.EXACT
    assert result.raw_return == 0.020000000000000018
    assert result.elapsed_trading_minutes == 60.0


def test_event_between_bars_uses_first_bar_after_event() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 2, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 99.0),
                (datetime(2026, 3, 27, 10, 5, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 11, 5, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.entry_timestamp == datetime(2026, 3, 27, 14, 5)
    assert result.raw_return == 0.010000000000000009


def test_event_shortly_after_market_open_is_valid() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 9, 31, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 9, 35, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 10, 35, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.entry_timestamp == datetime(2026, 3, 27, 13, 35)


def test_event_shortly_before_close_crosses_to_next_session_for_1h() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 26, 15, 45, tzinfo=NY),
            [
                (datetime(2026, 3, 26, 15, 45, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 10, 15, tzinfo=NY), 103.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.target_timestamp == datetime(2026, 3, 27, 14, 15)
    assert result.elapsed_trading_minutes == 60.0


def test_missing_immediate_entry_bar_outside_tolerance_is_rejected() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 9, 30, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 12, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 13, 0, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.OUT_OF_TOLERANCE
    assert result.raw_return is None


def test_after_close_event_effective_time_is_next_session_open() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 26, 16, 1, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 10, 30, tzinfo=NY), 102.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 3, 27, 13, 30)
    assert result.entry_timestamp == datetime(2026, 3, 27, 13, 30)


def test_late_evening_event_uses_next_session_open() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 26, 22, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 10, 30, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 3, 27, 13, 30)


def test_friday_after_hours_advances_over_weekend() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 17, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 30, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 30, 10, 30, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 3, 30, 13, 30)


def test_after_hours_before_known_holiday_advances_to_next_open() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 7, 2, 17, 0, tzinfo=NY),
            [
                (datetime(2026, 7, 6, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 7, 6, 10, 30, tzinfo=NY), 102.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 7, 6, 13, 30)


def test_saturday_event_uses_monday_open() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 28, 12, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 30, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 30, 10, 30, tzinfo=NY), 102.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 3, 30, 13, 30)


def test_sunday_event_uses_monday_open() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 29, 12, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 30, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 30, 10, 30, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 3, 30, 13, 30)


def test_known_market_holiday_advances_to_next_open() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 7, 3, 11, 0, tzinfo=NY),
            [
                (datetime(2026, 7, 6, 9, 30, tzinfo=NY), 100.0),
                (datetime(2026, 7, 6, 10, 30, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 7, 6, 13, 30)


def test_consecutive_closed_dates_advance_to_session() -> None:
    calendar = calendar_for_exchange("US")
    assert calendar is not None
    effective = calendar.effective_event_time(datetime(2026, 7, 3, 12, 0, tzinfo=NY))
    assert effective == datetime(2026, 7, 6, 9, 30, tzinfo=NY)


def test_1h_crossing_session_boundary_uses_trading_minutes() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 26, 15, 30, tzinfo=NY),
            [
                (datetime(2026, 3, 26, 15, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.target_timestamp == datetime(2026, 3, 27, 14, 0)


def test_4h_same_session() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 14, 0, tzinfo=NY), 104.0),
            ],
            horizons=["4h"],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.elapsed_trading_minutes == 240.0


def test_4h_crossing_overnight() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 26, 14, 30, tzinfo=NY),
            [
                (datetime(2026, 3, 26, 14, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 12, 0, tzinfo=NY), 102.0),
            ],
            horizons=["4h"],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.target_timestamp == datetime(2026, 3, 27, 16, 0)


def test_4h_crossing_weekend() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 14, 30, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 14, 30, tzinfo=NY), 100.0),
                (datetime(2026, 3, 30, 12, 0, tzinfo=NY), 105.0),
            ],
            horizons=["4h"],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.target_timestamp == datetime(2026, 3, 30, 16, 0)


def test_1d_next_trading_session_same_local_time() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 11, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 30, 11, 0, tzinfo=NY), 103.0),
            ],
            horizons=["1d"],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.target_timestamp == datetime(2026, 3, 30, 15, 0)


def test_slightly_delayed_exit_match_is_accepted_and_degraded_or_good() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 11, 5, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.matched_exit_timestamp == datetime(2026, 3, 27, 15, 5)
    assert result.match_quality in {MatchQuality.GOOD, MatchQuality.DEGRADED}


def test_far_late_exit_match_is_rejected() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 28, 10, 0, tzinfo=NY), 110.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.OUT_OF_TOLERANCE
    assert result.raw_return is None


def test_daily_bars_do_not_support_1h_or_4h() -> None:
    results = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=AAPL,
            event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            price_bars=_daily(
                [
                    (datetime(2026, 3, 27, 16, 0, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 30, 16, 0, tzinfo=NY), 102.0),
                ]
            ),
            horizons=[EventStudyHorizon.parse("1h"), EventStudyHorizon.parse("4h")],
        )
    )

    assert [result.status for result in results] == [
        EventStudyStatus.UNSUPPORTED_GRANULARITY,
        EventStudyStatus.UNSUPPORTED_GRANULARITY,
    ]


def test_daily_bars_support_1d_session_day_return() -> None:
    result = _evaluate(
        EventStudyInputV2(
            instrument=AAPL,
            event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            price_bars=_daily(
                [
                    (datetime(2026, 3, 27, 16, 0, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 30, 16, 0, tzinfo=NY), 103.0),
                ]
            ),
            horizons=[EventStudyHorizon.parse("1d")],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.raw_return == 0.030000000000000027


def test_utc_article_timestamp_converts_to_us_exchange_time() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 14, 0, tzinfo=timezone.utc),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.entry_timestamp == datetime(2026, 3, 27, 14, 0)


def test_india_timezone_aware_article() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 4, 15, 10, 0, tzinfo=IST),
            [
                (datetime(2026, 4, 15, 10, 0, tzinfo=IST), 100.0),
                (datetime(2026, 4, 15, 11, 0, tzinfo=IST), 102.0),
            ],
            symbol=TCS,
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.entry_timestamp == datetime(2026, 4, 15, 4, 30)


def test_utc_article_timestamp_converts_to_india_exchange_time() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 4, 15, 4, 30, tzinfo=timezone.utc),
            [
                (datetime(2026, 4, 15, 10, 0, tzinfo=IST), 100.0),
                (datetime(2026, 4, 15, 11, 0, tzinfo=IST), 101.0),
            ],
            symbol=TCS,
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.effective_event_timestamp == datetime(2026, 4, 15, 4, 30)


def test_naive_timestamp_defaults_to_canonical_utc_policy() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 14, 0),
            [
                (datetime(2026, 3, 27, 14, 0), 100.0),
                (datetime(2026, 3, 27, 15, 0), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.original_event_timestamp == datetime(2026, 3, 27, 14, 0)


def test_explicit_local_timezone_for_naive_source_timestamp() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0),
            [
                (datetime(2026, 3, 27, 10, 0), 100.0),
                (datetime(2026, 3, 27, 11, 0), 102.0),
            ],
            event_timezone="America/New_York",
            bars_timezone="America/New_York",
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.original_event_timestamp == datetime(2026, 3, 27, 14, 0)


def test_invalid_timezone_is_invalid_timestamp() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0),
            [(datetime(2026, 3, 27, 10, 0), 100.0)],
            event_timezone="Mars/Exchange",
        )
    )

    assert result.status == EventStudyStatus.INVALID_TIMESTAMP


def test_us_dst_sensitive_date_uses_new_york_offset() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 11, 2, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 11, 2, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 11, 2, 11, 0, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert result.entry_timestamp == datetime(2026, 11, 2, 15, 0)


def test_duplicate_and_unsorted_bars_are_normalized_with_warning() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 101.0),
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 99.0),
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert "Duplicate bar timestamps were collapsed." in result.quality_warnings


def test_invalid_price_bar_is_ignored_with_warning() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), -1.0),
                (datetime(2026, 3, 27, 10, 5, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 11, 5, tzinfo=NY), 101.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.VALID
    assert any("invalid prices" in warning for warning in result.quality_warnings)


def test_missing_timestamp_column_and_plain_index_is_supported() -> None:
    frame = pd.DataFrame(
        [{"close": 100.0}, {"close": 101.0}],
        index=[datetime(2026, 3, 27, 10, 0, tzinfo=NY), datetime(2026, 3, 27, 11, 0, tzinfo=NY)],
    )

    result = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=AAPL,
            event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            price_bars=frame,
            horizons=[EventStudyHorizon.parse("1h")],
        )
    )[0]

    assert result.status == EventStudyStatus.VALID


def test_irregular_intervals_are_rejected_explicitly() -> None:
    result = _evaluate(
        _input(
            datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            [
                (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                (datetime(2026, 3, 27, 10, 1, tzinfo=NY), 101.0),
                (datetime(2026, 3, 27, 15, 0, tzinfo=NY), 102.0),
            ],
        )
    )

    assert result.status == EventStudyStatus.UNSUPPORTED_GRANULARITY
    assert result.bar_frequency == BarFrequency.IRREGULAR


def test_empty_data_is_insufficient_data() -> None:
    result = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=AAPL,
            event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
            price_bars=pd.DataFrame(),
            horizons=[EventStudyHorizon.parse("1h")],
        )
    )[0]

    assert result.status == EventStudyStatus.INSUFFICIENT_DATA


def test_persist_valid_result_round_trips_metadata() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as session:
        service = EventStudyServiceV2(session=session)
        records = service.evaluate(
            _input(
                datetime(2026, 3, 27, 10, 0, tzinfo=NY),
                [
                    (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 102.0),
                ],
            ),
            persist=True,
        )

        row = session.execute(select(EventStudyResult).where(EventStudyResult.id == records[0].persisted_result_id)).scalar_one()
        metadata = json_loads(row.metadata_json)
        assert row.status == "VALID"
        assert row.raw_return == records[0].result.raw_return
        assert row.matched_market_timestamp == datetime(2026, 3, 27, 15, 0)
        assert row.target_timestamp == datetime(2026, 3, 27, 15, 0)
        assert row.elapsed_minutes == 60.0
        assert metadata["engine_name"] == ENGINE_NAME_EVENT_STUDY_V2
        assert metadata["engine_version"] == ENGINE_VERSION_EVENT_STUDY_V2
        assert metadata["entry_timestamp"] == "2026-03-27T14:00:00"


def test_persist_invalid_no_exit_result_preserves_null_return_and_status() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as session:
        service = EventStudyServiceV2(session=session)
        records = service.evaluate(
            _input(datetime(2026, 3, 27, 10, 0, tzinfo=NY), [(datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0)]),
            persist=True,
        )

        row = session.execute(select(EventStudyResult).where(EventStudyResult.id == records[0].persisted_result_id)).scalar_one()
        assert row.status == "INSUFFICIENT_DATA"
        assert row.raw_return is None


def test_experiment_and_signal_ids_are_preserved() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as session:
        instrument = registry.get("US", "AAPL")
        stored_signal = ResearchResultRepository(session).store_signal_run(
            instrument_id=1,
            experiment_id=7,
            generated_at=datetime(2026, 3, 27, 14, 0),
            engine_name="finsent_composite",
            engine_version="2.0",
            final_score=0.5,
            label="bullish",
            confidence=0.6,
            signal_mode="NEWS_PLUS_MARKET",
        )
        result = EventStudyServiceV2(session=session).evaluate(
            EventStudyInputV2(
                instrument=instrument,
                event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
                price_bars=_bars(
                    [
                        (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                        (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 105.0),
                    ]
                ),
                horizons=[EventStudyHorizon.parse("1h")],
                signal_run_id=stored_signal.id,
                experiment_id=7,
            ),
            persist=True,
        )[0].result

        assert result.status == EventStudyStatus.VALID
        assert result.signal_run_id == stored_signal.id
        assert result.experiment_id == 7


def test_v1_and_v2_event_study_records_can_coexist() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as session:
        repo = ResearchResultRepository(session)
        repo.store_event_study_result(
            instrument_id=1,
            event_timestamp=datetime(2026, 3, 27, 14, 0),
            horizon_minutes=60,
            status="VALID",
            matching_method="legacy_v1_loose_asof",
            metadata={"engine_name": "legacy_market_impact", "engine_version": "1.0"},
        )
        EventStudyServiceV2(session=session).evaluate(
            _input(
                datetime(2026, 3, 27, 10, 0, tzinfo=NY),
                [
                    (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                    (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 101.0),
                ],
            ),
            persist=True,
        )

        rows = session.execute(select(EventStudyResult).order_by(EventStudyResult.id)).scalars().all()
        assert len(rows) == 2
        assert rows[0].matching_method == "legacy_v1_loose_asof"
        assert "first_bar_at_or_after" in rows[1].matching_method


def test_batch_runner_evaluates_small_input_list_without_claiming_accuracy() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as session:
        runner = EventStudyBatchRunnerV2(session=session)
        summary = runner.evaluate_inputs(
            [
                _input(
                    datetime(2026, 3, 27, 10, 0, tzinfo=NY),
                    [
                        (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                        (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 101.0),
                    ],
                )
            ],
            persist=False,
        )

        assert summary.evaluated == 1
        assert summary.valid == 1
        assert summary.persisted == 0


def test_signal_v2_to_event_study_v2_linkage_computes_known_return() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as session:
        stored_signal = ResearchResultRepository(session).store_signal_run(
            instrument_id=1,
            experiment_id=11,
            generated_at=datetime(2026, 3, 27, 14, 0),
            engine_name="finsent_composite",
            engine_version="2.0",
            final_score=0.7,
            label="strong_bullish",
            confidence=0.8,
            signal_mode="NEWS_PLUS_MARKET",
        )
        record = EventStudyServiceV2(session=session).evaluate(
            EventStudyInputV2(
                instrument=AAPL,
                event_timestamp=datetime(2026, 3, 27, 10, 0, tzinfo=NY),
                price_bars=_bars(
                    [
                        (datetime(2026, 3, 27, 10, 0, tzinfo=NY), 100.0),
                        (datetime(2026, 3, 27, 11, 0, tzinfo=NY), 104.0),
                    ]
                ),
                horizons=[EventStudyHorizon.parse("1h")],
                signal_run_id=stored_signal.id,
                experiment_id=11,
            ),
            persist=True,
        )[0]

        assert record.result.signal_run_id == stored_signal.id
        assert record.result.raw_return == 0.040000000000000036


def test_unsupported_market_is_explicit() -> None:
    unknown = type(AAPL)(
        internal_id="x",
        ticker="X",
        display_name="X",
        exchange="MOON",
        provider_symbol="X",
        ui_label="X",
        sector="Test",
    )
    result = EventStudyEngineV2().evaluate(
        EventStudyInputV2(
            instrument=unknown,
            event_timestamp=datetime(2026, 3, 27, 10, 0),
            price_bars=_bars([(datetime(2026, 3, 27, 10, 0), 100.0)]),
            horizons=[EventStudyHorizon.parse("1h")],
        )
    )[0]

    assert result.status == EventStudyStatus.UNSUPPORTED_MARKET
