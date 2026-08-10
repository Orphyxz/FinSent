# Phase 15 Final Holdout Acquisition

FINAL PERFORMANCE NOT EVALUATED.

## Why Phase 14 Holdout Failed
Previous bounded prefix scans started at byte zero in an alphabetically ticker-sorted CSV, so early tickers consumed scan budget before later target symbols were reached.

## FNSPID Physical Layout
{
  "alternative_formats": "Hugging Face API exposes All_external.csv and nasdaq_exteral_data.csv only; no Parquet files reported.",
  "full_source_downloaded": false,
  "organization": "Rows are clustered/sorted by Stock_symbol alphabetically; dates within symbol are generally reverse chronological or mixed by source region.",
  "sampled_regions": {
    "0": "A",
    "11_350_000_000": "NVDA region",
    "15_050_000_000": "TSLA region",
    "1_450_000_000": "AMZN region",
    "80_000_000": "AAP/AAPL region",
    "8_200_000_000": "GOOG region; GOOGL not observed as supported source symbol"
  },
  "size_bytes": 23232979597,
  "source_file": "Stock_news/nasdaq_exteral_data.csv"
}

## Previous Sampling Bug / Limitation
Filtering occurred after source iteration, and acquisition stopped at global scan caps. In a ticker-grouped source, this is not a stratified sample.

## New Acquisition Method
Remote HTTP byte-range ticker-region extraction with independent per-symbol quotas and chronological evenly spaced within-symbol sampling.

## Availability by Symbol
{
  "by_symbol_month": {
    "AAPL": {
      "2023-01": 468,
      "2023-02": 376,
      "2023-03": 406,
      "2023-04": 419,
      "2023-05": 531,
      "2023-06": 504,
      "2023-07": 483,
      "2023-08": 571,
      "2023-09": 674,
      "2023-10": 553,
      "2023-11": 472,
      "2023-12": 296
    },
    "AMZN": {
      "2023-03": 318,
      "2023-04": 525,
      "2023-05": 431,
      "2023-06": 521,
      "2023-07": 528,
      "2023-08": 602,
      "2023-09": 594,
      "2023-10": 238
    },
    "NVDA": {
      "2023-01": 153,
      "2023-02": 240,
      "2023-03": 269,
      "2023-04": 299,
      "2023-05": 554,
      "2023-06": 611,
      "2023-07": 500,
      "2023-08": 42
    },
    "TSLA": {
      "2023-01": 540,
      "2023-02": 364,
      "2023-03": 376,
      "2023-04": 521,
      "2023-05": 405,
      "2023-06": 508,
      "2023-07": 641,
      "2023-08": 478,
      "2023-09": 438
    }
  },
  "notes": [
    "FNSPID Nasdaq source uses GOOG in the Alphabet region; local registry supports GOOGL, so GOOG is documented but not forced into the final holdout.",
    "No full 23GB source download; bounded byte ranges only."
  ],
  "source_records_by_symbol": {
    "AAPL": 5753,
    "AMZN": 3757,
    "NVDA": 2668,
    "TSLA": 4271
  },
  "source_windows": {
    "AAPL": [
      80000000,
      170000000
    ],
    "AMZN": [
      1430000000,
      1520000000
    ],
    "NVDA": [
      11330000000,
      11410000000
    ],
    "TSLA": [
      15040000000,
      15100000000
    ]
  }
}

## Window Selection Rule
Earliest 90-day future window with >=3 supported symbols, >=20 candidate articles per represented symbol, and >=90 total candidate articles; tie-break by represented symbol count then balance.

## Selected Window
{
  "adequate": true,
  "algorithm": "Earliest 90-day future window with >=3 supported symbols, >=20 candidate articles per represented symbol, and >=90 total candidate articles; tie-break by represented symbol count then balance.",
  "blockers": [],
  "candidate_counts": {
    "AAPL": 1250,
    "AMZN": 318,
    "NVDA": 662,
    "TSLA": 1280
  },
  "end_date": "2023-03-31T23:59:59",
  "represented_symbols": [
    "AAPL",
    "AMZN",
    "NVDA",
    "TSLA"
  ],
  "start_date": "2023-01-01T00:00:00"
}

