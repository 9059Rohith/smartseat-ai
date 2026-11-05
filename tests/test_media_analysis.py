import base64
import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from app import create_app
from media_analysis import infer_frame
from vision import PersonDetector
from media_analysis import MediaJobs
from threading import Event
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[1]


def jpeg(frame):
    ok,data=cv2.imencode('.jpg',frame)
    assert ok
    return 'data:image/jpeg;base64,'+base64.b64encode(data).decode()


class MediaHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=create_app(Path(self.temp.name)/'media.sqlite3')
        self.app.state.store.add_user('manager','media-test-password','manager')
        self.app.state.store.add_user('staff','media-staff-password','staff')
        self.client=TestClient(self.app,base_url='http://127.0.0.1')
        self.addCleanup(self.client.close)
        self.addCleanup(lambda:getattr(self.app.state,'media',None) and self.app.state.media.close())

    def login(self,client=None,staff=False):
        result=(client or self.client).post('/api/login',json={'name':'staff' if staff else 'manager',
            'password':'media-staff-password' if staff else 'media-test-password'})
        self.assertEqual(result.status_code,200)

    def wait(self,job):
        for _ in range(600):
            response=self.client.get('/api/media/jobs/'+job)
            self.assertEqual(response.status_code,200,response.text)
            result=response.json()
            if result['status'] not in ('queued','running'):return result
            time.sleep(.1)
        self.fail('Media analysis did not finish')

    def test_authentication_precedes_image_parsing(self):
        self.assertEqual(self.client.post('/api/media/analyze',content=b'not json').status_code,401)

    def test_real_photo_returns_actual_boxes_without_mutating_restaurant(self):
        self.login();before=self.app.state.store.snapshot()
        frame=cv2.imread(str(ROOT/'evaluation/public-images/picnic-outdoor.jpg'))
        response=self.client.post('/api/media/analyze',json={'image':jpeg(frame),'broad':False,'frame_time':0})
        self.assertEqual(response.status_code,202,response.text)
        job=response.json()['id'];result=self.wait(job)
        self.assertEqual(result['status'],'done',result)
        data=result['result'];self.assertGreater(data['summary']['tables'],0)
        self.assertEqual(data['summary']['tables'],len(data['tables']))
        self.assertEqual(sum(data['summary'][k] for k in ('occupied','items_present','looks_clear','unknown')),len(data['tables']))
        after=self.app.state.store.snapshot()
        self.assertEqual({k:v for k,v in before.items() if k!='now'},
                         {k:v for k,v in after.items() if k!='now'})
        other=TestClient(self.app,base_url='http://127.0.0.1');self.addCleanup(other.close)
        self.login(other,staff=True)
        self.assertEqual(other.get('/api/media/jobs/'+job).status_code,404)
        self.assertEqual(other.delete('/api/media/jobs/'+job).status_code,404)
        self.assertEqual(self.client.delete('/api/media/jobs/'+job).status_code,200)
        self.assertEqual(self.client.get('/api/media/jobs/'+job).status_code,404)

    def test_blocked_image_reports_unverified_not_cleaned(self):
        self.login()
        response=self.client.post('/api/media/analyze',json={'image':jpeg(np.zeros((64,64,3),np.uint8)),'broad':False})
        self.assertEqual(response.status_code,202,response.text)
        result=self.wait(response.json()['id'])['result']
        self.assertEqual(result['view'],'blocked')
        self.assertEqual(result['summary']['tables'],0)
        self.assertEqual(result['summary']['looks_clear'],0)

    def test_invalid_and_oversized_images_are_rejected(self):
        self.login()
        for body in [{'image':'garbage'},{'image':'data:image/jpeg;base64,aGVsbG8='},
                     {'image':jpeg(np.zeros((32,32,3),np.uint8)),'frame_time':-1}]:
            self.assertIn(self.client.post('/api/media/analyze',json=body).status_code,(400,422))
        self.assertEqual(self.client.post('/api/media/analyze',content=b'x'*1048577,
            headers={'content-type':'application/json','content-length':'2'}).status_code,413)
        huge=jpeg(np.full((2100,2100,3),100,np.uint8))
        self.assertEqual(self.client.post('/api/media/analyze',json={'image':huge}).status_code,422)

    def test_empty_round_table_chair_is_not_reported_as_person_overlap(self):
        frame=cv2.imread(str(ROOT/'evaluation/public-images/round-dining.jpg'))
        result=infer_frame(frame,PersonDetector)
        self.assertEqual(result['summary']['people'],0)

    def test_jobs_bound_work_and_expire_without_exposing_other_users(self):
        gate=Event();now=[0]
        def detector():
            gate.wait(10)
            return PersonDetector()
        jobs=MediaJobs(detector,clock=lambda:now[0]);self.addCleanup(jobs.close);self.addCleanup(gate.set)
        frame=np.full((64,64,3),100,np.uint8)
        first=jobs.submit('one',frame)['id'];second=jobs.submit('one',frame)['id']
        with self.assertRaises(HTTPException) as full:jobs.submit('one',frame)
        self.assertEqual(full.exception.status_code,429)
        with self.assertRaises(HTTPException) as hidden:jobs.get(first,'two')
        self.assertEqual(hidden.exception.status_code,404)
        jobs.delete(first,'one')
        with self.assertRaises(HTTPException):jobs.submit('one',frame)
        gate.set()
        for _ in range(100):
            if jobs.get(second,'one')['status']=='done':break
            time.sleep(.1)
        self.assertEqual(jobs.get(second,'one')['status'],'done')
        now[0]=301
        with self.assertRaises(HTTPException):jobs.get(second,'one')
