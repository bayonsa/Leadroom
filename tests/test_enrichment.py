import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from app.config import ScraperConfig
from app.enrichment import (
    FetchResult,
    HtmlFetcher,
    apply_enrichment,
    discover_relevant_links,
    enrich_public_pages,
    extract_public_data,
)

HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {"@type":"BeautySalon","name":"Example Beauty","telephone":"020 1234 5678",
       "email":"info@example.com","address":{"addressLocality":"London"}}
    </script>
  </head>
  <body>
    <a href="/contact-us">Contact us</a>
    <a href="/about">About</a>
    <a href="/book-online">Book now</a>
    <a href="https://other.example/contact">External contact</a>
    <a href="mailto:owner.person@example.com">Owner</a>
    <a href="mailto:hello@example.com?subject=Hi">Email</a>
    <a href="tel:+442012345678">Call</a>
    <a href="https://instagram.com/example">Instagram</a>
  </body>
</html>
"""

GRAPH_HTML = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"Example site"},
  {"@type":"Dentist","name":"Graph Dental","telephone":"0121 000 0000"}
]}
</script>
"""

MULTI_TYPE_HTML = """
<script type="application/ld+json">
{"@type":["Organization","HVACBusiness"],"name":"Air Options"}
</script>
"""


class EnrichmentTests(unittest.TestCase):
    @patch("app.enrichment.sync_playwright")
    def test_browser_fallback_uses_system_edge_on_windows(self, playwright_factory):
        playwright = MagicMock()
        playwright_factory.return_value.__enter__.return_value = playwright
        page = playwright.chromium.launch.return_value.new_context.return_value.new_page.return_value
        page.content.return_value = HTML
        page.url = "https://example.com/"

        with tempfile.TemporaryDirectory() as temp_dir, patch("app.enrichment.sys.platform", "win32"):
            fetcher = HtmlFetcher(Path(temp_dir), 1, 0, 1)
            result = fetcher._fetch_with_browser("https://example.com/")
            fetcher.close()

        playwright.chromium.launch.assert_called_once_with(headless=True, channel="msedge")
        self.assertEqual(result.method, "browser-fallback")

    def test_discovers_ranked_same_domain_links(self):
        links = discover_relevant_links(HTML, "https://example.com/", limit=3)
        self.assertEqual(links[0], "https://example.com/contact-us")
        self.assertIn("https://example.com/book-online", links)
        self.assertNotIn("https://other.example/contact", links)

    def test_extracts_json_ld_and_public_generic_contacts(self):
        data, evidence = extract_public_data(HTML, "https://example.com/")
        self.assertEqual(data["business_name"], "Example Beauty")
        self.assertEqual(data["generic_email"], "info@example.com")
        self.assertEqual(data["phone"], "020 1234 5678")
        self.assertEqual(data["city_or_area"], "London")
        self.assertEqual(evidence["business_name"]["method"], "json-ld")

    def test_extracts_business_from_json_ld_graph(self):
        data, _ = extract_public_data(GRAPH_HTML, "https://dental.example/")
        self.assertEqual(data["business_name"], "Graph Dental")
        self.assertEqual(data["phone"], "0121 000 0000")

    def test_extracts_business_when_json_ld_type_is_a_list(self):
        data, _ = extract_public_data(MULTI_TYPE_HTML, "https://airoptions.co.uk/")

        self.assertEqual(data["business_name"], "Air Options")

    def test_extracts_up_to_three_unique_public_contacts(self):
        html = """
        <a href="mailto:info@example.com">Info</a>
        <a href="mailto:hello@example.com">Hello</a>
        <a href="tel:+44%2020%208050%207969">Call</a>
        <a href="tel:+44%2020%208050%207969">Call again</a>
        <a href="tel:0800%20043%202639">Freephone</a>
        """

        data, _ = extract_public_data(html, "https://example.com/")

        self.assertEqual(data["emails"], ["info@example.com", "hello@example.com"])
        self.assertEqual(data["phones"], ["+44 20 8050 7969", "0800 043 2639"])
        self.assertEqual(data["phone"], "+44 20 8050 7969")

    def test_extracts_named_obfuscated_and_visible_contacts_but_rejects_unrelated_domains(self):
        html = """
        <a href="mailto:studio@example.com">Studio</a>
        <a href="mailto:alex@example.com">Alex</a>
        <a href="mailto:no-reply@example.com">Automated</a>
        <a href="mailto:sales@unrelated.test">Wrong company</a>
        <p>Bookings: work [at] example [dot] com</p>
        <p>Telephone +44 (0)20 7946 0123</p>
        """

        data, _ = extract_public_data(html, "https://example.com/")

        self.assertEqual(data["emails"], ["studio@example.com", "work@example.com", "alex@example.com"])
        self.assertEqual(data["phones"], ["+44 (0)20 7946 0123"])

    @patch.object(HtmlFetcher, "fetch")
    def test_crawls_relevant_links_to_depth_two(self, fetch):
        pages = {
            "https://example.com/": '<a href="/about">About</a>',
            "https://example.com/about": '<a href="/team">Meet the team</a>',
            "https://example.com/team": '<a href="mailto:producer@example.com">Producer</a>',
        }
        fetch.side_effect = lambda url: FetchResult(url, pages[url], False, "http")
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ScraperConfig(
                niche="filmmakers",
                location="London",
                cache_dir=Path(temp_dir),
                browser_fallback=False,
            )
            data, evidence, errors = enrich_public_pages("https://example.com/", config)

        self.assertEqual(data["emails"], ["producer@example.com"])
        self.assertEqual(evidence["generic_email"]["source_url"], "https://example.com/team")
        self.assertEqual(errors, [])
        self.assertEqual(fetch.call_count, 3)

    @patch.object(HtmlFetcher, "fetch_text")
    @patch.object(HtmlFetcher, "fetch")
    def test_deep_crawl_discovers_contact_page_from_sitemap(self, fetch, fetch_text):
        pages = {
            "https://example.com/": "<main>Portfolio</main>",
            "https://example.com/hidden-contact": '<a href="mailto:studio@example.com">Studio</a>',
        }
        documents = {
            "https://example.com/robots.txt": "Sitemap: https://example.com/sitemap.xml",
            "https://example.com/sitemap.xml": """
                <urlset><url><loc>https://example.com/hidden-contact</loc></url>
                <url><loc>https://example.com/privacy</loc></url></urlset>
            """,
        }
        fetch.side_effect = lambda url: FetchResult(url, pages[url], False, "http")
        fetch_text.side_effect = lambda url: FetchResult(url, documents[url], False, "http-document")
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ScraperConfig(
                niche="filmmakers",
                location="London",
                cache_dir=Path(temp_dir),
                browser_fallback=False,
                crawl_mode="deep",
                crawl_page_limit=20,
                crawl_depth=3,
            )
            data, evidence, errors = enrich_public_pages("https://example.com/", config)

        self.assertEqual(data["emails"], ["studio@example.com"])
        self.assertEqual(evidence["generic_email"]["source_url"], "https://example.com/hidden-contact")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(errors, [])

    @patch.object(HtmlFetcher, "fetch")
    def test_adaptive_crawl_reports_progress_and_stops_after_contact_goal(self, fetch):
        pages = {
            "https://example.com/": """
                <a href="/contact">Contact</a><a href="/team">Team</a>
                <a href="/about">About</a><a href="/services">Services</a>
                <a href="mailto:info@example.com">Info</a>
            """,
            "https://example.com/contact": '<a href="mailto:studio@example.com">Studio</a><a href="tel:02070000001">Call</a>',
            "https://example.com/team": '<a href="mailto:sales@example.com">Sales</a>',
            "https://example.com/about": '<a href="tel:02070000002">Call</a>',
            "https://example.com/services": "<p>Should not be needed</p>",
        }
        fetch.side_effect = lambda url: FetchResult(url, pages[url], False, "http")
        progress: list[dict] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ScraperConfig(
                niche="filmmakers",
                location="London",
                cache_dir=Path(temp_dir),
                browser_fallback=False,
                crawl_mode="quick",
                crawl_page_limit=6,
                crawl_depth=2,
            )
            data, _, _ = enrich_public_pages(
                "https://example.com/",
                config,
                progress_callback=progress.append,
            )

        self.assertTrue(data["crawl_stopped_early"])
        self.assertEqual(data["crawl_pages_checked"], 4)
        self.assertEqual(progress[-1]["crawl_pages_checked"], 4)
        self.assertEqual(progress[-1]["crawl_contacts_found"], 5)
        self.assertEqual(fetch.call_count, 4)

    def test_verified_html_business_contact_overrides_false_model_rejection(self):
        enriched = apply_enrichment(
            {"is_valid_lead": False, "website": "https://example.com/", "emails": [], "phones": []},
            {"business_name": "Example Films", "phone": "020 7946 0123", "phones": ["020 7946 0123"]},
            {
                "business_name": {
                    "source_url": "https://example.com/",
                    "method": "json-ld",
                    "value": "Example Films",
                },
                "phone": {
                    "source_url": "https://example.com/",
                    "method": "json-ld",
                    "value": "020 7946 0123",
                },
            },
            [],
        )

        self.assertTrue(enriched["is_valid_lead"])
        self.assertGreater(enriched["lead_score"], 0)

    def test_extracts_equivalent_uk_phone_links_once(self):
        html = """
        <a href="tel:02076242434">Local</a>
        <a href="tel:+442076242434">International</a>
        <a href="tel:+44%20020%207624%202434">Mixed format</a>
        """

        data, _ = extract_public_data(html, "https://example.com/")

        self.assertEqual(data["phones"], ["02076242434"])

    def test_fetcher_retries_server_error_and_then_caches(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, request=request, headers={"content-type": "text/html"})
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/html; charset=utf-8"},
                text=HTML,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            fetcher = HtmlFetcher(
                cache_dir=Path(temp_dir),
                timeout_seconds=1,
                retry_attempts=1,
                cache_ttl_hours=1,
                browser_fallback=False,
                transport=httpx.MockTransport(handler),
            )
            first = fetcher.fetch("https://example.com/")
            second = fetcher.fetch("https://example.com/")
            fetcher.close()

        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(calls, 2)

    def test_html_evidence_overrides_llm_contact_fields_and_rescores(self):
        lead = {
            "is_valid_lead": True,
            "business_name": "Example Beauty",
            "website": "https://example.com/",
            "services": ["Hair"],
            "generic_email": "",
            "phone": "",
            "contact_page": "",
            "booking_page": "",
            "instagram_or_social": "",
            "has_online_booking": False,
        }
        enriched = apply_enrichment(
            lead,
            {"generic_email": "hello@example.com", "contact_page": "https://example.com/contact"},
            {"generic_email": {"url": "https://example.com/contact", "method": "html-link"}},
            [],
        )
        self.assertEqual(enriched["generic_email"], "hello@example.com")
        self.assertEqual(enriched["lead_score"], 3)
        self.assertEqual(enriched["field_evidence"]["generic_email"]["method"], "html-link")
        self.assertEqual(enriched["field_evidence"]["generic_email"]["method"], "html-link")
        self.assertEqual(enriched["field_evidence"]["business_name"]["method"], "llm")


if __name__ == "__main__":
    unittest.main()
