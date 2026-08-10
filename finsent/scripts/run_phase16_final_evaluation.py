from __future__ import annotations

import argparse
import json
from pathlib import Path

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.services.phase16_final_evaluation import (
    PHASE16_OUTPUT_DIR,
    file_sha256,
    run_phase16_final_evaluation,
)


def validate_results_manifest(path: Path = PHASE16_OUTPUT_DIR / "FINAL_RESULTS_MANIFEST.json") -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mismatches: dict[str, tuple[str, str]] = {}
    for name, expected in payload.get("artifact_hashes", {}).items():
        artifact_path = _artifact_path(name, payload)
        if artifact_path is None or not artifact_path.exists():
            mismatches[name] = (str(expected), "MISSING")
            continue
        actual = file_sha256(artifact_path)
        if actual != expected:
            mismatches[name] = (str(expected), actual)
    return {"valid": not mismatches, "mismatches": mismatches}


def _artifact_path(name: str, payload: dict[str, object]) -> Path | None:
    paths = payload.get("artifact_paths")
    if isinstance(paths, dict) and name in paths:
        return Path(str(paths[name]))
    mapping = {
        "row_export": PHASE16_OUTPUT_DIR / "final_holdout_predictions.csv",
        "summary_json": PHASE16_OUTPUT_DIR / "FINAL_EVALUATION_SUMMARY.json",
        "final_report": PHASE16_OUTPUT_DIR / "FINAL_EVALUATION_REPORT.md",
        "pre_execution_manifest": PHASE16_OUTPUT_DIR / "PRE_EXECUTION_MANIFEST.json",
        "execution_config": PHASE16_OUTPUT_DIR / "FINAL_EXECUTION_CONFIG.json",
        "holdout_status": PHASE16_OUTPUT_DIR / "final_holdout_v3_evaluated_lock.json",
    }
    if name in mapping:
        return mapping[name]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 16 one-shot final holdout evaluation.")
    parser.add_argument("--execute", action="store_true", help="Actually run the locked final evaluation.")
    parser.add_argument("--no-v2-1", action="store_true", help="Skip preregistered secondary V2.1 research candidate.")
    parser.add_argument("--verify-manifest", action="store_true", help="Validate final result artifact hashes.")
    args = parser.parse_args()

    if args.verify_manifest:
        print(json.dumps(validate_results_manifest(), indent=2, sort_keys=True))
        return
    if not args.execute:
        raise SystemExit("Refusing to run final holdout evaluation without --execute.")

    init_db()
    with SessionLocal() as session:
        result = run_phase16_final_evaluation(session, include_v2_1=not args.no_v2_1)
    summary = result["summary"]
    print(
        json.dumps(
            {
                "experiment_id": result["experiment_id"],
                "status": "COMPLETED_LOCKED",
                "final_evaluated_n": summary["final_evaluated_n"],
                "execution_config_hash": summary["execution_config_hash"],
                "protocol_hash": summary["protocol_hash"],
                "results_hash": result["result_manifest"]["results_hash"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
