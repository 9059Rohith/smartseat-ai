"""Watchdog safety, incident privacy, and recovery behavior."""
import json
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path

from operations.watchdog import Monitor, Probe, ProcessLock, probe_health
from store import SCHEMA


HEALTHY = {"app": "smartseat", "capture": {"configured": 1, "live": 1,
           "blocked": 0, "unavailable": 0, "stopped": 0}}


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "local").mkdir()
        with closing(sqlite3.connect(self.root / "local/smartseat.sqlite3")) as db:
            db.executescript(SCHEMA)
            db.execute("insert into users values('test-manager','existing-hash','manager')")
            db.commit()
        (self.root / "local/public-connection.json").write_text(json.dumps({
            "engine_origin": "https://example.test/smartseat-engine"}))
        self.probes = [Probe("ok", HEALTHY), Probe("ok", {"app": "smartseat-router"}),
                       Probe("ok", HEALTHY)]
        self.calls = []
        self.repairs = []
        self.now = 1000.0
        self.monitor = Monitor(self.root, probe=self.probe,
                               recover=lambda: self.repairs.append(self.now) or True,
                               clock=lambda: self.now, public_interval=45)

    def probe(self, url, identity):
        self.calls.append((url, identity))
        return self.probes[{"smartseat-router": 1}.get(identity, 2 if url.startswith("https") else 0)]

    def test_missing_database_is_critical_and_never_created_or_repaired(self):
        (self.root / "local/smartseat.sqlite3").unlink()
        self.probes[0] = Probe("offline")
        status = self.monitor.check()
        self.assertEqual(status["state"], "critical")
        self.assertIn("database_missing", status["issues"])
        self.assertEqual(self.repairs, [])
        self.assertFalse((self.root / "local/smartseat.sqlite3").exists())

    def test_only_exact_service_identity_is_healthy_and_mismatch_prevents_repair(self):
        self.probes[0] = Probe("mismatch", {"app": "otherapp"})
        self.assertIn("engine_offline", self.monitor.check()["issues"])
        self.assertEqual(self.repairs, [])

    def test_empty_foreign_or_invalid_database_is_not_initialized_or_repaired(self):
        path = self.root / "local/smartseat.sqlite3"
        for raw in (b"", b"foreign-file"):
            path.write_bytes(raw)
            self.probes[0] = Probe("offline")
            status = self.monitor.check()
            self.assertIn("database_unrecognized", status["issues"])
            self.assertEqual(status["state"], "critical")
            self.assertEqual(self.repairs, [])
            self.assertEqual(path.read_bytes(), raw)
        path.unlink()
        with closing(sqlite3.connect(path)) as db:
            db.execute("create table foreign_app(id integer)")
            db.commit()
        before = path.read_bytes()
        self.assertIn("database_unrecognized", self.monitor.check()["issues"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.repairs, [])

    def test_smartseat_database_without_existing_manager_is_not_repaired(self):
        with closing(sqlite3.connect(self.root / "local/smartseat.sqlite3")) as db:
            db.execute("delete from users")
            db.execute("insert into users values('staff-user','existing-hash','staff')")
            db.commit()
        self.probes[0] = Probe("offline")
        self.assertIn("database_unrecognized", self.monitor.check()["issues"])
        self.assertEqual(self.repairs, [])

    def test_matching_table_names_with_missing_required_column_is_not_repaired(self):
        with closing(sqlite3.connect(self.root / "local/smartseat.sqlite3")) as db:
            db.execute("alter table cameras drop column source")
            db.commit()
        self.probes[0] = Probe("offline")
        self.assertIn("database_unrecognized", self.monitor.check()["issues"])
        self.assertEqual(self.repairs, [])

    def test_blocked_camera_alerts_without_restart_and_safe_status_has_no_source(self):
        self.probes[0] = Probe("ok", {"app": "smartseat", "capture": {
            "configured": 1, "live": 0, "blocked": 1, "unavailable": 0, "stopped": 0},
            "secret": "rtsp://password@camera/private"})
        status = self.monitor.check()
        self.assertEqual(status["issues"], ["camera_blocked"])
        self.assertEqual(self.repairs, [])
        content = (self.root / "local/monitor-status.json").read_text()
        self.assertNotIn("rtsp", content)
        self.assertNotIn("secret", content)
        self.assertEqual(set(status), {"at", "state", "issues", "last_recovery_at", "recovery_ok"})

    def test_recovery_cooldown_persists_across_process_restart(self):
        self.probes[0] = Probe("offline")
        first = self.monitor.check()
        self.assertTrue(first["recovery_ok"])
        self.now += 299
        self.monitor = Monitor(self.root, probe=self.probe,
            recover=lambda: self.repairs.append(self.now) or True, clock=lambda: self.now)
        self.monitor.check()
        self.assertEqual(self.repairs, [1000.0])
        self.now += 1
        self.monitor.check()
        self.assertEqual(self.repairs, [1000.0, 1300.0])

    def test_no_repair_and_public_probe_throttle(self):
        self.probes[0] = Probe("offline")
        self.monitor.check(repair=False)
        self.now += 44
        self.monitor.check(repair=False)
        self.assertEqual(len([u for u, _ in self.calls if u.startswith("https")]), 1)
        self.now += 1
        self.monitor.check(repair=False)
        self.assertEqual(len([u for u, _ in self.calls if u.startswith("https")]), 2)
        self.assertEqual(self.repairs, [])

    def test_repeated_incident_does_not_grow_log_and_recovery_is_logged(self):
        self.probes[2] = Probe("offline")
        self.monitor.check(repair=False)
        for _ in range(20):
            self.monitor.check(repair=False)
        log = self.root / "local/monitor-events.jsonl"
        self.assertEqual(len(log.read_text().splitlines()), 1)
        self.probes[2] = Probe("ok", HEALTHY)
        self.now += 45
        self.monitor.check(repair=False)
        events = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual([e["event"] for e in events], ["incident", "resolved"])

    def test_single_process_lock_rejects_second_owner(self):
        path = self.root / "local/watchdog.lock"
        with ProcessLock(path):
            with self.assertRaises(RuntimeError):
                with ProcessLock(path):
                    self.fail("duplicate lock acquired")
        with ProcessLock(path):
            pass

    def test_unknown_capture_and_stopped_capture_are_alerted_separately(self):
        self.probes[0] = Probe("ok", {"app": "smartseat"})
        self.assertEqual(self.monitor.check()["issues"], ["capture_unknown"])
        self.probes[0] = Probe("ok", {"app": "smartseat", "capture": {
            "configured": 2, "live": 1, "blocked": 0, "unavailable": 0, "stopped": 1}})
        self.assertEqual(self.monitor.check()["issues"], ["camera_unavailable"])
        self.assertEqual(self.repairs, [])

    def test_ambiguous_router_blocks_recovery_of_an_offline_engine(self):
        self.probes[0] = Probe("offline")
        self.probes[1] = Probe("mismatch")
        self.monitor.check()
        self.assertEqual(self.repairs, [])

    def test_engine_outage_with_public_gateway_error_allows_safe_recovery(self):
        self.probes[0] = Probe("offline")
        self.probes[2] = Probe("offline")
        status = self.monitor.check()
        self.assertIn("engine_offline", status["issues"])
        self.assertIn("public_offline", status["issues"])
        self.assertIs(status["recovery_ok"], True)
        self.assertEqual(self.repairs, [1000.0])

    def test_camera_blocked_does_not_inhibit_repair_of_router_and_public_outage(self):
        self.probes[0] = Probe("ok", {"app": "smartseat", "capture": {
            "configured": 1, "live": 0, "blocked": 1, "unavailable": 0, "stopped": 0}})
        self.probes[1] = Probe("offline")
        self.probes[2] = Probe("offline")
        status = self.monitor.check()
        self.assertEqual(status["issues"], ["camera_blocked", "public_offline", "router_offline"])
        self.assertIs(status["recovery_ok"], True)
        self.assertEqual(self.repairs, [1000.0])
        self.now += 30
        self.monitor.check()
        self.assertEqual(self.repairs, [1000.0])

    def test_log_rotates_without_unbounded_history(self):
        path = self.root / "local/monitor-events.jsonl"
        path.write_text("x" * 131072)
        self.probes[0] = Probe("offline")
        self.monitor.check(repair=False)
        self.assertLess(path.stat().st_size, 1000)
        self.assertEqual((self.root / "local/monitor-events.previous.jsonl").stat().st_size, 131072)

    def test_failed_recovery_records_cooldown_without_exception_details(self):
        self.probes[0] = Probe("offline")
        def fail():
            raise RuntimeError("password-marker rtsp://private-source")
        self.monitor.recover = fail
        status = self.monitor.check()
        self.assertIs(status["recovery_ok"], False)
        self.assertEqual(status["last_recovery_at"], "1970-01-01T00:16:40Z")
        self.assertNotIn("password-marker", (self.root / "local/monitor-events.jsonl").read_text())


class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.body = b'{"app":"smartseat"}'
        self.code = 200
        parent = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(parent.code)
                self.send_header("Content-Type", "application/json")
                if parent.code == 302:
                    self.send_header("Location", "/should-not-follow")
                self.end_headers()
                self.wfile.write(parent.body)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/health"

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_http_probe_requires_exact_identity(self):
        self.assertEqual(probe_health(self.url, "smartseat").state, "ok")
        self.body = b'{"app":"smartseat-other"}'
        self.assertEqual(probe_health(self.url, "smartseat").state, "mismatch")

    def test_occupied_error_response_is_ambiguous_and_redirects_are_rejected(self):
        self.code = 503
        self.assertEqual(probe_health(self.url, "smartseat").state, "mismatch")
        self.code = 302
        self.assertEqual(probe_health(self.url, "smartseat").state, "mismatch")

    def test_oversized_or_invalid_json_is_not_service_identity(self):
        self.body = b"x" * 65537
        self.assertEqual(probe_health(self.url, "smartseat").state, "mismatch")
        self.body = b"not-json"
        self.assertEqual(probe_health(self.url, "smartseat").state, "mismatch")

    def test_public_gateway_errors_are_transport_outages_while_local_errors_remain_ambiguous(self):
        for code in (502, 503, 504):
            with patch("operations.watchdog.build_opener") as opener:
                opener.return_value.open.side_effect = HTTPError(
                    "https://example.test/smartseat-engine/api/health", code, "gateway", {}, None)
                result = probe_health("https://example.test/smartseat-engine/api/health", "smartseat")
                self.assertEqual(result.state, "offline")
        self.code = 502
        self.assertEqual(probe_health(self.url, "smartseat").state, "mismatch")


if __name__ == "__main__":
    unittest.main()
