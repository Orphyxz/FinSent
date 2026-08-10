from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.services.model_comparison import (
    ArticleSelectionService,
    GeminiFinBertExperimentRunner,
    ModelComparisonConfig,
    finbert_dependencies_available,
    summary_to_dict,
)
from finsent.app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or dry-run a controlled Gemini vs FinBERT comparison.")
    parser.add_argument("--symbols", nargs="*", default=[], help="Symbols to include, e.g. AAPL TCS.NS.")
    parser.add_argument("--market", nargs="*", default=[], help="Markets to include: US NSE BSE.")
    parser.add_argument("--start-date", default=None, help="Inclusive publication start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Inclusive publication end date, YYYY-MM-DD.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum articles. Default is deliberately small.")
    parser.add_argument("--horizons", nargs="*", default=["1h", "4h", "1d"], help="Horizons: 1h 4h 1d.")
    parser.add_argument("--experiment-name", default="Gemini vs FinBERT controlled comparison", help="Experiment name.")
    parser.add_argument("--reuse-existing", action="store_true", default=True, help="Reuse exact compatible existing runs.")
    parser.add_argument("--force-rerun", action="store_true", help="Ignore reusable model runs.")
    parser.add_argument("--export", action="store_true", help="Export paired CSV and summary JSON.")
    parser.add_argument("--output-dir", default="output/research", help="Export output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Select data and report readiness without model execution or writes.")
    parser.add_argument("--execute", action="store_true", help="Actually execute model/event runs. Required for non-dry execution.")
    return parser.parse_args()


def _parse_date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def main() -> None:
    configure_logging()
    args = parse_args()
    init_db()
    config = ModelComparisonConfig(
        experiment_name=args.experiment_name,
        symbols=args.symbols,
        markets=args.market,
        start_date=_parse_date(args.start_date),
        end_date=_parse_date(args.end_date),
        max_articles=args.limit,
        horizons=args.horizons,
        reuse_existing=args.reuse_existing,
        force_rerun=args.force_rerun,
    )
    with SessionLocal() as session:
        runner = GeminiFinBertExperimentRunner(session=session)
        selection = ArticleSelectionService(session).select_articles(config)
        print(f"Selected articles: {selection.selected_count}")
        print(f"Excluded articles: {selection.excluded_count}")
        print(f"Planned Gemini executions: <= {selection.selected_count if args.force_rerun else selection.selected_count}")
        print(f"Planned FinBERT executions: <= {selection.selected_count if args.force_rerun else selection.selected_count}")
        print(f"Horizons: {', '.join(config.horizons)}")
        if args.dry_run or not args.execute:
            summary = runner.dry_run(config)
            print("Mode: DRY_RUN")
            print(f"Gemini configured: {getattr(runner.gemini_analyzer, 'configured', False)}")
            print(f"FinBERT dependencies available: {finbert_dependencies_available()}")
            print(f"Dry-run readiness: {summary_to_dict(summary, include_rows=False)['exclusion_counts']}")
            print(f"Event-study coverage: {summary.config.get('dry_run_readiness', {}).get('event_study_coverage', {})}")
            return
        summary = runner.run(config, persist=True, export_dir=Path(args.output_dir) if args.export else None)
        session.commit()
        print("Mode: EXECUTED")
        print(f"Experiment ID: {summary.experiment_id}")
        print(f"Paired observations: {len(summary.paired_rows)}")
        print(f"Agreement N: {summary.agreement.eligible}")
        print(f"Agreement rate: {summary.agreement.agreement_rate}")
        if args.export:
            print(f"Exported under: {Path(args.output_dir) / str(summary.experiment_id or 'dry_run')}")


if __name__ == "__main__":
    main()
