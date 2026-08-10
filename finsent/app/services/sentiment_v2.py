from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter
from typing import Any, Protocol
from hashlib import sha256

from finsent.app.config.settings import settings
from finsent.app.services.gemini_client import GeminiClient
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_contracts import classify_exception
from finsent.app.services.symbol_registry import SymbolRecord
from finsent.app.utils.logging import safe_log_message


class SentimentLabel(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class CatalystTag(str, Enum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    M_AND_A = "m_and_a"
    REGULATION = "regulation"
    LITIGATION = "litigation"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"
    ANALYST_RATING = "analyst_rating"
    MANAGEMENT = "management"
    LAYOFFS = "layoffs"
    FINANCING = "financing"
    MACRO = "macro"
    OTHER = "other"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    ONE_TO_THREE_DAYS = "1-3d"
    ONE_TO_TWO_WEEKS = "1-2w"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ModelFailureCategory(str, Enum):
    UNCONFIGURED = "UNCONFIGURED"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    PARSE_FAILURE = "PARSE_FAILURE"
    MODEL_LOAD_FAILURE = "MODEL_LOAD_FAILURE"
    INFERENCE_FAILURE = "INFERENCE_FAILURE"
    UNKNOWN = "UNKNOWN"


class ModelExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FALLBACK_USED = "FALLBACK_USED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class SentimentAnalysisInput:
    article_id: str | int | None
    instrument_id: int | None
    symbol: str
    company_name: str | None
    exchange: str
    title: str
    summary: str | None
    body: str | None
    publisher: str | None
    published_at: datetime
    source_provider: str | None
    leaf_provider: str | None
    data_mode: str | None
    language: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(part for part in [self.title, self.summary, self.body] if part).strip()


@dataclass(slots=True)
class SentimentAnalysisResult:
    requested_analyzer: str
    actual_analyzer: str
    provider: str
    model_family: str
    model_name: str
    model_version: str | None
    analysis_method: str
    sentiment_label: str
    sentiment_score: float
    confidence: float | None
    relevance: float | None
    impact_strength: float | None
    time_horizon: str | None
    catalyst_tag: str | None
    short_reason: str | None
    parse_status: str
    fallback_used: bool
    fallback_reason: str | None
    schema_version: str | None
    prompt_version: str | None
    latency_ms: int | None
    created_at: datetime
    status: ModelExecutionStatus = ModelExecutionStatus.SUCCESS
    failure_category: ModelFailureCategory | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SentimentAnalyzer(Protocol):
    analyzer_name: str
    model_family: str
    model_name: str
    model_version: str | None
    analysis_method: str
    configured: bool

    def analyze(self, analysis_input: SentimentAnalysisInput) -> SentimentAnalysisResult:
        ...


@dataclass(slots=True)
class ModelHealthRecord:
    analyzer: str
    configured: bool
    available: bool
    last_success: datetime | None = None
    last_failure: datetime | None = None
    failure_category: ModelFailureCategory | None = None
    last_latency_ms: int | None = None
    fallback_used: bool = False


class ModelHealthRegistry:
    def __init__(self) -> None:
        self._records: dict[str, ModelHealthRecord] = {}

    def record(self, result: SentimentAnalysisResult) -> None:
        now = result.created_at
        success = result.status in {ModelExecutionStatus.SUCCESS, ModelExecutionStatus.FALLBACK_USED}
        self._records[result.requested_analyzer] = ModelHealthRecord(
            analyzer=result.requested_analyzer,
            configured=result.failure_category != ModelFailureCategory.UNCONFIGURED,
            available=success,
            last_success=now if success else None,
            last_failure=None if success else now,
            failure_category=result.failure_category,
            last_latency_ms=result.latency_ms,
            fallback_used=result.fallback_used,
        )

    def snapshot(self) -> list[ModelHealthRecord]:
        return list(self._records.values())


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def duration_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def normalize_sentiment_label(value: object) -> str | None:
    text = str(value or "").strip().lower()
    mapping = {"positive": "bullish", "negative": "bearish", "bull": "bullish", "bear": "bearish"}
    text = mapping.get(text, text)
    return text if text in {item.value for item in SentimentLabel} else None


def sentiment_score_from_label(label: str, confidence: float | None) -> float:
    magnitude = max(0.0, min(float(confidence or 0.0), 1.0))
    if label == SentimentLabel.BULLISH.value:
        return magnitude
    if label == SentimentLabel.BEARISH.value:
        return -magnitude
    return 0.0


def finbert_score(probabilities: dict[str, float]) -> float:
    return max(min(float(probabilities.get("positive", 0.0)) - float(probabilities.get("negative", 0.0)), 1.0), -1.0)


def label_from_score(score: float) -> str:
    if score > 0.15:
        return SentimentLabel.BULLISH.value
    if score < -0.15:
        return SentimentLabel.BEARISH.value
    return SentimentLabel.NEUTRAL.value


def safe_float(value: object, *, default: float = 0.0, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return default
    return max(min(parsed, maximum), minimum)


CATALYST_ALIASES = {
    "analyst": CatalystTag.ANALYST_RATING.value,
    "rating": CatalystTag.ANALYST_RATING.value,
    "lawsuit": CatalystTag.LITIGATION.value,
    "legal": CatalystTag.LITIGATION.value,
    "merger": CatalystTag.M_AND_A.value,
    "acquisition": CatalystTag.M_AND_A.value,
    "m&a": CatalystTag.M_AND_A.value,
}


def normalize_catalyst(value: object, *, fallback: str = CatalystTag.OTHER.value) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = CATALYST_ALIASES.get(text, text)
    allowed = {item.value for item in CatalystTag}
    return text if text in allowed else fallback


HORIZON_ALIASES = {
    "1_to_3_days": TimeHorizon.ONE_TO_THREE_DAYS.value,
    "1-3days": TimeHorizon.ONE_TO_THREE_DAYS.value,
    "short_term": TimeHorizon.ONE_TO_THREE_DAYS.value,
    "longer_term": TimeHorizon.ONE_TO_TWO_WEEKS.value,
}


def normalize_time_horizon(value: object, *, fallback: str = TimeHorizon.ONE_TO_THREE_DAYS.value) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    text = HORIZON_ALIASES.get(text, text)
    allowed = {item.value for item in TimeHorizon}
    return text if text in allowed else fallback


def validate_gemini_payload(payload: object) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(payload, dict):
        return None, ["payload is not a JSON object"]
    required = {"relevant", "sentiment", "confidence", "impact_strength", "time_horizon", "catalyst_tag", "short_reason"}
    missing = sorted(required - set(payload))
    if missing:
        return None, [f"missing required fields: {missing}"]
    label = normalize_sentiment_label(payload.get("sentiment"))
    if label is None:
        return None, ["invalid sentiment label"]
    normalized = {
        "relevant": bool(payload.get("relevant")),
        "sentiment": label,
        "confidence": safe_float(payload.get("confidence")),
        "impact_strength": safe_float(payload.get("impact_strength")),
        "time_horizon": normalize_time_horizon(payload.get("time_horizon")),
        "catalyst_tag": normalize_catalyst(payload.get("catalyst_tag")),
        "short_reason": str(payload.get("short_reason") or "").strip() or "No explanation generated",
    }
    return normalized, []


def normalize_article_input(symbol: SymbolRecord, article: NormalizedNewsArticle, *, article_db_id: int | None = None, instrument_id: int | None = None) -> SentimentAnalysisInput:
    return SentimentAnalysisInput(
        article_id=article_db_id if article_db_id is not None else article.article_id,
        instrument_id=instrument_id,
        symbol=symbol.ticker,
        company_name=symbol.display_name,
        exchange=symbol.exchange,
        title=article.title,
        summary=article.summary,
        body=None,
        publisher=article.source,
        published_at=article.published_at,
        source_provider=article.provider,
        leaf_provider=article.provider,
        data_mode=None,
        language=None,
        context={"dedupe_hash": article.dedupe_hash, "relevance_score": article.relevance_score},
    )


def run_fingerprint(analysis_input: SentimentAnalysisInput, result: SentimentAnalysisResult) -> str:
    raw = "|".join(
        [
            str(analysis_input.article_id),
            result.model_family,
            result.model_name,
            str(result.model_version),
            str(result.prompt_version),
            str(result.schema_version),
            result.analysis_method,
        ]
    )
    return sha256(raw.encode("utf-8")).hexdigest()


class HeuristicSentimentAnalyzer:
    analyzer_name = "heuristic"
    model_family = "heuristic"
    model_name = "local_keyword_heuristic"
    model_version = "v2_1"
    analysis_method = "heuristic"
    configured = True

    def __init__(self, *, requested_analyzer: str = "heuristic", fallback_reason: str | None = None) -> None:
        self.requested_analyzer = requested_analyzer
        self.fallback_reason = fallback_reason

    def analyze(self, analysis_input: SentimentAnalysisInput) -> SentimentAnalysisResult:
        started = perf_counter()
        text = analysis_input.text.lower()
        positive_terms = {"beat", "beats", "surge", "growth", "record", "strong", "upgrade", "raises", "raised", "buyback", "profit", "expands", "wins", "partnership", "launch", "approval"}
        negative_terms = {"miss", "misses", "cut", "cuts", "downgrade", "lawsuit", "probe", "investigation", "fall", "drops", "drop", "slump", "warning", "weak", "decline", "layoffs", "selloff"}
        impact_terms = {"earnings", "guidance", "forecast", "outlook", "regulation", "lawsuit", "investigation", "upgrade", "downgrade", "merger", "acquisition", "buyback", "dividend", "ceo", "management", "launch", "approval"}
        positive_hits = sum(1 for term in positive_terms if term in text)
        negative_hits = sum(1 for term in negative_terms if term in text)
        impact_hits = sum(1 for term in impact_terms if term in text)
        if positive_hits > negative_hits:
            label = SentimentLabel.BULLISH.value
        elif negative_hits > positive_hits:
            label = SentimentLabel.BEARISH.value
        else:
            label = SentimentLabel.NEUTRAL.value
        relevance_score = safe_float(analysis_input.context.get("relevance_score"), default=0.0) if analysis_input.context else 0.0
        symbol_match = analysis_input.symbol.lower() in text or bool(analysis_input.company_name and analysis_input.company_name.lower() in text)
        relevance = 1.0 if symbol_match else relevance_score if relevance_score > 0 else None
        confidence = max(0.12, min(0.22 + (0.14 if relevance else 0.0) + min(abs(positive_hits - negative_hits) * 0.12, 0.28), 0.82))
        impact_strength = max(0.08, min(0.16 + (0.10 if relevance else 0.0) + min(impact_hits * 0.12, 0.36), 0.86))
        catalyst = self._infer_catalyst(text)
        horizon = TimeHorizon.INTRADAY.value if impact_strength >= 0.58 else TimeHorizon.ONE_TO_THREE_DAYS.value if impact_strength >= 0.34 else TimeHorizon.ONE_TO_TWO_WEEKS.value
        reason_prefix = self.fallback_reason or "Local heuristic analysis used."
        return SentimentAnalysisResult(
            requested_analyzer=self.requested_analyzer,
            actual_analyzer=self.analyzer_name,
            provider=self.analyzer_name,
            model_family=self.model_family,
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=label,
            sentiment_score=sentiment_score_from_label(label, confidence),
            confidence=confidence,
            relevance=relevance,
            impact_strength=impact_strength,
            time_horizon=horizon,
            catalyst_tag=catalyst,
            short_reason=f"{reason_prefix} Keyword rules classified the article as {label}.",
            parse_status="heuristic_fallback" if self.requested_analyzer != self.analyzer_name else "ok",
            fallback_used=self.requested_analyzer != self.analyzer_name,
            fallback_reason=self.fallback_reason,
            schema_version="sentiment_analysis_result_v2_1",
            prompt_version=None,
            latency_ms=duration_ms(started),
            created_at=utc_now(),
            status=ModelExecutionStatus.FALLBACK_USED if self.requested_analyzer != self.analyzer_name else ModelExecutionStatus.SUCCESS,
            metadata={"positive_hits": positive_hits, "negative_hits": negative_hits, "impact_hits": impact_hits},
        )

    @staticmethod
    def _infer_catalyst(text: str) -> str:
        if any(term in text for term in {"earnings", "profit"}):
            return CatalystTag.EARNINGS.value
        if any(term in text for term in {"guidance", "forecast", "outlook"}):
            return CatalystTag.GUIDANCE.value
        if any(term in text for term in {"upgrade", "downgrade", "analyst"}):
            return CatalystTag.ANALYST_RATING.value
        if any(term in text for term in {"lawsuit", "probe", "investigation"}):
            return CatalystTag.LITIGATION.value
        if any(term in text for term in {"launch", "product", "device", "chip"}):
            return CatalystTag.PRODUCT.value
        if any(term in text for term in {"partnership", "partner"}):
            return CatalystTag.PARTNERSHIP.value
        if any(term in text for term in {"layoff", "layoffs"}):
            return CatalystTag.LAYOFFS.value
        if any(term in text for term in {"macro", "inflation", "rates", "fed", "tariff"}):
            return CatalystTag.MACRO.value
        return CatalystTag.OTHER.value


class GeminiSentimentAnalyzer:
    analyzer_name = "gemini"
    model_family = "gemini"
    analysis_method = "llm_json"

    def __init__(self, client: GeminiClient | None = None) -> None:
        self.client = client or GeminiClient()
        self.model_name = self.client.model
        self.model_version = self.client.model

    @property
    def configured(self) -> bool:
        return bool(self.client.configured)

    def analyze(self, analysis_input: SentimentAnalysisInput) -> SentimentAnalysisResult:
        from finsent.app.prompts.financial_sentiment import (
            FINANCIAL_SENTIMENT_PROMPT_VERSION,
            FINANCIAL_SENTIMENT_SCHEMA_VERSION,
            build_financial_sentiment_prompt,
        )

        started = perf_counter()
        if not self.configured:
            return self._failure(
                analysis_input,
                started,
                ModelFailureCategory.UNCONFIGURED,
                "Gemini is not configured.",
                parse_status="unconfigured",
            )
        symbol = _symbol_from_input(analysis_input)
        prompt = build_financial_sentiment_prompt(symbol, analysis_input)
        try:
            payload = self.client.generate_json(prompt, use_search_grounding=False, temperature=0.1, max_output_tokens=400)
        except Exception as exc:
            return self._failure(
                analysis_input,
                started,
                classify_model_exception(exc),
                safe_log_message(exc),
                parse_status="provider_failure",
            )
        normalized, errors = validate_gemini_payload(payload)
        if normalized is None:
            return self._failure(
                analysis_input,
                started,
                ModelFailureCategory.PARSE_FAILURE,
                "; ".join(errors),
                parse_status="parse_failure",
                metadata={"validation_errors": errors},
            )
        label = normalized["sentiment"]
        confidence = normalized["confidence"]
        return SentimentAnalysisResult(
            requested_analyzer=self.analyzer_name,
            actual_analyzer=self.analyzer_name,
            provider=self.analyzer_name,
            model_family=self.model_family,
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=label,
            sentiment_score=sentiment_score_from_label(label, confidence),
            confidence=confidence,
            relevance=1.0 if normalized["relevant"] else 0.0,
            impact_strength=normalized["impact_strength"],
            time_horizon=normalized["time_horizon"],
            catalyst_tag=normalized["catalyst_tag"],
            short_reason=normalized["short_reason"],
            parse_status="ok",
            fallback_used=False,
            fallback_reason=None,
            schema_version=FINANCIAL_SENTIMENT_SCHEMA_VERSION,
            prompt_version=FINANCIAL_SENTIMENT_PROMPT_VERSION,
            latency_ms=duration_ms(started),
            created_at=utc_now(),
            status=ModelExecutionStatus.SUCCESS,
            metadata={"raw_payload": payload},
        )

    def _failure(
        self,
        analysis_input: SentimentAnalysisInput,
        started: float,
        category: ModelFailureCategory,
        reason: str,
        *,
        parse_status: str,
        metadata: dict[str, Any] | None = None,
    ) -> SentimentAnalysisResult:
        return SentimentAnalysisResult(
            requested_analyzer=self.analyzer_name,
            actual_analyzer=self.analyzer_name,
            provider=self.analyzer_name,
            model_family=self.model_family,
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=SentimentLabel.NEUTRAL.value,
            sentiment_score=0.0,
            confidence=0.0,
            relevance=None,
            impact_strength=0.0,
            time_horizon=TimeHorizon.UNKNOWN.value,
            catalyst_tag=CatalystTag.UNKNOWN.value,
            short_reason=reason,
            parse_status=parse_status,
            fallback_used=False,
            fallback_reason=reason,
            schema_version="sentiment_analysis_result_v2_1",
            prompt_version="financial_sentiment_v2_1",
            latency_ms=duration_ms(started),
            created_at=utc_now(),
            status=ModelExecutionStatus.FAILED,
            failure_category=category,
            metadata=metadata or {},
        )


class FinBERTSentimentAnalyzer:
    analyzer_name = "finbert"
    model_family = "finbert"
    analysis_method = "classifier"

    def __init__(self, model_name: str | None = None, *, model: object | None = None, tokenizer: object | None = None, torch_module: object | None = None, device: str | None = None) -> None:
        self.model_name = model_name or settings.model_name
        self.model_version = self.model_name
        self.device = device or "cpu"
        self._model = model
        self._tokenizer = tokenizer
        self._torch = torch_module
        self._load_error: str | None = None

    @property
    def configured(self) -> bool:
        return True

    def analyze(self, analysis_input: SentimentAnalysisInput) -> SentimentAnalysisResult:
        started = perf_counter()
        if not analysis_input.text:
            return self._result(started, {"positive": 0.0, "negative": 0.0, "neutral": 1.0}, metadata={"empty_text": True})
        try:
            probabilities, metadata = self._predict_probabilities(analysis_input.text)
        except ImportError as exc:
            return self._unavailable(started, ModelFailureCategory.DEPENDENCY_MISSING, str(exc))
        except Exception as exc:
            return self._unavailable(started, ModelFailureCategory.INFERENCE_FAILURE, safe_log_message(exc))
        return self._result(started, probabilities, metadata=metadata)

    def _predict_probabilities(self, text: str) -> tuple[dict[str, float], dict[str, Any]]:
        if self._model is None or self._tokenizer is None or self._torch is None:
            try:
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
            except ImportError as exc:
                raise ImportError("FinBERT requires: pip install -r requirements-research.txt") from exc
            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self._model.eval()
        encoded = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
        with self._torch.no_grad():
            logits = self._model(**encoded).logits
            probs = self._torch.nn.functional.softmax(logits, dim=-1)[0].tolist()
        labels = [self._model.config.id2label[idx].lower() for idx in range(len(probs))]
        mapped = {label: float(prob) for label, prob in zip(labels, probs)}
        probabilities = {
            "positive": mapped.get("positive", mapped.get("bullish", 0.0)),
            "negative": mapped.get("negative", mapped.get("bearish", 0.0)),
            "neutral": mapped.get("neutral", 0.0),
        }
        total = sum(max(value, 0.0) for value in probabilities.values())
        if total <= 0:
            probabilities = {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
        else:
            probabilities = {key: max(value, 0.0) / total for key, value in probabilities.items()}
        return probabilities, {"probabilities": probabilities, "labels": labels, "device": self.device}

    def _result(self, started: float, probabilities: dict[str, float], *, metadata: dict[str, Any] | None = None) -> SentimentAnalysisResult:
        score = finbert_score(probabilities)
        label = label_from_score(score)
        confidence = max(probabilities.values()) if probabilities else 0.0
        return SentimentAnalysisResult(
            requested_analyzer=self.analyzer_name,
            actual_analyzer=self.analyzer_name,
            provider=self.analyzer_name,
            model_family=self.model_family,
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=label,
            sentiment_score=score,
            confidence=confidence,
            relevance=None,
            impact_strength=None,
            time_horizon=TimeHorizon.NOT_APPLICABLE.value,
            catalyst_tag=CatalystTag.NOT_APPLICABLE.value,
            short_reason=None,
            parse_status="ok",
            fallback_used=False,
            fallback_reason=None,
            schema_version="sentiment_analysis_result_v2_1",
            prompt_version=None,
            latency_ms=duration_ms(started),
            created_at=utc_now(),
            status=ModelExecutionStatus.SUCCESS,
            metadata=metadata or {"probabilities": probabilities, "device": self.device},
        )

    def _unavailable(self, started: float, category: ModelFailureCategory, reason: str) -> SentimentAnalysisResult:
        return SentimentAnalysisResult(
            requested_analyzer=self.analyzer_name,
            actual_analyzer=self.analyzer_name,
            provider=self.analyzer_name,
            model_family=self.model_family,
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=SentimentLabel.NEUTRAL.value,
            sentiment_score=0.0,
            confidence=0.0,
            relevance=None,
            impact_strength=None,
            time_horizon=TimeHorizon.NOT_APPLICABLE.value,
            catalyst_tag=CatalystTag.NOT_APPLICABLE.value,
            short_reason=reason,
            parse_status="dependency_missing" if category == ModelFailureCategory.DEPENDENCY_MISSING else "inference_failure",
            fallback_used=False,
            fallback_reason=reason,
            schema_version="sentiment_analysis_result_v2_1",
            prompt_version=None,
            latency_ms=duration_ms(started),
            created_at=utc_now(),
            status=ModelExecutionStatus.UNAVAILABLE,
            failure_category=category,
            metadata={"device": self.device},
        )


class OpenAIAnalyzerStubV2:
    analyzer_name = "openai"
    model_family = "openai"
    model_name = settings.openai_model
    model_version = settings.openai_model
    analysis_method = "stub"
    configured = False

    def analyze(self, analysis_input: SentimentAnalysisInput) -> SentimentAnalysisResult:
        started = perf_counter()
        return SentimentAnalysisResult(
            requested_analyzer=self.analyzer_name,
            actual_analyzer=self.analyzer_name,
            provider=self.analyzer_name,
            model_family=self.model_family,
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method=self.analysis_method,
            sentiment_label=SentimentLabel.NEUTRAL.value,
            sentiment_score=0.0,
            confidence=0.0,
            relevance=None,
            impact_strength=None,
            time_horizon=TimeHorizon.NOT_APPLICABLE.value,
            catalyst_tag=CatalystTag.NOT_APPLICABLE.value,
            short_reason="OpenAI analyzer is a stub and is not implemented in Phase 6.",
            parse_status="unconfigured",
            fallback_used=False,
            fallback_reason="OpenAI analyzer is deferred.",
            schema_version="sentiment_analysis_result_v2_1",
            prompt_version=None,
            latency_ms=duration_ms(started),
            created_at=utc_now(),
            status=ModelExecutionStatus.UNAVAILABLE,
            failure_category=ModelFailureCategory.UNCONFIGURED,
        )


def classify_model_exception(exc: Exception) -> ModelFailureCategory:
    provider_category = classify_exception(exc)
    mapping = {
        "AUTHENTICATION": ModelFailureCategory.AUTHENTICATION,
        "RATE_LIMIT": ModelFailureCategory.RATE_LIMIT,
        "TIMEOUT": ModelFailureCategory.TIMEOUT,
        "NETWORK": ModelFailureCategory.NETWORK,
        "INVALID_RESPONSE": ModelFailureCategory.INVALID_RESPONSE,
    }
    return mapping.get(str(getattr(provider_category, "value", provider_category)), ModelFailureCategory.UNKNOWN)


def build_sentiment_analyzer(name: str | None = None) -> SentimentAnalyzer:
    normalized = (name or settings.sentiment_provider or "gemini").strip().lower()
    if normalized == "gemini":
        return GeminiSentimentAnalyzer()
    if normalized == "finbert":
        return FinBERTSentimentAnalyzer()
    if normalized == "heuristic":
        return HeuristicSentimentAnalyzer()
    if normalized == "openai":
        return OpenAIAnalyzerStubV2()
    raise ValueError(f"Unknown sentiment analyzer: {name}")


def _symbol_from_input(analysis_input: SentimentAnalysisInput) -> SymbolRecord:
    return SymbolRecord(
        internal_id=f"{analysis_input.exchange.lower()}-{analysis_input.symbol.lower()}",
        ticker=analysis_input.symbol,
        display_name=analysis_input.company_name or analysis_input.symbol,
        exchange=analysis_input.exchange,
        provider_symbol=f"{analysis_input.exchange}:{analysis_input.symbol}" if analysis_input.exchange != "US" else analysis_input.symbol,
        ui_label=analysis_input.symbol,
        sector="Unknown",
    )

