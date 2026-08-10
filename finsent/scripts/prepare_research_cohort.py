from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.research_repository import ExperimentRepository
from finsent.app.services.historical_news_acquisition import (
    DEFAULT_NORMALIZED_DIR,
    FNSPIDAcquisitionConfig,
    FNSPIDPartialAcquirer,
    PriceAcquisitionConfig,
    ResearchSubsetImporter,
    YFinanceDailyPriceAcquirer,
    apply_sentiment_result_to_article,
    article_rows_for_sentiment,
    default_batch_id,
    export_normalized_articles,
    readiness_report,
)
from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluationConfig, HistoricalSignalEvaluator
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig
from finsent.app.services.sentiment_intelligence import SentimentIntelligenceService
from finsent.app.services.sentiment_v2 import SentimentAnalysisInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a bounded real historical research cohort.")
    parser.add_argument("--source", choices=["fnspid"], default="fnspid")
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "AMZN"])
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-scan-rows", type=int, default=200_000)
    parser.add_argument("--horizons", nargs="+", default=["1d"])
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acquire-prices", action="store_true")
    parser.add_argument("--analyze-finbert", action="store_true")
    parser.add_argument("--analyze-gemini", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="output/research/phase11")
    return parser.parse_args()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _sentiment_input(row) -> SentimentAnalysisInput:
    return SentimentAnalysisInput(
        article_id=row.id,
        instrument_id=row.instrument_id,
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
        context={"dedupe_hash": row.dedupe_hash, "relevance_score": row.relevance_score},
    )


