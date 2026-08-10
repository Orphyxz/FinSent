from __future__ import annotations

import argparse
import json
from pathlib import Path
from dataclasses import asdict

from finsent.app.database.base import SCHEMA_VERSION, SessionLocal, init_db
from finsent.app.services.historical_news_acquisition import ResearchSubsetImporter
from finsent.app.services.phase12_research import StratifiedFNSPIDAcquirer, StratifiedFNSPIDAcquisitionConfig, YahooChartDailyPriceAcquirer, YahooChartDailyPriceConfig
from finsent.app.services.phase14_research import (
    FINAL_HOLDOUT_V2_DATASET_ID,
    PHASE14_OUTPUT_DIR,
    BinnedCalibrator,
    FinalHoldoutAdequacyPolicy,
    FinalHoldoutV2Preregistration,
    fit_selected_calibrator,
    calibrator_config,
    load_calibration_observations,
    raw_calibration_analysis,
    render_calibration_report,
    render_holdout_report,
    replacement_holdout_status,
    retire_holdout_if_inadequate,
    temporal_calibration_validation,
    write_phase14_docs,
    metrics_to_dict,
)
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig
from finsent.app.services.phase13_research import to_jsonable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 14 confidence calibration and final-holdout replacement preparation.")
    parser.add_argument("--prepare-final-holdout", action="store_true")
    parser.add_argument("--calibrate-confidence", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default=str(PHASE14_OUTPUT_DIR))
    parser.add_argument("--phase13-holdout-lock", default="output/research/phase13/phase13_development_tuning_v1/final_holdout_lock.json")
    parser.add_argument("--unlock-final-holdout", action="store_true", help="Dangerous future-use flag. Phase 14 refuses to use it.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.unlock_final_holdout:
        raise SystemExit("--unlock-final-holdout is reserved for Phase 15 and is unavailable in Phase 14.")
    if args.all:
        args.prepare_final_holdout = True
        args.calibrate_confidence = True
        args.report = True
    execute = bool(args.execute) and not args.dry_run
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    policy = FinalHoldoutAdequacyPolicy()
    prereg = FinalHoldoutV2Preregistration()
    final_status: dict = {"status": "not_attempted"}
    retired: dict = {"status": "not_checked"}

    with SessionLocal() as session:
        if args.prepare_final_holdout:
            lock_path = Path(args.phase13_holdout_lock)
            existing_lock = json.loads(lock_path.read_text(encoding="utf-8"))
            retired = retire_holdout_if_inadequate(existing_lock, policy, output_dir / "retired_final_holdout_v1.json")
            print(f"Existing holdout adequacy: adequate={retired['adequate']} status={retired['status']} reason={retired['retirement_reason']}")

            acquisition_manifest = None
            if not retired["adequate"]:
                acquisition = StratifiedFNSPIDAcquirer().acquire(
                    StratifiedFNSPIDAcquisitionConfig(
                        symbols=prereg.symbols,
                        start_date=prereg.start_date,
                        end_date=prereg.end_date,
                        per_symbol_limit=prereg.per_symbol_target,
                        max_scan_rows=prereg.max_scan_rows,
                        batch_id=FINAL_HOLDOUT_V2_DATASET_ID,
                        dry_run=not execute,
                        source_url=prereg.source_url,
                        source_file=prereg.source_file,
                        request_timeout_seconds=60,
                        selection_version="phase14_final_holdout_v2_stratified_v1",
                    )
                )
                acquisition_manifest = {
                    "requested_symbols": acquisition.requested_symbols,
                    "per_symbol_counts": acquisition.per_symbol_counts,
                    "written_rows": acquisition.written_rows,
                    "scanned_rows": acquisition.scanned_rows,
                    "quota_satisfied": acquisition.quota_satisfied,
                    "scan_limit_reached": acquisition.scan_limit_reached,
                    "subset_path": acquisition.subset_path,
                    "checksum_sha256": acquisition.checksum_sha256,
                }
                (output_dir / "replacement_acquisition_summary.json").write_text(json.dumps(to_jsonable(acquisition_manifest), indent=2, sort_keys=True), encoding="utf-8")
                print(f"Replacement acquisition: {acquisition_manifest}")
                if execute and acquisition.subset_path:
                    summary = ResearchSubsetImporter(session).import_fnspid_subset(Path(acquisition.subset_path), dataset_id=FINAL_HOLDOUT_V2_DATASET_ID, dry_run=False)
                    session.commit()
                    print(f"Replacement import: imported={summary.imported} duplicates={summary.duplicates} invalid={summary.invalid}")
                    active_symbols = [symbol for symbol, count in acquisition.per_symbol_counts.items() if count > 0]
                    if active_symbols:
                        prices = YahooChartDailyPriceAcquirer().acquire(
                            YahooChartDailyPriceConfig(
                                symbols=active_symbols,
                                start_date=prereg.start_date,
                                end_date=prereg.end_date,
                                batch_id=FINAL_HOLDOUT_V2_DATASET_ID,
                                dry_run=False,
                            ),
                            db_session=session,
                        )
                        session.commit()
                        print(f"Replacement prices: {prices.imported_rows}; failures={prices.failures}")

            cohort = ResearchCohortBuilder(session).build(
                ResearchCohortConfig(
                    symbols=prereg.symbols,
                    markets=["US"],
                    start_date=prereg.start_date,
                    end_date=prereg.end_date,
                    horizons=[prereg.horizon],
                    limit=prereg.per_symbol_target * len(prereg.symbols),
                    seed=42,
                    dataset_id=FINAL_HOLDOUT_V2_DATASET_ID,
                )
            )
            final_status = replacement_holdout_status(cohort, policy, output_dir / "replacement_final_holdout_status.json", source_manifest=acquisition_manifest)
            print(f"Replacement status: {final_status['status']} eligible={final_status['technically_eligible_n']} blockers={final_status['blockers']}")

        calibration_config = None
        if args.calibrate_confidence:
            observations = load_calibration_observations()
            raw = raw_calibration_analysis(observations)
            folds, results = temporal_calibration_validation(observations)
            selected = next(result for result in results if result.selected)
            calibrator = fit_selected_calibrator(selected.method, observations)
            calibration_config = calibrator_config(selected.method, calibrator, observations, results)
            (output_dir / "confidence_calibrator_config.json").write_text(json.dumps(to_jsonable(calibration_config), indent=2, sort_keys=True), encoding="utf-8")
            metrics_payload = {
                "raw": metrics_to_dict(raw),
                "folds": folds,
                "results": [asdict(result) for result in results],
            }
            (output_dir / "confidence_calibration_metrics.json").write_text(json.dumps(to_jsonable(metrics_payload), indent=2, sort_keys=True), encoding="utf-8")
            print(f"Calibration selected: {selected.method}; justified={selected.justified}")
            print(f"Raw Brier={raw.brier} ECE={raw.ece} MCE={raw.mce}")
            if args.report:
                render_calibration_report(output_dir / "CONFIDENCE_CALIBRATION_REPORT.md", observations=observations, raw=raw, folds=folds, results=results, config=calibration_config, final_status=final_status)

        if args.report:
            if (output_dir / "replacement_final_holdout_status.json").exists():
                final_status = json.loads((output_dir / "replacement_final_holdout_status.json").read_text(encoding="utf-8"))
            if (output_dir / "retired_final_holdout_v1.json").exists():
                retired = json.loads((output_dir / "retired_final_holdout_v1.json").read_text(encoding="utf-8"))
            if calibration_config is None and (output_dir / "confidence_calibrator_config.json").exists():
                calibration_config = json.loads((output_dir / "confidence_calibrator_config.json").read_text(encoding="utf-8"))
            render_holdout_report(output_dir / "FINAL_HOLDOUT_PREPARATION.md", retired=retired, preregistration=prereg, replacement=final_status)
            write_phase14_docs(policy, prereg, calibration_config or {"status": "not_run"})
            update_docs_and_changelog(output_dir, retired, final_status, calibration_config or {"status": "not_run"})
            print(f"Reports: {output_dir}")

    print(f"DB schema version: {SCHEMA_VERSION}")


def update_docs_and_changelog(output_dir: Path, retired: dict, replacement: dict, calibration_config: dict) -> None:
    updates = {
        Path("docs") / "CONFIDENCE_SEMANTICS.md": "\n\n## Phase 14 Calibration\n\nCalibrated reliability is an optional empirical correctness estimate fitted on Phase 12 DEVELOPMENT only. It is not probability of price increase or profit, and it does not change signal direction.\n",
        Path("docs") / "SIGNAL_TUNING_POLICY.md": "\n\n## Phase 14\n\nDirectional tuning remains closed. Confidence calibration may be fitted only on DEVELOPMENT data. FINAL_HOLDOUT_V2, if locked, is reserved for Phase 15 only.\n",
        Path("docs") / "RESEARCH_REPRODUCIBILITY.md": "\n\n## Phase 14\n\nPhase 14 stores confidence calibration artifacts and holdout adequacy/retirement metadata under `output/research/phase14/`. Final-holdout performance remains unevaluated.\n",
        Path("docs") / "LOCKED_COHORT_EVALUATION.md": "\n\n## Phase 14 Holdout Status\n\nThe Phase 13 AAPL-only holdout is structurally retired unevaluated if it fails adequacy. Replacement status is recorded separately and must not be evaluated before Phase 15.\n",
        Path("docs") / "FINAL_HOLDOUT_PREREGISTRATION.md": "\n\n## Phase 14 Retirement Note\n\nThe Phase 13 AAPL-only holdout is preserved but structurally inadequate for final testing under the Phase 14 adequacy policy. It remains unevaluated.\n",
    }
    for path, text in updates.items():
        existing = path.read_text(encoding="utf-8") if path.exists() else f"# {path.stem.replace('_', ' ').title()}\n"
        if text.strip() not in existing:
            path.write_text(existing.rstrip() + text, encoding="utf-8")
    changelog = Path("docs") / "LOCAL_CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Local Changelog\n"
    if "## Phase 14 - Confidence Calibration and Final Holdout Replacement" not in existing:
        lines = [
            "",
            "## Phase 14 - Confidence Calibration and Final Holdout Replacement",
            "",
            "- Added development-only Signal V2 confidence calibration analysis.",
            f"- Calibration status: `{calibration_config.get('status')}`.",
            f"- Retired holdout status: `{retired.get('status')}`; reason: `{retired.get('retirement_reason')}`.",
            f"- Replacement holdout status: `{replacement.get('status')}`; fingerprint: `{replacement.get('cohort_fingerprint')}`.",
            "- Final-holdout performance remains unevaluated.",
            f"- Artifacts: `{output_dir.as_posix()}`.",
        ]
        changelog.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    readme = Path("README.md")
    if readme.exists():
        existing = readme.read_text(encoding="utf-8")
        marker = "Phase 14 research artifacts"
        if marker not in existing:
            readme.write_text(existing.rstrip() + "\n\n### Phase 14 research artifacts\n\nPhase 14 adds development-only confidence calibration artifacts and final-holdout adequacy metadata under `output/research/phase14/`. Directional signal logic remains frozen.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
