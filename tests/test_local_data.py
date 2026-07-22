from __future__ import annotations

import subprocess
import sys
from unittest import TestCase, mock

from app.local_data import LocalDataService, _expand_niche, _run_hidden, _sql_literal
from app.pipeline import _has_local_seed, _lead_from_osm

OSM_ROW = {
    "osm_type": "N",
    "osm_id": 42,
    "name": "Elm Beauty Rooms",
    "category": "shop",
    "category_value": "beauty",
    "website": "",
    "phone": "020 7946 0102",
    "email": "hello@elm.test",
    "address": "14 Sample Street",
    "city": "London",
    "postcode": "W1F 8AA",
    "latitude": 51.51,
    "longitude": -0.14,
}


class LocalDataTests(TestCase):
    def test_osm_row_becomes_structured_candidate(self):
        candidate = LocalDataService._candidate(OSM_ROW)

        self.assertEqual(candidate["source"], "osm_local")
        self.assertEqual(candidate["domain"], "osm-N-42")
        self.assertEqual(candidate["osm_url"], "https://www.openstreetmap.org/node/42")
        self.assertEqual(candidate["phone"], "020 7946 0102")

    def test_phone_only_candidate_becomes_valid_lead_without_scraping(self):
        candidate = LocalDataService._candidate({**OSM_ROW, "email": ""})
        lead = _lead_from_osm(candidate)

        self.assertTrue(lead["is_valid_lead"])
        self.assertEqual(lead["business_name"], "Elm Beauty Rooms")
        self.assertEqual(lead["phones"], ["020 7946 0102"])
        self.assertGreaterEqual(lead["lead_score"], 4)

    def test_hybrid_candidate_keeps_its_local_seed_for_enrichment(self):
        self.assertTrue(_has_local_seed({"source": "hybrid", "sources": ["web", "local"]}))

    def test_sql_literal_escapes_user_input(self):
        self.assertEqual(_sql_literal("King's Cross"), "'King''s Cross'")

    def test_common_market_language_expands_to_osm_categories(self):
        terms = _expand_niche("HVAC contractors")

        self.assertIn("air conditioning", terms)
        self.assertIn("heating", terms)

    def test_market_qualifiers_do_not_drive_fuzzy_matches(self):
        terms = _expand_niche("independent cafes")

        self.assertIn("cafe", terms)
        self.assertNotIn("independent cafes", terms)

    @mock.patch("app.local_data.subprocess.run")
    def test_windows_child_processes_never_open_a_console(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "{}", "")

        _run_hidden(["wsl", "--", "true"], timeout=2)

        options = run.call_args.kwargs
        self.assertTrue(options["capture_output"])
        self.assertEqual(options["encoding"], "utf-8")
        self.assertEqual(options["errors"], "replace")
        if sys.platform == "win32":
            self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
            self.assertTrue(options["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)

    @mock.patch("app.local_data._run_hidden")
    def test_manual_update_starts_without_waiting_for_the_sync(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        service = LocalDataService()

        result = service.request_update()

        self.assertEqual(result["status"], "started")
        self.assertIn("--no-block", run.call_args.args[0])
