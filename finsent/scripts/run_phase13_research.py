from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from finsent.app.database.base import SCHEMA_VERSION, SessionLocal, init_db
from finsent.app.services.historical_news_acquisition import FNSPIDPartialAcquirer, FNSPIDAcquisitionConfig, ResearchSubsetImporter
from finsent.app.services.phase12_research import YahooChartDailyPriceAcquirer, YahooChartDailyPriceConfig
from finsent.app.services.phase13_research import (
    DEFAULT_PHASE12_ROWS,
    DEFAULT_PHASE13_DIR,
    FINAL_HOLDOUT_DATASET_ID,
    FinalHoldoutPreregistration,
    SignalV2ParameterSearch,
    baseline_fold_results,
    build_temporal_folds,
    development_error_analysis,
    export_search_results,
    freeze_phase12_artifact_reference,
    freeze_phase12_database_reference,
    generate_candidate_grid,
    load_development_rows,
    load_v1_development_rows,
    lock_final_holdout,
    render_phase13_report,
    selected_candidate_config,
    stable_fingerprint,
    to_jsonable,
    write_final_holdout_preregistration,
    write_phase13_docs,
)
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 13 development-only Signal V2.1 tuning and final-holdout lock.")
    parser.add_argument("--write-final-holdout-preregistration", action="store_true")
    parser.add_argument("--freeze-phase12", action="store_true")
    parser.add_argument("--acquire-final-holdout", action="store_true")
    parser.add_argument("--import-final-holdout", action="store_true")
    parser.add_argument("--acquire-final-prices", action="store_true")
    parser.add_argument("--lock-final-holdout", action="store_true")
    parser.add_argument("--analyze-development", action="store_true")
    parser.add_argument("--search", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--phase12-rows", default=str(DEFAULT_PHASE12_ROWS))
    parser.add_argument("--output-dir", default=str(DEFAULT_PHASE13_DIR))
    parser.add_argument("--final-batch-id", default=FINAL_HOLDOUT_DATASET_ID)
    parser.add_argument("--unlock-final-holdout", action="store_true", help="Dangerous future-use flag. Phase 13 does not use it.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    execute = bool(args.execute) and not args.dry_run
    if args.unlock_final_holdout:
        raise SystemExit("--unlock-final-holdout is intentionally unused in Phase 13.")
    if args.all:
        args.write_final_holdout_preregistration = True
        args.freeze_phase12 = True
        args.acquire_final_holdout = True
        args.import_final_holdout = True
        args.acquire_final_prices = True
        args.lock_final_holdout = True
        args.analyze_development = True
        args.search = True
        args.report = True

    init_db()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_csv = Path(args.phase12_rows)
    prereg = FinalHoldoutPreregistration()

    if args.write_final_holdout_preregistration:
        path = write_final_holdout_preregistration(Path("docs") / "FINAL_HOLDOUT_PREREGISTRATION.md", prereg)
        print(f"Final holdout preregistration: {path}")

    with SessionLocal() as session:
        artifact_ref = None
        if args.freeze_phase12:
            artifact_ref = freeze_phase12_artifact_reference(rows_csv, output_dir / "phase12_artifact_reference.json")
            freeze_phase12_database_reference(session, artifact_ref["development_article_ids"] + artifact_ref["observed_validation_article_ids"], output_dir / "phase12_database_reference.json")
            print(f"Phase 12 artifact reference: {output_dir / 'phase12_artifact_reference.json'}")

        acquisition_manifest = None
        subset_path = Path("data") / "research_sources" / "fnspid" / "subsets" / f"{args.final_batch_id}.csv"
        if args.acquire_final_holdout:
            acquisition = FNSPIDPartialAcquirer().acquire(
                FNSPIDAcquisitionConfig(
                    symbols=prereg.locked_symbols,
                    start_date=prereg.start_date,
                    end_date=prereg.end_date,
                    limit=prereg.per_symbol_target * len(prereg.locked_symbols),
                    max_scan_rows=prereg.max_scan_rows,
                    batch_id=args.final_batch_id,
                    dry_run=not execute,
                    source_url=prereg.source_url,
                    request_timeout_seconds=60,
                )
            )
            acquisition_manifest = {
                "requested_symbols": acquisition.requested_symbols,
                "matched_rows": acquisition.matched_rows,
                "scanned_rows": acquisition.scanned_rows,
                "scan_limit_reached": acquisition.scan_limit_reached,
                "subset_path": acquisition.subset_path,
                "checksum_sha256": acquisition.checksum_sha256,
            }
            (output_dir / "final_holdout_acquisition_summary.json").write_text(json.dumps(to_jsonable(acquisition_manifest), indent=2, sort_keys=True), encoding="utf-8")
            if acquisition.subset_path:
                subset_path = Path(acquisition.subset_path)
            print(f"Final holdout acquisition: {acquisition_manifest}")

        if execute and args.import_final_holdout:
            summary = ResearchSubsetImporter(session).import_fnspid_subset(subset_path, dataset_id=args.final_batch_id, dry_run=False)
            session.commit()
            print(f"Final holdout import: imported={summary.imported} duplicates={summary.duplicates} invalid={summary.invalid}")

        if execute and args.acquire_final_prices:
            prices = YahooChartDailyPriceAcquirer().acquire(
                YahooChartDailyPriceConfig(
                    symbols=prereg.locked_symbols,
                    start_date=prereg.start_date,
                    end_date=prereg.end_date,
                    batch_id=args.final_batch_id,
                    dry_run=False,
                ),
                db_session=session,
            )
            session.commit()
            print(f"Final holdout price rows: {prices.imported_rows}; failures={prices.failures}")

        final_lock = None
        if args.lock_final_holdout:
            cohort = ResearchCohortBuilder(session).build(final_holdout_cohort_config(prereg))
            final_lock = lock_final_holdout(
                cohort,
                preregistration=prereg,
                output_path=output_dir / "final_holdout_lock.json",
                source_manifest=acquisition_manifest,
            )
            print(f"Final holdout lock: {output_dir / 'final_holdout_lock.json'}")
            print(f"Final holdout fingerprint: {cohort.fingerprint}")
            print(f"Final holdout technical coverage: {cohort.coverage_summary}")

        dev_rows = None
        error_summary = None
        if args.analyze_development or args.search or args.report:
            dev_rows = load_development_rows(rows_csv)
            error_frame, error_summary = development_error_analysis(dev_rows)
            error_frame.to_csv(output_dir / "development_error_analysis.csv", index=False)
            (output_dir / "development_error_analysis.json").write_text(json.dumps(to_jsonable(error_summary), indent=2, sort_keys=True), encoding="utf-8")
            print(f"Development rows: {len(dev_rows)}")

        search_results = None
        folds = None
        baselines = None
        selected_config = None
        if args.search or args.report:
            assert dev_rows is not None
            folds = build_temporal_folds(dev_rows)
            candidates = generate_candidate_grid()
            print(f"Candidate count: {len(candidates)}")
            search_results = SignalV2ParameterSearch(dev_rows, candidates=candidates, folds=folds).run()
            export_search_results(search_results, output_dir / "v2_parameter_search.csv")
            v1_rows = load_v1_development_rows(rows_csv)
            baselines = baseline_fold_results(dev_rows, v1_rows, folds)
            selected = next(result for result in search_results if result.selected)
            selected_config = selected_candidate_config(
                selected,
                tuning_fingerprint=stable_fingerprint(dev_rows[["article_id", "evaluation_timestamp", "1D_realized_direction"]].to_dict("records")),
            )
            (output_dir / "v2_1_research_candidate.json").write_text(json.dumps(to_jsonable(selected_config), indent=2, sort_keys=True), encoding="utf-8")
            (output_dir / "temporal_folds.json").write_text(json.dumps([to_jsonable(asdict(fold)) for fold in folds], indent=2, sort_keys=True), encoding="utf-8")
            (output_dir / "baseline_fold_results.json").write_text(json.dumps(to_jsonable(baselines), indent=2, sort_keys=True), encoding="utf-8")
            print(f"Selected candidate: {selected.candidate.candidate_id}; justified={selected.justified}")

        if args.report:
            assert dev_rows is not None and folds is not None and search_results is not None and baselines is not None and error_summary is not None and selected_config is not None
            candidates = generate_candidate_grid()
            if final_lock is None and (output_dir / "final_holdout_lock.json").exists():
                final_lock = json.loads((output_dir / "final_holdout_lock.json").read_text(encoding="utf-8"))
            render_phase13_report(
                rows=dev_rows,
                folds=folds,
                candidates=candidates,
                search_results=search_results,
                baselines=baselines,
                error_summary=error_summary,
                final_holdout_lock=final_lock,
                output_path=output_dir / "PHASE13_TUNING_REPORT.md",
            )
            write_phase13_docs(output_dir=output_dir, final_lock=final_lock, selected_config=selected_config, error_summary=error_summary)
            update_changelog(output_dir, final_lock, selected_config)
            update_readme()
            print(f"Report: {output_dir / 'PHASE13_TUNING_REPORT.md'}")

    print(f"DB schema version: {SCHEMA_VERSION}")


def final_holdout_cohort_config(prereg: FinalHoldoutPreregistration) -> ResearchCohortConfig:
    return ResearchCohortConfig(
        symbols=prereg.locked_symbols,
        markets=prereg.markets,
        start_date=prereg.start_date,
        end_date=prereg.end_date,
        horizons=[prereg.horizon],
        limit=prereg.per_symbol_target * len(prereg.locked_symbols),
        seed=42,
        dataset_id=prereg.dataset_id,
    )


def update_changelog(output_dir: Path, final_lock: dict | None, selected_config: dict) -> None:
    path = Path("docs") / "LOCAL_CHANGELOG.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Local Changelog\n"
    if "## Phase 13 - Development-Only Signal V2.1 Tuning" in existing:
        return
    lines = [
        "",
        "## Phase 13 - Development-Only Signal V2.1 Tuning",
        "",
        "- Added a preregistered, locked future-period final holdout and an explicit evaluation guard.",
        f"- Final holdout fingerprint: `{(final_lock or {}).get('cohort_fingerprint', 'not locked')}`.",
        "- Added development-only V2 error analysis, temporal CV, baseline comparisons, and a modest V2.1 parameter grid.",
        f"- Frozen research candidate: `{selected_config.get('engine_version')}` with status `{selected_config.get('status')}`.",
        f"- Artifacts: `{output_dir.as_posix()}`.",
        "- Signal V1, Signal V2.0 defaults, Event Study V2, FinBERT configuration, confidence calibration, and dashboard defaults remain unchanged.",
        "- No commit hashes recorded.",
    ]
    path.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def update_readme() -> None:
    path = Path("README.md")
    if not path.exists():
        return
    existing = path.read_text(encoding="utf-8")
    marker = "Phase 13 research artifacts"
    if marker in existing:
        return
    addition = (
        "\n\n### Phase 13 research artifacts\n\n"
        "Phase 13 freezes a development-only Signal V2.1 research candidate under "
        "`output/research/phase13/phase13_development_tuning_v1/` and locks a new "
        "future-period final holdout as unevaluated. The dashboard default remains unchanged.\n"
    )
    path.write_text(existing.rstrip() + addition, encoding="utf-8")


if __name__ == "__main__":
    main()
