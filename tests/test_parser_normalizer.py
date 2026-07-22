import unittest

from app.normalizer import clean_leads, normalize_lead, normalize_phone
from app.parser import extract_json_from_text, parse_model_output


class ParserNormalizerTests(unittest.TestCase):
    def test_extracts_fenced_json(self):
        parsed = extract_json_from_text('Thinking...\n```json\n{"ok": true}\n```')
        self.assertEqual(parsed, {"ok": True})

    def test_parse_content_dict_without_json_loads_error(self):
        parsed, _ = parse_model_output({"content": {"business_name": "Looks London"}})
        self.assertEqual(parsed["business_name"], "Looks London")

    def test_normalizes_json_ld_business(self):
        lead = normalize_lead(
            {
                "@type": "WebPage",
                "name": "Hari's Hairdressers",
                "url": "https://harissalon.com/",
                "telephone": "+44 20 7349 8722",
                "email": "info@harissalon.com",
                "sameAs": ["https://www.instagram.com/harishair/"],
                "address": {"addressLocality": "London"},
            },
            source_url="https://harissalon.com/",
        )
        self.assertTrue(lead["is_valid_lead"])
        self.assertEqual(lead["business_name"], "Hari's Hairdressers")
        self.assertEqual(lead["generic_email"], "info@harissalon.com")

    def test_clean_keeps_normalized_real_lead(self):
        lead = normalize_lead(
            {
                "title": "Beauty Club London",
                "url": "https://www.beautyclublondon.co.uk/",
                "phone": "020 7946 0102",
            }
        )
        clean = clean_leads([lead])
        self.assertEqual(len(clean), 1)

    def test_model_contacts_must_match_business_domain_and_na_urls_are_empty(self):
        lead = normalize_lead(
            {
                "business_name": "Example Films",
                "website": "https://example.com/",
                "emails": ["sales@unrelated.test", "studio@example.com"],
                "contact_page": "N/A",
                "booking_page": "NA",
            },
            source_url="https://example.com/",
        )

        self.assertEqual(lead["emails"], ["studio@example.com"])
        self.assertEqual(lead["contact_page"], "")
        self.assertEqual(lead["booking_page"], "")
        self.assertFalse(lead["has_online_booking"])

    def test_relative_contact_links_become_absolute(self):
        lead = normalize_lead(
            {
                "business_name": "Figaro London",
                "website": "https://figarolondon.uk/",
                "contact_page": "/contact-us/",
            },
            source_url="https://figarolondon.uk/",
        )
        self.assertEqual(lead["contact_page"], "https://figarolondon.uk/contact-us/")

    def test_string_false_does_not_become_a_valid_lead(self):
        lead = normalize_lead(
            {
                "is_valid_lead": "false",
                "business_name": "Directory Result",
                "website": "https://example.com/",
            },
            source_url="https://example.com/",
        )
        self.assertFalse(lead["is_valid_lead"])
        self.assertEqual(lead["lead_score"], 0)

    def test_llm_score_is_ignored_in_favour_of_evidence(self):
        lead = normalize_lead(
            {
                "is_valid_lead": True,
                "business_name": "Sparse Salon",
                "website": "https://example.com/",
                "lead_score": 10,
            },
            source_url="https://example.com/",
        )
        self.assertEqual(lead["lead_score"], 1)

    def test_percent_encoded_phone_is_decoded_and_contact_lists_are_deduplicated(self):
        lead = normalize_lead(
            {
                "business_name": "J Sons and Co.",
                "website": "https://jsonsco.com/",
                "emails": ["info@jsonsco.com", "info@jsonsco.com", "hello@jsonsco.com"],
                "phones": ["tel:+44%2020%208050%207969", "+44 20 8050 7969"],
            },
            source_url="https://jsonsco.com/",
        )

        self.assertEqual(normalize_phone("tel:+44%2020%208050%207969"), "+44 20 8050 7969")
        self.assertEqual(lead["emails"], ["info@jsonsco.com", "hello@jsonsco.com"])
        self.assertEqual(lead["phones"], ["+44 20 8050 7969"])
        self.assertEqual(lead["phone"], "+44 20 8050 7969")

    def test_uk_national_and_international_phone_forms_are_deduplicated(self):
        lead = normalize_lead(
            {
                "business_name": "London Office",
                "website": "https://example.com/",
                "phones": [
                    "02076242434",
                    "+442076242434",
                    "+44 020 7624 2434",
                    "+447700100779",
                    "02075897792",
                    "020 7589 7792",
                ],
            },
            source_url="https://example.com/",
        )

        self.assertEqual(
            lead["phones"],
            ["02076242434", "+447700100779", "02075897792"],
        )
        self.assertEqual(lead["phone"], "02076242434")


if __name__ == "__main__":
    unittest.main()
