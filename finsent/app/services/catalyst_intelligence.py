from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import Iterable, Sequence

import pandas as pd


CATALYST_CLASSIFIER_VERSION = "catalyst-intelligence-v1.0"


class CatalystType(str, Enum):
    EARNINGS = "EARNINGS"
    GUIDANCE = "GUIDANCE"
    M_AND_A = "M_AND_A"
    REGULATION = "REGULATION"
    LITIGATION = "LITIGATION"
    PRODUCT = "PRODUCT"
    PARTNERSHIP = "PARTNERSHIP"
    ANALYST_RATING = "ANALYST_RATING"
    MANAGEMENT = "MANAGEMENT"
    LAYOFFS = "LAYOFFS"
    FINANCING = "FINANCING"
    MACRO = "MACRO"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class CatalystDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class ImpactLabel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class TimeHorizon(str, Enum):
    INTRADAY = "INTRADAY"
    SHORT_TERM = "SHORT_TERM"
    MULTI_DAY = "MULTI_DAY"
    MEDIUM_TERM = "MEDIUM_TERM"
    UNKNOWN = "UNKNOWN"


class NoveltyLabel(str, Enum):
    NEW = "NEW"
    REPEATED = "REPEATED"
    ONGOING = "ONGOING"


class FreshnessLabel(str, Enum):
    FRESH = "FRESH"
    RECENT = "RECENT"
    AGING = "AGING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class CatalystArticleInput:
    article_id: str
    primary_symbol: str
    title: str
    summary: str = ""
    source: str = ""
    url: str = ""
    published_at: datetime | pd.Timestamp | None = None
    sentiment_label: str | None = None
    sentiment_confidence: float | None = None
    relevance_score: float | None = None
    stored_catalyst: str | None = None


@dataclass(frozen=True, slots=True)
class CatalystResult:
    article_id: str
    url: str
    source: str
    published_at: datetime | None
    primary_symbol: str
    affected_symbols: tuple[str, ...]
    catalyst_type: CatalystType
    primary_catalyst: str
    secondary_catalysts: tuple[str, ...]
    event_title: str
    event_summary: str
    direction: CatalystDirection
    impact_score: float
    impact_label: ImpactLabel
    confidence: float
    time_horizon: TimeHorizon
    novelty_score: float
    novelty_label: NoveltyLabel
    recency_score: float
    freshness_label: FreshnessLabel
    event_group_id: str
    classifier: str
    version: str
    evidence_tags: tuple[str, ...]
    created_at: datetime
    catalyst_priority: float
    related_article_count: int
    related_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CatalystProfile:
    catalyst_type: CatalystType
    patterns: tuple[str, ...]
    evidence: tuple[str, ...]
    base_impact: float
    default_horizon: TimeHorizon


_PROFILES: tuple[_CatalystProfile, ...] = (
    _CatalystProfile(CatalystType.GUIDANCE, ("guidance", "outlook", "forecast", "expects", "raises forecast", "cuts forecast", "lowers forecast"), ("guidance", "outlook"), 0.76, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.EARNINGS, ("earnings", "quarterly results", "q1", "q2", "q3", "q4", "revenue", "eps", "profit", "loss", "results"), ("earnings", "results"), 0.72, TimeHorizon.SHORT_TERM),
    _CatalystProfile(CatalystType.M_AND_A, ("acquire", "acquires", "acquisition", "merger", "takeover", "buyout", "deal to buy", "stake in"), ("m&a", "deal"), 0.78, TimeHorizon.MEDIUM_TERM),
    _CatalystProfile(CatalystType.REGULATION, ("approval", "approved", "fda", "sec", "doj", "regulator", "regulatory", "antitrust", "probe", "investigation"), ("regulation", "approval"), 0.70, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.LITIGATION, ("lawsuit", "sues", "settlement", "court", "judge", "trial", "patent dispute", "class action"), ("litigation", "legal"), 0.68, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.PRODUCT, ("launches", "unveils", "introduces", "product", "chip", "ai platform", "software", "model", "vehicle", "iphone"), ("product", "launch"), 0.54, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.PARTNERSHIP, ("partners", "partnership", "collaboration", "alliance", "contract", "supply agreement", "deal with"), ("partnership", "contract"), 0.50, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.ANALYST_RATING, ("upgrade", "upgrades", "downgrade", "downgrades", "initiates", "price target", "rating", "overweight", "underperform", "buy rating", "sell rating"), ("analyst", "rating"), 0.48, TimeHorizon.SHORT_TERM),
    _CatalystProfile(CatalystType.MANAGEMENT, ("ceo", "cfo", "resigns", "steps down", "appoints", "names", "chairman", "board"), ("management", "leadership"), 0.50, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.LAYOFFS, ("layoff", "layoffs", "job cuts", "cuts jobs", "restructuring", "workforce reduction"), ("layoffs", "restructuring"), 0.58, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.FINANCING, ("offering", "debt", "convertible", "loan", "funding", "capital raise", "share sale", "buyback", "dividend"), ("financing", "capital"), 0.56, TimeHorizon.MULTI_DAY),
    _CatalystProfile(CatalystType.MACRO, ("fed", "federal reserve", "inflation", "cpi", "rates", "tariff", "jobs report", "gdp", "recession", "treasury yields"), ("macro", "economy"), 0.62, TimeHorizon.INTRADAY),
)

