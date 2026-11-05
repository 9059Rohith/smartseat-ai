"""Local person detection, anonymous tracking, and camera capture."""
from dataclasses import dataclass
import os
from pathlib import Path
from threading import Condition, Event, Lock, Thread
import time

import cv2
import numpy as np
from broad_tables import TableScanner

ROOT = Path(__file__).resolve().parent
DINING_ITEMS = {39:'bottle',40:'wine glass',41:'cup',42:'fork',43:'knife',44:'spoon',45:'bowl',
                46:'banana',47:'apple',48:'sandwich',49:'orange',50:'broccoli',51:'carrot',
                52:'hot dog',53:'pizza',54:'donut',55:'cake'}
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")


class PersonDetector:
    def __init__(self, model=None):
        cv2.setNumThreads(4)
        self.model_path = Path(model or ROOT / "models/yolox_s.onnx")
        self.net = cv2.dnn.readNetFromONNX(str(self.model_path))
        self.lock = Lock()
        self.size = 416 if self.model_path.name in ("yolox_nano.onnx", "yolox_tiny.onnx") else 640
        self.grids = []
        for stride in (8, 16, 32):
            y, x = np.mgrid[:self.size // stride, :self.size // stride]
            self.grids.extend(zip(x.ravel(), y.ravel(), [stride] * x.size))
        self.grids = np.asarray(self.grids, np.float32)

    def detect_scene(self, frame, confidence=0.25):
        h, w = frame.shape[:2]
        scale = min(self.size / w, self.size / h)
        resized = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))
        padded = np.full((self.size, self.size, 3), 114, np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        with self.lock:
            self.net.setInput(cv2.dnn.blobFromImage(padded))
            pred = self.net.forward()[0]
        classes = np.argmax(pred[:, 5:], axis=1)
        scores = pred[:, 4] * np.max(pred[:, 5:], axis=1)
        thresholds = np.where(classes == 0, confidence, np.where(classes == 60, .08, .30))
        keep = (scores >= thresholds) & np.isin(classes, (0, 56, 60, *DINING_ITEMS))
        pred, grid, scores, classes = pred[keep], self.grids[keep], scores[keep], classes[keep]
        centers = (pred[:, :2] + grid[:, :2]) * grid[:, 2:]
        sizes = np.exp(np.clip(pred[:, 2:4], -10, 10)) * grid[:, 2:]
        corners = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) / scale
        corners[:, (0, 2)] = np.clip(corners[:, (0, 2)], 0, w - 1)
        corners[:, (1, 3)] = np.clip(corners[:, (1, 3)], 0, h - 1)
        boxes = corners.copy()
        boxes[:, 2:] -= boxes[:, :2]
        scene = {"people": [], "chairs": [], "tables": [], "items": []}
        weak_tables = []
        for class_id, label in ((0, "people"), (56, "chairs"), (60, "tables"), *((key,'items') for key in DINING_ITEMS)):
            candidates = np.flatnonzero(classes == class_id)
            threshold = confidence if class_id == 0 else (.08 if class_id == 60 else .30)
            picked = cv2.dnn.NMSBoxes(boxes[candidates].tolist(), scores[candidates].tolist(), threshold, .45)
            for index in picked:
                source = candidates[index]
                if min(boxes[source, 2:]) <= 3:
                    continue
                rect = tuple(int(n) for n in corners[source])
                if label == "people":
                    scene[label].append(rect)
                else:
                    x1, y1, x2, y2 = rect
                    item = {
                        "box": rect,
                        "zone": [[x1 / w, y1 / h], [x2 / w, y1 / h], [x2 / w, y2 / h], [x1 / w, y2 / h]],
                        "confidence": round(float(scores[source]), 3),
                        "method": "object_model",
                    }
                    if label == 'items':
                        item['label'] = DINING_ITEMS[class_id]
                    if label == "tables" and scores[source] < .30:
                        weak_tables.append(item)
                    else:
                        scene[label].append(item)
        scene["tables"].extend(table_surface_candidates(frame, weak_tables, scene["tables"]))
        return scene

    def detect(self, frame, confidence=0.25):
        return self.detect_scene(frame, confidence)["people"]


