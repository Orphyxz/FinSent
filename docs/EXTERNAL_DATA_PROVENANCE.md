# External Data Provenance

## FNSPID News

- source name: FNSPID
- source identifier: `Zihan1004/FNSPID`
- source URL: `https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv`
- adapter version: `fnspid_adapter_v1`
- local subset path: `data/research_sources/fnspid/subsets/phase11_fnspid_aapl_amzn_2023_v1.csv`
- subset checksum: `479d285b9c2911e823a421239c0adccbc98c921e3cae5dfdbbb40fcac1d59db5`
- subset size: 47,104 bytes
- rows: 50

Manifest:

```text
data/research_sources/fnspid/MANIFEST.json
```

## Price Data

- source name: `yfinance_daily`
- source identifier: Yahoo Finance via yfinance
- adapter version: `yfinance_daily_price_adapter_v1`
- local path: `data/research_sources/yfinance_daily/prices/phase11_fnspid_aapl_amzn_2023_v1/`
- rows: 502
- symbols: AAPL, AMZN

Manifest:

```text
data/research_sources/yfinance_daily/MANIFEST.json
```

One later retry was rate-limited by yfinance and imported no additional rows. The previously imported rows remain the Phase 11 price source.

## Normalized Export

```text
data/research/normalized_articles_phase11_fnspid_aapl_amzn_2023_v1.csv
```

The normalized export contains title/summary metadata and canonical text hashes. It does not contain API keys, provider credentials, or generated synthetic articles.

## Phase 15 Final Holdout V3

Dataset id: `phase15_final_holdout_v3`. Source: FNSPID Nasdaq CSV via bounded byte ranges. Full source downloaded: false. Fingerprint: `8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e`.