_STORED_CATALYST_MAP = {
    "earnings": CatalystType.EARNINGS,
    "guidance": CatalystType.GUIDANCE,
    "m_and_a": CatalystType.M_AND_A,
    "m&a": CatalystType.M_AND_A,
    "regulation": CatalystType.REGULATION,
    "litigation": CatalystType.LITIGATION,
    "product": CatalystType.PRODUCT,
    "partnership": CatalystType.PARTNERSHIP,
    "analyst_rating": CatalystType.ANALYST_RATING,
    "management": CatalystType.MANAGEMENT,
    "layoffs": CatalystType.LAYOFFS,
    "financing": CatalystType.FINANCING,
    "macro": CatalystType.MACRO,
}

_BULLISH_PATTERNS = (
    "beats",
    "beat estimates",
    "tops estimates",
    "raises guidance",
    "raises outlook",
    "raises forecast",
    "upgrades",
    "upgrade",
    "price target raised",
    "wins approval",
    "approved",
    "record revenue",
    "strong demand",
    "buyback",
    "dividend increase",
    "surges",
    "rises",
)
_BEARISH_PATTERNS = (
    "misses",
    "miss estimates",
    "cuts guidance",
    "lowers guidance",
    "cuts forecast",
    "downgrades",
    "downgrade",
    "price target cut",
    "lawsuit",
    "probe",
    "investigation",
    "antitrust",
    "fine",
    "recall",
    "layoffs",
    "resigns",
    "falls",
    "slumps",
)
_MATERIALITY_PATTERNS = (
    "billion",
    "million",
    "record",
    "major",
    "exclusive",
    "approval",
    "investigation",
    "lawsuit",
    "antitrust",
    "acquisition",
    "merger",
    "beats",
    "misses",
    "raises guidance",
    "cuts guidance",
)
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "after",
    "before",
    "amid",
    "over",
    "into",
    "stock",
    "shares",
    "market",
    "says",
    "report",
    "reports",
    "company",
    "inc",
    "corp",
    "ltd",
    "plc",
}


