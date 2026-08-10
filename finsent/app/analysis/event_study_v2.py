from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
import math
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from finsent.app.services.symbol_registry import SymbolRecord


ENGINE_NAME_EVENT_STUDY_V2 = "finsent_event_study"
ENGINE_VERSION_EVENT_STUDY_V2 = "2.0"


class EventStudyStatus(str, Enum):
    VALID = "VALID"
    NO_ENTRY_BAR = "NO_ENTRY_BAR"
    NO_EXIT_BAR = "NO_EXIT_BAR"
    OUT_OF_TOLERANCE = "OUT_OF_TOLERANCE"
    UNSUPPORTED_GRANULARITY = "UNSUPPORTED_GRANULARITY"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MatchQuality(str, Enum):
    EXACT = "EXACT"
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"


class BarFrequency(str, Enum):
    INTRADAY = "INTRADAY"
    DAILY = "DAILY"
    IRREGULAR = "IRREGULAR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EventStudyHorizon:
    label: str
    trading_minutes: int | None = None
    trading_days: int | None = None

    @property
    def horizon_minutes(self) -> int:
        if self.trading_minutes is not None:
            return self.trading_minutes
        if self.trading_days is not None:
            return self.trading_days * 1440
        return 0

    @classmethod
    def parse(cls, value: str) -> EventStudyHorizon:
        normalized = value.strip().lower()
        if normalized == "1h":
            return cls("1H", trading_minutes=60)
        if normalized == "4h":
            return cls("4H", trading_minutes=240)
        if normalized == "1d":
            return cls("1D", trading_days=1)
        raise ValueError(f"Unsupported event-study horizon: {value}")


