import tempfile
import unittest
from pathlib import Path

from app.compliance import ComplianceService
from app.config import ScraperConfig
from app.database import RunRepository

SITE = {
    "title": "Example Salon",
    "url": "https://example-salon.test/contact",
    "homepage": "https://example-salon.test/",
    "snippet": "London salon",
    "domain": "example-salon.test",
}


class ComplianceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "compliance.db"
        repository = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        self.run_id = repository.create_run(config)
        repository.add_candidates(self.run_id, [SITE])
        candidate_id = repository.claim(self.run_id, SITE["domain"])
        repository.complete(candidate_id, self._lead("hello@example-salon.test"))
        repository.engine.dispose()
        self.service = ComplianceService(self.database_path)

    def tearDown(self):
        self.service.close()
        self.temp_dir.cleanup()

    def test_requires_generic_verified_high_quality_lead(self):
        repository = self.service.repository
        repository.update_lead(self.run_id, SITE["domain"], {"generic_email": "owner@example-salon.test"})

        with self.assertRaisesRegex(ValueError, "generic business"):
            self._create_draft()

    def test_blocks_unknown_subscriber_without_consent(self):
        with self.assertRaisesRegex(ValueError, "Consent is required"):
            self._create_draft(subscriber_type="unknown")

    def test_draft_requires_human_approval_before_export(self):
        draft = self._create_draft()
        self.assertEqual(draft["status"], "draft")
        self.assertIn("public business website", draft["body"])
        with self.assertRaisesRegex(ValueError, "approved"):
            self.service.export_approved([draft["id"]])

        with self.assertRaisesRegex(ValueError, "Corporate subscriber"):
            self.service.approve_draft(draft["id"], "Reviewer", False, True)
        approved = self.service.approve_draft(draft["id"], "Reviewer", True, True)
        exported = self.service.export_approved([draft["id"]])

        self.assertEqual(approved["approved_by"], "Reviewer")
        self.assertEqual(exported[0]["status"], "exported")

    def test_suppression_is_minimized_and_blocks_draft(self):
        suppression = self.service.add_suppression("hello@example-salon.test", "email", "Recipient opted out")
        self.assertNotIn("value", suppression)
        self.assertEqual(suppression["display_hint"], "he***@example-salon.test")

        with self.assertRaisesRegex(ValueError, "suppression"):
            self._create_draft()

    def test_new_suppression_blocks_pending_approval(self):
        draft = self._create_draft()
        self.service.add_suppression(SITE["domain"], "domain", "Business objected")

        self.assertEqual(self.service.list_drafts()[0]["status"], "blocked")
        with self.assertRaisesRegex(ValueError, "blocked"):
            self.service.approve_draft(draft["id"], "Reviewer", True, True)

    def test_non_corporate_consent_must_be_documented(self):
        with self.assertRaisesRegex(ValueError, "document consent"):
            self.service.create_draft(
                run_id=self.run_id,
                domain=SITE["domain"],
                subscriber_type="sole_trader",
                lawful_basis_note="A note without the required evidence reference.",
                sender_identity="Example Agency Ltd",
                opt_out_address="privacy@example-agency.test",
                offer_summary="We provide appointment workflow reviews for independent salons.",
                consent_confirmed=True,
            )

    def test_duplicate_recipient_and_batch_limit_are_blocked(self):
        self._create_draft()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self._create_draft()
        with self.assertRaisesRegex(ValueError, "1-25"):
            self.service.export_approved([str(index) for index in range(26)])

    def test_bulk_preflight_create_and_approval(self):
        preflight = self.service.preflight_run(self.run_id)
        self.assertEqual(preflight["eligible"], 1)
        self.assertEqual(preflight["results"][0]["domain"], SITE["domain"])

        created = self.service.create_drafts_bulk(
            domains=[SITE["domain"]],
            run_id=self.run_id,
            subscriber_type="corporate",
            lawful_basis_note="Legitimate interests assessment reference LIA-001.",
            sender_identity="Example Agency Ltd",
            opt_out_address="privacy@example-agency.test",
            offer_summary="We provide appointment workflow reviews for independent salons.",
            consent_confirmed=False,
        )
        approved = self.service.approve_drafts_bulk([created["drafts"][0]["id"]], "Bulk Reviewer", True, True)

        self.assertEqual(created["created"], 1)
        self.assertEqual(approved["approved"], 1)
        self.assertEqual(approved["drafts"][0]["approved_by"], "Bulk Reviewer")

    def test_approved_draft_can_be_queued_sent_and_audited(self):
        draft = self._create_draft()
        self.service.approve_draft(draft["id"], "Reviewer", True, True)

        queued = self.service.queue_deliveries([draft["id"]])
        payload = self.service.delivery_payload(draft["id"])
        self.service.mark_delivery_started(draft["id"])
        sent = self.service.complete_delivery(
            draft["id"],
            "sent",
            provider_message_id="<message@example.test>",
        )

        self.assertEqual(queued, [draft["id"]])
        self.assertEqual(payload["recipient"], "hello@example-salon.test")
        self.assertEqual(sent["status"], "sent")
        listed = self.service.list_drafts()[0]
        self.assertEqual(listed["delivery_status"], "sent")
        self.assertEqual(listed["provider_message_id"], "<message@example.test>")

    def test_failed_delivery_returns_draft_to_approved_for_retry(self):
        draft = self._create_draft()
        self.service.approve_draft(draft["id"], "Reviewer", True, True)
        self.service.queue_deliveries([draft["id"]])
        self.service.mark_delivery_started(draft["id"])

        failed = self.service.complete_delivery(draft["id"], "failed", error="Mailbox unavailable")

        self.assertEqual(failed["status"], "approved")
        listed = self.service.list_drafts()[0]
        self.assertEqual(listed["delivery_status"], "failed")
        self.assertEqual(listed["delivery_error"], "Mailbox unavailable")

    def test_restart_releases_queue_entries_that_never_started_smtp(self):
        draft = self._create_draft()
        self.service.approve_draft(draft["id"], "Reviewer", True, True)
        self.service.queue_deliveries([draft["id"]])

        recovered = self.service.recover_interrupted_deliveries()

        self.assertEqual(recovered, 1)
        listed = self.service.list_drafts()[0]
        self.assertEqual(listed["status"], "approved")
        self.assertEqual(listed["delivery_status"], "released")
        self.assertEqual(self.service.queue_deliveries([draft["id"]]), [draft["id"]])

    def test_restart_quarantines_delivery_after_smtp_started(self):
        draft = self._create_draft()
        self.service.approve_draft(draft["id"], "Reviewer", True, True)
        self.service.queue_deliveries([draft["id"]])
        self.service.mark_delivery_started(draft["id"], "<stable@example.test>")

        self.service.recover_interrupted_deliveries()

        listed = self.service.list_drafts()[0]
        self.assertEqual(listed["status"], "uncertain")
        self.assertEqual(listed["delivery_status"], "uncertain")
        self.assertEqual(listed["provider_message_id"], "<stable@example.test>")

    def test_deletion_removes_lead_but_preserves_suppression(self):
        result = self.service.delete_lead_data(self.run_id, SITE["domain"], "Data subject deletion request")

        self.assertTrue(result["suppression_preserved"])
        self.assertEqual(self.service.repository.load_leads(self.run_id), [])
        self.assertEqual(len(self.service.list_suppressions()), 2)

    def test_deletion_removes_every_copy_of_the_same_domain(self):
        second_run = self.service.repository.create_run(self.service.repository.load_config(self.run_id))
        self.service.repository.add_candidates(second_run, [SITE])
        candidate_id = self.service.repository.claim(second_run, SITE["domain"])
        self.service.repository.complete(candidate_id, self._lead("privacy@example-salon.test"))
        self.service.repository.import_repository_leads(second_run, [SITE["domain"]])

        self.service.delete_lead_data(self.run_id, SITE["domain"], "Data subject deletion request")

        self.assertEqual(self.service.repository.load_leads(self.run_id), [])
        self.assertEqual(self.service.repository.load_leads(second_run), [])
        self.assertEqual(self.service.repository.list_repository_leads(), [])
        self.assertEqual(len(self.service.list_suppressions()), 3)

    def _create_draft(self, subscriber_type: str = "corporate"):
        return self.service.create_draft(
            run_id=self.run_id,
            domain=SITE["domain"],
            subscriber_type=subscriber_type,
            lawful_basis_note="Legitimate interests assessment reference LIA-001.",
            sender_identity="Example Agency Ltd",
            opt_out_address="privacy@example-agency.test",
            offer_summary="We provide appointment workflow reviews for independent salons.",
        )

    @staticmethod
    def _lead(email: str) -> dict:
        return {
            "is_valid_lead": True,
            "business_name": "Example Salon",
            "website": SITE["homepage"],
            "city_or_area": "London",
            "business_type": "Salon",
            "services": ["Hair styling"],
            "generic_email": email,
            "phone": "020 1234 5678",
            "contact_page": SITE["url"],
            "booking_page": "",
            "instagram_or_social": "",
            "has_online_booking": False,
            "website_quality_note": "",
            "lead_score": 9,
            "lead_reason": "Verified public business contact",
            "domain": SITE["domain"],
            "field_evidence": {
                "generic_email": {"value": email, "source_url": SITE["url"], "method": "html_mailto"}
            },
            "enrichment_errors": [],
        }


if __name__ == "__main__":
    unittest.main()
