from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from finsent.app.database.entities import (
    ArticleInstrument,
    DataQualityAssessmentEntity,
    DatasetMetadata,
    EventStudyResult,
    ExperimentRun,
    Instrument,
    ProviderAuditRun,
    SentimentAnalysisRun,
    SignalRun,
)
from finsent.app.services.provider_contracts import ProviderFailureCategory, ProviderResult
from finsent.app.services.provider_reliability import DataQualityAssessment
from finsent.app.services.symbol_registry import SymbolRecord
from finsent.app.utils.logging import safe_log_message


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def canonicalize_url(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or parts.path
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def canonical_symbol(exchange: str, ticker: str) -> str:
    return f"{exchange.upper().strip()}:{ticker.upper().strip()}"


def _enum_value(value: object | None) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def commit_or_rollback(session: Session) -> None:
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise


class InstrumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_canonical_symbol(self, value: str) -> Instrument | None:
        return self.session.execute(
            select(Instrument).where(Instrument.canonical_symbol == value.upper().strip())
        ).scalar_one_or_none()

    def get_or_create(
        self,
        *,
        canonical_symbol_value: str,
        display_symbol: str,
        exchange: str,
        company_name: str | None = None,
        market: str | None = None,
        currency: str | None = None,
        sector: str | None = None,
        provider_symbols: dict[str, str] | None = None,
        active: bool = True,
    ) -> Instrument:
        canonical = canonical_symbol_value.upper().strip()
        instrument = self.get_by_canonical_symbol(canonical)
        now = utc_now()
        if instrument is None:
            instrument = Instrument(
                canonical_symbol=canonical,
                display_symbol=display_symbol.upper().strip(),
                company_name=company_name,
                exchange=exchange.upper().strip(),
                market=market,
                currency=currency,
                sector=sector,
                provider_symbols_json=json_dumps(provider_symbols or {}),
                active=1 if active else 0,
                created_at=now,
                updated_at=now,
            )
            self.session.add(instrument)
        else:
            instrument.display_symbol = display_symbol.upper().strip()
            instrument.company_name = company_name or instrument.company_name
            instrument.exchange = exchange.upper().strip()
            instrument.market = market or instrument.market
            instrument.currency = currency or instrument.currency
            instrument.sector = sector or instrument.sector
            if provider_symbols is not None:
                instrument.provider_symbols_json = json_dumps(provider_symbols)
            instrument.active = 1 if active else 0
            instrument.updated_at = now
        self.session.flush()
        return instrument

    def get_or_create_from_symbol(self, symbol: SymbolRecord) -> Instrument:
        ticker = getattr(symbol, "ticker")
        exchange = getattr(symbol, "exchange")
        provider_symbol = getattr(symbol, "provider_symbol", f"{exchange}:{ticker}" if exchange != "US" else ticker)
        provider_symbols = {"default": provider_symbol}
        polygon_symbol = getattr(symbol, "polygon_symbol", None)
        kite_instrument_key = getattr(symbol, "kite_instrument_key", None)
        if polygon_symbol:
            provider_symbols["polygon"] = polygon_symbol
        if kite_instrument_key:
            provider_symbols["kite"] = kite_instrument_key
        market = "US" if exchange == "US" else "India"
        currency = "USD" if exchange == "US" else "INR"
        return self.get_or_create(
            canonical_symbol_value=canonical_symbol(exchange, ticker),
            display_symbol=ticker,
            exchange=exchange,
            company_name=getattr(symbol, "display_name", ticker),
            market=market,
            currency=currency,
            sector=getattr(symbol, "sector", None),
            provider_symbols=provider_symbols,
            active=True,
        )


class ArticleRelationshipRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def link_article_to_instrument(
        self,
        *,
        article_id: int,
        instrument_id: int,
        relevance_score: float | None,
        association_source: str,
    ) -> ArticleInstrument:
        existing = self.session.execute(
            select(ArticleInstrument).where(
                ArticleInstrument.article_id == article_id,
                ArticleInstrument.instrument_id == instrument_id,
                ArticleInstrument.association_source == association_source,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.relevance_score = relevance_score
            self.session.flush()
            return existing
        link = ArticleInstrument(
            article_id=article_id,
            instrument_id=instrument_id,
            relevance_score=relevance_score,
            association_source=association_source,
            created_at=utc_now(),
        )
        self.session.add(link)
        self.session.flush()
        return link


class ExperimentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        name: str,
        experiment_type: str,
        configuration: dict[str, Any] | None = None,
        code_version_label: str | None = None,
        dataset_id: str | None = None,
        notes: str | None = None,
    ) -> ExperimentRun:
        run = ExperimentRun(
            name=name,
            experiment_type=experiment_type,
            created_at=utc_now(),
            completed_at=None,
            status="RUNNING",
            configuration_json=json_dumps(configuration or {}),
            code_version_label=code_version_label,
            dataset_id=dataset_id,
            notes=notes,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def complete(self, experiment_id: int, *, status: str = "COMPLETED", notes: str | None = None) -> ExperimentRun:
        run = self.session.get(ExperimentRun, experiment_id)
        if run is None:
            raise ValueError(f"ExperimentRun {experiment_id} does not exist")
        run.status = status
        run.completed_at = utc_now()
        if notes is not None:
            run.notes = notes
        self.session.flush()
        return run

    def configuration(self, run: ExperimentRun) -> dict[str, Any]:
        return json_loads(run.configuration_json, {})


class ResearchResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store_sentiment_run(
        self,
        *,
        article_id: int,
        model_family: str,
        model_name: str,
        analysis_method: str,
        instrument_id: int | None = None,
        experiment_id: int | None = None,
        provider: str | None = None,
        model_version: str | None = None,
        prompt_version: str | None = None,
        schema_version: str | None = None,
        sentiment_label: str | None = None,
        sentiment_score: float | None = None,
        confidence: float | None = None,
        relevance: float | None = None,
        impact_strength: float | None = None,
        time_horizon: str | None = None,
        catalyst_tag: str | None = None,
        short_reason: str | None = None,
        parse_status: str | None = None,
        fallback_used: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SentimentAnalysisRun:
        run = SentimentAnalysisRun(
            article_id=article_id,
            instrument_id=instrument_id,
            experiment_id=experiment_id,
            provider=provider,
            model_family=model_family,
            model_name=model_name,
            model_version=model_version,
            analysis_method=analysis_method,
            prompt_version=prompt_version,
            schema_version=schema_version,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            confidence=confidence,
            relevance=relevance,
            impact_strength=impact_strength,
            time_horizon=time_horizon,
            catalyst_tag=catalyst_tag,
            short_reason=short_reason,
            parse_status=parse_status,
            fallback_used=1 if fallback_used else 0,
            metadata_json=json_dumps(metadata or {}),
            created_at=utc_now(),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def store_signal_run(
        self,
        *,
        instrument_id: int,
        generated_at: datetime,
        engine_name: str,
        engine_version: str,
        final_score: float | None,
        label: str | None,
        confidence: float | None,
        signal_mode: str | None,
        experiment_id: int | None = None,
        legacy_signal_snapshot_id: int | None = None,
        input_quality: dict[str, Any] | None = None,
        provider_metadata: dict[str, Any] | None = None,
        news_component: float | None = None,
        market_component: float | None = None,
        future_component: dict[str, Any] | None = None,
        explanation: str | None = None,
    ) -> SignalRun:
        run = SignalRun(
            instrument_id=instrument_id,
            experiment_id=experiment_id,
            legacy_signal_snapshot_id=legacy_signal_snapshot_id,
            generated_at=generated_at,
            engine_name=engine_name,
            engine_version=engine_version,
            final_score=final_score,
            label=label,
            confidence=confidence,
            signal_mode=signal_mode,
            input_quality_json=json_dumps(input_quality or {}),
            provider_metadata_json=json_dumps(provider_metadata or {}),
            news_component=news_component,
            market_component=market_component,
            future_component_json=json_dumps(future_component) if future_component is not None else None,
            explanation=explanation,
            created_at=utc_now(),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def store_event_study_result(
        self,
        *,
        instrument_id: int,
        event_timestamp: datetime,
        horizon_minutes: int,
        status: str,
        article_id: int | None = None,
        sentiment_run_id: int | None = None,
        signal_run_id: int | None = None,
        experiment_id: int | None = None,
        target_timestamp: datetime | None = None,
        matched_market_timestamp: datetime | None = None,
        entry_price: float | None = None,
        exit_price: float | None = None,
        raw_return: float | None = None,
        benchmark_adjusted_return: float | None = None,
        matching_method: str | None = None,
        elapsed_minutes: float | None = None,
        data_quality_label: str | None = None,
        validity_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventStudyResult:
        result = EventStudyResult(
            article_id=article_id,
            sentiment_run_id=sentiment_run_id,
            signal_run_id=signal_run_id,
            experiment_id=experiment_id,
            instrument_id=instrument_id,
            event_timestamp=event_timestamp,
            horizon_minutes=horizon_minutes,
            target_timestamp=target_timestamp,
            matched_market_timestamp=matched_market_timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            raw_return=raw_return,
            benchmark_adjusted_return=benchmark_adjusted_return,
            matching_method=matching_method,
            elapsed_minutes=elapsed_minutes,
            data_quality_label=data_quality_label,
            status=status,
            validity_reason=validity_reason,
            metadata_json=json_dumps(metadata or {}),
            created_at=utc_now(),
        )
        self.session.add(result)
        self.session.flush()
        return result


class ProviderAuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_provider_result(
        self,
        *,
        result: ProviderResult[Any],
        operation: str,
        instrument_id: int | None = None,
        record_count: int | None = None,
    ) -> ProviderAuditRun:
        started_at = result.fetched_at
        selected_attempt = next((attempt for attempt in result.attempts if attempt.selected), None)
        failure_category = None
        if selected_attempt is not None and selected_attempt.category is not None:
            failure_category = _enum_value(selected_attempt.category)
        elif result.attempts:
            last_category = result.attempts[-1].category
            failure_category = _enum_value(last_category)

        quality = result.quality
        quality_score = getattr(quality, "score", None)
        quality_label = _enum_value(getattr(quality, "label", None))
        freshness_label = _enum_value(getattr(quality, "freshness", None)) or _enum_value(result.freshness)
        safe_message = safe_log_message(result.message or result.status.message)
        audit = ProviderAuditRun(
            provider=result.provider,
            leaf_provider=result.leaf_provider,
            service=result.service,
            operation=operation,
            instrument_id=instrument_id,
            started_at=started_at,
            completed_at=result.fetched_at,
            status=_enum_value(result.status.status) or str(result.status.status),
            failure_category=failure_category,
            data_mode=_enum_value(result.data_mode),
            from_cache=1 if result.from_cache else 0,
            fallback_used=1 if result.fallback_used else 0,
            source_timestamp=result.source_timestamp,
            attempt_count=len(result.attempts),
            duration_ms=selected_attempt.duration_ms if selected_attempt is not None else None,
            record_count=record_count,
            quality_score=quality_score,
            quality_label=quality_label,
            freshness_label=freshness_label,
            safe_message=safe_message,
        )
        self.session.add(audit)
        self.session.flush()
        return audit

    def record_manual(
        self,
        *,
        provider: str,
        service: str,
        operation: str,
        status: str,
        safe_message: str | None = None,
        failure_category: ProviderFailureCategory | str | None = None,
        leaf_provider: str | None = None,
        instrument_id: int | None = None,
        data_mode: str | None = None,
        from_cache: bool = False,
        fallback_used: bool = False,
        source_timestamp: datetime | None = None,
        attempt_count: int | None = None,
        duration_ms: int | None = None,
        record_count: int | None = None,
    ) -> ProviderAuditRun:
        now = utc_now()
        audit = ProviderAuditRun(
            provider=provider,
            leaf_provider=leaf_provider,
            service=service,
            operation=operation,
            instrument_id=instrument_id,
            started_at=now,
            completed_at=now,
            status=status,
            failure_category=_enum_value(failure_category),
            data_mode=data_mode,
            from_cache=1 if from_cache else 0,
            fallback_used=1 if fallback_used else 0,
            source_timestamp=source_timestamp,
            attempt_count=attempt_count,
            duration_ms=duration_ms,
            record_count=record_count,
            safe_message=safe_log_message(safe_message),
        )
        self.session.add(audit)
        self.session.flush()
        return audit


class DataQualityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store_assessment(
        self,
        *,
        subject_type: str,
        subject_id: int | None,
        assessment: DataQualityAssessment,
    ) -> DataQualityAssessmentEntity:
        entity = DataQualityAssessmentEntity(
            subject_type=subject_type,
            subject_id=subject_id,
            score=assessment.score,
            label=_enum_value(assessment.label),
            reasons_json=json_dumps(assessment.reasons),
            freshness=_enum_value(assessment.freshness),
            provider=assessment.provider,
            mode=_enum_value(assessment.mode),
            evaluated_at=assessment.evaluated_at,
        )
        self.session.add(entity)
        self.session.flush()
        return entity


class DatasetRegistryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_metadata(
        self,
        *,
        dataset_id: str,
        name: str,
        path: str,
        dataset_type: str,
        status: str,
        market: str | None = None,
        frequency: str | None = None,
        date_start: datetime | None = None,
        date_end: datetime | None = None,
        symbol_count: int | None = None,
        row_count: int | None = None,
        file_size_bytes: int | None = None,
        source: str | None = None,
        checksum: str | None = None,
        columns: Iterable[str] | None = None,
        issues: Iterable[str] | None = None,
        notes: str | None = None,
        last_scanned_at: datetime | None = None,
    ) -> DatasetMetadata:
        existing = self.session.execute(
            select(DatasetMetadata).where(DatasetMetadata.dataset_id == dataset_id)
        ).scalar_one_or_none()
        entity = existing or DatasetMetadata(dataset_id=dataset_id)
        entity.name = name
        entity.path = path
        entity.dataset_type = dataset_type
        entity.market = market
        entity.frequency = frequency
        entity.date_start = date_start
        entity.date_end = date_end
        entity.symbol_count = symbol_count
        entity.row_count = row_count
        entity.file_size_bytes = file_size_bytes
        entity.status = status
        entity.source = source
        entity.checksum = checksum
        entity.last_scanned_at = last_scanned_at or utc_now()
        entity.columns_json = json_dumps(list(columns or []))
        entity.issues_json = json_dumps(list(issues or []))
        entity.notes = notes
        if existing is None:
            self.session.add(entity)
        self.session.flush()
        return entity
