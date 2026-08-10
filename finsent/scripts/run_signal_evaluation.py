from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluationConfig, HistoricalSignalEvaluator, export_signal_evaluation
from finsent.app.services.research_dataset import ResearchCohortConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or dry-run historical Signal V1/V2 evaluation over stored research articles.")
    parser.add_argument("--symbols", nargs="*", default=[])
    parser.add_argument("--market", nargs="*", default=[])
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--horizons", nargs="*", default=["1h", "4h", "1d"])
    parser.add_argument("--engines", nargs="*", default=["v1", "v2"], choices=["v1", "v2"])
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--holdout-start", default=None)
    parser.add_argument("--experiment-name", default="Historical Signal Evaluation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output-dir", default="output/research")
    return parser.parse_args()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def main() -> None:
    args = parse_args()
    init_db()
    config = HistoricalSignalEvaluationConfig(
        experiment_name=args.experiment_name,
        engines=args.engines,
        horizons=args.horizons,
        cohort=ResearchCohortConfig(
            symbols=args.symbols,
            markets=args.market,
            start_date=_dt(args.start_date),
            end_date=_dt(args.end_date),
            horizons=args.horizons,
            limit=args.limit,
            seed=args.seed,
            holdout_start=_dt(args.holdout_start),
        ),
        export=args.export,
    )
    with SessionLocal() as session:
        evaluator = HistoricalSignalEvaluator(session)
        if args.dry_run or not args.execute:
            summary = evaluator.dry_run(config)
            print("Mode: DRY_RUN")
            print(f"Cohort fingerprint: {summary.cohort_fingerprint}")
            print(f"Rows expected: {len(summary.rows)}")
            print(f"Coverage: {summary.coverage}")
            print(f"Expected V1 runs: {summary.coverage.get('articles', 0) if 'v1' in args.engines else 0}")
            print(f"Expected V2 runs: {summary.coverage.get('articles', 0) if 'v2' in args.engines else 0}")
            return
        summary = evaluator.run(config, persist=True, export_dir=Path(args.output_dir) if args.export else None)
        session.commit()
        print("Mode: EXECUTED")
        print(f"Experiment ID: {summary.experiment_id}")
        print(f"Rows: {len(summary.rows)}")
        if args.export:
            print(f"Exported under: {Path(args.output_dir) / str(summary.experiment_id or 'dry_run')}")


if __name__ == "__main__":
    main()