def assess_clearance(frame, counts, regions, items, visible_tables):
    """Visible-object evidence, never a sanitation or staff-cleaning certification."""
    h,w=frame.shape[:2]
    results={}
    for region in regions:
        key=region['id']; poly=zone_contour(region['zone'],w,h)
        if len(poly)<3:
            results[key]={'state':'unknown','items':[]};continue
        visible=any(cv2.pointPolygonTest(poly,((item['box'][0]+item['box'][2])/2,
                     (item['box'][1]+item['box'][3])/2),False)>=0 for item in visible_tables)
        found=[{'label':item['label'],'confidence':item['confidence']} for item in items
               if cv2.pointPolygonTest(poly,((item['box'][0]+item['box'][2])/2,
                  (item['box'][1]+item['box'][3])/2),False)>=0]
        state='occupied' if counts.get(key,0)>0 else 'unknown' if not visible else 'items_present' if found else 'looks_clear'
        results[key]={'state':state,'items':found}
    return results


def table_surface_candidates(frame, evidence, existing):
    """Refine weak model proposals using large, convex tabletop-like contours."""
    if not evidence:
        return []
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if not .06 * width * height <= area <= .70 * width * height:
            continue
        polygon = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
        if not 4 <= len(polygon) <= 6 or not cv2.isContourConvex(polygon):
            continue
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        rect = cv2.minAreaRect(polygon)
        rectangle_area = rect[1][0] * rect[1][1]
        if hull_area <= 0 or area / hull_area < .90 or rectangle_area <= 0 or area / rectangle_area < .72:
            continue
        x, y, box_width, box_height = cv2.boundingRect(polygon)
        box = (x, y, min(width - 1, x + box_width), min(height - 1, y + box_height))
        if any(overlap(box, item["box"]) > .45 for item in existing + results):
            continue
        support = []
        for proposal in evidence:
            left, top, right, bottom = proposal["box"]
            intersection = max(0, min(box[2], right) - max(x, left)) * max(0, min(box[3], bottom) - max(y, top))
            if intersection / (box_width * box_height) >= .85:
                support.append(proposal)
        if not support:
            continue
        score = max(item["confidence"] for item in support)
        results.append({
            "box": box,
            "zone": [[round(float(p[0]) / width, 5), round(float(p[1]) / height, 5)]
                     for p in polygon[:, 0]],
            "confidence": score,
            "method": "surface_outline",
        })
    return results


