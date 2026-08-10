# Signal V2.1 Development-Only Tuning

## Research Discipline
Parameter selection used only Phase 12 DEVELOPMENT rows. Phase 12 HOLDOUT is renamed OBSERVED_VALIDATION and was not used for tuning. The new final holdout is locked and unevaluated.

## Data Used
Development observations: 118 valid 1D V2 rows.

## Data NOT Used
- Phase 12 OBSERVED_VALIDATION metrics
- New FINAL_HOLDOUT_LOCKED outcomes or accuracy

## Temporal Folds
[
  {
    "fold_id": "fold_1",
    "train_article_ids": [
      123,
      124,
      125,
      126,
      155,
      156,
      51,
      130,
      131,
      178,
      179,
      180,
      181,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60,
      61,
      91,
      92,
      93,
      132,
      133,
      182
    ],
    "train_end_index": 29,
    "train_start_index": 0,
    "validation_article_ids": [
      183,
      62,
      63,
      64,
      65,
      94,
      95,
      96,
      97,
      134,
      135,
      136,
      137,
      138,
      139,
      184,
      195,
      196,
      197,
      198,
      66,
      98,
      99,
      100,
      101,
      140,
      141,
      142,
      143,
      144
    ],
    "validation_end": "2020-05-29 00:00:00",
    "validation_end_index": 59,
    "validation_start": "2020-05-27 00:00:00",
    "validation_start_index": 29
  },
  {
    "fold_id": "fold_2",
    "train_article_ids": [
      123,
      124,
      125,
      126,
      155,
      156,
      51,
      130,
      131,
      178,
      179,
      180,
      181,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60,
      61,
      91,
      92,
      93,
      132,
      133,
      182,
      183,
      62,
      63,
      64,
      65,
      94,
      95,
      96,
      97,
      134,
      135,
      136,
      137,
      138,
      139,
      184,
      195,
      196,
      197,
      198,
      66,
      98,
      99,
      100,
      101,
      140,
      141,
      142,
      143,
      144
    ],
    "train_end_index": 59,
    "train_start_index": 0,
    "validation_article_ids": [
      199,
      200,
      201,
      202,
      102,
      203,
      204,
      67,
      68,
      103,
      104,
      205,
      185,
      69,
      70,
      71,
      72,
      73,
      74,
      105,
      106,
      107,
      108,
      109,
      110,
      111,
      112,
      113,
      145
    ],
    "validation_end": "2020-06-01 00:00:00",
    "validation_end_index": 88,
    "validation_start": "2020-05-29 00:00:00",
    "validation_start_index": 59
  },
  {
    "fold_id": "fold_3",
    "train_article_ids": [
      123,
      124,
      125,
      126,
      155,
      156,
      51,
      130,
      131,
      178,
      179,
      180,
      181,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60,
      61,
      91,
      92,
      93,
      132,
      133,
      182,
      183,
      62,
      63,
      64,
      65,
      94,
      95,
      96,
      97,
      134,
      135,
      136,
      137,
      138,
      139,
      184,
      195,
      196,
      197,
      198,
      66,
      98,
      99,
      100,
      101,
      140,
      141,
      142,
      143,
      144,
      199,
      200,
      201,
      202,
      102,
      203,
      204,
      67,
      68,
      103,
      104,
      205,
      185,
      69,
      70,
      71,
      72,
      73,
      74,
      105,
      106,
      107,
      108,
      109,
      110,
      111,
      112,
      113,
      145
    ],
    "train_end_index": 88,
    "train_start_index": 0,
    "validation_article_ids": [
      206,
      207,
      208,
      209,
      210,
      211,
      212,
      213,
      214,
      215,
      216,
      217,
      75,
      76,
      77,
      78,
      79,
      80,
      114,
      115,
      218,
      219,
      220,
      221,
      222,
      223,
      186,
      187,
      146,
      147
    ],
    "validation_end": "2020-06-04 09:08:37",
    "validation_end_index": 118,
    "validation_start": "2020-06-01 00:00:00",
    "validation_start_index": 88
  }
]

