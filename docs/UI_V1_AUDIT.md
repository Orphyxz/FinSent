# UI V1 Audit

Phase 17 audited the accepted dashboard before visual changes and kept the backend behavior frozen.

## Baseline Findings

- The app was already a Dash and Plotly application with functional summary, stock detail, news impact, compare, and alerts pages.
- The root route still behaved like a landing/search surface, so the first screen did not immediately present the analytics workspace.
- Page headers and cards used a larger marketing-style visual language with gradients, radial backgrounds, large radii, and mixed typography.
- Navigation did not expose the final research results from Phase 16.
- Research artifacts existed under `output/research/phase16/`, but there was no dashboard page for controlled read-only presentation.
- News table styling and page copy were functional but visually inconsistent with a professional research terminal.

## Preserved Behavior

- Dash, Plotly, callbacks, page routing, provider routers, database repositories, and runtime view-model data construction were preserved.
- Signal V1 remains the active dashboard signal.
- Signal V2.0 and Signal V2.1 remain research-only.
- FinBERT, Event Study V2, confidence calibration, Phase 16 final artifacts, and final-holdout methodology were not recomputed or altered.

## Phase 17 UI Risks Addressed

- Root now maps to the functional Overview workspace.
- The final Research page reads locked Phase 16 artifacts and does not run evaluation code.
- Shared UI components reduce repeated badge, metric, and section markup.
- Styling now uses a dense graphite analytics aesthetic with compact spacing and restrained color.
- Dashboard route smoke tests and read-only research-page tests cover the main visual routes.

