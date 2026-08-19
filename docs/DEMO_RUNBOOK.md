# Demo Runbook

## Before Presentation

1. Connect to the internet.
2. Open a terminal.
3. Enter the repository:

```bash
cd FinSent
```

4. Activate the virtual environment.

Windows:

```powershell
.\.venv\Scripts\activate
```

macOS:

```bash
source .venv/bin/activate
```

5. Run preflight:

```bash
python -m finsent.scripts.demo_preflight
```

6. Optionally warm FinBERT and the workspace:

```bash
python -m finsent.scripts.demo_preflight --warm
```

7. Start the dashboard:

```bash
python -m finsent.scripts.run_dashboard
```

8. Open:

```text
http://127.0.0.1:8050/
```

## Presentation Flow

1. Overview
2. Stock Research: NVDA
3. News Intelligence / FinBERT
4. Catalyst Intelligence
5. Signal V1 and Signal V2
6. Market Context Intelligence
7. Compare: AAPL / NVDA / TSLA
8. Research dashboard
9. System Status if asked about engineering reliability

## Recommended Symbols

Primary demo:

- `NVDA`: liquid US technology stock, frequent current coverage, sector ETF mapping to XLK.

Compare:

- `AAPL`, `NVDA`, `TSLA`: recognizable, liquid, different current-news/catalyst profiles.

Backup:

- `META`, `JPM`, `AMZN`: supported symbols with sector mappings and generally good provider coverage.

Do not promise that current news exists at every moment. If one symbol has sparse current news, switch to another supported symbol.

## Talking Points

Overview:

- This is the main live/latest workspace for a selected ticker.
- Market data and news come from configured providers, with local fallback states shown explicitly.
- The page combines sentiment, catalysts, market context, and signal summaries.
- System Status can explain provider health and cache behavior.

Stock Research:

- Current/latest price comes from Alpaca IEX when configured.
- News headlines are analyzed by FinBERT.
- Catalyst Intelligence explains what type of event is driving coverage.
- Market Context compares the stock against SPY and a sector ETF where available.
- Signals summarize evidence; they are not trading guarantees.

News Intelligence:

- Each headline carries sentiment, confidence, impact, and catalyst fields.
- Filters can isolate catalyst type and direction.
- Confidence is model/engineering confidence, not future-price probability.

Catalyst Intelligence:

- The classifier is deterministic and uses headline/summary evidence.
- It separates event type from sentiment.
- Event grouping reduces repeated coverage into understandable clusters.

Signal V1/V2:

- Signal V1 is the compact compatibility signal.
- Signal V2 separates news, momentum, volume, freshness, liquidity, and quality.
- V2 is explainable but was not proven superior on the locked final cohort.

Market Context:

- SPY, QQQ, and sector ETFs provide context for market-relative performance.
- Relative returns use aligned overlapping windows.
- Volatility, correlation, beta, and regime are descriptive context, not prediction.

Compare:

- Compare ranks selected symbols by sentiment, movement, catalyst coverage, and relative strength.
- Partial provider data is shown rather than hidden.

Research:

- This page reads locked Phase 16 artifacts.
- It does not rerun experiments.
- V1 beat V2.0 on strict and balanced accuracy in the final cohort; V2 had slightly higher directional accuracy on fewer directional calls.

## Failure Recovery

### No Price

Check System Status, verify Alpaca credentials in `.env`, restart the app, or use a backup symbol.

### Market Closed

Explain that latest available price is correctly shown. Current news may still update even when markets are closed.

### No News

Provider fallback may be active or a symbol may have sparse coverage. Use another liquid supported symbol such as AAPL, NVDA, TSLA, META, JPM, or AMZN.

### FinBERT Loading

Wait for first model initialization or run:

```bash
python -m finsent.scripts.demo_preflight --warm
```

### Compare Partial

Remove unavailable symbols or inspect provider status. Partial data is expected when providers return no current records.

### Internet Failure

Use the Research page and local data mode. Explain the live path separately from the locked historical evaluation.

## Exit Status For Preflight

- `0`: Core app checks passed. Live Alpaca may still be missing; in that case preflight prints `DEMO READY - OFFLINE MODE ONLY`.
- `1`: A core app check failed and needs attention before the demo.
