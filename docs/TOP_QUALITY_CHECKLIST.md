# SmartSeat quality checklist

This is an evidence-based release checklist, not a claim of a measured market percentile. Checks are complete only when implemented and verified.

## Account and data foundation — current work

- [x] Provision a dedicated hosted PostgreSQL project on the quoted free tier.
- [ ] Accept public email/password sign-up and sign-in after authorized SMTP delivery and a complete real account lifecycle are verified.
- [x] Configure and test the real Google OAuth callback using the existing Google Cloud project.
- [x] Add HTTP-only, secure session cookies and server-side identity validation.
- [x] Verify the owner's real recovery email, browser PKCE callback and password-reset form without changing the owner's password.
- [ ] Verify a real new-account email confirmation and completed password-change/email-login lifecycle; public delivery still needs authorized SMTP.
- [x] Verify Google sign-out clears account access and disconnects the camera session.
- [x] Add real profiles and private restaurant workspaces.
- [x] Enforce database row-level security and test cross-account isolation.
- [x] Keep camera-engine authentication separate from account identity; a Google account alone must not gain access to the existing restaurant camera.
- [x] Persist actual floor snapshots and owner report data in the hosted database.
- [x] Show sync time and engine availability explicitly when reading saved data.
- [x] Record account/workspace actions without passwords, tokens or camera pixels in audit logs.
- [x] Verify production deployment, OAuth/confirmation errors, invalid/expired managed sessions, auth failures and owner report access.
- [x] Verify production Google callback, wrong pairing credentials, sign-out protection and actual owner report access.
- [x] Verify an offline page reload retains cloud identity and restores manager controls when the engine returns.

## Product experience

- [x] Responsive desktop/mobile UI and 24 locally stored background images.
- [x] Reduced-motion support, pause control and keyboard focus indicators.
- [x] Real daily, weekly and weekend analytics with CSV export.
- [x] Visual dining-item clearance suggestions with staff-confirmed cleaning.
- [x] Add account settings, workspace setup and a clear engine-connection flow.
- [x] Add actionable loading, validation, empty and offline states to Google sign-in and engine pairing.
- [x] Verify Google/account flows on desktop and owner reports on desktop/mobile without fabricated restaurant records.
- [x] Verify CSV export and weekend selection against actual report records.
- [x] Stop and restart the real engine; verify saved reports during the outage and live recovery afterward.
- [x] Provide and verify one startup command for the engine, local router and existing public connector.

## Restaurant acceptance and operations

- [x] Real local inference; no replacement camera frames or paid inference service.
- [x] Covered-camera and stale-evidence handling.
- [x] Protect camera frames and mutations behind authentication.
- [ ] Measure table/occupancy/clearance precision and recall on each restaurant's actual cameras.
- [ ] Test a complete staffed shift with crowding, lighting changes, camera outages and clearing/reset cycles.
- [x] Install and verify a per-user background supervisor and automatic engine/connector recovery; keep the restaurant computer awake and signed in.
- [ ] Verify startup through a future real Windows logon and unattended 24/7 availability on the actual restaurant host.
- [x] Schedule encrypted SQLite/cloud-application backups and verify integrity plus an isolated local restore; native scheduled run succeeded.
- [ ] Verify offsite recovery and a full hosted-database/Auth disaster-recovery procedure; the current cloud archive intentionally excludes Auth/storage/configuration.
- [x] Add bounded gateway auth/request/body controls, background monitoring, private incident logs and manager-only in-app operational alerts.
- [x] Provide actual staff access inventory and a non-destructive retention preview in the manager dashboard, with a documented review policy.
- [ ] Obtain the restaurant owner's retention/access sign-off and individual real staff assignments; no owner approval or staff identities are fabricated.

## Real laptop-table acceptance — blocked physical prerequisites

- [ ] Map a visible real tabletop/seating polygon and verify its actual capacity.
- [ ] Observe a real empty → occupied → departed cycle against the mapped zone.
- [ ] Observe actual dishes/items left and removed, then a human cleaning confirmation after real wiping.

Earlier inspected frames were almost black (about 3.15/255 mean intensity), or showed a person with the table outside the frame. In the later table-detector retest the camera was clear and detected one person, but the tabletop was still outside the image; zero table candidates and zero mapped zones were appropriate for those observations. No table, visit or cleaning confirmation was inserted to manufacture acceptance. Earlier blocked-frame evidence is in ignored `local/latest-live-acceptance.json`; the later six-sample sequence is in `local/table-motion-live-observations.json`. A clearly visible tabletop and seating area, plus actual occupancy and clearing actions, are required before these checks can pass.

Visible dishes are not proof that a table is dirty, and their absence does not prove sanitation. Those limits stay explicit in the product.

## Verification evidence — 5 November 2026

