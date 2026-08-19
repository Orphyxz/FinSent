# FinSent Final UI Design

Phase 22 is a UI/UX-only polish pass. It does not change providers, signals, FinBERT behavior, Catalyst Intelligence semantics, Market Context formulas, database schema, or locked Phase 16 research artifacts.

## Design Philosophy

FinSent should feel like a serious financial intelligence terminal: compact, data-first, readable, and honest about freshness. The interface avoids generic AI-dashboard styling, excessive decoration, and trade-execution language.

## Layout System

- Global sticky top navigation with compact brand and active route state.
- Workspace controls stay above page content and preserve callback IDs.
- System Status is an expandable utility strip near the top of the workspace.
- Page content uses dense panels and primary chart areas rather than oversized hero cards.
- Main presentation target is laptop/desktop, with responsive stacking on smaller screens.

## Visual Hierarchy

Primary information:

- symbol
- price/latest price
- window move
- V1/V2 signal context
- FinBERT sentiment
- market/freshness state

Secondary information:

- catalysts
- market/sector context
- recent news
- comparison summaries

Tertiary information:

- provider provenance
- cache status
- DB/schema state
- runtime diagnostics

## Color Semantics

- Positive/bullish: green
- Negative/bearish: red
- Warning/stale/locked-research caution: amber
- Neutral: gray
- Benchmark/context line: muted blue-gray
- Page surfaces: graphite/charcoal

The palette is intentionally restrained and avoids rainbow metric styling.

## Typography

The UI uses the existing system font stack. Page titles are compact, section headings are medium-weight, labels are small and muted, and metrics remain prominent without oversized marketing-style typography.

## Reusable Components

Existing shared primitives remain the foundation:

- `section_header`
- `metric_cell`
- `research_metric`
- `status_badge`
- `signal_badge`
- `quality_badge`
- `metadata_row`
- `component_bar`
- `compact_empty`

Repeated panel, metric, badge, table, and chart styling is centralized in `finsent/app/dashboard/assets/dashboard.css`.

## Chart Conventions

- Plotly modebar is hidden for demo cleanliness.
- Chart backgrounds match the graphite surface.
- Grid lines are subtle.
- Hover labels use the same dark theme.
- Focus stock lines are visually dominant.
- Benchmarks and sector series are subdued.
- V1/V2 colors are distinct but restrained.

## Table Conventions

- News Intelligence uses a compact terminal-style table.
- Primary visible columns prioritize time, ticker, source, headline, sentiment, confidence, impact, and catalyst.
- Lower-value provenance columns remain available in data but are hidden from the primary presentation.
- Numeric columns are right-aligned where practical.
- Rows have subtle hover/selection states.

## Page Structure

Overview:

- page header
- data status strip
- compact metric strip
- primary market chart
- signal intelligence explanation
- market context
- active catalysts

Stock Research:

- stock header
- compact metric strip
- primary chart
- signal intelligence
- market metadata
- catalyst summary
- relative performance
- market context
- key catalysts and timeline

News Intelligence:

- compact header and filters
- status strip
- sentiment/impact chart
- summary panel
- dense headline terminal table

Compare:

- selector summary
- metric strip
- indexed performance
- comparison brief
- market/sector relative chart
- market context and catalysts

Research:

- visually distinct locked Phase 16 banner
- final N, symbols, horizon, source metadata
- V1/V2 metrics
- visible baselines
- charts and secondary V2.1/calibration notes

Alerts:

- contextual monitoring language
- no persistent notification claims
- severity/reason-oriented feed

## Responsive Behavior

- 1366x768: header, workspace controls, metric strip, and primary chart are compact enough for a laptop demo.
- 1920x1080: shell max width prevents unreadably wide content.
- Tablet/mobile: grids stack and tables allow horizontal scrolling.

## Accessibility

- Labels accompany semantic colors.
- Focus outlines remain visible.
- Contrast is improved through graphite surfaces and high-contrast text.
- Charts keep legends and meaningful series names.

## Known UI/UX Limitations

- Large financial tables still rely on horizontal scrolling on small screens.
- System Status is an expandable details panel rather than a full drawer/modal.
- Screenshots are not generated as committed artifacts.
- The dashboard remains a local Dash application, not a deployed production service.

