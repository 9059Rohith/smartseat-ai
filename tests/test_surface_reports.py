import tempfile
from pathlib import Path
import unittest
import cv2
import numpy as np
from datetime import datetime,timedelta,timezone
from store import Store
from vision import assess_clearance


class SurfaceReportTest(unittest.TestCase):
    def test_objects_require_visible_table_and_do_not_certify_cleaning(self):
        frame = np.full((100,100,3),120,np.uint8)
        zone = [[.1,.1],[.9,.1],[.9,.9],[.1,.9]]
        regions = [{'id':1,'zone':zone}]
        table = {'box':(10,10,90,90),'zone':zone}
        item = {'box':(30,30,45,45),'label':'cup','confidence':.8}
        self.assertEqual(assess_clearance(frame,{1:0},regions,[item],[table])[1]['state'],'items_present')
        self.assertEqual(assess_clearance(frame,{1:0},regions,[],[table])[1]['state'],'looks_clear')
        self.assertEqual(assess_clearance(frame,{1:1},regions,[],[table])[1]['state'],'occupied')
        self.assertEqual(assess_clearance(frame,{1:0},regions,[],[])[1]['state'],'unknown')

    def test_daily_report_splits_visits_across_local_midnight(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder)/'test.sqlite')
            table = store.add_table('Actual test table',4,None,[])
            # 2026-11-01 23:50 in UTC+05:30, twenty minute visit.
            start = datetime(2026,11,1,23,50,tzinfo=timezone(timedelta(minutes=330))).timestamp()
            with store.db(True) as db:
                db.execute('UPDATE tables SET created=?',(start-86400,))
                db.execute('INSERT INTO visits(table_id,started,greeted,ended,cleaned,party_size) VALUES(?,?,?,?,?,?)',
                           (table,start,start+60,start+1200,start+1500,3))
            report = store.report(start-600,start+2400,timezone_offset=330)
            self.assertEqual(sum(day['seatings'] for day in report['daily']),1)
            self.assertEqual(sum(day['guests'] for day in report['daily']),3)
            self.assertEqual(sum(day['cleaned'] for day in report['daily']),1)
            self.assertEqual(sum(day['occupied_seconds'] for day in report['daily']),1200)
            self.assertEqual(len(report['daily']),2)
            self.assertEqual((report['hourly'][0]['hour']+330*60)%3600,0)

    def test_surface_check_expires_and_cannot_reset_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite'); camera=store.add_camera('Real setup','webcam','0')
            table=store.add_table('T1',4,camera,[[0,0],[1,0],[1,1],[0,1]])
            store.table_action(table,'occupy',100);store.table_action(table,'depart',110)
            zone=[[0,0],[1,0],[1,1],[0,1]]
            store.observe_surfaces(camera,{table:{'state':'looks_clear','items':[]}},111,expected_zones={table:zone})
            self.assertEqual(store.snapshot(112)['tables'][0]['surface']['state'],'looks_clear')
            self.assertEqual(store.snapshot(112)['tables'][0]['state'],'cleaning')
            self.assertEqual(store.snapshot(120)['tables'][0]['surface']['state'],'unknown')
            store.camera_offline(camera)
            self.assertEqual(store.snapshot(112)['tables'][0]['surface']['state'],'unknown')

    def test_zone_edit_rejects_in_flight_old_clearance(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite');camera=store.add_camera('Camera','webcam','0')
            old=[[0,0],[1,0],[1,1],[0,1]];new=[[.1,.1],[.5,.1],[.5,.5],[.1,.5]]
            table=store.add_table('T1',2,camera,old)
            store.edit_table(table,'T1',2,camera,new,True)
            checks={table:{'state':'looks_clear','items':[]}}
            store.observe_surfaces(camera,checks,100,expected_zones={table:old})
            self.assertEqual(store.snapshot(101)['tables'][0]['surface']['state'],'unknown')
            store.observe_surfaces(camera,checks,102,expected_zones={table:new})
            self.assertEqual(store.snapshot(103)['tables'][0]['surface']['state'],'looks_clear')

    def test_departure_at_report_start_counts_once(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite');table=store.add_table('T1',2,None,[],now=0)
            with store.db(True) as db:
                db.execute('INSERT INTO visits(table_id,started,ended,cleaned) VALUES(?,?,?,?)',(table,10,100,101))
            report=store.report(100,200)
            self.assertEqual(report['turnover'],1)
            self.assertEqual(report['dining'],90)
            self.assertEqual(report['daily'][0]['occupied_seconds'],0)
            self.assertEqual(report['daily'][0]['turnover'],1)


if __name__=='__main__':unittest.main()
