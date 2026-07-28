from __future__ import annotations

import filecmp
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class StorageConfigurationError(ValueError):
    pass


def default_storage_paths(bootstrap_root: Path) -> dict[str, Path]:
    local_app_data = Path(os.getenv("LOCALAPPDATA", bootstrap_root.parent))
    return {
        "data_root": bootstrap_root,
        "cache_dir": bootstrap_root / "cache",
        "browser_dir": local_app_data / "ms-playwright",
        "ollama_dir": Path.home() / ".ollama" / "models",
    }


def load_storage_config(config_path: Path, bootstrap_root: Path) -> dict[str, Any]:
    defaults = default_storage_paths(bootstrap_root)
    if not config_path.exists():
        stored: dict[str, Any] = {}
    else:
        try:
            stored = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageConfigurationError(
                f"Storage configuration is unreadable: {config_path}. "
                "Restore or remove this file after locating your existing workspace."
            ) from exc
        if not isinstance(stored, dict):
            raise StorageConfigurationError(
                f"Storage configuration must contain an object: {config_path}"
            )
    data_root = _configured_path(stored.get("data_root")) or defaults["data_root"]
    downloads_root = _configured_path(stored.get("downloads_root"))
    return {
        **stored,
        "data_root": str(data_root),
        "downloads_root": str(downloads_root) if downloads_root else "",
        "cache_dir": str(downloads_root / "cache" if downloads_root else defaults["cache_dir"]),
        "browser_dir": str(downloads_root / "playwright" if downloads_root else defaults["browser_dir"]),
        "ollama_dir": str(downloads_root / "ollama" / "models" if downloads_root else defaults["ollama_dir"]),
    }


def save_storage_config(config_path: Path, payload: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(config_path)


def validate_storage_directory(value: str) -> dict[str, Any]:
    path = _required_absolute_path(value)
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".leadroom-write-test-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"leadroom")
    finally:
        probe.unlink(missing_ok=True)
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "free_bytes": usage.free,
        "total_bytes": usage.total,
    }


def directory_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def schedule_storage_change(
    config_path: Path,
    bootstrap_root: Path,
    current_data_root: Path,
    data_root: str,
    downloads_root: str,
    data_action: str,
    move_downloads: bool,
) -> dict[str, Any]:
    data_target = Path(validate_storage_directory(data_root)["path"])
    downloads_target = Path(validate_storage_directory(downloads_root)["path"])
    if data_action not in {"move", "use"}:
        raise ValueError("Choose whether to move current data or use the selected folder")
    current_data_root = current_data_root.resolve()
    if data_action == "move" and data_target != current_data_root:
        _reject_overlapping_paths(current_data_root, data_target, "workspace")
    if data_action == "move" and data_target != current_data_root:
        target_database = data_target / "lead_scraper.db"
        if target_database.exists():
            raise ValueError(
                "The selected data folder already contains lead_scraper.db. Choose use existing instead."
            )
    if data_action == "use" and (data_target / "lead_scraper.db").exists():
        _validate_database(data_target / "lead_scraper.db", require_leadroom_schema=True)
    current = load_storage_config(config_path, bootstrap_root)
    payload = {
        "data_root": str(data_target),
        "downloads_root": str(downloads_target),
        "data_action": data_action,
        "move_downloads": move_downloads,
    }
    if data_action == "move" and data_target != current_data_root:
        payload["previous_data_root"] = str(current_data_root)
    if move_downloads:
        current_cache = _configured_path(current.get("cache_dir"))
        current_browser = _configured_path(current.get("browser_dir"))
        if current_cache and current_cache != downloads_target / "cache":
            _reject_overlapping_paths(current_cache, downloads_target / "cache", "cache")
            payload["previous_cache_dir"] = str(current_cache)
        if current_browser and current_browser != downloads_target / "playwright":
            _reject_overlapping_paths(
                current_browser,
                downloads_target / "playwright",
                "browser downloads",
            )
            payload["previous_browser_dir"] = str(current_browser)
    _set_ollama_models_environment(downloads_target / "ollama" / "models")
    save_storage_config(config_path, payload)
    return load_storage_config(config_path, bootstrap_root)


def apply_pending_storage(config_path: Path, bootstrap_root: Path) -> dict[str, Any]:
    config = load_storage_config(config_path, bootstrap_root)
    data_root = Path(config["data_root"])
    previous_data_root = _configured_path(config.get("previous_data_root"))
    if previous_data_root and previous_data_root != data_root:
        _migrate_workspace(previous_data_root, data_root)
        config.pop("previous_data_root", None)
    downloads_root = _configured_path(config.get("downloads_root"))
    previous_cache = _configured_path(config.get("previous_cache_dir"))
    previous_browser = _configured_path(config.get("previous_browser_dir"))
    if downloads_root and previous_cache:
        _merge_directory(previous_cache, downloads_root / "cache")
        config.pop("previous_cache_dir", None)
    if downloads_root and previous_browser:
        _merge_directory(previous_browser, downloads_root / "playwright")
        config.pop("previous_browser_dir", None)
    data_root.mkdir(parents=True, exist_ok=True)
    Path(config["cache_dir"]).mkdir(parents=True, exist_ok=True)
    if config.get("downloads_root"):
        Path(config["downloads_root"]).mkdir(parents=True, exist_ok=True)
    persisted = {
        key: value for key, value in config.items() if key not in {"cache_dir", "browser_dir", "ollama_dir"}
    }
    save_storage_config(config_path, persisted)
    return load_storage_config(config_path, bootstrap_root)


