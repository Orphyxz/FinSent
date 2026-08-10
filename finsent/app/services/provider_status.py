from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from finsent.app.utils.logging import safe_log_message


class DataSourceState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNCONFIGURED = "UNCONFIGURED"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    provider: str
    service: str
    status: DataSourceState
    message: str
    configured: bool
    available: bool
    stale: bool = False
    source_timestamp: datetime | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    @classmethod
    def available_status(
        cls,
        provider: str,
        service: str,
        message: str,
        *,
        source_timestamp: datetime | None = None,
    ) -> ProviderStatus:
        return cls(
            provider=provider,
            service=service,
            status=DataSourceState.AVAILABLE,
            message=safe_log_message(message),
            configured=True,
            available=True,
            source_timestamp=source_timestamp,
        )

    @classmethod
    def degraded(
        cls,
        provider: str,
        service: str,
        message: str,
        *,
        source_timestamp: datetime | None = None,
    ) -> ProviderStatus:
        return cls(
            provider=provider,
            service=service,
            status=DataSourceState.DEGRADED,
            message=safe_log_message(message),
            configured=True,
            available=True,
            source_timestamp=source_timestamp,
        )

    @classmethod
    def stale_status(
        cls,
        provider: str,
        service: str,
        message: str,
        *,
        source_timestamp: datetime | None = None,
    ) -> ProviderStatus:
        return cls(
            provider=provider,
            service=service,
            status=DataSourceState.STALE,
            message=safe_log_message(message),
            configured=True,
            available=True,
            stale=True,
            source_timestamp=source_timestamp,
        )

    @classmethod
    def unavailable(cls, provider: str, service: str, message: str, *, configured: bool = True) -> ProviderStatus:
        return cls(
            provider=provider,
            service=service,
            status=DataSourceState.UNAVAILABLE if configured else DataSourceState.UNCONFIGURED,
            message=safe_log_message(message),
            configured=configured,
            available=False,
        )

    @classmethod
    def unconfigured(cls, provider: str, service: str, message: str) -> ProviderStatus:
        return cls.unavailable(provider, service, message, configured=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "service": self.service,
            "status": self.status.value,
            "message": self.message,
            "configured": self.configured,
            "available": self.available,
            "stale": self.stale,
            "source_timestamp": self.source_timestamp,
            "checked_at": self.checked_at,
        }