@dataclass(frozen=True, slots=True)
class EventStudyInputV2:
    instrument: SymbolRecord
    event_timestamp: datetime
    price_bars: pd.DataFrame
    horizons: list[EventStudyHorizon] = field(default_factory=lambda: [EventStudyHorizon.parse("1h")])
    event_timezone: str | None = None
    bars_timezone: str | None = None
    article_id: int | None = None
    sentiment_run_id: int | None = None
    signal_run_id: int | None = None
    experiment_id: int | None = None
    provider: str | None = None
    source: str | None = None
    data_quality_label: str | None = None
    data_quality_score: float | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BarMatchResult:
    status: EventStudyStatus
    requested_timestamp: datetime | None
    matched_timestamp: datetime | None
    price: float | None
    delay_minutes: float | None
    tolerance_minutes: float | None
    matching_method: str
    quality: MatchQuality
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class EventStudyResultV2:
    engine_name: str
    engine_version: str
    instrument: SymbolRecord
    original_event_timestamp: datetime
    effective_event_timestamp: datetime | None
    entry_timestamp: datetime | None
    entry_price: float | None
    horizon: EventStudyHorizon
    target_timestamp: datetime | None
    matched_exit_timestamp: datetime | None
    exit_price: float | None
    elapsed_wall_clock_minutes: float | None
    elapsed_trading_minutes: float | None
    raw_return: float | None
    log_return: float | None
    status: EventStudyStatus
    matching_method: str
    match_quality: MatchQuality
    bar_frequency: BarFrequency
    quality_warnings: list[str]
    provider: str | None
    source: str | None
    data_quality_label: str | None
    data_quality_score: float | None
    created_at: datetime
    article_id: int | None = None
    sentiment_run_id: int | None = None
    signal_run_id: int | None = None
    experiment_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedBars:
    frame: pd.DataFrame
    frequency: BarFrequency
    median_interval_minutes: float | None
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class ExchangeCalendar:
    exchange: str
    timezone_name: str
    open_time: time
    close_time: time
    holidays: frozenset[date] = frozenset()

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def is_weekend(self, local_date: date) -> bool:
        return local_date.weekday() >= 5

    def is_holiday(self, local_date: date) -> bool:
        return local_date in self.holidays

    def is_session_day(self, local_date: date) -> bool:
        return not self.is_weekend(local_date) and not self.is_holiday(local_date)

    def session_open(self, local_date: date) -> datetime:
        return datetime.combine(local_date, self.open_time, self.tz)

    def session_close(self, local_date: date) -> datetime:
        return datetime.combine(local_date, self.close_time, self.tz)

    def is_inside_session(self, local_dt: datetime) -> bool:
        local_dt = local_dt.astimezone(self.tz)
        if not self.is_session_day(local_dt.date()):
            return False
        return self.session_open(local_dt.date()) <= local_dt <= self.session_close(local_dt.date())

    def next_session_open(self, local_dt: datetime) -> datetime:
        current = local_dt.astimezone(self.tz)
        for offset in range(370):
            candidate_date = current.date() + timedelta(days=offset)
            if not self.is_session_day(candidate_date):
                continue
            open_dt = self.session_open(candidate_date)
            close_dt = self.session_close(candidate_date)
            if current <= open_dt:
                return open_dt
            if open_dt <= current <= close_dt:
                return current
        raise ValueError(f"No future session found for {self.exchange}")

    def effective_event_time(self, local_dt: datetime) -> datetime:
        current = local_dt.astimezone(self.tz)
        if self.is_inside_session(current):
            return current
        if self.is_session_day(current.date()) and current < self.session_open(current.date()):
            return self.session_open(current.date())
        return self.next_session_open(current + timedelta(minutes=1))

    def advance_trading_minutes(self, start_local: datetime, minutes: int) -> datetime:
        remaining = timedelta(minutes=minutes)
        current = self.effective_event_time(start_local)
        while remaining > timedelta(0):
            close_dt = self.session_close(current.date())
            available = close_dt - current
            if remaining <= available:
                return current + remaining
            remaining -= available
            current = self.next_session_open(close_dt + timedelta(minutes=1))
        return current

    def advance_trading_days(self, start_local: datetime, days: int) -> datetime:
        current = self.effective_event_time(start_local)
        target_time = current.timetz().replace(tzinfo=None)
        seen = 0
        candidate_date = current.date()
        while seen < days:
            candidate_date += timedelta(days=1)
            if self.is_session_day(candidate_date):
                seen += 1
        open_dt = self.session_open(candidate_date)
        close_dt = self.session_close(candidate_date)
        target = datetime.combine(candidate_date, target_time, self.tz)
        if target < open_dt:
            return open_dt
        if target > close_dt:
            return close_dt
        return target

    def trading_minutes_between(self, start_local: datetime, end_local: datetime) -> float:
        start = self.effective_event_time(start_local)
        end = end_local.astimezone(self.tz)
        if end <= start:
            return 0.0
        total = timedelta(0)
        current = start
        while current < end:
            if not self.is_session_day(current.date()):
                current = self.next_session_open(current + timedelta(days=1))
                continue
            close_dt = self.session_close(current.date())
            if current < self.session_open(current.date()):
                current = self.session_open(current.date())
            segment_end = min(close_dt, end)
            if segment_end > current:
                total += segment_end - current
            if end <= close_dt:
                break
            current = self.next_session_open(close_dt + timedelta(minutes=1))
        return total.total_seconds() / 60.0


US_HOLIDAYS = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
    }
)

INDIA_HOLIDAYS = frozenset(
    {
        date(2026, 1, 26),
        date(2026, 3, 4),
        date(2026, 3, 27),
        date(2026, 4, 14),
        date(2026, 5, 1),
        date(2026, 8, 15),
        date(2026, 10, 2),
        date(2026, 11, 9),
        date(2026, 12, 25),
    }
)


def calendar_for_exchange(exchange: str) -> ExchangeCalendar | None:
    normalized = exchange.upper().strip()
    if normalized == "US":
        return ExchangeCalendar("US", "America/New_York", time(9, 30), time(16, 0), US_HOLIDAYS)
    if normalized in {"NSE", "BSE"}:
        return ExchangeCalendar(normalized, "Asia/Kolkata", time(9, 15), time(15, 30), INDIA_HOLIDAYS)
    return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _coerce_datetime(value: Any, *, timezone_name: str | None) -> datetime:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("timestamp is missing")
    dt = timestamp.to_pydatetime()
    if dt.tzinfo is not None:
        return dt
    if timezone_name:
        try:
            return dt.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {timezone_name}") from exc
    return dt.replace(tzinfo=timezone.utc)


def _price_column(frame: pd.DataFrame) -> str | None:
    for column in ("close", "Close", "adj_close", "Adj Close"):
        if column in frame.columns:
            return column
    return None


