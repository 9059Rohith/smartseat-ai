import json
from pathlib import Path
import tempfile
import time
import unittest
from fastapi.testclient import TestClient
from app import create_app

class OperationalStatusTest(unittest.TestCase):
    def test_status_is_manager_only_and_does_not_return_unapproved_file_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);status=root/'status';status.mkdir()
            (status/'monitor-status.json').write_text(json.dumps({'at':'2026-11-05T12:00:00Z','state':'degraded','issues':['camera_blocked'],'password':'must-not-leak'}))
            (status/'backup-status.json').write_text(json.dumps({'ok':True,'at':'2026-11-05T12:00:00Z','secret':'must-not-leak'}))
            app=create_app(root/'db.sqlite',operations_dir=status)
            app.state.store.add_user('manager','test-only-password','manager');app.state.store.add_user('staff','test-staff-password','staff')
            with TestClient(app,base_url='http://127.0.0.1') as client:
                self.assertEqual(client.get('/api/operations').status_code,401)
                client.post('/api/login',json={'name':'staff','password':'test-staff-password'})
                self.assertEqual(client.get('/api/operations').status_code,403)
                client.post('/api/login',json={'name':'manager','password':'test-only-password'})
                response=client.get('/api/operations');self.assertEqual(response.status_code,200)
                self.assertNotIn('must-not-leak',response.text)
                self.assertEqual(response.json()['monitor']['issues'],['camera_blocked'])
                self.assertFalse(response.json()['retention']['delete_enabled'])

    def test_retention_preview_counts_only_and_preserves_operational_records(self):
        from operational import retention_preview
        from store import Store
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db.sqlite');table=store.add_table('Isolated test table',2,None,[])
            old=time.time()-100*86400
            with store.db(True) as db:
                db.execute('INSERT INTO visits(table_id,started,ended,cleaned) VALUES(?,?,?,?)',(table,old,old+10,old+20))
            preview=retention_preview(store)
            self.assertFalse(preview['delete_enabled']);self.assertEqual(preview['candidates']['completed_visits'],1)
            with store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM visits').fetchone()[0],1)

    def test_public_health_contains_capture_status_without_camera_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app(Path(directory)/'db.sqlite');app.state.store.add_camera('Private camera name','rtsp','rtsp://private:secret@example.invalid/stream')
            with TestClient(app,base_url='http://127.0.0.1') as client:
                response=client.get('/api/health');self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['capture']['configured'],1)
                self.assertNotIn('secret',response.text);self.assertNotIn('Private camera name',response.text)
