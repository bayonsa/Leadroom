from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from app.config import ScraperConfig
from app.filters import (
    domain_key,
    homepage_url,
    is_good_business_url,
    is_relevant_to_location,
    is_relevant_to_niche,
)
from app.search_providers import SearchProvider, create_provider


class SearchStopped(RuntimeError):
    pass


def build_queries(niche: str, location: str) -> list[str]:
    return [
        f'{niche} "{location}" official website contact',
        f'{niche} "{location}" "book now" "contact"',
        f'{niche} "{location}" "services" "prices"',
        f'"{niche}" "{location}" "official website"',
        f'"{niche}" "{location}" "contact"',
    ]


def search_business_sites(
    config: ScraperConfig,
    provider: SearchProvider | None = None,
    excluded_domains: set[str] | None = None,
    diagnostics: dict[str, int | bool] | None = None,
    start_page: int = 0,
    local_start_page: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[], None] | None = None,
    deadline: float | None = None,
) -> list[dict[str, str]]:
    unique: list[dict[str, Any]] = []
    candidate_positions: dict[str, int] = {}
    seen_domains: set[str] = set()
    excluded_domains = excluded_domains or set()
    provider = provider or create_provider(config.search_provider, config.brave_search_api_key)
    queries = build_queries(config.niche, config.location)
    target_pool = (
        config.max_sites
        if provider.name == "osm_local"
        else min(500, max(config.max_sites * 2, config.max_results_per_query))
    )
    max_pages = 4 if excluded_domains else 1
    raw_result_count = 0
    relevant_result_count = 0
    previous_result_count = 0
    duplicate_result_count = 0
    successful_sources = 0
    failed_sources = 0
    local_result_count = 0
    web_result_count = 0
    merged_result_count = 0
    pages_searched = 0
    last_page = start_page - 1
    local_page = start_page if local_start_page is None else local_start_page

    def check_control() -> None:
        if cancel_check and cancel_check():
            raise SearchStopped("Search was stopped")
        if deadline is not None and time.monotonic() >= deadline:
            raise SearchStopped("Search timed out")

    def controlled_sleep(seconds: float) -> None:
        remaining = seconds
        while remaining > 0:
            check_control()
            interval = min(0.1, remaining)
            time.sleep(interval)
            remaining -= interval

    def collect(item: dict[str, Any]) -> None:
        nonlocal relevant_result_count, previous_result_count, duplicate_result_count
        nonlocal local_result_count, web_result_count, merged_result_count
        url = item.get("url") or ""
        title = item.get("title", "")
        body = item.get("snippet", "")
        structured = item.get("source") == "osm_local"
        source_name = "local" if structured else "web"
        if structured:
            local_result_count += 1
        else:
            web_result_count += 1
        if not structured:
            if not is_good_business_url(url, title, config.blocked_domains):
                return
            if not is_relevant_to_niche(url, title, body, config.niche):
                return
            if not is_relevant_to_location(url, title, body, config.location):
                return
        relevant_result_count += 1
        domain = item.get("domain") or domain_key(url)
        if domain in excluded_domains:
            previous_result_count += 1
            return
        if domain in candidate_positions:
            duplicate_result_count += 1
            position = candidate_positions[domain]
            before = set(unique[position].get("sources") or [])
            unique[position] = _merge_search_candidate(unique[position], dict(item), source_name)
            if len(set(unique[position].get("sources") or [])) > len(before):
                merged_result_count += 1
            return
        seen_domains.add(domain)
        if structured:
            candidate = dict(item)
        else:
            candidate = {
                "title": title,
                "url": url,
                "homepage": homepage_url(url),
                "snippet": body,
                "domain": domain,
                "source": "web",
            }
        candidate["sources"] = list(dict.fromkeys([*(candidate.get("sources") or []), source_name]))
        candidate["source_evidence"] = [_search_evidence(candidate, source_name)]
        candidate_positions[domain] = len(unique)
        unique.append(candidate)

    executor: ThreadPoolExecutor | None = None
    local_future: Future[list[dict[str, str]]] | None = None
    try:
        market_search = getattr(provider, "search_market", None)
        if market_search:
            check_control()
            if progress_callback:
                progress_callback()
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-discovery")
            local_future = executor.submit(
                market_search,
                config.niche,
                config.location,
                target_pool,
                local_page * target_pool,
            )
            if provider.name == "osm_local":
                last_page = start_page

        page_range = [] if provider.name == "osm_local" else range(start_page, start_page + max_pages)
        for page in page_range:
            last_page = page
            offset = page * config.max_results_per_query
            for query in queries:
                check_control()
                if progress_callback:
                    progress_callback()
                print(f"\nSearch query [{provider.name}, page {page + 1}]: {query}")
                started = time.perf_counter()
                try:
                    results = provider.search(query, config.max_results_per_query, offset)
                except Exception as exc:
                    failed_sources += 1
                    print(f"Search failed [{provider.name}]: {type(exc).__name__}: {exc}")
                    continue
                successful_sources += 1
                check_control()
                pages_searched += 1
                raw_result_count += len(results)
                elapsed_ms = round((time.perf_counter() - started) * 1000)
                print(f"Search result [{provider.name}]: {len(results)} result(s), {elapsed_ms} ms")

                for item in results:
                    collect(item)

                controlled_sleep(config.delay_seconds)
            if len(unique) >= target_pool:
                break

        if local_future is not None:
            check_control()
            try:
                timeout = None if deadline is None else max(0.01, deadline - time.monotonic())
                local_results = local_future.result(timeout=timeout)
                successful_sources += 1
            except FutureTimeout as exc:
                local_future.cancel()
                raise SearchStopped("Local discovery timed out") from exc
            except Exception as exc:
                failed_sources += 1
                print(f"Search failed [osm_local]: {type(exc).__name__}: {exc}")
                local_results = []
            pages_searched += 1
            raw_result_count += len(local_results)
            for item in local_results:
                collect(item)
    finally:
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        close = getattr(provider, "close", None)
        if close:
            close()

    if successful_sources == 0 and failed_sources:
        raise RuntimeError("All configured discovery sources failed")

    if diagnostics is not None:
        diagnostics.update(
            {
                "raw_results": raw_result_count,
                "relevant_results": relevant_result_count,
                "previously_seen_filtered": previous_result_count,
                "duplicates_filtered": duplicate_result_count,
                "local_results": local_result_count,
                "web_results": web_result_count,
                "merged_results": merged_result_count,
                "new_candidates": len(unique),
                "pages_searched": pages_searched,
                "next_search_page": last_page + 1,
                "next_local_page": local_page + 1 if local_future is not None else local_page,
                "target_reached": len(unique) >= config.max_sites,
            }
        )

    unique.sort(
        key=lambda item: (
            len(item.get("sources") or []),
            bool(item.get("email") or item.get("phone")),
            bool(item.get("url")),
        ),
        reverse=True,
    )
    return unique


