# Hosting status — 11 November 2026

## Public application

The configured address is https://smartseat-ai-9059.vercel.app/. GitHub points to that correct address, but Vercel currently rejects it with HTTP **402**, `X-Vercel-Error: DEPLOYMENT_DISABLED`.

An authenticated inspection of the correct Vercel team returned:

- Plan: Hobby; billing status: active.
- Team soft-block reason: `FAIR_USE_LIMITS_EXCEEDED`.
- Resource type: `fluidCpuDuration`.
- Block started: 6 November 2026, 18:17 IST.
- Provider-reported `unpauseAt`: **6 December 2026, 18:17 IST**. This is a scheduled provider timestamp, not a guarantee that access will resume.
- The existing production deployment is still marked Ready. A Ready build does not override a team-level serving block.

This is a shared-team CPU allowance; the available evidence does not establish which project or traffic source consumed the allowance. It is not a missing repository, bad application URL, paused laptop camera or failed application build.

The project has not been upgraded, no billing setting was changed, and no new account/project was created to circumvent the restriction. The existing URL remains unavailable until Vercel restores access. The owner can review usage and contact Vercel about the block; waiting for the free allowance reset is the no-upgrade route. A paid plan is not automatically authorized by this project.

[Vercel's deployment-disabled guidance](https://vercel.com/docs/errors/deployment_disabled) · [Team usage dashboard](https://vercel.com/rohiths-projects-5e14931b/~/usage)

## Working alternatives checked today

| Destination | Verified result | Scope |
| --- | --- | --- |
| [Recorded walkthrough](https://9059rohith.github.io/smartseat-ai/) | HTTP 200; linked MP4 also HTTP 200 | Recorded video, not an interactive app |
| [Local application](http://127.0.0.1:8766/) | SmartSeat web application and engine health return HTTP 200 | This restaurant laptop only; existing manager/staff login |
| Dedicated engine | `app=smartseat`, `demo=false`, one live camera | Local inference continues independently of Vercel |
| Loopback router | Correct SmartSeat router identity, HTTP 200 | Connector routing is still running |

Open the local address on the same laptop. On a new installation or different port, follow the README's local setup instructions. Do not stop another application on port 8765.

## Before declaring public service restored

1. Confirm the team no longer reports the CPU soft-block; do not treat a successful build alone as recovery.
2. Verify the public homepage and authentication configuration return HTTP 200 rather than 402.
3. Verify actual Google sign-in, restaurant pairing, fresh camera state and one media upload through the public gateway.
4. Review per-project CPU/request usage and the active/background polling behavior before leaving an unattended public dashboard running. No single-project cause has been established by the team-block response alone.
5. Update the README status after the checks pass. Do not relabel the recorded video as the working interactive application.
