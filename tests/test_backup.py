"""Real SQLite and Windows DPAPI recovery tests; no production database writes."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

from operations.backup import create_backup, restore_backup, verify_backup
from operations import backup


class CloudOutputTest(unittest.TestCase):
    def test_accepts_agent_envelope_and_regular_cli_json_array(self):
        samples = (
            'Target: production\n{"boundary":"id","rows":[{"verification_value":1}],"warning":"untrusted"}',
            '[\n {"verification_value":1}\n]',
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(backup._query_rows(sample), [{"verification_value": 1}])


@unittest.skipUnless(os.name == "nt", "CurrentUser DPAPI is Windows-only")
class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.sqlite3"
        self.db = sqlite3.connect(self.source)
        self.addCleanup(self.db.close)
        self.db.execute("pragma journal_mode=WAL")
        self.db.execute("create table records(id integer primary key, detail text)")
        self.db.execute("insert into records values(1,'credential-marker-not-on-disk')")
        self.db.commit()

    def backup(self):
        return create_backup(self.source, self.root / "archives")

    def test_live_wal_snapshot_roundtrips_and_never_writes_plaintext_archive(self):
        archive = self.backup()
        self.assertNotIn(b"credential-marker-not-on-disk", archive.read_bytes())
        self.assertEqual([p.suffix for p in archive.parent.iterdir()], [".ssbackup"])
        self.db.execute("insert into records values(2,'after snapshot')")
        self.db.commit()
        report = restore_backup(archive, self.root / "recovery")
        with closing(sqlite3.connect(self.root / "recovery" / "smartseat.sqlite3")) as restored:
            self.assertEqual(restored.execute("select * from records").fetchall(),
                             [(1, "credential-marker-not-on-disk")])
        self.assertEqual(report["integrity"], "ok")
        self.assertEqual(self.db.execute("select count(*) from records").fetchone()[0], 2)

    def test_verify_checks_integrity_without_creating_plaintext_files(self):
        archive = self.backup()
        before = set(self.root.rglob("*"))
        report = verify_backup(archive)
        self.assertEqual(report["integrity"], "ok")
        self.assertEqual(report["table_counts"], {"records": 1})
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_missing_source_is_not_silently_created(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            create_backup(missing, self.root / "archives")
        self.assertFalse(missing.exists())

    def test_corrupted_ciphertext_is_rejected(self):
        archive = self.backup()
        raw = bytearray(archive.read_bytes())
        raw[-15] ^= 0x55
        archive.write_bytes(raw)
        with self.assertRaises(ValueError):
            verify_backup(archive)

    def test_restore_refuses_existing_directory_and_leaves_source_untouched(self):
        archive = self.backup()
        recovery = self.root / "recovery"
        recovery.mkdir()
        (recovery / "keep.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            restore_backup(archive, recovery)
        self.assertEqual((recovery / "keep.txt").read_text(), "keep")

    def test_restore_refuses_live_database_parent_directory(self):
        archive = self.backup()
        with self.assertRaises(FileExistsError):
            restore_backup(archive, self.source.parent)


if __name__ == "__main__":
    unittest.main()
