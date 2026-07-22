import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.config import ScraperConfig
from app.database import RunRepository

SITE = {
    "title": "Example Salon",
    "url": "https://example.com/contact",
    "homepage": "https://example.com/",
    "snippet": "London salon",
    "domain": "example.com",
}


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "lead_scraper.db"
        self.repository = RunRepository(self.database_path)
        self.config = ScraperConfig(
            niche="salons",
            location="London",
            database_path=self.database_path,
            delay_seconds=0,
        )

    def tearDown(self):
        self.repository.engine.dispose()
        self.temp_dir.cleanup()

    def test_run_config_and_candidates_survive_new_repository(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE, SITE])
        self.repository.engine.dispose()

        reopened = RunRepository(self.database_path)
        try:
            loaded = reopened.load_config(run_id)
            candidates = reopened.list_candidates(run_id)
        finally:
            reopened.engine.dispose()

        self.assertEqual(loaded.niche, "salons")
        self.assertEqual(len(candidates), 1)

    def test_candidate_crawl_progress_is_persisted_while_processing(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        candidate_id = self.repository.claim(run_id, SITE["domain"])

        self.repository.update_candidate_crawl(
            candidate_id,
            {
                "crawl_mode": "deep",
                "crawl_pages_checked": 7,
                "crawl_page_limit": 20,
                "crawl_current_url": "https://example.com/team",
                "crawl_contacts_found": 3,
                "ignored": "not persisted",
            },
        )
        candidate = self.repository.list_candidates(run_id)[0]

        self.assertEqual(candidate["crawl_mode"], "deep")
        self.assertEqual(candidate["crawl_pages_checked"], 7)
        self.assertEqual(candidate["crawl_page_limit"], 20)
        self.assertEqual(candidate["crawl_contacts_found"], 3)
        self.assertNotIn("ignored", candidate)

    def test_old_windows_bridge_text_is_repaired_when_displayed(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(
            run_id,
            [{**SITE, "snippet": "office graphic design | 90â€“92 Pentonville Road"}],
        )

        candidate = self.repository.list_candidates(run_id)[0]

        self.assertEqual(candidate["snippet"], "office graphic design | 90–92 Pentonville Road")

    def test_500_candidate_detail_read_stays_within_local_budget(self):
        run_id = self.repository.create_run(self.config)
        sites = [
            {**SITE, "domain": f"candidate-{index}.test", "url": f"https://candidate-{index}.test/"}
            for index in range(500)
        ]
        self.repository.add_candidates(run_id, sites)

        started = time.perf_counter()
        candidates = self.repository.list_candidates(run_id)
        elapsed = time.perf_counter() - started

        self.assertEqual(len(candidates), 500)
        self.assertLess(elapsed, 0.5)

    def test_candidate_completion_is_idempotently_stored(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        candidate_id = self.repository.claim(run_id, "example.com")
        self.repository.complete(candidate_id, {"business_name": "Example", "lead_score": 8})
        status = self.repository.run_status(run_id)
        self.assertEqual(status["counts"], {"completed": 1})

        with self.assertRaisesRegex(ValueError, "Cannot claim"):
            self.repository.claim(run_id, "example.com")

        updated = self.repository.update_lead(run_id, "example.com", {"business_name": "Edited"})
        self.assertEqual(updated["business_name"], "Edited")
        self.assertEqual(self.repository.load_leads(run_id)[0]["business_name"], "Edited")

    def test_manual_contact_edit_invalidates_old_evidence_and_recomputes_score(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        candidate_id = self.repository.claim(run_id, "example.com")
        self.repository.complete(
            candidate_id,
            {
                "is_valid_lead": True,
                "business_name": "Example",
                "domain": "example.com",
                "services": ["Hair"],
                "generic_email": "info@example.com",
                "lead_score": 9,
                "field_evidence": {
                    "generic_email": {
                        "value": "info@example.com",
                        "source_url": SITE["url"],
                        "method": "html_mailto",
                    }
                },
            },
        )

        updated = self.repository.update_lead(run_id, "example.com", {"generic_email": "hello@example.com"})

        self.assertEqual(updated["field_evidence"]["generic_email"]["method"], "manual")
        self.assertEqual(updated["field_evidence"]["generic_email"]["source_url"], "")
        self.assertLess(updated["lead_score"], 9)

    def test_app_secrets_are_not_stored_as_plaintext(self):
        self.repository.update_app_settings(
            {
                "llm_api_key": "model-secret",
                "smtp_password": "mail-secret",
                "email_accounts": json.dumps([{"id": "sales", "password": "account-secret"}]),
            }
        )

        connection = sqlite3.connect(self.database_path)
        try:
            rows = dict(
                connection.execute(
                    "SELECT key, value FROM app_settings WHERE key IN ('llm_api_key', 'smtp_password', 'email_accounts')"
                )
            )
        finally:
            connection.close()

        self.assertNotEqual(rows["llm_api_key"], "model-secret")
        self.assertNotEqual(rows["smtp_password"], "mail-secret")
        self.assertNotIn("account-secret", rows["email_accounts"])
        self.assertEqual(self.repository.app_settings()["llm_api_key"], "model-secret")
        self.assertIn("account-secret", self.repository.app_settings()["email_accounts"])

    def test_candidate_can_only_be_claimed_by_one_worker(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        barrier = threading.Barrier(2)
        outcomes = []

        def claim():
            repository = RunRepository(self.database_path)
            try:
                barrier.wait()
                outcomes.append(("claimed", repository.claim(run_id, "example.com")))
            except ValueError:
                outcomes.append(("rejected", None))
            finally:
                repository.engine.dispose()

        workers = [threading.Thread(target=claim) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

        self.assertEqual([result[0] for result in outcomes].count("claimed"), 1)
        self.assertEqual([result[0] for result in outcomes].count("rejected"), 1)

    def test_failed_or_processing_candidates_are_recovered_on_resume(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(
            run_id,
            [SITE, {**SITE, "domain": "two.example", "url": "https://two.example/"}],
        )
        first_id = self.repository.claim(run_id, "example.com")
        self.repository.fail(first_id, "timeout")
        self.repository.claim(run_id, "two.example")

        recovered = self.repository.recover_for_resume(run_id)

        self.assertEqual(recovered, 2)
        self.assertEqual(self.repository.run_status(run_id)["counts"], {"queued": 2})

    def test_illegal_state_transition_is_rejected(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        candidate_id = self.repository.claim(run_id, "example.com")
        self.repository.complete(candidate_id, {"lead_score": 1})
        with self.assertRaisesRegex(ValueError, "Illegal candidate transition"):
            self.repository.fail(candidate_id, "too late")

    def test_completed_lead_can_be_reused_across_runs(self):
        first_run = self.repository.create_run(self.config)
        self.repository.add_candidates(first_run, [SITE])
        candidate_id = self.repository.claim(first_run, "example.com")
        self.repository.complete(candidate_id, {"business_name": "Cached", "lead_score": 8})

        cached = self.repository.find_cached_lead("example.com", exclude_run_id="another-run")

        self.assertEqual(cached["business_name"], "Cached")

    def test_repository_merges_contacts_and_tracks_source_runs(self):
        first_run = self.repository.create_run(self.config)
        self.repository.add_candidates(
            first_run,
            [{**SITE, "source": "hybrid", "sources": ["local", "web"]}],
        )
        first_candidate = self.repository.claim(first_run, "example.com")
        self.repository.complete(
            first_candidate,
            {
                "business_name": "Example",
                "domain": "example.com",
                "generic_email": "info@example.com",
                "emails": ["info@example.com"],
                "phone": "tel:+44%2020%208050%207969",
                "lead_score": 8,
            },
        )
        second_run = self.repository.create_run(self.config)
        self.repository.add_candidates(second_run, [SITE])
        second_candidate = self.repository.claim(second_run, "example.com")
        self.repository.complete(
            second_candidate,
            {
                "business_name": "Example Ltd",
                "domain": "example.com",
                "generic_email": "hello@example.com",
                "emails": ["hello@example.com"],
                "phone": "0800 043 2639",
                "lead_score": 9,
            },
        )

        first = self.repository.import_repository_leads(first_run, ["example.com"])
        second = self.repository.import_repository_leads(second_run, ["example.com"])
        repeated = self.repository.import_repository_leads(second_run, ["example.com"])
        saved = self.repository.list_repository_leads()[0]

        self.assertEqual(first, {"added": 1, "updated": 0, "skipped": 0, "total": 1})
        self.assertEqual(second, {"added": 0, "updated": 1, "skipped": 0, "total": 1})
        self.assertEqual(repeated, {"added": 0, "updated": 1, "skipped": 0, "total": 1})
        self.assertEqual(saved["emails"], ["info@example.com", "hello@example.com"])
        self.assertEqual(saved["phones"], ["+44 20 8050 7969", "0800 043 2639"])
        self.assertEqual(saved["source_run_ids"], [first_run, second_run])
        self.assertEqual(saved["niches"], ["salons"])
        self.assertEqual(saved["locations"], ["London"])
        self.assertEqual(saved["sources"], ["local", "web"])

        self.repository.update_repository_lead("example.com", {"niches": []})
        self.assertEqual(self.repository.list_repository_leads()[0]["niches"], ["salons"])
        edited = self.repository.update_repository_lead(
            "example.com", {"business_name": "Edited Example", "niches": ["dental clinics"]}
        )
        self.assertEqual(edited["business_name"], "Edited Example")
        self.assertEqual(self.repository.list_repository_leads()[0]["niches"], ["dental clinics"])

        merged = self.repository.merge_repository_collections(["dental clinics"], "healthcare providers")
        self.assertEqual(merged["updated_leads"], 1)
        self.assertEqual(self.repository.list_repository_leads()[0]["niches"], ["healthcare providers"])
        removed_collection = self.repository.delete_repository_collection("healthcare providers")
        self.assertEqual(removed_collection["updated_leads"], 1)
        self.assertEqual(self.repository.list_repository_leads()[0]["niches"], ["Uncategorised"])

        self.assertEqual(self.repository.delete_repository_lead("example.com")["status"], "deleted")
        self.assertEqual(self.repository.list_repository_leads(), [])

    def test_repository_read_deduplicates_equivalent_uk_phone_formats(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        candidate_id = self.repository.claim(run_id, "example.com")
        self.repository.complete(
            candidate_id,
            {
                "business_name": "Example",
                "domain": "example.com",
                "phones": ["02076242434", "+442076242434", "+44 020 7624 2434"],
                "lead_score": 8,
            },
        )

        self.repository.import_repository_leads(run_id, ["example.com"])

        self.assertEqual(self.repository.load_leads(run_id)[0]["phones"], ["02076242434"])
        self.assertEqual(self.repository.list_repository_leads()[0]["phones"], ["02076242434"])

    def test_repository_skips_completed_results_without_public_contacts(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        candidate_id = self.repository.claim(run_id, "example.com")
        self.repository.complete(
            candidate_id,
            {
                "is_valid_lead": True,
                "business_name": "Example Films",
                "domain": "example.com",
                "lead_score": 2,
            },
        )

        result = self.repository.import_repository_leads(run_id, ["example.com"])

        self.assertEqual(result, {"added": 0, "updated": 0, "skipped": 1, "total": 0})
        self.assertEqual(self.repository.list_repository_leads(), [])

    def test_market_history_is_scoped_and_counts_unique_domains(self):
        first_run = self.repository.create_run(self.config)
        self.repository.add_candidates(first_run, [SITE])
        candidate_id = self.repository.claim(first_run, "example.com")
        self.repository.complete(candidate_id, {"business_name": "Cached", "lead_score": 8})
        second_run = self.repository.create_run(self.config)
        self.repository.add_candidates(second_run, [SITE])
        other_market = self.repository.create_run(
            ScraperConfig(niche="salons", location="Manchester", database_path=self.database_path)
        )
        self.repository.add_candidates(
            other_market,
            [{**SITE, "domain": "manchester.example", "url": "https://manchester.example/"}],
        )

        seen = self.repository.seen_domains("  SALONS ", "london")
        history = self.repository.market_history("salons", "London")

        self.assertEqual(seen, {"example.com"})
        self.assertEqual(
            history,
            {"previous_runs": 2, "seen_domains": 1, "completed_leads": 1},
        )

    def test_app_settings_survive_repository_reopen(self):
        self.repository.update_app_settings(
            {
                "workspace_name": "Northstar",
                "blocked_domains": '["example-directory.com"]',
            }
        )
        self.repository.engine.dispose()

        reopened = RunRepository(self.database_path)
        try:
            settings = reopened.app_settings()
        finally:
            reopened.engine.dispose()

        self.assertEqual(settings["workspace_name"], "Northstar")
        self.assertEqual(settings["blocked_domains"], '["example-directory.com"]')

    def test_discovery_summary_is_persisted_with_run(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(
            run_id,
            [SITE],
            {"mode": "new_only", "previously_seen_filtered": 3, "pages_searched": 10},
        )

        discovery = self.repository.run_status(run_id)["discovery"]

        self.assertEqual(discovery["mode"], "new_only")
        self.assertEqual(discovery["count"], 1)
        self.assertEqual(discovery["previously_seen_filtered"], 3)

    def test_empty_search_finishes_and_stale_search_is_stopped(self):
        empty_run = self.repository.create_run(self.config)
        self.repository.add_candidates(empty_run, [])
        stale_run = self.repository.create_run(self.config)

        stopped = self.repository.stop_stale_searches(stale_seconds=0)

        self.assertEqual(self.repository.run_status(empty_run)["status"], "completed")
        self.assertEqual(stopped, 1)
        self.assertEqual(self.repository.run_status(stale_run)["status"], "stopped")

    def test_integrity_check_and_backup(self):
        run_id = self.repository.create_run(self.config)
        self.repository.add_candidates(run_id, [SITE])
        backup_path = Path(self.temp_dir.name) / "backup" / "lead_scraper.db"

        self.assertEqual(self.repository.integrity_check(), "ok")
        self.repository.backup_to(backup_path)

        backup = RunRepository(backup_path)
        try:
            self.assertEqual(backup.run_status(run_id)["counts"], {"queued": 1})
        finally:
            backup.engine.dispose()


if __name__ == "__main__":
    unittest.main()