class CatalystIntelligenceService:
    """Deterministic catalyst classification over already-loaded news records."""

    classifier = "deterministic_rules"
    version = CATALYST_CLASSIFIER_VERSION

    def __init__(self) -> None:
        self._cache: dict[str, CatalystResult] = {}

    def analyze(self, articles: Sequence[CatalystArticleInput]) -> list[CatalystResult]:
        created_at = _utc_now()
        provisional: list[CatalystResult] = []
        for article in articles:
            cache_key = self._cache_key(article)
            cached = self._cache.get(cache_key)
            if cached is None:
                cached = self._classify(article, created_at)
                self._cache[cache_key] = cached
            provisional.append(cached)
        return self._apply_group_novelty(provisional)

    def classify(self, article: CatalystArticleInput) -> CatalystResult:
        return self.analyze([article])[0]

    def _classify(self, article: CatalystArticleInput, created_at: datetime) -> CatalystResult:
        text = _normalize_text(f"{article.title} {article.summary}")
        scored = self._score_profiles(text)
        stored_type = _stored_type(article.stored_catalyst)
        if scored:
            primary_type = scored[0][0].catalyst_type
            secondary_types = tuple(profile.catalyst_type.value for profile, _score in scored[1:4])
            default_horizon = scored[0][0].default_horizon
            evidence = tuple(dict.fromkeys(tag for profile, _score in scored[:4] for tag in profile.evidence))
            base_impact = scored[0][0].base_impact
        elif stored_type is not None:
            primary_type = stored_type
            secondary_types = ()
            default_horizon = self._profile_for_type(stored_type).default_horizon if self._profile_for_type(stored_type) else TimeHorizon.UNKNOWN
            evidence = (stored_type.value.lower(), "stored_sentiment_catalyst")
            base_impact = self._profile_for_type(stored_type).base_impact if self._profile_for_type(stored_type) else 0.35
        else:
            primary_type = CatalystType.UNKNOWN if not text.strip() else CatalystType.OTHER
            secondary_types = ()
            default_horizon = TimeHorizon.UNKNOWN
            evidence = ("no_specific_catalyst",)
            base_impact = 0.20

        direction = _infer_direction(text, primary_type, article.sentiment_label)
        impact_score = self._impact_score(text, base_impact, direction, article)
        confidence = self._confidence(text, primary_type, article, scored)
        published_at = _coerce_datetime(article.published_at)
        recency_score, freshness = _recency(published_at)
        event_group_id = _event_group_id(article.primary_symbol, primary_type, direction, text, published_at)
        novelty_score = 1.0
        novelty_label = NoveltyLabel.NEW
        priority = _priority(impact_score, recency_score, novelty_score, confidence)

        return CatalystResult(
            article_id=str(article.article_id or ""),
            url=str(article.url or ""),
            source=str(article.source or ""),
            published_at=published_at,
            primary_symbol=str(article.primary_symbol or "").upper().strip(),
            affected_symbols=_affected_symbols(article.primary_symbol, text),
            catalyst_type=primary_type,
            primary_catalyst=primary_type.value,
            secondary_catalysts=secondary_types,
            event_title=_compact_title(article.title, primary_type),
            event_summary=_compact_summary(article.summary, article.title),
            direction=direction,
            impact_score=impact_score,
            impact_label=_impact_label(impact_score),
            confidence=confidence,
            time_horizon=_infer_horizon(text, primary_type, default_horizon),
            novelty_score=novelty_score,
            novelty_label=novelty_label,
            recency_score=recency_score,
            freshness_label=freshness,
            event_group_id=event_group_id,
            classifier=self.classifier,
            version=self.version,
            evidence_tags=evidence,
            created_at=created_at,
            catalyst_priority=priority,
            related_article_count=1,
            related_sources=(str(article.source or "") or "unknown",),
        )

    def _score_profiles(self, text: str) -> list[tuple[_CatalystProfile, float]]:
        scored: list[tuple[_CatalystProfile, float]] = []
        for position, profile in enumerate(_PROFILES):
            matches = sum(_contains_phrase(text, pattern) for pattern in profile.patterns)
            if matches:
                score = matches + profile.base_impact + ((len(_PROFILES) - position) * 0.001)
                scored.append((profile, score))
        return sorted(scored, key=lambda item: item[1], reverse=True)

    def _profile_for_type(self, catalyst_type: CatalystType) -> _CatalystProfile | None:
        for profile in _PROFILES:
            if profile.catalyst_type == catalyst_type:
                return profile
        return None

    def _impact_score(
        self,
        text: str,
        base_impact: float,
        direction: CatalystDirection,
        article: CatalystArticleInput,
    ) -> float:
        score = base_impact
        score += 0.04 * sum(_contains_phrase(text, pattern) for pattern in _MATERIALITY_PATTERNS)
        if direction in {CatalystDirection.BULLISH, CatalystDirection.BEARISH, CatalystDirection.MIXED}:
            score += 0.04
        if article.relevance_score is not None:
            score += 0.05 * min(max(float(article.relevance_score), 0.0), 1.0)
        if article.sentiment_confidence is not None:
            score += 0.05 * min(max(float(article.sentiment_confidence), 0.0), 1.0)
        return round(float(min(max(score, 0.05), 0.95)), 3)

    def _confidence(
        self,
        text: str,
        primary_type: CatalystType,
        article: CatalystArticleInput,
        scored: list[tuple[_CatalystProfile, float]],
    ) -> float:
        if primary_type == CatalystType.UNKNOWN:
            return 0.20
        base = 0.48 if primary_type == CatalystType.OTHER else 0.62
        if scored:
            base += min(scored[0][1] * 0.035, 0.16)
        if article.sentiment_confidence is not None:
            base += 0.08 * min(max(float(article.sentiment_confidence), 0.0), 1.0)
        if len(text.split()) >= 8:
            base += 0.05
        return round(float(min(max(base, 0.15), 0.92)), 3)

    def _apply_group_novelty(self, results: Sequence[CatalystResult]) -> list[CatalystResult]:
        grouped: dict[str, list[CatalystResult]] = {}
        for result in results:
            grouped.setdefault(result.event_group_id, []).append(result)
        related_counts = {group_id: len(group) for group_id, group in grouped.items()}
        related_sources = {
            group_id: tuple(sorted({source for source in (row.source or "unknown" for row in group) if source}))
            for group_id, group in grouped.items()
        }
        output: list[CatalystResult] = []
        for group_id, group in grouped.items():
            ordered = sorted(group, key=lambda row: row.published_at or datetime.min)
            first_ts = ordered[0].published_at
            for index, result in enumerate(ordered):
                novelty_label = NoveltyLabel.NEW
                novelty_score = 1.0
                if index > 0:
                    delta_hours = (
                        (result.published_at - first_ts).total_seconds() / 3600.0
                        if result.published_at is not None and first_ts is not None
                        else 0.0
                    )
                    if delta_hours <= 6:
                        novelty_label = NoveltyLabel.REPEATED
                        novelty_score = 0.45
                    else:
                        novelty_label = NoveltyLabel.ONGOING
                        novelty_score = 0.65
                output.append(
                    replace(
                        result,
                        novelty_label=novelty_label,
                        novelty_score=novelty_score,
                        catalyst_priority=_priority(result.impact_score, result.recency_score, novelty_score, result.confidence),
                        related_article_count=related_counts[group_id],
                        related_sources=related_sources[group_id],
                    )
                )
        return sorted(output, key=lambda row: row.catalyst_priority, reverse=True)

    def _cache_key(self, article: CatalystArticleInput) -> str:
        raw = "|".join(
            [
                str(article.article_id or ""),
                str(article.primary_symbol or ""),
                str(article.title or ""),
                str(article.summary or ""),
                str(article.published_at or ""),
            ]
        )
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def catalyst_results_to_records(results: Iterable[CatalystResult]) -> list[dict[str, object]]:
    return [
        {
            "article_id": result.article_id,
            "url": result.url,
            "source": result.source,
            "published_at": result.published_at,
            "primary_symbol": result.primary_symbol,
            "affected_symbols": ", ".join(result.affected_symbols),
            "catalyst_type": result.catalyst_type.value,
            "primary_catalyst": result.primary_catalyst,
            "secondary_catalysts": ", ".join(result.secondary_catalysts),
            "event_title": result.event_title,
            "event_summary": result.event_summary,
            "catalyst_direction": result.direction.value,
            "catalyst_impact_score": result.impact_score,
            "catalyst_impact_label": result.impact_label.value,
            "catalyst_confidence": result.confidence,
            "catalyst_time_horizon": result.time_horizon.value,
            "novelty_score": result.novelty_score,
            "novelty_label": result.novelty_label.value,
            "recency_score": result.recency_score,
            "freshness_label": result.freshness_label.value,
            "event_group_id": result.event_group_id,
            "classifier": result.classifier,
            "classifier_version": result.version,
            "evidence_tags": ", ".join(result.evidence_tags),
            "created_at": result.created_at,
            "catalyst_priority": result.catalyst_priority,
            "related_article_count": result.related_article_count,
            "related_sources": ", ".join(result.related_sources),
        }
        for result in results
    ]


