"""Consistent, encrypted SmartSeat snapshots. Only explicit restore writes plaintext.

Windows DPAPI CurrentUser protects the complete archive; no external keys or
plaintext temporary dumps are used. Supabase exports are application rows only.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b"SMARTSEAT-DPAPI-1\n"
MAX_BYTES = 256 * 1024 * 1024
CLOUD_TABLES = (
    "smartseat_profiles", "smartseat_workspaces", "smartseat_memberships",
    "smartseat_floor_cache", "smartseat_report_cache", "smartseat_daily_metrics",
    "smartseat_audit_events",
)


class CloudExportError(RuntimeError):
    def __init__(self, category, exit_code=None):
        super().__init__("Read-only cloud export failed")
        self.category = category
        self.exit_code = exit_code


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def private_directory(path: Path):
    """Create a new directory and restrict it to this Windows user and SYSTEM."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        raise RuntimeError("Windows CurrentUser DPAPI is required")
    identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                              capture_output=True, text=True, check=True,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    import csv
    sid = next(csv.reader(io.StringIO(identity.stdout.strip())))[1]
    result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                             f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError("Cannot restrict backup directory ACL")


def _dpapi(data: bytes, *, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Windows CurrentUser DPAPI is required")
    if len(data) > MAX_BYTES:
        raise ValueError("Backup exceeds the 256 MiB safety limit")

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ValueError(f"DPAPI {'decryption' if decrypt else 'encryption'} failed ({ctypes.get_last_error()})")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel.LocalFree(outgoing.pbData)


def _database_report(db):
    integrity = db.execute("pragma integrity_check").fetchall()
    if integrity != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    tables = [r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
    counts = {name: db.execute('select count(*) from "' + name.replace('"', '""') + '"').fetchone()[0]
              for name in tables}
    return {"integrity": "ok", "table_counts": counts}


def _snapshot(source: Path):
    if not source.is_file():
        raise FileNotFoundError("Source SQLite database does not exist")
    start = time.monotonic()

    def progress(status, remaining, total):
        if time.monotonic() - start > 60:
            raise TimeoutError("SQLite online backup exceeded one minute")

    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as live:
        with closing(sqlite3.connect(":memory:")) as snapshot:
            live.backup(snapshot, pages=1024, progress=progress, sleep=0.05)
            report = _database_report(snapshot)
            data = snapshot.serialize()
            # SQLite's documented deserialize workaround: the online backup is
            # complete, but a WAL source retains WAL header flags. An isolated
            # in-memory restore has no WAL file. Only the snapshot flags change.
            # https://www.sqlite.org/c3ref/deserialize.html
            return data[:18] + b"\x01\x01" + data[20:], report


def _query_rows(output: str):
    # CLI v3 returns a boundary/rows envelope for detected agents, but a
    # regular JSON row array for native scheduled tasks. Ignore the target
    # banner before decoding; never treat database values as instructions.
    starts = [index for char in ("[", "{") if (index := output.find(char)) >= 0]
    if not starts:
        raise ValueError("Missing cloud query JSON")
    envelope = json.JSONDecoder().raw_decode(output[min(starts):])[0]
    rows = envelope if isinstance(envelope, list) else envelope.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Unexpected cloud query envelope")
    return rows


def _cloud_export(project: str):
    if len(project) != 20 or not project.isalnum():
        raise ValueError("Invalid Supabase project reference")
    npx = shutil.which("npx.cmd")
    if not npx:
        raise RuntimeError("npx.cmd is unavailable")
    # One SQL statement means all seven tables use the same transaction snapshot.
    pairs = ",".join("'" + table + "',coalesce((select jsonb_agg(to_jsonb(t)) from public."
                     + table + " t),'[]'::jsonb)" for table in CLOUD_TABLES)
    sql = "select jsonb_build_object(" + pairs + ") as smartseat_backup"
    result = subprocess.run([npx, "--yes", "supabase@3.0.0", "db", "query",
                             f"--remote={project}", "--read-only", "--output", "json", sql],
                            cwd=ROOT, capture_output=True, timeout=180,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        # CLI stderr may contain credentials or user data: never surface it.
        message = (result.stderr + result.stdout).decode("utf-8", errors="replace").lower()
        category = "cli_failure"
        for label, markers in (
            ("authentication", ("access token", "not logged", "unauthorized", "authentication", "login")),
            ("network", ("enotfound", "econnrefused", "fetch failed", "timeout", "network", "proxy")),
            ("certificate", ("certificate", "tls", "ssl")),
            ("node_runtime", ("node is not recognized", "node' is not recognized", "could not determine executable")),
            ("npm", ("npm error", "npm err!")),
            ("permission", ("permission denied", "eacces", "access is denied")),
        ):
            if any(marker in message for marker in markers):
                category = label
                break
        raise CloudExportError(category, result.returncode)
    output = result.stdout.decode("utf-8")
    rows = _query_rows(output)
    if len(rows) != 1:
        raise ValueError("Unexpected cloud export envelope")
    data = rows[0]["smartseat_backup"]
    if isinstance(data, str):
        data = json.loads(data)
    if set(data) != set(CLOUD_TABLES) or not all(isinstance(v, list) for v in data.values()):
        raise ValueError("Incomplete cloud application export")
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def create_backup(source: Path, destination: Path, *, cloud_project=None):
    source, destination = Path(source), Path(destination)
    sqlite_bytes, report = _snapshot(source)
    payloads = {"smartseat.sqlite3": sqlite_bytes}
    manifest = {"format": 1, "created_at": utc_now(), "protection": "Windows-DPAPI-CurrentUser",
                "sqlite": report, "cloud_state": "not_requested"}
    if cloud_project:
        try:
            payloads["cloud-application.json"] = _cloud_export(cloud_project)
            for migration in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
                payloads["migrations/" + migration.name] = migration.read_bytes()
            manifest["cloud_state"] = "included"
            manifest["cloud_project"] = cloud_project
            manifest["cloud_scope"] = "public SmartSeat application rows; excludes auth, storage, project configuration"
        except Exception as error:
            manifest["cloud_state"] = "failed"
            manifest["cloud_error_type"] = type(error).__name__
            if isinstance(error, CloudExportError):
                manifest["cloud_error_code"] = error.category
                manifest["cloud_cli_exit_code"] = error.exit_code
    manifest["sha256"] = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    container = io.BytesIO()
    with zipfile.ZipFile(container, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", json.dumps(manifest).encode("utf-8"))
    encrypted = MAGIC + _dpapi(container.getvalue())
    private_directory(destination)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = destination / f"smartseat-{stamp}-{uuid.uuid4().hex[:8]}.ssbackup"
    temporary = final.with_suffix(".partial")
    try:
        with temporary.open("xb") as handle:
            handle.write(encrypted)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.rename(final)
        verify_backup(final)
    finally:
        temporary.unlink(missing_ok=True)
    return final


def _load(archive: Path):
    if archive.stat().st_size > MAX_BYTES:
        raise ValueError("Backup exceeds safety limit")
    encrypted = archive.read_bytes()
    if not encrypted.startswith(MAGIC):
        raise ValueError("Unknown backup format")
    raw = _dpapi(encrypted[len(MAGIC):], decrypt=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as container:
        if sum(info.file_size for info in container.infolist()) > MAX_BYTES:
            raise ValueError("Decompressed backup exceeds safety limit")
        manifest = json.loads(container.read("manifest.json"))
        if manifest.get("format") != 1:
            raise ValueError("Unsupported backup format")
        payloads = {}
        for name, expected in manifest["sha256"].items():
            if name not in {"smartseat.sqlite3", "cloud-application.json"} and not (
                    name.startswith("migrations/") and Path(name).name == name[len("migrations/"):] and name.endswith(".sql")):
                raise ValueError("Unsafe archive entry")
            data = container.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Backup payload hash mismatch")
            payloads[name] = data
    if "smartseat.sqlite3" not in payloads:
        raise ValueError("Missing SQLite payload")
    return manifest, payloads


def verify_backup(archive: Path):
    manifest, payloads = _load(Path(archive))
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(payloads["smartseat.sqlite3"])
        report = _database_report(db)
    if report != manifest["sqlite"]:
        raise ValueError("Restored SQLite row counts differ from snapshot")
    if manifest["cloud_state"] == "included":
        cloud = json.loads(payloads["cloud-application.json"])
        if set(cloud) != set(CLOUD_TABLES) or not all(isinstance(v, list) for v in cloud.values()):
            raise ValueError("Incomplete cloud payload")
        report["cloud_table_counts"] = {name: len(rows) for name, rows in cloud.items()}
    report.update({"created_at": manifest["created_at"], "cloud_state": manifest["cloud_state"],
                   "verified_at": utc_now(), "archive_sha256": hashlib.sha256(Path(archive).read_bytes()).hexdigest()})
    return report


def restore_backup(archive: Path, destination: Path):
    """Recover only into a fresh directory, never overwrite a running database."""
    destination = Path(destination)
    # lexists also rejects dangling symlinks, unlike Path.exists().
    if os.path.lexists(destination):
        raise FileExistsError("Recovery destination must not already exist")
    report = verify_backup(archive)
    manifest, payloads = _load(Path(archive))
    destination.mkdir(parents=True, exist_ok=False)
    private_directory(destination)
    for name, data in payloads.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
    with closing(sqlite3.connect((destination / "smartseat.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if _database_report(db) != manifest["sqlite"]:
            raise ValueError("Recovered file integrity check failed")
    (destination / "recovery-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _write_status(status):
    path = ROOT / "local" / "backup-status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"backup-status-{uuid.uuid4().hex}.partial")
    try:
        temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--source", type=Path, default=ROOT / "local" / "smartseat.sqlite3")
    create.add_argument("--destination", type=Path, default=ROOT / "local" / "backups")
    create.add_argument("--cloud-project")
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    status = {"at": utc_now(), "ok": False}
    try:
        if args.command == "create":
            archive = create_backup(args.source, args.destination, cloud_project=args.cloud_project)
            report = verify_backup(archive)
            status.update({"archive": archive.name, "last_archive": archive.name,
                           "integrity": report["integrity"], "cloud_state": report["cloud_state"],
                           "last_restore_verified_at": report["verified_at"],
                           "archive_sha256": report["archive_sha256"],
                           "ok": report["cloud_state"] != "failed"})
            if report["cloud_state"] == "failed":
                manifest, _ = _load(archive)
                for key in ("cloud_error_type", "cloud_error_code", "cloud_cli_exit_code"):
                    if key in manifest:
                        status[key] = manifest[key]
            _write_status(status)
            print(json.dumps(status))
            return 0 if status["ok"] else 1
        report = (verify_backup(args.archive) if args.command == "verify" else
                  restore_backup(args.archive, args.destination))
        print(json.dumps(report, indent=2))
        return 0
    except Exception as error:
        # Paths, subprocess stderr, query data and connection details stay out of logs.
        status["error_type"] = type(error).__name__
        if args.command == "create":
            _write_status(status)
        print(json.dumps(status), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
