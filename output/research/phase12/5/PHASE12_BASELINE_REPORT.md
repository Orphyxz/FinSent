# Phase 12 Locked-Cohort Baseline

## Preregistration
Dataset id: `phase12_locked_multisymbol_v1`
Preregistration fingerprint: `f882035bef86d356f4207e58bf1fa751943e4c4b4fb81b71dc7ff8dc38edf306`

## Dataset
Source: FNSPID / Stock_news/All_external.csv
Cohort fingerprint: `b6299de35bd8bbd6ab88b2d071329e1dba227f356f07597c9081489fbe217db2`

## Symbols
AAPL, AMZN, GOOGL, NVDA, TSLA

## Dates
2020-05-01T00:00:00 to 2020-06-15T23:59:59

## Price Source
yahoo_chart_daily; basis: Unadjusted Yahoo Finance chart quote.close; adjclose is fetched for audit but not used by Event Study V2

## Sentiment Model
FinBERT only

## Development Split
{
  "v1": {
    "balanced_accuracy": 0.23232323232323235,
    "correct": 30,
    "directional_accuracy": 0.3333333333333333,
    "directional_correct": 18,
    "directional_eligible": 54,
    "f1": {
      "BEARISH": null,
      "BULLISH": 0.32142857142857145,
      "NEUTRAL": 0.31578947368421056
    },
    "incorrect": 88,
    "neutral_outcome_count": 33,
    "neutral_prediction_count": 43,
    "precision": {
      "BEARISH": 0.0,
      "BULLISH": 0.3103448275862069,
      "NEUTRAL": 0.27906976744186046
    },
    "recall": {
      "BEARISH": 0.0,
      "BULLISH": 0.3333333333333333,
      "NEUTRAL": 0.36363636363636365
    },
    "strict_accuracy": 0.2542372881355932,
    "total": 118,
    "wilson_interval": [
      0.18428115742871232,
      0.33969095061977017
    ]
  },
  "v2": {
    "balanced_accuracy": 0.29236812570145904,
    "correct": 34,
    "directional_accuracy": 0.3170731707317073,
    "directional_correct": 13,
    "directional_eligible": 41,
    "f1": {
      "BEARISH": null,
      "BULLISH": 0.25742574257425743,
      "NEUTRAL": 0.4285714285714286
    },
    "incorrect": 84,
    "neutral_outcome_count": 33,
    "neutral_prediction_count": 65,
    "precision": {
      "BEARISH": 0.0,
      "BULLISH": 0.2765957446808511,
      "NEUTRAL": 0.3230769230769231
    },
    "recall": {
      "BEARISH": 0.0,
      "BULLISH": 0.24074074074074073,
      "NEUTRAL": 0.6363636363636364
    },
    "strict_accuracy": 0.288135593220339,
    "total": 118,
    "wilson_interval": [
      0.21412021512201196,
      0.3755109125059902
    ]
  }
}

## Holdout Split
{
  "v1": {
    "balanced_accuracy": 0.1388888888888889,
    "correct": 5,
    "directional_accuracy": 0.16666666666666666,
    "directional_correct": 5,
    "directional_eligible": 30,
    "f1": {
      "BEARISH": null,
      "BULLISH": 0.25,
      "NEUTRAL": null
    },
    "incorrect": 36,
    "neutral_outcome_count": 0,
    "neutral_prediction_count": 11,
    "precision": {
      "BEARISH": 0.0,
      "BULLISH": 0.22727272727272727,
      "NEUTRAL": 0.0
    },
    "recall": {
      "BEARISH": 0.0,
      "BULLISH": 0.2777777777777778,
      "NEUTRAL": null
    },
    "strict_accuracy": 0.12195121951219512,
    "total": 41,
    "wilson_interval": [
      0.053232579973408245,
      0.25544507648844866
    ]
  },
  "v2": {
    "balanced_accuracy": 0.1111111111111111,
    "correct": 4,
    "directional_accuracy": 0.14285714285714285,
    "directional_correct": 4,
    "directional_eligible": 28,
    "f1": {
      "BEARISH": null,
      "BULLISH": 0.1904761904761905,
      "NEUTRAL": null
    },
    "incorrect": 37,
    "neutral_outcome_count": 0,
    "neutral_prediction_count": 13,
    "precision": {
      "BEARISH": 0.0,
      "BULLISH": 0.16666666666666666,
      "NEUTRAL": 0.0
    },
    "recall": {
      "BEARISH": 0.0,
      "BULLISH": 0.2222222222222222,
      "NEUTRAL": null
    },
    "strict_accuracy": 0.0975609756097561,
    "total": 41,
    "wilson_interval": [
      0.0385964597529614,
      0.22547975519030555
    ]
  }
}

