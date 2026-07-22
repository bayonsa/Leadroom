from __future__ import annotations

import argparse
from pathlib import Path

from app.config import ScraperConfig
from app.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local AI lead scraper")
    parser.add_argument("--niche", default="hair and beauty salons")
    parser.add_argument("--location", default="London UK")
    parser.add_argument("--max-results", type=int, default=12)
    parser.add_argument("--max-sites", type=int, default=10)
    parser.add_argument("--model", default="ollama/llama3.2:3b")
    parser.add_argument("--output", default="data/exports")
    parser.add_argument("--run-name", default="lead_pipeline_v3")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--database", default="data/lead_scraper.db")
    parser.add_argument("--resume", default="", help="Resume a persisted run ID")
    parser.add_argument("--search-provider", choices=["auto", "brave", "ddgs"], default="auto")
    parser.add_argument(
        "--discovery-mode",
        choices=["new_only", "reuse", "refresh"],
        default="new_only",
        help="Skip seen market domains, reuse saved leads, or scrape returned sites again",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ScraperConfig(
        niche=args.niche,
        location=args.location,
        model=args.model,
        max_results_per_query=args.max_results,
        max_sites=args.max_sites,
        output_dir=Path(args.output),
        run_name=args.run_name,
        delay_seconds=args.delay,
        database_path=Path(args.database),
        search_provider=args.search_provider,
        discovery_mode=args.discovery_mode,
    )
    run_pipeline(config, resume_run_id=args.resume or None)


if __name__ == "__main__":
    main()