def overlap(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    area = max(0, right - left) * max(0, bottom - top)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - area
    return area / union if union else 0


class Tracker:
    """Short-lived IDs based on spatial continuity in a single camera."""
    def __init__(self):
        self.active = {}
        self.sequence = 0

    def update(self, boxes, now):
        self.active = {key: v for key, v in self.active.items() if now - v[1] <= 2}
        pairs = sorted(((overlap(box, old), index, key)
                        for index, box in enumerate(boxes)
                        for key, (old, _) in self.active.items()), reverse=True)
        assigned, used = {}, set()
        for score, index, key in pairs:
            if score < .16:
                break
            if index not in assigned and key not in used:
                assigned[index] = key
                used.add(key)
        current = {}
        for index, box in enumerate(boxes):
            key = assigned.get(index)
            if key is None:
                self.sequence += 1
                key = self.sequence
            self.active[key] = box, now
            current[key] = box
        return current


def zone_contour(zone, w, h):
    return np.asarray([(x * w, y * h) for x, y in zone], dtype=np.float32)


def frame_is_obscured(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.percentile(gray[::4, ::4], 99)) < 14


def analyze(frame, people, tables, entrance):
    h, w = frame.shape[:2]
    contours = [(row, zone_contour(row["zone"], w, h)) for row in tables if len(row["zone"]) >= 3]
    counts = {row["id"]: 0 for row, _ in contours}
    entry = zone_contour(entrance, w, h) if len(entrance) >= 3 else None
    masks = []
    for row, poly in contours:
        x, y, width, height = cv2.boundingRect(poly)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [(poly - (x, y)).astype(np.int32)], 1)
        masks.append((row["id"], poly, mask, x, y, x + width, y + height))
    in_entry = {}
    for key, box in people.items():
        x1, y1, x2, y2 = box
        anchor = ((x1 + x2) / 2, y1 + (y2 - y1) * .80)
        area = max(1, (x2 - x1) * (y2 - y1))
        matches = []
        for table_id, poly, mask, x, y, right, bottom in masks:
            left, top, end_x, end_y = max(x, x1), max(y, y1), min(right, x2), min(bottom, y2)
            if end_x <= left or end_y <= top:
                continue
            coverage = cv2.countNonZero(mask[top-y:end_y-y, left-x:end_x-x]) / area
            inside = cv2.pointPolygonTest(poly, anchor, False) >= 0
            if coverage >= .19 or inside:
                matches.append((coverage + (.08 if inside else 0), table_id))
        if matches:
            _, table_id = max(matches)
            counts[table_id] += 1
        if entry is not None:
            in_entry[key] = cv2.pointPolygonTest(entry, ((x1 + x2) / 2, y2), False) >= 0
    return counts, in_entry, contours


