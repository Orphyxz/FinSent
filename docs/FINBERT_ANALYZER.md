# FinBERT Analyzer

`FinBERTSentimentAnalyzer` is available through the same Sentiment Intelligence V2 contract as Gemini and heuristic analysis.

## What FinBERT Provides

FinBERT provides classifier probabilities for financial text sentiment classes:

- positive
- negative
- neutral

Phase 6 normalizes those probabilities into:

```text
sentiment_score = P(positive) - P(negative)
```

The canonical label is:

- bullish if score `> 0.15`
- bearish if score `< -0.15`
- neutral otherwise

Confidence is the winning class probability.

## What FinBERT Does Not Provide

The base FinBERT classifier does not inherently provide:

- catalyst tag
- impact horizon
- instrument relevance reasoning
- short natural-language reason
- event-study expectation

These fields are stored as `not_applicable`, `None`, or equivalent explicit semantics. Phase 6 does not fabricate Gemini-style fields for FinBERT.

## Dependencies

FinBERT dependencies remain optional and live in:

```powershell
pip install -r requirements-research.txt
```

Default dashboard/runtime installation does not require `torch` or `transformers`. If FinBERT is selected without those dependencies, the analyzer returns structured `DEPENDENCY_MISSING` instead of crashing the app.

## Limitations

FinBERT can be compared with Gemini in a later experiment, but Phase 6 does not run that benchmark and does not claim comparative accuracy.
