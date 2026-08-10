from __future__ import annotations

import logging

import pytest

from finsent.app.dashboard import view_model
from finsent.app.services.kaggle_data import is_git_lfs_pointer, load_us_price_frames
from finsent.app.utils.logging import safe_log_message


def test_env_example_contains_referenced_variables() -> None:
    env_example = view_model.Path(".env.example").read_text(encoding="utf-8")
    required = {
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "POLYGON_API_KEY",
        "KITE_API_KEY",
        "KITE_API_SECRET",
        "KITE_ACCESS_TOKEN",
        "MARKETAUX_API_TOKEN",
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "OPENAI_API_KEY",
        "MODEL_NAME",
        "FINSENT_LOG_LEVEL",
    }

    for name in required:
        assert f"{name}=" in env_example


def test_gitignore_keeps_env_example_available() -> None:
    lines = [
        line.strip()
        for line in view_model.Path(".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert ".env" in lines
    assert "!.env.example" in lines
    assert ".env.example" not in lines


def test_safe_log_message_redacts_environment_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "super-secret-token")

    message = safe_log_message("Provider failed with apiKey=super-secret-token")

    assert "super-secret-token" not in message
    assert "[redacted]" in message


def test_ensure_live_data_logs_refresh_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "super-secret-token")
    monkeypatch.setattr(view_model, "needs_live_refresh", lambda *_args, **_kwargs: True)

    def fail_refresh(_symbol):
        raise RuntimeError("provider failed with token super-secret-token")

    monkeypatch.setattr(view_model.intelligence_service, "run", fail_refresh)

    with caplog.at_level(logging.WARNING, logger=view_model.__name__):
        view_model.ensure_live_data(["AAPL"])

    assert "Live data refresh failed for AAPL" in caplog.text
    assert "super-secret-token" not in caplog.text


def test_us_price_import_rejects_git_lfs_pointer(tmp_path) -> None:
    pointer = tmp_path / "SnP_daily_update.csv"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:example\n"
        "size 147237046\n",
        encoding="utf-8",
    )

    assert is_git_lfs_pointer(pointer)
    with pytest.raises(ValueError, match="Git LFS pointer"):
        load_us_price_frames(pointer)
