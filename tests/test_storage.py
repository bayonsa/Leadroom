from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from app.database import RunRepository
from app.storage import (
    StorageConfigurationError,
    apply_pending_storage,
    load_storage_config,
    schedule_storage_change,
)


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
    selected = RunRepository(target / "lead_scraper.db")
    selected.update_app_settings({"workspace_name": "Selected workspace"})
    selected.engine.dispose()

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

    selected = RunRepository(target / "lead_scraper.db")
    assert selected.app_settings()["workspace_name"] == "Selected workspace"
    selected.engine.dispose()
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


def test_storage_config_never_silently_falls_back_when_locator_is_invalid(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    config_path = bootstrap / "storage.json"
    bootstrap.mkdir()
    config_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(StorageConfigurationError, match="locating your existing workspace"):
        load_storage_config(config_path, bootstrap)


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


def test_workspace_migration_recovers_after_export_copy_failure(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    source = tmp_path / "source"
    target = tmp_path / "target"
    config_path = bootstrap / "storage.json"
    _database(source / "lead_scraper.db", "recoverable")
    (source / "exports").mkdir(parents=True)
    (source / "exports" / "leads.csv").write_text("business,email\n", encoding="utf-8")
    with patch("app.storage._set_ollama_models_environment"):
        schedule_storage_change(
            config_path,
            bootstrap,
            source,
            str(target),
            str(tmp_path / "downloads"),
            "move",
            False,
        )

    with (
        patch("app.storage._copy_directory", side_effect=OSError("disk interrupted")),
        pytest.raises(OSError, match="disk interrupted"),
    ):
        apply_pending_storage(config_path, bootstrap)

    assert (source / "lead_scraper.db").exists()
    assert (source / "exports" / "leads.csv").exists()
    assert not (target / "lead_scraper.db").exists()
    (target / ".leadroom-workspace-migration" / "lead_scraper.db").write_bytes(b"interrupted")

    apply_pending_storage(config_path, bootstrap)
    with sqlite3.connect(target / "lead_scraper.db") as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("recoverable",)
    assert (target / "exports" / "leads.csv").exists()
    assert not (source / "lead_scraper.db").exists()


def test_nested_workspace_destination_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "workspace"
    source.mkdir()

    with patch("app.storage._set_ollama_models_environment"), pytest.raises(
        ValueError, match="cannot contain"
    ):
        schedule_storage_change(
            tmp_path / "bootstrap" / "storage.json",
            tmp_path / "bootstrap",
            source,
            str(source / "nested"),
            str(tmp_path / "downloads"),
            "move",
            False,
        )


def test_use_existing_rejects_corrupt_or_unrelated_database(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "lead_scraper.db").write_bytes(b"not sqlite")

    with patch("app.storage._set_ollama_models_environment"), pytest.raises(
        ValueError, match="valid SQLite"
    ):
        schedule_storage_change(
            tmp_path / "bootstrap" / "storage.json",
            tmp_path / "bootstrap",
            tmp_path / "source",
            str(target),
            str(tmp_path / "downloads"),
            "use",
            False,
        )


def test_migration_never_adopts_a_database_that_appears_after_scheduling(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    source = tmp_path / "source"
    target = tmp_path / "target"
    config_path = bootstrap / "storage.json"
    _database(source / "lead_scraper.db", "source")
    with patch("app.storage._set_ollama_models_environment"):
        schedule_storage_change(
            config_path,
            bootstrap,
            source,
            str(target),
            str(tmp_path / "downloads"),
            "move",
            False,
        )
    _database(target / "lead_scraper.db", "unrelated")

    with pytest.raises(FileExistsError, match="unrelated database"):
        apply_pending_storage(config_path, bootstrap)

    with sqlite3.connect(source / "lead_scraper.db") as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("source",)
    with sqlite3.connect(target / "lead_scraper.db") as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("unrelated",)
