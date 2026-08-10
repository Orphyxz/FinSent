# Phase 13 Error Analysis

All findings use Phase 12 DEVELOPMENT rows only.

```json
{
  "component_agreement": {
    "NEWS_BULLISH_MARKET_BULLISH": {
      "metrics": {
        "balanced_accuracy": 0.46222222222222226,
        "correct": 26,
        "directional_accuracy": 0.37142857142857144,
        "directional_correct": 13,
        "directional_eligible": 35,
        "f1": {
          "BEARISH": null,
          "BULLISH": 0.4193548387096774,
          "NEUTRAL": 0.6190476190476191
        },
        "incorrect": 38,
        "neutral_outcome_count": 25,
        "neutral_prediction_count": 17,
        "precision": {
          "BEARISH": null,
          "BULLISH": 0.2765957446808511,
          "NEUTRAL": 0.7647058823529411
        },
        "recall": {
          "BEARISH": 0.0,
          "BULLISH": 0.8666666666666667,
          "NEUTRAL": 0.52
        },
        "strict_accuracy": 0.40625,
        "total": 64,
        "wilson_interval": [
          0.29456724435258885,
          0.528550134954503
        ]
      },
      "n": 64
    },
    "NEWS_MARKET_CONFLICT": {
      "metrics": {
        "balanced_accuracy": 0.3333333333333333,
        "correct": 7,
        "directional_accuracy": 0.0,
        "directional_correct": 0,
        "directional_eligible": 6,
        "f1": {
          "BEARISH": null,
          "BULLISH": null,
          "NEUTRAL": 0.358974358974359
        },
        "incorrect": 31,
        "neutral_outcome_count": 7,
        "neutral_prediction_count": 32,
        "precision": {
          "BEARISH": 0.0,
          "BULLISH": null,
          "NEUTRAL": 0.21875
        },
        "recall": {
          "BEARISH": 0.0,
          "BULLISH": 0.0,
          "NEUTRAL": 1.0
        },
        "strict_accuracy": 0.18421052631578946,
        "total": 38,
        "wilson_interval": [
          0.09221648453257492,
          0.33419168341511346
        ]
      },
      "n": 38
    },
    "ONE_COMPONENT_NEUTRAL": {
      "metrics": {
        "balanced_accuracy": 0.3333333333333333,
        "correct": 1,
        "directional_accuracy": null,
        "directional_correct": 0,
        "directional_eligible": 0,
        "f1": {
          "BEARISH": null,
          "BULLISH": null,
          "NEUTRAL": 0.11764705882352941
        },
        "incorrect": 15,
        "neutral_outcome_count": 1,
        "neutral_prediction_count": 16,
        "precision": {
          "BEARISH": null,
          "BULLISH": null,
          "NEUTRAL": 0.0625
        },
        "recall": {
          "BEARISH": 0.0,
          "BULLISH": 0.0,
          "NEUTRAL": 1.0
        },
        "strict_accuracy": 0.0625,
        "total": 16,
        "wilson_interval": [
          0.01111905730833121,
          0.2832926836802987
        ]
      },
      "n": 16
    }
  },
  "component_distributions": {
    "momentum": {
      "max": 1.0,
      "mean": 0.3353537087246431,
      "median": 0.2453221353844653,
      "min": -0.318304422024358,
      "n": 118,
      "q1": 0.18742774663311823,
      "q3": 0.46257563072974334,
      "std": 0.2855526172136722
    },
    "news": {
      "max": 1.0,
      "mean": 0.19462759886797082,
      "median": 0.139004820196955,
      "min": -1.0,
      "n": 118,
      "q1": -0.0729597790122159,
      "q3": 0.5906793665785838,
      "std": 0.4479360171452804
    },
    "volume": {
      "max": 0.5,
      "mean": 0.050560273252788404,
      "median": 0.028768788862957584,
      "min": -0.5,
      "n": 118,
      "q1": 0.0008806141475179302,
      "q3": 0.08223651115858749,
      "std": 0.12461574247022342
    }
  },
  "error_categories": {
    "NEUTRAL_BAND_MISS": 44,
    "NEWS_MARKET_AGREE_WRONG": 34,
    "NEWS_MARKET_CONFLICT": 6
  },
  "incorrect": 84,
  "n": 118,
  "per_symbol": {
    "US:AAPL": {
      "balanced_accuracy": 0.14285714285714285,
      "n": 30,
      "realized_distribution": {
        "BULLISH": 16,
        "NEUTRAL": 14
      },
      "signal_distribution": {
        "BEARISH": 3,
        "BULLISH": 10,
        "NEUTRAL": 17
      },
      "strict_accuracy": 0.13333333333333333
    },
    "US:AMZN": {
      "balanced_accuracy": 0.3333333333333333,
      "n": 25,
      "realized_distribution": {
        "BEARISH": 3,
        "BULLISH": 10,
        "NEUTRAL": 12
      },
      "signal_distribution": {
        "BULLISH": 3,
        "NEUTRAL": 22
      },
      "strict_accuracy": 0.48
    },
    "US:GOOGL": {
      "balanced_accuracy": 0.2380952380952381,
      "n": 22,
      "realized_distribution": {
        "BEARISH": 5,
        "BULLISH": 10,
        "NEUTRAL": 7
      },
      "signal_distribution": {
        "BEARISH": 3,
        "BULLISH": 2,
        "NEUTRAL": 17
      },
      "strict_accuracy": 0.22727272727272727
    },
    "US:NVDA": {
      "balanced_accuracy": 0.375,
      "n": 12,
      "realized_distribution": {
        "BEARISH": 8,
        "BULLISH": 4
      },
      "signal_distribution": {
        "BULLISH": 7,
        "NEUTRAL": 5
      },
      "strict_accuracy": 0.25
    },
    "US:TSLA": {
      "balanced_accuracy": 0.35714285714285715,
      "n": 29,
      "realized_distribution": {
        "BEARISH": 15,
        "BULLISH": 14
      },
      "signal_distribution": {
        "BULLISH": 25,
        "NEUTRAL": 4
      },
      "strict_accuracy": 0.3448275862068966
    }
  },
  "prediction_distribution": {
    "BEARISH": 6,
    "BULLISH": 47,
    "NEUTRAL": 65
  },
  "realized_distribution": {
    "BEARISH": 31,
    "BULLISH": 54,
    "NEUTRAL": 33
  },
  "score_distribution": {
    "max": 0.4415884916744016,
    "mean": 0.13386041944116792,
    "median": 0.0924968589776668,
    "min": -0.2913786087268835,
    "n": 118,
    "q1": 0.014114337072443,
    "q3": 0.3003402858366125,
    "std": 0.17475774220692455
  },
  "title_only_limitation": "Current FNSPID rows mostly lack usable summaries, so sentiment evidence is predominantly title-based."
}
```