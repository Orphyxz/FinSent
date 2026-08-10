# FinSent Local Development Changelog

Git synchronization is intentionally deferred until explicit authorization. No commits, pushes, pulls, branches, remotes, pull requests, or Git history operations should be performed during local Phase 0 work.

## Phase 0 - Forensic Baseline Audit

- Created project-local Python virtual environment: `.venv`.
- Installed pinned runtime dependencies from `requirements.txt`.
- Installed missing pinned dashboard dependency `dash-bootstrap-components==1.6.0` after full requirements installation timed out twice but left most packages installed.
- Installed `pytest` in `.venv` to run the existing test suite because it is not declared in `requirements.txt`.
- Initialized/opened local SQLite database at `data/finsent.db`.
- Ran package consistency check with `pip check`.
- Ran Python compilation check for `finsent` and `scripts`.
- Ran major import smoke checks.
- Ran existing tests: 10 passed, 14 warnings.
- Ran Dash startup smoke through Flask test client: HTTP 200 for `/`.
- Created `docs/V2_BASELINE_AUDIT.md`.
- Created `docs/LOCAL_CHANGELOG.md`.
- Generated ignored local cache artifacts during checks: `.pytest_cache` and `__pycache__` folders. A recursive cleanup command was blocked by execution policy, so they remain local ignored artifacts.

## Phase 1 - Development Foundation

- Re-ran the accepted baseline before modifications: Python 3.13.13, compile pass, `pip check` pass, major imports pass, DB init pass, dashboard smoke HTTP 200, pipeline import pass, and 10 tests passing.
- Split dependencies into `requirements.txt`, `requirements-dev.txt`, `requirements-research.txt`, and `requirements-presentation.txt`.
- Moved heavy FinBERT/transformer dependencies to the research requirements file while keeping FinBERT code intact.
- Added `.env.example` with safe placeholder values only.
- Updated `.gitignore` so `.env` remains ignored while `.env.example` is available for future source control.
- Added standard-library logging setup in `finsent/app/utils/logging.py`.
- Wired logging into dashboard and pipeline entry points.
- Replaced the silent broad exception in `ensure_live_data` with a warning log that preserves graceful degraded operation.
- Added Git LFS pointer detection for the US price CSV importer.
- Converted presentation script paths from personal absolute paths to project-relative defaults and CLI inputs.
- Added `docs/ACTIVE_ARCHITECTURE.md`.
- Added `docs/KNOWN_CORRECTNESS_ISSUES.md`.
- Added `docs/DEVELOPMENT.md`.
- Updated `README.md` to describe the current active architecture and setup workflow.
- Remaining known issues are documented in `docs/KNOWN_CORRECTNESS_ISSUES.md`; no algorithmic fixes, UI redesign, provider rewrite, or Git operations were performed.

## Phase 2 - Correctness and Trust Layer