## Baselines
{
  "always_neutral": [
    {
      "balanced_accuracy": 0.3333333333333333,
      "correct": 9,
      "directional_accuracy": null,
      "directional_correct": 0,
      "directional_eligible": 0,
      "f1": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.4615384615384615
      },
      "fold_id": "fold_1",
      "incorrect": 21,
      "macro_f1": 0.4615384615384615,
      "n": 30,
      "neutral_outcome_count": 9,
      "neutral_prediction_count": 30,
      "precision": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.3
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.0,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.3,
      "total": 30,
      "wilson_interval": [
        0.16664562643958933,
        0.4787612101166018
      ]
    },
    {
      "balanced_accuracy": 0.3333333333333333,
      "correct": 12,
      "directional_accuracy": null,
      "directional_correct": 0,
      "directional_eligible": 0,
      "f1": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.5853658536585366
      },
      "fold_id": "fold_2",
      "incorrect": 17,
      "macro_f1": 0.5853658536585366,
      "n": 29,
      "neutral_outcome_count": 12,
      "neutral_prediction_count": 29,
      "precision": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.41379310344827586
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.0,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.41379310344827586,
      "total": 29,
      "wilson_interval": [
        0.2551293527964552,
        0.5926247152148476
      ]
    },
    {
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
      "fold_id": "fold_3",
      "incorrect": 30,
      "macro_f1": null,
      "n": 30,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 30,
      "precision": {
        "BEARISH": null,
        "BULLISH": null,
        "NEUTRAL": 0.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.0,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.0,
      "total": 30,
      "wilson_interval": [
        0.0,
        0.113517091390478
      ]
    }
  ],
  "majority_class": [
    {
      "balanced_accuracy": 0.3333333333333333,
      "correct": 1,
      "directional_accuracy": 0.047619047619047616,
      "directional_correct": 1,
      "directional_eligible": 21,
      "f1": {
        "BEARISH": 0.06451612903225806,
        "BULLISH": null,
        "NEUTRAL": null
      },
      "fold_id": "fold_1",
      "incorrect": 29,
      "macro_f1": 0.06451612903225806,
      "n": 30,
      "neutral_outcome_count": 9,
      "neutral_prediction_count": 0,
      "precision": {
        "BEARISH": 0.03333333333333333,
        "BULLISH": null,
        "NEUTRAL": null
      },
      "recall": {
        "BEARISH": 1.0,
        "BULLISH": 0.0,
        "NEUTRAL": 0.0
      },
      "strict_accuracy": 0.03333333333333333,
      "total": 30,
      "wilson_interval": [
        0.0059084379948573795,
        0.16670751396958874
      ]
    },
    {
      "balanced_accuracy": 0.3333333333333333,
      "correct": 14,
      "directional_accuracy": 0.8235294117647058,
      "directional_correct": 14,
      "directional_eligible": 17,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.6511627906976745,
        "NEUTRAL": null
      },
      "fold_id": "fold_2",
      "incorrect": 15,
      "macro_f1": 0.6511627906976745,
      "n": 29,
      "neutral_outcome_count": 12,
      "neutral_prediction_count": 0,
      "precision": {
        "BEARISH": null,
        "BULLISH": 0.4827586206896552,
        "NEUTRAL": null
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 1.0,
        "NEUTRAL": 0.0
      },
      "strict_accuracy": 0.4827586206896552,
      "total": 29,
      "wilson_interval": [
        0.3138581933079522,
        0.6556926202943085
      ]
    },
    {
      "balanced_accuracy": 0.5,
      "correct": 16,
      "directional_accuracy": 0.5333333333333333,
      "directional_correct": 16,
      "directional_eligible": 30,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.6956521739130436,
        "NEUTRAL": null
      },
      "fold_id": "fold_3",
      "incorrect": 14,
      "macro_f1": 0.6956521739130436,
      "n": 30,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 0,
      "precision": {
        "BEARISH": null,
        "BULLISH": 0.5333333333333333,
        "NEUTRAL": null
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 1.0,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.5333333333333333,
      "total": 30,
      "wilson_interval": [
        0.3614201328152505,
        0.6976787277587178
      ]
    }
  ],
  "news_direction": [
    {
      "balanced_accuracy": 0.08333333333333333,
      "correct": 5,
      "directional_accuracy": 1.0,
      "directional_correct": 5,
      "directional_eligible": 5,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.3448275862068966,
        "NEUTRAL": null
      },
      "fold_id": "fold_1",
      "incorrect": 25,
      "macro_f1": 0.3448275862068966,
      "n": 30,
      "neutral_outcome_count": 9,
      "neutral_prediction_count": 16,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.5555555555555556,
        "NEUTRAL": 0.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.25,
        "NEUTRAL": 0.0
      },
      "strict_accuracy": 0.16666666666666666,
      "total": 30,
      "wilson_interval": [
        0.07336434240351686,
        0.33564705185680177
      ]
    },
    {
      "balanced_accuracy": 0.4523809523809524,
      "correct": 17,
      "directional_accuracy": 0.29411764705882354,
      "directional_correct": 5,
      "directional_eligible": 17,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.45454545454545453,
        "NEUTRAL": 1.0
      },
      "fold_id": "fold_2",
      "incorrect": 12,
      "macro_f1": 0.7272727272727273,
      "n": 29,
      "neutral_outcome_count": 12,
      "neutral_prediction_count": 12,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.625,
        "NEUTRAL": 1.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.35714285714285715,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.5862068965517241,
      "total": 29,
      "wilson_interval": [
        0.40737528478515245,
        0.7448706472035449
      ]
    },
    {
      "balanced_accuracy": 0.1875,
      "correct": 6,
      "directional_accuracy": 0.3,
      "directional_correct": 6,
      "directional_eligible": 20,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.35294117647058826,
        "NEUTRAL": null
      },
      "fold_id": "fold_3",
      "incorrect": 24,
      "macro_f1": 0.35294117647058826,
      "n": 30,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 10,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.3333333333333333,
        "NEUTRAL": 0.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.375,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.2,
      "total": 30,
      "wilson_interval": [
        0.09504978102401235,
        0.37306047381027446
      ]
    }
  ],
  "v1": [
    {
      "balanced_accuracy": 0.08333333333333333,
      "correct": 5,
      "directional_accuracy": 1.0,
      "directional_correct": 5,
      "directional_eligible": 5,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.3448275862068966,
        "NEUTRAL": null
      },
      "fold_id": "fold_1",
      "incorrect": 25,
      "macro_f1": 0.3448275862068966,
      "n": 30,
      "neutral_outcome_count": 9,
      "neutral_prediction_count": 16,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.5555555555555556,
        "NEUTRAL": 0.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.25,
        "NEUTRAL": 0.0
      },
      "strict_accuracy": 0.16666666666666666,
      "total": 30,
      "wilson_interval": [
        0.07336434240351686,
        0.33564705185680177
      ]
    },
    {
      "balanced_accuracy": 0.4523809523809524,
      "correct": 17,
      "directional_accuracy": 0.29411764705882354,
      "directional_correct": 5,
      "directional_eligible": 17,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.45454545454545453,
        "NEUTRAL": 1.0
      },
      "fold_id": "fold_2",
      "incorrect": 12,
      "macro_f1": 0.7272727272727273,
      "n": 29,
      "neutral_outcome_count": 12,
      "neutral_prediction_count": 12,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.625,
        "NEUTRAL": 1.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.35714285714285715,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.5862068965517241,
      "total": 29,
      "wilson_interval": [
        0.40737528478515245,
        0.7448706472035449
      ]
    },
    {
      "balanced_accuracy": 0.1875,
      "correct": 6,
      "directional_accuracy": 0.3,
      "directional_correct": 6,
      "directional_eligible": 20,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.35294117647058826,
        "NEUTRAL": null
      },
      "fold_id": "fold_3",
      "incorrect": 24,
      "macro_f1": 0.35294117647058826,
      "n": 30,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 10,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.3333333333333333,
        "NEUTRAL": 0.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.375,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.2,
      "total": 30,
      "wilson_interval": [
        0.09504978102401235,
        0.37306047381027446
      ]
    }
  ],
  "v2_0": [
    {
      "balanced_accuracy": 0.39999999999999997,
      "correct": 13,
      "directional_accuracy": 1.0,
      "directional_correct": 4,
      "directional_eligible": 4,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.33333333333333337,
        "NEUTRAL": 0.5142857142857142
      },
      "fold_id": "fold_1",
      "incorrect": 17,
      "macro_f1": 0.4238095238095238,
      "n": 30,
      "neutral_outcome_count": 9,
      "neutral_prediction_count": 26,
      "precision": {
        "BEARISH": null,
        "BULLISH": 1.0,
        "NEUTRAL": 0.34615384615384615
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.2,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.43333333333333335,
      "total": 30,
      "wilson_interval": [
        0.2737723743061511,
        0.6080299045459127
      ]
    },
    {
      "balanced_accuracy": 0.35714285714285715,
      "correct": 13,
      "directional_accuracy": 0.14285714285714285,
      "directional_correct": 1,
      "directional_eligible": 7,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.11111111111111112,
        "NEUTRAL": 0.7058823529411764
      },
      "fold_id": "fold_2",
      "incorrect": 16,
      "macro_f1": 0.4084967320261438,
      "n": 29,
      "neutral_outcome_count": 12,
      "neutral_prediction_count": 22,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.25,
        "NEUTRAL": 0.5454545454545454
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.07142857142857142,
        "NEUTRAL": 1.0
      },
      "strict_accuracy": 0.4482758620689655,
      "total": 29,
      "wilson_interval": [
        0.2841291114874579,
        0.6245233293193238
      ]
    },
    {
      "balanced_accuracy": 0.1875,
      "correct": 6,
      "directional_accuracy": 0.3,
      "directional_correct": 6,
      "directional_eligible": 20,
      "f1": {
        "BEARISH": null,
        "BULLISH": 0.35294117647058826,
        "NEUTRAL": null
      },
      "fold_id": "fold_3",
      "incorrect": 24,
      "macro_f1": 0.35294117647058826,
      "n": 30,
      "neutral_outcome_count": 0,
      "neutral_prediction_count": 10,
      "precision": {
        "BEARISH": 0.0,
        "BULLISH": 0.3333333333333333,
        "NEUTRAL": 0.0
      },
      "recall": {
        "BEARISH": 0.0,
        "BULLISH": 0.375,
        "NEUTRAL": null
      },
      "strict_accuracy": 0.2,
      "total": 30,
      "wilson_interval": [
        0.09504978102401235,
        0.37306047381027446
      ]
    }
  ]
}

