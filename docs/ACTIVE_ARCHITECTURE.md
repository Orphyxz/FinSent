# FinSent Active Architecture

This document freezes the current active behavior boundary. It does not claim future research algorithms are implemented.

## Entry Points

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `python -m finsent.scripts.run_dashboard` | Canonical dashboard entry point. |
| ACTIVE | `python -m finsent.scripts.run_pipeline` | CLI smoke/pipeline entry point. |
| ACTIVE | `finsent.app.dashboard.app.create_app` | Dash application factory. |
| RESEARCH / KEEP FOR NOW | `finsent.scripts.import_kaggle_prices` | Offline historical import utility. |
| RESEARCH / KEEP FOR NOW | `scripts/build_presentation.py` | Presentation tooling, now project-relative. |

## Active Dashboard

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `finsent/app/dashboard/app.py` | Callback orchestration and page refresh behavior. |
| ACTIVE | `finsent/app/dashboard/layout.py` | Root Dash layout and stores. |
| ACTIVE | `finsent/app/dashboard/components.py` | Nav, controls, empty states. |
| ACTIVE | `finsent/app/dashboard/ui_components.py` | Shared presentation primitives for badges, metrics, metadata, and compact empty states. |
| ACTIVE | `finsent/app/dashboard/research_results.py` | Read-only Phase 16 final artifact loader and integrity checks. |
| ACTIVE | `finsent/app/dashboard/pages/*.py` | Summary, stock detail, news impact, compare, research, and alerts layouts. |
| ACTIVE | `finsent/app/dashboard/view_model.py` | Loads DB data, triggers refreshes, builds data frames/figures. |
| ACTIVE | `finsent/app/dashboard/assets/dashboard.css` | Current visual styling. |

Phase 21 maps `/` to the functional Overview dashboard and keeps `/research` as a read-only final-results page. The Research page reads locked Phase 16 artifacts and must not rerun FinBERT, Signal V1/V2/V2.1 evaluation, Event Study V2, or final-holdout experiments.

## Active Market Data Path

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `finsent/app/services/market_providers.py` | Normalized quote model plus Alpaca/Polygon/Kite provider implementations. |
| ACTIVE | `finsent/app/services/provider_status.py` | Small structured status model for active provider diagnostics. |
| ACTIVE | `finsent/app/services/provider_contracts.py` | Provider contracts, result wrapper, attempt trace, and failure categories. |
| ACTIVE | `finsent/app/services/provider_routers.py` | Canonical active routing path for market quotes, bars, and news. |
| ACTIVE | `finsent/app/services/provider_reliability.py` | Timeout/retry support, cache, freshness, validation, data quality, and provider health. |
| ACTIVE | `AlpacaMarketDataProvider` | Primary US quote and bar provider when keyed; normally IEX feed. |
| ACTIVE | `PolygonMarketDataProvider` | Optional US quote and bar fallback when keyed. |
| ACTIVE | `KiteMarketDataProvider` | NSE/BSE quote and bar provider when keyed. |
| ACTIVE | `UnavailableMarketProvider` | Graceful unavailable state for unsupported/missing providers. |
| LEGACY | `finsent/app/services/market_data.py` | Deprecated yfinance/older market service. Do not delete yet. |

## Active News Path

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `finsent/app/services/news_providers.py` | Normalized article model plus Polygon/Marketaux/fallback provider implementations. |
| ACTIVE | `AlpacaNewsProvider` | Primary US current news when keyed; uses Alpaca/Benzinga news. |
| ACTIVE | `PolygonNewsProvider` | Optional US provider-grade news fallback when keyed. |
| ACTIVE | `MarketauxNewsProvider` | Optional US/NSE/BSE provider-grade news fallback when keyed. |
| ACTIVE | `CuratedWebNewsProvider` | Fallback path through `YahooFinanceScraper`. |
| ACTIVE | `finsent/app/scrapers/yahoo_finance.py` | Fallback Gemini search, Alpaca news, yfinance news, Yahoo HTML scraping. |

## Active Provider Status Boundary

Phase 2 adds `ProviderStatus` with these states:

- `AVAILABLE`
- `DEGRADED`
- `UNAVAILABLE`
- `UNCONFIGURED`
- `STALE`

