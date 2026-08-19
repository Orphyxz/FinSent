from __future__ import annotations

import logging

from finsent.app.config.settings import settings
from finsent.app.dashboard.app import create_app
from finsent.app.services.runtime_diagnostics import database_health
from finsent.app.utils.logging import configure_logging


logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    app = create_app()
    db = database_health()
    logger.info(
        "FinSent startup | Database=%s | Schema=%s | Alpaca=%s | Feed=%s | FinBERT=%s | Dashboard=http://127.0.0.1:8050",
        db.state,
        db.schema_version,
        "configured" if settings.alpaca_api_key and settings.alpaca_api_secret else "unconfigured",
        settings.alpaca_feed,
        "warmup" if settings.finbert_warmup else "lazy",
    )
    app.run(debug=False)


if __name__ == "__main__":
    main()