## Article Acquisition
{
  "acquired_counts": {
    "AAPL": 40,
    "AMZN": 40,
    "NVDA": 40,
    "TSLA": 40
  },
  "checksum_sha256": "54cfd1013ab4c4fba9db0e29ac2e235116dd1156a2873476c20ce9fd67554314",
  "duplicate_rows": 0,
  "requested_symbols": [
    "AAPL",
    "AMZN",
    "GOOGL",
    "NVDA",
    "TSLA"
  ],
  "selected_window": {
    "adequate": true,
    "algorithm": "Earliest 90-day future window with >=3 supported symbols, >=20 candidate articles per represented symbol, and >=90 total candidate articles; tie-break by represented symbol count then balance.",
    "blockers": [],
    "candidate_counts": {
      "AAPL": 1250,
      "AMZN": 318,
      "NVDA": 662,
      "TSLA": 1280
    },
    "end_date": "2023-03-31T23:59:59",
    "represented_symbols": [
      "AAPL",
      "AMZN",
      "NVDA",
      "TSLA"
    ],
    "start_date": "2023-01-01T00:00:00"
  },
  "source_bytes_requested": 320000000,
  "source_candidate_counts": {
    "AAPL": 5753,
    "AMZN": 3757,
    "NVDA": 2668,
    "TSLA": 4271
  },
  "subset_path": "data\\research_sources\\fnspid\\subsets\\phase15_final_holdout_v3.csv",
  "written_rows": 160
}

## Price Coverage
Yahoo chart daily prices with 30 days before and 10 days after the selected window.

## Adequacy
{
  "adequate": true,
  "article_ids": [
    264,
    343,
    383,
    265,
    384,
    344,
    385,
    266,
    386,
    345,
    267,
    387,
    268,
    388,
    269,
    346,
    389,
    270,
    390,
    271,
    347,
    391,
    272,
    392,
    348,
    273,
    274,
    349,
    393,
    394,
    275,
    395,
    350,
    396,
    276,
    351,
    397,
    398,
    277,
    278,
    399,
    279,
    352,
    280,
    400,
    281,
    353,
    401,
    282,
    283,
    402,
    354,
    284,
    403,
    355,
    285,
    356,
    286,
    357,
    404,
    358,
    405,
    287,
    359,
    406,
    288,
    360,
    361,
    362,
    363,
    407,
    289,
    364,
    408,
    365,
    409,
    290,
    366,
    410,
    291,
    367,
    411,
    292,
    368,
    412,
    293,
    369,
    413,
    294,
    304,
    305,
    306,
    370,
    307,
    371,
    308,
    414,
    295,
    309,
    310,
    311,
    312,
    313,
    296,
    314,
    372,
    415,
    315,
    316,
    373,
    297,
    317,
    318,
    374,
    319,
    320,
    321,
    375,
    416,
    322,
    323,
    376,
    298,
    324,
    325,
    326,
    377,
    417,
    299,
    327,
    328,
    378,
    329,
    330,
    379,
    300,
    331,
    332,
    418,
    301,
    333,
    334,
    380,
    335,
    336,
    302,
    337,
    338,
    339,
    340,
    381,
    419,
    303,
    341,
    342,
    382,
    420
  ],
  "blockers": [],
  "candidate_n": 157,
  "dataset_id": "phase15_final_holdout_v3",
  "date_end": "2023-03-31T00:00:00",
  "date_start": "2023-01-03T00:00:00",
  "eligible_per_symbol": {
    "AMZN": 39,
    "NVDA": 37,
    "TSLA": 35
  },
  "fingerprint": "8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e",
  "manifest_path": "data\\research_sources\\fnspid\\MANIFEST.json",
  "status": "FINAL_HOLDOUT_V3_LOCKED",
  "technically_eligible_n": 111
}

## Fingerprint
8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e

## Lock Status
FINAL_HOLDOUT_V3_LOCKED

## Performance Status
Predictive performance, realized directions, returns, FinBERT outputs, and Signal V1/V2 runs were not generated.