def _search_evidence(candidate: dict[str, Any], source: str) -> dict[str, str]:
    return {
        "source": source,
        "url": str(candidate.get("osm_url") or candidate.get("url") or ""),
        "source_id": str(candidate.get("source_id") or candidate.get("domain") or ""),
    }


def _merge_search_candidate(current: dict[str, Any], incoming: dict[str, Any], source: str) -> dict[str, Any]:
    merged = dict(current)
    current_sources = list(current.get("sources") or [])
    incoming_sources = list(incoming.get("sources") or [source])
    merged["sources"] = list(dict.fromkeys([*current_sources, *incoming_sources]))
    evidence = [*(current.get("source_evidence") or []), _search_evidence(incoming, source)]
    evidence_by_location = {f"{item.get('source')}:{item.get('url')}": item for item in evidence}
    merged["source_evidence"] = list(evidence_by_location.values())
    for field in (
        "business_name",
        "business_type",
        "city_or_area",
        "address",
        "phone",
        "email",
        "latitude",
        "longitude",
        "osm_url",
        "source_id",
    ):
        if incoming.get(field) and not merged.get(field):
            merged[field] = incoming[field]
    for field in ("url", "homepage", "title"):
        if incoming.get(field) and not merged.get(field):
            merged[field] = incoming[field]
    snippets = [value for value in (current.get("snippet"), incoming.get("snippet")) if value]
    merged["snippet"] = " | ".join(dict.fromkeys(snippets))
    merged["source"] = "hybrid" if len(merged["sources"]) > 1 else current.get("source", source)
    return merged