def normalize_bars(frame: pd.DataFrame, *, calendar: ExchangeCalendar, bars_timezone: str | None = None) -> NormalizedBars:
    warnings: list[str] = []
    if frame is None or frame.empty:
        return NormalizedBars(pd.DataFrame(columns=["timestamp_utc", "timestamp_local", "close"]), BarFrequency.UNKNOWN, None, ["No price bars were supplied."])
    price_column = _price_column(frame)
    if price_column is None:
        return NormalizedBars(pd.DataFrame(columns=["timestamp_utc", "timestamp_local", "close"]), BarFrequency.UNKNOWN, None, ["No close price column was supplied."])
    work = frame.copy()
    if "timestamp" in work.columns:
        timestamps = work["timestamp"]
    else:
        timestamps = work.index
    rows: list[dict[str, Any]] = []
    invalid_timestamps = 0
    invalid_prices = 0
    for raw_timestamp, raw_price in zip(timestamps, work[price_column], strict=False):
        try:
            aware = _coerce_datetime(raw_timestamp, timezone_name=bars_timezone)
        except ValueError:
            invalid_timestamps += 1
            continue
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            invalid_prices += 1
            continue
        if not math.isfinite(price) or price <= 0:
            invalid_prices += 1
            continue
        utc_ts = aware.astimezone(timezone.utc)
        rows.append({"timestamp_utc": utc_ts, "timestamp_local": utc_ts.astimezone(calendar.tz), "close": price})
    normalized = pd.DataFrame(rows)
    if normalized.empty:
        warnings.append("No valid timestamp/price bars remained after normalization.")
        return NormalizedBars(pd.DataFrame(columns=["timestamp_utc", "timestamp_local", "close"]), BarFrequency.UNKNOWN, None, warnings)
    before = len(normalized)
    normalized = normalized.sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc"], keep="last").reset_index(drop=True)
    if len(normalized) < before:
        warnings.append("Duplicate bar timestamps were collapsed.")
    if invalid_timestamps:
        warnings.append(f"{invalid_timestamps} bars had invalid timestamps.")
    if invalid_prices:
        warnings.append(f"{invalid_prices} bars had invalid prices.")
    frequency, median = detect_bar_frequency(normalized["timestamp_utc"].tolist(), normalized["timestamp_local"].tolist(), calendar)
    if frequency == BarFrequency.IRREGULAR:
        warnings.append("Bar timestamps are irregular; strict tolerance still applies.")
    return NormalizedBars(normalized, frequency, median, warnings)


def detect_bar_frequency(
    timestamps: list[datetime],
    local_timestamps: list[datetime] | None = None,
    calendar: ExchangeCalendar | None = None,
) -> tuple[BarFrequency, float | None]:
    if len(timestamps) < 2:
        return BarFrequency.UNKNOWN, None
    ordered = sorted(timestamps)
    deltas = [(ordered[index] - ordered[index - 1]).total_seconds() / 60.0 for index in range(1, len(ordered))]
    positive = [delta for delta in deltas if delta > 0]
    if not positive:
        return BarFrequency.UNKNOWN, None
    median = float(pd.Series(positive).median())
    if _looks_like_daily_bars(local_timestamps or [], calendar):
        return BarFrequency.DAILY, median
    if len(positive) > 1 and min(positive) <= 2 and max(positive) >= 120:
        return BarFrequency.IRREGULAR, median
    if min(positive) <= 6 * 60:
        return BarFrequency.INTRADAY, median
    if median >= 18 * 60:
        return BarFrequency.INTRADAY, median
    if median <= 6 * 60:
        short_deltas = [delta for delta in positive if delta <= max(median * 3, median + 15)]
        if len(short_deltas) < max(1, int(len(positive) * 0.6)):
            return BarFrequency.IRREGULAR, median
        return BarFrequency.INTRADAY, median
    return BarFrequency.IRREGULAR, median


def _looks_like_daily_bars(local_timestamps: list[datetime], calendar: ExchangeCalendar | None) -> bool:
    if len(local_timestamps) < 2 or calendar is None:
        return False
    local_dates = [timestamp.date() for timestamp in local_timestamps]
    if len(set(local_dates)) != len(local_dates):
        return False
    allowed_times = {time(0, 0), calendar.close_time}
    return all(timestamp.timetz().replace(tzinfo=None) in allowed_times for timestamp in local_timestamps)