## Candidate Space
Candidates evaluated: 80
Tuned only news weight, momentum weight, volume-confirmation weight, and symmetric directional threshold.

## Objective
Primary objective: median temporal-fold balanced accuracy. Tie breakers: worst fold, closeness to V2.0, deterministic id.

## Degeneracy Rules
Reject candidates with <20% directional predictions, >90% one-class predictions, or fewer than two predicted classes when validation outcomes contain all three classes.

## Results
V2.0 reference median balanced accuracy: 0.3571
Selected candidate median balanced accuracy: 0.3571
Selected candidate worst-fold balanced accuracy: 0.2500
Selected candidate justified: False

## Selected Candidate
{
  "candidate": {
    "candidate_id": "v2_1_grid_042",
    "directional_threshold": 0.15,
    "momentum_weight": 0.45,
    "news_weight": 0.55,
    "volume_weight": 0.0
  },
  "confidence_formula": "unchanged from V2.0: 0.35*abs(score)+0.30*reliability+0.20*agreement+0.15*availability",
  "created_at": "2026-08-10T00:41:42.653371",
  "engine_name": "finsent_composite",
  "engine_version": "2.1-research",
  "momentum_return_scale": 0.05,
  "news_decay": {
    "max_news_age_hours": 72.0,
    "min_news_recency_weight": 0.2
  },
  "parent_version": "2.0",
  "status": "FROZEN_RESEARCH_CANDIDATE_NOT_JUSTIFIED",
  "strong_threshold": 0.55,
  "tuning_dataset_fingerprint": "62a7844695106cd34bb4bd8f2583483e3af2394876b9728502a4dc30cf4e039b",
  "tuning_method": "Phase 12 DEVELOPMENT rows only; 3-fold chronological expanding-window validation; median balanced accuracy objective."
}