Phase 3 adds `ProviderResult`, `ProviderAttempt`, failure categories, and deterministic routers.

Phase 4 adds leaf-provider provenance, data modes, freshness labels, data-quality assessments, in-memory TTL cache, stale-cache fallback, and current-session provider health.

Current coverage:

- Alpaca/Polygon/Kite quote snapshots carry structured market status.
- News routing records configured/unconfigured/fallback status.
- FinBERT/Gemini/OpenAI analyzer selection records model status without exposing secrets.
- `IntelligenceSnapshot.provider_statuses` carries service-level diagnostics for the active refresh.
- `IntelligenceSnapshot.provider_attempts` carries the lightweight routed attempt trace.

Raw response archiving is intentionally not implemented. The dashboard exposes compact System Status diagnostics; provider audit rows record real provider attempts.

## Active Sentiment Path

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `finsent/app/services/llm_analyzers.py` | Current article analysis and aggregation layer. |
| ACTIVE | `finsent/app/services/sentiment_v2.py` | Canonical Sentiment V2 input/result, analyzers, validation, taxonomies, failure taxonomy, and model health. |
| ACTIVE | `finsent/app/services/sentiment_intelligence.py` | Research execution service for analyzer selection, fallback, batch runs, and optional model-run persistence. |
| ACTIVE / RESEARCH | `finsent/app/services/model_comparison.py` | Phase 9 controlled Gemini-vs-FinBERT selection, paired execution, metrics, reuse, dry-run, and export framework. |
| ACTIVE | `finsent/app/prompts/financial_sentiment.py` | Versioned Gemini prompt/schema: `financial_sentiment_v2_1`. |
| ACTIVE | `FinBERTNewsAnalyzer` | Current default live article analyzer when `SENTIMENT_PROVIDER=finbert`. |
| OPTIONAL | `GeminiNewsAnalyzer` | Compatibility wrapper using Gemini Sentiment V2 when explicitly selected and configured. |
| ACTIVE FALLBACK | `heuristic_article_analysis` / `HeuristicSentimentAnalyzer` | Safe fallback for missing model dependencies, unconfigured providers, request failure, parse failure, or budget limits. |
| ACTIVE / OPTIONAL | `FinBERTSentimentAnalyzer` | Sentiment V2 analyzer using optional `requirements-research.txt`; active live default when installed. |
| STUB / DEFERRED | `OpenAIAnalyzerStub` / `OpenAIAnalyzerStubV2` | Explicit unavailable stub; no OpenAI support implemented in Phase 6. |
| RESEARCH / KEEP FOR NOW | `finsent/app/services/sentiment.py` | Legacy FinBERT/Gemini sentiment service for older experiments. |
| RESEARCH / KEEP FOR NOW | `FinBERTSentimentService` | Preserved, not active in dashboard runtime. |

Phase 6 adds the safe CLI `python -m finsent.scripts.run_sentiment_analysis` for small explicit sentiment research runs over stored articles.

Phase 9 adds the safe CLI `python -m finsent.scripts.run_model_comparison` for conservative dry-runs and explicitly executed paired Gemini-vs-FinBERT comparison runs.

## Active Database Path

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `finsent/app/database/base.py` | SQLAlchemy engine/session, schema version, and additive SQLite migration. |
| ACTIVE | `finsent/app/database/entities.py` | V1 compatibility tables plus V2 research/storage ORM tables. |
| ACTIVE | `finsent/app/database/repository.py` | Current dashboard/pipeline persistence and read adapters. |
| ACTIVE | `finsent/app/database/research_repository.py` | Phase 5 repositories for instruments, experiments, model runs, signal runs, event results, provider audits, data quality, and dataset metadata. |
| ACTIVE | `finsent/app/services/dataset_registry.py` | Explicit CSV/reference dataset metadata scanner. |
| ACTIVE | `data/finsent.db` | Local runtime database, ignored. |

Phase 5 adds schema version `2`, canonical instruments, article-instrument links, immutable model-run storage, signal-run storage, event-study result storage, experiment runs, persistent provider audits, data-quality assessment storage, and dataset metadata. Signal V2 uses the signal-run storage added in Phase 5, and Event Study V2 uses the event-study storage.

