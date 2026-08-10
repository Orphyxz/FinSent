# Data Quality

Phase 4 introduces deterministic data-quality infrastructure. It does not change Signal Engine V1 scoring.

## Quality Dimensions

Market quote quality checks:

- provider availability
- finite positive price
- valid timestamp
- bid/ask validity when present
- nonnegative volume when present
- quote mode such as live snapshot, last trade, previous close, or cache
- freshness
- spread availability

Historical bar quality checks:

- timestamp validity
- chronological ordering
- duplicate timestamps
- finite positive OHLC values
- `high >= low`
- `high >= open/close`
- `low <= open/close`
- nonnegative volume
- sparse history

News quality checks:

- provider availability
- non-empty title
- usable source
- valid publication timestamp
- URL validity when present
- article count
- fallback depth
- leaf source mode such as provider-grade, search-derived, or scraped
- freshness

## Score Range

`DataQualityAssessment.score` is deterministic and bounded from `0.0` to `1.0`.

Labels:

- `HIGH`: score >= `0.80`
- `MEDIUM`: score >= `0.50`
- `LOW`: score > `0.0`
- `UNAVAILABLE`: score == `0.0`

## Quote Rules

Start at `1.0` only when quote validation passes.

Penalties:

- previous close: `-0.35`
- aging quote: `-0.15`
- stale quote: `-0.35`
- unknown quote freshness: `-0.20`
- spread unavailable: `-0.10`

Invalid quotes score `0.0`.

## Historical Bar Rules

Start at `1.0` only when bar validation passes.

Penalties:

- unknown freshness: `-0.20`
- fewer than two bars: `-0.15`

Invalid or empty bar frames score `0.0`.

## News Rules

Start at `1.0` only when at least one article validates.

Penalties:

- fallback provider used: `-0.15`
- scraped data mode: `-0.25`
- search-derived data mode: `-0.15`
- aging news: `-0.10`
- stale news: `-0.30`
- unknown freshness: `-0.20`
- fewer than three valid articles: `-0.10`

Malformed records are excluded.

## Freshness Labels

Freshness labels are:

- `FRESH`
- `AGING`
- `STALE`
- `UNKNOWN`

Quote defaults:

- fresh: <= `QUOTE_FRESH_SECONDS`
- aging: <= `QUOTE_AGING_SECONDS`
- stale: older than aging threshold

News defaults:

- fresh: <= `NEWS_FRESH_MINUTES`
- aging: <= `NEWS_AGING_MINUTES`
- stale: older than aging threshold

Previous-close quotes are treated as aging/stale rather than live.

## Important Distinctions

Data quality is not model confidence.

Data quality is not signal confidence.

Data quality is not a probability that a stock direction is correct.

It only describes whether provider inputs look trustworthy enough to use or display.

## Limitations

- No exchange-calendar/session awareness yet.
- No persistent data-quality history.
- No full provider-run database table.
- No statistical calibration against realized outcomes.
