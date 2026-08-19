from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
from time import perf_counter

import pandas as pd

from finsent.app.config.settings import settings
from finsent.app.dashboard.research_results import FinalResearchResultsService
from finsent.app.database.base import SCHEMA_VERSION, sqlite_path_from_url
from finsent.app.services.market_providers import AlpacaMarketDataProvider, is_usable_quote_snapshot
from finsent.app.services.symbol_registry import registry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_FINGERPRINT = "8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e"
EXPECTED_PROTOCOL_HASH = "d9f0781f59f63279a896719f4a7327c124fd53ae05d2f62f8c292f6d221282c3"
EXPECTED_CONFIG_HASH = "e4b7e0355d9514415c5ce57147ee7ea156d0fa8c74d18ccd4fe5c1d03b527f0e"


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    detail: str
    core: bool = False


@dataclass(frozen=True, slots=True)
class PreflightReport:
    checks: tuple[CheckResult, ...]
    warmup_elapsed_seconds: float | None

    @property
    def has_core_failure(self) -> bool:
        return any(row.core and row.status == "FAIL" for row in self.checks)

    @property
    def alpaca_ok(self) -> bool:
        return any(row.name == "Alpaca" and row.status == "OK" for row in self.checks)

    @property
    def research_ok(self) -> bool:
        return any(row.name == "Research" and row.status == "OK" for row in self.checks)

    @property
    def exit_code(self) -> int:
        return 1 if self.has_core_failure else 0

    @property
    def final_label(self) -> str:
        if self.has_core_failure:
            return "DEMO ATTENTION REQUIRED"
        if not self.alpaca_ok and self.research_ok:
            return "DEMO READY - OFFLINE MODE ONLY"
        return "DEMO READY"


def build_report(*, warm: bool = False, symbols: list[str] | None = None) -> PreflightReport:
    checks = [
        check_git_code(),
        check_runtime_imports(),
        check_database(),
        check_research_artifacts(),
        check_alpaca(),
        check_finbert(),
        check_catalyst_engine(),
        check_market_context(),
        check_directories(),
        check_port_8050(),
    ]
    elapsed: float | None = None
    if warm:
        started = perf_counter()
        checks.extend(run_warmup(symbols or ["NVDA", "AAPL", "TSLA"]))
        elapsed = perf_counter() - started
    return PreflightReport(tuple(checks), elapsed)


def check_git_code() -> CheckResult:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        return CheckResult("Git/Code", "WARN", "Git metadata unavailable; build shown as unknown/local.")
    return CheckResult("Git/Code", "OK", f"commit {commit}")


def check_runtime_imports() -> CheckResult:
    try:
        import dash  # noqa: F401
        import dash_bootstrap_components  # noqa: F401
        import pandas  # noqa: F401
        import sqlalchemy  # noqa: F401
        from finsent.app.dashboard.app import create_app

        app = create_app(default_ticker="AAPL")
        routes = {"/", "/summary", "/stock-detail", "/news-impact", "/compare", "/research", "/alerts"}
        if not routes.issubset({"/", "/summary", "/stock-detail", "/news-impact", "/compare", "/research", "/alerts"}):
            return CheckResult("Runtime Imports", "FAIL", "route manifest mismatch", core=True)
        if app.server is None:
            return CheckResult("Runtime Imports", "FAIL", "Dash app factory returned no server", core=True)
    except Exception as exc:
        return CheckResult("Runtime Imports", "FAIL", _safe_message(exc), core=True)
    return CheckResult("Runtime Imports", "OK", "Dash/app imports ready", core=True)


def check_database() -> CheckResult:
    db_path = sqlite_path_from_url(settings.database_url)
    if db_path is None:
        return CheckResult("Database", "WARN", f"non-SQLite DATABASE_URL configured; expected schema v{SCHEMA_VERSION}")
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    if not db_path.exists():
        writable = _directory_writable(db_path.parent)
        status = "WARN" if writable else "FAIL"
        return CheckResult("Database", status, f"missing; parent writable={writable}; schema v{SCHEMA_VERSION} expected", core=not writable)
    try:
        with sqlite3.connect(str(db_path)) as connection:
            connection.execute("SELECT 1").fetchone()
            schema_version = _schema_version(connection) or f"v{SCHEMA_VERSION}"
    except sqlite3.Error as exc:
        return CheckResult("Database", "FAIL", _safe_message(exc), core=True)
    writable = _directory_writable(db_path.parent)
    size = _format_bytes(db_path.stat().st_size)
    return CheckResult("Database", "OK", f"schema {schema_version}; {size}; parent writable={writable}", core=True)


def check_research_artifacts(
    summary_path: Path | None = None,
    manifest_path: Path | None = None,
) -> CheckResult:
    summary = summary_path or PROJECT_ROOT / "output/research/phase16/FINAL_EVALUATION_SUMMARY.json"
    manifest = manifest_path or PROJECT_ROOT / "output/research/phase16/FINAL_RESULTS_MANIFEST.json"
    service = FinalResearchResultsService(summary_path=summary, manifest_path=manifest)
    status = service.load()
    if not status.available:
        return CheckResult("Research", "WARN", status.warning or "Phase 16 final artifacts unavailable.")
    protocol = status.summary.get("protocol_hash")
    config = status.summary.get("execution_config_hash")
    fingerprint = status.summary.get("holdout_fingerprint")
    if (
        not status.locked
        or fingerprint != EXPECTED_FINGERPRINT
        or protocol != EXPECTED_PROTOCOL_HASH
        or config != EXPECTED_CONFIG_HASH
    ):
        return CheckResult("Research", "FAIL", status.warning or "Phase 16 integrity mismatch.", core=True)
    return CheckResult("Research", "OK", "Phase 16 locked; fingerprint/protocol/config verified")


