from __future__ import annotations

import argparse

from finsent.app.services.pipeline import FinSentPipeline
from finsent.app.utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the FinSent v1 pipeline.")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol to analyze.")
    parser.add_argument("--limit", type=int, default=15, help="Number of news items to scrape.")
    parser.add_argument(
        "--return-window-minutes",
        type=int,
        default=60,
        help="Forward return window in minutes.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    pipeline = FinSentPipeline()
    result = pipeline.run(
        ticker=args.ticker,
        limit=args.limit,
        return_window_minutes=args.return_window_minutes,
    )

    print(f"News rows: {len(result.news_df)}")
    print(f"Price rows: {len(result.price_df)}")
    print(f"Joined event rows: {len(result.event_df)}")
    if not result.summary_df.empty:
        print(result.summary_df.to_string(index=False))
    else:
        print("No summary data available.")


if __name__ == "__main__":
    main()
