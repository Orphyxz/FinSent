from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsent.app.database.entities import SignalRun
from finsent.app.database.research_repository import InstrumentRepository, ResearchResultRepository
from finsent.app.database.research_repository import json_loads
from finsent.app.services.llm_analyzers import ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_reliability import DataQualityAssessment
from finsent.app.services.signal_engine_v2 import (
    ENGINE_NAME_V2,
    ENGINE_VERSION_V2,
    SignalEngineV2,
    SignalInputV2,
    SignalNewsItemV2,
    SignalResultV2,
    result_metadata,
)
from finsent.app.services.symbol_registry import SymbolRecord


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(slots=True)
class SignalRunRecordV2:
    result: SignalResultV2
    persisted_run_id: int | None = None


class SignalEngineV2Service:
    def __init__(self, *, session: Session | None = None, engine: SignalEngineV2 | None = None) -> None:
        self.session = session
        self.engine = engine or SignalEngineV2()

    def build_input(
        self,
        *,
        instrument: SymbolRecord,
        news_pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]] | None = None,
        quote: QuoteSnapshot | None = None,
        price_bars: pd.DataFrame | None = None,
        quote_quality: DataQualityAssessment | None = None,
        bars_quality: DataQualityAssessment | None = None,
        news_quality: DataQualityAssessment | None = None,
        provider_metadata: dict[str, Any] | None = None,
        evaluation_timestamp: datetime | None = None,
    ) -> SignalInputV2:
        return SignalInputV2(
            instrument=instrument,
            evaluation_timestamp=evaluation_timestamp or utc_now(),
            news_items=[SignalNewsItemV2(article=article, analysis=analysis) for article, analysis in (news_pairs or [])],
            quote=quote,
            price_bars=price_bars,
            quote_quality=quote_quality,
            bars_quality=bars_quality,
            news_quality=news_quality,
            provider_metadata=provider_metadata or {},
        )

    def evaluate(
        self,
        signal_input: SignalInputV2,
        *,
        persist: bool = False,
        experiment_id: int | None = None,
    ) -> SignalRunRecordV2:
        result = self.engine.evaluate(signal_input)
        persisted_id = self.persist(signal_input, result, experiment_id=experiment_id) if persist else None
        return SignalRunRecordV2(result=result, persisted_run_id=persisted_id)

    def persist(self, signal_input: SignalInputV2, result: SignalResultV2, *, experiment_id: int | None = None) -> int:
        if self.session is None:
            raise ValueError("A SQLAlchemy session is required to persist Signal V2 runs.")
        instrument = InstrumentRepository(self.session).get_or_create_from_symbol(signal_input.instrument)
        reusable = self._latest_equivalent_live_run(
            instrument_id=instrument.id,
            provider_metadata=signal_input.provider_metadata,
            experiment_id=experiment_id,
        )
        if reusable is not None:
            return reusable.id
        metadata = result_metadata(result)
        row = ResearchResultRepository(self.session).store_signal_run(
            instrument_id=instrument.id,
            experiment_id=experiment_id,
            generated_at=result.generated_at,
            engine_name=ENGINE_NAME_V2,
            engine_version=ENGINE_VERSION_V2,
            final_score=result.final_score,
            label=result.label,
            confidence=result.confidence,
            signal_mode=result.signal_mode,
            input_quality=result.data_quality,
            provider_metadata=signal_input.provider_metadata,
            news_component=_component_value(result, "news"),
            market_component=_component_value(result, "price_momentum"),
            future_component=metadata,
            explanation=result.explanation,
        )
        return row.id

    def _latest_equivalent_live_run(
        self,
        *,
        instrument_id: int,
        provider_metadata: dict[str, Any],
        experiment_id: int | None,
    ) -> SignalRun | None:
        if provider_metadata.get("run_type") != "APPLICATION_LIVE_RUN":
            return None
        fingerprint = provider_metadata.get("input_fingerprint")
        if not fingerprint:
            return None
        stmt = select(SignalRun).where(
            SignalRun.instrument_id == instrument_id,
            SignalRun.engine_name == ENGINE_NAME_V2,
            SignalRun.engine_version == ENGINE_VERSION_V2,
        )
        stmt = stmt.where(SignalRun.experiment_id.is_(None)) if experiment_id is None else stmt.where(SignalRun.experiment_id == experiment_id)
        row = self.session.execute(stmt.order_by(SignalRun.generated_at.desc(), SignalRun.id.desc()).limit(1)).scalar_one_or_none()
        if row is None:
            return None
        existing = json_loads(row.provider_metadata_json, {})
        return row if existing.get("input_fingerprint") == fingerprint else None


def _component_value(result: SignalResultV2, name: str) -> float | None:
    for component in result.components:
        if component.name == name and component.available:
            return component.normalized_value
    return None