def annotate(frame, people, contours, entrance, furniture=()):
    palette = dict(available=(120, 239, 177), occupied=(239, 196, 116),
                   waiting=(78, 194, 254), cleaning=(212, 141, 249))
    h, w = frame.shape[:2]
    for index, item in enumerate(furniture, 1):
        x1, y1, x2, y2 = item["box"]
        color = (225, 208, 134)
        if item.get("method") == "surface_outline":
            cv2.polylines(frame, [zone_contour(item["zone"], w, h).astype(np.int32)], True, color, 2)
            label = f"Table surface {index} - model {item['confidence']:.0%}"
        else:
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{item.get('label', 'Dining table')} {index} score {item['confidence']:.0%}"
        cv2.putText(frame, label, (x1, max(17, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, .48, color, 1)
    if entrance:
        cv2.polylines(frame, [zone_contour(entrance, w, h).astype(np.int32)], True, (235, 214, 135), 2)
    for row, contour in contours:
        poly = contour.astype(np.int32)
        color = palette[row["state"]]
        cv2.polylines(frame, [poly], True, color, 2, cv2.LINE_AA)
        x, y = poly[0]
        cv2.putText(frame, row["name"], (x + 4, max(18, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
    for key, (x1, y1, x2, y2) in people.items():
        color = (239, 223, 150)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        cv2.putText(frame, f"P{key}", (x1, max(15, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
    return frame


@dataclass(frozen=True)
class CameraView:
    status: str = "idle"
    message: str = "Start this camera to see the floor."
    people: int = 0
    frames: int = 0
    jpeg: bytes | None = None
    raw: bytes | None = None
    at: float = 0
    furniture: tuple = ()
    chairs: int = 0
    inference_ms: int = 0
    table_scan: dict | None = None


class LiveFrames:
    """Continuously drain the device and retain only its newest frame."""
    def __init__(self, capture):
        self.capture = capture
        self.condition = Condition()
        self.stop = Event()
        self.latest = None
        self.sequence = 0
        self.ended = False
        self.thread = Thread(target=self.read, daemon=True, name="camera-reader")
        self.thread.start()

    def read(self):
        try:
            while not self.stop.is_set():
                ok, frame = self.capture.read()
                if not ok:
                    break
                with self.condition:
                    self.sequence += 1
                    self.latest = self.sequence, time.time(), frame
                    self.condition.notify_all()
        finally:
            with self.condition:
                self.ended = True
                self.condition.notify_all()

    def next(self, previous):
        with self.condition:
            self.condition.wait_for(lambda: self.sequence > previous or self.ended, timeout=.25)
            return self.latest if self.sequence > previous else None

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.capture.release()
            self.thread.join(timeout=1)


class CameraWorker:
    def __init__(self, store, camera, get_detector):
        self.store, self.camera, self.get_detector = store, camera, get_detector
        self.stop = Event()
        self.view = CameraView("starting", "Opening camera…")
        self.thread = Thread(target=self.run, daemon=True, name=f"camera-{camera['id']}")
        self.thread.start()

    def capture(self):
        source = self.camera["source"]
        kind = self.camera["kind"]
        if kind == "webcam":
            cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(int(source))
            if not cap.isOpened() and os.name == "nt":
                cap.release()
                cap = cv2.VideoCapture(int(source), cv2.CAP_MSMF)
            return cap
        if kind == "rtsp":
            return cv2.VideoCapture(source, cv2.CAP_FFMPEG,
                                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4500, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4500])
        return cv2.VideoCapture(str(ROOT / "demo/restaurant.mp4"))

    @staticmethod
    def jpeg(frame):
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok else None

    def run(self):
        camera_id = self.camera["id"]
        frames = 0
        video = self.camera["kind"] == "sample"
        try:
            detector = self.get_detector()
            while not self.stop.is_set():
                cap = self.capture()
                try:
                    frames, done = self.process(cap, detector, frames, video)
                finally:
                    cap.release()
                self.store.camera_offline(camera_id)
                if done or self.stop.is_set():
                    break
                self.view = CameraView("reconnecting", "Camera signal lost. Reconnecting…", frames=frames)
                self.stop.wait(2)
        except Exception as exc:
            self.store.camera_offline(camera_id)
            message = "The local vision model could not load." if frames == 0 and isinstance(exc, cv2.error) else "Camera processing stopped. Check camera setup and restart."
            self.view = CameraView("error", message, frames=frames)
        if self.stop.is_set():
            self.view = CameraView("idle", "Camera stopped.", frames=frames)

    def process(self, cap, detector, frames, video):
        reader = None if video else LiveFrames(cap)
        self.table_scanner = None if video else TableScanner()
        try:
            return self.process_frames(cap, detector, frames, video, reader)
        finally:
            if reader:
                reader.close()
            if self.table_scanner:
                self.table_scanner.close()

    def process_frames(self, cap, detector, frames, video, reader):
        tracker, entry_state, counted = Tracker(), {}, set()
        fps = cap.get(cv2.CAP_PROP_FPS) or 24
        stride = max(1, round(fps / 6)) if video else 1
        clock = time.monotonic()
        index = 0
        sequence = 0
        while not self.stop.is_set():
            if reader:
                record = reader.next(sequence)
                if record is None:
                    if reader.ended:
                        return frames, False
                    continue
                sequence, captured_at, frame = record
                ok = True
            else:
                ok, frame = cap.read()
                captured_at = time.time()
            if not ok:
                if video:
                    prev = self.view
                    self.view = CameraView("complete" if index else "error",
                        "Sample finished. The last frame is shown." if index else "The sample file could not be opened.",
                        prev.people, frames, prev.jpeg, prev.raw, prev.at,
                        prev.furniture, prev.chairs, prev.inference_ms)
                    return frames, True
                return frames, False
            index += 1
            if (index - 1) % stride:
                continue
            if video and self.stop.wait(max(0, clock + (index - 1) / fps - time.monotonic())):
                break
            height, width = frame.shape[:2]
            if width > 960:
                frame = cv2.resize(frame, (960, max(1, int(height * 960 / width))), interpolation=cv2.INTER_AREA)
            if frame_is_obscured(frame):
                self.store.camera_offline(self.camera["id"])
                raw = self.jpeg(frame)
                frames += 1
                self.view = CameraView("obscured", "Camera view is too dark or covered. Uncover the lens and improve lighting.",
                                       frames=frames, jpeg=raw, raw=raw, at=captured_at)
                self.stop.wait(.15)
                continue
            now = time.time()
            inference_start = time.perf_counter()
            scene = detector.detect_scene(frame, .19 if video else .26)
            inference_ms = round(1000 * (time.perf_counter() - inference_start))
            scan = None
            if self.table_scanner:
                broad, scan = self.table_scanner.update(frame, captured_at, people=scene['people'])
                # Prefer the broader result for duplicate objects.
                scene['tables'] = broad + [item for item in scene['tables']
                    if not any(overlap(item['box'], other['box']) > .40 for other in broad)]
            people = tracker.update(scene["people"], captured_at)
            candidates = [dict(id=i, zone=item["zone"]) for i, item in enumerate(scene["tables"])]
            candidate_counts, _, _ = analyze(frame, people, candidates, [])
            candidate_surfaces = assess_clearance(frame,candidate_counts,candidates,scene['items'],scene['tables'])
            for i, item in enumerate(scene["tables"]):
                item["people"] = candidate_counts[i]
                item['surface'] = dict(candidate_surfaces[i],at=captured_at)
            entrance, tables = self.store.camera_config(self.camera["id"])
            counts, inside, contours = analyze(frame, people, tables, entrance)
            surface_checks=assess_clearance(frame,counts,tables,scene['items'],scene['tables'])
            for key in list(entry_state):
                if key not in tracker.active:
                    entry_state.pop(key)
                    counted.discard(key)
            arrivals = {key for key, entering in inside.items()
                        if entering and entry_state.get(key) is False and key not in counted}
            entry_state.update(inside)
            counted.update(arrivals)
            self.store.observe(self.camera["id"], counts, captured_at, entries=len(arrivals))
            self.store.observe_surfaces(self.camera['id'],surface_checks,captured_at,
                                        expected_zones={table['id']:table['zone'] for table in tables})
            raw = self.jpeg(frame)
            rendered = self.jpeg(annotate(frame, people, contours, entrance, scene["tables"]))
            frames += 1
            self.view = CameraView("live", "Live camera · local person and table detection",
                                   len(people), frames, rendered, raw, captured_at,
                                   tuple(scene["tables"]), len(scene["chairs"]), inference_ms, scan)
            if not video:
                self.stop.wait(.08)
        return frames, True


class Cameras:
    def __init__(self, store):
        self.store = store
        self.lock = Lock()
        self.model_lock = Lock()
        self.model = None
        self.workers = {}

    def get_detector(self):
        with self.model_lock:
            if self.model is None:
                self.model = PersonDetector()
            return self.model

    def start(self, camera_id):
        camera = self.store.camera(camera_id)
        with self.lock:
            worker = self.workers.get(camera_id)
            if worker and worker.thread.is_alive():
                if worker.stop.is_set():
                    return "stopping"
                return worker.view.status
            if camera["kind"] == "webcam":
                for active in self.workers.values():
                    if (active.thread.is_alive() and active.camera["kind"] == "webcam"
                            and active.camera["source"] == camera["source"]):
                        from store import Conflict
                        raise Conflict("That webcam is already in use.")
            self.workers[camera_id] = CameraWorker(self.store, camera, self.get_detector)
            return "starting"

    def stop(self, camera_id):
        self.store.camera(camera_id)
        with self.lock:
            worker = self.workers.get(camera_id)
            if worker:
                worker.stop.set()
                if not worker.thread.is_alive():
                    worker.view = CameraView()

    def view(self, camera_id):
        with self.lock:
            worker = self.workers.get(camera_id)
            if not worker:
                return CameraView()
            view = worker.view
            if worker.stop.is_set() and worker.thread.is_alive():
                return CameraView("stopping", "Closing camera…", frames=view.frames)
            if view.status == "live" and time.time() - view.at > 5:
                return CameraView("reconnecting", "Waiting for a fresh frame.", frames=view.frames)
            return view

    def shutdown(self):
        with self.lock:
            workers = list(self.workers.values())
        for worker in workers:
            worker.stop.set()
        for worker in workers:
            worker.thread.join(timeout=6)

