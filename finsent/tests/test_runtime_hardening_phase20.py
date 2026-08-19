from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.config.settings import settings
from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import SignalRun
from finsent.app.services.market_context import aligned_window_returns
from finsent.app.services.provider_reliability import CacheEntry, DataMode, ProviderTTLCache
from finsent.app.services.sentiment_v2 import FinBERTSentimentAnalyzer, ModelLoadState
from finsent.app.services.signal_service_v2 import SignalEngineV2Service
from finsent.app.services.symbol_registry import registry


NOW = datetime(2026, 8, 19, 16, 0, 0)


def test_provider_ttl_cache_records_hits_misses_expiry_and_stale_hits() -> None:
    current = {"now": NOW}
    cache = ProviderTTLCache(clock=lambda: current["now"], name="test_cache")
    cache.set(("quote", "AAPL"), CacheEntry("payload", "alpaca", "alpaca", DataMode.LIVE, NOW, NOW))

    assert cache.get(("quote", "AAPL"), 10).data == "payload"
    assert cache.get(("quote", "MSFT"), 10) is None
    current["now"] = NOW + timedelta(seconds=30)
    assert cache.get(("quote", "AAPL"), 10) is None
    assert cache.get_stale(("quote", "AAPL")).data == "payload"

    stats = cache.stats()
    assert stats.hits == 1
    assert stats.misses == 2
    assert stats.expired == 1
    assert stats.stale_hits == 1
    assert stats.entries == 1


def test_finbert_model_initializes_once_across_analyzer_instances(monkeypatch) -> None:
    model_name = "unit-test-finbert"
    FinBERTSentimentAnalyzer._shared_assets.pop(model_name, None)
    FinBERTSentimentAnalyzer._shared_errors.pop(model_name, None)
    FinBERTSentimentAnalyzer._shared_state.pop(model_name, None)
    calls = {"tokenizer": 0, "model": 0}

    class FakeTokenizer:
        @classmethod
        def from_pretrained(cls, name):
            assert name == model_name
            calls["tokenizer"] += 1
            return cls()

        def __call__(self, text, **_kwargs):
            assert text
            return {"input_ids": [1, 2, 3]}

    class FakeModel:
        config = SimpleNamespace(id2label={0: "positive", 1: "negative", 2: "neutral"})

        @classmethod
        def from_pretrained(cls, name):
            assert name == model_name
            calls["model"] += 1
            return cls()

        def eval(self):
            return None

        def __call__(self, **_encoded):
            return SimpleNamespace(logits=[[1.0, 0.0, 0.0]])

    class FakeNoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    class FakeProbabilities:
        def __getitem__(self, _idx):
            return self

        def tolist(self):
            return [0.7, 0.1, 0.2]

    fake_torch = SimpleNamespace(
        no_grad=lambda: FakeNoGrad(),
        nn=SimpleNamespace(functional=SimpleNamespace(softmax=lambda _logits, dim: FakeProbabilities())),
    )
    fake_transformers = SimpleNamespace(
        AutoTokenizer=FakeTokenizer,
        AutoModelForSequenceClassification=FakeModel,
    )
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setitem(__import__("sys").modules, "transformers", fake_transformers)

    first = FinBERTSentimentAnalyzer(model_name=model_name)
    second = FinBERTSentimentAnalyzer(model_name=model_name)

    assert first.warmup() is True
    assert second.warmup() is True
    assert calls == {"tokenizer": 1, "model": 1}
    assert first.state == ModelLoadState.READY
    assert second.state == ModelLoadState.READY


def test_dashboard_state_cache_reuses_identical_workspace(monkeypatch) -> None:
    from finsent.app.dashboard import view_model

    calls = {"count": 0}
    state = view_model.DashboardState(
        news_df=view_model.empty_news_frame(),
        price_df=view_model.empty_price_frame(),
        event_df=pd.DataFrame(),
        daily_summary_df=pd.DataFrame(),
        compare_df=pd.DataFrame(columns=view_model.COMPARE_COLUMNS),
        sector_df=pd.DataFrame(),
        snapshot_map={},
        quote_meta_map={},
        signal_meta_map={},
        demo_mode=False,
        data_status="ok",
        data_mode=view_model.DATA_MODE_UNAVAILABLE,
    )

    def fake_builder(*_args, **_kwargs):
        calls["count"] += 1
        return state

    view_model._dashboard_state_cache._entry = None
    monkeypatch.setattr(view_model, "_build_dashboard_state_uncached", fake_builder)
    monkeypatch.setattr(view_model, "detect_data_mode", lambda: view_model.DATA_MODE_UNAVAILABLE)
    monkeypatch.setattr(settings, "dashboard_state_cache_ttl_seconds", 60)

    first = view_model.build_dashboard_state("AAPL", ["NVDA"], "medium", None, None)
    second = view_model.build_dashboard_state("AAPL", ["NVDA"], "medium", None, None)

    assert first is second
    assert calls["count"] == 1


def test_market_context_aligned_returns_use_common_overlap() -> None:
    timestamps = pd.to_datetime(["2026-08-19 10:00", "2026-08-19 10:15", "2026-08-19 10:30"])
    stock = pd.DataFrame({"timestamp": timestamps, "close": [100, 103, 106]})
    benchmark = pd.DataFrame({"timestamp": timestamps[1:], "close": [200, 202]})

    stock_return, benchmark_return, overlap = aligned_window_returns(stock, benchmark)

    assert overlap == 2
    assert stock_return == pytest.approx((106 - 103) / 103)
    assert benchmark_return == pytest.approx((202 - 200) / 200)


def test_signal_v2_live_persistence_reuses_identical_input_fingerprint() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    symbol = registry.resolve_any("AAPL")
    assert symbol is not None

    with Session() as session:
        service = SignalEngineV2Service(session=session)
        signal_input = service.build_input(
            instrument=symbol,
            provider_metadata={
                "run_type": "APPLICATION_LIVE_RUN",
                "input_fingerprint": "same-input",
            },
            evaluation_timestamp=NOW,
        )
        first = service.evaluate(signal_input, persist=True)
        second = service.evaluate(signal_input, persist=True)
        session.commit()

        rows = session.execute(select(SignalRun)).scalars().all()

    assert first.persisted_run_id == second.persisted_run_id
    assert len(rows) == 1
