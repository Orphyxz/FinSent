from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsent.app.database.base import Base
from finsent.app.database.repository import NewsRepository
from finsent.app.services.news_providers import NormalizedNewsArticle, build_article_dedupe_hash, normalize_news_limit


@pytest.fixture
def in_memory_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with Session() as session:
        yield session


def test_pipeline_passes_requested_article_limit(monkeypatch) -> None:
    import finsent.app.services.pipeline as pipeline_module

    seen: dict[str, int | None] = {}

    class StubIntelligenceService:
        def run(self, symbol, *, news_limit=None):
            seen["news_limit"] = news_limit

    monkeypatch.setattr(pipeline_module, "intelligence_service", StubIntelligenceService())

    pipeline_module.FinSentPipeline().run("AAPL", limit=3)

    assert seen["news_limit"] == 3


def test_pipeline_zero_article_limit_takes_precedence(monkeypatch) -> None:
    import finsent.app.services.pipeline as pipeline_module

    seen: dict[str, int | None] = {}

    class StubIntelligenceService:
        def run(self, symbol, *, news_limit=None):
            seen["news_limit"] = news_limit

    monkeypatch.setattr(pipeline_module, "intelligence_service", StubIntelligenceService())

    pipeline_module.FinSentPipeline().run("AAPL", limit=0)

    assert seen["news_limit"] == 0


def test_news_limit_validation() -> None:
    assert normalize_news_limit(None, default=7) == 7
    assert normalize_news_limit(0, default=7) == 0
    assert normalize_news_limit(999, default=7) == 50
    with pytest.raises(ValueError, match="zero or greater"):
        normalize_news_limit(-1)


def test_dedupe_hash_ignores_tracking_query_parameters() -> None:
    published_at = datetime(2026, 8, 9, 10, 30)

    first = build_article_dedupe_hash(
        title="Apple beats expectations",
        url="https://Example.com/story/?utm_source=newsletter&id=42",
        source="Reuters",
        published_at=published_at,
    )
    second = build_article_dedupe_hash(
        title="  apple   beats expectations ",
        url="https://example.com/story?id=42&utm_campaign=x",
        source="reuters",
        published_at=published_at,
    )
    separate_article = build_article_dedupe_hash(
        title="Apple beats expectations",
        url="https://example.com/story?id=43",
        source="Reuters",
        published_at=published_at,
    )

    assert first == second
    assert first != separate_article


def test_news_repository_uses_dedupe_hash_before_url(in_memory_session) -> None:
    article = NormalizedNewsArticle(
        article_id="a1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple beats expectations",
        summary="First version",
        url="https://example.com/story?utm_source=one&id=42",
        published_at=datetime(2026, 8, 9, 10, 30),
        ingested_at=datetime(2026, 8, 9, 10, 31),
        provider="polygon",
        dedupe_hash="same-hash",
        relevance_score=1.0,
    )
    updated = NormalizedNewsArticle(
        article_id="a2",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple beats expectations",
        summary="Updated version",
        url="https://example.com/story?id=42&utm_source=two",
        published_at=datetime(2026, 8, 9, 10, 30),
        ingested_at=datetime(2026, 8, 9, 10, 35),
        provider="polygon",
        dedupe_hash="same-hash",
        relevance_score=1.0,
    )
    repo = NewsRepository(in_memory_session)
    first_row = repo.upsert_normalized_news(_Symbol(), article, _Analysis())
    second_row = repo.upsert_normalized_news(_Symbol(), updated, _Analysis())
    in_memory_session.flush()
    stored = repo.list_news_df("AAPL", "US")

    assert first_row.id == second_row.id
    assert len(stored) == 1
    assert stored.iloc[0]["summary"] == "Updated version"


class _Symbol:
    ticker = "AAPL"
    exchange = "US"


class _Analysis:
    relevant = True
    sentiment = "bullish"
    confidence = 0.7
    impact_strength = 0.5
    time_horizon = "1-3d"
    catalyst_tag = "earnings"
    short_reason = "test"
    provider = "gemini"
    parse_status = "ok"