## Active Signal Path

| Classification | Component | Notes |
|---|---|---|
| ACTIVE | `finsent/app/services/signal_engine.py` | Current deterministic signal formula. |
| ACTIVE | `CompositeSignalEngine.compute` | Behavior is characterized and frozen for Phase 2 before V2 changes. |
| ACTIVE / RESEARCH | `finsent/app/services/signal_engine_v2.py` | Explainable component signal engine; deterministic and separately callable. |
| ACTIVE / RESEARCH | `finsent/app/services/signal_service_v2.py` | Builds V2 inputs from stored/live data and can persist idempotent V2 signal runs. |
| RESEARCH / EXPLICIT | `python -m finsent.scripts.run_signal_v2` | Safe local CLI for explicit V2 evaluation and optional persistence. |
| RESEARCH / EXPLICIT | `finsent/app/services/research_dataset.py` | Phase 10 historical article import, cohort construction, coverage, and fingerprints. |
| RESEARCH / EXPLICIT | `finsent/app/services/historical_signal_evaluation.py` | Phase 10 Signal V1/V2 historical evaluation and exports. |
| RESEARCH / EXPLICIT | `python -m finsent.scripts.ingest_research_articles` | Safe explicit local CSV article importer. |
| RESEARCH / EXPLICIT | `python -m finsent.scripts.run_signal_evaluation` | Safe dry-run-first historical signal evaluation CLI. |

Phase 2 mode labels:

- `News + Quote Quality`
- `Quote-quality fallback`
- `News-only signal`
- `Unavailable`

Usable quotes require a positive current price, market timestamp, acceptable quality, and non-unavailable provider status. Signal V1 does not calculate true momentum, volume momentum, RSI/MACD, or order flow.

Signal Engine V2 combines news, price momentum, and volume confirmation, then attenuates score magnitude and confidence with liquidity, freshness, and data quality. V2 stores component explanations in the existing Phase 5 `signal_runs.future_component_json` field. The dashboard shows both live V1 and live V2 context, while Phase 16 research conclusions remain locked.

Phase 10 adds a research-only evaluator that compares frozen Signal V1 and Signal V2 on stored historical articles. It does not promote V2 to the dashboard and does not change either signal formula.

## Active Market Impact Path

| Classification | Component | Notes |
|---|---|---|
| LEGACY / CALLABLE | `finsent/app/analysis/market_impact.py` | V1 loose as-of event-study matching retained for dashboard compatibility/reference. |
| ACTIVE / RESEARCH | `finsent/app/analysis/event_study_v2.py` | Strict exchange-session-aware Event Study V2 engine. |
| ACTIVE / RESEARCH | `finsent/app/services/event_study_service_v2.py` | V2 service, persistence adapter, and small batch runner. |
| ACTIVE / RESEARCH | `python -m finsent.scripts.run_event_study_v2` | Safe explicit V2 CLI over stored local DB data. |
| ACTIVE | `dashboard/view_model.py::build_event_frame` | Uses 60-minute configured event frames for dashboard. |

Phase 8 does not redesign dashboard event views; the strict V2 path is explicit research infrastructure.

Phase 10 uses Event Study V2 as the realized outcome layer for historical signal evaluation. Future prices are used only after signal generation to measure outcomes.

## Research / Keep For Now

| Component | Reason |
|---|---|
| `finsent/app/services/sentiment.py` | FinBERT and old Gemini code support older comparison/research paths. |
| `requirements-research.txt` | Keeps heavy transformer dependencies explicit but optional. |
| `archive/v1` | Historical NSE prices for future backtesting/import work. |
| `finsent/app/services/kaggle_data.py` | Offline historical import path. |

## Questionable Modules Requiring Later Decisions

| Component | Question |
|---|---|
| `scripts/build_presentation.py` | Keep as maintained reporting tool, or replace with final report pipeline? |
| Existing generated `.pptx` files | Keep as submission artifacts, or regenerate from portable script later? |
| Large CSV universes | Keep as reference datasets; later decide whether to expand active symbol coverage from them. |
| Deprecated market/sentiment services | Keep for experiments or retire after V2 equivalents exist? |
