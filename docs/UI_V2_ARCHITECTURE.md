# UI V2 Architecture

Phase 17 added the consolidated presentation layer. Phase 21 keeps that UI architecture and documents the current live V1/V2, Catalyst, Market Context, and System Status surfaces.

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
- `/research`: locked Research Dashboard
- `/alerts`: Operational Watchlist

The Research route hides live workspace controls and reads only final artifacts. Other routes keep the stored-data/provider-backed callback behavior and may show live/latest V1, V2, Catalyst, Market Context, and runtime status.

## Behavior Boundary

The UI layer may format, summarize, and visualize existing data. It must not:

- Present Signal V2.0 as proven superior to Signal V1.
- Promote Signal V2.1 from its frozen research-candidate status.
- Recompute Phase 16 final metrics.
- Rerun FinBERT, Gemini, Event Study V2, or final-holdout evaluation.
- Mutate final research artifacts.
- Fabricate market data, provider status, or performance claims.
