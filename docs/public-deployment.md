# Running the deployed SmartSeat app

**Working full app:** [https://9059rohith.github.io/smartseat-ai/app/](https://9059rohith.github.io/smartseat-ai/app/). See [the public runtime guide](public-runtime.md). The app can be opened on another laptop; keep the restaurant host awake and online.

> **11 November 2026:** Vercel currently returns HTTP 402 / DEPLOYMENT_DISABLED because of the team's Hobby CPU allowance. The public URL below is configured correctly but unavailable while the provider block remains. See [hosting status and working alternatives](hosting-status.md). The local engine and recorded demo remain available.

Live application: https://smartseat-ai-9059.vercel.app/

Run `./Start-PublicApp.ps1` from this project on the restaurant laptop. It checks the dedicated engine on `127.0.0.1:8766`, starts it if needed, checks/starts the loopback router on port 8767, and verifies the public connector. Existing requests for the other local app continue to port 8765. The `/smartseat-engine/*` namespace is reserved for SmartSeat; its API routes go to port 8766. The script does not stop other apps or change their data.

Sign in with Google, open **Account**, and connect the restaurant using its existing engine manager/staff credentials. New Google sessions deliberately require pairing again. No camera access is granted just because someone has a Google account. The local engine continues enforcing its own manager/staff permissions.

The hosted Supabase project is `tnwrnwhitnbxuhdfuwvh`, in the user's organization. Managed Auth stores identities; PostgreSQL stores private profiles, workspaces, memberships, constrained audit events and actual synced floor/report data. Row-level security separates accounts. The existing local SQLite database remains the source for operational restaurant records and camera configuration. Frames and model weights are not uploaded as database records.

The restaurant laptop, engine, router and connector must remain online for live inference and restaurant changes. During outages, saved reports show their timestamps; camera evidence is invalidated. This free public connection is not a managed always-on production engine. The launcher fails rather than changing an unexpected connector or claiming a failed health check passed.

The production gateway's `SMARTSEAT_ENGINE_ORIGIN` includes `/smartseat-engine`. Public connector configuration and private credentials stay in ignored local files or deployment environment settings. Do not commit or share `local/`, OAuth client JSON, session cookies or environment secrets.

Run `./Publish-SmartSeat.ps1` to build and deploy the web UI and gateway. The staging allowlist excludes local databases, camera images, model files and credentials. If the CLI loses its connection after deployment, use `vercel inspect` to confirm the existing deployment and alias before redeploying.

The per-user monitor and encrypted-backup tasks are installed. Account → Restaurant safeguards shows their actual status and the retention/access preview. Actual engine and router failures were recovered by the supervisor, and an isolated encrypted-backup restore passed. Owner recovery email delivery and the reset callback/form were verified without changing the password. Both launchers refuse missing or unrecognized databases instead of initializing replacements.

See [TOP_QUALITY_CHECKLIST.md](TOP_QUALITY_CHECKLIST.md) for remaining acceptance work: visible real table mapping and physical occupancy/clearing cycles, installed-restaurant accuracy/full shift, public email signup delivery via authorized SMTP, owner retention/staff sign-off, a future real Windows logon and offsite/full hosted Auth recovery. A dark frame is not evidence of a clean or empty table.
