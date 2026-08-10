# Historical News Source Evaluation

Phase 11 evaluated historical financial-news sources before importing the first real cohort.

## Decision Summary

| Source | Decision | Readiness | Rationale |
|---|---|---|---|
| FNSPID | PREFERRED | Ready | Public research dataset with historical timestamps, tickers, titles, URLs, publishers, summaries/articles, citation, and reproducible source location. Full files are very large, so FinSent uses bounded streaming subsets only. |
| Marketaux historical news | SECONDARY | Unconfigured | Legitimate API with entity linkage and date filters, but no local `MARKETAUX_API_TOKEN` is configured. |
| Polygon News | SECONDARY | Unconfigured | Legitimate US provider with `published_utc` filters, but no local `POLYGON_API_KEY` is configured. |
| Alpaca News | SECONDARY | Unconfigured | Alpaca documents historical Benzinga news back to 2015, but no local Alpaca keys are configured. |
| Yahoo HTML scraping | REJECTED as primary | Deferred | Useful runtime fallback, but too brittle and weakly reproducible for the primary historical research corpus. |

## Source Notes

FNSPID is hosted at `https://huggingface.co/datasets/Zihan1004/FNSPID` and points to the GitHub project `https://github.com/Zdong104/FNSPID_Financial_News_Dataset`. The Hugging Face dataset card lists a 29.6 GB total size and CC BY-NC-4.0 terms. The GitHub README identifies 15.7 million financial-news records and 29.7 million stock-price records for 4,775 S&P 500 companies from 1999 to 2023.

Marketaux documentation is at `https://www.marketaux.com/documentation`.

Polygon News exposes `GET /v2/reference/news` with ticker and `published_utc` filters according to its client/API docs.

Alpaca historical news documentation is at `https://docs.alpaca.markets/us/docs/historical-news-data` and describes historical news dating back to 2015.

## Selected Source

FNSPID was selected for Phase 11 because it is public, research-oriented, ticker-linked, timestamped, and accessible without local provider credentials.

## Hard Limit

The full FNSPID CSV was not downloaded. The selected raw news file advertises a 23.2 GB content length, so Phase 11 streams rows and stops once the configured symbol/date/record limit is satisfied.
