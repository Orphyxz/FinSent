from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from finsent.app.analysis.event_study_v2 import (
    ENGINE_NAME_EVENT_STUDY_V2,
    ENGINE_VERSION_EVENT_STUDY_V2,
    EventStudyEngineV2,
    EventStudyHorizon,
    EventStudyInputV2,
    EventStudyResultV2,
)
from finsent.app.database.repository import NewsRepository, PriceRepository
from finsent.app.database.research_repository import InstrumentRepository, ResearchResultRepository
from finsent.app.services.symbol_registry import SymbolRecord


@dataclass(slots=True)
class EventStudyRunRecordV2:
    result: EventStudyResultV2
    persisted_result_id: int | None = None


@dataclass(slots=True)
class EventStudyBatchSummaryV2:
    evaluated: int
    persisted: int
    valid: int
    invalid: int
    status_counts: dict[str, int]
    records: list[EventStudyRunRecordV2]


class EventStudyServiceV2:
    def __init__(self, *, session: Session | None = None, engine: EventStudyEngineV2 | None = None) -> None:
        self.session = session
        self.engine = engine or EventStudyEngineV2()

    def build_input(
        self,
        *,
        instrument: SymbolRecord,
        event_timestamp,
        price_bars: pd.DataFrame,
        horizons: list[EventStudyHorizon] | None = None,
        event_timezone: str | None = None,
        bars_timezone: str | None = None,
        article_id: int | None = None,
        sentiment_run_id: int | None = None,
        signal_run_id: int | None = None,
        experiment_id: int | None = None,
        provider: str | None = None,
        source: str | None = None,
        data_quality_label: str | None = None,
        data_quality_score: float | None = None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> EventStudyInputV2:
        return EventStudyInputV2(
            instrument=instrument,
            event_timestamp=event_timestamp,
            price_bars=price_bars,
            horizons=horizons or [EventStudyHorizon.parse("1h")],
            event_timezone=event_timezone,
            bars_timezone=bars_timezone,
            article_id=article_id,
            sentiment_run_id=sentiment_run_id,
            signal_run_id=signal_run_id,
            experiment_id=experiment_id,
            provider=provider,
            source=source,
            data_quality_label=data_quality_label,
            data_quality_score=data_quality_score,
            provider_metadata=provider_metadata or {},
        )

    def evaluate(self, study_input: EventStudyInputV2, *, persist: bool = False) -> list[EventStudyRunRecordV2]:
        results = self.engine.evaluate(study_input)
        records: list[EventStudyRunRecordV2] = []
        for result in results:
            persisted_id = self.persist(result) if persist else None
            records.append(EventStudyRunRecordV2(result=result, persisted_result_id=persisted_id))
        return records

    def persist(self, result: EventStudyResultV2) -> int:
        if self.session is None:
            raise ValueError("A SQLAlchemy session is required to persist Event Study V2 results.")
        instrument = InstrumentRepository(self.session).get_or_create_from_symbol(result.instrument)
        metadata = dict(result.metadata)
        metadata.update(
            {
                "engine_name": ENGINE_NAME_EVENT_STUDY_V2,
                "engine_version": ENGINE_VERSION_EVENT_STUDY_V2,
                "effective_event_timestamp": result.effective_event_timestamp.isoformat() if result.effective_event_timestamp else None,
                "entry_timestamp": result.entry_timestamp.isoformat() if result.entry_timestamp else None,
                "match_quality": result.match_quality.value,
                "bar_frequency": result.bar_frequency.value,
                "quality_warnings": result.quality_warnings,
                "log_return": result.log_return,
                "elapsed_trading_minutes": result.elapsed_trading_minutes,
                "provider": result.provider,
                "source": result.source,
            }
        )
        row = ResearchResultRepository(self.session).store_event_study_result(
            instrument_id=instrument.id,
            article_id=result.article_id,
            sentiment_run_id=result.sentiment_run_id,
            signal_run_id=result.signal_run_id,
            experiment_id=result.experiment_id,
            event_timestamp=result.original_event_timestamp,
            horizon_minutes=result.horizon.horizon_minutes,
            target_timestamp=result.target_timestamp,
            matched_market_timestamp=result.matched_exit_timestamp,
            entry_price=result.entry_price,
            exit_price=result.exit_price,
            raw_return=result.raw_return,
            matching_method=result.matching_method,
            elapsed_minutes=result.elapsed_wall_clock_minutes,
            data_quality_label=result.data_quality_label,
            status=result.status.value,
            validity_reason="; ".join(result.quality_warnings) if result.quality_warnings else None,
            metadata=metadata,
        )
        return row.id


class EventStudyBatchRunnerV2:
    def __init__(self, *, session: Session, service: EventStudyServiceV2 | None = None) -> None:
        self.session = session
        self.service = service or EventStudyServiceV2(session=session)

    def evaluate_inputs(self, inputs: list[EventStudyInputV2], *, persist: bool = False) -> EventStudyBatchSummaryV2:
        records: list[EventStudyRunRecordV2] = []
        for study_input in inputs:
            records.extend(self.service.evaluate(study_input, persist=persist))
        return self._summary(records)

    def evaluate_stored_articles(
        self,
        *,
        instrument: SymbolRecord,
        horizons: list[EventStudyHorizon],
        limit: int = 5,
        persist: bool = False,
        experiment_id: int | None = None,
    ) -> EventStudyBatchSummaryV2:
        news_df = NewsRepository(self.session).list_news_df(instrument.ticker, instrument.exchange).tail(max(limit, 0))
        price_df = PriceRepository(self.session).list_price_df(instrument.ticker)
        inputs: list[EventStudyInputV2] = []
        for _, row in news_df.iterrows():
            inputs.append(
                self.service.build_input(
                    instrument=instrument,
                    event_timestamp=row["published_at"],
                    price_bars=price_df,
                    horizons=horizons,
                    article_id=int(row["id"]) if "id" in row and pd.notna(row["id"]) else None,
                    experiment_id=experiment_id,
                    provider=str(row.get("provider")) if pd.notna(row.get("provider")) else None,
                    source=str(row.get("source")) if pd.notna(row.get("source")) else None,
                )
            )
        return self.evaluate_inputs(inputs, persist=persist)

    @staticmethod
    def _summary(records: list[EventStudyRunRecordV2]) -> EventStudyBatchSummaryV2:
        status_counts: dict[str, int] = {}
        for record in records:
            status = record.result.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        valid = status_counts.get("VALID", 0)
        persisted = sum(1 for record in records if record.persisted_result_id is not None)
        return EventStudyBatchSummaryV2(
            evaluated=len(records),
            persisted=persisted,
            valid=valid,
            invalid=len(records) - valid,
            status_counts=status_counts,
            records=records,
        )
