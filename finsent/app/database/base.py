from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from finsent.app.config.settings import settings


Base = declarative_base()
SCHEMA_VERSION = "2"

if settings.database_url.startswith("sqlite:///"):
    sqlite_path = Path(settings.database_url.replace("sqlite:///", "", 1))
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def sqlite_path_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url.replace("sqlite:///", "", 1))


def backup_sqlite_database(database_url: str | None = None, suffix: str = "phase5-pre-migration") -> Path | None:
    target_url = database_url or settings.database_url
    sqlite_path = sqlite_path_from_url(target_url)
    if sqlite_path is None or not sqlite_path.exists() or sqlite_path.stat().st_size == 0:
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = sqlite_path.with_name(f"{sqlite_path.stem}.{suffix}.{timestamp}{sqlite_path.suffix}")
    shutil.copy2(sqlite_path, backup_path)
    return backup_path


def _table_names(bind: Engine) -> set[str]:
    with bind.begin() as connection:
        return {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def _add_missing_columns(bind: Engine, required_columns: dict[str, dict[str, str]]) -> None:
    with bind.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table_name, columns in required_columns.items():
            if table_name not in tables:
                continue
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_type in columns.items():
                if column_name in existing:
                    continue
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )


def _ensure_indexes(bind: Engine) -> None:
    indexes = [
        ("ix_news_articles_instrument_id", "news_articles", "instrument_id"),
        ("ix_news_articles_canonical_url", "news_articles", "canonical_url"),
        ("ix_news_articles_leaf_provider", "news_articles", "leaf_provider"),
        ("ix_quote_snapshots_instrument_id", "quote_snapshots", "instrument_id"),
        ("ix_quote_snapshots_data_mode", "quote_snapshots", "data_mode"),
        ("ix_signal_snapshots_instrument_id", "signal_snapshots", "instrument_id"),
        ("ix_price_bars_instrument_id", "price_bars", "instrument_id"),
        ("ix_price_bars_dataset_id", "price_bars", "dataset_id"),
    ]
    with bind.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for index_name, table_name, column_name in indexes:
            if table_name not in tables:
                continue
            columns = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            if column_name not in columns:
                continue
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"
            )


def _set_schema_version(bind: Engine) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with bind.begin() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "schema_metadata" not in tables:
            return
        existing = connection.exec_driver_sql(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if existing is None:
            connection.exec_driver_sql(
                "INSERT INTO schema_metadata (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", SCHEMA_VERSION, now),
            )
        elif existing[0] != SCHEMA_VERSION:
            connection.exec_driver_sql(
                "UPDATE schema_metadata SET value = ?, updated_at = ? WHERE key = 'schema_version'",
                (SCHEMA_VERSION, now),
            )


def apply_sqlite_migrations(bind: Engine | None = None) -> None:
    target_engine = bind or engine
    if target_engine.dialect.name != "sqlite":
        return

    required_columns = {
        "news_articles": {
            "instrument_id": "INTEGER",
            "exchange": "VARCHAR(16)",
            "provider": "VARCHAR(64)",
            "source_provider": "VARCHAR(64)",
            "leaf_provider": "VARCHAR(64)",
            "data_mode": "VARCHAR(32)",
            "publisher": "VARCHAR(128)",
            "canonical_url": "VARCHAR(1024)",
            "original_url": "VARCHAR(1024)",
            "raw_symbol": "VARCHAR(64)",
            "ingested_at": "DATETIME",
            "dedupe_hash": "VARCHAR(128)",
            "relevance_score": "FLOAT",
            "model_label": "VARCHAR(32)",
            "model_confidence": "FLOAT",
            "text_score": "FLOAT",
            "signal_confidence": "FLOAT",
            "bid_ask_spread": "FLOAT",
            "spread_pct": "FLOAT",
            "volume_ratio": "FLOAT",
            "buy_sell_ratio": "FLOAT",
            "buy_pressure": "FLOAT",
            "market_signal": "FLOAT",
            "relevant": "INTEGER",
            "impact_strength": "FLOAT",
            "time_horizon": "VARCHAR(32)",
            "catalyst_tag": "VARCHAR(64)",
            "short_reason": "TEXT",
            "analysis_provider": "VARCHAR(64)",
            "parse_status": "VARCHAR(32)",
        },
        "price_bars": {
            "instrument_id": "INTEGER",
            "provider": "VARCHAR(64)",
            "dataset_id": "VARCHAR(128)",
            "data_mode": "VARCHAR(32)",
            "quality_status": "VARCHAR(32)",
        },
        "quote_snapshots": {
            "instrument_id": "INTEGER",
            "leaf_provider": "VARCHAR(64)",
            "data_mode": "VARCHAR(32)",
            "freshness_label": "VARCHAR(32)",
            "data_quality_score": "FLOAT",
            "data_quality_label": "VARCHAR(32)",
            "data_quality_reasons_json": "TEXT",
        },
        "signal_snapshots": {
            "instrument_id": "INTEGER",
            "engine_name": "VARCHAR(64)",
            "engine_version": "VARCHAR(32)",
            "experiment_id": "INTEGER",
        },
    }

    _add_missing_columns(target_engine, required_columns)
    _ensure_indexes(target_engine)
    _set_schema_version(target_engine)


def init_db() -> None:
    from finsent.app.database import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