## Class Distribution
{
  "DEVELOPMENT": {
    "finbert": {
      "BEARISH": 17,
      "BULLISH": 79,
      "NEUTRAL": 46
    },
    "realized": {
      "BEARISH": 31,
      "BULLISH": 54,
      "NEUTRAL": 33
    },
    "v1": {
      "BEARISH": 17,
      "BULLISH": 79,
      "NEUTRAL": 46
    },
    "v2": {
      "BEARISH": 6,
      "BULLISH": 68,
      "NEUTRAL": 68
    }
  },
  "HOLDOUT": {
    "finbert": {
      "BEARISH": 8,
      "BULLISH": 22,
      "NEUTRAL": 11
    },
    "realized": {
      "BEARISH": 23,
      "BULLISH": 18
    },
    "v1": {
      "BEARISH": 8,
      "BULLISH": 22,
      "NEUTRAL": 11
    },
    "v2": {
      "BEARISH": 4,
      "BULLISH": 24,
      "NEUTRAL": 13
    }
  }
}

## Baselines
{
  "DEVELOPMENT": {
    "ALWAYS_NEUTRAL": {
      "balanced_accuracy": 0.3333333333333333,
      "correct": 33,
      "directional_accuracy": null,
      "directional_correct": 0,
      "directional_eligible": 0,
      "f1": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.4370860927152318
      },
      "incorrect": 85,
      "majority_class": null,
      "neutral_outcome_count": 33,
      "neutral_prediction_count": 118,
      "precision": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.2796610169491525
      },
      "prediction_rule": "ALWAYS_NEUTRAL",
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.0,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.2796610169491525,
      "total": 118,
      "wilson_interval": [
        0.20660883500092975,
        0.36660753773219246
      ]
    },
    "MAJORITY_CLASS": {
      "balanced_accuracy": 0.3333333333333333,
      "correct": 54,
      "directional_accuracy": 0.6352941176470588,
      "directional_correct": 54,
      "directional_eligible": 85,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.627906976744186,
        "NEUTRAL": null
      },
      "incorrect": 64,
      "majority_class": "BULLISH",
      "neutral_outcome_count": 33,
      "neutral_prediction_count": 0,
      "precision": {
        "BEARISH": null,
        "BULLISH": 0.4576271186440678,
        "NEUTRAL": null
      },
      "prediction_rule": "MAJORITY_CLASS",
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 1.0,
        "NEUTRAL": 0.0
      },
      "strict_accuracy": 0.4576271186440678,
      "total": 118,
      "wilson_interval": [
        0.3704897254617516,
        0.5474365000638488
      ]
    },
    "NEWS_DIRECTION_ONLY": {
      "balanced_accuracy": 0.23232323232323235,
      "correct": 30,
      "directional_accuracy": 0.3333333333333333,
      "directional_correct": 18,
      "directional_eligible": 54,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.32142857142857145,
        "NEUTRAL": 0.31578947368421056
      },
      "incorrect": 88,
      "majority_class": null,
      "neutral_outcome_count": 33,
      "neutral_prediction_count": 43,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.3103448275862069,
        "NEUTRAL": 0.27906976744186046
      },
      "prediction_rule": "NEWS_DIRECTION_ONLY",
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.3333333333333333,
        "NEUTRAL": 0.36363636363636365
      },
      "strict_accuracy": 0.2542372881355932,
      "total": 118,
      "wilson_interval": [
        0.18428115742871232,
        0.33969095061977017
      ]
    }
  },
  "HOLDOUT": {
    "ALWAYS_NEUTRAL": {
      "balanced_accuracy": 0.0,
      "correct": 0,
      "directional_accuracy": null,
      "directional_correct": 0,
      "directional_eligible": 0,
      "f1": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": null
      },
      "incorrect": 41,
      "majority_class": null,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 41,
      "precision": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.0
      },
      "prediction_rule": "ALWAYS_NEUTRAL",
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.0,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.0,
      "total": 41,
      "wilson_interval": [
        0.0,
        0.08567044886890744
      ]
    },
    "MAJORITY_CLASS": {
      "balanced_accuracy": 0.5,
      "correct": 23,
      "directional_accuracy": 0.5609756097560976,
      "directional_correct": 23,
      "directional_eligible": 41,
      "f1": {
        "BEARISH": 0.71875,
        "BULLISH": null,
        "NEUTRAL": null
      },
      "incorrect": 18,
      "majority_class": "BEARISH",
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 0,
      "precision": {
        "BEARISH": 0.5609756097560976,
        "BULLISH": null,
        "NEUTRAL": null
      },
      "prediction_rule": "MAJORITY_CLASS",
      "recall": {
        "BEARISH": 1.0,
        "BULLISH": 0.0,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.5609756097560976,
      "total": 41,
      "wilson_interval": [
        0.41040265151757305,
        0.7011009522789017
      ]
    },
    "NEWS_DIRECTION_ONLY": {
      "balanced_accuracy": 0.1388888888888889,
      "correct": 5,
      "directional_accuracy": 0.16666666666666666,
      "directional_correct": 5,
      "directional_eligible": 30,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.25,
        "NEUTRAL": null
      },
      "incorrect": 36,
      "majority_class": null,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 11,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.22727272727272727,
        "NEUTRAL": 0.0
      },
      "prediction_rule": "NEWS_DIRECTION_ONLY",
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.2777777777777778,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.12195121951219512,
      "total": 41,
      "wilson_interval": [
        0.053232579973408245,
        0.25544507648844866
      ]
    }
  }
}

