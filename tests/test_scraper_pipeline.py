import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import ScraperConfig
from app.database import RunRepository
from app.pipeline import run_pipeline
from app.scraper import scrape_business_site


class ScraperPipelineTests(unittest.TestCase):
    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_scraper_passes_json_schema_and_normalizes_result(self, graph_class, fetcher_class, _enrich):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        graph_class.return_value.run.return_value = {
            "content": {
                "is_valid_lead": True,
                "business_name": "Schema Salon",
                "website": "https://schema.example/",
                "services": ["Hair"],
            }
        }
        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        lead = scrape_business_site("https://schema.example/", config)

        graph_config = graph_class.call_args.kwargs["config"]
        self.assertEqual(graph_config["llm"]["format"]["type"], "object")
        self.assertEqual(lead["business_name"], "Schema Salon")
        self.assertGreater(lead["lead_score"], 0)

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_scraper_configures_openai_compatible_model_without_ollama_format(
        self, graph_class, fetcher_class, _enrich
    ):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        graph_class.return_value.run.return_value = {
            "content": {"business_name": "API Salon", "website": "https://api.example/"}
        }
        config = ScraperConfig(
            niche="salons",
            location="London",
            model="oneapi/paid-model",
            ollama_base_url="https://models.example/v1",
            llm_api_key="secret-key",
        )

        scrape_business_site("https://api.example/", config)

        llm = graph_class.call_args.kwargs["config"]["llm"]
        self.assertEqual(llm["model"], "oneapi/paid-model")
        self.assertEqual(llm["base_url"], "https://models.example/v1")
        self.assertEqual(llm["api_key"], "secret-key")
        self.assertNotIn("format", llm)

    @patch("app.scraper.enrich_public_pages", return_value=({}, {}, []))
    @patch("app.scraper.HtmlFetcher")
    @patch("app.scraper.SmartScraperGraph")
    def test_scraper_preserves_schema_validation_errors(self, graph_class, fetcher_class, _enrich):
        fetcher_class.return_value.fetch.return_value.html = "<html></html>"
        graph_class.return_value.run.return_value = {
            "content": {
                "is_valid_lead": True,
                "business_name": "Broken Shape",
                "services": "not-a-list",
            }
        }
        config = ScraperConfig(niche="salons", location="London", delay_seconds=0)

        lead = scrape_business_site("https://broken.example/", config)

        self.assertFalse(lead["is_valid_lead"])
        self.assertTrue(lead["validation_errors"])
        self.assertIn("not-a-list", lead["raw_output"])

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_emits_typed_summary_and_quality_metrics(self, scrape, search):
        search.return_value = [
            {
                "title": "Example Salon",
                "url": "https://example.com/contact",
                "homepage": "https://example.com/",
                "snippet": "London salon",
                "domain": "example.com",
            }
        ]
        scrape.return_value = {
            "is_valid_lead": True,
            "business_name": "Example Salon",
            "website": "https://example.com/",
            "city_or_area": "London",
            "business_type": "Salon",
            "services": ["Hair"],
            "generic_email": "info@example.com",
            "phone": "123",
            "contact_page": "https://example.com/contact",
            "booking_page": "",
            "instagram_or_social": "",
            "has_online_booking": False,
            "website_quality_note": "",
            "lead_score": 0,
            "lead_reason": "",
            "source_url": "",
            "search_title": "",
            "search_snippet": "",
            "domain": "example.com",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=Path(temp_dir) / "test.db",
                delay_seconds=0,
            )
            output = run_pipeline(config)

        self.assertEqual(output["summary"]["clean_lead_count"], 1)
        self.assertEqual(output["summary"]["clean_yield"], 1.0)
        self.assertEqual(output["summary"]["generic_email_coverage"], 1.0)
        self.assertEqual(output["failed_urls"], [])

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_can_cancel_before_scraping_next_domain(self, scrape, search):
        search.return_value = [
            {
                "title": "One",
                "url": "https://one.example/",
                "homepage": "https://one.example/",
                "snippet": "",
                "domain": "one.example",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = run_pipeline(
                ScraperConfig(
                    niche="salons",
                    location="London",
                    output_dir=Path(temp_dir),
                    database_path=Path(temp_dir) / "test.db",
                    delay_seconds=0,
                ),
                cancel_check=lambda: True,
            )
        scrape.assert_not_called()
        self.assertTrue(output["summary"]["cancelled"])

    @patch("app.pipeline.save_run", side_effect=OSError("disk full"))
    @patch("app.pipeline.search_business_sites", return_value=[])
    def test_export_disk_error_marks_run_failed(self, _search, _save):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
            )
            with self.assertRaisesRegex(OSError, "disk full"):
                run_pipeline(config)
            repository = RunRepository(database_path)
            try:
                self.assertEqual(repository.list_runs()[0]["status"], "failed")
            finally:
                repository.engine.dispose()

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_pipeline_resume_keeps_completed_leads_and_processes_pending(self, scrape, search):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
                reuse_existing_leads=False,
            )
            repository = RunRepository(database_path)
            run_id = repository.create_run(config)
            sites = [
                {
                    "title": "One",
                    "url": "https://one-example.com/",
                    "homepage": "https://one-example.com/",
                    "snippet": "",
                    "domain": "one-example.com",
                },
                {
                    "title": "Two",
                    "url": "https://two-example.com/",
                    "homepage": "https://two-example.com/",
                    "snippet": "",
                    "domain": "two-example.com",
                },
            ]
            repository.add_candidates(run_id, sites)
            first_id = repository.claim(run_id, "one-example.com")
            first_lead = self._lead("One", "https://one-example.com/", "one-example.com")
            repository.complete(first_id, first_lead)
            repository.engine.dispose()
            scrape.return_value = self._lead("Two", "https://two-example.com/", "two-example.com")

            output = run_pipeline(config, resume_run_id=run_id)

        search.assert_not_called()
        scrape.assert_called_once()
        self.assertEqual(output["summary"]["clean_lead_count"], 2)

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_reuse_mode_uses_cached_lead_without_scraping(self, scrape, search):
        search.return_value = [
            {
                "title": "Existing",
                "url": "https://existing.co.uk/",
                "homepage": "https://existing.co.uk/",
                "snippet": "London salon",
                "domain": "existing.co.uk",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
                discovery_mode="reuse",
            )
            repository = RunRepository(database_path)
            old_run = repository.create_run(config)
            repository.add_candidates(old_run, search.return_value)
            candidate_id = repository.claim(old_run, "existing.co.uk")
            repository.complete(
                candidate_id,
                self._lead("Cached", "https://existing.co.uk/", "existing.co.uk"),
            )
            repository.engine.dispose()

            output = run_pipeline(config)

        scrape.assert_not_called()
        self.assertEqual(output["clean_leads"][0]["business_name"], "Cached")

    @patch("app.pipeline.search_business_sites")
    @patch("app.pipeline.scrape_business_site")
    def test_refresh_mode_scrapes_previously_completed_domain(self, scrape, search):
        site = {
            "title": "Existing",
            "url": "https://existing.co.uk/",
            "homepage": "https://existing.co.uk/",
            "snippet": "London salon",
            "domain": "existing.co.uk",
        }
        search.return_value = [site]
        scrape.return_value = self._lead("Refreshed", site["homepage"], site["domain"])
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            cached_config = ScraperConfig(
                niche="salons",
                location="London",
                database_path=database_path,
            )
            repository = RunRepository(database_path)
            old_run = repository.create_run(cached_config)
            repository.add_candidates(old_run, [site])
            candidate_id = repository.claim(old_run, site["domain"])
            repository.complete(
                candidate_id,
                self._lead("Cached", site["homepage"], site["domain"]),
            )
            repository.engine.dispose()
            config = ScraperConfig(
                niche="salons",
                location="London",
                output_dir=Path(temp_dir),
                database_path=database_path,
                delay_seconds=0,
                discovery_mode="refresh",
            )

            output = run_pipeline(config)

        scrape.assert_called_once()
        self.assertEqual(output["clean_leads"][0]["business_name"], "Refreshed")

    @staticmethod
    def _lead(name: str, website: str, domain: str) -> dict:
        return {
            "is_valid_lead": True,
            "business_name": name,
            "website": website,
            "city_or_area": "London",
            "business_type": "Salon",
            "services": ["Hair"],
            "generic_email": f"info@{domain}",
            "phone": "123",
            "contact_page": f"{website}contact",
            "booking_page": "",
            "instagram_or_social": "",
            "has_online_booking": False,
            "website_quality_note": "",
            "lead_score": 8,
            "lead_reason": "Verified",
            "source_url": website,
            "search_title": name,
            "search_snippet": "",
            "domain": domain,
            "field_evidence": {},
            "enrichment_errors": [],
        }


if __name__ == "__main__":
    unittest.main()