def build_catalyst_inputs_from_news_frame(news_df: pd.DataFrame) -> list[CatalystArticleInput]:
    if news_df.empty:
        return []
    inputs: list[CatalystArticleInput] = []
    for _, row in news_df.iterrows():
        article_id = row.get("id")
        if pd.isna(article_id):
            article_id = row.get("dedupe_hash") or row.get("url") or row.get("title") or ""
        inputs.append(
            CatalystArticleInput(
                article_id=str(article_id),
                primary_symbol=str(row.get("ticker") or "").upper().strip(),
                title=str(row.get("title") or ""),
                summary=str(row.get("summary") or ""),
                source=str(row.get("source") or row.get("provider") or ""),
                url=str(row.get("url") or ""),
                published_at=row.get("published_at"),
                sentiment_label=str(row.get("sentiment_label") or "") or None,
                sentiment_confidence=_optional_float(row.get("model_confidence") if row.get("model_confidence") is not None else row.get("signal_confidence")),
                relevance_score=_optional_float(row.get("relevance_score")),
                stored_catalyst=str(row.get("catalyst_tag") or "") or None,
            )
        )
    return inputs


def _stored_type(value: str | None) -> CatalystType | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "unknown", "not_applicable", "none", "other"}:
        return None
    return _STORED_CATALYST_MAP.get(normalized)


