from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from finsent.app.utils.files import file_sha256


SUMMARY_PATH = Path("output/research/phase16/FINAL_EVALUATION_SUMMARY.json")
MANIFEST_PATH = Path("output/research/phase16/FINAL_RESULTS_MANIFEST.json")
EXPECTED_FINGERPRINT = "8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e"


@dataclass(frozen=True, slots=True)
class ResearchArtifactStatus:
    available: bool
    locked: bool
    warning: str | None
    summary: dict[str, Any]
    manifest: dict[str, Any]


class FinalResearchResultsService:
    def __init__(self, summary_path: Path = SUMMARY_PATH, manifest_path: Path = MANIFEST_PATH) -> None:
        self.summary_path = summary_path
        self.manifest_path = manifest_path

    def load(self) -> ResearchArtifactStatus:
        if not self.summary_path.exists() or not self.manifest_path.exists():
            return ResearchArtifactStatus(False, False, "Final evaluation artifact unavailable.", {}, {})
        try:
            summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ResearchArtifactStatus(False, False, "Final evaluation artifact could not be parsed.", {}, {})

        warnings: list[str] = []
        if summary.get("holdout_fingerprint") != EXPECTED_FINGERPRINT:
            warnings.append("Holdout fingerprint mismatch.")
        expected_hash = manifest.get("artifact_hashes", {}).get("summary_json")
        actual_hash = file_sha256(self.summary_path)
        if expected_hash and expected_hash != actual_hash:
            warnings.append("Final summary hash does not match the result manifest.")
        if manifest.get("holdout_status") != "FINAL_HOLDOUT_V3_EVALUATED_LOCKED":
            warnings.append("Final holdout is not marked evaluated-locked.")

        return ResearchArtifactStatus(
            available=True,
            locked=not warnings,
            warning=" ".join(warnings) if warnings else None,
            summary=summary,
            manifest=manifest,
        )


def pct(value: float | None, *, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{digits}f}%"
