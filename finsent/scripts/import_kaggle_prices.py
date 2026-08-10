from __future__ import annotations

import argparse

from finsent.app.services.kaggle_data import import_nse_archive, import_us_daily_update


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Kaggle India or US historical price files into the local FinSent database.")
    parser.add_argument(
        "--market",
        choices=["india", "us"],
        default="india",
        help="Choose which Kaggle dataset importer to use.",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        help="Optional ticker list to import, for example TCS.NS RELIANCE.NS INFY.NS or AAPL MSFT NVDA",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional India-only limit on how many CSV files to import from the archive.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.market == "us":
        imported = import_us_daily_update(tickers=args.tickers)
    else:
        imported = import_nse_archive(tickers=args.tickers, limit=args.limit)

    if not imported:
        print("No Kaggle price files were imported.")
        return

    print(f"Imported {len(imported)} ticker files into the local database.")
    for ticker, row_count in list(imported.items())[:20]:
        print(f"- {ticker}: {row_count} rows")
    if len(imported) > 20:
        print(f"... and {len(imported) - 20} more tickers")


if __name__ == "__main__":
    main()
