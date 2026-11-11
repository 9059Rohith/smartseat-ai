# Full public application — 11 November 2026

**[Open the working application](https://9059rohith.github.io/smartseat-ai/app/)**

Direct HTTPS address: https://bee-nonintersecting-overwarily.ngrok-free.dev/smartseat/

This is the interactive web app, available from another laptop's browser. The GitHub Pages `/app/` address redirects to the public app; the Pages root still hosts the separately labeled recorded walkthrough. It does not replace the application with a video.

## Access

1. Open the application link. On the free ngrok notice, choose **Visit Site**.
2. Continue with your existing Google account.
3. In **Account**, connect with the restaurant's existing manager/staff credentials. New browsers require this pairing; Google identity alone does not grant access to the camera.
4. Use Floor, Waitlist, Reservations, Analytics, Cameras and Media Analysis normally. Uploaded media uses actual local inference and never becomes the live camera source.

The restaurant laptop must be powered on, awake, signed in and online. Other laptops do not install Python, models or the database. The free connector remains subject to its provider's limits. This is laptop-hosted availability, not a managed 24/7 hosting guarantee.

## Runtime

HTTPS connector → loopback router on port 8767 → `/smartseat/` Node gateway on port 8768 → Python engine on port 8766. The gateway reuses managed Supabase identity, RLS, workspace data and engine authorization. Engine inference and SQLite remain on the laptop.

Other router paths continue to the existing application's port 8765. `/smartseat-engine/api/*` remains the dedicated engine API. Internal listeners bind only to 127.0.0.1; no private database/configuration directory is served. The public static allowlist covers only the built index/favicon/assets.

The prefix build uses `/smartseat/` for APIs, assets, OAuth callbacks and navigation. Auth cookies remain Secure/HttpOnly and are scoped to this prefix. CSRF Origin checks remain exact; new Google sessions still require engine pairing. All six old/new Supabase callbacks were retained; Google client credentials were not changed.

The router overwrites client-supplied identity headers. It uses ngrok's validated final appended X-Forwarded-For value and a per-router salted HMAC to assign opaque rate identities. The gateway trusts this key only in explicit local mode from the loopback router. Vercel's original identity rules remain unchanged. [ngrok documents the last-value rule](https://ngrok.com/docs/gateway/endpoints/http).

## Startup

From an already configured installation:

```powershell
./Build-PublicApp.ps1
./Start-PublicApp.ps1
```

Build installs missing gateway/web dependencies and writes the prefix bundle into ignored `local/public-runtime/`. Startup verifies the existing restaurant database, engine/router/connector and starts the public gateway if configured. It refuses unexpected occupied ports and never creates a replacement production database.

Private `local/public-connection.json` adds `public_app_origin` (the HTTPS connector origin, without a path) and `gateway_port:8768` to the earlier engine/router configuration. The public app origin must match the existing connector host. `local/cloud-env-private.json` supplies only the dedicated project's `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`; no service-role or Google secret is needed by the browser or local gateway. Do not publish either configuration file or any cookies.

The existing Windows monitor checks the configured gateway and can restore it with the guarded startup command. Missing/unrecognized databases and wrong service identities still block recovery. Backup schedules remain in place.

## Verification

- A fresh public browser passed the connector notice, actual Google account callback and existing restaurant pairing.
- The authenticated app received real 640×480 camera pixels from `/smartseat/api/cameras/1/frame` and fresh person/table proposals. No table maps or service records were fabricated.
- Actual last-seven-day owner reports refreshed over the public URL.
- A clearly labeled four-second AI-generated upstream test clip uploaded through Media Analysis; all four sampled frames completed with actual local-model boxes and summary counts. The final test frame returned nine table proposals, seven in-use regions and two looks-clear regions. This verifies the upload pipeline, not field accuracy.
- Anonymous private state is denied (401), private static paths return 404, and invalid callback redirects stay within `/smartseat/`.
- The existing application on port 8765 retained an identical OpenAPI fingerprint after routing changes.
- Regression checks cover spoofed proxy identities, independent limits, prefix callbacks/cookies/assets, actual body bounds, static allowlist and optional gateway recovery. Physical restaurant accuracy/cleaning acceptance remains separate.

## Legacy Vercel address

The old `smartseat-ai-9059.vercel.app` address is still provider-disabled for the Hobby team's CPU allowance. No paid upgrade, new Vercel account or quota bypass was used. The working runtime above is a separate, legitimate hosting path on the already-running restaurant laptop. See [the historical block details](hosting-status.md).
