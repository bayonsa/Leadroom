from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.outreach_ai import CampaignBrief, compose_outreach_message

LEAD = {
    "domain": "example-salon.test",
    "business_name": "Example Salon",
    "business_type": "hair salon",
    "city_or_area": "London",
    "services": ["hair colouring"],
    "website": "https://example-salon.test",
}


class OutreachAITests(TestCase):
    def setUp(self):
        self.brief = CampaignBrief(
            base_message="We help {business_name} improve booking follow-up.",
            tone="professional",
            links=("https://agency.example/opt-in",),
            sender_identity="Example Agency",
            opt_out_address="privacy@agency.example",
        )
        self.runtime = {
            "model_provider": "ollama",
            "model_name": "llama3.2:3b",
            "model_endpoint": "http://localhost:11434",
        }

    def test_template_fallback_is_personalized_and_keeps_required_footer(self):
        subject, body, metadata = compose_outreach_message(
            LEAD,
            self.brief,
            self.runtime,
            personalize=False,
        )

        self.assertEqual(subject, "A note for Example Salon")
        self.assertIn("public business website", body)
        self.assertIn("Example Salon improve booking", body)
        self.assertIn("https://agency.example/opt-in", body)
        self.assertIn("privacy@agency.example", body)
        self.assertEqual(metadata["personalized_by"], "template")

    @patch("app.outreach_ai.httpx.post")
    def test_ollama_json_personalization(self, post):
        response = MagicMock()
        response.json.return_value = {
            "message": {
                "content": '{"subject":"Booking follow-up","body":"Hello Example Salon team, a relevant idea."}'
            }
        }
        post.return_value = response

        subject, body, metadata = compose_outreach_message(LEAD, self.brief, self.runtime)

        self.assertEqual(subject, "Booking follow-up")
        self.assertIn("a relevant idea", body)
        self.assertEqual(metadata["personalized_by"], "ai")
        self.assertEqual(post.call_args.kwargs["json"]["format"], "json")
