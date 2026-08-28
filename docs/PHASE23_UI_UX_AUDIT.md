# Phase 23 UI/UX Audit

## Before Issues

- The Phase 22 dashboard exposed its full analytical density to every user, including provider details, confidence decomposition, benchmark diagnostics, and research metadata.
- The stock selector covered too few instruments and did not provide a clear US/India market workflow.
- Repeated controls and panels did not consistently distinguish primary decisions from supporting diagnostics.
- Narrow layouts needed stronger grid containment, table scrolling, long-text wrapping, and predictable control stacking.
- Currency and benchmark language assumed US instruments in several presentation paths.

## Changes Made

- Added persistent Simple and Analyst display modes that share the same state, services, calculations, and callbacks.
- Added one global market filter and searchable company/ticker selector backed by the centralized instrument registry.
- Reordered each route around its primary user question and added capability-aware empty states.
- Added market-aware currency, exchange labels, India provider states, and explicit Indian benchmark limitations.
- Standardized spacing, focus treatment, responsive grid behavior, headline wrapping, table containment, and chart priority.
- Reduced nested visual containers and used section spacing, compact borders, and hierarchy to group information.

## Simple Mode Philosophy

Simple is the default mode for demonstrations, supervisors, and non-specialist users. It prioritizes identity, price movement, FinBERT sentiment, Signal V1/V2, the strongest catalyst, market context, freshness, and recent news. Provider internals, decomposition detail, and secondary diagnostics are progressively hidden. Labels describe analytical evidence and never present investment instructions.

## Analyst Mode Philosophy

Analyst mode preserves the Phase 22 research and operational depth. It exposes confidence and reliability, catalyst detail, benchmark and sector comparisons, beta, volatility, correlation, provenance, and system diagnostics while retaining clear page and section hierarchy.

## Stock Selector Design

- The selector searches ticker and company name and displays ticker, company, and market/exchange.
- ALL, US, and INDIA filters reduce the result set without triggering provider requests.
- Registry metadata loads eagerly; quotes, bars, news, inference, and context remain on demand.
- The selected instrument remains obvious in both the control and page heading.
- Recent-selection persistence was not added because it was optional and would add state complexity beyond the phase requirement.

## US/India Market Design

US instruments retain the Alpaca IEX-first routing and existing fallback behavior. Indian instruments use canonical application symbols and centralized Kite/Yahoo translations. Kite unavailability is reported as unconfigured or unavailable; it is never presented as live. Indian equities are not compared with SPY, QQQ, or US sector ETFs.

## Spacing System

The interface uses a six-step spacing scale: 4, 8, 12, 16, 24, and 32 pixels. The same tokens drive navigation, controls, section gaps, panel padding, and responsive reductions. Simple mode uses slightly more internal breathing room while retaining a compact laptop footprint.

## Typography

The hierarchy distinguishes page titles, section titles, primary metrics, secondary metrics, labels, body copy, helper text, and metadata. Headings remain compact, labels remain readable, letter spacing is zero for normal text, and long company names and headlines wrap instead of colliding with adjacent content.

## Responsive Review

Visual QA was performed with Chromium DevTools screenshots at 1920x1080, 1440x900, 1366x768, 1024x768, 768x1024, and 390x844. Simple and Analyst modes rendered nonblank Plotly charts. Desktop and laptop layouts preserved hierarchy; controls stack at tablet widths; the News table scrolls within its section at 768px; and the mobile layout remains functional without page-level horizontal overflow.

## Accessibility Review

- Simple/Analyst and market controls use labeled radio inputs with keyboard access and visible selected states.
- Interactive elements have visible focus outlines.
- Status text accompanies color, so meaning does not depend on color alone.
- Controls have visible labels, charts retain textual titles, and empty/error states use explicit language.
- Contrast uses the established dark financial-workspace palette with distinct text, border, positive, negative, warning, and neutral tokens.

## Known Limitations

- The registry is curated and locally searchable; dynamic external instrument discovery is not implemented.
- Kite live validation requires a valid API key and active access token/session.
- Indian benchmark and sector-index context is intentionally unavailable until a reliable supported data path and methodology are defined.
- News availability varies by provider and symbol. Missing news does not suppress available price or signal information.
- Mobile is functional but intentionally less dense than the desktop-first analyst workspace; genuinely wide tables use local horizontal scrolling.

## Screenshot QA Status

Screenshot QA passed for all required viewport classes using a locally installed Chromium browser controlled through the Chrome DevTools Protocol. Canvas/Plotly checks confirmed nonblank charts on Overview and Stock Research. The screenshots are temporary QA assets outside the repository and are not part of the application deliverables.
