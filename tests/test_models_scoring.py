import unittest

from pydantic import ValidationError

from app.models import Lead, LeadExtraction
from app.scoring import explain_score, score_lead


class ModelsScoringTests(unittest.TestCase):
    def test_extraction_schema_parses_false_string(self):
        extraction = LeadExtraction.model_validate({"is_valid_lead": "false"})
        self.assertIs(extraction.is_valid_lead, False)

    def test_lead_rejects_scores_outside_range(self):
        with self.assertRaises(ValidationError):
            Lead(lead_score=11)

    def test_complete_opportunity_scores_ten(self):
        lead = {
            "is_valid_lead": True,
            "business_name": "Example Salon",
            "website": "https://example.com/",
            "city_or_area": "London",
            "services": ["Hair"],
            "generic_email": "info@example.com",
            "phone": "+44 20 0000 0000",
            "contact_page": "https://example.com/contact",
            "instagram_or_social": "https://instagram.com/example",
            "has_online_booking": False,
            "field_evidence": {
                "business_name": {
                    "value": "Example Salon",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
                "website": {
                    "value": "https://example.com/",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
                "city_or_area": {
                    "value": "London",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
                "generic_email": {
                    "value": "info@example.com",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
                "phone": {
                    "value": "+44 20 0000 0000",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
                "contact_page": {
                    "value": "https://example.com/contact",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
                "instagram_or_social": {
                    "value": "https://instagram.com/example",
                    "source_url": "https://example.com/contact",
                    "method": "html",
                },
            },
        }
        self.assertEqual(score_lead(lead), 10)
        self.assertIn("no verified online booking", explain_score(lead))

    def test_invalid_lead_scores_zero(self):
        self.assertEqual(score_lead({"is_valid_lead": False, "website": "https://example.com"}), 0)


if __name__ == "__main__":
    unittest.main()
