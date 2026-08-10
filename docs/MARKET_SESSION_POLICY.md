# Market Session Policy

Event Study V2 uses exchange-local market sessions for timing, then converts persisted/output timestamps back to naive UTC.

## Supported Markets

| Market | Timezone | Regular Session |
|---|---|---|
| US | `America/New_York` | 09:30-16:00 |
| NSE | `Asia/Kolkata` | 09:15-15:30 |
| BSE | `Asia/Kolkata` | 09:15-15:30 |

NSE and BSE share the same regular-session abstraction in Phase 8.

## Timestamp Policy

- Existing persisted naive datetimes are treated as canonical UTC.
- Timezone-aware datetimes are converted to the instrument exchange timezone.
- Synthetic/source-local naive datetimes can pass an explicit event/bar timezone.
- Unknown timezone names produce `INVALID_TIMESTAMP`.

This avoids silently inventing exchange-local meaning for unknown naive timestamps.

## Event Effective Time

During session:

```text
effective_event_timestamp = article timestamp
```

Before open:

```text
effective_event_timestamp = same-day market open
```

After close:

```text
effective_event_timestamp = next valid session open
```

Weekend or holiday:

```text
effective_event_timestamp = next valid session open
```

V2 does not use a previous close as entry for after-hours events.

## Holidays

Phase 8 includes compact known 2026 holiday sets for US and India market-session tests. This is sufficient for deterministic local validation, but it is not a replacement for a full exchange-calendar dependency.

## Trading-Time Advancement

`1H` and `4H` advance by trading minutes. If a target crosses a close, remaining minutes continue at the next valid session open.

`1D` advances to the next trading session at the same local time, clamped inside regular session hours.