def _infer_direction(text: str, catalyst_type: CatalystType, sentiment_label: str | None) -> CatalystDirection:
    bullish = sum(_contains_phrase(text, pattern) for pattern in _BULLISH_PATTERNS)
    bearish = sum(_contains_phrase(text, pattern) for pattern in _BEARISH_PATTERNS)
    if bullish and bearish:
        return CatalystDirection.MIXED
    if bullish:
        return CatalystDirection.BULLISH
    if bearish:
        return CatalystDirection.BEARISH
    sentiment = str(sentiment_label or "").strip().lower()
    if sentiment in {"bullish", "positive"} and catalyst_type not in {CatalystType.UNKNOWN, CatalystType.OTHER}:
        return CatalystDirection.BULLISH
    if sentiment in {"bearish", "negative"} and catalyst_type not in {CatalystType.UNKNOWN, CatalystType.OTHER}:
        return CatalystDirection.BEARISH
    if catalyst_type in {CatalystType.UNKNOWN, CatalystType.OTHER}:
        return CatalystDirection.UNKNOWN
    return CatalystDirection.NEUTRAL


def _infer_horizon(text: str, catalyst_type: CatalystType, default_horizon: TimeHorizon) -> TimeHorizon:
    if any(_contains_phrase(text, pattern) for pattern in ("today", "premarket", "after hours", "market open", "intraday")):
        return TimeHorizon.INTRADAY
    if catalyst_type == CatalystType.ANALYST_RATING:
        return TimeHorizon.SHORT_TERM
    if catalyst_type in {CatalystType.M_AND_A, CatalystType.REGULATION, CatalystType.LITIGATION}:
        return TimeHorizon.MEDIUM_TERM if _contains_phrase(text, "merger") or _contains_phrase(text, "court") else default_horizon
    return default_horizon


def _recency(published_at: datetime | None) -> tuple[float, FreshnessLabel]:
    if published_at is None:
        return 0.35, FreshnessLabel.UNKNOWN
    now = _utc_now()
    age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    if age_hours <= 2:
        return 1.0, FreshnessLabel.FRESH
    if age_hours <= 24:
        return round(max(0.55, 1.0 - (age_hours / 48.0)), 3), FreshnessLabel.RECENT
    if age_hours <= 72:
        return round(max(0.25, 0.62 - ((age_hours - 24.0) / 120.0)), 3), FreshnessLabel.AGING
    return 0.15, FreshnessLabel.STALE


def _event_group_id(
    symbol: str,
    catalyst_type: CatalystType,
    direction: CatalystDirection,
    text: str,
    published_at: datetime | None,
) -> str:
    date_key = published_at.strftime("%Y%m%d") if published_at else "nodate"
    signature_tokens = _signature_tokens(text, catalyst_type)
    raw = "|".join([str(symbol or "").upper(), catalyst_type.value, direction.value, date_key, "-".join(signature_tokens)])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _signature_tokens(text: str, catalyst_type: CatalystType) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]{3,}", text)
    filtered = [word for word in words if word not in _STOPWORDS and word not in {"announces", "update", "latest"}]
    if catalyst_type == CatalystType.ANALYST_RATING:
        analyst_words = [word for word in filtered if word in {"upgrade", "upgrades", "downgrade", "downgrades", "initiates", "target", "morgan", "stanley", "bofa", "goldman", "jpmorgan", "ubs", "wells", "citi"}]
        return tuple(analyst_words[:4] or filtered[:3])
    if catalyst_type == CatalystType.EARNINGS:
        return ("earnings",)
    if catalyst_type == CatalystType.GUIDANCE:
        return ("guidance",)
    return tuple(filtered[:4])


def _affected_symbols(primary_symbol: str, text: str) -> tuple[str, ...]:
    del text
    symbol = str(primary_symbol or "").upper().strip()
    return (symbol,) if symbol else ()


def _impact_label(score: float) -> ImpactLabel:
    if score >= 0.80:
        return ImpactLabel.VERY_HIGH
    if score >= 0.55:
        return ImpactLabel.HIGH
    if score >= 0.30:
        return ImpactLabel.MEDIUM
    return ImpactLabel.LOW


def _priority(impact: float, recency: float, novelty: float, confidence: float) -> float:
    return round(float(max(impact, 0.0) * max(recency, 0.0) * max(novelty, 0.0) * max(confidence, 0.0)), 4)


def _compact_title(title: str, catalyst_type: CatalystType) -> str:
    clean = " ".join(str(title or "").split())
    if clean:
        return clean[:180]
    return f"{catalyst_type.value.replace('_', ' ').title()} catalyst"


def _compact_summary(summary: str, title: str) -> str:
    clean = " ".join(str(summary or "").split())
    if not clean:
        clean = " ".join(str(title or "").split())
    return clean[:260]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.lower().strip()
    if not phrase:
        return False
    if " " in phrase or "&" in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _coerce_datetime(value: object) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert("UTC").tz_localize(None) if hasattr(ts, "tz_convert") else ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts


def _optional_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


catalyst_intelligence_service = CatalystIntelligenceService()
