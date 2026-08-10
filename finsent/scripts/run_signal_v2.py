from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.repository import NewsRepository, PriceRepository, QuoteSnapshotRepository, SignalSnapshotRepository
from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_service_v2 import SignalEngineV2Service
from finsent.app.services.symbol_registry import registry
from finsent.app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small explicit Signal Engine V2 evaluation over stored local data.")
    parser.add_argument("--symbol", default="AAPL", help="Symbol to evaluate, e.g. AAPL or TCS.NS.")
    parser.add_argument("--engine", choices=["v1", "v2"], default="v2", help="Engine to run explicitly.")
    parser.add_argument("--persist", action="store_true", help="Persist V2 result to signal_runs.")
    parser.add_argument("--experiment-id", type=int, default=None, help="Optional experiment_runs.id.")
    parser.add_argument("--compare-v1", action="store_true", help="Also print a small V1 result over the same stored inputs.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum stored news rows to use.")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    init_db()
    symbol = registry.resolve_any(args.symbol)
    if symbol is None:
        print(f"Unknown symbol: {args.symbol}")
        return

    with SessionLocal() as session:
        news_df = NewsRepository(session).list_news_df(symbol.ticker, symbol.exchange).tail(max(0, min(args.limit, 25)))
        price_df = PriceRepository(session).list_price_df(_storage_ticker(symbol))
        quote_row = QuoteSnapshotRepository(session).latest_for_symbol(symbol.ticker, symbol.exchange)
        quote = _quote_from_row(quote_row, symbol) if quote_row is not None else None
        news_pairs = _pairs_from_df(news_df)

        if args.engine == "v2":
            service = SignalEngineV2Service(session=session)
            signal_input = service.build_input(
                instrument=symbol,
                news_pairs=news_pairs,
                quote=quote,
                price_bars=_bars_from_df(price_df),
                provider_metadata={"source": "stored_local_data"},
            )
            record = service.evaluate(signal_input, persist=args.persist, experiment_id=args.experiment_id)
            if args.persist:
                session.commit()
            result = record.result
            print(f"Engine: {result.engine_name} {result.engine_version}")
            print(f"Label: {result.label}")
            print(f"Score: {result.final_score:.4f}")
            print(f"Confidence: {result.confidence:.4f} ({result.confidence_label})")
            print(f"Mode: {result.signal_mode}")
            print(f"Persisted run: {record.persisted_run_id if record.persisted_run_id is not None else 'not persisted'}")
            print(f"Explanation: {result.explanation}")

        if args.engine == "v1" or args.compare_v1:
            aggregate = AggregateAnalysis("neutral", 0.0, "no strong edge", "watch", "Stored local V1 smoke.", "stored")
            v1 = CompositeSignalEngine().compute(quote, news_pairs, aggregate)
            print(f"V1 label: {v1.composite_label}")
            print(f"V1 score: {v1.composite_score:.4f}")
            print(f"V1 confidence: {v1.signal_confidence:.4f}")


def _storage_ticker(symbol) -> str:
    if symbol.exchange == "NSE":
        return f"{symbol.ticker}.NS"
    if symbol.exchange == "BSE":
        return f"{symbol.ticker}.BO"
    return symbol.ticker


def _bars_from_df(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return frame.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}).set_index("timestamp")


def _pairs_from_df(frame: pd.DataFrame) -> list[tuple[NormalizedNewsArticle, ArticleAnalysis]]:
    pairs: list[tuple[NormalizedNewsArticle, ArticleAnalysis]] = []
    for row in frame.to_dict("records"):
        article = NormalizedNewsArticle(
            article_id=str(row.get("id") or row.get("dedupe_hash") or row.get("url")),
            ticker=str(row.get("ticker") or ""),
            exchange=str(row.get("exchange") or "US"),
            source=str(row.get("source") or ""),
            title=str(row.get("title") or ""),
            summary=row.get("summary"),
            url=str(row.get("url") or ""),
            published_at=pd.to_datetime(row.get("published_at")).to_pydatetime(),
            ingested_at=pd.to_datetime(row.get("ingested_at") or row.get("published_at")).to_pydatetime(),
            provider=str(row.get("provider") or "stored"),
            dedupe_hash=str(row.get("dedupe_hash") or row.get("url")),
            relevance_score=float(row.get("relevance_score") or 0.0),
        )
        analysis = ArticleAnalysis(
            relevant=bool(row.get("relevant", 1)),
            sentiment=str(row.get("sentiment_label") or "neutral"),
            confidence=float(row.get("model_confidence") or 0.0),
            impact_strength=float(row.get("impact_strength") or 0.0),
            time_horizon=str(row.get("time_horizon") or "1-3d"),
            catalyst_tag=str(row.get("catalyst_tag") or "other"),
            short_reason=str(row.get("short_reason") or ""),
            provider=str(row.get("analysis_provider") or "stored"),
            parse_status=str(row.get("parse_status") or "ok"),
        )
        pairs.append((article, analysis))
    return pairs


def _quote_from_row(row, symbol) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol.ticker,
        exchange=symbol.exchange,
        provider_symbol=symbol.provider_symbol,
        current_price=row.current_price,
        currency=row.currency,
        bid=row.bid,
        ask=row.ask,
        spread_absolute=row.spread_absolute,
        spread_percentage=row.spread_percentage,
        volume=row.volume,
        market_timestamp=row.market_timestamp,
        ingested_at=row.ingested_at or datetime.now(timezone.utc).replace(tzinfo=None),
        provider=row.provider,
        freshness_seconds=row.freshness_seconds,
        quality_status=row.quality_status,
        note=row.note or "stored quote",
    )


if __name__ == "__main__":
    main()
