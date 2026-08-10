# Event Study V2

Phase 8 adds a strict, auditable event-study engine in `finsent/app/analysis/event_study_v2.py`.

## Methodology

Engine identity:

- `engine_name`: `finsent_event_study`
- `engine_version`: `2.0`

V2 measures realized price movement after an article/event timestamp using exchange-session-aware timing. It does not fetch provider data, optimize signals, calibrate confidence, or claim predictive accuracy.

## Event Timing

The original event timestamp is normalized to exchange-local time for session logic. Persisted output timestamps are returned as naive UTC, matching the existing database convention.

Effective event time:

- during market hours: article timestamp
- before market open: same session open
- after market close: next valid session open
- weekend/holiday: next valid session open

## Horizon Definitions

Supported horizons:

| Horizon | Meaning |
|---|---|
| `1H` | 60 trading minutes after entry |
| `4H` | 240 trading minutes after entry |
| `1D` | next trading session at the same local time, clamped to session hours |

Trading-time advancement crosses market closes, weekends, and known holidays.

## Entry Matching

Entry rule:

```text
first valid price bar at or after effective_event_timestamp
```

V2 never uses a bar before the event as entry. If no acceptable bar exists, the result status is `NO_ENTRY_BAR` or `OUT_OF_TOLERANCE`.

## Exit Matching

Exit rule:

```text
first valid price bar at or after target_timestamp
```

If the candidate exit bar exceeds the strict tolerance, the result is invalid and `raw_return` remains null.

## Tolerances

Tolerance is based on detected bar frequency:

- intraday bars: `max(2 * median_interval, 10 minutes)`, capped at `120` minutes for entry and `90` minutes for exit
- daily bars: `36` hours for session-date matching
- irregular/unknown bars: unsupported

## Granularity Rules

Daily bars cannot support true hourly event studies:

- daily + `1H`: `UNSUPPORTED_GRANULARITY`
- daily + `4H`: `UNSUPPORTED_GRANULARITY`
- daily + `1D`: supported as a trading-session-day return

No intraday interpolation is fabricated from daily close data.

## Return Formula

For valid matches:

```text
raw_return = (exit_price / entry_price) - 1
```

Returns are decimal values:

```text
0.025 = +2.5%
```

V2 also computes `log_return` in metadata, but simple raw return remains the main field.

## Result Statuses

- `VALID`
- `NO_ENTRY_BAR`
- `NO_EXIT_BAR`
- `OUT_OF_TOLERANCE`
- `UNSUPPORTED_GRANULARITY`
- `INVALID_PRICE`
- `INVALID_TIMESTAMP`
- `UNSUPPORTED_MARKET`
- `INSUFFICIENT_DATA`

Invalid results do not hide as zero returns.

## Match Quality

Match quality labels:

- `EXACT`: entry and exit match requested timestamps exactly
- `GOOD`: small delay within tolerance
- `DEGRADED`: valid but delayed or normalized with warnings
- `INVALID`: no valid measured return

Quality is interpretation metadata. It does not alter the return calculation.

## Storage

V2 persists through the existing Phase 5 `event_study_results` table. Existing columns store event time, horizon, target, matched exit timestamp, entry/exit prices, return, elapsed wall-clock minutes, status, matching method, and quality label. V2-specific audit fields are stored in `metadata_json`:

- engine name/version
- effective event timestamp
- entry timestamp
- match quality
- bar frequency
- tolerances and delays
- elapsed trading minutes
- provider/source metadata
- optional log return

No schema change is required.

## Limitations

- Holiday lists are compact built-ins for supported project markets, not exhaustive exchange calendars.
- No benchmark-adjusted or sector-relative return is calculated yet.
- No provider data is fetched inside the engine.
- No predictive-accuracy claim is made from small smoke runs.
