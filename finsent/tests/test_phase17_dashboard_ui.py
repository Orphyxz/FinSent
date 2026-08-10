from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select

from finsent.app.dashboard import components
from finsent.app.dashboard.app import create_app
from finsent.app.dashboard.pages import alerts, compare, news_impact, research, stock_detail, summary
from finsent.app.dashboard.research_results import EXPECTED_FINGERPRINT, FinalResearchResultsService, file_sha256, pct
from finsent.app.dashboard.ui_components import compact_empty, quality_badge, research_metric, signal_badge, status_badge
from finsent.app.database.base import SessionLocal, engine
from finsent.app.database.entities import EventStudyResult, ExperimentRun, SentimentAnalysisRun, SignalRun


def test_research_result_service_loads_locked_artifact_copy(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    manifest_path = tmp_path / "manifest.json"
    summary_path.write_text(json.dumps(_minimal_summary()), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "holdout_status": "FINAL_HOLDOUT_V3_EVALUATED_LOCKED",
                "artifact_hashes": {"summary_json": file_sha256(summary_path)},
            }
        ),
        encoding="utf-8",
    )

    status = FinalResearchResultsService(summary_path, manifest_path).load()

    assert status.available
    assert status.locked
    assert status.warning is None
    assert status.summary["holdout_fingerprint"] == EXPECTED_FINGERPRINT


def test_research_result_service_reports_missing_or_tampered_artifacts(tmp_path: Path) -> None:
    missing = FinalResearchResultsService(tmp_path / "missing.json", tmp_path / "manifest.json").load()
    assert not missing.available
    assert "unavailable" in (missing.warning or "")

    summary_path = tmp_path / "summary.json"
    manifest_path = tmp_path / "manifest.json"
    summary_path.write_text(json.dumps({**_minimal_summary(), "holdout_fingerprint": "wrong"}), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "holdout_status": "FINAL_HOLDOUT_V3_EVALUATED_LOCKED",
                "artifact_hashes": {"summary_json": "not-the-real-hash"},
            }
        ),
        encoding="utf-8",
    )

    tampered = FinalResearchResultsService(summary_path, manifest_path).load()

    assert tampered.available
    assert not tampered.locked
    assert "fingerprint mismatch" in (tampered.warning or "").lower()
    assert "hash" in (tampered.warning or "").lower()


def test_reusable_ui_components_expose_consistent_badge_classes() -> None:
    assert status_badge("Holdout", "FINAL_HOLDOUT_V3_EVALUATED_LOCKED").className == (
        "status-badge status-final-holdout-v3-evaluated-locked"
    )
    assert signal_badge("bullish").className == "signal-badge signal-positive"
    assert signal_badge("bearish").children == "Signal: Bearish"
    assert quality_badge("ok").children == "Quality: OK"
    assert research_metric("Strict Accuracy", "32.4%", 111).className == "research-metric"
    assert compact_empty("No data", "Artifact missing").className == "empty-state-card compact-empty"
    assert pct(0.3243) == "32.4%"


def test_dashboard_nav_includes_research_and_root_maps_to_overview() -> None:
    labels = [label for label, _path in components.ANALYSIS_NAV_ITEMS]
    links = components.build_nav_links("/", analysis_ready=True)

    assert "Research" in labels
    assert links
    assert links[0].href == "/summary"
    assert "is-active" in links[0].className


@pytest.mark.parametrize("layout_factory", [summary.layout, stock_detail.layout, news_impact.layout, compare.layout, research.layout, alerts.layout])
def test_dashboard_pages_render_without_provider_or_research_execution(layout_factory) -> None:
    rendered = layout_factory()

    assert rendered is not None


def test_dashboard_http_routes_smoke() -> None:
    app = create_app()
    client = app.server.test_client()

    for path in ["/", "/summary", "/stock-detail", "/news-impact", "/compare", "/research", "/alerts"]:
        response = client.get(path)
        assert response.status_code == 200


