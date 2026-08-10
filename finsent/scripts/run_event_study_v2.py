from __future__ import annotations

import argparse

from finsent.app.analysis.event_study_v2 import EventStudyHorizon
from finsent.app.database.base import SessionLocal, init_db
from finsent.app.services.event_study_service_v2 import EventStudyBatchRunnerV2
from finsent.app.services.symbol_registry import registry
from finsent.app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small explicit Event Study V2 evaluation over stored local data.")
    parser.add_argument("--symbol", default="AAPL", help="Symbol to evaluate, e.g. AAPL, TCS.NS, or BSE:TCS.")
    parser.add_argument("--horizon", action="append", choices=["1h", "4h", "1d"], help="Horizon to evaluate. Repeatable. Defaults to 1h.")
    parser.add_argument("--persist", action="store_true", help="Persist V2 results to event_study_results.")
    parser.add_argument("--experiment-id", type=int, default=None, help="Optional experiment_runs.id.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum stored articles to evaluate.")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    init_db()
    symbol = registry.resolve_any(args.symbol)
    if symbol is None:
        raise SystemExit(f"Unknown symbol: {args.symbol}")
    horizons = [EventStudyHorizon.parse(value) for value in (args.horizon or ["1h"])]
    with SessionLocal() as session:
        runner = EventStudyBatchRunnerV2(session=session)
        summary = runner.evaluate_stored_articles(
            instrument=symbol,
            horizons=horizons,
            limit=args.limit,
            persist=args.persist,
            experiment_id=args.experiment_id,
        )
        if args.persist:
            session.commit()
        print("Engine: finsent_event_study 2.0")
        print(f"Symbol: {symbol.exchange}:{symbol.ticker}")
        print(f"Evaluated: {summary.evaluated}")
        print(f"Valid: {summary.valid}")
        print(f"Invalid: {summary.invalid}")
        print(f"Persisted: {summary.persisted}")
        print(f"Statuses: {summary.status_counts}")


if __name__ == "__main__":
    main()
