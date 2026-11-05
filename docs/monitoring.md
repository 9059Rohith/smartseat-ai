# SmartSeat health supervision

`operations/watchdog.py` checks the dedicated engine, the loopback connector router's independent identity endpoint, and the public engine health endpoint configured in ignored `local/public-connection.json`. Local checks default to every 30 seconds; public checks default to every 60 seconds and cannot be configured below 45 seconds. The public website and another application's default router path are not monitor targets.

The monitor writes `local/monitor-status.json` atomically with UTC `at`, `state` (`healthy`, `degraded`, or `critical`), an issue enum list, `last_recovery_at`, and `recovery_ok`. It stores no camera names, source URLs, frames, credentials, IP addresses, or subprocess output. Issue changes and recovery attempts go to `local/monitor-events.jsonl`; one previous log is retained and each file rotates around 128 KiB. Local files are ignored by git. A covered or dark camera view becomes `camera_blocked`, unavailable or stopped captures become `camera_unavailable`, and absent/inconsistent aggregate capture counts become `capture_unknown`. These alerts are visible in the status file; no email or external alert delivery is configured.

Only an exact `app: smartseat` engine response and exact `app: smartseat-router` router response establish identity. An occupied local port or response with an unexpected identity inhibits recovery. Public HTTPS 502/503/504 gateway responses count as transport outages and permit recovery when local identities and the database are safe; a successful response identifying another app still inhibits recovery. Camera-only problems never trigger service recovery. A genuine engine, router, or public connector outage can trigger guarded recovery even while `camera_blocked` is present; the launcher preserves a healthy engine when repairing a connector, so a covered camera does not cause an engine restart loop. Missing `local/smartseat.sqlite3` is critical (`database_missing`). Before any recovery the monitor opens the existing database in SQLite read-only mode, runs integrity checking, verifies all required SmartSeat tables and columns, and requires an existing manager account. Empty, corrupt, foreign, or incomplete databases are critical (`database_unrecognized`) and inhibit recovery. The watchdog never creates, replaces, or initializes the restaurant database.

Eligible service outages invoke the reviewed `Start-PublicApp.ps1` hidden, with a maximum 180-second wait and at least five minutes between attempts. The attempt time is persisted before launch, so process restarts preserve the cooldown. The launcher performs its own ownership and existing shared-route checks. `recovery_ok` reports the launcher's verified success; subsequent health checks determine when issues are resolved. A Windows byte-range lock allows one monitor process per project.

Run a read-only health check from the project directory:

```powershell
.\.venv\Scripts\python.exe operations/watchdog.py --once --no-repair
.\.venv\Scripts\python.exe operations/watchdog.py --check-database
```

Exit status is 0 for healthy, 1 for degraded, 2 for critical, and 3 when another monitor holds the lock. A foreground continuous monitor uses the same command without `--once`; add `--no-repair` for observation only. Stop a foreground monitor with Ctrl+C.

Install per-user startup without running it immediately:

```powershell
.\operations\watchdog-startup.ps1 -Mode Install -Disabled
.\operations\watchdog-startup.ps1 -Mode Status
.\operations\watchdog-startup.ps1 -Mode Enable
```

Installation first registers and verifies a limited, interactive logon scheduled task for the current user. Only an actual Windows access-denied failure enables the fallback: a hidden launcher in that user's Startup folder. `-Disabled` stages either mechanism without enabling launch. Enabling schedules future logon startup and does not execute the monitor immediately. `-Mode Run` runs it now when ready. `-Mode Disable` prevents future startup; it leaves an existing process unchanged. `-Mode Remove` removes only the startup registration and retains local health records.

This runs on the user's computer while that user is signed in. It does not keep the laptop awake, change power settings, wake it, guarantee 24/7 availability, require administrator credentials, or provision a paid host. After installation, verify one real logon start and a deliberate service recovery during a maintenance window. Validate camera access and verify the public endpoint separately; a healthy public website alone does not establish a healthy restaurant engine.

## Verified installation, 2026-11-05

The current-user logon scheduled task is installed and enabled with an interactive limited principal, the exact hidden interpreter action, one current-user logon trigger, and wake disabled. Manual task start and stop were verified; stopping the task releases the watchdog lock. A real future Windows logon has not been exercised.

A read-only check first reported fully healthy engine, router, public endpoint, and live camera. During a later controlled drill, only the verified dedicated engine was stopped. The running watchdog detected `engine_offline` at 12:03:01 UTC, validated the existing database, invoked the guarded launcher, recorded `recovery_ok: true`, and restored both local and public engine health. The next health cycle at 12:03:43 UTC reported `degraded` with only `camera_blocked`; no additional camera restart was attempted. The task was left running. The remaining covered or dark camera view warning requires separate resolution and is not evidence of an engine or connector outage.

A second controlled drill stopped only the verified connector router while the camera view remained blocked. At 12:09:03 UTC the monitor detected `router_offline` alongside `camera_blocked` and automatically recovered the connector. The replacement router returned the exact expected identity and public engine health was restored. The dedicated engine process remained unchanged throughout. By 12:09:43 UTC the monitor again reported only `camera_blocked`, with one successful recovery attempt and no camera-only restart.
