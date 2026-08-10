from __future__ import annotations

"""
Deprecated legacy sentiment module.

This file is preserved for backward compatibility with earlier FinBERT-based
experiments. The production runtime now uses:
`news_providers -> llm_analyzers -> signal_engine`,
with final composite scoring owned by deterministic app logic.
"""

import numpy as np
import warnings

from finsent.app.config.settings import settings
from finsent.app.models.schemas import MarketSignalSnapshot, SentimentResult
from finsent.app.services.gemini_client import GeminiClient


LABEL_MAP = {
    "positive": "positive",
    "negative": "negative",
    "neutral": "neutral",
}


def normalize_score(score_map: dict[str, float]) -> float:
    return round(score_map.get("positive", 0.0) - score_map.get("negative", 0.0), 6)


def compose_signal(
    text_score: float,
    model_confidence: float,
    market_signal: float,
) -> tuple[float, float, str]:
    composite_score = float(np.clip((0.65 * text_score) + (0.35 * market_signal), -1.0, 1.0))
    agreement = 1.0 - min(abs(text_score - market_signal) / 2.0, 1.0)
    signal_confidence = float(
        np.clip(
            (0.7 * model_confidence) + (0.15 * abs(market_signal)) + (0.15 * agreement),
            0.0,
            1.0,
        )
    )

    if composite_score > 0.15:
        label = "positive"
    elif composite_score < -0.15:
        label = "negative"
    else:
        label = "neutral"
    return composite_score, signal_confidence, label


