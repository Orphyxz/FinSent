# FinSent

FinSent is a local financial-news intelligence, signal-research, and short-term market-impact dashboard built with Python, Dash, Plotly, Pandas, SQLAlchemy, and SQLite.

The current application has a professional Dash research-terminal UI, provider routing, Gemini-based live article analysis with heuristic fallback, deterministic active Signal V1 scoring, local persistence, and locked historical research results. It is not a trading system and does not claim profitability.

## Current Active Architecture

The canonical dashboard entry point is:

```powershell
python -m finsent.scripts.run_dashboard
```

The active runtime path is:

```text
Dash UI
  -> dashboard callbacks
  -> dashboard presentation components
  -> dashboard view_model.ensure_live_data
  -> SymbolRegistry
  -> IntelligenceService
  -> provider_routers
  -> market_providers / news_providers
  -> Sentiment Intelligence V2
  -> GeminiNewsAnalyzer compatibility output or heuristic fallback
  -> CompositeSignalEngine
  -> SQLAlchemy repositories
  -> SQLite database schema v2
  -> Plotly/Dash views
```

Dashboard routes:

- `/` and `/summary`: Overview
- `/stock-detail`: Stock Research
- `/news-impact`: News Intelligence
- `/compare`: Compare
- `/research`: locked final-holdout research results
- `/alerts`: Alerts

## Active Providers

Market data:

- US symbols: Polygon through `MarketDataRouter`, when `POLYGON_API_KEY` is configured.
- NSE/BSE symbols: Kite through `MarketDataRouter`, when `KITE_API_KEY` and `KITE_ACCESS_TOKEN` are configured.
- Missing credentials produce explicit `UNCONFIGURED` diagnostics and degrade to unavailable quote/bars rather than making every integration mandatory.

News:

- US symbols: Polygon News through `NewsProviderRouter`, then fallback web.
- NSE/BSE symbols: Marketaux through `NewsProviderRouter`, then fallback web.
- Fallback web path: Gemini search if configured, then Alpaca news if configured, then yfinance/Yahoo Finance scraping.

Sentiment / AI:

- Active article analysis uses Gemini through the Sentiment Intelligence V2-backed `GeminiNewsAnalyzer` when `GEMINI_API_KEY` is configured.
- If Gemini is unavailable, malformed, quota-limited, or over the per-refresh budget, the app uses local heuristic analysis.
- Sentiment Intelligence V2 provides canonical Gemini, heuristic, and optional FinBERT analyzer contracts.
- FinBERT is available for explicit research execution when `requirements-research.txt` is installed, but it is not active in the current dashboard Signal V1 path.
- Gemini-vs-FinBERT comparison is available as an explicit controlled research framework with dry-run safety and small default limits.
- Historical Signal V1/V2 evaluation is available as an explicit Phase 10 research framework with deterministic cohorts, no-lookahead input construction, Event Study V2 outcomes, and exportable reports.
- Phase 11 adds a bounded real FNSPID historical-news cohort, yfinance daily research prices, a controlled FinBERT run, and a PRELIMINARY 1D signal evaluation.

Signal engine:

- The current signal is deterministic app logic in `CompositeSignalEngine`.
- It combines article sentiment, confidence, impact strength, recency, quote freshness, quote quality, and spread penalty.
- Current modes are `News + Quote Quality`, `Quote-quality fallback`, `News-only signal`, and `Unavailable`.
- Signal Engine V2 exists as an explicit research engine in `finsent/app/services/signal_engine_v2.py` and `python -m finsent.scripts.run_signal_v2`.
- V2 combines news, price momentum, volume confirmation, liquidity, freshness, and data quality, but it is not the dashboard default.
- Confidence values are not calibrated price probabilities.

Event study:

- Event Study V2 exists as an explicit research engine in `finsent/app/analysis/event_study_v2.py`.
- It uses exchange-session-aware effective event times, strict first-bar-at-or-after matching, explicit 1H/4H/1D horizons, and auditable status metadata.
- The dashboard still keeps the legacy event frame path for compatibility; V2 is available through service/CLI for research execution.

## Project Structure

```text
finsent/
  app/
    analysis/       # current market-impact/event-study functions
    config/         # environment-backed settings
    dashboard/      # Dash app, pages, callbacks, CSS assets
    database/       # SQLAlchemy models, migrations, runtime and research repositories
    models/         # shared dataclasses
    prompts/        # versioned model prompts
    scrapers/       # fallback Yahoo/yfinance/Gemini/Alpaca news scraping
    services/       # providers, intelligence pipeline, signal logic, importers
    utils/          # text/time/logging helpers
  scripts/          # canonical run/import entry points
  tests/            # pytest test suite
archive/v1/         # large NSE historical CSV archive for offline import
docs/               # audit and development documentation
scripts/            # presentation/report tooling
```

