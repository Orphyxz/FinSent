from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import select

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.entities import NewsArticle, SentimentAnalysisRun
from finsent.app.database.research_repository import ExperimentRepository
from finsent.app.services.historical_news_acquisition import (
    DEFAULT_NORMALIZED_DIR,
    ResearchSubsetImporter,
    apply_sentiment_result_to_article,
    export_normalized_articles,
)
from finsent.app.services.historical_signal_evaluation import HistoricalSignalEvaluationConfig, HistoricalSignalEvaluator
from finsent.app.services.phase12_research import (
    DEFAULT_PHASE12_BATCH_ID,
    StratifiedFNSPIDAcquisitionConfig,
    StratifiedFNSPIDAcquirer,
    YahooChartDailyPriceAcquirer,
    YahooChartDailyPriceConfig,
    cohort_selection_config,
    evaluate_rows_by_split,
    export_v2_diagnostic_from_rows,
    phase12_preregistration,
    render_locked_baseline_report,
    summarize_v2_diagnostic,
    systematic_disagreement_cases,
    v2_parameter_registry,
    write_preregistration,
)
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig
from finsent.app.services.sentiment_intelligence import SentimentIntelligenceService
from finsent.app.services.sentiment_v2 import SentimentAnalysisInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 12 locked-cohort diagnostics and baseline evaluation.")
    parser.add_argument("--write-preregistration", action="store_true")
    parser.add_argument("--diagnose-phase11", action="store_true")
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--import-subset", action="store_true")
    parser.add_argument("--acquire-prices", action="store_true")
    parser.add_argument("--analyze-finbert", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-id", default=DEFAULT_PHASE12_BATCH_ID)
    parser.add_argument("--output-dir", default="output/research/phase12")
    parser.add_argument("--phase11-rows", default="output/research/phase12_reproduction/3/signal_evaluation_rows.csv")
    parser.add_argument("--phase11-diagnostic", default="output/research/phase12_v2_diagnostic.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    execute = bool(args.execute) and not args.dry_run
    prereg = phase12_preregistration()
    output_dir = Path(args.output_dir)
    init_db()

    if args.write_preregistration:
        path = write_preregistration(Path("docs") / "PHASE12_COHORT_PREREGISTRATION.md", prereg)
        print(f"Preregistration: {path}")
        policy = Path("docs") / "SIGNAL_TUNING_POLICY.md"
        policy.write_text(render_tuning_policy(), encoding="utf-8")
        print(f"Tuning policy: {policy}")

    with SessionLocal() as session:
        if args.diagnose_phase11:
            diagnostic_path = export_v2_diagnostic_from_rows(session, Path(args.phase11_rows), Path(args.phase11_diagnostic))
            print(f"Phase 11 V2 diagnostic: {diagnostic_path}")
            print(f"Diagnostic summary: {summarize_v2_diagnostic(diagnostic_path)}")

        acquisition = None
        if args.acquire:
            acquisition = StratifiedFNSPIDAcquirer().acquire(
                StratifiedFNSPIDAcquisitionConfig(
                    symbols=prereg.symbols,
                    start_date=prereg.start_date,
                    end_date=prereg.end_date,
                    per_symbol_limit=prereg.per_symbol_target,
                    max_scan_rows=prereg.max_scan_rows,
                    batch_id=args.batch_id,
                    dry_run=not execute,
                )
            )
            print(f"Acquisition mode: {'EXECUTE' if execute else 'DRY_RUN'}")
            print(f"Scanned rows: {acquisition.scanned_rows}")
            print(f"Per-symbol counts: {acquisition.per_symbol_counts}")
            print(f"Quota satisfied: {acquisition.quota_satisfied}")
            print(f"Invalid rows: {acquisition.invalid_rows} {acquisition.invalid_reasons}")
            if acquisition.subset_path:
                print(f"Subset: {acquisition.subset_path}")

        subset_path = Path("data") / "research_sources" / "fnspid" / "subsets" / f"{args.batch_id}.csv"
        dataset_id = args.batch_id
        if execute and args.import_subset:
            if acquisition is not None and acquisition.subset_path:
                subset_path = Path(acquisition.subset_path)
            summary = ResearchSubsetImporter(session).import_fnspid_subset(subset_path, dataset_id=dataset_id, dry_run=False)
            session.commit()
            print(f"Imported articles: {summary.imported}")
            print(f"Import duplicates: {summary.duplicates}")
            print(f"Import invalid: {summary.invalid} {summary.invalid_reasons}")
            if acquisition is not None:
                export_path = DEFAULT_NORMALIZED_DIR / f"normalized_articles_{args.batch_id}.csv"
                export_normalized_articles(acquisition.records, export_path)
                print(f"Normalized export: {export_path}")

        if execute and args.acquire_prices:
            price_summary = YahooChartDailyPriceAcquirer().acquire(
                YahooChartDailyPriceConfig(
                    symbols=prereg.symbols,
                    start_date=prereg.start_date,
                    end_date=prereg.end_date,
                    batch_id=args.batch_id,
                    dry_run=False,
                ),
                db_session=session,
            )
            session.commit()
            print(f"Price rows: {price_summary.imported_rows}")
            print(f"Price failures: {price_summary.failures}")

        cohort_config = cohort_selection_config(prereg)
        cohort = ResearchCohortBuilder(session).build(cohort_config)
        print(f"Cohort fingerprint: {cohort.fingerprint}")
        print(f"Cohort samples: {len(cohort.samples)}")
        print(f"Cohort coverage: {cohort.coverage_summary}")
        print(f"Cohort exclusions: {cohort.exclusion_counts}")

        experiment_id = None
        if execute and args.analyze_finbert:
            experiment = ExperimentRepository(session).create(
                name="Phase 12 FinBERT locked cohort analysis",
                experiment_type="phase12_sentiment_analysis",
                configuration={"dataset_id": dataset_id, "cohort_fingerprint": cohort.fingerprint, "symbols": prereg.symbols},
                dataset_id=dataset_id,
                notes="Phase 12 locked-cohort FinBERT analysis. No heuristic fallback.",
            )
            experiment_id = experiment.id
            counters = run_finbert_for_cohort(session, cohort_config, experiment_id)
            ExperimentRepository(session).complete(experiment_id, notes=f"FinBERT counters: {counters}")
            session.commit()
            print(f"FinBERT counters: {counters}")

        if execute and args.evaluate:
            summary = HistoricalSignalEvaluator(session).run(
                HistoricalSignalEvaluationConfig(
                    experiment_name="Phase 12 locked multi-symbol FinBERT baseline",
                    engines=["v1", "v2"],
                    horizons=[prereg.horizon],
                    cohort=cohort_config,
                    sentiment_source="FINBERT_LOCKED_COHORT",
                    export=True,
                ),
                persist=True,
                export_dir=output_dir,
            )
            session.commit()
            target = output_dir / str(summary.experiment_id)
            rows_path = target / "signal_evaluation_rows.csv"
            diagnostic_path = target / "v2_diagnostic.csv"
            export_v2_diagnostic_from_rows(session, rows_path, diagnostic_path)
            systematic_disagreement_cases(rows_path, target / "v1_v2_disagreement_cases.csv")
            metrics = evaluate_rows_by_split(rows_path)
            (target / "phase12_metrics.json").write_text(__import__("json").dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
            print(f"Evaluation experiment ID: {summary.experiment_id}")
            print(f"Rows: {len(summary.rows)}")
            print(f"Metrics: {target / 'phase12_metrics.json'}")

        if args.report:
            latest = latest_experiment_dir(output_dir)
            if latest is None:
                print("No Phase 12 evaluation output found for report.")
            else:
                rows_path = latest / "signal_evaluation_rows.csv"
                metrics_path = latest / "phase12_metrics.json"
                diagnostic_path = latest / "v2_diagnostic.csv"
                metrics = __import__("json").loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else evaluate_rows_by_split(rows_path)
                diagnostic_summary = summarize_v2_diagnostic(diagnostic_path) if diagnostic_path.exists() else {}
                report_path = render_locked_baseline_report(
                    preregistration=prereg,
                    cohort_fingerprint=cohort.fingerprint,
                    rows_csv=rows_path,
                    metrics=metrics,
                    output_path=latest / "PHASE12_BASELINE_REPORT.md",
                    diagnostic_summary=diagnostic_summary,
                )
                registry_path = latest / "v2_parameter_registry.json"
                registry_path.write_text(__import__("json").dumps(v2_parameter_registry(), indent=2, sort_keys=True), encoding="utf-8")
                print(f"Report: {report_path}")
                print(f"Parameter registry: {registry_path}")


def run_finbert_for_cohort(session, cohort_config: ResearchCohortConfig, experiment_id: int | None) -> dict[str, int | float | str | None]:
    cohort = ResearchCohortBuilder(session).build(cohort_config)
    service = SentimentIntelligenceService(session=session, fallback_to_heuristic=False)
    counters = {"new": 0, "reused": 0, "failed": 0, "attempted": 0, "latency_ms": 0}
    started = perf_counter()
    for sample in cohort.samples:
        article = session.get(NewsArticle, sample.article_id)
        if article is None:
            counters["failed"] += 1
            continue
        existing = latest_finbert_run(session, article.id)
        if existing is not None and article.analysis_provider == "finbert":
            counters["reused"] += 1
            continue
        counters["attempted"] += 1
        record = service.analyze(_sentiment_input(article), analyzer_name="finbert", experiment_id=experiment_id, persist=True)
        if record.result.status.value == "SUCCESS":
            apply_sentiment_result_to_article(article, record.result)
            counters["new"] += 1
        else:
            counters["failed"] += 1
        counters["latency_ms"] += int(record.result.latency_ms or 0)
    counters["elapsed_seconds"] = round(perf_counter() - started, 3)
    counters["device"] = "cpu"
    return counters


def latest_finbert_run(session, article_id: int) -> SentimentAnalysisRun | None:
    return session.execute(
        select(SentimentAnalysisRun)
        .where(SentimentAnalysisRun.article_id == article_id, SentimentAnalysisRun.model_family == "finbert")
        .order_by(SentimentAnalysisRun.created_at.desc(), SentimentAnalysisRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _sentiment_input(row: NewsArticle) -> SentimentAnalysisInput:
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


def latest_experiment_dir(output_dir: Path) -> Path | None:
    if not output_dir.exists():
        return None
    candidates = [path for path in output_dir.iterdir() if path.is_dir() and (path / "signal_evaluation_rows.csv").exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: int(path.name) if path.name.isdigit() else -1)[-1]


def render_tuning_policy() -> str:
    return """# Signal Tuning Policy

Phase 12 is measurement-only. Signal V2 weights, thresholds, confidence coefficients, news decay, momentum normalization, and volume behavior are read-only.

Future tuning rules:

- Use DEVELOPMENT split only for parameter experiments.
- Do not tune on HOLDOUT.
- Version every parameter experiment.
- Do not repeatedly peek at HOLDOUT to select parameters.
- Evaluate HOLDOUT only after a candidate model is frozen.
- Keep the Phase 12 locked cohort intact; create a new cohort version for genuine data-quality corrections.
- If Gemini becomes configured, run it on the same locked cohort rather than an easier replacement cohort.
"""


if __name__ == "__main__":
    main()
