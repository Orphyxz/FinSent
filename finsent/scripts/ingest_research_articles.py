from __future__ import annotations

import argparse
from pathlib import Path

from finsent.app.database.base import SessionLocal, init_db
from finsent.app.services.research_dataset import LocalResearchArticleImporter, ResearchArticleImportConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely import real historical research articles from an explicit local CSV.")
    parser.add_argument("--source", choices=["local-csv"], default="local-csv")
    parser.add_argument("--file", required=True, help="Input CSV with title/headline, published_at/timestamp, symbol/ticker, and source columns.")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--market", default=None, help="Default exchange/market if rows omit exchange.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dry_run and not args.execute:
        print("Use --dry-run to validate or --execute to import.")
        return
    init_db()
    with SessionLocal() as session:
        summary = LocalResearchArticleImporter(session).import_file(
            ResearchArticleImportConfig(
                source_file=Path(args.file),
                dataset_id=args.dataset_id,
                default_exchange=args.market,
                limit=args.limit,
                dry_run=not args.execute,
            )
        )
        if args.execute:
            session.commit()
        print(summary)


if __name__ == "__main__":
    main()
