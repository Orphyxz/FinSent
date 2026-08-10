# Dataset Registry

Phase 5 makes local dataset provenance explicit. CSV files remain intentional project resources; they are not technical debt simply because they are CSVs.

## Registered Dataset Roles

| Dataset | Role | Status Policy |
|---|---|---|
| `archive/v1/*.csv` | Offline NSE historical/import/reference data | Keep. Default scan is sampled and marked partial unless deep-scanned. Not a live quote substitute. |
| `All_Indian_Stocks_listed_in_nifty500.csv` | India company universe/reference | Keep as reference data. |
| `6000 Largest Companies ranked by Market Cap.csv` | US company universe/reference | Keep as reference data. |
| `SnP_daily_update.csv` | Intended US historical price file | Keep guarded. Current local copy is a Git LFS pointer and is classified `BROKEN`. Do not fabricate replacement data. |
| `data/research_sources/fnspid` | Phase 11 bounded FNSPID historical-news subset | Keep local/generated. Manifest is reproducibility metadata; subset data remains ignored. |
| `data/research_sources/yfinance_daily` | Phase 11 bounded daily research price subset | Keep local/generated. Daily bars support only `1D` Event Study V2. |

## Scanner

`finsent/app/services/dataset_registry.py` provides an explicit `DatasetScanner`.

It can inspect:

- path existence
- file size
- Git LFS pointer state
- rows and columns
- date range where a `Date` column exists
- inferred symbol count
- duplicate or malformed dates
- missing-value rates for OHLCV columns
- checksum for files

Directory scans do not deep-read the large archive by default. Deep scans are explicit research/developer operations.

## Persistence

`dataset_metadata` stores:

- dataset id and name
- path
- type, market, frequency
- date range
- symbol and row counts where known
- status
- source
- checksum where practical
- scan timestamp
- columns and issues JSON
- notes

The registry does not import every CSV into SQLite and does not mutate files.
