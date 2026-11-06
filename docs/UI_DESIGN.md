# Dashboard UI Design

The dashboard is a Dash app styled by one stylesheet, `finsent/app/dashboard/assets/dashboard.css`. UI changes never alter providers, signals, FinBERT, Catalyst Intelligence, Market Context formulas, the database schema, or the locked Phase 16 research artifacts.

## Structure

| Area | Source | Notes |
|---|---|---|
| App shell and callbacks | `app.py`, `layout.py` | Navigation, control dock, page router, stores |
| Shared controls | `components.py` | Navbar, market/search controls, filters, landing search, footer |
| Small primitives | `ui_components.py` | Section headers, status badges, research metrics, metadata rows, empty states |
| Data shaping and charts | `view_model.py` | Dashboard state, Plotly figures, status panels |
| Intelligence modules | `intelligence.py`, `intel_callbacks.py` | Watchlist aggregates, compare profiles, and the callbacks for the six modules |
| Charts and widgets | `charts.py`, `widgets.py` | Themed Plotly figures, SVG sparklines, index/watchlist/news/signal building blocks |
| Pages | `pages/*.py` | Overview (`summary.py`), Stock Research, News Intelligence, Compare, Research, Alerts |

Supporting services: `analysis/technicals.py` (SMA, EMA, RSI, MACD, Bollinger, volatility), `services/market_overview.py` (cached daily history, index levels, watchlist quotes), `services/entity_extraction.py` (rule-based entities) and `services/event_explorer.py` (exploratory multi-window event study over the locked holdout).

## Modules

| Module | Page | What it shows |
|---|---|---|
| A. Executive intelligence | Overview | Market sentiment gauge, index cards, watchlist with sparklines and V1/V2, top bullish/bearish catalysts, today's events, sentiment movers, signal distribution, provider strip |
| B. Stock research | Stock Research | Quote header with 52-week range, OHLCV workbench (1D–1Y, candles/line, SMA/EMA/Bollinger, volume/RSI/MACD), technical snapshot, sentiment history, market and sector context |
| C. News intelligence | News Intelligence | Article cards with sentiment, confidence, entities and catalyst; sentiment donut; catalyst breakdown; sentiment, symbol, catalyst and direction filters |
| D. Explainable signals | Stock Research | V1 vs V2 cards, V2 contribution chart, weight table (news 55%, momentum 35%, volume 10%) and trust modifiers |
| E. Multi-stock comparison | Compare | Up to five stocks: snapshot cards, normalized performance, sentiment mix, catalyst distribution, volatility, V1/V2 matrix |
| F. Research laboratory | Research | Locked Phase 16 metrics, precision/recall/F1, confusion matrices, and the exploratory 1D/3D/5D abnormal-return explorer (CSV export) |
| Market Map | Market Map | Sector treemap of every primary listing coloured by day change, breadth strip, gainers, losers, per-sector advancers vs decliners |

Further features: benchmark relative strength on Stock Research (`services/benchmarks.py`, SPY + sector ETF or NIFTY 50 + NSE sector index), FinBERT word explanations on news cards (`services/sentiment_explainer.py`), per-market custom watchlists in browser storage (`watchlist-store`), a print/PDF report (`@media print`), and keyboard shortcuts (`assets/shortcuts.js`: `/` search, `1`–`7` pages, `P` print, `Esc` close popovers).

## Performance

- Daily bars, index levels and watchlist quotes are cached in memory (15 and 5 minutes); the overview snapshot is served stale-while-revalidate, rebuilt in a background thread after 60 seconds.
- The dashboard launcher warms these caches and the event explorer in the background at startup, then a small scheduler (`services/scheduler.py`) refreshes watchlist news every 15 minutes and the market map and indices every 2 minutes.
- The market map uses one Alpaca multi-symbol snapshot call for US and Yahoo Chart spark batches of 20 for NSE, instead of one request per stock.
- The price chart callback reads only cached bars, so indicator and period toggles redraw without rebuilding dashboard state.
- Sparklines are inline SVG data URIs rather than Plotly graphs, keeping index and watchlist cards light.

## Layout

- **Control dock.** Market selector, company search, Filters and System status share one bar (`.control-dock`). Inner wrappers use `display: contents`, so the controls sit in a single CSS grid row. Filters and Status open as pop-up panels instead of pushing the page down.
- **Page rhythm.** Every page is a grid with 16px gaps. Cards use 20px × 22px padding and 12px corners. Cards in the same row share one height.
- **Status strip.** Market state is one line: a green (open) or amber (closed) dot, the state, and the data source and freshness.
- **Simple and Analyst views.** `.simple-only` and `.analyst-only` classes switch content. The two views answer different questions, as described below.

## Simple vs Analyst

Simple answers "what do I need to know?" in plain English. Analyst shows the working. New detail belongs in Analyst unless a non-specialist needs it to act on the page.

| Page | Simple | Analyst adds |
|---|---|---|
| Overview | One-paragraph market brief, sentiment gauge, index cards, watchlist (price, day, trend, signal), top 3 catalysts each way | Provider strip, sentiment, news count, 1M, RSI, volatility and V1/V2 columns, signal distribution, movers, correlation matrix, today's events, full focus-stock section |
| Stock Research | Plain-English verdict, price line, key catalysts, headlines | Candles, overlays, volume/RSI/MACD, technicals, signal explainer, risk profile (Sharpe, Sortino, drawdown, rolling beta, return distribution), relative strength, sentiment history, market context, event timeline |
| News Intelligence | One-line summary, sentiment filter, headlines | Filters, summary band, confidence, entities, catalysts, word explanations, donut, breakdown, impact map, headline terminal with CSV export |
| Compare | Stock cards, normalized performance, written brief | Sentiment mix, catalyst distribution, volatility, V1/V2 matrix, correlation matrix, market context, intraday bars |
| Market Map | Treemap, gainers, losers | Tile sizing, breadth strip, sector breadth |
| Research | Plain-English findings and three headline numbers | All locked metrics, precision/recall/F1, confusion matrices, event explorer, calibration and component findings |
| Alerts | Alert feed | Status strip, summary, sentiment trend, sector mood |

## Visual language

- Dark surfaces (`--bg-primary #0a0c0e`, `--surface #101315`), soft borders, and green/red reserved for direction and status.
- System font stack (SF Pro on macOS, Segoe UI on Windows) so the app works offline. Weights 500–700; uppercase only for small labels.
- Pill-shaped tabs, segmented toggles and badges. Metric values use tabular numbers.
- Charts share the card background (`PALETTE["paper"]`), hide the Plotly mode bar, and cap the main price chart at 560px.

## Responsive behavior

- At 1100px and below, search moves to its own row and the nav tabs scroll sideways.
- At 680px and below, controls stack, padding tightens, and the page never scrolls horizontally.

## Accessibility

- Focus outlines use the accent color on links, buttons, inputs and dropdowns.
- Segmented controls keep native radio inputs (visually hidden), so keyboard and screen-reader behavior is preserved.
