# Encrypted backups and recovery

`operations/backup.py` takes a consistent SQLite online backup from the live
database into memory. The complete compressed archive is encrypted using
Windows DPAPI **CurrentUser**, including database contents, payload hashes,
row counts, cloud exports and migration SQL. No plaintext temporary SQL or
SQLite dump is written during creation or verification. The archive directory
has inherited access removed and grants full access only to the current user
and Windows SYSTEM. Archive files inherit that protection.

DPAPI authenticates ciphertext; verification also checks SHA-256 for every
payload, restores SQLite into an isolated in-memory connection, runs
`PRAGMA integrity_check`, and compares every application table's row count.
The source database is opened read-only and is never replaced. The SQLite
online backup includes committed data in a live WAL. The isolated snapshot
uses SQLite's documented WAL-header conversion for deserialization.

## Schedule installed on this Windows account

Task Scheduler task: **SmartSeat Encrypted Backup**. It runs daily at
**02:30 Asia/Kolkata** and when this user signs in. A missed daily run starts
when possible; overlapping scheduled instances are ignored. Failures retry
three times at 15-minute intervals. The task runs with the current user's
interactive token and limited privileges, invoking the virtual environment's
windowless `pythonw.exe` directly. No PowerShell execution-policy override is used.
No Windows password or Supabase access token is stored in task arguments.

The daily task needs this Windows user signed in and the computer awake.
It does not run while the account is signed out. The cloud portion also
requires internet access and the existing Supabase CLI login. A failed cloud
export still saves and verifies the local encrypted snapshot, records
`cloud_state: failed`, and exits nonzero so Task Scheduler retries.

From the project directory in PowerShell:

```powershell
# Inspect the actual installed action, triggers, last result and next run.
powershell.exe -NoProfile -File operations/backup-schedule.ps1 -Mode Status

# Run the registered task now; examine status after it completes.
Start-ScheduledTask -TaskName 'SmartSeat Encrypted Backup'
Get-ScheduledTaskInfo -TaskName 'SmartSeat Encrypted Backup'
Get-Content local/backup-status.json

# Reinstall after moving this project or changing its Windows user.
powershell.exe -NoProfile -File operations/backup-schedule.ps1 -Mode Install

# Remove only the schedule; encrypted archives are retained.
powershell.exe -NoProfile -File operations/backup-schedule.ps1 -Mode Remove
```

Archives are under `local/backups/smartseat-<UTC time>-<random>.ssbackup`.
`local/backup-status.json` contains only timestamps, success state, archive
filename, integrity state, cloud state and archive hash. Failure messages
contain only an exception class; database contents, subprocess output and
connection credentials are never logged. `last_restore_verified_at` means
the SQLite snapshot was successfully deserialized and checked in memory;
it does not assert a production recovery or restaurant field test.

## Manual backup and isolated recovery

```powershell
# Local + cloud application backup, using pinned Supabase CLI 3.0.0.
.venv/Scripts/python.exe operations/backup.py create --cloud-project tnwrnwhitnbxuhdfuwvh

# Local-only encrypted backup (no network required).
.venv/Scripts/python.exe operations/backup.py create

$latest = Get-ChildItem local/backups/*.ssbackup | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1

# Decrypt only in RAM; validate payload hashes, SQLite integrity and row counts.
.venv/Scripts/python.exe operations/backup.py verify $latest.FullName

# Explicit recovery writes decrypted data into a NEW user/SYSTEM-only directory.
# The command refuses every existing destination, including the live directory.
.venv/Scripts/python.exe operations/backup.py restore $latest.FullName --destination local/recovery-review-20261105
```

The explicit recovery directory contains `smartseat.sqlite3`, a non-sensitive
verification report, and (if included) `cloud-application.json` plus migration
SQL. Decrypted files are operational data: retain the restricted ACL, review
privately, and remove the isolated recovery directory when the drill is done.
Never place a recovery directory in a public web root or a repository commit.

