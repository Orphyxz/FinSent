# Known Correctness Issues

Phase 2 verified the Phase 0/1 findings directly against current code. Some issues were fixed; larger research rewrites remain deferred.

## Fixed Or Refined In Phase 2

### Unavailable Market Snapshot Could Produce Market Mode

- Affected modules: `finsent/app/services/signal_engine.py`, `finsent/app/services/market_providers.py`, `finsent/app/dashboard/view_model.py`.
- Previous behavior: a quote object could influence mode semantics even when it had no usable price/timestamp or represented an unavailable provider.
- Phase 2 behavior: quote usability requires valid positive price, valid timestamp, acceptable quality (`live`, `delayed`, `stale`), and a non-unavailable provider state.
- Test coverage: `test_provider_status_phase2.py`, `test_signal_engine_v1_phase2.py`.

### Article Limit Propagation

- Affected modules: `finsent/app/services/pipeline.py`, `finsent/app/services/intelligence_service.py`, `finsent/app/dashboard/view_model.py`, `finsent/app/services/news_providers.py`.
- Previous behavior: `FinSentPipeline.run(limit=N)` accepted `N`, but `IntelligenceService.run` fetched `settings.default_news_limit`.
- Phase 2 behavior: caller-provided limits propagate into active news fetches; `0` remains caller intent, negative values raise `ValueError`, and very large values clamp to the provider-safe maximum of `50`.
- Test coverage: `test_pipeline_limits_and_dedupe_phase2.py`.

### Provider Status And Missing Credential Diagnostics

- Affected modules: `finsent/app/services/provider_status.py`, `market_providers.py`, `news_providers.py`, `intelligence_service.py`.
- Previous behavior: missing credentials and failures were mostly inferred from empty data, exceptions, or unavailable quote objects.
- Phase 2 behavior: active providers can emit `AVAILABLE`, `DEGRADED`, `UNAVAILABLE`, `UNCONFIGURED`, and `STALE` states with sanitized messages.
- Test coverage: `test_provider_status_phase2.py`.

### UI Signal/Confidence Wording

- Affected modules: dashboard callbacks, page copy, and view-model status text.
- Previous behavior: visible text implied order flow, buy/sell pressure, market agreement, or broad market blending beyond the implemented formula.
- Phase 2 behavior: visible copy now describes headline/news signals, model confidence, quote quality, spread-derived liquidity proxies, and stored volume context.
- Reference docs: `docs/CONFIDENCE_SEMANTICS.md`, `docs/SIGNAL_ENGINE_V1_REFERENCE.md`.

### URL Tracking Dedupe

- Affected modules: `finsent/app/services/news_providers.py`, `finsent/app/database/repository.py`.
- Previous behavior: database upsert primarily keyed by URL; runtime dedupe hashes did not normalize tracking query parameters.
- Phase 2 behavior: article dedupe hashes normalize title/source/time bucket and strip common tracking parameters from URLs. Repository upsert checks `dedupe_hash` before URL.
- Remaining limitation: this is not a robust NLP or cross-publisher duplicate detector.
- Test coverage: `test_pipeline_limits_and_dedupe_phase2.py`.

## Fixed Or Refined In Phase 8

### Loose 60-Minute Event Matching

- Affected modules: `finsent/app/analysis/event_study_v2.py`, `finsent/app/services/event_study_service_v2.py`.
- Previous behavior: V1 entry prices could match up to two days before the headline, and future prices could match up to two days after the target.
- Phase 8 behavior: V2 uses exchange-session-aware effective times, first bar at or after effective/target time, strict frequency-based tolerances, daily-bar granularity checks, explicit statuses, and auditable metadata.
- Test coverage: `test_event_study_v2_phase8.py`, updated V2 checks in `test_event_study_phase2.py`.
- Converted defect coverage:
  - Weekend articles no longer use Friday entry prices.
  - After-close articles use the next session open as effective event time.
  - Far-late future bars are rejected as out of tolerance.

## Still Open After Phase 8

### Signal V1 Lacks Real Momentum / Volume Behavior

- Affected module: `finsent/app/services/signal_engine.py`.
- Current behavior: Signal V1 uses news score, quote availability/quality, spread penalty, freshness penalty, and a small live-quote component.
- Phase 7 status: Signal V2 now exists as an explicit research engine with separately tested price momentum, volume confirmation, liquidity, freshness, and data-quality components.
- Remaining limitation: the active dashboard/pipeline default is still Signal V1, and V2 weights/confidence are engineering priors rather than calibrated research results.
- Test coverage: `test_signal_engine_v1_phase2.py` freezes current behavior before V2 changes.
- V2 coverage: `test_signal_engine_v2_phase7.py`.

### Confidence Is Not Calibrated

- Affected modules: `llm_analyzers.py`, `signal_engine.py`, dashboard view-models.
- Current behavior: confidence values are model/aggregate/signal confidence scores, not calibrated probabilities.
- Expected future behavior: experiment-backed calibration by model, exchange, ticker class, and horizon.
- Reference: `docs/CONFIDENCE_SEMANTICS.md`.

### US Historical Dataset Pointer

- Affected module: `finsent/app/services/kaggle_data.py`.
- Current behavior: local `SnP_daily_update.csv` is a Git LFS pointer instead of real CSV data.
- Phase 1 mitigation: diagnostic guard rejects the pointer.
- Expected future behavior: documented dataset acquisition or small checked-in fixture.

### Provider Architecture Remaining Limitations

- Affected modules: active providers, fallback scraper, and legacy services.
- Current behavior: Phase 5 adds persistent provider audit metadata without raw API response bodies or secrets.
- Remaining limitation: there is still no provider observability UI, no raw/audited response sampling layer, and provider health summaries are only partially surfaced in the dashboard.
- Expected future behavior: richer status display, retention controls, and provider reliability dashboards.

### Research Storage Does Not Mean Research Algorithms Are Complete

- Affected modules: `finsent/app/database/entities.py`, `finsent/app/database/research_repository.py`.
- Current behavior: Phase 5 adds tables for experiments, sentiment/model runs, signal runs, event-study results, provider audits, data quality, and datasets.
- Remaining limitation: Gemini-vs-FinBERT comparison, event-study rewrite, backtesting, catalyst analytics, Signal V2 calibration, and confidence calibration are still not implemented.
