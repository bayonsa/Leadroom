from __future__ import annotations

import time
from typing import Any, Protocol

import httpx
from ddgs import DDGS

from app.local_data import LocalDataService


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, limit: int, offset: int = 0) -> list[dict[str, str]]: ...


class DdgsProvider:
    name = "ddgs"

    def search(self, query: str, limit: int, offset: int = 0) -> list[dict[str, str]]:
        with DDGS(timeout=10) as ddgs:
            results = list(
                ddgs.text(
                    query,
                    region="uk-en",
                    safesearch="moderate",
                    max_results=limit + offset,
                )
            )[offset : offset + limit]
            return [
                {
                    "url": str(item.get("href") or item.get("url") or ""),
                    "title": str(item.get("title") or ""),
                    "snippet": str(item.get("body") or ""),
                }
                for item in results
            ]


class BraveProvider:
    name = "brave"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise ValueError("BRAVE_SEARCH_API_KEY is required for the Brave provider")
        self.client = httpx.Client(
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            timeout=httpx.Timeout(12),
            transport=transport,
        )

    def search(self, query: str, limit: int, offset: int = 0) -> list[dict[str, str]]:
        page = offset // max(1, limit)
        if page > 9:
            return []
        response: httpx.Response | None = None
        for attempt in range(3):
            response = self.client.get(
                self.endpoint,
                params={
                    "q": query,
                    "country": "GB",
                    "search_lang": "en",
                    "count": min(limit, 20),
                    "offset": page,
                },
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            time.sleep(0.25 * (2**attempt))
        assert response is not None
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return [
            {
                "url": str(item.get("url") or ""),
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("description") or ""),
            }
            for item in (payload.get("web") or {}).get("results", [])
        ]

    def close(self) -> None:
        self.client.close()


class OsmLocalProvider:
    name = "osm_local"

    def __init__(self, service: LocalDataService | None = None) -> None:
        self.service = service or LocalDataService()

    def search(self, query: str, limit: int, offset: int = 0) -> list[dict[str, str]]:
        raise RuntimeError("OSM local search requires a market niche and location")

    def search_market(
        self,
        niche: str,
        location: str,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, str]]:
        return self.service.search(niche, location, limit, offset)


class HybridProvider(DdgsProvider):
    name = "hybrid"

    def __init__(self, local: LocalDataService | None = None) -> None:
        self.local = OsmLocalProvider(local)

    def search_market(
        self,
        niche: str,
        location: str,
        limit: int,
        offset: int = 0,
    ) -> list[dict[str, str]]:
        status = self.local.service.status()
        if not status["ready"]:
            raise RuntimeError("The local discovery index is not ready")
        return self.local.search_market(niche, location, limit, offset)


def create_provider(name: str, brave_api_key: str = "") -> SearchProvider:
    resolved = "brave" if name == "auto" and brave_api_key else "ddgs" if name == "auto" else name
    if resolved == "brave":
        return BraveProvider(brave_api_key)
    if resolved == "ddgs":
        return DdgsProvider()
    if resolved == "osm_local":
        return OsmLocalProvider()
    if resolved == "hybrid":
        return HybridProvider()
    raise ValueError(f"Unknown search provider: {name}")
