"""Per-user SmartSeat supervision. Health records contain aggregates only."""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
ISSUES = frozenset({"engine_offline", "router_offline", "public_offline",
                    "camera_blocked", "camera_unavailable", "capture_unknown", "database_missing",
                    "database_unrecognized"})
MAX_LOG_BYTES = 131072
REQUIRED_SCHEMA = {
    "cameras": {"id", "name", "kind", "source", "entrance"},
    "tables": {"id", "name", "capacity", "camera", "zone", "created", "state", "people", "since", "greeted", "vision"},
    "visits": {"id", "table_id", "started", "greeted", "ended", "cleaned", "party_size"},
    "queue": {"id", "name", "size", "joined", "status", "table_id", "called", "seated"},
    "reservations": {"id", "name", "size", "table_id", "start", "end", "status"},
    "events": {"id", "at", "kind", "table_id", "detail"},
    "users": {"name", "secret", "role"},
    "sessions": {"digest", "name", "expires"},
    "surface_checks": {"table_id", "at", "state", "items"},
}


def database_state(root):
    """Recognize an existing restaurant database without initializing any schema."""
    path = Path(root) / "local/smartseat.sqlite3"
    if not path.is_file():
        return "missing"
    try:
        if path.stat().st_size == 0:
            return "unrecognized"
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA integrity_check(1)").fetchone() != ("ok",):
                return "unrecognized"
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if not set(REQUIRED_SCHEMA) <= tables:
                return "unrecognized"
            for table, required in REQUIRED_SCHEMA.items():
                columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
                if not required <= columns:
                    return "unrecognized"
            manager = db.execute("SELECT 1 FROM users WHERE role='manager' AND length(trim(name))>0 "
                                 "AND length(secret)>0 LIMIT 1").fetchone()
            return "recognized" if manager else "unrecognized"
    except (OSError, sqlite3.Error, ValueError):
        return "unrecognized"


def utc_at(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Probe:
    state: str
    payload: dict | None = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_health(url, identity):
    """Reject redirects, oversized/non-JSON responses and unexpected identities."""
    try:
        request = Request(url, headers={"ngrok-skip-browser-warning": "true", "Accept": "application/json"})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                return Probe("mismatch")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("app") != identity:
                return Probe("mismatch")
            return Probe("ok", payload)
    except HTTPError as error:
        if urlsplit(url).scheme == "https" and error.code in {502, 503, 504}:
            return Probe("offline")
        # A listening service returning an unexpected response is never replaced.
        return Probe("mismatch")
    except (ValueError, UnicodeError):
        return Probe("mismatch")
    except (OSError, TimeoutError):
        target = urlsplit(url)
        if target.hostname == "127.0.0.1":
            try:
                with socket.create_connection((target.hostname, target.port), timeout=1):
                    return Probe("mismatch")
            except OSError:
                pass
        return Probe("offline")


def public_health_url(root):
    try:
        config = json.loads((root / "local/public-connection.json").read_text(encoding="utf-8"))
        origin = config["engine_origin"]
        parts = urlsplit(origin)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path.rstrip("/") != "/smartseat-engine"):
            return None
        return origin.rstrip("/") + "/api/health"
    except (OSError, ValueError, KeyError, TypeError):
        return None


