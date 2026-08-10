# UI V2 Architecture

Phase 17 keeps the existing Dash architecture and adds a consolidated presentation layer.

## Active Dashboard Modules

- `finsent/app/dashboard/app.py`: Dash factory, routes, and callbacks.
- `finsent/app/dashboard/layout.py`: root shell, stores, interval, nav, controls, page container, footer.
- `finsent/app/dashboard/components.py`: global nav, workspace controls, empty states.
- `finsent/app/dashboard/ui_components.py`: reusable presentation primitives for badges, metrics, metadata, and compact empty states.
- `finsent/app/dashboard/research_results.py`: read-only Phase 16 artifact loader and integrity checks.
- `finsent/app/dashboard/pages/research.py`: Phase 16 research dashboard.
- `finsent/app/dashboard/assets/dashboard.css`: consolidated visual system.

## Routing

The functional routes are:

- `/` and `/summary`: Overview
- `/stock-detail`: Stock Research
- `/news-impact`: News Intelligence
- `/compare`: Compare
- `/research`: Research and Validation
- `/alerts`: Alerts

The Research route hides live workspace controls and reads only final artifacts. Other routes keep the existing stored-data/provider-backed callback behavior.

## Behavior Boundary

The UI layer may format, summarize, and visualize existing data. It must not:

- Promote Signal V2.0 or V2.1 to the active dashboard signal.
- Recompute Phase 16 final metrics.
- Rerun FinBERT, Gemini, Event Study V2, or final-holdout evaluation.
- Mutate final research artifacts.
- Fabricate market data, provider status, or performance claims.

