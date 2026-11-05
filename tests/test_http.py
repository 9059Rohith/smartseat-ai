import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app


class HttpWorkflowTest(unittest.TestCase):
    def test_live_workspace_contains_only_the_requested_camera(self):
        app = create_app(self.db.parent / "clean-live.sqlite3", webcam=True)
        snapshot = app.state.store.snapshot()
        self.assertEqual([c["kind"] for c in snapshot["cameras"]], ["webcam"])
        for collection in ("tables", "queue", "reservations", "events"):
            self.assertEqual(snapshot[collection], [])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "pilot.sqlite3"
        self.app = create_app(self.db)
        self.app.state.store.add_user("manager", "test-only-password", "manager")
        self.app.state.store.add_user("staff", "test-staff-password", "staff")
        self.client = TestClient(self.app, base_url="http://127.0.0.1")
        self.addCleanup(self.client.close)

    def login(self, staff=False):
        name, password = ("staff", "test-staff-password") if staff else ("manager", "test-only-password")
        response = self.client.post("/api/login", json={"name": name, "password": password})
        self.assertEqual(response.status_code, 200, response.text)

    def test_private_camera_and_manager_actions(self):
        self.assertEqual(self.client.get('/api/health').json().get('app'), 'smartseat')
        self.assertEqual(self.client.get("/api/state").status_code, 401)

        self.assertEqual(self.client.get("/api/cameras/1/frame").status_code, 401)
        self.assertEqual(self.client.get("/api/health", headers={"host": "external.example"}).status_code, 400)
        self.login(staff=True)
        self.assertEqual(self.client.post("/api/cameras", json={
            "kind": "webcam", "source": "0", "name": "Office"
        }).status_code, 403)
        self.assertEqual(self.client.post("/api/queue", json={"name": "Party", "size": 2},
                                          headers={"origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/state").status_code, 401)

    def test_public_gateway_keeps_host_and_origin_restrictions(self):
        app=create_app(self.db,public_hosts=['engine.example'],public_origins=['https://restaurant.example'])
        client=TestClient(app,base_url='https://engine.example')
        self.addCleanup(client.close)
        login={'name':'manager','password':'test-only-password'}
        response=client.post('/api/login',json=login,headers={'origin':'https://restaurant.example'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('Secure',response.headers['set-cookie'])
        self.assertEqual(client.get('/api/state').status_code,200)
        self.assertEqual(client.get('/api/health',headers={'host':'evil.example'}).status_code,400)
        self.assertEqual(client.post('/api/logout',headers={'origin':'https://evil.example'}).status_code,403)
        self.assertEqual(client.post('/api/logout',headers={'origin':'https://restaurant.example'}).status_code,200)

    def test_reservation_conflict_and_waitlist_end_to_end(self):
        self.login()
        table = self.client.post("/api/tables", json={"name": "T1", "capacity": 4}).json()["id"]
        start = datetime.now(timezone.utc) + timedelta(minutes=2)
        booking = {"name": "First", "size": 2, "table": table,
                   "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat()}
        reserve = self.client.post("/api/reservations", json=booking)
        self.assertEqual(reserve.status_code, 201, reserve.text)
        self.assertEqual(self.client.post("/api/reservations", json=booking).status_code, 409)
        party = self.client.post("/api/queue", json={"name": "Walk-in", "size": 3}).json()["id"]
        assign = {"table": table, "action": "seat"}
        self.assertEqual(self.client.post(f"/api/queue/{party}/assign", json=assign).status_code, 409)
        self.assertEqual(self.client.post(f"/api/reservations/{reserve.json()['id']}/cancel").status_code, 200)
        self.assertEqual(self.client.post(f"/api/queue/{party}/assign", json=assign).status_code, 200)
        for action in ("greet", "depart", "clean"):
            self.assertEqual(self.client.post(f"/api/tables/{table}/{action}").status_code, 200)
        report = self.client.get("/api/analytics", params={"start": time.time() - 60, "end": time.time()}).json()
        self.assertEqual(report["turnover"], 1)
        self.assertIsNotNone(report["wait"])
        self.assertIsNotNone(report["cleaning"])
        restored = create_app(self.db)
        self.assertEqual(restored.state.store.snapshot()["tables"][0]["state"], "available")