## Windows PowerShell Setup

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Edit `.env` with any provider credentials you actually have. Leave unknown credentials blank.

Run tests:

```powershell
python -m pytest finsent\tests -q
```

Start the dashboard:

```powershell
python -m finsent.scripts.run_dashboard
```

Open:

```text
http://127.0.0.1:8050
```

Pipeline smoke:

```powershell
python -m finsent.scripts.run_pipeline --ticker AAPL --limit 15
```

## Dependency Files

- `requirements.txt`: active runtime dashboard/application dependencies.
- `requirements-dev.txt`: runtime dependencies plus test tooling.
- `requirements-research.txt`: dev dependencies plus heavy FinBERT/transformer dependencies.
- `requirements-presentation.txt`: dependencies for presentation tooling.

The heavy `torch` and `transformers` packages are intentionally separated because FinBERT is preserved for research but is not active in the current dashboard path.

## Configuration

Use `.env.example` as the safe template. Real `.env` files are ignored and should not be shared.

Important groups:

- Core runtime and SQLite database path.
- Provider selection.
- Gemini.
- Polygon.
- Kite.
- Marketaux.
- Optional legacy providers such as Alpaca.
- Optional research settings such as FinBERT model name.

Logging uses the standard library and defaults to `INFO`. Set `FINSENT_LOG_LEVEL=WARNING` or `DEBUG` locally if needed.

## Local Data

The app initializes SQLite at:

```text
data/finsent.db
```

This is local runtime state and is ignored.

`archive/v1` contains a large NSE historical CSV archive for offline imports. It is not required for dashboard startup.

`SnP_daily_update.csv` is currently a Git LFS pointer in this local copy, not the actual US price dataset. The US importer now detects that condition and stops with a clear diagnostic instead of reading the pointer text as market data.

Database and dataset references:

- `docs/DATABASE_V1_REFERENCE.md`: pre-Phase-5 schema reference.
- `docs/DATABASE_V2.md`: current schema version, entities, migration, indexes, and compatibility notes.
- `docs/RESEARCH_STORAGE.md`: experiment/model/signal/event/provider-audit storage design.
- `docs/DATASET_REGISTRY.md`: CSV/reference dataset roles and scanner behavior.

Sentiment references:

- `docs/SENTIMENT_INTELLIGENCE_V2.md`: canonical sentiment input/result, analyzers, taxonomies, fallback, and persistence.
- `docs/GEMINI_ANALYZER.md`: Gemini prompt/schema version and validation behavior.
- `docs/FINBERT_ANALYZER.md`: FinBERT capabilities, normalization, dependencies, and limits.
- `docs/SENTIMENT_RESEARCH_EXECUTION.md`: safe explicit sentiment model-run execution.

Signal references:

- `docs/SIGNAL_ENGINE_V1_REFERENCE.md`: frozen active Signal V1 behavior.
- `docs/SIGNAL_ENGINE_V2.md`: Phase 7 explainable Signal V2 architecture, score formula, labels, and limitations.
- `docs/SIGNAL_COMPONENTS_V2.md`: V2 component formulas and missing-data behavior.

Event-study references:

- `docs/EVENT_STUDY_V1_REFERENCE.md`: preserved loose legacy matcher behavior.
- `docs/EVENT_STUDY_V2.md`: strict V2 methodology, horizons, tolerances, statuses, and storage.
- `docs/MARKET_SESSION_POLICY.md`: US/NSE/BSE session and timezone rules.
- `docs/EVALUATION_HARNESS.md`: small safe evaluation runner and CLI behavior.

Model-comparison references:

- `docs/GEMINI_FINBERT_EXPERIMENT.md`: paired experiment design and eligibility rules.
- `docs/MODEL_EVALUATION_METRICS.md`: agreement, accuracy, F1, balanced accuracy, confidence buckets, and limitations.
- `docs/RESEARCH_REPRODUCIBILITY.md`: configuration, reuse fingerprints, exports, and no-lookahead policy.

Historical signal evaluation references:

