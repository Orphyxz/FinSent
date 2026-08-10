# Event Study V1 Reference

This document preserves the legacy market-impact matcher for comparison. V1 remains callable through `finsent/app/analysis/market_impact.py`.

## Current V1 Behavior

`align_news_with_prices` accepts a news DataFrame, a price DataFrame, and a return window in minutes.

The V1 path:

- reads article time from `news_df["published_at"]`
- reads bar time from `price_df["timestamp"]`
- converts both with `pandas.to_datetime`
- sorts prices by timestamp
- uses `pandas.merge_asof` for entry matching
- uses another `merge_asof` for future-price matching

## Matching Rules

Entry price:

```text
nearest prior bar at or before published_at
tolerance = 2 calendar days
```

Exit price:

```text
first bar at or after entry_timestamp + return_window_minutes
tolerance = max(return_window_minutes, 2 calendar days)
```

Return:

```text
forward_return = (future_close - entry_close) / entry_close
```

## Known Defects

V1 is loose and not market-session-aware:

- Weekend articles can use a Friday price as entry.
- After-close articles can be labeled as a next-session 60-minute return without an explicit effective-time policy.
- A far-late future bar can satisfy a short horizon because the tolerance can be two calendar days.
- Timezone semantics are inherited from pandas conversion and are not exchange-aware.
- Daily and intraday bars are not distinguished.
- No match-quality status is returned; invalid matches are often dropped silently.

## Original Defect Cases

Phase 2 froze three known xfail cases:

- weekend entry matching
- after-close next-session matching
- far-late future bar matching

Phase 8 replaces those xfails with passing Event Study V2 tests. V1 is kept only as legacy/reference behavior for dashboard compatibility and historical comparison.
