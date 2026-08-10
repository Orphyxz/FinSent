# Research Data Ingestion

Phase 11 adds a bounded real-data ingestion path.

## CLI

Dry-run:

```powershell
python -m finsent.scripts.prepare_research_cohort --source fnspid --symbols AAPL AMZN --start-date 2023-01-01 --end-date 2023-12-31 --limit 50 --horizons 1d --dry-run
```

Execute:

```powershell
python -m finsent.scripts.prepare_research_cohort --source fnspid --symbols AAPL AMZN --start-date 2023-01-01 --end-date 2023-12-31 --limit 50 --horizons 1d --batch-id phase11_fnspid_aapl_amzn_2023_v1 --execute --acquire-prices --export
```

## FNSPID Adapter

`FNSPIDAdapter` maps raw FNSPID rows into a canonical historical article subset with:

- source record id
- UTC publication timestamp
- ticker and exchange
- title
- summary
- URL
- publisher
- source dataset/file
- deterministic dedupe hash
- canonical text hash

The text policy is `title + available summary`. The adapter prefers provided summary columns and only uses an article excerpt if no summary is present.

## Cache Location

External research data is stored under:

```text
data/research_sources/
```

Normalized article exports are stored under:

```text
data/research/
```

These paths are ignored by default, except source manifests.

## Price Data

Phase 11 used `yfinance_daily` as a bounded daily research price source for the selected US symbols. Daily bars are normalized to US market close timestamps before Event Study V2 coverage checks.

Daily bars support Track A (`1D`) only. Phase 11 does not compute fake `1H` or `4H` results.

## Manifests

Every executed external acquisition writes or appends a `MANIFEST.json` with source name, source identifier, filters, record count, local relative path, checksum where practical, and adapter version.

## Phase 15 Remote Range Acquisition

The FNSPID Nasdaq CSV is accessed via bounded HTTP byte ranges around ticker regions. The full 23GB source is not downloaded.