## Signal V1
Metrics are split above. Interpret every percentage with its N.

## Signal V2
Metrics are split above. Signal V2 weights, thresholds, confidence, news decay, momentum, and volume behavior were not changed.

## Paired Comparison
{
  "DEVELOPMENT": {
    "both_correct": 25,
    "both_wrong": 79,
    "mcnemar": {
      "applicable": true,
      "discordant": 14,
      "p_value_chi_square_approx": 0.4226780741706354,
      "statistic": 0.6428571428571429
    },
    "n": 118,
    "v1_correct_v2_wrong": 5,
    "v1_wrong_v2_correct": 9
  },
  "HOLDOUT": {
    "both_correct": 4,
    "both_wrong": 36,
    "mcnemar": {
      "applicable": false,
      "discordant": 1,
      "p_value_chi_square_approx": 1.0,
      "statistic": 0.0
    },
    "n": 41,
    "v1_correct_v2_wrong": 1,
    "v1_wrong_v2_correct": 0
  }
}

## Component Diagnostics
{
  "news": {
    "correct_mean": 0.27073407550912254,
    "incorrect_mean": 0.29613719373580466,
    "mean": 0.2908622292952914,
    "n": 183
  },
  "price_momentum": {
    "correct_mean": 0.44396641338588544,
    "incorrect_mean": 0.3273813354515154,
    "mean": 0.3515902587384337,
    "n": 183
  },
  "volume_confirmation": {
    "correct_mean": 0.05990342768438499,
    "incorrect_mean": 0.09026262568580323,
    "mean": 0.0839585299259459,
    "n": 183
  }
}

## Data Quality
{
  "directions": {
    "BEARISH": 10,
    "BULLISH": 92,
    "NEUTRAL": 81
  },
  "labels": {
    "bearish": 10,
    "bullish": 92,
    "neutral": 81
  },
  "momentum_available": 183,
  "n": 183,
  "news_available": 183,
  "realized": {
    "BEARISH": 54,
    "BULLISH": 72,
    "NEUTRAL": 33,
    "nan": 24
  },
  "score_max": 0.4415884916744016,
  "score_mean": 0.16999889063701637,
  "score_min": -0.3547540212684199,
  "signal_modes": {
    "NEWS_PLUS_MARKET": 183
  },
  "volume_available": 183
}

## Limitations
Daily bars support 1D only. Gemini remains unconfigured. This is a bounded FNSPID/yfinance cohort, not a final market-wide claim.

## Conclusions Allowed
On this locked cohort, the exported metrics describe baseline behavior for the unchanged engines.

## Conclusions NOT Allowed
Do not claim a universal winner, tune V2 against these results, or infer profitability.