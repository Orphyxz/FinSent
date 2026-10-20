# FinSent Documentation

Start with the four "Start here" docs. Everything else is reference material for specific subsystems or for the historical research record.

## Start here

| Doc | What it covers |
|---|---|
| [Project Summary](PROJECT_SUMMARY.md) | What FinSent is and what it does, on one page |
| [Active Architecture](ACTIVE_ARCHITECTURE.md) | How the live app and research paths fit together |
| [Development Guide](DEVELOPMENT.md) | Running, testing and working on the codebase |
| [Known Limitations](KNOWN_LIMITATIONS.md) | What FinSent does not do, stated up front |

## Setup and configuration

- [macOS Setup](SETUP_MACOS.md), [Windows Setup](SETUP_WINDOWS.md)
- [Configuration Reference](CONFIGURATION.md)
- [Alpaca Setup](ALPACA_SETUP.md)
- [Data Bundle](DATA_BUNDLE.md)
- [Demo Runbook](DEMO_RUNBOOK.md)

## Live intelligence pipeline

- Data providers: [Provider Architecture](PROVIDER_ARCHITECTURE.md), [Provider Fallback Decisions](PROVIDER_FALLBACK_DECISIONS.md), [Provider Reliability](PROVIDER_RELIABILITY.md), [Runtime Reliability](RUNTIME_RELIABILITY.md)
- Markets: [Market Universe](MARKET_UNIVERSE.md), [Market Session Policy](MARKET_SESSION_POLICY.md), [Market Context Intelligence](MARKET_CONTEXT_INTELLIGENCE.md)
- Sentiment: [FinBERT Analyzer](FINBERT_ANALYZER.md), [Gemini Analyzer](GEMINI_ANALYZER.md), [Sentiment Intelligence V2](SENTIMENT_INTELLIGENCE_V2.md)
- Signals: [Signal Engine V2](SIGNAL_ENGINE_V2.md), [Signal Components V2](SIGNAL_COMPONENTS_V2.md), [Confidence Semantics](CONFIDENCE_SEMANTICS.md), [Catalyst Intelligence](CATALYST_INTELLIGENCE.md)
- Storage: [Database V2](DATABASE_V2.md), [Data Quality](DATA_QUALITY.md)
- Dashboard UI: [UI Final Design](UI_FINAL_DESIGN.md), [UI Design System](UI_DESIGN_SYSTEM.md), [UI V2 Architecture](UI_V2_ARCHITECTURE.md)

## Research methodology and results

The historical evaluation was preregistered and run once against a locked holdout. These docs record that process and its outcome.

- Results: [Final Holdout Results](FINAL_HOLDOUT_RESULTS.md), [Phase 16 Final Evaluation](PHASE16_FINAL_EVALUATION.md)
- Protocol: [Final Evaluation Protocol](FINAL_EVALUATION_PROTOCOL.md), [Lookahead Prevention](LOOKAHEAD_PREVENTION.md), [Signal Tuning Policy](SIGNAL_TUNING_POLICY.md), [Research Reproducibility](RESEARCH_REPRODUCIBILITY.md)
- Evaluation: [Evaluation Harness](EVALUATION_HARNESS.md), [Model Evaluation Metrics](MODEL_EVALUATION_METRICS.md), [Event Study V2](EVENT_STUDY_V2.md), [Historical Signal Evaluation](HISTORICAL_SIGNAL_EVALUATION.md), [Locked Cohort Evaluation](LOCKED_COHORT_EVALUATION.md), [Confidence Calibration](CONFIDENCE_CALIBRATION.md)
- Experiments: [Gemini vs FinBERT Experiment](GEMINI_FINBERT_EXPERIMENT.md), [Signal V2 Parameter Search](SIGNAL_V2_PARAMETER_SEARCH.md), [Signal V2.1 Research Candidate](SIGNAL_V2_1_RESEARCH_CANDIDATE.md)
- Data: [Research Dataset](RESEARCH_DATASET.md), [Dataset Registry](DATASET_REGISTRY.md), [External Data Provenance](EXTERNAL_DATA_PROVENANCE.md), [Research Data Availability](RESEARCH_DATA_AVAILABILITY.md), [Research Data Ingestion](RESEARCH_DATA_INGESTION.md), [Research Storage](RESEARCH_STORAGE.md), [FNSPID Source Layout](FNSPID_SOURCE_LAYOUT.md), [Historical News Source Evaluation](HISTORICAL_NEWS_SOURCE_EVALUATION.md)
- Cohorts and holdouts: [Research Cohort Policy](RESEARCH_COHORT_POLICY.md), [Initial Research Cohort](INITIAL_RESEARCH_COHORT.md), [Final Holdout Adequacy Policy](FINAL_HOLDOUT_ADEQUACY_POLICY.md), preregistrations [V1](FINAL_HOLDOUT_PREREGISTRATION.md) / [V2](FINAL_HOLDOUT_V2_PREREGISTRATION.md) / [V3](FINAL_HOLDOUT_V3_PREREGISTRATION.md)
- [Research Dashboard](RESEARCH_DASHBOARD.md), [Sentiment Research Execution](SENTIMENT_RESEARCH_EXECUTION.md), [Known Correctness Issues](KNOWN_CORRECTNESS_ISSUES.md)

## Development log

Phase-by-phase working notes, kept as a record of how the project evolved:

- [Phase 12 Cohort Preregistration](PHASE12_COHORT_PREREGISTRATION.md), [Phase 12 V2 Diagnostic](PHASE12_V2_DIAGNOSTIC.md), [Phase 13 Error Analysis](PHASE13_ERROR_ANALYSIS.md), [Phase 14 Research Protocol](PHASE14_RESEARCH_PROTOCOL.md), [Phase 15 Holdout Acquisition](PHASE15_HOLDOUT_ACQUISITION.md), [Phase 23 UI/UX Audit](PHASE23_UI_UX_AUDIT.md)
- Audits: [V2 Baseline Audit](V2_BASELINE_AUDIT.md), [UI V1 Audit](UI_V1_AUDIT.md)
- Superseded V1 references: [Database V1](DATABASE_V1_REFERENCE.md), [Event Study V1](EVENT_STUDY_V1_REFERENCE.md), [Signal Engine V1](SIGNAL_ENGINE_V1_REFERENCE.md)
- [Local Changelog](LOCAL_CHANGELOG.md), [Presentation Checklist](PRESENTATION_CHECKLIST.md)
- [Full project report (HTML)](FinSent_Project_Report.html)