def tolerance_minutes(frequency: BarFrequency, median_interval_minutes: float | None, *, match_type: str) -> float:
    if frequency == BarFrequency.DAILY:
        return 36 * 60
    if frequency == BarFrequency.INTRADAY and median_interval_minutes is not None:
        base = max(median_interval_minutes * 2, 10.0)
        return min(base, 120.0 if match_type == "entry" else 90.0)
    return 0.0


class EventStudyEngineV2:
    def evaluate(self, study_input: EventStudyInputV2) -> list[EventStudyResultV2]:
        calendar = calendar_for_exchange(study_input.instrument.exchange)
        if calendar is None:
            return [self._invalid_result(study_input, horizon, EventStudyStatus.UNSUPPORTED_MARKET, "Unsupported market/exchange.") for horizon in study_input.horizons]
        try:
            event_aware = _coerce_datetime(study_input.event_timestamp, timezone_name=study_input.event_timezone)
        except ValueError as exc:
            return [self._invalid_result(study_input, horizon, EventStudyStatus.INVALID_TIMESTAMP, str(exc)) for horizon in study_input.horizons]
        event_local = event_aware.astimezone(calendar.tz)
        effective_local = calendar.effective_event_time(event_local)
        bars = normalize_bars(study_input.price_bars, calendar=calendar, bars_timezone=study_input.bars_timezone)
        if len(bars.frame) < 2:
            return [
                self._invalid_result(
                    study_input,
                    horizon,
                    EventStudyStatus.INSUFFICIENT_DATA,
                    "; ".join(bars.warnings) or "No usable price bars.",
                    effective_local=effective_local,
                    bar_frequency=bars.frequency,
                    warnings=bars.warnings,
                )
                for horizon in study_input.horizons
            ]
        return [self._evaluate_horizon(study_input, calendar, event_aware, effective_local, bars, horizon) for horizon in study_input.horizons]

    def _evaluate_horizon(
        self,
        study_input: EventStudyInputV2,
        calendar: ExchangeCalendar,
        event_aware: datetime,
        effective_local: datetime,
        bars: NormalizedBars,
        horizon: EventStudyHorizon,
    ) -> EventStudyResultV2:
        if bars.frequency == BarFrequency.DAILY and horizon.trading_minutes is not None:
            return self._invalid_result(
                study_input,
                horizon,
                EventStudyStatus.UNSUPPORTED_GRANULARITY,
                "Daily bars cannot support intraday 1H/4H event-study horizons.",
                effective_local=effective_local,
                bar_frequency=bars.frequency,
                warnings=bars.warnings,
            )
        if bars.frequency in {BarFrequency.UNKNOWN, BarFrequency.IRREGULAR}:
            return self._invalid_result(
                study_input,
                horizon,
                EventStudyStatus.UNSUPPORTED_GRANULARITY,
                "Bar frequency is unknown or irregular.",
                effective_local=effective_local,
                bar_frequency=bars.frequency,
                warnings=bars.warnings,
            )
        if bars.frequency == BarFrequency.DAILY:
            return self._evaluate_daily_horizon(study_input, calendar, effective_local, bars, horizon)
        entry = self._match_bar_at_or_after(
            bars,
            effective_local.astimezone(timezone.utc),
            tolerance_minutes(bars.frequency, bars.median_interval_minutes, match_type="entry"),
            match_type="entry",
        )
        if entry.status != EventStudyStatus.VALID:
            return self._from_failed_match(study_input, horizon, effective_local, None, entry, None, bars)
        assert entry.matched_timestamp is not None
        entry_local = entry.matched_timestamp.astimezone(calendar.tz)
        if horizon.trading_minutes is not None:
            target_local = calendar.advance_trading_minutes(entry_local, horizon.trading_minutes)
        else:
            target_local = calendar.advance_trading_days(entry_local, horizon.trading_days or 1)
        exit_match = self._match_bar_at_or_after(
            bars,
            target_local.astimezone(timezone.utc),
            tolerance_minutes(bars.frequency, bars.median_interval_minutes, match_type="exit"),
            match_type="exit",
        )
        if exit_match.status != EventStudyStatus.VALID:
            return self._from_failed_match(study_input, horizon, effective_local, target_local, entry, exit_match, bars)
        return self._valid_result(study_input, calendar, event_aware, effective_local, target_local, entry, exit_match, bars, horizon)

    def _evaluate_daily_horizon(
        self,
        study_input: EventStudyInputV2,
        calendar: ExchangeCalendar,
        effective_local: datetime,
        bars: NormalizedBars,
        horizon: EventStudyHorizon,
    ) -> EventStudyResultV2:
        if horizon.trading_days is None:
            return self._invalid_result(study_input, horizon, EventStudyStatus.UNSUPPORTED_GRANULARITY, "Daily bars only support trading-day horizons.", effective_local=effective_local, bar_frequency=bars.frequency, warnings=bars.warnings)
        frame = bars.frame.copy()
        frame["trading_date"] = frame["timestamp_local"].apply(lambda item: item.date())
        entry_date = effective_local.date()
        entry_rows = frame[frame["trading_date"] >= entry_date]
        if entry_rows.empty:
            match = BarMatchResult(EventStudyStatus.NO_ENTRY_BAR, effective_local.astimezone(timezone.utc), None, None, None, tolerance_minutes(bars.frequency, bars.median_interval_minutes, match_type="entry"), "daily_session_date", MatchQuality.INVALID, "No daily entry bar on or after effective event date.")
            return self._from_failed_match(study_input, horizon, effective_local, None, match, None, bars)
        entry_row = entry_rows.iloc[0]
        target_local = calendar.advance_trading_days(entry_row["timestamp_local"], horizon.trading_days)
        target_date = target_local.date()
        exit_rows = frame[frame["trading_date"] >= target_date]
        entry = BarMatchResult(EventStudyStatus.VALID, effective_local.astimezone(timezone.utc), entry_row["timestamp_utc"], float(entry_row["close"]), 0.0, tolerance_minutes(bars.frequency, bars.median_interval_minutes, match_type="entry"), "daily_session_date", MatchQuality.GOOD)
        if exit_rows.empty:
            exit_match = BarMatchResult(EventStudyStatus.NO_EXIT_BAR, target_local.astimezone(timezone.utc), None, None, None, tolerance_minutes(bars.frequency, bars.median_interval_minutes, match_type="exit"), "daily_session_date", MatchQuality.INVALID, "No daily exit bar on or after target trading date.")
            return self._from_failed_match(study_input, horizon, effective_local, target_local, entry, exit_match, bars)
        exit_row = exit_rows.iloc[0]
        exit_match = BarMatchResult(EventStudyStatus.VALID, target_local.astimezone(timezone.utc), exit_row["timestamp_utc"], float(exit_row["close"]), 0.0, tolerance_minutes(bars.frequency, bars.median_interval_minutes, match_type="exit"), "daily_session_date", MatchQuality.GOOD)
        try:
            event_aware = _coerce_datetime(study_input.event_timestamp, timezone_name=study_input.event_timezone)
        except ValueError:
            event_aware = study_input.event_timestamp
        return self._valid_result(study_input, calendar, event_aware, effective_local, target_local, entry, exit_match, bars, horizon)

    def _match_bar_at_or_after(
        self,
        bars: NormalizedBars,
        requested_utc: datetime,
        tolerance: float,
        *,
        match_type: str,
    ) -> BarMatchResult:
        frame = bars.frame
        candidates = frame[frame["timestamp_utc"] >= requested_utc].copy()
        method = f"first_bar_at_or_after_{match_type}"
        if candidates.empty:
            status = EventStudyStatus.NO_ENTRY_BAR if match_type == "entry" else EventStudyStatus.NO_EXIT_BAR
            return BarMatchResult(status, requested_utc, None, None, None, tolerance, method, MatchQuality.INVALID, f"No {match_type} bar at or after requested timestamp.")
        row = candidates.iloc[0]
        matched = row["timestamp_utc"]
        delay = (matched - requested_utc).total_seconds() / 60.0
        if delay > tolerance:
            return BarMatchResult(EventStudyStatus.OUT_OF_TOLERANCE, requested_utc, matched, None, delay, tolerance, method, MatchQuality.INVALID, f"{match_type.title()} bar delay exceeded tolerance.")
        price = float(row["close"])
        quality = self._match_quality(delay, tolerance)
        return BarMatchResult(EventStudyStatus.VALID, requested_utc, matched, price, delay, tolerance, method, quality)

    @staticmethod
    def _match_quality(delay: float, tolerance: float) -> MatchQuality:
        if delay <= 1e-9:
            return MatchQuality.EXACT
        if delay <= max(1.0, tolerance / 2):
            return MatchQuality.GOOD
        return MatchQuality.DEGRADED

    def _valid_result(
        self,
        study_input: EventStudyInputV2,
        calendar: ExchangeCalendar,
        event_aware: datetime,
        effective_local: datetime,
        target_local: datetime,
        entry: BarMatchResult,
        exit_match: BarMatchResult,
        bars: NormalizedBars,
        horizon: EventStudyHorizon,
    ) -> EventStudyResultV2:
        if entry.price is None or exit_match.price is None or entry.price <= 0 or exit_match.price <= 0:
            return self._from_failed_match(study_input, horizon, effective_local, target_local, entry, exit_match, bars, status=EventStudyStatus.INVALID_PRICE, reason="Entry or exit price was invalid.")
        assert entry.matched_timestamp is not None and exit_match.matched_timestamp is not None
        raw_return = (exit_match.price / entry.price) - 1.0
        log_return = math.log(exit_match.price / entry.price)
        elapsed_wall = (exit_match.matched_timestamp - entry.matched_timestamp).total_seconds() / 60.0
        elapsed_trading = calendar.trading_minutes_between(entry.matched_timestamp.astimezone(calendar.tz), exit_match.matched_timestamp.astimezone(calendar.tz))
        return EventStudyResultV2(
            engine_name=ENGINE_NAME_EVENT_STUDY_V2,
            engine_version=ENGINE_VERSION_EVENT_STUDY_V2,
            instrument=study_input.instrument,
            original_event_timestamp=to_naive_utc(event_aware) or study_input.event_timestamp,
            effective_event_timestamp=to_naive_utc(effective_local),
            entry_timestamp=to_naive_utc(entry.matched_timestamp),
            entry_price=entry.price,
            horizon=horizon,
            target_timestamp=to_naive_utc(target_local),
            matched_exit_timestamp=to_naive_utc(exit_match.matched_timestamp),
            exit_price=exit_match.price,
            elapsed_wall_clock_minutes=elapsed_wall,
            elapsed_trading_minutes=elapsed_trading,
            raw_return=raw_return,
            log_return=log_return,
            status=EventStudyStatus.VALID,
            matching_method=f"{entry.matching_method}+{exit_match.matching_method}",
            match_quality=self._combined_quality(entry.quality, exit_match.quality, bars.warnings),
            bar_frequency=bars.frequency,
            quality_warnings=bars.warnings,
            provider=study_input.provider,
            source=study_input.source,
            data_quality_label=study_input.data_quality_label,
            data_quality_score=study_input.data_quality_score,
            created_at=utc_now(),
            article_id=study_input.article_id,
            sentiment_run_id=study_input.sentiment_run_id,
            signal_run_id=study_input.signal_run_id,
            experiment_id=study_input.experiment_id,
            metadata=self._metadata(study_input, entry, exit_match, bars),
        )

    def _from_failed_match(
        self,
        study_input: EventStudyInputV2,
        horizon: EventStudyHorizon,
        effective_local: datetime,
        target_local: datetime | None,
        entry: BarMatchResult,
        exit_match: BarMatchResult | None,
        bars: NormalizedBars,
        *,
        status: EventStudyStatus | None = None,
        reason: str | None = None,
    ) -> EventStudyResultV2:
        selected_status = status or (exit_match.status if exit_match is not None else entry.status)
        selected_reason = reason or (exit_match.reason if exit_match is not None else entry.reason)
        return EventStudyResultV2(
            engine_name=ENGINE_NAME_EVENT_STUDY_V2,
            engine_version=ENGINE_VERSION_EVENT_STUDY_V2,
            instrument=study_input.instrument,
            original_event_timestamp=self._original_event_timestamp(study_input),
            effective_event_timestamp=to_naive_utc(effective_local),
            entry_timestamp=to_naive_utc(entry.matched_timestamp),
            entry_price=entry.price,
            horizon=horizon,
            target_timestamp=to_naive_utc(target_local),
            matched_exit_timestamp=to_naive_utc(exit_match.matched_timestamp) if exit_match else None,
            exit_price=None,
            elapsed_wall_clock_minutes=None,
            elapsed_trading_minutes=None,
            raw_return=None,
            log_return=None,
            status=selected_status,
            matching_method=entry.matching_method if exit_match is None else f"{entry.matching_method}+{exit_match.matching_method}",
            match_quality=MatchQuality.INVALID,
            bar_frequency=bars.frequency,
            quality_warnings=bars.warnings + ([selected_reason] if selected_reason else []),
            provider=study_input.provider,
            source=study_input.source,
            data_quality_label=study_input.data_quality_label,
            data_quality_score=study_input.data_quality_score,
            created_at=utc_now(),
            article_id=study_input.article_id,
            sentiment_run_id=study_input.sentiment_run_id,
            signal_run_id=study_input.signal_run_id,
            experiment_id=study_input.experiment_id,
            metadata=self._metadata(study_input, entry, exit_match, bars),
        )

    def _invalid_result(
        self,
        study_input: EventStudyInputV2,
        horizon: EventStudyHorizon,
        status: EventStudyStatus,
        reason: str,
        *,
        effective_local: datetime | None = None,
        bar_frequency: BarFrequency = BarFrequency.UNKNOWN,
        warnings: list[str] | None = None,
    ) -> EventStudyResultV2:
        return EventStudyResultV2(
            engine_name=ENGINE_NAME_EVENT_STUDY_V2,
            engine_version=ENGINE_VERSION_EVENT_STUDY_V2,
            instrument=study_input.instrument,
            original_event_timestamp=self._original_event_timestamp(study_input),
            effective_event_timestamp=to_naive_utc(effective_local),
            entry_timestamp=None,
            entry_price=None,
            horizon=horizon,
            target_timestamp=None,
            matched_exit_timestamp=None,
            exit_price=None,
            elapsed_wall_clock_minutes=None,
            elapsed_trading_minutes=None,
            raw_return=None,
            log_return=None,
            status=status,
            matching_method="event_study_v2",
            match_quality=MatchQuality.INVALID,
            bar_frequency=bar_frequency,
            quality_warnings=(warnings or []) + [reason],
            provider=study_input.provider,
            source=study_input.source,
            data_quality_label=study_input.data_quality_label,
            data_quality_score=study_input.data_quality_score,
            created_at=utc_now(),
            article_id=study_input.article_id,
            sentiment_run_id=study_input.sentiment_run_id,
            signal_run_id=study_input.signal_run_id,
            experiment_id=study_input.experiment_id,
            metadata={"engine_name": ENGINE_NAME_EVENT_STUDY_V2, "engine_version": ENGINE_VERSION_EVENT_STUDY_V2, "reason": reason},
        )

    @staticmethod
    def _original_event_timestamp(study_input: EventStudyInputV2) -> datetime:
        try:
            event_aware = _coerce_datetime(study_input.event_timestamp, timezone_name=study_input.event_timezone)
        except ValueError:
            return study_input.event_timestamp
        return to_naive_utc(event_aware) or study_input.event_timestamp

    @staticmethod
    def _combined_quality(entry_quality: MatchQuality, exit_quality: MatchQuality, warnings: list[str]) -> MatchQuality:
        if warnings:
            return MatchQuality.DEGRADED
        if MatchQuality.DEGRADED in {entry_quality, exit_quality}:
            return MatchQuality.DEGRADED
        if MatchQuality.GOOD in {entry_quality, exit_quality}:
            return MatchQuality.GOOD
        return MatchQuality.EXACT

    @staticmethod
    def _metadata(
        study_input: EventStudyInputV2,
        entry: BarMatchResult,
        exit_match: BarMatchResult | None,
        bars: NormalizedBars,
    ) -> dict[str, Any]:
        return {
            "engine_name": ENGINE_NAME_EVENT_STUDY_V2,
            "engine_version": ENGINE_VERSION_EVENT_STUDY_V2,
            "entry_delay_minutes": entry.delay_minutes,
            "entry_tolerance_minutes": entry.tolerance_minutes,
            "exit_delay_minutes": exit_match.delay_minutes if exit_match else None,
            "exit_tolerance_minutes": exit_match.tolerance_minutes if exit_match else None,
            "bar_frequency": bars.frequency.value,
            "median_interval_minutes": bars.median_interval_minutes,
            "provider_metadata": study_input.provider_metadata,
        }