## V2.0 vs V2.1 Development Comparison
{
  "selected": {
    "candidate": {
      "candidate_id": "v2_1_grid_042",
      "directional_threshold": 0.15,
      "momentum_weight": 0.45,
      "news_weight": 0.55,
      "volume_weight": 0.0
    },
    "degeneracy_reason": null,
    "degenerate": false,
    "folds": [
      {
        "balanced_accuracy": 0.39999999999999997,
        "candidate_id": "v2_1_grid_042",
        "coverage": 1.0,
        "directional_accuracy": 1.0,
        "fold_id": "fold_1",
        "macro_f1": 0.4238095238095238,
        "n": 30,
        "prediction_distribution": {
          "BULLISH": 4,
          "NEUTRAL": 26
        },
        "realized_distribution": {
          "BEARISH": 1,
          "BULLISH": 20,
          "NEUTRAL": 9
        },
        "strict_accuracy": 0.43333333333333335
      },
      {
        "balanced_accuracy": 0.35714285714285715,
        "candidate_id": "v2_1_grid_042",
        "coverage": 1.0,
        "directional_accuracy": 0.14285714285714285,
        "fold_id": "fold_2",
        "macro_f1": 0.4084967320261438,
        "n": 29,
        "prediction_distribution": {
          "BEARISH": 3,
          "BULLISH": 4,
          "NEUTRAL": 22
        },
        "realized_distribution": {
          "BEARISH": 3,
          "BULLISH": 14,
          "NEUTRAL": 12
        },
        "strict_accuracy": 0.4482758620689655
      },
      {
        "balanced_accuracy": 0.25,
        "candidate_id": "v2_1_grid_042",
        "coverage": 1.0,
        "directional_accuracy": 0.36363636363636365,
        "fold_id": "fold_3",
        "macro_f1": 0.4444444444444445,
        "n": 30,
        "prediction_distribution": {
          "BEARISH": 2,
          "BULLISH": 20,
          "NEUTRAL": 8
        },
        "realized_distribution": {
          "BEARISH": 14,
          "BULLISH": 16
        },
        "strict_accuracy": 0.26666666666666666
      }
    ],
    "justified": false,
    "mean_balanced_accuracy": 0.3357142857142857,
    "mean_macro_f1": 0.42558356676003734,
    "median_balanced_accuracy": 0.35714285714285715,
    "selected": true,
    "std_balanced_accuracy": 0.06308400618805604,
    "worst_fold_balanced_accuracy": 0.25
  },
  "v2_0": {
    "candidate": {
      "candidate_id": "v2_0_reference",
      "directional_threshold": 0.2,
      "momentum_weight": 0.35,
      "news_weight": 0.55,
      "volume_weight": 0.1
    },
    "degeneracy_reason": null,
    "degenerate": false,
    "folds": [
      {
        "balanced_accuracy": 0.39999999999999997,
        "candidate_id": "v2_0_reference",
        "coverage": 1.0,
        "directional_accuracy": 1.0,
        "fold_id": "fold_1",
        "macro_f1": 0.4238095238095238,
        "n": 30,
        "prediction_distribution": {
          "BULLISH": 4,
          "NEUTRAL": 26
        },
        "realized_distribution": {
          "BEARISH": 1,
          "BULLISH": 20,
          "NEUTRAL": 9
        },
        "strict_accuracy": 0.43333333333333335
      },
      {
        "balanced_accuracy": 0.35714285714285715,
        "candidate_id": "v2_0_reference",
        "coverage": 1.0,
        "directional_accuracy": 0.14285714285714285,
        "fold_id": "fold_2",
        "macro_f1": 0.4084967320261438,
        "n": 29,
        "prediction_distribution": {
          "BEARISH": 3,
          "BULLISH": 4,
          "NEUTRAL": 22
        },
        "realized_distribution": {
          "BEARISH": 3,
          "BULLISH": 14,
          "NEUTRAL": 12
        },
        "strict_accuracy": 0.4482758620689655
      },
      {
        "balanced_accuracy": 0.1875,
        "candidate_id": "v2_0_reference",
        "coverage": 1.0,
        "directional_accuracy": 0.3,
        "fold_id": "fold_3",
        "macro_f1": 0.35294117647058826,
        "n": 30,
        "prediction_distribution": {
          "BEARISH": 2,
          "BULLISH": 18,
          "NEUTRAL": 10
        },
        "realized_distribution": {
          "BEARISH": 14,
          "BULLISH": 16
        },
        "strict_accuracy": 0.2
      }
    ],
    "justified": false,
    "mean_balanced_accuracy": 0.3148809523809524,
    "mean_macro_f1": 0.39508247743541863,
    "median_balanced_accuracy": 0.35714285714285715,
    "selected": false,
    "std_balanced_accuracy": 0.0917555227968258,
    "worst_fold_balanced_accuracy": 0.1875
  }
}

