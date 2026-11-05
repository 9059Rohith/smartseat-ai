from pathlib import Path
import unittest

import cv2
import numpy as np

from vision import PersonDetector, Tracker, analyze


class VisionTest(unittest.TestCase):
    def test_small_model_uses_its_trained_input_resolution(self):
        detector = PersonDetector(model=Path(__file__).resolve().parents[1] / "models/yolox_s.onnx")
        self.assertEqual(detector.size, 640)

    def test_real_model_detects_dining_tables_in_recorded_footage(self):
        root = Path(__file__).resolve().parents[1]
        capture = cv2.VideoCapture(str(root / "demo/restaurant.mp4"))
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        self.assertTrue(ok)
        scene = PersonDetector().detect_scene(frame)
        self.assertGreater(len(scene["people"]), 0)
        self.assertGreaterEqual(len(scene["tables"]), 5)
        self.assertTrue(all(.0 < item["confidence"] <= 1 for item in scene["tables"]))
        self.assertTrue(all(0 <= x <= 1 and 0 <= y <= 1
                            for item in scene["tables"] for x, y in item["zone"]))

    def test_bundled_sample_runs_real_inference(self):
        root = Path(__file__).resolve().parents[1]
        capture = cv2.VideoCapture(str(root / "demo/restaurant.mp4"))
        try:
            ok, frame = capture.read()
        finally:
            capture.release()
        self.assertTrue(ok)
        people = PersonDetector().detect(frame, .19)
        self.assertGreater(len(people), 0)
        self.assertTrue(all(x1 < x2 and y1 < y2 for x1, y1, x2, y2 in people))

    def test_overlapping_zones_assign_person_only_once(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        tables = [
            {"id": 1, "zone": [[.1,.2],[.5,.2],[.5,.7],[.1,.7]]},
            {"id": 2, "zone": [[.3,.2],[.7,.2],[.7,.7],[.3,.7]]},
        ]
        tracker = Tracker()
        first = tracker.update([(28, 15, 51, 73)], 1)
        second = tracker.update([(29, 15, 53, 73)], 2)
        self.assertEqual(set(first), set(second))
        counts, _, _ = analyze(frame, second, tables, [])
        self.assertEqual(sum(counts.values()), 1)
