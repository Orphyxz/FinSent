from __future__ import annotations

from finsent.app.services.symbol_registry import SymbolRecord
from finsent.app.services.sentiment_v2 import SentimentAnalysisInput


FINANCIAL_SENTIMENT_PROMPT_VERSION = "financial_sentiment_v2_1"
FINANCIAL_SENTIMENT_SCHEMA_VERSION = "sentiment_analysis_result_v2_1"


def build_financial_sentiment_prompt(symbol: SymbolRecord, analysis_input: SentimentAnalysisInput) -> str:
    return f"""
You are analyzing stock-specific news for short-term market impact.

Instrument:
- symbol: {analysis_input.symbol}
- exchange: {analysis_input.exchange}
- company: {analysis_input.company_name or symbol.display_name}

Article:
- headline: {analysis_input.title}
- summary: {analysis_input.summary or ''}
- publisher: {analysis_input.publisher or ''}
- published_at: {analysis_input.published_at.isoformat()}
- source_provider: {analysis_input.source_provider or ''}
- leaf_provider: {analysis_input.leaf_provider or ''}
- data_mode: {analysis_input.data_mode or ''}

Return strict JSON only with this schema:
{{
  "relevant": true,
  "sentiment": "bullish|bearish|neutral",
  "confidence": 0.0,
  "impact_strength": 0.0,
  "time_horizon": "intraday|1-3d|1-2w",
  "catalyst_tag": "earnings|guidance|m_and_a|regulation|litigation|product|partnership|analyst_rating|management|layoffs|financing|macro|other|unknown",
  "short_reason": "short reason"
}}

Rules:
- Analyze relevance to the requested instrument, not broad market interest.
- confidence is model self-assessed classification confidence, not price probability.
- impact_strength is model-assessed article importance, not realized return.
- Do not include markdown or commentary outside JSON.
""".strip()

