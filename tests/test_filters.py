import unittest

from app.filters import (
    domain_key,
    homepage_url,
    is_good_business_url,
    is_relevant_to_location,
    is_relevant_to_niche,
)


class FilterTests(unittest.TestCase):
    def test_domain_key(self):
        self.assertEqual(domain_key("https://www.beautyclublondon.co.uk/path"), "beautyclublondon.co.uk")

    def test_homepage_url(self):
        self.assertEqual(homepage_url("https://example.com/a/b?x=1"), "https://example.com/")

    def test_blocks_platforms_and_directories(self):
        self.assertFalse(is_good_business_url("https://www.fresha.com/en-GB", "Book salons"))
        self.assertFalse(
            is_good_business_url(
                "https://d7leadfinder.com/app/view-leads/1",
                "List of all Hair Salons",
            )
        )
        self.assertFalse(
            is_good_business_url(
                "https://www.whatclinic.com/beauty-salons/uk/london",
                "Beauty Salons in London - Check Prices & Reviews",
            )
        )
        self.assertFalse(is_good_business_url("https://www.tiktok.com/discover/hair-salon", "Hair salon"))
        self.assertFalse(
            is_good_business_url("https://en.wikipedia.org/wiki/Graphic_design", "Graphic design")
        )
        self.assertFalse(is_good_business_url("https://portfolio.github.io/", "Graphic designer London"))
        self.assertFalse(
            is_good_business_url("https://www.paris.edu/programs/graphic-design", "Graphic design")
        )
        self.assertFalse(
            is_good_business_url(
                "https://find-and-update.company-information.service.gov.uk/company/123",
                "Company information",
            )
        )
        self.assertFalse(
            is_good_business_url("https://www.123rf.com/stock-photo/design.html", "Stock photos")
        )
        self.assertFalse(
            is_good_business_url(
                "https://example.com/graphic-design-agencies",
                "Top 5 Graphic Design Agencies in London",
            )
        )
        self.assertTrue(
            is_good_business_url(
                "https://en.wikipedia.org/wiki/Graphic_design",
                "Graphic design",
                {"custom-directory.example"},
            )
        )

    def test_allows_business_site(self):
        self.assertTrue(is_good_business_url("https://www.beautyclublondon.co.uk/", "Beauty Club London"))

    def test_niche_relevance_rejects_query_drift(self):
        self.assertFalse(
            is_relevant_to_niche(
                "https://theyardleyclinic.co.uk/",
                "IV Vitamin Drips Birmingham",
                "IV therapy and infusions",
                "dental clinics",
            )
        )
        self.assertFalse(
            is_relevant_to_niche(
                "https://unrelated.example/",
                "Unrelated products",
                "Office graphic design services in London",
                "office graphic design",
            )
        )
        self.assertTrue(
            is_relevant_to_niche(
                "https://edgbastonsmile.co.uk/",
                "Edgbaston Smile Clinic | Dentist Birmingham",
                "General and cosmetic dental care",
                "dental clinics",
            )
        )
        self.assertFalse(
            is_relevant_to_niche(
                "https://fengshuibracelets.net/",
                "Feng Shui Bracelets",
                "A beautiful design delivered to our London office",
                "office graphic design",
            )
        )
        self.assertTrue(
            is_relevant_to_niche(
                "https://example.co.uk/",
                "Independent graphic design studio",
                "Brand identity services",
                "office graphic design",
            )
        )

    def test_location_relevance_rejects_another_city(self):
        self.assertFalse(
            is_relevant_to_location(
                "https://drakedentalpractice.co.uk/",
                "Dentist in Rochdale",
                "NHS and private dental practice in Rochdale",
                "Birmingham UK",
            )
        )
        self.assertTrue(
            is_relevant_to_location(
                "https://hallgreendentalpractice.co.uk/",
                "Hall Green Dental Practice",
                "Family dentist in Birmingham",
                "Birmingham UK",
            )
        )
        self.assertFalse(
            is_relevant_to_location(
                "https://example.com/",
                "Graphic design resources",
                "A conference speaker visited London before studying in Paris",
                "London UK",
            )
        )
        self.assertTrue(
            is_relevant_to_location(
                "https://example.com/",
                "Independent graphic design studio",
                "A London-based team working with local businesses",
                "London UK",
            )
        )


if __name__ == "__main__":
    unittest.main()
