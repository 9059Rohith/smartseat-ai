"""Ephemeral uploaded-frame inference. Never writes camera or restaurant state."""
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import secrets
from threading import BoundedSemaphore, Lock
import time
import warnings

import cv2
import numpy as np
from PIL import Image
from fastapi import HTTPException

from broad_tables import MODEL, GroundedTables, TableScanner
from vision import analyze, assess_clearance, frame_is_obscured, overlap

MAX_REQUEST = 1048576
COLORS = {'occupied':'#fb7185','items_present':'#fbbf24','looks_clear':'#86efac','unknown':'#a8b3bd'}


def decode_frame(value):
    if not isinstance(value,str) or not value.startswith('data:image/jpeg;base64,') or len(value)>1000000:
        raise HTTPException(422,'Choose an image or a video frame that can be decoded as JPEG.')
    try:
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        if not raw.startswith(b'\xff\xd8') or len(raw)>750000:raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                w,h=image.size
                if image.format!='JPEG' or not 16<=w<=2048 or not 16<=h<=2048 or w*h>4194304:raise ValueError()
                image.verify()
        frame=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        if frame is None or frame.shape[:2]!=(h,w):raise ValueError()
        return frame
    except (ValueError,binascii.Error,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Invalid JPEG frame. Use an image up to 2048 × 2048 pixels.') from None


def summarize_frame(frame,scene,*,frame_time=0,broad_status='not_requested'):
    h,w=frame.shape[:2]
    tables=[dict(item,id=index+1) for index,item in enumerate(scene['tables'])]
    counts,_,_=analyze(frame,dict(enumerate(scene['people'],1)),tables,[])
    surface=assess_clearance(frame,counts,tables,scene['items'],tables)
    output=[]
    for item in tables:
        result=surface[item['id']];state=result['state']
        output.append({**item,'state':state,'color':COLORS[state],
                       'people':counts.get(item['id'],0),'items':result['items']})
    summary={key:sum(item['state']==key for item in output) for key in COLORS}
    summary.update(tables=len(output),people=len(scene['people']),chairs=len(scene['chairs']))
    return {'width':w,'height':h,'frame_time':frame_time,'view':'clear','tables':output,
            'people':[{'box':box} for box in scene['people']],'summary':summary,'broad_status':broad_status}


def infer_frame(frame,get_detector,*,broad=False,frame_time=0):
    start=time.perf_counter()
    if frame_is_obscured(frame):
        result=summarize_frame(frame,{'tables':[],'people':[],'chairs':[],'items':[]},frame_time=frame_time)
        result['view']='blocked';return result
    # Uploaded stills lack temporal confirmation; be more conservative about
    # person overlap than the continuous live-camera tracker.
    scene=get_detector().detect_scene(frame,confidence=.4)
    status='not_requested'
    if broad:
        if not (MODEL/'model.safetensors').is_file():status='unavailable'
        else:
            with TableScanner.model_lock:
                if TableScanner.model is None:TableScanner.model=GroundedTables()
                candidates=TableScanner.model.detect(frame)
            for item in candidates:
                if not any(overlap(item['box'],old['box'])>.45 for old in scene['tables']):scene['tables'].append(item)
            status='complete'
    result=summarize_frame(frame,scene,frame_time=frame_time,broad_status=status)
    result['inference_ms']=round((time.perf_counter()-start)*1000)
    return result


class MediaJobs:
    def __init__(self,get_detector,*,clock=time.monotonic,ttl=300,max_jobs=20):
        self.get_detector=get_detector;self.clock=clock;self.ttl=ttl;self.max_jobs=max_jobs
        self.lock=Lock();self.slots=BoundedSemaphore(2);self.jobs={};self.closed=False
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='media-analysis')

    def _prune(self):
        now=self.clock()
        for key in [key for key,job in self.jobs.items() if now-job['created']>self.ttl]:
            self.jobs.pop(key)

    def submit(self,owner,frame,*,broad=False,frame_time=0):
        with self.lock:
            self._prune()
            if self.closed or len(self.jobs)>=self.max_jobs or not self.slots.acquire(blocking=False):
                raise HTTPException(429,'Media analysis is busy. Finish or clear an existing analysis and try again.')
            key=secrets.token_urlsafe(20)
            self.jobs[key]={'id':key,'owner':owner,'created':self.clock(),'status':'queued'}
        try:self.pool.submit(self._run,key,frame,broad,frame_time)
        except RuntimeError:
            with self.lock:self.jobs.pop(key,None)
            self.slots.release();raise HTTPException(503,'Media analysis is stopping.') from None
        return {'id':key,'status':'queued'}

    def _run(self,key,frame,broad,frame_time):
        try:
            with self.lock:
                if key not in self.jobs:return
                self.jobs[key]['status']='running'
            result=infer_frame(frame,self.get_detector,broad=broad,frame_time=frame_time)
            with self.lock:
                if key in self.jobs:self.jobs[key].update(status='done',result=result)
        except Exception:
            with self.lock:
                if key in self.jobs:self.jobs[key].update(status='error',error='The local model could not analyze this frame. Try the fast scan or check the engine.')
        finally:self.slots.release()

    def get(self,key,owner):
        with self.lock:
            self._prune();job=self.jobs.get(key)
            if not job or job['owner']!=owner:raise HTTPException(404,'This media analysis is unavailable or expired.')
            return {k:v for k,v in job.items() if k not in ('owner','created')}

    def delete(self,key,owner):
        with self.lock:
            job=self.jobs.get(key)
            if not job or job['owner']!=owner:raise HTTPException(404,'This media analysis is unavailable or expired.')
            self.jobs.pop(key)

    def close(self):
        with self.lock:self.closed=True;self.jobs.clear()
        self.pool.shutdown(wait=False,cancel_futures=True)
