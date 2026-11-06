"""Word-level explanations for FinBERT headline sentiment (leave-one-word-out occlusion).

Each word's weight is how much the FinBERT score (P(positive) − P(negative)) drops when
that word is removed. Positive weights pushed the headline bullish, negative weights
bearish. All variants run through the model in one batched forward pass, so explaining a
headline costs a single inference call. This is descriptive and never changes stored
sentiment rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

from finsent.app.services.sentiment_v2 import FinBERTSentimentAnalyzer, finbert_score, label_from_score


MAX_WORDS = 40
_analyzer: FinBERTSentimentAnalyzer | None = None


@dataclass(frozen=True, slots=True)
class WordWeight:
    word: str
    weight: float


@dataclass(frozen=True, slots=True)
class SentimentExplanation:
    text: str
    score: float
    label: str
    words: tuple[WordWeight, ...]
    available: bool
    message: str = ""

    def top(self, count: int = 3, *, positive: bool) -> list[WordWeight]:
        ranked = sorted((w for w in self.words if (w.weight > 0) == positive and abs(w.weight) > 0.01), key=lambda w: abs(w.weight), reverse=True)
        return ranked[:count]


def _model() -> FinBERTSentimentAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = FinBERTSentimentAnalyzer()
    _analyzer._ensure_model_loaded()
    return _analyzer


def _scores(analyzer: FinBERTSentimentAnalyzer, texts: list[str]) -> list[float]:
    torch = analyzer._torch
    encoded = analyzer._tokenizer(texts, return_tensors="pt", truncation=True, max_length=128, padding=True)
    with torch.no_grad():
        probabilities = torch.nn.functional.softmax(analyzer._model(**encoded).logits, dim=-1).tolist()
    labels = [analyzer._model.config.id2label[index].lower() for index in range(len(probabilities[0]))]
    return [finbert_score(dict(zip(labels, row, strict=False))) for row in probabilities]


@lru_cache(maxsize=512)
def explain_headline(text: str) -> SentimentExplanation:
    words = re.findall(r"\S+", text or "")[:MAX_WORDS]
    if not words:
        return SentimentExplanation(text, 0.0, "neutral", (), False, "Nothing to explain.")
    try:
        analyzer = _model()
    except Exception as exc:  # FinBERT is an optional dependency
        return SentimentExplanation(text, 0.0, "neutral", (), False, f"FinBERT is unavailable: {type(exc).__name__}.")
    variants = [" ".join(words)] + [" ".join(words[:i] + words[i + 1:]) or "." for i in range(len(words))]
    scores = _scores(analyzer, variants)
    base = scores[0]
    weights = tuple(WordWeight(word, base - score) for word, score in zip(words, scores[1:], strict=False))
    return SentimentExplanation(" ".join(words), base, label_from_score(base), weights, True)
