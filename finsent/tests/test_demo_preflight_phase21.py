from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from finsent.app.config.settings import settings
from finsent.scripts import demo_preflight


def _set_database_url(monkeypatch: pytest.MonkeyPatch, db_path) -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")


def test_preflight_database_healthy_local_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "finsent.db"
    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO schema_metadata (key, value) VALUES ('schema_version', '2')")

    _set_database_url(monkeypatch, db_path)

    result = demo_preflight.check_database()

    assert result.status == "OK"
    assert "schema v2" in result.detail


def test_preflight_database_missing_is_offline_warning(tmp_path, monkeypatch) -> None:
    _set_database_url(monkeypatch, tmp_path / "missing.db")

    result = demo_preflight.check_database()

    assert result.status == "WARN"
    assert "missing" in result.detail


def test_preflight_phase16_present_and_locked(tmp_path) -> None:
    summary = {
        "holdout_fingerprint": demo_preflight.EXPECTED_FINGERPRINT,
        "protocol_hash": demo_preflight.EXPECTED_PROTOCOL_HASH,
        "execution_config_hash": demo_preflight.EXPECTED_CONFIG_HASH,
    }
    summary_path = tmp_path / "FINAL_EVALUATION_SUMMARY.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    manifest = {
        "holdout_status": "FINAL_HOLDOUT_V3_EVALUATED_LOCKED",
        "artifact_hashes": {"summary_json": sha256(summary_path.read_bytes()).hexdigest()},
    }
    manifest_path = tmp_path / "FINAL_RESULTS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = demo_preflight.check_research_artifacts(summary_path, manifest_path)

    assert result.status == "OK"
    assert "Phase 16 locked" in result.detail


def test_preflight_alpaca_unconfigured_reports_offline_ready(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alpaca_api_key", "")
    monkeypatch.setattr(settings, "alpaca_api_secret", "")

    result = demo_preflight.check_alpaca()

    assert result.status == "WARN"
    assert "offline" in result.detail


def test_preflight_alpaca_configured_uses_safe_probe(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alpaca_api_key", "key")
    monkeypatch.setattr(settings, "alpaca_api_secret", "secret")

    class FakeAlpacaProvider:
        def __init__(self, timeout: int) -> None:
            assert timeout == 10

        def fetch_quote_snapshot(self, _symbol):
            return SimpleNamespace(
                current_price=100.0,
                market_timestamp=datetime(2026, 8, 19, 14, 30, 0),
                quality_status="live",
                provider_status=None,
                feed="iex",
                note="ok",
            )

    monkeypatch.setattr(demo_preflight, "AlpacaMarketDataProvider", FakeAlpacaProvider)

    result = demo_preflight.check_alpaca()

    assert result.status == "OK"
    assert "feed iex" in result.detail


def test_preflight_finbert_dependencies_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(demo_preflight.importlib.util, "find_spec", lambda name: None if name in {"torch", "transformers"} else object())

    result = demo_preflight.check_finbert()

    assert result.status == "WARN"
    assert "torch" in result.detail
    assert "transformers" in result.detail


def test_preflight_output_never_prints_secrets(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alpaca_api_key", "visible-key")
    monkeypatch.setattr(settings, "alpaca_api_secret", "visible-secret")

    class FailingAlpacaProvider:
        def __init__(self, timeout: int) -> None:
            pass

        def fetch_quote_snapshot(self, _symbol):
            raise RuntimeError("visible-key visible-secret failed")

    monkeypatch.setattr(demo_preflight, "AlpacaMarketDataProvider", FailingAlpacaProvider)

    rendered = demo_preflight.render_report(
        demo_preflight.PreflightReport((demo_preflight.check_alpaca(),), None)
    )

    assert "visible-key" not in rendered
    assert "visible-secret" not in rendered
    assert "[redacted]" in rendered


def test_preflight_offline_ready_exits_zero_when_core_checks_pass() -> None:
    report = demo_preflight.PreflightReport(
        (
            demo_preflight.CheckResult("Runtime Imports", "OK", "ok", core=True),
            demo_preflight.CheckResult("Database", "OK", "ok", core=True),
            demo_preflight.CheckResult("Research", "OK", "Phase 16 locked"),
            demo_preflight.CheckResult("Alpaca", "WARN", "not configured"),
        ),
        None,
    )

    assert report.exit_code == 0
    assert report.final_label == "DEMO READY - OFFLINE MODE ONLY"
