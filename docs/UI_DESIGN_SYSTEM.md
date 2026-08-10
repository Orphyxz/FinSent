# UI Design System

Phase 17 defines the current dashboard design language for FinSent.

## Visual Direction

- Theme: dark graphite financial analytics terminal.
- Typography: Segoe UI system stack.
- Surfaces: flat graphite panels with subtle borders, no decorative gradients, no ornamental backgrounds.
- Corners: compact radii, usually 6px to 8px.
- Density: compact cards, tables, metadata rows, and toolbar controls.

## Core Tokens

The active CSS tokens live in `finsent/app/dashboard/assets/dashboard.css`.

- Background: `#080a0d`, `#0d1014`
- Surface: `#12161b`, `#171c22`
- Border: `#2a3038`, `#20262e`
- Text: `#f4f7fa`, `#b4beca`, `#808b98`
- Accent: `#38bdf8`
- Positive: `#35c27a`
- Negative: `#ef5b5b`
- Warning: `#d6a63a`

## Component Rules

- Use `section_header` for page and panel headings.
- Use `research_metric` and `metric_cell` for compact numeric displays.
- Use `status_badge`, `signal_badge`, and `quality_badge` for state labels.
- Use `metadata_row` for label/value facts.
- Use Plotly charts on dark paper/plot backgrounds and keep chart titles concise.
- Cards are for individual panels and repeated items only; sections should not be nested cards.

## Responsive Behavior

- Wide screens use two-column research and chart grids.
- Below 1100px, major grids collapse to one column.
- Below 680px, shell padding and header type size are reduced, and action rows stack vertically.

