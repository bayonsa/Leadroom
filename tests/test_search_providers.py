import unittest
from threading import Event
from unittest.mock import patch

import httpx

from app.config import ScraperConfig
from app.search import SearchStopped, build_queries, search_business_sites
from app.search_providers import BraveProvider, create_provider


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.closed = False
        self.calls = 0

    def search(self, _query: str, _limit: int, _offset: int = 0) -> list[dict[str, str]]:
        self.calls += 1
        return [
            {
                "url": "https://studio-example.co.uk/contact",
                "title": "Studio Example Salon",
                "snippet": "London",
            },
            {"url": "https://yell.com/example", "title": "Directory", "snippet": ""},
        ]

    def close(self) -> None:
        self.closed = True


class SearchProviderTests(unittest.TestCase):
    def test_search_honors_stop_signal_and_closes_provider(self):
        provider = FakeProvider()
        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        with self.assertRaisesRegex(SearchStopped, "stopped"):
            search_business_sites(config, provider=provider, cancel_check=lambda: True)

        self.assertEqual(provider.calls, 0)
        self.assertTrue(provider.closed)

    def test_provider_results_are_normalized_filtered_and_deduplicated(self):
        provider = FakeProvider()
        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        sites = search_business_sites(config, provider=provider)

        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0]["domain"], "studio-example.co.uk")
        self.assertEqual(provider.calls, 5)
        self.assertTrue(provider.closed)

    def test_hybrid_search_runs_local_and_web_together_and_merges_evidence(self):
        local_started = Event()
        web_started = Event()

        class ConcurrentHybridProvider:
            name = "hybrid"

            def search_market(self, _niche, _location, _limit, _offset=0):
                local_started.set()
                self.assert_web_started()
                return [
                    {
                        "source": "osm_local",
                        "sources": ["local"],
                        "source_id": "osm-N-42",
                        "url": "https://merged-salon.co.uk/",
                        "homepage": "https://merged-salon.co.uk/",
                        "domain": "merged-salon.co.uk",
                        "title": "Merged Salon",
                        "snippet": "shop hairdresser | London",
                        "business_name": "Merged Salon",
                        "business_type": "shop hairdresser",
                        "city_or_area": "London",
                        "phone": "020 7000 0042",
                        "email": "",
                        "osm_url": "https://www.openstreetmap.org/node/42",
                    }
                ]

            def assert_web_started(self):
                if not web_started.wait(timeout=2):
                    raise AssertionError("web discovery did not overlap local discovery")

            def search(self, _query, _limit, _offset=0):
                self.assert_local_started()
                web_started.set()
                return [
                    {
                        "url": "https://merged-salon.co.uk/contact",
                        "title": "Merged Salon London",
                        "snippet": "Hair salon services in London",
                    }
                ]

            def assert_local_started(self):
                if not local_started.wait(timeout=2):
                    raise AssertionError("local discovery did not start before web discovery")

        diagnostics = {}
        config = ScraperConfig(
            niche="hair salons",
            location="London",
            delay_seconds=0,
        )

        sites = search_business_sites(
            config,
            provider=ConcurrentHybridProvider(),
            diagnostics=diagnostics,
        )

        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0]["sources"], ["web", "local"])
        self.assertEqual(sites[0]["phone"], "020 7000 0042")
        self.assertEqual(len(sites[0]["source_evidence"]), 2)
        self.assertEqual(diagnostics["merged_results"], 1)

    def test_local_continuation_has_no_total_limit_and_uses_exact_batches(self):
        class LocalProvider:
            name = "osm_local"

            def __init__(self):
                self.calls = []

            def search_market(self, _niche, _location, limit, offset=0):
                self.calls.append((limit, offset))
                return [
                    {
                        "source": "osm_local",
                        "domain": f"osm-N-{offset + index}",
                        "title": f"Local business {offset + index}",
                        "snippet": "shop beauty | London",
                        "url": "",
                    }
                    for index in range(limit)
                ]

        provider = LocalProvider()
        config = ScraperConfig(
            niche="beauty salons",
            location="London",
            search_provider="osm_local",
            max_sites=7,
            delay_seconds=0,
        )

        first = search_business_sites(config, provider=provider, start_page=0)
        second = search_business_sites(config, provider=provider, start_page=1)

        self.assertEqual(len(first), 7)
        self.assertEqual(len(second), 7)
        self.assertEqual(provider.calls, [(7, 0), (7, 7)])

    def test_new_only_searches_deeper_after_filtering_prior_domains(self):
        class PagingProvider:
            name = "paging"

            def __init__(self):
                self.calls: list[int] = []

            def search(self, query: str, _limit: int, offset: int = 0):
                self.calls.append(offset)
                query_number = build_queries("salons", "London").index(query)
                prefix = "old" if offset == 0 else "new"
                return [
                    {
                        "url": f"https://{prefix}-{query_number}.co.uk/",
                        "title": "London salons",
                        "snippet": "Salon services in London",
                    }
                ]

        provider = PagingProvider()
        diagnostics = {}
        config = ScraperConfig(
            niche="salons",
            location="London",
            max_results_per_query=1,
            max_sites=2,
            delay_seconds=0,
        )
        excluded = {f"old-{index}.co.uk" for index in range(5)}

        sites = search_business_sites(
            config,
            provider=provider,
            excluded_domains=excluded,
            diagnostics=diagnostics,
        )

        self.assertEqual(len(sites), 5)
        self.assertEqual(diagnostics["previously_seen_filtered"], 5)
        self.assertEqual(diagnostics["pages_searched"], 10)
        self.assertTrue(diagnostics["target_reached"])
        self.assertIn(1, provider.calls)

    def test_continuation_starts_at_persisted_search_page(self):
        class PagingProvider:
            name = "paging"

            def __init__(self):
                self.offsets: list[int] = []

            def search(self, query: str, _limit: int, offset: int = 0):
                self.offsets.append(offset)
                index = build_queries("salons", "London").index(query)
                return [
                    {
                        "url": f"https://page-{offset}-{index}.co.uk/",
                        "title": "London salon",
                        "snippet": "Salon services in London",
                    }
                ]

        provider = PagingProvider()
        diagnostics = {}
        config = ScraperConfig(
            niche="salons",
            location="London",
            max_results_per_query=10,
            max_sites=2,
            delay_seconds=0,
        )

        search_business_sites(
            config,
            provider=provider,
            excluded_domains={"already-seen.co.uk"},
            diagnostics=diagnostics,
            start_page=3,
        )

        self.assertTrue(all(offset >= 30 for offset in provider.offsets))
        self.assertEqual(diagnostics["next_search_page"], 5)

    def test_total_provider_failure_is_not_reported_as_an_empty_success(self):
        class FailedProvider:
            name = "failed"

            def search(self, _query, _limit, _offset=0):
                raise RuntimeError("provider unavailable")

        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        with self.assertRaisesRegex(RuntimeError, "All configured discovery sources failed"):
            search_business_sites(config, provider=FailedProvider())

    @patch("app.search_providers.time.sleep")
    def test_brave_retries_transient_failure_and_normalizes_response(self, _sleep):
        calls = 0
        offsets = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            offsets.append(request.url.params.get("offset"))
            if calls == 1:
                return httpx.Response(503, request=request)
            return httpx.Response(
                200,
                request=request,
                json={
                    "web": {
                        "results": [{"url": "https://clinic.test", "title": "Clinic", "description": "UK"}]
                    }
                },
            )

        provider = BraveProvider("secret", transport=httpx.MockTransport(handler))
        try:
            results = provider.search("clinic London", 10, offset=30)
        finally:
            provider.close()

        self.assertEqual(calls, 2)
        self.assertEqual(offsets, ["3", "3"])
        self.assertEqual(results[0]["snippet"], "UK")

    def test_auto_provider_and_config_snapshot_do_not_expose_api_key(self):
        config = ScraperConfig(
            niche="salons",
            location="London",
            brave_search_api_key="top-secret",
        )
        provider = create_provider("auto", config.brave_search_api_key)
        provider.close()

        self.assertEqual(provider.name, "brave")
        self.assertNotIn("top-secret", config.model_dump_json())


if __name__ == "__main__":
    unittest.main()
