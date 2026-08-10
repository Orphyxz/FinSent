from __future__ import annotations

import argparse

from sqlalchemy import select

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.entities import NewsArticle
from finsent.app.database.research_repository import InstrumentRepository
from finsent.app.services.sentiment_intelligence import SentimentIntelligenceService
from finsent.app.services.sentiment_v2 import SentimentAnalysisInput
from finsent.app.services.symbol_registry import registry
from finsent.app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small explicit Sentiment Intelligence V2 analysis over stored articles.")
    parser.add_argument("--symbol", default="AAPL", help="Symbol to select stored articles for, e.g. AAPL or TCS.NS.")
    parser.add_argument("--article-id", type=int, default=None, help="Analyze one stored news_articles.id.")
    parser.add_argument("--analyzer", choices=["gemini", "finbert", "heuristic"], default="heuristic", help="Analyzer to request.")
    parser.add_argument("--experiment-id", type=int, default=None, help="Optional experiment_runs.id for persisted model runs.")
    parser.add_argument("--limit", type=int, default=3, help="Maximum articles to analyze; clamped by service safety limits.")
    parser.add_argument("--no-persist", action="store_true", help="Execute without writing sentiment_analysis_runs.")
    return parser.parse_args()


def _input_from_row(row: NewsArticle, instrument_id: int | None) -> SentimentAnalysisInput:
    return SentimentAnalysisInput(
        article_id=row.id,
        instrument_id=instrument_id or row.instrument_id,
        symbol=row.ticker,
        company_name=None,
        exchange=row.exchange or "US",
        title=row.title,
        summary=row.summary,
        body=None,
        publisher=row.publisher or row.source,
        published_at=row.published_at,
        source_provider=row.source_provider or row.provider,
        leaf_provider=row.leaf_provider,
        data_mode=row.data_mode,
        language=None,
        context={"dedupe_hash": row.dedupe_hash, "relevance_score": row.relevance_score},
    )


def main() -> None:
    configure_logging()
    args = parse_args()
    init_db()
    symbol = registry.resolve_any(args.symbol)

    with SessionLocal() as session:
        stmt = select(NewsArticle).order_by(NewsArticle.published_at.desc())
        if args.article_id is not None:
            stmt = stmt.where(NewsArticle.id == args.article_id)
        elif symbol is not None:
            stmt = stmt.where(NewsArticle.ticker == symbol.ticker, NewsArticle.exchange == symbol.exchange)
        else:
            stmt = stmt.where(NewsArticle.ticker == args.symbol.upper())
        rows = session.execute(stmt.limit(max(0, min(args.limit, 50)))).scalars().all()
        if not rows:
            print("No stored articles matched the request.")
            return

        instrument_id = None
        if symbol is not None:
            instrument_id = InstrumentRepository(session).get_or_create_from_symbol(symbol).id
        inputs = [_input_from_row(row, instrument_id) for row in rows]
        service = SentimentIntelligenceService(session=session)
        summary = service.analyze_articles(
            inputs,
            analyzer_name=args.analyzer,
            experiment_id=args.experiment_id,
            limit=args.limit,
            persist=not args.no_persist,
        )
        if not args.no_persist:
            session.commit()

        print(f"Requested analyzer: {summary.requested_analyzer}")
        print(f"Attempted: {summary.attempted}")
        print(f"Succeeded: {summary.succeeded}")
        print(f"Failed: {summary.failed}")
        print(f"Persisted: {summary.persisted}")
        for record in summary.records:
            result = record.result
            persisted = record.persisted_run_id if record.persisted_run_id is not None else "not persisted"
            print(
                f"- article={record.input.article_id} actual={result.actual_analyzer} "
                f"label={result.sentiment_label} score={result.sentiment_score:.3f} "
                f"status={result.status.value} parse={result.parse_status} run={persisted}"
            )


if __name__ == "__main__":
    main()