## Optional Observed-Validation Result
Skipped in Phase 13 to avoid any risk of post-freeze tuning feedback.

## New Final Holdout
{
  "article_ids": [
    256,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    234,
    235,
    236,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    246,
    247,
    248,
    249,
    250,
    251,
    252,
    253,
    254,
    255
  ],
  "cohort_fingerprint": "a6db3f66a5a648a755dca53325577e499f1fe607ab4b70d1e6c896133395b9c4",
  "coverage_summary": {
    "articles": 30,
    "horizons": {
      "1D": {
        "eligible": 30,
        "no_coverage": 0,
        "unsupported_granularity": 0
      }
    },
    "with_historical_bars": 30,
    "with_instrument": 30
  },
  "dataset_id": "phase13_final_holdout_v1",
  "date_end": "2023-12-13T00:00:00",
  "date_start": "2023-12-12T00:00:00",
  "excluded_count": 0,
  "exclusion_counts": {},
  "instruments": [
    "US:AAPL"
  ],
  "lock_rule": "No Phase 13 performance evaluation. Technical coverage only.",
  "locked_at": "2026-08-10T00:40:11.994428",
  "source_manifest": {
    "checksum_sha256": "bb1e277a4167fb85472d93ebbae58a1727e5b32f518aa0a8cbc988a3a4e3ae2c",
    "matched_rows": 30,
    "requested_symbols": [
      "AAPL"
    ],
    "scan_limit_reached": false,
    "scanned_rows": 12110,
    "subset_path": "data\\research_sources\\fnspid\\subsets\\phase13_final_holdout_v1.csv"
  },
  "status": "FINAL_HOLDOUT_LOCKED"
}

## Final Holdout Status
FINAL_HOLDOUT_LOCKED and UNEVALUATED. Only technical price coverage metadata was checked.

## Error Analysis
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

## Limitations
Small development sample, title-heavy FNSPID text, daily bars only, no confidence calibration, and final-holdout symbol coverage limited by bounded-source feasibility.

## What Cannot Yet Be Claimed
Do not claim production superiority, profitability, calibration, or final generalization until the locked final holdout is evaluated in a later explicit phase.