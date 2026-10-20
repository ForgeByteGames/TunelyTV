> **v0.9.6 update:** Parts of this earlier development document describe a prior version. Current implementation details and new Railway instructions are in [V0.9.6-LICENSE-AND-ENTITLEMENTS.md](V0.9.6-LICENSE-AND-ENTITLEMENTS.md).

# TunelyTV v0.9.1 — Multi-View testing notes

## Included
- Toolbar **▦ Multi-View** button, 2-pane and 4-pane layouts, independent channel choices, video controls, switchable single active audio source, Stop All and Exit.
- Full-viewport immersive browser layouts on desktop and phone, with an optional browser fullscreen toggle, compact per-screen channel/audio/stop controls, and no page chrome while viewing.
- Signed-in plan lookup: Free = 0 panes, Plus Lifetime = 2, Premium/Family = 4 in TEST billing state. Private invitation-only staging may enable `TUNELY_MULTIVIEW_PRIVATE_PREVIEW=true` to show a 4-pane preview even when no Stripe test plan exists.
- Each pane opens user-supplied streams **directly in the viewer's browser**; HLS.js used when available. No content proxies, provider circumvention, channel bundles, recording, or stored extra source credentials.

## Try from the phone now
Open `TunelyTV-Live-TV-v0.9-MultiView-Preview.html` in a capable browser. Choose **Add a source**, acknowledge source permission and upload your own `.m3u` playlist. Tap **▦ Multi-View** in the player toolbar; choose 2 or 4 panes, then select a channel in each. The HTML preview has no included playable streams. Browser-file HLS playback may not work on every phone; the visual layout can be explored regardless.

## Try after deployment
1. Deploy v0.9 to private Railway staging, with persistent database and `TUNELY_SIGNUP_CODE` set.
2. Optional for internal testing only: add `TUNELY_MULTIVIEW_PRIVATE_PREVIEW=true`. **Do not leave enabled on public launch.**
3. Sign in on the dashboard, open `/watch`, load an authorized saved playlist or local M3U, and click **Multi-View**.
4. Verify play/stop, 2↔4, audio source switching, playlist change, single-view switch, provider connection limits, and mobile compatibility.
5. Remove preview env var to check locked Free access.

## Limitations / pending
- Google Sign-In and paid purchase remain not enabled; Stripe is test-only, without account no Stripe transactions.
- The approved **7-day Plus trial is specified but not activated/enforced**; Free web/phone restrictions and TV slot limits are also pending in the rest of the app.
- 4 panes represent a layout capability, not a promise of 4 simultaneous authorized streams. Some devices cannot decode 4 streams; individual streams may fail due to HTTPS/CORS/codec restrictions or provider connection limits.
- No TV application, Tunely Home DVR, provider catch-up, or cloud recording included. No live provider media playback tested in automated checks.

## Automated testing
- `PYTHONPATH=. python -m pytest -q tests` includes per-account Multi-View access checks.
- Desktop/mobile Chromium tests used isolated interface fixtures with non-working sample URLs, not real content.