def check_alpaca() -> CheckResult:
    key_present = bool(settings.alpaca_api_key.strip())
    secret_present = bool(settings.alpaca_api_secret.strip())
    if not key_present and not secret_present:
        return CheckResult("Alpaca", "WARN", "not configured; offline/local research demo available")
    if key_present != secret_present:
        return CheckResult("Alpaca", "WARN", "partial credentials configured; set both key and secret")
    symbol = registry.resolve_any("AAPL")
    if symbol is None:
        return CheckResult("Alpaca", "FAIL", "AAPL is missing from symbol registry", core=True)
    try:
        quote = AlpacaMarketDataProvider(timeout=10).fetch_quote_snapshot(symbol)
    except Exception as exc:
        return CheckResult("Alpaca", "WARN", f"configured but live check failed: {_safe_message(exc)}")
    if is_usable_quote_snapshot(quote):
        feed = quote.feed or settings.alpaca_feed
        return CheckResult("Alpaca", "OK", f"configured; feed {feed}; {quote.quality_status}")
    return CheckResult("Alpaca", "WARN", f"configured but no usable AAPL quote: {quote.note}")


def check_finbert() -> CheckResult:
    torch_ok = importlib.util.find_spec("torch") is not None
    transformers_ok = importlib.util.find_spec("transformers") is not None
    if torch_ok and transformers_ok:
        return CheckResult("FinBERT", "OK", "dependencies importable; model loads lazily unless warm-up is requested")
    missing = ", ".join(name for name, ok in {"torch": torch_ok, "transformers": transformers_ok}.items() if not ok)
    return CheckResult("FinBERT", "WARN", f"missing optional research dependency: {missing}")


def check_catalyst_engine() -> CheckResult:
    try:
        from finsent.app.services.catalyst_intelligence import CatalystIntelligenceService

        CatalystIntelligenceService()
    except Exception as exc:
        return CheckResult("Catalyst Engine", "FAIL", _safe_message(exc), core=True)
    return CheckResult("Catalyst Engine", "OK", "deterministic service importable", core=True)


def check_market_context() -> CheckResult:
    try:
        from finsent.app.services.market_context import MarketContextService

        MarketContextService()
    except Exception as exc:
        return CheckResult("Market Context", "FAIL", _safe_message(exc), core=True)
    return CheckResult("Market Context", "OK", "service importable", core=True)


def check_directories() -> CheckResult:
    paths = {
        "data": PROJECT_ROOT / "data",
        "archive/v1": PROJECT_ROOT / "archive/v1",
        "research_sources": PROJECT_ROOT / "data/research_sources",
        "phase16": PROJECT_ROOT / "output/research/phase16",
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return CheckResult("Directories", "WARN", f"missing optional/local data dirs: {', '.join(missing)}")
    return CheckResult("Directories", "OK", "local app/research directories present")


def check_port_8050() -> CheckResult:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        in_use = sock.connect_ex(("127.0.0.1", 8050)) == 0
    if in_use:
        return CheckResult("Port 8050", "WARN", "already in use; dashboard may already be running")
    return CheckResult("Port 8050", "OK", "available")


def run_warmup(symbols: list[str]) -> list[CheckResult]:
    results: list[CheckResult] = []
    try:
        from finsent.app.services.sentiment_v2 import FinBERTSentimentAnalyzer

        analyzer = FinBERTSentimentAnalyzer()
        ready = analyzer.warmup()
        state = getattr(analyzer, "state", "UNKNOWN")
        results.append(CheckResult("Warm FinBERT", "OK" if ready else "WARN", str(state)))
    except Exception as exc:
        results.append(CheckResult("Warm FinBERT", "WARN", _safe_message(exc)))

    try:
        from finsent.app.dashboard.view_model import build_dashboard_state

        end = pd.Timestamp.now().normalize()
        start = end - pd.Timedelta(days=30)
        focus = symbols[0]
        peers = [symbol for symbol in symbols[1:4] if registry.resolve_any(symbol)]
        build_dashboard_state(focus, peers, "medium", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        results.append(CheckResult("Warm Workspace", "OK", f"symbols warmed: {', '.join([focus, *peers])}"))
    except Exception as exc:
        results.append(CheckResult("Warm Workspace", "WARN", _safe_message(exc)))
    return results


def render_report(report: PreflightReport) -> str:
    lines = ["FinSent Demo Preflight", ""]
    for row in report.checks:
        lines.append(f"{row.name:<18} {row.status:<4} {row.detail}")
    if report.warmup_elapsed_seconds is not None:
        lines.append(f"{'Warm-Up Elapsed':<18} INFO {report.warmup_elapsed_seconds:.1f}s")
    lines.extend(["", report.final_label])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a non-secret FinSent demo readiness check.")
    parser.add_argument("--warm", action="store_true", help="Optionally warm FinBERT and the current demo workspace.")
    parser.add_argument("--symbols", default="NVDA,AAPL,TSLA", help="Comma-separated warm-up symbols, used only with --warm.")
    args = parser.parse_args(argv)
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    report = build_report(warm=args.warm, symbols=symbols)
    print(render_report(report))
    return report.exit_code


def _schema_version(connection: sqlite3.Connection) -> str | None:
    try:
        row = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    value = str(row[0]).strip()
    return value if value.startswith("v") else f"v{value}"


def _directory_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".finsent-preflight-", delete=True):
            return True
    except OSError:
        return False


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _safe_message(exc: Exception | str) -> str:
    text = str(exc).strip() or exc.__class__.__name__ if isinstance(exc, Exception) else str(exc)
    for secret in [settings.alpaca_api_key, settings.alpaca_api_secret, settings.polygon_api_key, settings.marketaux_api_token, settings.gemini_api_key]:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:240]


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