def _migrate_workspace(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    source_database = source / "lead_scraper.db"
    target_database = target / "lead_scraper.db"
    migration_root = target / ".leadroom-workspace-migration"
    staged_database = migration_root / "lead_scraper.db"
    staged_exports = migration_root / "exports"
    marker_path = migration_root / "marker.json"
    if source_database.exists():
        if target_database.exists():
            marker = _read_migration_marker(marker_path)
            if (
                marker.get("source") != str(source.resolve())
                or marker.get("database_sha256") != _file_sha256(target_database)
            ):
                raise FileExistsError(
                    f"Refusing to replace or adopt an unrelated database at {target_database}"
                )
            _validate_database(target_database)
        else:
            migration_root.mkdir(parents=True, exist_ok=True)
            marker = _read_migration_marker(marker_path) if marker_path.exists() else {}
            if marker and marker.get("source") != str(source.resolve()):
                raise RuntimeError("The pending migration belongs to a different workspace")
            if staged_database.exists():
                try:
                    _validate_database(staged_database)
                except ValueError:
                    staged_database.unlink(missing_ok=True)
            if not staged_database.exists():
                source_connection = sqlite3.connect(source_database)
                target_connection = sqlite3.connect(staged_database)
                try:
                    source_connection.backup(target_connection)
                finally:
                    target_connection.close()
                    source_connection.close()
            _validate_database(staged_database)
            _write_migration_marker(
                marker_path,
                {
                    "source": str(source.resolve()),
                    "database_sha256": _file_sha256(staged_database),
                },
            )
    if (source / "exports").exists():
        migration_root.mkdir(parents=True, exist_ok=True)
        _copy_directory(source / "exports", staged_exports)
    if source_database.exists() and not target_database.exists():
        staged_database.replace(target_database)
    _merge_directory(staged_exports, target / "exports")
    if (source / "exports").exists():
        shutil.rmtree(source / "exports")
    if source_database.exists():
        for suffix in ("", "-wal", "-shm"):
            _unlink_with_retry(source / f"lead_scraper.db{suffix}")
    if migration_root.exists():
        marker_path.unlink(missing_ok=True)
        migration_root.rmdir()


def _unlink_with_retry(path: Path, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError as exc:
            if attempt == attempts - 1:
                raise PermissionError(
                    f"Could not remove {path}; close any program using the Leadroom database and retry."
                ) from exc
            time.sleep(0.1 * (attempt + 1))


def _merge_directory(source: Path, target: Path) -> None:
    if not source.exists() or source.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _merge_directory(item, destination)
        elif destination.exists():
            if filecmp.cmp(item, destination, shallow=False):
                item.unlink()
            else:
                preserved = target / f"{item.stem}-from-previous-{uuid.uuid4().hex[:8]}{item.suffix}"
                shutil.move(str(item), str(preserved))
        else:
            shutil.move(str(item), str(destination))
    source.rmdir()


def _copy_directory(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_directory(item, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(f"{destination.suffix}.{uuid.uuid4().hex}.tmp")
            shutil.copy2(item, temporary)
            temporary.replace(destination)


def _validate_database(path: Path, require_leadroom_schema: bool = False) -> None:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        integrity = connection.execute("PRAGMA quick_check").fetchone()
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"The selected database is not a valid SQLite workspace: {path}") from exc
    finally:
        if connection is not None:
            connection.close()
    if not integrity or integrity[0] != "ok":
        raise ValueError(f"The selected database failed its integrity check: {path}")
    if require_leadroom_schema and not {"runs", "app_settings"}.issubset(tables):
        raise ValueError("The selected database is not a compatible Leadroom workspace")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_migration_marker(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_migration_marker(path: Path, value: dict[str, str]) -> None:
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


def _reject_overlapping_paths(source: Path, target: Path, label: str) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        return
    if source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError(
            f"The selected {label} folder cannot contain, or be contained by, its current folder"
        )


def _configured_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(os.path.expandvars(value.strip())).expanduser().resolve()


def _required_absolute_path(value: str) -> Path:
    expanded = Path(os.path.expandvars(value.strip())).expanduser()
    if not value.strip() or not expanded.is_absolute():
        raise ValueError("Choose an absolute folder path such as D:\\LeadroomData")
    return expanded.resolve()


def _set_ollama_models_environment(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.environ["OLLAMA_MODELS"] = str(path)
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "OLLAMA_MODELS", 0, winreg.REG_SZ, str(path))
    except OSError as exc:
        raise ValueError(f"Could not update the Ollama model location: {exc}") from exc
