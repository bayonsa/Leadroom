import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api import _select_discovery_batch, create_app, make_run_name
from app.config import ScraperConfig
from app.database import RunRepository

SITE = {
    "title": "Example Salon",
    "url": "https://example.com/contact",
    "homepage": "https://example.com/",
    "snippet": "London salon",
    "domain": "example.com",
}

SECOND_SITE = {
    "title": "Second Salon",
    "url": "https://second.example/contact",
    "homepage": "https://second.example/",
    "snippet": "London salon",
    "domain": "second.example",
}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "api.db"
        self.app = create_app(self.database_path)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.app.state.executor.shutdown(wait=True, cancel_futures=True)
        self.temp_dir.cleanup()

    def wait_for_run(self, run_id: str, statuses: set[str], timeout: float = 3) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.client.get(f"/api/v1/runs/{run_id}").json()["run"]
            if run["status"] in statuses:
                return run
            time.sleep(0.01)
        self.fail(f"Run {run_id} did not reach {statuses}")

    def test_health_and_openapi(self):
        self.assertEqual(self.client.get("/api/v1/health").json(), {"status": "ok", "database": "ok"})
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/runs", schema["paths"])

    @patch("app.storage._set_ollama_models_environment")
    def test_storage_settings_validate_and_schedule_new_locations(self, _set_ollama):
        target = Path(self.temp_dir.name) / "workspace-data"
        downloads = Path(self.temp_dir.name) / "large-downloads"

        initial = self.client.get("/api/v1/settings/storage")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["active_data_root"], str(self.database_path.parent.resolve()))

        saved = self.client.put(
            "/api/v1/settings/storage",
            json={
                "data_root": str(target),
                "downloads_root": str(downloads),
                "data_action": "use",
                "move_downloads": True,
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["data_root"], str(target.resolve()))
        self.assertTrue(saved.json()["restart_required"])
        self.assertTrue(saved.json()["ollama_restart_required"])
        self.assertTrue(downloads.exists())

        self.app.state.choose_directory = lambda initial: str(target if initial else downloads)
        browsed = self.client.post("/api/v1/settings/storage/browse", json={"initial_path": str(downloads)})
        self.assertEqual(browsed.json(), {"path": str(target)})

    def test_run_name_combines_niche_and_timestamp(self):
        generated = make_run_name("Office Graphic Design", datetime(2026, 7, 15, 17, 42, 8, 123000))
        self.assertEqual(generated, "office_graphic_design_20260715_174208_123000")

    def test_static_frontend_supports_spa_deep_links(self):
        frontend = Path(self.temp_dir.name) / "frontend"
        frontend.mkdir()
        (frontend / "index.html").write_text("<h1>Leadroom app</h1>", encoding="ascii")
        static_app = create_app(self.database_path, frontend_dir=frontend)
        with TestClient(static_app) as client:
            response = client.get("/runs/example-run")
        static_app.state.executor.shutdown(wait=True, cancel_futures=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Leadroom app", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0, must-revalidate")

    @patch("app.api.search_business_sites", return_value=[SITE])
    def test_create_list_get_and_cancel_run(self, _search):
        response = self.client.post(
            "/api/v1/runs",
            json={"niche": "salons", "location": "London", "delay_seconds": 0},
        )
        self.assertEqual(response.status_code, 201)
        run_id = response.json()["run"]["id"]
        self.assertRegex(
            response.json()["run"]["run_name"],
            r"^salons_\d{8}_\d{6}_\d{6}$",
        )
        self.assertEqual(response.json()["run"]["status"], "searching")
        self.wait_for_run(run_id, {"ready"})

        self.assertEqual(len(self.client.get("/api/v1/runs").json()), 1)
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}").status_code, 200)
        diagnostics = self.client.get(f"/api/v1/runs/{run_id}/diagnostics").json()
        self.assertEqual(diagnostics["database"], "ok")
        self.assertEqual(diagnostics["configuration"]["niche"], "salons")
        self.assertTrue(diagnostics["events"])
        cancelled = self.client.post(f"/api/v1/runs/{run_id}/cancel").json()
        self.assertEqual(cancelled["status"], "stopped")

    def test_validation_and_missing_run_use_actionable_problem_shape(self):
        invalid = self.client.post("/api/v1/runs", json={"niche": "", "location": "London"})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(set(invalid.json()), {"problem", "cause", "fix"})

        missing = self.client.get("/api/v1/runs/not-a-run")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("Check the run ID", missing.json()["fix"])

    def test_desktop_token_bootstrap_redirects_to_clean_url_and_authorizes_api(self):
        secured_path = Path(self.temp_dir.name) / "secured.db"
        with patch.dict("os.environ", {"LEADROOM_LAUNCH_TOKEN": "one-time-token"}):
            secured_app = create_app(secured_path)
            with TestClient(secured_app) as client:
                bootstrap = client.get("/runs/example?launch_token=one-time-token", follow_redirects=False)
                self.assertEqual(bootstrap.status_code, 303)
                self.assertNotIn("launch_token", bootstrap.headers["location"])
                self.assertEqual(client.get("/api/v1/runs").status_code, 200)
            secured_app.state.executor.shutdown(wait=True, cancel_futures=True)

    def test_editable_settings_persist_brand_model_secret_and_filters(self):
        logo = "data:image/png;base64,iVBORw0KGgo="
        response = self.client.put(
            "/api/v1/settings",
            json={
                "model_provider": "openai_compatible",
                "model_name": "paid-model",
                "model_endpoint": "https://models.example/v1/",
                "api_key": "secret-key",
                "clear_api_key": False,
                "blocked_domains": ["Directory.Example", "directory.example"],
                "workspace_name": "Northstar",
                "workspace_subtitle": "Lead desk",
                "logo_data_url": logo,
                "theme": "vercel",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["default_model"], "oneapi/paid-model")
        self.assertEqual(data["model_endpoint"], "https://models.example/v1")
        self.assertEqual(data["blocked_domains"], ["directory.example"])
        self.assertEqual(data["workspace_name"], "Northstar")
        self.assertEqual(data["logo_data_url"], logo)
        self.assertEqual(data["theme"], "vercel")
        self.assertTrue(data["api_key_configured"])
        self.assertNotIn("api_key", data)

        trust_blue = self.client.patch("/api/v1/settings/theme", json={"theme": "trustblue"})
        self.assertEqual(trust_blue.status_code, 200)
        self.assertEqual(trust_blue.json()["theme"], "trustblue")
        zen_grid = self.client.patch("/api/v1/settings/theme", json={"theme": "zengrid"})
        self.assertEqual(zen_grid.status_code, 200)
        self.assertEqual(zen_grid.json()["theme"], "zengrid")
        self.assertEqual(
            self.client.patch("/api/v1/settings/theme", json={"theme": "unknown"}).status_code,
            422,
        )

        repo = RunRepository(self.database_path)
        try:
            self.assertEqual(repo.app_settings()["llm_api_key"], "secret-key")
        finally:
            repo.engine.dispose()

    def test_empty_workspace_identity_uses_brand_defaults(self):
        response = self.client.put(
            "/api/v1/settings",
            json={
                "model_provider": "ollama",
                "model_name": "llama3.2:3b",
                "model_endpoint": "http://localhost:11434",
                "clear_api_key": False,
                "blocked_domains": [],
                "workspace_name": "   ",
                "workspace_subtitle": "",
                "logo_data_url": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["workspace_name"], "Leadroom")
        self.assertEqual(response.json()["workspace_subtitle"], "Signal desk")

        stored = self.client.get("/api/v1/settings").json()
        self.assertEqual(stored["workspace_name"], "Leadroom")
        self.assertEqual(stored["workspace_subtitle"], "Signal desk")

    @patch("app.api.SMTPEmailProvider.test_connection")
    def test_email_settings_are_masked_and_connection_can_be_tested(self, test_connection):
        test_connection.return_value = {"status": "ok", "provider": "smtp"}
        response = self.client.put(
            "/api/v1/settings",
            json={
                "model_provider": "ollama",
                "model_name": "llama3.2:3b",
                "model_endpoint": "http://localhost:11434",
                "blocked_domains": [],
                "workspace_name": "Leadroom",
                "workspace_subtitle": "Signal desk",
                "logo_data_url": "",
                "smtp_host": "smtp.example.test",
                "smtp_port": 587,
                "smtp_security": "starttls",
                "smtp_username": "sender@example.test",
                "smtp_password": "app-password",
                "smtp_from_email": "sender@example.test",
                "smtp_from_name": "Example Agency",
                "smtp_reply_to": "privacy@example.test",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["smtp_password_configured"])
        self.assertTrue(response.json()["email_configured"])
        self.assertNotIn("smtp_password", response.json())
        tested = self.client.post("/api/v1/settings/test-email")
        self.assertEqual(tested.json()["status"], "ok")
        test_connection.assert_called_once_with()

        repo = RunRepository(self.database_path)
        try:
            self.assertEqual(repo.app_settings()["smtp_password"], "app-password")
        finally:
            repo.engine.dispose()

    @patch("app.api.SMTPEmailProvider.test_connection")
    def test_multiple_email_accounts_can_be_managed_and_tested(self, test_connection):
        test_connection.return_value = {"status": "ok", "sender": "sales@example.test"}
        first = self.client.post(
            "/api/v1/settings/email-accounts",
            json={
                "label": "Sales",
                "host": "smtp.example.test",
                "port": 587,
                "security": "starttls",
                "username": "sales@example.test",
                "password": "sales-secret",
                "from_email": "sales@example.test",
                "from_name": "Example Sales",
                "reply_to": "replies@example.test",
            },
        )
        self.assertEqual(first.status_code, 201)
        first_account = first.json()["accounts"][0]
        self.assertTrue(first_account["is_default"])
        self.assertTrue(first_account["password_configured"])
        self.assertNotIn("password", first_account)

        second = self.client.post(
            "/api/v1/settings/email-accounts",
            json={
                "label": "Partnerships",
                "host": "smtp.partner.test",
                "port": 465,
                "security": "ssl",
                "username": "partners@example.test",
                "password": "partner-secret",
                "from_email": "partners@example.test",
                "from_name": "Example Partnerships",
                "reply_to": "",
            },
        )
        second_id = second.json()["accounts"][1]["id"]
        made_default = self.client.patch(f"/api/v1/settings/email-accounts/{second_id}/default")
        self.assertEqual(made_default.json()["default_account_id"], second_id)

        tested = self.client.post(f"/api/v1/settings/email-accounts/{first_account['id']}/test")
        self.assertEqual(tested.status_code, 200)
        self.assertEqual(tested.json()["label"], "Sales")
        test_connection.assert_called_once_with()

        deleted = self.client.delete(f"/api/v1/settings/email-accounts/{second_id}").json()
        self.assertEqual(len(deleted["accounts"]), 1)
        self.assertEqual(deleted["default_account_id"], first_account["id"])

        settings = self.client.get("/api/v1/settings").json()
        self.assertTrue(settings["email_configured"])
        self.assertEqual(settings["default_email_account_id"], first_account["id"])

    def test_settings_reject_invalid_domain_and_logo(self):
        payload = {
            "model_provider": "ollama",
            "model_name": "llama3.2:3b",
            "model_endpoint": "http://localhost:11434",
            "clear_api_key": False,
            "blocked_domains": ["https://bad.example/path"],
            "workspace_name": "Leadroom",
            "workspace_subtitle": "Signal desk",
            "logo_data_url": "data:image/svg+xml;base64,PHN2Zz4=",
        }
        response = self.client.put("/api/v1/settings", json=payload)

        self.assertEqual(response.status_code, 422)

    def test_settings_reject_remote_plaintext_model_endpoint(self):
        response = self.client.put(
            "/api/v1/settings",
            json={
                "model_provider": "openai_compatible",
                "model_name": "remote-model",
                "model_endpoint": "http://models.example/v1",
                "api_key": "secret-key",
                "blocked_domains": [],
                "workspace_name": "Leadroom",
                "workspace_subtitle": "Signal desk",
                "logo_data_url": "",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("HTTPS", response.json()["cause"])

    @patch("app.api.httpx.get")
    def test_model_connection_uses_saved_compatible_endpoint_without_exposing_key(self, get):
        get.return_value.raise_for_status.return_value = None
        payload = {
            "model_provider": "openai_compatible",
            "model_name": "paid-model",
            "model_endpoint": "https://models.example/v1",
            "api_key": "secret-key",
            "clear_api_key": False,
            "blocked_domains": [],
            "workspace_name": "Leadroom",
            "workspace_subtitle": "Signal desk",
            "logo_data_url": "",
        }
        self.client.put("/api/v1/settings", json=payload)

        response = self.client.post("/api/v1/settings/test-model")

        self.assertEqual(response.json()["status"], "ok")
        get.assert_called_once_with(
            "https://models.example/v1/models",
            headers={"Authorization": "Bearer secret-key"},
            timeout=8,
            follow_redirects=True,
        )

    @patch("app.api.httpx.get")
    def test_ollama_model_inventory_returns_installed_details(self, get):
        get.return_value.raise_for_status.return_value = None
        get.return_value.json.return_value = {
            "models": [
                {
                    "name": "qwen2.5:7b",
                    "size": 4_700_000_000,
                    "modified_at": "2026-07-16T10:00:00Z",
                    "details": {"parameter_size": "7.6B", "quantization_level": "Q4_K_M", "family": "qwen2"},
                }
            ]
        }

        response = self.client.get("/api/v1/settings/ollama/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"][0]["name"], "qwen2.5:7b")
        self.assertEqual(response.json()["models"][0]["details"]["parameter_size"], "7.6B")

    @patch("app.api.httpx.get")
    def test_ollama_catalog_merges_official_models_with_local_inventory(self, get):
        tags_response = MagicMock()
        tags_response.raise_for_status.return_value = None
        tags_response.json.return_value = {"models": [{"name": "qwen3.5:4b"}]}
        catalog_response = MagicMock()
        catalog_response.raise_for_status.return_value = None
        catalog_response.text = """
        <ul><li><a href="/library/qwen3.5"><div title="qwen3.5"><h2><span>qwen3.5</span></h2>
        <p>Multimodal model family.</p></div><div class="flex flex-wrap"><span>vision</span>
        <span>tools</span><span>cloud</span><span>0.8b</span><span>4b</span></div></a></li></ul>
        """
        get.side_effect = [tags_response, catalog_response]

        response = self.client.get("/api/v1/settings/ollama/catalog?q=qwen")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["installed"], ["qwen3.5:4b"])
        self.assertEqual(response.json()["models"][0]["name"], "qwen3.5")
        self.assertEqual(response.json()["models"][0]["variants"], ["0.8b", "4b"])
        self.assertTrue(response.json()["models"][0]["local"])

    @patch("app.api.httpx.stream")
    def test_ollama_model_download_reports_streamed_progress(self, stream):
        fake = MagicMock()
        fake.raise_for_status.return_value = None
        fake.iter_lines.return_value = iter(
            [
                '{"status":"pulling manifest"}',
                '{"status":"downloading","total":100,"completed":55}',
                '{"status":"success","total":100,"completed":100}',
            ]
        )
        stream.return_value.__enter__.return_value = fake
        started = self.client.post("/api/v1/settings/ollama/pull", json={"model": "qwen2.5:7b"})
        job_id = started.json()["id"]

        deadline = time.time() + 2
        status = started.json()
        while status["status"] not in {"completed", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            status = self.client.get(f"/api/v1/settings/ollama/pulls/{job_id}").json()

        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["percent"], 100)
        stream.assert_called_once()

    @patch("app.api.httpx.post")
    @patch("app.api.httpx.get")
    def test_ollama_benchmark_scores_lead_extraction_quality(self, get, post):
        get.return_value.raise_for_status.return_value = None
        get.return_value.json.return_value = {"models": [{"name": "qwen2.5:7b"}]}
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {
            "response": '{"business_name":"Bright Smile Dental Clinic","generic_email":"hello@brightsmile.example","phone":"020 7946 0123","city_or_area":"London","services":["Dental implants","Dental hygiene"]}',
            "eval_count": 50,
            "eval_duration": 2_000_000_000,
        }

        response = self.client.post("/api/v1/settings/ollama/benchmark", json={"model": "qwen2.5:7b"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["score"], 10)
        self.assertEqual(response.json()["verdict"], "recommended")
        self.assertEqual(response.json()["tokens_per_second"], 25.0)
        self.assertEqual(len(response.json()["checks"]), 6)

    @patch("app.api.search_business_sites", return_value=[SITE])
    def test_new_run_uses_saved_default_model_endpoint_and_custom_filters(self, _search):
        self.client.put(
            "/api/v1/settings",
            json={
                "model_provider": "openai_compatible",
                "model_name": "paid-model",
                "model_endpoint": "https://models.example/v1",
                "api_key": "secret-key",
                "clear_api_key": False,
                "blocked_domains": ["custom-directory.example"],
                "workspace_name": "Leadroom",
                "workspace_subtitle": "Signal desk",
                "logo_data_url": "",
            },
        )
        response = self.client.post(
            "/api/v1/runs",
            json={
                "niche": "salons",
                "location": "London",
                "delay_seconds": 0,
            },
        )
        run_id = response.json()["run"]["id"]
        repo = RunRepository(self.database_path)
        try:
            config = repo.load_config(run_id)
        finally:
            repo.engine.dispose()

        self.assertEqual(config.model, "oneapi/paid-model")
        self.assertEqual(config.ollama_base_url, "https://models.example/v1")
        self.assertEqual(config.blocked_domains, {"custom-directory.example"})

    @patch("app.api.search_business_sites", side_effect=RuntimeError("search backend unavailable"))
    def test_create_run_persists_search_failure_diagnostics(self, _search):
        client = TestClient(self.app, raise_server_exceptions=False)
        try:
            response = client.post(
                "/api/v1/runs",
                json={"niche": "HVAC subcontractor", "location": "London UK", "delay_seconds": 0},
            )
        finally:
            client.close()

        self.assertEqual(response.status_code, 201)
        run_id = response.json()["run"]["id"]
        self.wait_for_run(run_id, {"failed"})
        events = self.client.get(f"/api/v1/runs/{run_id}/diagnostics").json()["events"]
        self.assertEqual(events[-1]["event"], "run_failed")
        self.assertEqual(events[-1]["data"]["error_type"], "RuntimeError")
        self.assertEqual(events[-1]["data"]["message"], "search backend unavailable")

    def test_start_submits_work_without_blocking_request(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        repo.engine.dispose()
        self.app.state.executor.submit = MagicMock()

        response = self.client.post(f"/api/v1/runs/{run_id}/start")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.app.state.executor.submit.assert_called_once()

        duplicate = self.client.post(f"/api/v1/runs/{run_id}/start")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["cause"], "Run is already running")
        self.app.state.executor.submit.assert_called_once()

    def test_completed_lead_can_be_edited(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        candidate_id = repo.claim(run_id, "example.com")
        repo.complete(candidate_id, {"business_name": "Example", "domain": "example.com", "lead_score": 8})
        repo.engine.dispose()

        response = self.client.patch(
            f"/api/v1/runs/{run_id}/leads/example.com",
            json={"business_name": "Edited", "generic_email": "hello@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["business_name"], "Edited")
        saved_lead = self.client.get(f"/api/v1/runs/{run_id}").json()["leads"][0]
        self.assertEqual(saved_lead["generic_email"], "hello@example.com")

    def test_repository_import_list_export_and_delete(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(
            niche="salons",
            location="London",
            run_name="salons_20260721_120000_123456",
            database_path=self.database_path,
        )
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        candidate_id = repo.claim(run_id, "example.com")
        repo.complete(
            candidate_id,
            {
                "business_name": "Example Salon",
                "website": "https://example.com/",
                "domain": "example.com",
                "generic_email": "info@example.com",
                "emails": ["info@example.com", "hello@example.com"],
                "phone": "020 1234 5678",
                "phones": ["020 1234 5678"],
                "lead_score": 9,
            },
        )
        repo.engine.dispose()

        imported = self.client.post(
            "/api/v1/repository/import",
            json={"run_id": run_id, "domains": ["example.com"]},
        )
        listed = self.client.get("/api/v1/repository")
        edited = self.client.patch(
            "/api/v1/repository/example.com",
            json={
                "business_name": "Edited Salon",
                "collection": "premium salons",
                "emails": ["team@example.com"],
            },
        )
        merged = self.client.post(
            "/api/v1/repository/collections/merge",
            json={"sources": ["premium salons"], "target": "salon businesses"},
        )
        removed_collection = self.client.delete("/api/v1/repository/collections/salon%20businesses")
        csv_export = self.client.get("/api/v1/repository/export?format=csv")
        json_export = self.client.get("/api/v1/repository/export?format=json")
        run_csv_export = self.client.get(f"/api/v1/runs/{run_id}/export?format=csv")
        run_json_export = self.client.get(f"/api/v1/runs/{run_id}/export?format=json")
        deleted = self.client.delete("/api/v1/repository/example.com")

        self.assertEqual(imported.json(), {"added": 1, "updated": 0, "skipped": 0, "total": 1})
        self.assertEqual(listed.json()["count"], 1)
        self.assertEqual(listed.json()["leads"][0]["emails"], ["info@example.com", "hello@example.com"])
        self.assertEqual(listed.json()["leads"][0]["niches"], ["salons"])
        self.assertEqual(listed.json()["leads"][0]["sources"], ["web"])
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["business_name"], "Edited Salon")
        self.assertEqual(edited.json()["niches"], ["premium salons"])
        self.assertEqual(edited.json()["emails"], ["team@example.com"])
        self.assertEqual(merged.json()["updated_leads"], 1)
        self.assertEqual(removed_collection.json()["moved_to"], "Uncategorised")
        self.assertRegex(
            csv_export.headers["content-disposition"],
            r'filename="lead_repository_downloaded_\d{8}_\d{6}\.csv"',
        )
        self.assertRegex(
            json_export.headers["content-disposition"],
            r'filename="lead_repository_downloaded_\d{8}_\d{6}\.json"',
        )
        self.assertRegex(
            run_csv_export.headers["content-disposition"],
            r'filename="salons_20260721_120000_123456_downloaded_\d{8}_\d{6}\.csv"',
        )
        self.assertRegex(
            run_json_export.headers["content-disposition"],
            r'filename="salons_20260721_120000_123456_downloaded_\d{8}_\d{6}\.json"',
        )
        self.assertIn("niches,locations,sources", csv_export.text)
        self.assertEqual(json_export.json()["count"], 1)
        self.assertEqual(deleted.json(), {"domain": "example.com", "status": "deleted"})

    def test_repository_csv_neutralizes_spreadsheet_formulas(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        candidate_id = repo.claim(run_id, "example.com")
        repo.complete(
            candidate_id,
            {
                "business_name": '=HYPERLINK("https://example.test")',
                "website": "https://example.com/",
                "domain": "example.com",
                "phone": "020 7946 0102",
                "lead_score": 1,
            },
        )
        repo.import_repository_leads(run_id, ["example.com"])
        repo.engine.dispose()

        exported = self.client.get("/api/v1/repository/export?format=csv")

        self.assertEqual(exported.status_code, 200)
        self.assertIn("'=HYPERLINK", exported.text)

    def test_outreach_api_requires_approval_before_export(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        candidate_id = repo.claim(run_id, "example.com")
        repo.complete(
            candidate_id,
            {
                "business_name": "Example Salon",
                "domain": "example.com",
                "city_or_area": "London",
                "services": ["Hair styling"],
                "generic_email": "hello@example.com",
                "lead_score": 9,
                "field_evidence": {
                    "generic_email": {
                        "value": "hello@example.com",
                        "source_url": "https://example.com/contact",
                        "method": "html_mailto",
                    }
                },
            },
        )
        repo.engine.dispose()
        draft = self.client.post(
            "/api/v1/outreach/drafts",
            json={
                "run_id": run_id,
                "domain": "example.com",
                "subscriber_type": "corporate",
                "lawful_basis_note": "Legitimate interests assessment reference LIA-001.",
                "sender_identity": "Example Agency Ltd",
                "opt_out_address": "privacy@example-agency.test",
                "offer_summary": "We review appointment workflows for independent salons.",
            },
        ).json()

        blocked = self.client.post("/api/v1/outreach/export", json={"draft_ids": [draft["id"]]})
        self.assertEqual(blocked.status_code, 409)
        approved = self.client.post(
            "/api/v1/outreach/drafts/approve-bulk",
            json={
                "draft_ids": [draft["id"]],
                "reviewed_by": "Reviewer",
                "corporate_status_confirmed": True,
                "privacy_notice_confirmed": True,
            },
        )
        exported = self.client.post("/api/v1/outreach/export", json={"draft_ids": [draft["id"]]})

        self.assertEqual(approved.json()["approved"], 1)
        self.assertEqual(approved.json()["drafts"][0]["status"], "approved")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["content-disposition"])

    @patch("app.api.SMTPEmailProvider.send", return_value="<message-1@example.test>")
    def test_approved_outreach_can_be_sent_and_audited(self, send):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        candidate_id = repo.claim(run_id, "example.com")
        repo.complete(
            candidate_id,
            {
                "business_name": "Example Salon",
                "domain": "example.com",
                "city_or_area": "London",
                "services": ["Hair styling"],
                "generic_email": "hello@example.com",
                "lead_score": 9,
                "field_evidence": {
                    "generic_email": {
                        "value": "hello@example.com",
                        "source_url": "https://example.com/contact",
                        "method": "html_mailto",
                    },
                },
            },
        )
        repo.update_app_settings(
            {
                "smtp_host": "smtp.example.test",
                "smtp_port": "587",
                "smtp_security": "starttls",
                "smtp_username": "sender@example.test",
                "smtp_password": "app-password",
                "smtp_from_email": "sender@example.test",
                "smtp_from_name": "Example Agency",
                "smtp_reply_to": "privacy@example.test",
            }
        )
        repo.engine.dispose()
        draft = self.client.post(
            "/api/v1/outreach/drafts",
            json={
                "run_id": run_id,
                "domain": "example.com",
                "subscriber_type": "corporate",
                "lawful_basis_note": "Legitimate interests assessment reference LIA-001.",
                "sender_identity": "Example Agency Ltd",
                "opt_out_address": "privacy@example.test",
                "offer_summary": "We review appointment workflows for independent salons.",
            },
        ).json()
        self.client.post(
            "/api/v1/outreach/drafts/approve-bulk",
            json={
                "draft_ids": [draft["id"]],
                "reviewed_by": "Reviewer",
                "corporate_status_confirmed": True,
                "privacy_notice_confirmed": True,
            },
        )

        started = self.client.post("/api/v1/outreach/send", json={"draft_ids": [draft["id"]]})
        self.assertEqual(started.status_code, 202)
        job = started.json()
        deadline = time.time() + 2
        while job["status"] not in {"completed", "failed", "stopped"} and time.time() < deadline:
            time.sleep(0.01)
            job = self.client.get(f"/api/v1/outreach/send/{job['id']}").json()

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["sent"], 1)
        send.assert_called_once()
        drafts = self.client.get("/api/v1/outreach/drafts").json()
        self.assertEqual(drafts[0]["status"], "sent")
        self.assertEqual(drafts[0]["delivery_status"], "sent")
        self.assertEqual(drafts[0]["provider_message_id"], "<message-1@example.test>")

    @patch("app.api.search_business_sites", return_value=[SITE])
    def test_candidate_selection_settings_and_missing_export(self, _search):
        created = self.client.post(
            "/api/v1/runs",
            json={"niche": "salons", "location": "London", "delay_seconds": 0},
        ).json()
        run_id = created["run"]["id"]
        self.wait_for_run(run_id, {"ready"})

        deselected = self.client.put(
            f"/api/v1/runs/{run_id}/candidates/example.com",
            json={"selected": False},
        )
        self.assertEqual(deselected.json()["status"], "cancelled")
        selected = self.client.put(
            f"/api/v1/runs/{run_id}/candidates/example.com",
            json={"selected": True},
        )
        self.assertEqual(selected.json()["status"], "queued")

        settings = self.client.get("/api/v1/settings").json()
        self.assertIn("fresha.com", settings["blocked_domains"])
        missing_export = self.client.get(f"/api/v1/runs/{run_id}/export?format=json")
        self.assertEqual(missing_export.status_code, 404)

    @patch("app.api.search_business_sites", return_value=[SITE])
    def test_crawl_mode_applies_server_side_page_and_depth_presets(self, _search):
        created = self.client.post(
            "/api/v1/runs",
            json={
                "niche": "salons",
                "location": "London",
                "delay_seconds": 0,
                "crawl_mode": "exhaustive",
            },
        ).json()
        run_id = created["run"]["id"]
        self.wait_for_run(run_id, {"ready"})

        diagnostics = self.client.get(f"/api/v1/runs/{run_id}/diagnostics").json()

        self.assertEqual(diagnostics["configuration"]["crawl_mode"], "exhaustive")
        self.assertEqual(diagnostics["configuration"]["crawl_page_limit"], 40)
        self.assertEqual(diagnostics["configuration"]["crawl_depth"], 4)

    @patch("app.api.search_business_sites", return_value=[SITE])
    def test_new_only_uses_market_history_and_exposes_summary(self, search):
        payload = {
            "niche": "salons",
            "location": "London",
            "delay_seconds": 0,
            "discovery_mode": "new_only",
        }
        first = self.client.post("/api/v1/runs", json=payload)
        first_id = first.json()["run"]["id"]
        self.wait_for_run(first_id, {"ready"})
        second = self.client.post("/api/v1/runs", json=payload)
        second_id = second.json()["run"]["id"]
        second_run = self.wait_for_run(second_id, {"ready"})
        history = self.client.get(
            "/api/v1/discovery/history",
            params={"niche": "SALONS", "location": " london "},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(search.call_args.kwargs["excluded_domains"], {"example.com"})
        self.assertEqual(second_run["discovery"]["mode"], "new_only")
        self.assertEqual(second_run["discovery"]["previous_market_domains"], 1)
        self.assertEqual(history.json()["seen_domains"], 1)

    @patch("app.api.search_business_sites", return_value=[SECOND_SITE])
    def test_completed_run_can_discover_another_batch_in_place(self, search):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(
            niche="salons",
            location="London",
            max_sites=10,
            database_path=self.database_path,
        )
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE], {"next_search_page": 2})
        repo.finish_run(run_id, "completed")
        repo.engine.dispose()

        response = self.client.post(f"/api/v1/runs/{run_id}/discover-more")

        self.assertEqual(response.status_code, 202)
        run = self.wait_for_run(run_id, {"ready"})
        self.assertEqual(len(self.client.get(f"/api/v1/runs/{run_id}").json()["candidates"]), 2)
        self.assertEqual(run["status"], "ready")
        self.assertEqual(search.call_args.kwargs["excluded_domains"], {"example.com"})
        self.assertEqual(search.call_args.kwargs["start_page"], 2)

    def test_combined_batch_reserves_space_for_local_and_web_results(self):
        sites = [
            *[{"domain": f"local-{index}.test", "sources": ["local"]} for index in range(9)],
            *[{"domain": f"web-{index}.test", "sources": ["web"]} for index in range(6)],
        ]

        selected = _select_discovery_batch(sites, 10, "both")

        self.assertEqual(len(selected), 10)
        self.assertEqual(sum("local" in site["sources"] for site in selected), 5)
        self.assertEqual(sum("web" in site["sources"] for site in selected), 5)

    @patch("app.api.search_business_sites")
    def test_local_and_web_continuations_keep_independent_cursors(self, search):
        def find(config, *, diagnostics, start_page, **_kwargs):
            diagnostics["next_search_page"] = start_page + 1
            source = "local" if config.search_provider == "osm_local" else "web"
            return [
                {
                    **SECOND_SITE,
                    "domain": f"{source}-{start_page}.test",
                    "sources": [source],
                }
            ]

        search.side_effect = find
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(
            run_id,
            [SITE],
            {"source_mode": "both", "next_search_page": 2, "next_pages": {"local": 3, "web": 5, "both": 2}},
        )
        repo.finish_run(run_id, "completed")
        repo.engine.dispose()

        local = self.client.post(f"/api/v1/runs/{run_id}/discover-more?source=local")
        self.wait_for_run(run_id, {"ready"})
        web = self.client.post(f"/api/v1/runs/{run_id}/discover-more?source=web")
        self.wait_for_run(run_id, {"ready"})

        self.assertEqual(local.json()["source"], "local")
        self.assertEqual(web.json()["source"], "web")
        self.assertEqual([call.kwargs["start_page"] for call in search.call_args_list], [3, 5])
        self.assertEqual(
            [call.args[0].search_provider for call in search.call_args_list],
            ["osm_local", "auto"],
        )

    @patch("app.api.search_business_sites", return_value=[])
    def test_empty_continuation_keeps_terminal_state_and_advances_diagnostics(self, _search):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.add_candidates(run_id, [SITE])
        repo.finish_run(run_id, "completed")
        repo.engine.dispose()

        response = self.client.post(f"/api/v1/runs/{run_id}/discover-more")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.wait_for_run(run_id, {"completed"})["status"], "completed")

    def test_stopped_search_can_continue_and_run_can_be_deleted(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.engine.dispose()
        self.app.state.executor.submit = MagicMock()

        stopped = self.client.post(f"/api/v1/runs/{run_id}/cancel")
        continued = self.client.post(f"/api/v1/runs/{run_id}/continue")
        deleted = self.client.delete(f"/api/v1/runs/{run_id}")

        self.assertEqual(stopped.json()["status"], "stopped")
        self.assertEqual(continued.status_code, 202)
        self.assertEqual(continued.json()["kind"], "discovery")
        self.assertEqual(deleted.json(), {"id": run_id, "status": "deleted"})
        self.assertEqual(self.client.get(f"/api/v1/runs/{run_id}").status_code, 404)

    def test_terminal_run_event_stream_closes(self):
        repo = RunRepository(self.database_path)
        config = ScraperConfig(niche="salons", location="London", database_path=self.database_path)
        run_id = repo.create_run(config)
        repo.finish_run(run_id, "completed")
        repo.engine.dispose()

        response = self.client.get(f"/api/v1/runs/{run_id}/events")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: run_created", response.text)
        self.assertIn("event: run_completed", response.text)


if __name__ == "__main__":
    unittest.main()