- `docs/RESEARCH_DATA_AVAILABILITY.md`: local source audit and usable/unusable data.
- `docs/RESEARCH_DATASET.md`: CSV article import and cohort construction.
- `docs/HISTORICAL_SIGNAL_EVALUATION.md`: Signal V1/V2 historical evaluation framework.
- `docs/LOOKAHEAD_PREVENTION.md`: `T0` input boundary and outcome separation.
- `docs/RESEARCH_COHORT_POLICY.md`: eligibility, exclusions, splits, and sampling.
- `docs/HISTORICAL_NEWS_SOURCE_EVALUATION.md`: Phase 11 source audit and decision.
- `docs/RESEARCH_DATA_INGESTION.md`: bounded FNSPID/yfinance ingestion path.
- `docs/INITIAL_RESEARCH_COHORT.md`: first real cohort and preliminary results.
- `docs/EXTERNAL_DATA_PROVENANCE.md`: manifests, checksums, and local external-data paths.
- `docs/PHASE12_V2_DIAGNOSTIC.md`: investigation of the Phase 11 V2 0% preliminary result.
- `docs/PHASE12_COHORT_PREREGISTRATION.md`: locked multi-symbol cohort rules before Phase 12 evaluation.
- `docs/LOCKED_COHORT_EVALUATION.md`: Phase 12 development/holdout baseline metrics and limits.
- `docs/SIGNAL_TUNING_POLICY.md`: development-only tuning contract for future Signal V2 work.

## Known Limitations

- The active symbol universe is hard-coded and small.
- Provider credentials are optional, so the dashboard may run in degraded or unconfigured modes.
- Provider status and persistent provider audit metadata are modeled for the active pipeline, but raw response auditing and provider observability UI are future work.
- Provider routing is consolidated in `finsent/app/services/provider_routers.py`; see `docs/PROVIDER_ARCHITECTURE.md`.
- Provider reliability and data quality are documented in `docs/PROVIDER_RELIABILITY.md`, `docs/DATA_QUALITY.md`, and `docs/PROVIDER_FALLBACK_DECISIONS.md`.
- Event Study V2 provides strict outcome measurement, and historical signal evaluation now exists as an explicit research harness; benchmark-adjusted research and larger imported cohorts remain future work.
- The first real imported cohort was small and AAPL-only; Phase 12 adds a locked multi-symbol baseline, but it remains small, daily-only, and title-text limited.
- The dashboard still uses Signal V1 by default; Signal V2 is explicit research functionality.
- Broad live FinBERT/Gemini benchmarking, backtesting, Signal V2 calibration, catalyst analytics, and confidence calibration are future work.
- Sentiment model-run storage exists, but comparative accuracy/agreement results are not yet produced.
- The UI has been redesigned into a professional research dashboard, but visual screenshots are not stored in the repository.

## V2 Direction

The long-term V2 goal is a defensible research-oriented market/news intelligence platform with strict event studies, model comparisons, backtesting, confidence calibration, provider observability, and a professional analytics UI.

Those features are not claimed as implemented yet.

### Phase 13 research artifacts

Phase 13 freezes a development-only Signal V2.1 research candidate under `output/research/phase13/phase13_development_tuning_v1/` and locks a new future-period final holdout as unevaluated. The dashboard default remains unchanged.

### Phase 14 research artifacts

Phase 14 adds development-only confidence calibration artifacts and final-holdout adequacy metadata under `output/research/phase14/`. Directional signal logic remains frozen.

### Phase 15 research artifacts

Phase 15 adds robust source-layout-aware final holdout acquisition artifacts under `output/research/phase15/`. Final performance evaluation is reserved for Phase 16.

## Phase 16 Final Evaluation

The locked final holdout has been evaluated once under the preregistered protocol. Artifacts are under `output/research/phase16/`; the cohort is not available for future tuning.

## Research Dashboard

The `/research` page reads the locked Phase 16 summary and result manifest without recomputing experiments. It verifies the final-holdout fingerprint and summary hash before displaying metrics.

Key displayed final-holdout results:

- Final evaluated N: 111.
- Signal V1 strict accuracy: 32.4%; balanced accuracy: 51.9%; macro F1: 31.5%.
- Signal V2.0 strict accuracy: 22.5%; balanced accuracy: 39.2%; macro F1: 19.5%.
- Signal V2.1 remains an unpromoted research candidate.
- Results describe only the locked FNSPID/Yahoo daily 1D cohort.

UI and research-dashboard documentation:

- `docs/UI_V1_AUDIT.md`
- `docs/UI_DESIGN_SYSTEM.md`
- `docs/UI_V2_ARCHITECTURE.md`
- `docs/RESEARCH_DASHBOARD.md`
