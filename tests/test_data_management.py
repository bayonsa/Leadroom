import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.config import ScraperConfig
from app.data_management import backup_database, restore_database
from app.database import RunRepository


class DataManagementTests(unittest.TestCase):
    def test_backup_restore_and_safety_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "active.db"
            backup = root / "backup.db"
            repository = RunRepository(database)
            first_id = repository.create_run(
                ScraperConfig(niche="salons", location="London", database_path=database)
            )
            repository.engine.dispose()
            backup_database(database, backup)

            repository = RunRepository(database)
            repository.create_run(ScraperConfig(niche="dentists", location="Leeds", database_path=database))
            repository.engine.dispose()
            safety = restore_database(database, backup)

            restored = RunRepository(database)
            try:
                self.assertEqual(restored.list_runs()[0]["id"], first_id)
                self.assertEqual(len(restored.list_runs()), 1)
                self.assertEqual(restored.integrity_check(), "ok")
            finally:
                restored.engine.dispose()
            self.assertTrue(safety.is_file())

    def test_restore_rejects_corrupt_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corrupt = root / "corrupt.db"
            corrupt.write_text("not sqlite", encoding="ascii")
            with self.assertRaises(sqlite3.DatabaseError):
                restore_database(root / "active.db", corrupt)


if __name__ == "__main__":
    unittest.main()