def main() -> None:
    args = parse_args()
    if args.analyze_gemini and not args.execute:
        print("Gemini analysis requires --execute; dry-run will report readiness only.")
    execute = bool(args.execute)
    start = _dt(args.start_date)
    end = _dt(args.end_date)
    batch_id = args.batch_id or default_batch_id("phase11")
    dataset_id = f"phase11_{args.source}_{batch_id}"

    init_db()
    acquisition = FNSPIDPartialAcquirer().acquire(
        FNSPIDAcquisitionConfig(
            symbols=args.symbols,
            start_date=start,
            end_date=end,
            limit=args.limit,
            max_scan_rows=args.max_scan_rows,
            batch_id=batch_id,
            dry_run=not execute,
        )
    )
    print(f"Source: {acquisition.source_name}")
    print(f"Mode: {'EXECUTE' if execute else 'DRY_RUN'}")
    print(f"Requested symbols: {', '.join(acquisition.requested_symbols)}")
    print(f"Scanned rows: {acquisition.scanned_rows}")
    print(f"Candidate articles: {acquisition.matched_rows}")
    print(f"Estimated full source bytes: {acquisition.estimated_disk_bytes}")
    if acquisition.scan_limit_reached:
        print("Scan limit reached before article limit.")
    ready = readiness_report()
    print(f"FinBERT dependencies available: {ready['finbert_dependencies_available']}")
    print(f"Gemini configured: {ready['gemini_configured']}")

    with SessionLocal() as session:
        if execute and acquisition.subset_path:
            import_summary = ResearchSubsetImporter(session).import_fnspid_subset(Path(acquisition.subset_path), dataset_id=dataset_id, dry_run=False)
            session.commit()
            print(f"Imported articles: {import_summary.imported}")
            print(f"Import duplicates: {import_summary.duplicates}")
            print(f"Import invalid: {import_summary.invalid} {import_summary.invalid_reasons}")
            if args.export:
                export_path = DEFAULT_NORMALIZED_DIR / f"normalized_articles_{batch_id}.csv"
                export_normalized_articles(acquisition.records, export_path)
                print(f"Normalized export: {export_path}")

        if execute and args.acquire_prices:
            price_summary = YFinanceDailyPriceAcquirer().acquire(
                PriceAcquisitionConfig(symbols=args.symbols, start_date=start, end_date=end, batch_id=batch_id, dry_run=False),
                session=session,
            )
            session.commit()
            print(f"Price rows: {price_summary.imported_rows}")
            print(f"Price failures: {price_summary.failures}")

        cohort_config = ResearchCohortConfig(
            symbols=args.symbols,
            markets=["US"],
            start_date=start,
            end_date=end,
            horizons=args.horizons,
            limit=args.limit,
            seed=42,
            dataset_id=dataset_id,
        )
        cohort = ResearchCohortBuilder(session).build(cohort_config)
        print(f"Cohort fingerprint: {cohort.fingerprint}")
        print(f"Cohort eligible articles: {len(cohort.samples)}")
        print(f"Cohort coverage: {cohort.coverage_summary}")
        print(f"Cohort exclusions: {cohort.exclusion_counts}")

        experiment_id = None
        if execute and (args.analyze_finbert or args.analyze_gemini or args.evaluate):
            experiment = ExperimentRepository(session).create(
                name="Phase 11 preliminary real-data cohort",
                experiment_type="phase11_real_historical_cohort",
                configuration={
                    "dataset_id": dataset_id,
                    "batch_id": batch_id,
                    "symbols": args.symbols,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "horizons": args.horizons,
                    "cohort_fingerprint": cohort.fingerprint,
                    "preliminary": True,
                },
                dataset_id=dataset_id,
                notes="PRELIMINARY Phase 11 real-data execution.",
            )
            experiment_id = experiment.id

        if execute and args.analyze_finbert:
            rows = article_rows_for_sentiment(session, symbols=args.symbols, start_date=start, end_date=end, limit=min(args.limit, 20))
            service = SentimentIntelligenceService(session=session, fallback_to_heuristic=False)
            attempted = succeeded = failed = persisted = 0
            for row in rows:
                attempted += 1
                record = service.analyze(_sentiment_input(row), analyzer_name="finbert", experiment_id=experiment_id, persist=True)
                if record.result.status.value == "SUCCESS":
                    succeeded += 1
                    apply_sentiment_result_to_article(row, record.result)
                else:
                    failed += 1
                if record.persisted_run_id is not None:
                    persisted += 1
            session.commit()
            print(f"FinBERT attempted: {attempted}")
            print(f"FinBERT succeeded: {succeeded}")
            print(f"FinBERT failed: {failed}")
            print(f"FinBERT persisted: {persisted}")

        if execute and args.analyze_gemini:
            if not ready["gemini_configured"]:
                print("Gemini skipped: unconfigured.")
            else:
                rows = article_rows_for_sentiment(session, symbols=args.symbols, start_date=start, end_date=end, limit=min(args.limit, 10))
                service = SentimentIntelligenceService(session=session, fallback_to_heuristic=False)
                summary = service.analyze_articles(
                    [_sentiment_input(row) for row in rows],
                    analyzer_name="gemini",
                    experiment_id=experiment_id,
                    limit=len(rows),
                    persist=True,
                )
                session.commit()
                print(f"Gemini attempted: {summary.attempted}")
                print(f"Gemini succeeded: {summary.succeeded}")
                print(f"Gemini failed: {summary.failed}")
                print(f"Gemini persisted: {summary.persisted}")

        if execute and args.evaluate:
            signal_summary = HistoricalSignalEvaluator(session).run(
                HistoricalSignalEvaluationConfig(
                    experiment_name="PRELIMINARY Phase 11 real-data signal evaluation",
                    engines=["v1", "v2"],
                    horizons=args.horizons,
                    cohort=cohort_config,
                    sentiment_source="STORED_NEWS_ARTICLE_FIELDS",
                    export=args.export,
                ),
                persist=True,
                export_dir=Path(args.output_dir) if args.export else None,
            )
            session.commit()
            print(f"PRELIMINARY signal evaluation rows: {len(signal_summary.rows)}")
            for metric in signal_summary.metrics_by_engine_horizon:
                print(
                    f"PRELIMINARY {metric['engine']} {metric['horizon']} "
                    f"strict_accuracy={metric['strict_accuracy']} (N={metric['total']})"
                )


if __name__ == "__main__":
    main()
