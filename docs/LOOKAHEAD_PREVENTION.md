# Lookahead Prevention

Phase 10 defines the historical evaluation boundary around each article timestamp `T0`.

## Inputs Allowed At T0

Signal generation may use:

- the target article and earlier stored articles with `published_at <= T0`
- stored sentiment fields that were already attached to those articles
- price bars with `timestamp <= T0`
- static instrument metadata

## Inputs Not Allowed At T0

Signal generation must not use:

- articles published after `T0`
- prices after `T0`
- realized event-study returns
- future model outputs
- benchmark or outcome fields generated after signal evaluation

## Outcome Layer

Event Study V2 consumes future bars only after the signal has been generated. Its role is realized outcome measurement, not signal input construction.

## V1 Note

Signal V1 itself remains frozen. The Phase 10 evaluator controls its article set so future articles cannot leak into V1. V1's internal recency behavior is not refactored in this phase.

## Tests

Phase 10 regression tests include an adversarial future article and future price spike. The evaluator must exclude both from V2 signal inputs while still allowing Event Study V2 to use future bars for outcomes.
