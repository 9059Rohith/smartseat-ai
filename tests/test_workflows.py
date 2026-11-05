import tempfile
import unittest
from pathlib import Path

from store import Store, Conflict


class WorkflowTest(unittest.TestCase):
    def test_camera_table_is_unknown_until_a_fresh_observation(self):
        self.assertEqual(self.store.snapshot(100)["tables"][0]["display"], "unknown")
        self.store.observe(self.camera, {self.table: 0}, 100)
        self.assertEqual(self.store.snapshot(101)["tables"][0]["display"], "available")
        self.assertEqual(self.store.snapshot(110)["tables"][0]["display"], "unknown")
        self.store.camera_offline(self.camera)
        self.assertEqual(self.store.snapshot(111)["tables"][0]["display"], "unknown")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "test.db")
        self.camera = self.store.add_camera("Test", "webcam", "0")
        self.table = self.store.add_table("T1", 4, self.camera, [[0, 0], [1, 0], [1, 1], [0, 1]])

    def test_camera_to_service_and_cleaning(self):
        for second in range(100, 106):
            self.store.observe(self.camera, {self.table: 2}, second)
        self.assertEqual(self.store.snapshot(105)["tables"][0]["state"], "occupied")
        self.store.tick(405)
        self.assertEqual(self.store.snapshot(405)["tables"][0]["state"], "waiting")
        self.store.table_action(self.table, "greet", 410)
        for second in range(411, 425):
            self.store.observe(self.camera, {self.table: 0}, second)
        self.assertEqual(self.store.snapshot(425)["tables"][0]["state"], "cleaning")
        self.store.table_action(self.table, "clean", 430)
        self.assertEqual(self.store.snapshot(430)["tables"][0]["state"], "available")

    def test_queue_capacity_and_double_seating(self):
        large = self.store.add_party("Large", 6, 100)
        with self.assertRaises(Conflict):
            self.store.seat(large, self.table, 110)
        small = self.store.add_party("Small", 2, 100)
        self.store.seat(small, self.table, 110)
        next_party = self.store.add_party("Next", 2, 100)
        with self.assertRaises(Conflict):
            self.store.seat(next_party, self.table, 120)
        self.assertEqual(self.store.snapshot(120)["tables"][0]["state"], "occupied")

    def test_camera_gap_preserves_occupied_state(self):
        self.store.table_action(self.table, "occupy", 100)
        self.store.observe(self.camera, {self.table: 0}, 110)
        self.store.observe(self.camera, {self.table: 0}, 140)
        self.assertEqual(self.store.snapshot(140)["tables"][0]["state"], "occupied")