- Re-ran the accepted Phase 1 baseline before modifications: Python 3.13.13, compile pass, `pip check` pass, DB init/open pass, dashboard smoke HTTP 200, pipeline import pass, and 15 tests passing.
- Verified the key Phase 0/1 correctness findings directly against current code.
- Confirmed and fixed article-limit propagation: `FinSentPipeline.run(limit=N)` and dashboard `ensure_live_data(..., limit=N)` now pass the validated limit into `IntelligenceService.run(..., news_limit=N)`.
- Added safe news-limit validation: `None` uses the default, `0` is preserved as caller intent, negative values raise `ValueError`, and large values clamp to `50`.
- Introduced `ProviderStatus` and `DataSourceState` for explicit `AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `UNCONFIGURED`, and `STALE` provider diagnostics.
- Added missing-credential diagnostics for Polygon, Kite, Marketaux, Gemini, and OpenAI stub selection without making optional integrations mandatory.
- Fixed unavailable quote semantics: Signal V1 now requires a positive price, timestamp, acceptable quote quality, and non-unavailable provider status before market/quote data counts as usable.
- Replaced misleading Signal V1 mode labels with `News + Quote Quality`, `Quote-quality fallback`, `News-only signal`, and `Unavailable`.
- Updated dashboard wording around market blending, confidence, liquidity, volume context, and trading-style advice so the UI reflects current behavior.
- Added conservative article dedupe normalization for title/source/time bucket plus tracking-parameter-stripped URL, and changed repository upsert to check `dedupe_hash` before URL.
- Added `docs/CONFIDENCE_SEMANTICS.md`.
- Added `docs/SIGNAL_ENGINE_V1_REFERENCE.md`.
- Updated `docs/KNOWN_CORRECTNESS_ISSUES.md` with fixed/refined issues and remaining known defects.
- Updated `docs/ACTIVE_ARCHITECTURE.md` for Phase 2 provider status and Signal V1 boundaries.
- Added provider-status, quote-usability, article-limit, dedupe, Signal V1, and event-study regression tests.
- Added 3 intentional event-study xfail tests for confirmed Phase 1 defects:
  - weekend article using a Friday entry price,
  - after-close article using a later session as a 60-minute return,
  - future bar much later than the requested horizon.
- Final test result after Phase 2 code changes: 40 passed, 3 xfailed, 0 failed.
- Remaining correctness issues: loose event-study matching, uncalibrated confidence, no real market momentum/volume model in Signal V1, US historical CSV pointer, and incomplete provider architecture consolidation.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 3 - Provider Architecture Consolidation

- Re-ran the accepted Phase 2 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, and 40 passed / 3 xfailed / 0 failed tests.
- Added provider contracts and typed routing primitives in `finsent/app/services/provider_contracts.py`.
- Added `ProviderResult`, `ProviderAttempt`, and `ProviderFailureCategory`.
- Added classified provider failure categories for unconfigured, authentication, rate limit, timeout, network, invalid response, no data, stale data, unsupported symbol, and unknown failures.
- Added consolidated routers in `finsent/app/services/provider_routers.py`.
- Migrated `IntelligenceService` to consume `MarketDataRouter` and `NewsProviderRouter` instead of selecting providers directly.
- Preserved Signal Engine V1 numerical behavior and event-study behavior.
- Preserved Phase 2 article-limit propagation, provider status semantics, quote usability semantics, and dedupe behavior.
- Defined deterministic active market chains:
  - US market quote/bars: Polygon -> structured unavailable.
  - NSE/BSE market quote/bars: Kite -> structured unavailable.
- Defined deterministic active news chains:
  - US news: Polygon -> fallback web -> structured unavailable.
  - NSE/BSE news: Marketaux -> fallback web -> structured unavailable.
- Kept fallback web internals as Gemini search, Alpaca news, yfinance news, then Yahoo HTML scraping.
- Kept legacy Alpaca/yfinance market service out of the active router and documented it as legacy.
- Added lightweight in-memory provider attempt traces to `IntelligenceSnapshot.provider_attempts`.
- Added `docs/PROVIDER_ARCHITECTURE.md` with contracts, domain models, routing diagrams, fallback semantics, freshness/cache notes, provenance, current active providers, legacy providers, and new-provider instructions.
- Updated `docs/ACTIVE_ARCHITECTURE.md` and `README.md` to point to the canonical provider router path.
- Added Phase 3 provider router tests covering primary success, unconfigured primary, primary failure, fallback success, all-fail unavailable result, unsupported market, unusable quote, US/NSE/BSE routing, news fallback, failure classification, and local historical-data policy.
- Remaining provider limitations: no persistent provider-run table, no raw response audit, limited UI surfacing of attempt traces, no broad provider cache layer, and no activation of legacy yfinance/Alpaca market fallback in the active router.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 4 - Provider Reliability and Data Quality

- Re-ran the accepted Phase 3 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, and 54 passed / 3 xfailed / 0 failed tests.
- Audited active network calls across Polygon, Kite, Marketaux, Gemini search fallback, Alpaca news fallback, yfinance news fallback, and Yahoo HTML fallback.
- Added provider reliability infrastructure in `finsent/app/services/provider_reliability.py`.
- Added `DataMode`, `FreshnessLabel`, `DataQualityLabel`, and `DataQualityAssessment`.
- Added deterministic validators for quote snapshots, OHLCV bars, and normalized news articles.
- Added bounded retry helper for transient timeout/network/5xx-style failures only.
- Preserved no-retry behavior for unconfigured providers, authentication failures, permanent 4xx responses, invalid responses, unsupported symbols, and no-data cases.
- Added rate-limit classification with safe `Retry-After` parsing.
- Added in-memory TTL cache for routed quotes, news, and historical bars.
- Added explicit stale-cache fallback; stale cache returns `STALE` and `from_cache=True`, never fresh live status.
- Added current-session `ProviderHealthRegistry`.
- Added leaf-provider provenance for fallback web news:
  - `gemini_search`
  - `alpaca_news`
  - `yfinance_news`
  - `yahoo_html`
- Added Polygon quote-mode provenance through leaf provider labels:
  - `polygon/snapshot`
  - `polygon/last_trade`
  - `polygon/previous_close`
- Added compact dashboard status pills for quote mode and data-quality label.
- Created `docs/DATA_QUALITY.md`.
- Created `docs/PROVIDER_RELIABILITY.md`.
- Created `docs/PROVIDER_FALLBACK_DECISIONS.md`.
- Updated provider architecture, active architecture, known-issues, and README documentation.
- Added Phase 4 tests for retry, rate-limit classification, leaf provenance, Polygon quote modes, validation, freshness, cache hit/expiration, stale-cache fallback, data quality, provider health, and Signal V1 quote-usability preservation.
- Final test result after Phase 4 code changes: 71 passed, 3 xfailed, 0 failed.
- Signal Engine V1 formulas were not changed.
- The 3 event-study xfails remain intentionally unresolved.
- Remaining limitations: no persistent provider-run table, no raw response audit, provider health is process-local, no exchange-calendar freshness model, and legacy yfinance/Alpaca market fallbacks remain deferred.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 5 - Database and Research Storage V2

- Re-ran the accepted Phase 4 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, and 71 passed / 3 xfailed / 0 failed tests.
- Added schema version `2` in `schema_metadata`.
- Added additive SQLite migration support in `finsent/app/database/base.py`.
- Created a filesystem backup before migrating the local runtime DB: `data/finsent.phase5-pre-migration.20260809171335.db`.
- Added canonical instrument storage in `instruments`.
- Added article-instrument relationship storage in `article_instruments`.
- Added experiment grouping in `experiment_runs`.
- Added immutable future model-output storage in `sentiment_analysis_runs`.
- Added future-compatible signal-output storage in `signal_runs`.
- Added event-study result storage in `event_study_results` without changing the event-study algorithm.
- Added persistent provider audit history in `provider_audit_runs`.
- Added data-quality assessment storage in `data_quality_assessments`.
- Added dataset metadata storage in `dataset_metadata`.
- Added compatibility/provenance columns to existing news, price, quote, and signal tables.
- Added `finsent/app/database/research_repository.py` with focused repositories for instruments, article links, experiments, research results, provider audits, data quality, datasets, and transaction rollback helper.
- Added `finsent/app/services/dataset_registry.py` with explicit scanner support for local CSV/reference datasets, LFS pointer detection, row/column/date metadata, and non-mutating scans.
- Wired active pipeline provider results into persistent provider audit and data-quality rows.
- Preserved existing dashboard/pipeline compatibility fields.
- Preserved Signal Engine V1 numerical behavior.
- Preserved the 3 intentional event-study xfails.
- Created `docs/DATABASE_V1_REFERENCE.md`.
- Created `docs/DATABASE_V2.md`.
- Created `docs/RESEARCH_STORAGE.md`.
- Created `docs/DATASET_REGISTRY.md`.
- Added Phase 5 tests for fresh DB creation, schema version, idempotent migration, V1 record preservation, instruments, article provenance/dedupe, model runs, signal runs, event-study result storage, experiments, provider audit safety, data quality, dataset scanning, dataset registry, timestamps, transaction rollback, and Signal V1 compatibility.
- Final test result after Phase 5 code changes: 88 passed, 3 xfailed, 0 failed.
- Remaining limitations: no Alembic history, no persistent raw response audit, no provider observability UI, no exchange-calendar logic, no automatic full archive scan, no execution of future research algorithms.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 6 - Sentiment Intelligence V2

- Re-ran the accepted Phase 5 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, schema version `2`, and 88 passed / 3 xfailed / 0 failed tests.
- Added canonical `SentimentAnalysisInput` and `SentimentAnalysisResult`.
- Added sentiment, catalyst, and time-horizon taxonomies plus canonical `[-1.0, +1.0]` sentiment scale.
- Added model execution status, failure taxonomy, and current-session model health records.
- Added `GeminiSentimentAnalyzer` with versioned prompt/schema and structured output validation.
- Added prompt module `finsent/app/prompts/financial_sentiment.py` with `financial_sentiment_v2_1`.
- Added `HeuristicSentimentAnalyzer` behind the same canonical contract.
- Added `FinBERTSentimentAnalyzer` behind the same canonical contract while keeping `torch`/`transformers` optional in `requirements-research.txt`.
- Added structured `DEPENDENCY_MISSING` behavior when FinBERT dependencies are absent.
- Added explicit OpenAI V2 stub classification as unavailable/deferred.
- Added `SentimentIntelligenceService` for analyzer selection, Gemini-to-heuristic fallback, batch execution, model health, and optional persistence to `sentiment_analysis_runs`.
- Kept active dashboard compatibility through `GeminiNewsAnalyzer`, which now uses Sentiment V2 internally and still returns `ArticleAnalysis`.
- Preserved `news_articles` compatibility fields as active/latest fields and `sentiment_analysis_runs` as the research source of truth.
- Added safe research CLI: `python -m finsent.scripts.run_sentiment_analysis`.
- Added deterministic tests for canonical input/result validation, Gemini success/failure/fallback, heuristic outputs, FinBERT dependency/probability mapping, factory behavior, persistence, batch partial failure, secret sanitization, and Signal V1 compatibility.
- Created `docs/SENTIMENT_INTELLIGENCE_V2.md`.
- Created `docs/GEMINI_ANALYZER.md`.
- Created `docs/FINBERT_ANALYZER.md`.
- Created `docs/SENTIMENT_RESEARCH_EXECUTION.md`.
- Updated active architecture, confidence semantics, README, and local changelog documentation.
- Final test result after Phase 6 code changes: 103 passed, 3 xfailed, 0 failed.
- Signal Engine V1 formulas were not changed.
- The 3 event-study xfails remain intentionally unresolved.
- Remaining limitations: no full Gemini-vs-FinBERT benchmark, no accuracy/agreement statistics, no confidence calibration, no Signal V2, no event-study rewrite, no model-comparison UI, and no live FinBERT download smoke in the default environment.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 7 - Explainable Signal Engine V2

- Re-ran the accepted Phase 6 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, schema version `2`, and 103 passed / 3 xfailed / 0 failed tests.
- Added `SIGNAL_ENGINE_VERSION` setting with default `v1`.
- Added `SignalInputV2`, `SignalNewsItemV2`, `SignalComponentV2`, and `SignalResultV2`.
- Added deterministic `SignalEngineV2` with news, price momentum, volume confirmation, liquidity, freshness, and data-quality components.
- Kept directional components separate from reliability components.
- Added reliability attenuation so poor liquidity, stale data, and low data quality reduce magnitude/confidence without flipping direction.
- Added explicit engine identity `finsent_composite` version `2.0`.
- Added `SignalEngineV2Service` to build V2 inputs from stored local DB data and optionally persist V2 runs.
- Persisted V2 component breakdown and explanations to existing Phase 5 `signal_runs.future_component_json`; no schema change was required.
- Added safe explicit CLI: `python -m finsent.scripts.run_signal_v2`.
- Preserved the dashboard and active pipeline default on Signal V1.
- Preserved Signal Engine V1 numerical behavior.
- Added Phase 7 tests for V2 news scoring, time decay, disagreement, momentum horizons, normalization, volume confirmation, liquidity/freshness/data-quality attenuation, missing data, persistence, explanations, bounds, determinism, and V1 compatibility.
- Created `docs/SIGNAL_ENGINE_V2.md`.
- Created `docs/SIGNAL_COMPONENTS_V2.md`.
- Updated active architecture, confidence semantics, research storage, known-issues, README, and local changelog documentation.
- Final test result after Phase 7 code changes: 121 passed, 3 xfailed, 0 failed.
- The 3 event-study xfails remain intentionally unresolved.
- Remaining limitations: V2 weights are not backtest-optimized, confidence is not calibrated, there is no strict event-study/backtest integration yet, no sector/macro context, no technical indicator stack beyond basic momentum, and no UI promotion.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 8 - Event Study Engine V2

- Re-ran the accepted Phase 7 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, schema version `2`, and 121 passed / 3 xfailed / 0 failed tests.
- Preserved the legacy V1 event-study matcher in `finsent/app/analysis/market_impact.py`.
- Added strict `EventStudyEngineV2` with engine identity `finsent_event_study` version `2.0`.
- Added canonical `EventStudyInputV2`, `EventStudyHorizon`, `BarMatchResult`, and `EventStudyResultV2`.
- Added US, NSE, and BSE market-session calendars with exchange-local timezone conversion.
- Defined event effective-time policy for during-session, before-open, after-close, weekend, and holiday timestamps.
- Implemented first-valid-bar-at-or-after entry and exit matching.
- Added market-aware `1H`, `4H`, and `1D` horizons.
- Added trading-time advancement across market closes, weekends, and known holidays.
- Added frequency detection for intraday, daily, irregular, and unknown bars.
- Rejected daily bars for `1H` and `4H`; allowed `1D` daily session-day returns.
- Added result statuses, match-quality labels, strict tolerance metadata, raw decimal return, and optional log return metadata.
- Integrated V2 persistence with existing `event_study_results` using `metadata_json`; schema version remains `2`.
- Added `EventStudyServiceV2`, `EventStudyBatchRunnerV2`, and safe CLI `python -m finsent.scripts.run_event_study_v2`.
- Converted the original 3 event-study xfails into passing V2 correctness checks.
- Added Phase 8 tests for market-hours, after-hours, weekends, holidays, horizon advancement, daily bars, timezone/DST behavior, bar-quality handling, persistence, batch runner behavior, and Signal V2 result linkage.
- Created `docs/EVENT_STUDY_V1_REFERENCE.md`.
- Created `docs/EVENT_STUDY_V2.md`.
- Created `docs/MARKET_SESSION_POLICY.md`.
- Created `docs/EVALUATION_HARNESS.md`.
- Updated active architecture, research storage, known-issues, README, and local changelog documentation.
- Signal Engine V1 was not changed.
- Signal Engine V2 formulas were not changed.
- Remaining limitations: compact built-in holiday lists, no full exchange-calendar dependency, no benchmark-adjusted returns, no sector-relative context, no broad historical performance claims, and no dashboard redesign.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 9 - Gemini vs FinBERT Controlled Model Comparison

- Re-ran the accepted Phase 8 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, schema version `2`, and 165 passed / 0 xfailed / 0 failed tests.
- Added `ModelComparisonConfig` with versioned experiment settings, article filters, horizons, neutral thresholds, model identifiers, reuse flags, and random seed.
- Added deterministic `ArticleSelectionService` with symbol/market/provider/date filtering, content checks, dedupe control, seeded sampling, and explicit exclusion reasons.
- Added `GeminiFinBertExperimentRunner` for paired article execution using one canonical `SentimentAnalysisInput` for both models.
- Added exact-compatible run reuse through comparison fingerprints and optional force-rerun behavior.
- Added dry-run behavior that performs no Gemini calls, no FinBERT inference, no writes, and reports credential/dependency readiness plus Event Study V2 coverage.
- Added descriptive metrics for agreement, confusion matrices, strict accuracy, directional accuracy, precision, recall, F1, balanced accuracy, confidence buckets, catalyst grouping, disagreement analysis, horizon-separated outcomes, latency summaries, and Wilson intervals.
- Added row-level CSV and summary JSON export support under `output/research/<experiment_id>/`.
- Added safe CLI `python -m finsent.scripts.run_model_comparison`.
- Created `docs/GEMINI_FINBERT_EXPERIMENT.md`.
- Created `docs/MODEL_EVALUATION_METRICS.md`.
- Created `docs/RESEARCH_REPRODUCIBILITY.md`.
- Updated sentiment research execution, evaluation harness, research storage, active architecture, README, and local changelog documentation.
- No live Gemini-vs-FinBERT experiment was executed because the local dry-run selected 0 stored articles and Gemini was unconfigured.
- Signal Engine V1 was not changed.
- Signal Engine V2 formulas were not changed.
- Event Study V2 methodology was not changed.
- Remaining limitations: no statistical significance claims, no confidence calibration, no full historical benchmark, no research dashboard, no monetary Gemini cost calculation without provider usage data, and FinBERT live inference still depends on optional research packages/model availability.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 10 - Real Research Dataset and Historical Signal Evaluation

- Re-ran the accepted Phase 9 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, dashboard HTTP 200, pipeline import pass, schema version `2`, and 185 passed / 0 xfailed / 0 failed tests.
- Audited local data availability: runtime research tables were empty, `archive/v1/*.NS.csv` contained usable NSE daily price CSVs, local company CSVs were reference-only, and `SnP_daily_update.csv` was a Git LFS pointer rather than usable US prices.
- Added `LocalResearchArticleImporter` for explicit local CSV article ingestion with dry-run/execute behavior, provenance fields, canonical instrument resolution, dedupe checks, and article-instrument links.
- Added deterministic `ResearchCohortBuilder` with symbol/market/date filtering, dedupe, seeded sampling, development/holdout split, Event Study V2 coverage checks, exclusion counts, and stable cohort fingerprints.
- Added `HistoricalSignalEvaluator` for frozen Signal V1 and Signal V2 evaluation at article timestamp `T0`.
- Enforced the Phase 10 no-lookahead boundary: historical signal inputs use only articles and price bars timestamped at or before `T0`; Event Study V2 uses future bars only as outcome measurement.
- Added horizon-separated metrics, V1/V2 disagreement analysis, conditional returns, signal-mode segmentation, data-quality segmentation, V2 component summaries, and CSV/JSON/Markdown export artifacts.
- Added safe CLIs `python -m finsent.scripts.ingest_research_articles` and `python -m finsent.scripts.run_signal_evaluation`.
- Created `docs/RESEARCH_DATA_AVAILABILITY.md`, `docs/RESEARCH_DATASET.md`, `docs/HISTORICAL_SIGNAL_EVALUATION.md`, `docs/LOOKAHEAD_PREVENTION.md`, and `docs/RESEARCH_COHORT_POLICY.md`.
- Updated research reproducibility, evaluation harness, research storage, active architecture, README, and local changelog documentation.
- Added Phase 10 tests for CSV importer validation/provenance, deterministic cohorts, coverage/exclusions, no-lookahead protection, persistence, metrics/segmentation, exports, and CLI dry-run safety.
- No real historical article rows were imported during Phase 10 because no suitable article dataset was present in the local runtime DB and provider-gated data was not fabricated.
- No database schema change was required; schema version remains `2`.
- Signal Engine V1 formulas were not changed.
- Signal Engine V2 formulas were not changed.
- Event Study V2 methodology was not changed.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 11 - Real Historical News Acquisition and Cohort Population

- Re-ran the accepted Phase 10 baseline before modifications: compile pass, `pip check` pass, DB init/open pass, schema version `2`, pipeline import pass, dashboard HTTP 200, and 193 passed / 0 xfailed / 0 failed tests.
- Audited the 14 baseline warnings and classified them as project-owned Python `datetime.utcnow()` deprecation warnings in tests.
- Fixed the low-risk test timestamp warnings by switching test helpers to timezone-aware-now converted to naive UTC storage shape.
- Evaluated historical-news sources: FNSPID, Marketaux historical news, Polygon News, Alpaca News, and Yahoo HTML scraping.
- Selected FNSPID as the primary Phase 11 source because it is public, research-oriented, timestamped, ticker-linked, and accessible without local credentials.
- Added `finsent/app/services/historical_news_acquisition.py` with a source-specific FNSPID adapter, bounded streaming acquisition, manifests, normalized exports, source evaluation helpers, readiness reporting, yfinance daily price acquisition, and sentiment-to-article compatibility update helpers.
- Added `python -m finsent.scripts.prepare_research_cohort` as a dry-run-first bounded orchestrator.
- Updated `PriceRepository.upsert_price_bars` to accept optional provider/dataset/data-mode/quality provenance while preserving existing callers.
- Updated `.gitignore` so generated external research subsets remain local while source manifests can be preserved.
- Ran a locked FNSPID dry-run for AAPL and AMZN over 2023 with limit 50 and max scan 300000; the stream found 50 candidates after 12075 scanned rows.
- Executed the bounded acquisition with batch id `phase11_fnspid_aapl_amzn_2023_v1`.
- Imported 50 genuine FNSPID news articles, all AAPL because the bounded stream filled before AMZN rows were reached.
- Imported 502 yfinance daily price rows for AAPL and AMZN, normalized daily bars to US session-close timestamps, and verified 1D Event Study V2 coverage.
- Preserved manifests under `data/research_sources/fnspid/MANIFEST.json` and `data/research_sources/yfinance_daily/MANIFEST.json`.
- Exported normalized article metadata to `data/research/normalized_articles_phase11_fnspid_aapl_amzn_2023_v1.csv`.
- Ran a controlled real FinBERT analysis on 20 genuine FNSPID AAPL articles; 20 succeeded and 20 sentiment runs were persisted.
- Gemini remained unconfigured, so no Gemini run and no paired Gemini/FinBERT comparison were executed.
- Ran the first PRELIMINARY real-data historical signal evaluation over the 20 FinBERT-analyzed AAPL articles with 1D coverage.
- Exported preliminary signal evaluation artifacts under `output/research/phase11/2/`.
- Preliminary descriptive results: Signal V1 strict accuracy 60.0% (N=20); Signal V2 strict accuracy 0.0% (N=20). These are not final claims.
- Added Phase 11 tests for FNSPID row normalization, malformed rows, bounded acquisition, manifests, idempotent import, price provenance, daily 1D coverage, daily intraday rejection, source evaluation, readiness reporting, normalized exports, and CLI help.
- Created `docs/HISTORICAL_NEWS_SOURCE_EVALUATION.md`, `docs/RESEARCH_DATA_INGESTION.md`, `docs/INITIAL_RESEARCH_COHORT.md`, and `docs/EXTERNAL_DATA_PROVENANCE.md`.
- Updated research dataset, data availability, cohort policy, reproducibility, dataset registry, README, and local changelog documentation.
- No database schema change was required; schema version remains `2`.
- Signal Engine V1 formulas were not changed.
- Signal Engine V2 formulas, weights, thresholds, and confidence formula were not changed.
- Event Study V2 methodology was not changed.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 12 - Evaluation Integrity and Locked Multi-Symbol Baseline

- Re-ran the accepted Phase 11 baseline checks: compile pass, `pip check` pass, DB init/open pass, schema version `2`, dashboard HTTP 200, pipeline import pass, and full suite baseline 203 passed / 0 xfailed / 0 failed.
- Reproduced the Phase 11 preliminary experiment as experiment `3`: V1 strict accuracy 60.0% (N=20), V2 strict accuracy 0.0% (N=20).
- Exported row-level V2 diagnostics to `output/research/phase12_v2_diagnostic.csv`.
- Confirmed no FinBERT-to-V2 mapping bug: missing Gemini-specific fields did not zero relevance, impact, article weight, or news contribution.
- Classified the Phase 11 V2 0% result as a small-sample observed failure with input/mode/data limitations, not a confirmed implementation bug.
- Created `docs/PHASE12_COHORT_PREREGISTRATION.md` before locked-cohort evaluation metrics were generated.
- Added stratified FNSPID acquisition using per-symbol quotas so one ticker cannot fill the full cap.
- Selected AAPL, AMZN, GOOGL, NVDA, and TSLA based on FNSPID availability, price availability, FinSent support, and company diversity, not observed signal accuracy.
- Acquired 200 FNSPID source rows from `Stock_news/All_external.csv`; imported 183 after URL dedupe.
- Added direct Yahoo chart daily-price acquisition after yfinance was rate-limited before evaluation; imported 35 daily rows per selected symbol with unadjusted `quote.close` as the Event Study basis.
- Ran FinBERT on the locked cohort: 183 new runs, 0 reused, 0 failed.
- Ran locked V1/V2 1D evaluation as experiment `5`: 366 signal rows, 159 valid 1D outcome rows.
- Reported development and holdout separately with strict accuracy, directional accuracy, balanced accuracy, precision, recall, F1, Wilson intervals, simple baselines, paired correctness, and component summaries.
- Development N=118: V1 strict 25.4%, directional 33.3%; V2 strict 28.8%, directional 31.7%.
- Holdout N=41: V1 strict 12.2%, directional 16.7%; V2 strict 9.8%, directional 14.3%.
- Created `docs/PHASE12_V2_DIAGNOSTIC.md`, `docs/LOCKED_COHORT_EVALUATION.md`, and `docs/SIGNAL_TUNING_POLICY.md`.
- Added `finsent/app/services/phase12_research.py`, `finsent/scripts/run_phase12_research.py`, and Phase 12 tests.
- Signal Engine V1 formulas were not changed.
- Signal Engine V2 formulas, weights, thresholds, confidence, momentum normalization, news decay, and volume behavior were not changed.
- Event Study V2 methodology and realized-return threshold were not changed.
- Remaining limitations: title-only FNSPID rows, small locked cohort, no Gemini, 1D daily horizon only, no benchmark-adjusted returns, no tuning, and no final winner claim.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.

## Phase 13 - Development-Only Signal V2.1 Tuning

- Added a preregistered, locked future-period final holdout and an explicit evaluation guard.
- Final holdout fingerprint: `a6db3f66a5a648a755dca53325577e499f1fe607ab4b70d1e6c896133395b9c4`.
- Added development-only V2 error analysis, temporal CV, baseline comparisons, and a modest V2.1 parameter grid.
- Frozen research candidate: `2.1-research` with status `FROZEN_RESEARCH_CANDIDATE_NOT_JUSTIFIED`.
- Artifacts: `output/research/phase13/phase13_development_tuning_v1`.
- Signal V1, Signal V2.0 defaults, Event Study V2, FinBERT configuration, confidence calibration, and dashboard defaults remain unchanged.
- No commit hashes recorded.

## Phase 14 - Confidence Calibration and Final Holdout Replacement

- Added development-only Signal V2 confidence calibration analysis.
- Calibration status: `NO_CALIBRATION_JUSTIFIED_IDENTITY_SELECTED`.
- Retired holdout status: `FINAL_HOLDOUT_RETIRED_UNEVALUATED`; reason: `INSUFFICIENT_SYMBOL_DIVERSITY / INSUFFICIENT_TOTAL_TECHNICAL_COVERAGE / DATE_WINDOW_TOO_CLUSTERED`.
- Replacement holdout status: `FINAL_HOLDOUT_NOT_READY`; fingerprint: `0b6a02e786542351fac70d45a6547595457701c803b830327f1b75893020f400`.
- Final-holdout performance remains unevaluated.
- Artifacts: `output/research/phase14`.

## Phase 15 - Robust Final Holdout Acquisition

- Documented FNSPID Nasdaq CSV alphabetic ticker grouping and AAPL-prefix sampling failure.
- Added remote byte-range, per-symbol final holdout acquisition.
- Lock status: `FINAL_HOLDOUT_V3_LOCKED`; fingerprint: `8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e`.
- Added final evaluation protocol for Phase 16 before final results exist.
- Final performance was not evaluated.

## Phase 16 - One-Shot Final Holdout Evaluation

- Executed the frozen final protocol once on `phase15_final_holdout_v3`.
- Preserved FinBERT, Signal V1, Signal V2.0, V2.1 research-only, identity confidence calibration, and Event Study V2.
- Created Phase 16 row export, summary JSON, report, reproducibility manifest, and result manifest.
- Marked the final holdout as evaluated-locked and blocked from future tuning.

## Phase 17 - Complete UI/UX Revamp and Research Dashboard

- Reworked the dashboard into a dense dark graphite analytics UI while preserving Dash, Plotly, callbacks, providers, database architecture, and research methodology.
- Mapped `/` to the functional Overview page and exposed navigation for Overview, Stock Research, News Intelligence, Compare, Research, and Alerts.
- Added shared UI presentation primitives in `finsent/app/dashboard/ui_components.py`.
- Added a read-only Phase 16 artifact loader in `finsent/app/dashboard/research_results.py`.
- Added `/research` with locked final-holdout metrics, baselines, confusion matrices, class distributions, paired correctness, per-symbol charts, V2.1 unpromoted-candidate status, component findings, and confidence calibration.
- Replaced the previous marketing-style gradients/card-heavy styling with consolidated terminal-style CSS.
- Created `docs/UI_V1_AUDIT.md`, `docs/UI_DESIGN_SYSTEM.md`, `docs/UI_V2_ARCHITECTURE.md`, and `docs/RESEARCH_DASHBOARD.md`.
- Added Phase 17 tests for artifact integrity behavior, dashboard routes/pages, reusable UI components, nav exposure, and research page database non-mutation.
- Signal V1 remains the active dashboard signal. Signal V2.0 and Signal V2.1 remain research-only.
- Phase 16 final artifacts were read for display only and were not recomputed or modified.
- No Git commits, pushes, pulls, branches, remotes, pull requests, history changes, or other Git write operations were performed.