- Production: https://smartseat-ai-9059.vercel.app/
- Browser: Google account chooser → managed callback → verified private workspace → restaurant credentials → live laptop camera. Account sign-in clears the previous engine cookie.
- Real engine: `demo=false`, authenticated camera JPEG returned HTTP 200; live frames and anonymous person counts appeared in the public app. No restaurant tables or visits were fabricated for this test.
- Hosted database: one Google profile/workspace, one actual floor snapshot, one seven-day report and seven normalized daily metric rows were verified before additional report-period tests.
- Isolation: transactional two-account RLS test passed and rolled back its test records. Anonymous floor, camera, analytics and pairing requests were denied; malicious auth Origin was blocked; invalid OAuth callback was handled; PKCE cookies had Secure/HttpOnly/SameSite=Lax.
- Connector correction: dedicated SmartSeat engine uses loopback port 8766. Router 8767 reserves `/smartseat-engine/*`; other requests retain the original application's port 8765. Original application's public OpenAPI identity was verified after switching routes. No other application process was stopped.
- Reviewer-found stream interruption, account-role preservation and cached-report HTTP 5xx issues were corrected and regression tested.
- A real engine shutdown returned HTTP 502 at its connector; the public UI marked the camera disconnected and rendered its actual saved report with the saved timestamp. `Start-PublicApp.ps1` restored the engine and the UI returned to live updates.
- Browser CSV export produced seven daily records with valid columns. Latest-weekend selection returned 31 October and 1 November. Sign-out returned the login screen and the same browser's `/api/state` then required sign-in.
- Incorrect engine credentials produced the expected error without signing out the Google account; valid credentials reconnected successfully. On the final build, an offline page reload kept the cloud identity; after restart, the UI restored manager controls and loaded the real 640×480 camera image with fresh processed-frame counts.
- Verification commands: `python -m unittest discover -s tests -q` (20 passed); `node --test tests/cloud/connector.test.cjs` (4 passed); Vite production build passed. Browser console had no errors/warnings at the verified report screen.
- Supabase's security advisor flags the two authenticated SECURITY DEFINER RPCs. These are intentional for atomic workspace creation and constrained audit recording; both bind identity to `auth.uid()`, restrict inputs/access and use an empty search path. See https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable.
- On this later release pass, the owner's actual Supabase recovery email arrived at 17:17 IST, and a fresh browser-originated request produced another at 17:32 IST. The fresh link completed PKCE and opened `/?reset_password=1` with the real new-password form. No password was typed or changed. Public new-user delivery remains separate and unaccepted.
- Encrypted backups use Windows DPAPI CurrentUser and restricted archive ACLs. The scheduled native task finished with result 0; a real SQLite snapshot and all seven cloud application tables were verified in the encrypted archive. An isolated file restore passed integrity and row-count checks without replacing production. See `docs/backups.md` for the same-profile, local-only and hosted-Auth limitations.
- The enabled background supervisor detected a deliberately stopped real engine and restored local/public health automatically. A second drill stopped only the router while the camera was blocked: the router recovered, the engine PID stayed unchanged, and the private frame counter increased from 1618 to 2717. Subsequent cycles retained only the physical camera warning and made no repeated restart. See `docs/monitoring.md`.
- The manager safeguards panel shows real backup/monitoring status, actual engine account roles, mapped-zone count and retention candidate counts. Retention is preview-only; no production records were purged. See `docs/data-and-staff-access.md`.
- Gateway protection bounds per-instance identity buckets, auth attempts, mutation rate and actual UTF-8 request bytes. Vercel/provider protections remain in place; the in-process guard is not represented as a globally distributed limit. Production rejected an actual oversized request with HTTP 413, and the seven live authentication acceptance checks passed.
- Latest automated checkpoint: 50 Python tests and 22 cloud Node tests passed, including backup, watchdog, expired-session, bad-service identity, wrong database, interrupted stream, API body and rate-limit boundaries. These isolated tests are not substituted for physical table or full-shift acceptance.
- Production safeguards UI was verified at desktop 1280×900 and mobile 390×844 with no browser errors/warnings. It showed the real successful backup/restore timestamps, included cloud application snapshot, actual camera-blocked incident and completed automatic recovery, actual manager account, zero mapped zones and preview-only retention counts. The final app is left paired in the in-app browser; no password was changed.
- Later table-scan correction: moving people are excluded from common evidence, proposals are validated independently against visible table/background pixels, and age/camera-change/occlusion checks remain. Seven focused cases and the full 55-test Python suite passed; the dedicated engine was restarted, supervisor returned to Running, and fresh public camera frames and matched scan status were verified with no browser errors. See `docs/table-detection-verification.md`. No universal 100% recognition or positive live-table acceptance is claimed.
