"""A small in-process scheduler for background refresh jobs.

Jobs run on daemon threads at fixed intervals, never overlap with themselves, and log
rather than raise on failure, so a provider outage cannot take the dashboard down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from threading import Event, Lock, Thread
import time
from typing import Callable


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Job:
    name: str
    interval_seconds: float
    action: Callable[[], None]
    initial_delay_seconds: float = 0.0
    last_started: float | None = None
    last_finished: float | None = None
    last_error: str | None = None
    runs: int = 0
    _running: Lock = field(default_factory=Lock)


class BackgroundScheduler:
    def __init__(self, tick_seconds: float = 5.0) -> None:
        self._jobs: list[Job] = []
        self._stop = Event()
        self._tick = tick_seconds
        self._thread: Thread | None = None
        self._started_at = time.monotonic()

    @property
    def jobs(self) -> list[Job]:
        return list(self._jobs)

    def add(self, name: str, interval_seconds: float, action: Callable[[], None], *, initial_delay_seconds: float = 0.0) -> None:
        self._jobs.append(Job(name, interval_seconds, action, initial_delay_seconds))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._started_at = time.monotonic()
        self._thread = Thread(target=self._loop, name="finsent-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def due(self, job: Job, now: float) -> bool:
        if job.last_started is None:
            return now - self._started_at >= job.initial_delay_seconds
        return now - job.last_started >= job.interval_seconds

    def run_pending(self) -> None:
        now = time.monotonic()
        for job in self._jobs:
            if self.due(job, now) and job._running.acquire(blocking=False):
                job.last_started = now
                Thread(target=self._run, args=(job,), name=f"job-{job.name}", daemon=True).start()

    def _run(self, job: Job) -> None:
        try:
            job.action()
            job.last_error = None
        except Exception as exc:
            job.last_error = type(exc).__name__
            logger.warning("Background job %s failed: %s", job.name, job.last_error)
        finally:
            job.runs += 1
            job.last_finished = time.monotonic()
            job._running.release()

    def _loop(self) -> None:
        while not self._stop.wait(self._tick):
            self.run_pending()