def test_research_page_does_not_create_research_database_rows() -> None:
    table_names = set(inspect(engine).get_table_names())
    required = {
        ExperimentRun.__tablename__,
        SentimentAnalysisRun.__tablename__,
        SignalRun.__tablename__,
        EventStudyResult.__tablename__,
    }
    if not required.issubset(table_names):
        pytest.skip("research database tables are not initialized in this environment")

    entities = [ExperimentRun, SentimentAnalysisRun, SignalRun, EventStudyResult]
    with SessionLocal() as session:
        before = _counts(session, entities)
        research.layout()
        after = _counts(session, entities)

    assert after == before


def _counts(session, entities: list[type]) -> dict[str, int]:
    return {
        entity.__tablename__: session.execute(select(func.count()).select_from(entity)).scalar_one()
        for entity in entities
    }


def _minimal_summary() -> dict:
    metric = {
        "total": 111,
        "correct": 36,
        "strict_accuracy": 0.3243243243,
        "directional_eligible": 58,
        "directional_accuracy": 0.5,
        "balanced_accuracy": 0.5185185185,
        "macro_f1": 0.315,
        "confusion_matrix": {
            "BULLISH": {"BULLISH": 10, "NEUTRAL": 4, "BEARISH": 2},
            "NEUTRAL": {"BULLISH": 8, "NEUTRAL": 18, "BEARISH": 7},
            "BEARISH": {"BULLISH": 9, "NEUTRAL": 11, "BEARISH": 6},
        },
    }
    return {
        "holdout_fingerprint": EXPECTED_FINGERPRINT,
        "final_evaluated_n": 111,
        "metrics": {
            "v1": metric,
            "v2": {**metric, "correct": 25, "strict_accuracy": 0.2252252252},
            "v2_1": {**metric, "correct": 28, "strict_accuracy": 0.2522522523},
            "baselines": {
                "majority_class": {"strict_accuracy": 0.3513513514, "balanced_accuracy": 0.3333333333},
                "always_neutral": {"strict_accuracy": 0.3513513514},
                "news_direction": {"strict_accuracy": 0.2792792793},
            },
        },
        "class_distributions": {
            "realized": {"BULLISH": 34, "NEUTRAL": 39, "BEARISH": 38},
            "finbert": {"BULLISH": 22, "NEUTRAL": 54, "BEARISH": 35},
            "v1": {"BULLISH": 27, "NEUTRAL": 33, "BEARISH": 51},
            "v2": {"BULLISH": 24, "NEUTRAL": 59, "BEARISH": 28},
        },
        "paired_analysis": {"both_correct": 17, "v1_correct_v2_wrong": 19, "v1_wrong_v2_correct": 8, "both_wrong": 67},
        "symbol_results": {
            "v1": {
                "AMZN": {"metrics": {"strict_accuracy": 0.3333333333}},
                "NVDA": {"metrics": {"strict_accuracy": 0.3243243243}},
                "TSLA": {"metrics": {"strict_accuracy": 0.3142857143}},
            },
            "v2": {
                "AMZN": {"metrics": {"strict_accuracy": 0.2051282051}},
                "NVDA": {"metrics": {"strict_accuracy": 0.2432432432}},
                "TSLA": {"metrics": {"strict_accuracy": 0.2285714286}},
            },
        },
        "v2_component_analysis": {
            "news": {"correct_value": {"mean": 0.18}, "incorrect_value": {"mean": 0.05}},
            "price_momentum": {"correct_value": {"mean": 0.01}},
            "volume_confirmation": {"correct_value": {"mean": -0.02}},
        },
        "confidence_reliability": {
            "raw_confidence": {"mean": 0.55},
            "correct_mean_confidence": {"mean": 0.62},
            "incorrect_mean_confidence": {"mean": 0.52},
            "calibration_metrics_secondary": {"brier": 0.263, "ece": 0.324, "mce": 0.414},
        },
    }
