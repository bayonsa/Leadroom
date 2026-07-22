import csv
import tempfile
from pathlib import Path
from unittest import TestCase

from app.export import save_run


class ExportSecurityTests(TestCase):
    def test_automatic_csv_export_neutralizes_spreadsheet_formulas(self):
        with tempfile.TemporaryDirectory() as directory:
            _json_path, csv_path = save_run(
                {"clean_leads": [{"business_name": '=HYPERLINK("bad")', "domain": "example.com"}]},
                Path(directory),
                "formula",
            )

            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))

        self.assertTrue(row["business_name"].startswith("'="))
