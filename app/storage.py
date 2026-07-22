from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


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
    try:
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(stored, dict):
            stored = {}
    except (OSError, json.JSONDecodeError):
        stored = {}
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
        target_database = data_target / "lead_scraper.db"
        if target_database.exists():
            raise ValueError(
                "The selected data folder already contains lead_scraper.db. Choose use existing instead."
            )
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
            payload["previous_cache_dir"] = str(current_cache)
        if current_browser and current_browser != downloads_target / "playwright":
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
    if source_database.exists():
        if target_database.exists():
            raise FileExistsError(f"Refusing to overwrite existing database at {target_database}")
        temporary = target / "lead_scraper.db.migrating"
        temporary.unlink(missing_ok=True)
        source_connection = sqlite3.connect(source_database)
        target_connection = sqlite3.connect(temporary)
        try:
            source_connection.backup(target_connection)
            integrity = target_connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            target_connection.close()
            source_connection.close()
        if not integrity or integrity[0] != "ok":
            temporary.unlink(missing_ok=True)
            raise RuntimeError("The migrated database failed its integrity check")
        temporary.replace(target_database)
        for suffix in ("", "-wal", "-shm"):
            _unlink_with_retry(source / f"lead_scraper.db{suffix}")
    _merge_directory(source / "exports", target / "exports")


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
            item.rmdir()
        elif destination.exists():
            preserved = target / f"{item.stem}-from-previous-{uuid.uuid4().hex[:8]}{item.suffix}"
            shutil.move(str(item), str(preserved))
        else:
            shutil.move(str(item), str(destination))
    source.rmdir()


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
