"""Local open-vocabulary table scans, independent of the live person detector."""
import logging
import os
from pathlib import Path
from threading import Condition, Event, Lock, Thread
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / 'models/grounding-dino-tiny'


def _valid_box(box, frame):
    x1,y1,x2,y2=box
    return 0<=x1<x2<=frame.shape[1] and 0<=y1<y2<=frame.shape[0]


def _view_context(reference, current, age, boxes, people):
    """Check shared camera/background evidence once, before testing each object."""
    if not 0<=age<=30 or reference.shape!=current.shape:
        return None
    mask = None
    h,w=reference.shape[:2]
    if people:
        mask=np.ones((h,w),np.uint8)
        margin=max(4,round(min(h,w)*.015))
        for left,top,right,bottom in people:
            x1,y1=max(0,int(left)-margin),max(0,int(top)-margin)
            x2,y2=min(w,int(right)+margin),min(h,int(bottom)+margin)
            if x2>x1 and y2>y1:mask[y1:y2,x1:x2]=0
        if np.count_nonzero(mask)<.20*mask.size:return None
    background=mask.copy() if mask is not None else np.ones((h,w),np.uint8)
    for box in boxes:
        if _valid_box(box,reference):
            x1,y1,x2,y2=box;background[y1:y2,x1:x2]=0
    # A changed object must not masquerade as a camera change for every other
    # object. If a close-up fills the image, retain the conservative global check.
    comparison=background if np.count_nonzero(background)>=.25*background.size else mask
    def thumb(frame):
        return cv2.cvtColor(cv2.resize(frame,(96,72)),cv2.COLOR_BGR2GRAY)
    difference=cv2.absdiff(thumb(reference),thumb(current))
    if comparison is not None:
        visible=cv2.resize(comparison.astype(np.float32),(96,72),interpolation=cv2.INTER_AREA)>.995
        if np.count_nonzero(visible)<.20*visible.size:return None
        difference=difference[visible]
    if float(np.mean(difference)) >= 12 or float(np.percentile(difference, 95)) >= 40:
        return None
    return (mask,)


def _region_matches(reference,current,box,context):
    if not _valid_box(box,reference):return False
    x1,y1,x2,y2=box;mask=context[0];visible=None
    if mask is not None:
        region=mask[y1:y2,x1:x2]
        if np.count_nonzero(region)<max(64,.35*region.size):return False
        visible=cv2.resize(region.astype(np.float32),(64,48),interpolation=cv2.INTER_AREA)>.995
        if np.count_nonzero(visible)<.35*visible.size:return False
    left=cv2.resize(reference[y1:y2,x1:x2],(64,48))
    right=cv2.resize(current[y1:y2,x1:x2],(64,48))
    difference=cv2.absdiff(left,right)
    if visible is not None:difference=difference[visible]
    return float(np.mean(difference))<18


def result_matches_view(reference,current,age,boxes=(),*,people=()):
    """Reuse only still-visible image evidence, excluding detected people."""
    context=_view_context(reference,current,age,boxes,people)
    return context is not None and all(_region_matches(reference,current,box,context) for box in boxes)


class GroundedTables:
    def __init__(self):
        # Offline is mandatory at runtime. Only the setup script downloads public weights.
        os.environ.update(USE_TF='0', USE_FLAX='0', HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        torch.set_num_threads(2)
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(MODEL, local_files_only=True)
        self.processor.image_processor.size = {'shortest_edge': 320, 'longest_edge': 512}
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(MODEL, local_files_only=True).eval()

    def detect(self, frame):
        from PIL import Image
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        inputs = self.processor(images=image, text='table. desk.', return_tensors='pt')
        with self.torch.inference_mode():
            outputs = self.model(**inputs)
        result = self.processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, box_threshold=.28, text_threshold=.22,
            target_sizes=[image.size[::-1]])[0]
        h, w = frame.shape[:2]
        items = []
        for score, box, label in sorted(zip(result['scores'].tolist(), result['boxes'].tolist(), result['labels']), reverse=True):
            x1, y1, x2, y2 = [int(n) for n in box]
            x1, x2 = max(0, x1), min(w-1, x2)
            y1, y2 = max(0, y1), min(h-1, y2)
            if x2-x1 < 12 or y2-y1 < 12:
                continue
            # The same object can have both table and desk proposals.
            area = (x2-x1)*(y2-y1)
            duplicate = False
            for old in items:
                a,b,c,d = old['box']
                intersection = max(0,min(c,x2)-max(a,x1))*max(0,min(d,y2)-max(b,y1))
                if intersection / min(area,(c-a)*(d-b)) > .75:
                    duplicate = True
                    break
            if not duplicate:
                items.append({'box':(x1,y1,x2,y2), 'zone':[[x1/w,y1/h],[x2/w,y1/h],[x2/w,y2/h],[x1/w,y2/h]],
                              'confidence':round(score,3),'method':'open_vocabulary',
                              'label':'Desk' if 'desk' in label and 'table' not in label else 'Table'})
        return items


class TableScanner:
    """Latest-frame-only queue; no historical image can become the live feed."""
    model = None
    model_lock = Lock()

    def __init__(self):
        self.condition = Condition()
        self.stop = Event()
        self.pending = None
        self.result = None
        self.busy = False
        self.next_at = 0
        self.status = 'loading' if (MODEL / 'model.safetensors').is_file() else 'unavailable'
        self.thread = Thread(target=self.run, daemon=True, name='broad-table-scan')
        if self.status != 'unavailable':
            self.thread.start()

    def run(self):
        try:
            with self.model_lock:
                if TableScanner.model is None:
                    TableScanner.model = GroundedTables()
            self.status = 'ready'
            while not self.stop.is_set():
                with self.condition:
                    self.condition.wait_for(lambda: self.pending is not None or self.stop.is_set(), timeout=.5)
                    if self.stop.is_set():
                        break
                    if self.pending is None:
                        continue
                    frame, captured_at, people = self.pending
                    self.pending = None
                    self.busy = True
                self.status = 'scanning'
                start = time.perf_counter()
                with self.model_lock:
                    items = TableScanner.model.detect(frame)
                self.result = (frame, captured_at, items, round((time.perf_counter()-start)*1000), people)
                self.status = 'ready'
                self.busy = False
                self.next_at = time.time()+.5
        except Exception:
            logging.getLogger(__name__).exception('Local broad table scanner failed')
            self.status = 'error'
            self.busy = False

    def update(self, frame, captured_at, *, people=()):
        if self.status not in ('unavailable', 'error') and not self.busy and time.time() >= self.next_at:
            with self.condition:
                # Replace pending frames even during model loading; never accumulate a backlog.
                self.pending = frame.copy(), captured_at, tuple(tuple(box) for box in people)
                self.condition.notify()
        result = self.result
        if result:
            reference, at, items, milliseconds, prior_people = result
            age = time.time()-at
            exclusions=tuple(prior_people)+tuple(people)
            context=_view_context(reference,frame,age,[item['box'] for item in items],exclusions)
            valid=[item for item in items if context is not None and _region_matches(reference,frame,item['box'],context)]
            if valid or (not items and context is not None):
                return [dict(item, scan_at=at) for item in valid], {'status':self.status,'at':at,'ms':milliseconds,'matched':True}
            return [], {'status':self.status,'at':at,'ms':milliseconds,'matched':False}
        return [], {'status':self.status,'at':None,'ms':None,'matched':False}

    def close(self):
        self.stop.set()
        with self.condition:
            self.condition.notify_all()
