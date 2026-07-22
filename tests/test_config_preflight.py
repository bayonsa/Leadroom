import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import ScraperConfig
from app.preflight import check_ollama, check_output_dir, ollama_model_name


class ConfigPreflightTests(unittest.TestCase):
    def test_config_rejects_unsafe_run_name(self):
        with self.assertRaisesRegex(ValueError, "run_name"):
            ScraperConfig(niche="salons", location="London", run_name="../outside")

    def test_config_rejects_out_of_range_limits(self):
        with self.assertRaisesRegex(ValueError, "max_sites"):
            ScraperConfig(niche="salons", location="London", max_sites=0)

    def test_output_directory_is_created_and_writable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "exports"
            result = check_output_dir(target)
        self.assertTrue(result.ok)

    def test_ollama_model_prefix_is_removed(self):
        self.assertEqual(ollama_model_name("ollama/llama3.2:3b"), "llama3.2:3b")

    @patch("app.preflight.urlopen")
    def test_ollama_check_finds_installed_model(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode()
        response.__enter__.return_value = response
        mock_urlopen.return_value = response

        service, model = check_ollama("http://localhost:11434", "ollama/llama3.2:3b")

        self.assertTrue(service.ok)
        self.assertTrue(model.ok)


if __name__ == "__main__":
    unittest.main()
