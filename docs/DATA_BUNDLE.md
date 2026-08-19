# Data Bundle

The Git repository intentionally excludes local data that is large, private, machine-specific, or regenerated during experiments.

## Not In Git

- `data/finsent.db`
- `archive/v1/`
- bounded local research-source subsets under `data/research_sources/`
- local application/research data under `data/research/`
- local provider outputs and cache-like files
- `.env`
- model caches such as Hugging Face or Torch cache directories

These files are excluded to avoid uploading databases, giant raw datasets, credentials, or machine-local cache state.

## Expected Bundle Contents

A complete handoff bundle may include:

```text
archive/v1/
data/finsent.db
data/research_sources/
data/research/
output/research/
DATA_BUNDLE_README.txt
```

The full raw FNSPID source should not be included. Only bounded subsets used by FinSent should be transferred.

## Data Story

Live data:
Alpaca/optional provider calls made during a local application run.

Local application DB:
`data/finsent.db`, containing local quotes, bars, articles, signal snapshots/runs, provider audit rows, and research storage tables.

Historical research data:
Bounded FNSPID subsets and Yahoo/yfinance price CSVs used to build research cohorts.

Locked final evaluation:
Tracked Phase 16 final artifacts under `output/research/phase16`, read by the Research dashboard without recomputation.

## Requirements By Demo Type

Live demo:
Code, Python dependencies, Alpaca credentials, internet, and writable SQLite path. Historical archives are not required for a live-only demo.

Research demo:
Tracked Phase 16 artifacts are enough for the Research page summary. The data bundle gives a fuller local machine state.

Full demo:
Code, dependencies, Alpaca credentials, local SQLite DB, research sources, archive, and output research artifacts restored from the bundle.

Current local sizes are intentionally not hardcoded here because databases and bundles change during demos. Use PowerShell `Get-ChildItem` or macOS `du -sh` to check current sizes.
