from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from threading import RLock
from typing import Any

from sqlalchemy import text

from finsent.app.database.base import SCHEMA_VERSION, SessionLocal, sqlite_path_from_url
from finsent.app.config.settings import settings
from finsent.app.utils.logging import safe_log_message


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class CacheStats:
    name: str
    hits: int = 0
    misses: int = 0
    stale_hits: int = 0
    expired: int = 0
    evictions: int = 0
    entries: int = 0

    @property
    def total_lookups(self) -> int:
        return self.hits + self.misses + self.stale_hits

    @property
    def hit_rate(self) -> float | None:
        total = self.total_lookups
        if total <= 0:
            return None
        return self.hits / total


@dataclass(frozen=True, slots=True)
class RefreshDiagnostics:
    key: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    cache_status: str
    symbols: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    state: str
    schema_version: str
    path: str | None
    size_bytes: int | None
    checked_at: datetime
    message: str


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    app_mode: str
    build_ref: str
    provider_health: tuple[dict[str, Any], ...]
    cache_stats: tuple[CacheStats, ...]
    finbert_state: str
    finbert_error: str | None
    db_health: DatabaseHealth
    last_refresh: RefreshDiagnostics | None
    latest_runtime_error: str | None
    active_market_provider: str | None
    active_news_provider: str | None


class RuntimeDiagnosticsService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._cache_stats: dict[str, CacheStats] = {}
        self._provider_health: tuple[dict[str, Any], ...] = ()
        self._finbert_state = "UNINITIALIZED"
        self._finbert_error: str | None = None
        self._last_refresh: RefreshDiagnostics | None = None
        self._latest_runtime_error: str | None = None
        self._active_market_provider: str | None = None
        self._active_news_provider: str | None = None

    def record_cache_stats(self, stats: CacheStats) -> None:
        with self._lock:
            self._cache_stats[stats.name] = stats

    def record_provider_health(self, records: list[object]) -> None:
        safe_records: list[dict[str, Any]] = []
        for row in records:
            provider = str(getattr(row, "provider", "unknown"))
            service = str(getattr(row, "service", "unknown"))
            status = getattr(getattr(row, "last_status", None), "value", getattr(row, "last_status", None))
            if status is None:
                status = getattr(getattr(row, "state", None), "value", getattr(row, "state", "UNKNOWN"))
            safe_records.append(
                {
                    "provider": provider,
                    "service": service,
                    "configured": bool(getattr(row, "configured", False)),
                    "state": str(status),
                    "last_success": getattr(row, "last_successful_fetch", None) or getattr(row, "last_success", None),
                    "last_failure": getattr(row, "last_failure", None),
                    "last_latency_ms": getattr(row, "last_latency_ms", None),
                    "success_count": int(getattr(row, "success_count", 0) or 0),
                    "failure_count": int(getattr(row, "failure_count", 0) or 0),
                    "consecutive_failures": int(getattr(row, "consecutive_failures", 0) or 0),
                    "last_failure_category": str(getattr(getattr(row, "last_failure_category", None), "value", getattr(row, "last_failure_category", "")) or ""),
                    "rate_limited": bool(getattr(row, "rate_limited", False)),
                    "last_status_code": getattr(row, "last_status_code", None),
                    "circuit_state": getattr(row, "circuit_state", None),
                    "recent_fallback_used": bool(getattr(row, "recent_fallback_used", False)),
                }
            )
        with self._lock:
            self._provider_health = tuple(safe_records)

    def record_finbert_state(self, state: str, error: str | None = None) -> None:
        with self._lock:
            self._finbert_state = state
            self._finbert_error = safe_log_message(error) if error else None

    def record_refresh(
        self,
        *,
        key: str,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: int,
        cache_status: str,
        symbols: list[str],
        error: Exception | str | None = None,
    ) -> None:
        safe_error = safe_log_message(error) if error else None
        with self._lock:
            self._last_refresh = RefreshDiagnostics(
                key=key,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                cache_status=cache_status,
                symbols=tuple(symbols),
                error=safe_error,
            )
            if safe_error:
                self._latest_runtime_error = safe_error

    def record_active_providers(self, *, market_provider: str | None = None, news_provider: str | None = None) -> None:
        with self._lock:
            if market_provider:
                self._active_market_provider = market_provider
            if news_provider:
                self._active_news_provider = news_provider

    def snapshot(self, app_mode: str = "UNKNOWN") -> RuntimeSnapshot:
        with self._lock:
            return RuntimeSnapshot(
                app_mode=app_mode,
                build_ref=build_reference(),
                provider_health=self._provider_health,
                cache_stats=tuple(sorted(self._cache_stats.values(), key=lambda row: row.name)),
                finbert_state=self._finbert_state,
                finbert_error=self._finbert_error,
                db_health=database_health(),
                last_refresh=self._last_refresh,
                latest_runtime_error=self._latest_runtime_error,
                active_market_provider=self._active_market_provider,
                active_news_provider=self._active_news_provider,
            )


def build_reference() -> str:
    try:
        root = Path(__file__).resolve().parents[3]
        value = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
    except Exception:
        return "unknown/local"
    return value or "unknown/local"


def database_health() -> DatabaseHealth:
    checked_at = utc_now()
    db_path = sqlite_path_from_url(settings.database_url)
    size_bytes = db_path.stat().st_size if db_path is not None and db_path.exists() else None
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1")).scalar_one()
        return DatabaseHealth(
            state="HEALTHY",
            schema_version=f"v{SCHEMA_VERSION}",
            path=str(db_path) if db_path is not None else None,
            size_bytes=size_bytes,
            checked_at=checked_at,
            message="SQLite check succeeded.",
        )
    except Exception as exc:
        return DatabaseHealth(
            state="UNAVAILABLE",
            schema_version=f"v{SCHEMA_VERSION}",
            path=str(db_path) if db_path is not None else None,
            size_bytes=size_bytes,
            checked_at=checked_at,
            message=safe_log_message(exc),
        )


runtime_diagnostics = RuntimeDiagnosticsService()
