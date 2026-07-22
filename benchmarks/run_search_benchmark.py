from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.config import ScraperConfig
from app.search import search_business_sites


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run candidate-search benchmark cases")
    parser.add_argument("--cases", default="benchmarks/search_cases.json")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--provider", choices=["auto", "brave", "ddgs"], default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    summary = []
    for case in cases:
        config = ScraperConfig(
            niche=case["niche"],
            location=case["location"],
            max_results_per_query=args.max_results,
            max_sites=args.top,
            delay_seconds=args.delay,
            search_provider=args.provider,
        )
        started = time.perf_counter()
        sites = search_business_sites(config)[: args.top]
        elapsed = round(time.perf_counter() - started, 2)
        summary.append({"niche": config.niche, "candidates": len(sites), "elapsed_seconds": elapsed})
        print(f"\nCASE: {config.niche} | {config.location} | {len(sites)} candidates")
        for site in sites:
            print(f"{site['domain']} | {site['title']}")
    print(json.dumps({"provider": args.provider, "cases": summary}, indent=2))


if __name__ == "__main__":
    main()
