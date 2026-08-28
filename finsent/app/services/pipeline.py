from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from finsent.app.analysis.market_impact import align_news_with_prices, build_daily_impact_summary
from finsent.app.config.settings import settings
from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.repository import NewsRepository, PriceRepository
from finsent.app.services.intelligence_service import intelligence_service
from finsent.app.services.news_providers import normalize_news_limit
from finsent.app.services.symbol_registry import registry


@dataclass(slots=True)
class PipelineResult:
    news_df: pd.DataFrame
    price_df: pd.DataFrame
    event_df: pd.DataFrame
    summary_df: pd.DataFrame


class FinSentPipeline:
    def __init__(self) -> None:
        pass

    def run(
        self,
        ticker: str | None = None,
        limit: int | None = None,
        return_window_minutes: int | None = None,
    ) -> PipelineResult:
        ticker = (ticker or settings.default_ticker).upper()
        limit = normalize_news_limit(limit, default=settings.default_news_limit)
        return_window_minutes = return_window_minutes or settings.default_return_window_minutes

        init_db()
        symbol = registry.resolve_any(ticker)
        if symbol is None:
            return PipelineResult(
                news_df=pd.DataFrame(),
                price_df=pd.DataFrame(),
                event_df=pd.DataFrame(),
                summary_df=pd.DataFrame(),
            )

        intelligence_service.run(symbol, news_limit=limit)

        with SessionLocal() as session:
            news_repo = NewsRepository(session)
            price_repo = PriceRepository(session)
            ui_ticker = symbol.yahoo_symbol
            news_df = news_repo.list_news_df(ticker=ui_ticker, exchange=symbol.exchange)
            price_df = price_repo.list_price_df(ticker=ui_ticker)

        event_df = align_news_with_prices(
            news_df=news_df,
            price_df=price_df,
            return_window_minutes=return_window_minutes,
        )
        summary_df = build_daily_impact_summary(event_df)

        return PipelineResult(
            news_df=news_df,
            price_df=price_df,
            event_df=event_df,
            summary_df=summary_df,
        )