def recover_services(root):
    """Run only the reviewed launcher, hidden, without retaining process output."""
    if os.name != "nt" or database_state(root) != "recognized":
        return False
    script = root / "Start-PublicApp.ps1"
    shell = shutil.which("powershell.exe")
    if not script.is_file() or not shell:
        return False
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    try:
        completed = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(script)], cwd=root,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=180, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class Monitor:
    def __init__(self, root=ROOT, *, probe=probe_health, recover=None, clock=time.time,
                 public_interval=60, cooldown=300):
        self.root = Path(root)
        self.local = self.root / "local"
        self.local.mkdir(exist_ok=True)
        self.probe = probe
        self.recover = recover or (lambda: recover_services(self.root))
        self.clock = clock
        self.public_interval = max(45, public_interval)
        self.cooldown = max(300, cooldown)
        self.last_public_at = None
        self.public_result = Probe("offline")
        self.last_recovery = None
        self.recovery_ok = None
        self.previous_issues = None
        try:
            prior = json.loads((self.local / "monitor-status.json").read_text())
            if prior.get("last_recovery_at"):
                self.last_recovery = datetime.fromisoformat(prior["last_recovery_at"].replace("Z", "+00:00")).timestamp()
            self.recovery_ok = prior.get("recovery_ok") if isinstance(prior.get("recovery_ok"), bool) else None
            self.previous_issues = sorted(set(prior.get("issues", [])) & ISSUES)
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def _status(self, now, issues):
        state = "critical" if any(i in issues for i in ("engine_offline", "router_offline", "database_missing", "database_unrecognized")) else ("degraded" if issues else "healthy")
        return {"at": utc_at(now), "state": state, "issues": issues,
                "last_recovery_at": utc_at(self.last_recovery) if self.last_recovery is not None else None,
                "recovery_ok": self.recovery_ok}

    def _write_status(self, now, issues):
        status = self._status(now, issues)
        pending = self.local / "monitor-status.json.tmp"
        pending.write_text(json.dumps(status, separators=(",", ":")), encoding="utf-8")
        pending.replace(self.local / "monitor-status.json")
        return status

    def _event(self, event, now, issues):
        # Construct from a fixed schema; never serialize health payloads/exceptions.
        path = self.local / "monitor-events.jsonl"
        if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
            path.replace(self.local / "monitor-events.previous.jsonl")
        record = {"at": utc_at(now), "event": event, "issues": sorted(set(issues) & ISSUES)}
        if event == "recovery":
            record["ok"] = self.recovery_ok
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")

    def check(self, repair=True):
        now = self.clock()
        engine = self.probe("http://127.0.0.1:8766/api/health", "smartseat")
        router = self.probe("http://127.0.0.1:8767/smartseat-engine/router-health", "smartseat-router")
        public_url = public_health_url(self.root)
        if self.last_public_at is None or now - self.last_public_at >= self.public_interval:
            self.public_result = self.probe(public_url, "smartseat") if public_url else Probe("offline")
            self.last_public_at = now
        issues = []
        for result, issue in ((engine, "engine_offline"), (router, "router_offline"),
                              (self.public_result, "public_offline")):
            if result.state != "ok":
                issues.append(issue)
        database = database_state(self.root)
        if database == "missing":
            issues.append("database_missing")
        elif database != "recognized":
            issues.append("database_unrecognized")
        if engine.state == "ok":
            capture = (engine.payload or {}).get("capture")
            keys = ("configured", "live", "blocked", "unavailable", "stopped")
            if (not isinstance(capture, dict) or any(type(capture.get(k)) is not int or capture[k] < 0 for k in keys)
                    or sum(capture[k] for k in keys[1:]) != capture["configured"]):
                issues.append("capture_unknown")
            else:
                if capture["blocked"]:
                    issues.append("camera_blocked")
                if capture["unavailable"] or capture["stopped"]:
                    issues.append("camera_unavailable")
        issues.sort()
        if issues != self.previous_issues:
            if issues:
                self._event("incident", now, issues)
            elif self.previous_issues:
                self._event("resolved", now, [])
            self.previous_issues = issues
        results = (engine, router, self.public_result)
        safe_identity = all(result.state in {"ok", "offline"} for result in results)
        needs_repair = any(i in issues for i in ("engine_offline", "router_offline", "public_offline"))
        cooling_down = self.last_recovery is not None and now - self.last_recovery < self.cooldown
        if (repair and database == "recognized" and public_url and safe_identity and needs_repair
                and not cooling_down):
            self.last_recovery = now
            self.recovery_ok = None
            # Persist the attempt before starting a child so crashes retain cooldown.
            self._write_status(now, issues)
            try:
                self.recovery_ok = self.recover() is True
            except Exception:
                self.recovery_ok = False
            self._event("recovery", now, issues)
        return self._write_status(now, issues)


class ProcessLock:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(exist_ok=True)
        self.stream = self.path.open("a+b")
        self.stream.seek(0, 2)
        if not self.stream.tell():
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise RuntimeError("SmartSeat monitor is already running.") from None
        return self

    def __exit__(self, *args):
        if self.stream:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_UN)
            self.stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-database", action="store_true",
                        help="Read-only restaurant database validation; no service probes or launch")
    parser.add_argument("--no-repair", action="store_true")
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--public-interval", type=float, default=60)
    options = parser.parse_args()
    if options.check_database:
        state = database_state(ROOT)
        print(json.dumps({"database": state}))
        return 0 if state == "recognized" else 2
    try:
        with ProcessLock(ROOT / "local/watchdog.lock"):
            monitor = Monitor(public_interval=options.public_interval)
            while True:
                status = monitor.check(repair=not options.no_repair)
                if options.once:
                    print(json.dumps(status))
                    return {"healthy": 0, "degraded": 1, "critical": 2}[status["state"]]
                time.sleep(max(15, options.interval))
    except RuntimeError:
        print("SmartSeat monitor is already running.")
        return 3
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
