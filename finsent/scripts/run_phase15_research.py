from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from finsent.app.database.base import SCHEMA_VERSION, SessionLocal, init_db
from finsent.app.services.historical_news_acquisition import ResearchSubsetImporter
from finsent.app.services.phase12_research import YahooChartDailyPriceAcquirer, YahooChartDailyPriceConfig
from finsent.app.services.phase15_research import (
    FINAL_HOLDOUT_V3_DATASET_ID,
    PHASE15_OUTPUT_DIR,
    FinalHoldoutV3Preregistration,
    RemoteRangeFNSPIDReader,
    build_acquisition_summary,
    build_availability,
    lock_summary_from_cohort,
    render_report,
    select_records_for_window,
    select_window,
    source_layout_summary,
    write_lock_manifest,
    write_subset,
)
from finsent.app.services.phase13_research import to_jsonable
from finsent.app.services.research_dataset import ResearchCohortBuilder, ResearchCohortConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 15 robust final-holdout acquisition and lock preparation.")
    parser.add_argument("--audit-source", action="store_true")
    parser.add_argument("--availability", action="store_true")
    parser.add_argument("--prepare-holdout", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default=str(PHASE15_OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.all:
        args.audit_source = True
        args.availability = True
        args.prepare_holdout = True
        args.report = True
    execute = bool(args.execute) and not args.dry_run
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    prereg = FinalHoldoutV3Preregistration()
    init_db()

    layout = source_layout_summary()
    if args.audit_source:
        (output_dir / "fnspid_source_layout.json").write_text(json.dumps(to_jsonable(layout), indent=2, sort_keys=True), encoding="utf-8")
        write_source_layout_doc(layout)
        print("Source layout audited.")

    availability = None
    records_by_symbol = None
    acquisition = None
    lock = None
    manifest_path = None
    reader = RemoteRangeFNSPIDReader(source_url=prereg.source_url)
    if args.availability or args.prepare_holdout:
        availability, records_by_symbol = build_availability(reader, prereg)
        selection = select_window(records_by_symbol, prereg)
        (output_dir / "availability_by_symbol_month.json").write_text(json.dumps(to_jsonable(asdict(availability)), indent=2, sort_keys=True), encoding="utf-8")
        (output_dir / "selected_window.json").write_text(json.dumps(to_jsonable(asdict(selection)), indent=2, sort_keys=True), encoding="utf-8")
        print(f"Availability: {availability.source_records_by_symbol}")
        print(f"Selected window: {selection.start_date} to {selection.end_date}; adequate={selection.adequate}; counts={selection.candidate_counts}")

    with SessionLocal() as session:
        if args.prepare_holdout:
            assert records_by_symbol is not None
            selection = select_window(records_by_symbol, prereg)
            records = select_records_for_window(records_by_symbol, selection, prereg)
            subset_path = checksum = None
            if execute and selection.adequate:
                target = Path("data") / "research_sources" / "fnspid" / "subsets" / f"{FINAL_HOLDOUT_V3_DATASET_ID}.csv"
                subset, manifest, checksum = write_subset(records, target, prereg, source_bytes_requested=reader.bytes_requested)
                manifest_path = str(manifest)
                subset_path = subset
                summary = ResearchSubsetImporter(session).import_fnspid_subset(subset, dataset_id=FINAL_HOLDOUT_V3_DATASET_ID, dry_run=False)
                session.commit()
                print(f"Import: imported={summary.imported} duplicates={summary.duplicates} invalid={summary.invalid}")
                price_start = selection.start_date - __import__("datetime").timedelta(days=prereg.price_buffer_days_before)
                price_end = selection.end_date + __import__("datetime").timedelta(days=prereg.price_buffer_days_after)
                prices = YahooChartDailyPriceAcquirer().acquire(
                    YahooChartDailyPriceConfig(
                        symbols=prereg.acquisition_symbols,
                        start_date=price_start,
                        end_date=price_end,
                        batch_id=FINAL_HOLDOUT_V3_DATASET_ID,
                        dry_run=False,
                    ),
                    db_session=session,
                )
                session.commit()
                (output_dir / "price_acquisition_summary.json").write_text(json.dumps(to_jsonable(asdict(prices)), indent=2, sort_keys=True), encoding="utf-8")
                print(f"Prices: {prices.imported_rows}; failures={prices.failures}")
            acquisition = build_acquisition_summary(selection, records, records_by_symbol, prereg, subset_path=subset_path, checksum=checksum, source_bytes_requested=reader.bytes_requested)
            (output_dir / "article_acquisition_summary.json").write_text(json.dumps(to_jsonable(asdict(acquisition)), indent=2, sort_keys=True), encoding="utf-8")

            cohort = ResearchCohortBuilder(session).build(
                ResearchCohortConfig(
                    symbols=prereg.acquisition_symbols,
                    markets=["US"],
                    start_date=selection.start_date,
                    end_date=selection.end_date,
                    horizons=[prereg.event_horizon],
                    limit=prereg.per_symbol_quota * len(prereg.acquisition_symbols),
                    seed=42,
                    dataset_id=FINAL_HOLDOUT_V3_DATASET_ID,
                )
            )
            lock = lock_summary_from_cohort(cohort, prereg, manifest_path=manifest_path)
            (output_dir / "final_holdout_v3_lock.json").write_text(json.dumps(to_jsonable(asdict(lock)), indent=2, sort_keys=True), encoding="utf-8")
            write_lock_manifest(output_dir / "FINAL_HOLDOUT_V3_MANIFEST.json", lock, acquisition, availability, prereg)
            print(f"Lock status: {lock.status}; eligible={lock.technically_eligible_n}; per_symbol={lock.eligible_per_symbol}")

    if args.report:
        if availability is None:
            raw = json.loads((output_dir / "availability_by_symbol_month.json").read_text(encoding="utf-8"))
            from finsent.app.services.phase15_research import AvailabilitySummary

            availability = AvailabilitySummary(**raw)
        if acquisition is None:
            from finsent.app.services.phase15_research import AcquisitionSummaryV3, WindowSelection

            raw = json.loads((output_dir / "article_acquisition_summary.json").read_text(encoding="utf-8"))
            raw["selected_window"] = WindowSelection(**raw["selected_window"])
            acquisition = AcquisitionSummaryV3(**raw)
        if lock is None:
            from finsent.app.services.phase15_research import LockSummaryV3

            lock = LockSummaryV3(**json.loads((output_dir / "final_holdout_v3_lock.json").read_text(encoding="utf-8")))
        render_report(output_dir / "FINAL_HOLDOUT_ACQUISITION_REPORT.md", layout=layout, availability=availability, acquisition=acquisition, lock=lock, prereg=prereg)
        write_docs_and_changelog(output_dir, prereg, layout, acquisition, lock)
        print(f"Report: {output_dir / 'FINAL_HOLDOUT_ACQUISITION_REPORT.md'}")
    print(f"DB schema version: {SCHEMA_VERSION}")


def write_source_layout_doc(layout: dict) -> None:
    path = Path("docs") / "FNSPID_SOURCE_LAYOUT.md"
    lines = ["# FNSPID Source Layout", "", json.dumps(to_jsonable(layout), indent=2, sort_keys=True)]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_docs_and_changelog(output_dir: Path, prereg: FinalHoldoutV3Preregistration, layout: dict, acquisition, lock) -> None:
    docs = {
        Path("docs") / "FINAL_HOLDOUT_V3_PREREGISTRATION.md": ["# Final Holdout V3 Preregistration", "", json.dumps(prereg.to_dict(), indent=2, sort_keys=True)],
        Path("docs") / "FINAL_EVALUATION_PROTOCOL.md": [
            "# Final Evaluation Protocol",
            "",
            "Phase 16 may evaluate only frozen systems: Signal V1 and Signal V2.0 as primary systems, with V2.1-research only as an explicitly unpromoted research candidate.",
            "",
            "Metrics: strict accuracy, directional accuracy, balanced accuracy, macro F1, class precision/recall, confusion matrix, coverage, Wilson interval, and paired V1/V2 correctness. McNemar may be used if discordant N is sufficient.",
            "",
            "Baselines: majority-class, always-neutral, and news-direction baseline.",
            "",
            "Interpretation: V2 is not supported merely by a higher point estimate; balanced accuracy, macro F1, paired results, uncertainty, baselines, and sample size must all be considered.",
        ],
        Path("docs") / "PHASE15_HOLDOUT_ACQUISITION.md": ["# Phase 15 Holdout Acquisition", "", json.dumps(to_jsonable({"layout": layout, "acquisition": asdict(acquisition), "lock": asdict(lock)}), indent=2, sort_keys=True)],
    }
    for path, lines in docs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    append_once(Path("docs") / "FINAL_HOLDOUT_ADEQUACY_POLICY.md", "\n\n## Phase 15 V3\n\nV3 keeps the Phase 14 adequacy floor but uses robust per-symbol byte-range acquisition. It may lock four supported symbols when GOOGL is unavailable as a source symbol and GOOG is unsupported locally.\n")
    append_once(Path("docs") / "FINAL_HOLDOUT_V2_PREREGISTRATION.md", "\n\n## Phase 15 Supersession\n\nV2 remains not ready. V3 uses a source-layout-aware acquisition strategy and does not evaluate performance.\n")
    append_once(Path("docs") / "RESEARCH_DATA_INGESTION.md", "\n\n## Phase 15 Remote Range Acquisition\n\nThe FNSPID Nasdaq CSV is accessed via bounded HTTP byte ranges around ticker regions. The full 23GB source is not downloaded.\n")
    append_once(Path("docs") / "EXTERNAL_DATA_PROVENANCE.md", f"\n\n## Phase 15 Final Holdout V3\n\nDataset id: `{FINAL_HOLDOUT_V3_DATASET_ID}`. Source: FNSPID Nasdaq CSV via bounded byte ranges. Full source downloaded: false. Fingerprint: `{lock.fingerprint}`.\n")
    append_once(Path("docs") / "RESEARCH_REPRODUCIBILITY.md", "\n\n## Phase 15\n\nPhase 15 preregisters the final evaluation protocol before final performance exists and locks only technical holdout metadata.\n")
    append_once(Path("README.md"), "\n\n### Phase 15 research artifacts\n\nPhase 15 adds robust source-layout-aware final holdout acquisition artifacts under `output/research/phase15/`. Final performance evaluation is reserved for Phase 16.\n")
    changelog = Path("docs") / "LOCAL_CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Local Changelog\n"
    marker = "## Phase 15 - Robust Final Holdout Acquisition"
    if marker not in existing:
        lines = [
            "",
            marker,
            "",
            "- Documented FNSPID Nasdaq CSV alphabetic ticker grouping and AAPL-prefix sampling failure.",
            "- Added remote byte-range, per-symbol final holdout acquisition.",
            f"- Lock status: `{lock.status}`; fingerprint: `{lock.fingerprint}`.",
            "- Added final evaluation protocol for Phase 16 before final results exist.",
            "- Final performance was not evaluated.",
        ]
        changelog.write_text(existing.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def append_once(path: Path, text: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if text.strip() not in existing:
        path.write_text(existing.rstrip() + text, encoding="utf-8")


if __name__ == "__main__":
    main()
