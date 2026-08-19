# Catalyst Intelligence

## Purpose

Catalyst Intelligence adds an application-level explanation layer on top of the current FinSent news feed. It classifies already-fetched headlines into understandable market-event categories so a user can see what kind of news is driving the dashboard.

Catalyst Intelligence is an application-level explanatory intelligence feature. Phase 18 does not establish that catalyst classifications improve predictive performance, and the locked Phase 16 evaluation was not modified.

## Taxonomy

The deterministic taxonomy is:

- EARNINGS
- GUIDANCE
- M_AND_A
- REGULATION
- LITIGATION
- PRODUCT
- PARTNERSHIP
- ANALYST_RATING
- MANAGEMENT
- LAYOFFS
- FINANCING
- MACRO
- OTHER
- UNKNOWN

## Classification

The classifier lives in `finsent/app/services/catalyst_intelligence.py`. It uses deterministic keyword and phrase profiles over local article title and summary text. It can also use an already-stored catalyst tag as a fallback when text does not match a stronger rule.

No new provider request is made by Catalyst Intelligence. The dashboard reuses the news records that have already been fetched or loaded from the local SQLite database.

## Direction

Catalyst direction is separate from FinBERT sentiment. Supported values are:

- BULLISH
- BEARISH
- MIXED
- NEUTRAL
- UNKNOWN

Direction is inferred from event language such as beats, raises guidance, downgrade, lawsuit, investigation, approval, or mixed positive/negative phrases. If the article does not contain a specific catalyst, the direction remains UNKNOWN even if a sentiment label exists.

## Impact

Impact is a materiality score from 0.0 to 1.0. It is not a return forecast.

Labels are:

- LOW
- MEDIUM
- HIGH
- VERY_HIGH

The score combines catalyst family, materiality phrases, relevance, direction strength, and available model confidence.

## Horizon

Time horizon describes the expected explanation window, not a prediction guarantee.

Supported values are:

- INTRADAY
- SHORT_TERM
- MULTI_DAY
- MEDIUM_TERM
- UNKNOWN

## Novelty

Similar events are grouped deterministically. The first article in a group is NEW, later articles inside a short window are REPEATED, and later continuing coverage is ONGOING.

## Recency

Recency is computed from article publication time. Fresh articles receive higher priority; older articles decay. Freshness labels are FRESH, RECENT, AGING, STALE, and UNKNOWN.

## Event Grouping

Event group IDs are deterministic hashes built from symbol, catalyst type, direction, date, and event-signature tokens. Analyst rating events include rating-action and firm-like tokens so unrelated analyst calls do not collapse into the same group.

## Persistence And Cache

Phase 18 does not introduce a database schema migration. Catalyst fields are computed in the dashboard view model and cached in memory by the classifier service during the app process.

## UI Integration

The dashboard exposes Catalyst Intelligence in:

- Overview: Active Catalysts across the current workspace.
- Stock Research: Catalyst Summary, Key Catalysts, Event Timeline, and added Why This Signal context.
- News Intelligence: catalyst type, direction, impact, horizon, novelty, and event group fields in the headline table, plus symbol/type/direction filters.
- Compare: strongest recent catalyst and event-group count per compared symbol.

## Limitations

The current implementation is deterministic and intentionally conservative. It does not fabricate catalyst labels when no matching evidence exists. Gemini or other LLM classification is not required for Phase 18 and is not part of the default path.

These classifications improve dashboard explainability only. They are not used to retune Signal V1, Signal V2, or the Phase 16 final holdout.
