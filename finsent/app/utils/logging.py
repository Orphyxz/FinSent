from __future__ import annotations

import logging
import os
import re


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
SECRET_NAME_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
SECRET_PATTERN = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)(\s*[:=]\s*|\s+)[^\s&]+")


def configure_logging(level: str | None = None) -> None:
    """Configure readable local logs once, using only the standard library."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    raw_level = (level or os.getenv("FINSENT_LOG_LEVEL", "INFO")).strip().upper()
    numeric_level = getattr(logging, raw_level, logging.INFO)
    logging.basicConfig(level=numeric_level, format=DEFAULT_LOG_FORMAT)


def safe_log_message(message: object, max_length: int = 400) -> str:
    text = str(message or "").replace("\n", " ").strip()
    for name, value in os.environ.items():
        if not value or len(value) < 4:
            continue
        if any(marker in name.upper() for marker in SECRET_NAME_MARKERS):
            text = text.replace(value, "[redacted]")
    text = SECRET_PATTERN.sub(r"\1\2[redacted]", text)
    if len(text) > max_length:
        return f"{text[:max_length]}..."
    return text