For an actual local recovery, first validate the recovered database and record
the report. In a separate, planned maintenance window, stop the engine, retain
the current database and its WAL/SHM together, and replace the operational
database using the recovered snapshot. Clear restored `sessions` rows before
accepting logins, start the engine, and verify roles, camera configuration,
queue/reservation state and reports. The backup tool deliberately provides no
command that overwrites the live database or stops running services.

## Cloud scope and limits

The cloud backup executes **one read-only SQL statement** against the explicit
project `tnwrnwhitnbxuhdfuwvh` through the already-authenticated official CLI.
It includes all rows from these seven tables in one consistent statement
snapshot: `smartseat_profiles`, `smartseat_workspaces`,
`smartseat_memberships`, `smartseat_floor_cache`, `smartseat_report_cache`,
`smartseat_daily_metrics`, and `smartseat_audit_events`. Local migration files
are included to retain the application schema definition. Adding another
application table requires explicitly updating the exporter and tests.

This is a **cloud application export**, not a full Supabase database dump.
It excludes the `auth` schema (password hashes and authentication tokens),
storage objects, secrets, OAuth settings, platform configuration and
deployment credentials. A complete hosted disaster recovery still requires
an independently verified Supabase full backup/restore procedure. No paid
backup service or extra cloud project was provisioned. No cloud restore or
production overwrite was executed.

To recover application rows, use an isolated PostgreSQL/Supabase environment
with the matching application migrations and existing/restored `auth.users`
identities. Import the JSON using `jsonb_populate_recordset` in foreign-key
order: profiles, workspaces, memberships, floor cache, report cache, daily
metrics, audit events. Audit identities need `OVERRIDING SYSTEM VALUE` when
inserting preserved IDs, followed by resetting the identity sequence above
the maximum ID. Validate row counts, foreign keys, RLS policies and actual
user access before planning any production cutover. The same original
`auth.users` UUIDs are required: creating accounts with new UUIDs will not
restore membership links. This cloud recovery procedure has not been run
against a separate PostgreSQL instance here.

## Recovery boundaries and storage

DPAPI recovery requires the original Windows user's functioning profile and
keys, normally on this computer. An encrypted archive alone is insufficient
after loss of that profile or its DPAPI keys. Files stay on this disk; no
offsite copy was configured. Copy only encrypted `.ssbackup` archives to an
approved independent location and ensure the Windows/DPAPI recovery material
is recoverable before treating these as machine-loss disaster recovery.
Enable whole-device encryption to also protect the OS pagefile and the
original running database; the backup process cannot guarantee that the OS
never pages memory to disk.

At most 256 MiB of compressed/decompressed archive data is accepted. Large
databases need a streaming encryption design instead. Archives are retained
until explicitly removed; monitor free disk space and choose a retention
policy appropriate to the restaurant's record obligations. The schedule
provides a target 24-hour recovery point while its prerequisites hold.
No time-to-recovery or uninterrupted operation guarantee is asserted.

## Verification performed

On 2026-11-05, six recovery tests used actual Windows DPAPI and temporary SQLite WAL
databases, covering consistent restoration while the source changes,
in-memory verification, ciphertext tampering, missing-source refusal and
existing-destination refusal. A seventh test covers both Supabase CLI JSON
formats, including the native scheduled-task environment. A live local snapshot plus all seven cloud
application tables was encrypted, recovered into a fresh protected directory,
and independently verified; decrypted drill files were removed. Task Scheduler
installation and an on-demand run were checked separately. See
`local/backup-status.json` and the live Task Scheduler result for current
evidence; these files describe local software checks, not restaurant field
validation.

Primary implementation references:
[Windows DPAPI protection](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata),
[SQLite deserialization and WAL snapshot handling](https://www.sqlite.org/c3ref/deserialize.html),
[Supabase CLI v3 target/read-only behavior](https://supabase.com/changelog/supabase-cli-v3).
