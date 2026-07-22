import unittest

from app.metrics import build_quality_metrics


class MetricsTests(unittest.TestCase):
    def test_quality_metrics_cover_yield_contacts_failures_and_duplicates(self):
        clean = [
            {
                "domain": "one.example",
                "generic_email": "info@one.example",
                "phone": "123",
                "contact_page": "/contact",
                "booking_page": "",
            },
            {
                "domain": "one.example",
                "generic_email": "",
                "phone": "456",
                "contact_page": "",
                "booking_page": "/book",
            },
        ]
        metrics = build_quality_metrics([{}, {}, {}], [{}, {}], clean, [{"url": "failed"}])
        self.assertEqual(metrics["clean_yield"], 0.6667)
        self.assertEqual(metrics["failure_rate"], 0.3333)
        self.assertEqual(metrics["generic_email_coverage"], 0.5)
        self.assertEqual(metrics["phone_coverage"], 1.0)
        self.assertEqual(metrics["duplicate_rate"], 0.5)

    def test_empty_metrics_do_not_divide_by_zero(self):
        metrics = build_quality_metrics([], [], [], [])
        self.assertEqual(metrics["clean_yield"], 0.0)
        self.assertEqual(metrics["contact_page_coverage"], 0.0)


if __name__ == "__main__":
    unittest.main()
