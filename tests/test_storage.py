from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from app.storage import apply_pending_storage, load_storage_config, schedule_storage_change


def _database(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES (?)", (value,))


def test_workspace_database_and_exports_move_after_restart(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    source = tmp_path / "source"
    target = tmp_path / "target"
    downloads = tmp_path / "downloads"
    config_path = bootstrap / "storage.json"
    _database(source / "lead_scraper.db", "current workspace")
    (source / "exports").mkdir(parents=True)
    (source / "exports" / "leads.csv").write_text("business,email\n", encoding="utf-8")

    with patch("app.storage._set_ollama_models_environment"):
        schedule_storage_change(
            config_path,
            bootstrap,
            source,
            str(target),
            str(downloads),
            "move",
            False,
        )

    applied = apply_pending_storage(config_path, bootstrap)
    with sqlite3.connect(target / "lead_scraper.db") as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("current workspace",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert (target / "exports" / "leads.csv").exists()
    assert not (source / "lead_scraper.db").exists()
    assert "previous_data_root" not in json.loads(config_path.read_text(encoding="utf-8"))
    assert applied["data_root"] == str(target.resolve())


def test_use_existing_database_never_overwrites_it(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    source = tmp_path / "source"
    target = tmp_path / "existing"
    config_path = bootstrap / "storage.json"
    _database(source / "lead_scraper.db", "old")
    _database(target / "lead_scraper.db", "selected")

    with patch("app.storage._set_ollama_models_environment"):
        schedule_storage_change(
            config_path,
            bootstrap,
            source,
            str(target),
            str(tmp_path / "downloads"),
            "use",
            False,
        )
    apply_pending_storage(config_path, bootstrap)

    with sqlite3.connect(target / "lead_scraper.db") as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("selected",)
    assert (source / "lead_scraper.db").exists()


def test_move_refuses_to_replace_existing_database(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _database(source / "lead_scraper.db", "source")
    _database(target / "lead_scraper.db", "target")

    with patch("app.storage._set_ollama_models_environment"), pytest.raises(ValueError, match="use existing"):
        schedule_storage_change(
            tmp_path / "bootstrap" / "storage.json",
            tmp_path / "bootstrap",
            source,
            str(target),
            str(tmp_path / "downloads"),
            "move",
            False,
        )


def test_storage_config_falls_back_when_locator_is_invalid(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    config_path = bootstrap / "storage.json"
    bootstrap.mkdir()
    config_path.write_text("not-json", encoding="utf-8")

    config = load_storage_config(config_path, bootstrap)

    assert config["data_root"] == str(bootstrap)
    assert config["cache_dir"] == str(bootstrap / "cache")


def test_relative_storage_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute folder path"):
        schedule_storage_change(
            tmp_path / "storage.json",
            tmp_path,
            tmp_path,
            "relative/data",
            str(tmp_path / "downloads"),
            "move",
            False,
        )
