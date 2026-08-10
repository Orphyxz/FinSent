# Research Dataset

Phase 10 adds explicit dataset construction for historical signal evaluation. Phase 11 adds bounded real historical-news acquisition for FNSPID.

## Import Path

Use the local CSV importer only with an explicit source file:

```powershell
python -m finsent.scripts.ingest_research_articles --file path\to\articles.csv --dataset-id my_dataset --dry-run
python -m finsent.scripts.ingest_research_articles --file path\to\articles.csv --dataset-id my_dataset --execute
```

Required row fields are:

- `title` or `headline`
- `published_at` or `timestamp`
- `symbol` or `ticker`

Optional fields include `exchange`, `source`, `publisher`, `url`, `summary`, `description`, `dedupe_hash`, `sentiment_label`, `sentiment_score`, `model_confidence`, `signal_confidence`, `impact_strength`, `analysis_provider`, and `parse_status`.

## Provenance

Imported rows are stored in `news_articles` with:

- `provider = local_import`
- `source_provider = local_csv` by default
- `leaf_provider = local_import`
- `data_mode = HISTORICAL_IMPORT`
- original/canonical URL fields
- raw symbol and canonical ticker/exchange
- imported stored sentiment if sentiment fields are present

The importer also links eligible articles to canonical instruments through `article_instruments`.

## Cohorts

`ResearchCohortBuilder` filters stored articles by symbol, market, date range, horizons, limit, seed, and optional holdout start date.

Each sample records:

- article id
- canonical instrument
- event timestamp
- dedupe key
- development/holdout split
- per-horizon Event Study V2 coverage
- eligibility status and exclusion reasons

## Fingerprints

Each cohort receives a stable SHA-256 fingerprint from the cohort configuration and selected article/instrument/horizon identities. It does not include API keys, absolute file paths, raw article bodies, or provider credentials.

## Limits

Phase 10 does not add a new DB schema column for article dataset ids. Dataset ids are preserved in import summaries, cohort configuration, experiment configuration, and exports.

## Phase 11 FNSPID Path

`python -m finsent.scripts.prepare_research_cohort` streams a bounded FNSPID subset, writes a source manifest, imports canonical article rows, and can acquire daily research prices. Dry-run is safe and write-free; `--execute` is required for files or database writes.

The initial Phase 11 subset is documented in `docs/INITIAL_RESEARCH_COHORT.md`.
