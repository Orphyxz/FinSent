from __future__ import annotations

import logging
from threading import Thread

from finsent.app.config.settings import settings
from finsent.app.dashboard.app import create_app
from finsent.app.dashboard.intelligence import executive_snapshot, watchlist_for_market
from finsent.app.services.event_explorer import load_event_explorer
from finsent.app.dashboard.view_model import ensure_live_data
from finsent.app.services.market_map import market_map
from finsent.app.services.market_overview import index_summaries, warm_caches
from finsent.app.services.scheduler import BackgroundScheduler
from finsent.app.services.runtime_diagnostics import database_health
from finsent.app.utils.logging import configure_logging


logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    app = create_app()
    db = database_health()
    logger.info(
        "FinSent startup | Database=%s | Schema=%s | Alpaca=%s | Feed=%s | FinBERT=%s | Dashboard=http://%s:%s",
        db.state,
        db.schema_version,
        "configured" if settings.alpaca_api_key and settings.alpaca_api_secret else "unconfigured",
        settings.alpaca_feed,
        "warmup" if settings.finbert_warmup else "lazy",
        settings.dashboard_host,
        settings.dashboard_port,
    )
    # Fill index, watchlist and overview caches while the server starts, so the first
    # page load reads from memory instead of waiting on providers.
    Thread(target=_warm_up, name="dashboard-warmup", daemon=True).start()
    build_scheduler().start()
    app.run(host=settings.dashboard_host, port=settings.dashboard_port, debug=False)


def _warm_up() -> None:
    try:
        warm_caches(watchlist_for_market("US"))
        executive_snapshot("US")
        load_event_explorer()
    except Exception as exc:
        logger.warning("Dashboard warm-up failed: %s", type(exc).__name__)


def build_scheduler() -> BackgroundScheduler:
    """Keep watchlist news/sentiment, the market map and index levels fresh in the background."""
    scheduler = BackgroundScheduler()
    news_every = settings.background_news_refresh_minutes * 60
    market_every = settings.background_market_refresh_minutes * 60
    scheduler.add("us-watchlist-news", news_every, lambda: ensure_live_data(watchlist_for_market("US")), initial_delay_seconds=60)
    scheduler.add("india-watchlist-news", news_every, lambda: ensure_live_data(watchlist_for_market("INDIA")), initial_delay_seconds=120)
    scheduler.add("market-map", market_every, lambda: (market_map("US"), market_map("INDIA")), initial_delay_seconds=20)
    scheduler.add("indices", market_every, index_summaries, initial_delay_seconds=30)
    return scheduler


if __name__ == "__main__":
    main()