class FinBERTSentimentService:
    def __init__(self, model_name: str | None = None) -> None:
        warnings.warn(
            "FinBERTSentimentService is deprecated and not used by the production FinSent dashboard runtime. "
            "Use services.llm_analyzers plus services.signal_engine instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.model_name = model_name or settings.model_name
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = __import__("torch")
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self.model.eval()

    def predict(
        self,
        text: str,
        market_snapshot: MarketSignalSnapshot | None = None,
    ) -> SentimentResult:
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            return SentimentResult(
                label="neutral",
                score=0.0,
                positive=0.0,
                negative=0.0,
                neutral=1.0,
                model_label="neutral",
                model_confidence=0.0,
                text_score=0.0,
                signal_confidence=0.0,
            )

        encoded = self.tokenizer(
            cleaned_text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
        )
        with self.torch.no_grad():
            logits = self.model(**encoded).logits
            probs = self.torch.nn.functional.softmax(logits, dim=-1)[0].tolist()

        labels = [self.model.config.id2label[idx].lower() for idx in range(len(probs))]
        score_map = {LABEL_MAP.get(label, label): float(score) for label, score in zip(labels, probs)}
        model_label = max(score_map, key=score_map.get)
        model_confidence = float(score_map[model_label])
        text_score = normalize_score(score_map)
        market_signal = market_snapshot.market_signal if market_snapshot is not None else 0.0
        composite_score, signal_confidence, label = compose_signal(
            text_score=text_score,
            model_confidence=model_confidence,
            market_signal=market_signal,
        )

        return SentimentResult(
            label=label,
            score=composite_score,
            positive=score_map.get("positive", 0.0),
            negative=score_map.get("negative", 0.0),
            neutral=score_map.get("neutral", 0.0),
            model_label=model_label,
            model_confidence=model_confidence,
            text_score=text_score,
            signal_confidence=signal_confidence,
            bid_ask_spread=market_snapshot.bid_ask_spread if market_snapshot is not None else None,
            spread_pct=market_snapshot.spread_pct if market_snapshot is not None else 0.0,
            volume_ratio=market_snapshot.volume_ratio if market_snapshot is not None else 1.0,
            buy_sell_ratio=market_snapshot.buy_sell_ratio if market_snapshot is not None else 1.0,
            buy_pressure=market_snapshot.buy_pressure if market_snapshot is not None else 0.0,
            market_signal=market_signal,
        )

    @staticmethod
    def _normalize_score(score_map: dict[str, float]) -> float:
        return normalize_score(score_map)

    @staticmethod
    def compose_signal(
        text_score: float,
        model_confidence: float,
        market_signal: float,
    ) -> tuple[float, float, str]:
        return compose_signal(text_score=text_score, model_confidence=model_confidence, market_signal=market_signal)


class GeminiSentimentService:
    def __init__(self) -> None:
        self.client = GeminiClient()

    def predict(
        self,
        text: str,
        market_snapshot: MarketSignalSnapshot | None = None,
    ) -> SentimentResult:
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            return SentimentResult(
                label="neutral",
                score=0.0,
                positive=0.0,
                negative=0.0,
                neutral=1.0,
                model_label="neutral",
                model_confidence=0.0,
                text_score=0.0,
                signal_confidence=0.0,
            )

        market_signal = market_snapshot.market_signal if market_snapshot is not None else 0.0
        prompt = f"""
You are a financial sentiment engine.
Classify the following stock-market headline into positive, negative, or neutral sentiment for the stock.

Headline:
{cleaned_text}

Optional market context:
- market_signal: {market_signal:.4f}
- buy_sell_ratio: {market_snapshot.buy_sell_ratio if market_snapshot is not None else 1.0:.4f}
- volume_ratio: {market_snapshot.volume_ratio if market_snapshot is not None else 1.0:.4f}
- spread_pct: {market_snapshot.spread_pct if market_snapshot is not None else 0.0:.6f}

Return strict JSON only with this schema:
{{
  "label": "positive|negative|neutral",
  "positive": 0.0,
  "negative": 0.0,
  "neutral": 0.0,
  "confidence": 0.0
}}

Rules:
- probabilities must sum to 1.0
- confidence must equal the winning class probability
- do not include markdown
""".strip()
        payload = self.client.generate_json(prompt, use_search_grounding=False, temperature=0.1, max_output_tokens=300)
        score_map = self._parse_score_map(payload)
        model_label = max(score_map, key=score_map.get)
        model_confidence = float(score_map[model_label])
        text_score = normalize_score(score_map)
        composite_score, signal_confidence, label = compose_signal(
            text_score=text_score,
            model_confidence=model_confidence,
            market_signal=market_signal,
        )

        return SentimentResult(
            label=label,
            score=composite_score,
            positive=score_map.get("positive", 0.0),
            negative=score_map.get("negative", 0.0),
            neutral=score_map.get("neutral", 0.0),
            model_label=model_label,
            model_confidence=model_confidence,
            text_score=text_score,
            signal_confidence=signal_confidence,
            bid_ask_spread=market_snapshot.bid_ask_spread if market_snapshot is not None else None,
            spread_pct=market_snapshot.spread_pct if market_snapshot is not None else 0.0,
            volume_ratio=market_snapshot.volume_ratio if market_snapshot is not None else 1.0,
            buy_sell_ratio=market_snapshot.buy_sell_ratio if market_snapshot is not None else 1.0,
            buy_pressure=market_snapshot.buy_pressure if market_snapshot is not None else 0.0,
            market_signal=market_signal,
        )

    @staticmethod
    def _parse_score_map(payload: object) -> dict[str, float]:
        default = {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
        if not isinstance(payload, dict):
            return default
        values = {
            "positive": float(payload.get("positive", 0.0) or 0.0),
            "negative": float(payload.get("negative", 0.0) or 0.0),
            "neutral": float(payload.get("neutral", 0.0) or 0.0),
        }
        total = sum(max(value, 0.0) for value in values.values())
        if total <= 0:
            return default
        normalized = {key: float(max(value, 0.0) / total) for key, value in values.items()}
        label = str(payload.get("label", "")).strip().lower()
        if label not in normalized:
            label = max(normalized, key=normalized.get)
        normalized[label] = max(normalized[label], float(payload.get("confidence", normalized[label]) or normalized[label]))
        total = sum(normalized.values())
        return {key: value / total for key, value in normalized.items()}


def build_sentiment_service() -> FinBERTSentimentService | GeminiSentimentService:
    provider = settings.sentiment_provider.strip().lower()
    if provider == "gemini" and settings.gemini_api_key:
        return GeminiSentimentService()
    return FinBERTSentimentService()
