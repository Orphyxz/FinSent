# Gemini Analyzer

`GeminiSentimentAnalyzer` is the structured LLM analyzer in Sentiment Intelligence V2.

## Prompt And Schema

- Prompt version: `financial_sentiment_v2_1`
- Result schema version: `sentiment_analysis_result_v2_1`
- Prompt module: `finsent/app/prompts/financial_sentiment.py`

The prompt asks for strict JSON with:

- relevance
- sentiment
- confidence
- impact strength
- time horizon
- catalyst tag
- short reason

## Validation

The analyzer validates required fields, sentiment labels, numeric values, time horizon, catalyst tag, and reason text. Malformed numeric values degrade to documented safe defaults. Missing required structure or invalid labels produce parse failure and may trigger heuristic fallback in the orchestration service.

Markdown-wrapped JSON can still be handled by `GeminiClient` because current LLM behavior may include fenced JSON.

## Provenance

Results record:

- requested analyzer: `gemini`
- actual analyzer: `gemini` or `heuristic` if fallback was used by the service
- model name/version from `GEMINI_MODEL`
- prompt version
- schema version
- latency
- parse status
- failure category where applicable

## Limitations

Gemini confidence is model/self-assessed output confidence, not calibrated probability of future price movement. Gemini output is not treated as ground truth.
