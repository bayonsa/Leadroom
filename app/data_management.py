from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.config import _data_path
from app.database import RunRepository


def backup_database(database_path: Path, destination: Path) -> Path:
    repository = RunRepository(database_path)
    try:
        if repository.integrity_check() != "ok":
            raise RuntimeError("Source database integrity check failed")
        return repository.backup_to(destination)
    finally:
        repository.engine.dispose()


def restore_database(database_path: Path, source: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"Backup does not exist: {source}")
    with closing(sqlite3.connect(source)) as candidate:
        if candidate.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup database integrity check failed")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safety_backup = database_path.with_name(f"{database_path.stem}.before-restore-{timestamp}.db")
    if database_path.is_file():
        backup_database(database_path, safety_backup)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as candidate, closing(sqlite3.connect(database_path)) as target:
        candidate.backup(target)
    return safety_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up or restore the local Leadroom database.")
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("source_or_destination", type=Path)
    parser.add_argument("--database", type=Path, default=_data_path("lead_scraper.db"))
    args = parser.parse_args()
    if args.action == "backup":
        result = backup_database(args.database, args.source_or_destination)
        print(f"Backup created: {result}")
    else:
        result = restore_database(args.database, args.source_or_destination)
        print(f"Restore complete. Previous database backup: {result}")


if __name__ == "__main__":
    main()
