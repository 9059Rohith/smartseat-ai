# Uploaded media analysis

The separate Media Analysis navbar page accepts actual chosen images and videos. It uses local YOLOX and optionally Grounding DINO inference, colored table proposals and a per-selected-frame summary bar. It never substitutes uploaded pixels into the live camera, creates restaurant tables, or writes visits/cleaning/report history.

## Data flow and bounds

- The original file stays in the browser. Browser-supported images/video are decoded locally; JPEG frames at up to 960 pixels on the longest side are submitted to the paired engine.
- Up to 250 MB local input and 10 minutes of video; maximum 120 timestamps across the whole clip. Snapshot review playback is explicitly sampled, not continuous tracking.
- Authenticated `POST /api/media/analyze` accepts at most 1 MiB actual JSON bytes. It verifies JPEG bytes/metadata and at most 2048 × 2048 decoded pixels, then returns an ephemeral job ID.
- Authenticated `GET /api/media/jobs/{id}` returns only the same engine user's job; `DELETE` discards it. Another engine user receives 404. The job ID is an unpredictable token.
- Two unfinished jobs globally, twenty retained jobs, five-minute expiry and a single worker. Cancellation discards results and stops more submissions; already-running CPU inference finishes before its slot is released.
- Existing detector/DINO locks serialize model access. The camera's source, mapped zones, tracking thresholds and state transitions are unchanged.
- Original files/frames are not stored on disk or in cloud reports by this feature. The browser keeps completed frame previews for the current page until clear/navigation. Model outputs contain geometry, supported labels, timestamps and counts.

## Semantics

Red is visible person overlap, amber is supported visible items without person overlap, green means no supported items/person overlap were found, and gray is unverified evidence. Blue dashed boxes are person proposals. Green never means sanitized or staff-confirmed cleaned. IDs and statistics apply only to the current frame and are not unique-table/customer totals across a clip.

Images default to the broader scan; videos default to faster YOLOX. Broad CPU scans take tens of seconds and can exceed a minute under load. Unsupported codecs fail with an actionable error. The upload-only person threshold is 0.40, following a verified orange-chair false positive at 0.25 in the licensed empty round-table photo; the live threshold stays unchanged. This conservative choice can miss weak people detections and does not establish field precision/recall.

## Verification

- Real public photograph inference, JPEG/JSON/body/dimension validation, auth-before-image-parsing, no restaurant mutations, cross-user ownership, deletion/expiry and bounded queue checks are in `tests/test_media_analysis.py`.
- Node regressions check exact-route size bounds, sampled timestamps and actual per-frame CSV rows.
- Browser QA exercised the public round-table photograph with broader inference, then an explicitly AI-generated four-second extract of the upstream DineAssist development clip. The actual sampled clip yielded four analyzed frames with changing real model counts and correctly paired source timestamps; CSV export had four matching data rows. This is upload-pipeline evidence, not real restaurant accuracy acceptance.
- Desktop and 390 × 844 responsive review, frame slider, play/pause, annotated download and clear/cancel behavior are checked during release QA. The original production live camera is kept separate throughout.

Endpoint/runtime tests do not replace physical table occupancy/cleaning acceptance. See the main release checklist for that work.

## Production acceptance — 5 November 2026

Production deployment `dpl_HMgoZRE6TpYD68BdQ74sfWCutpif` is ready at https://smartseat-ai-9059.vercel.app/. The authenticated public browser uploaded the real round-table photograph: local YOLOX plus the broader scan returned one correctly placed green table proposal, zero people and about 17 seconds measured inference. It then uploaded the clearly labeled four-second upstream development clip: all four sampled timestamps completed; the final frame had nine table proposals, seven visual in-use regions and two looks-clear regions. Counts are model observations, not manually seeded service records.

Public play/pause advanced the selected source timestamp and summary together. Actual CSV export returned four matching rows. The laptop camera continued independently after engine restart; the production SQLite counts remained one camera and zero tables, visits, queue records, reservations or events. All 61 Python tests, 25 Node tests, the Vite production build and seven safe live authentication checks passed. An independent reviewer found no blocking issues. Browser console had no warnings/errors at the checked upload screen.

The README screenshot is actual production upload analysis on the AI-generated upstream test clip, with its MIT attribution preserved in `demo/DineAssist-LICENSE.txt`. It is not a live-camera demonstration or a physical restaurant acceptance claim.

The mobile-navbar follow-up is deployed as `dpl_U2zkhpfo8MeKfSSHvTWENSuoWN1m`. The final public check at a 390 × 844 viewport returned document width 375 and scroll width 375 (no horizontal page overflow), all seven navigation items were present, and the browser console was clear. The independent live camera continued to process fresh frames during upload QA (48 → 995 observed frames after restart). The app is left paired on the empty Media Analysis page, ready for the user's own upload.
