# Owner data and staff-access review

The manager-only **Account → Restaurant safeguards** panel shows the actual engine accounts and a non-destructive retention preview. It does not create staff accounts, record owner consent, delete restaurant records or certify restaurant readiness.

## Current access boundaries

| Identity | Access |
| --- | --- |
| Signed-out visitor | Public availability/auth configuration only; no restaurant floor, frames, reports or operations status. |
| Google account without restaurant credentials | Its own private cloud workspace and previously saved records; no live camera or restaurant mutations. |
| Paired restaurant staff | Floor/camera viewing, service confirmations, waitlist, reservations and operational analytics under the engine's existing staff permissions. |
| Paired restaurant manager | Staff capabilities plus camera/table configuration, creation of engine staff accounts and the private safeguards/access preview. |

Google identity and engine permissions are separate. A fresh account sign-in clears the prior engine proof. Backups and the background monitor run only under this signed-in Windows user; they do not grant another user database or camera access. No additional real staff accounts were invented for testing.

## Retention inventory

| Data | Current behavior | Review proposal |
| --- | --- | --- |
| Live camera frames | In-memory processing; no continuous video recording by the application. | Keep recording off unless a separate recording/retention requirement is approved. |
| Latest surface observations | Latest record per mapped table; evidence expires after five seconds and cannot certify sanitation. | Keep only this latest operational record. |
| Completed visits, past reservations, activity | Stored in SQLite; actual report copies in the private cloud workspace. | Preview completed records older than 90 days. |
| Closed waitlist entries | Stored in SQLite. | Preview completed entries older than 30 days. |
| Sessions | Engine access expires after 12 hours; expired records are removed on a subsequent login. Managed cloud tokens are validated/refreshed by Supabase. | Review separate account/session requirements before enabling a different policy. |
| Encrypted backup archives | Created daily and at logon, retained locally; same Windows DPAPI profile is required. | Owner chooses archive retention/offsite recovery requirements. |
| Monitoring incidents | Bounded, aggregate operational records; no camera pixels, guest names, passwords, tokens, RTSP sources or raw service responses. | Review the documented log bounds in monitoring.md. |
| Acceptance screenshots | Deliberate local inspection evidence, separate from continuous camera recording. | Owner decides when acceptance evidence can be removed. |

Automatic deletion is **disabled**. The preview reports candidate counts without deleting or changing live records. Active visits, live queue entries and future bookings are excluded from the proposed age checks. A restaurant owner still needs to accept retention periods and assign real individual staff credentials before a staffed launch; this document does not manufacture that approval.

## Physical restaurant acceptance

Keep the camera fixed with the whole tabletop and seating area visible. Map the observed seating polygon and confirm real capacity. Observe a real empty period, an actual seated person, departure, visible items left behind, and the same surface after items are removed. Confirm actual wiping/cleaning only after a person performs it. Save the actual times and observed transitions; do not use a manual status button as proof of automatic occupancy, and do not label an item-free view as proof of sanitation.

Precision/recall and complete-shift acceptance need labeled observations from the restaurant's installed cameras and real service activity. A laptop session cannot establish performance across other restaurants, lighting conditions, crowding or all table designs.
