# TunelyTV v0.10.0 — Playlist Movies/Series vs Where to Watch

See [V0.10.0-PLAYLIST-LIBRARIES.md](V0.10.0-PLAYLIST-LIBRARIES.md) for source-type selection, use of an existing Sintel HLS URL, licensing precautions and deployment details.

# TunelyTV v0.9.9 — Last Channel & Viewing Navigation

New in v0.9.9: reopen the user's most recent channel per selected playlist, attempt playback (muted fallback where browser requires), improve empty-player copy, correctly open the TV guide from fullscreen, and add links to official external streaming-service sites from service discovery cards and detail panels. Provider links are service landing pages, **not exact title deep links**; TMDb does not supply those. Licensing, EPG, Multi-View and provider-logo logic from v0.9.8 remain intact. See `V0.9.9-PLAYER-AND-EXTERNAL-NAVIGATION.md`.

# TunelyTV v0.9.8 — Live Guide Preview and Provider Logos

New in v0.9.8: A live picture preview in the full-screen guide using the existing video player, HTTPS channel logos from the user's M3U/XMLTV metadata, and accessible XMLTV guide setup from within TV mode. See `V0.9.7-GUIDE-PREVIEW-AND-LOGOS.md`. This release retains v0.9.6 licensing and TMDb-ready code (TMDb remains disabled until commercial rights are secured).

# TunelyTV v0.9.6 — License & Entitlement Management

The complete Railway-ready private staging source package. Based on v0.9.5, preserving its blue discovery homepage, minimal Live TV mode, full-screen EPG, automatic XMLTV discovery, M3U account playlists, pairing simulator, cloud favorite/recent-channel endpoints, and test-only Stripe implementation.

## New in v0.9.6

- Real server-enforced **seven-day Plus trial**: one per eligible account, no card and no automatic payment, server-time expiration.
- **Plus One-Time ($19.99)** major-version license records, starting with v1.x; future major software versions are not automatically included.
- Per-account feature API and runtime gating for web playback, 2-/4-pane Multi-View, and registered TV allowances (provisional paid TV slot counts).
- Secure, one-time verified Owner setup and an owner-only read-only customer/entitlement/audit dashboard. Owner can test Multi-View without purchasing; the former global private-preview bypass is disabled.
- Preserves customer playlists, device records and preferences when access expires. Expired subscriptions revert to the purchased Plus major or Free, as applicable.
- Signed Stripe TEST-mode purchase grants and matched full-refund revocation; no live Stripe charges.

**See [V0.9.6-LICENSE-AND-ENTITLEMENTS.md](V0.9.6-LICENSE-AND-ENTITLEMENTS.md) for full endpoints, limitations, and safe Railway upgrade/owner instructions.**

### Development pricing

| Tier | Charge | Web/phone/tablet | Registered TVs | Multi-View |
|---|---|---|---|---|
| Free | $0 | No | 1 | No |
| Plus 7-day trial | $0/no card | Yes during trial | 2 (proposed) | 2 panes (private staging) |
| Plus One-Time | $19.99 once for a designated major version | Supported web/phone/tablet (scope before launch TBD) | 2 (proposed) | 2 panes (private staging) |
| Premium | $4.99/mo | Yes | 3 (proposed) | Up to 4 panes (private staging) |
| Family | $7.99/mo | Yes | 5 (proposed) | Up to 4 panes (private staging) |

Annual Premium $29.99 and Family $49.99 are **proposals**, not approved or implemented for Stripe. All charges are disabled in this staging project unless explicit Stripe *test* integration is configured. Tunely Home/DVR and catch-up are not implemented; no TV channels, media, provider access, or third-party subscriptions are included.

### Deploy

Update the **existing** `ForgeByteGames/TunelyTV` repository and Railway service, preserving its `tunelytv-volume` mounted at `/app/instance` and current environment variables. Do not expose secrets in GitHub. New `licensing.py` and `/static/license-v096.js` are required for the release. Verify `/api/health` returns `0.9.6` and test account authorization after redeploy.

Run local tests: `PYTHONPATH=. python -m pytest -q` (with pytest/httpx installed). Local app: `python -m uvicorn server:app --reload --port 8765` after installing `requirements.txt`.

**Not yet public-launch ready:** licensing and TV/device restrictions are staging-grade; actual Stripe live payments, store receipts, owner recovery, paid upgrade checkout, native clients, legal review, production logging and disaster recovery remain pending.

### TMDB discovery integration (pre-launch preparation)

The v0.9.6 code includes optional, server-side title/series search, trending rails, provider-reported availability, and country-specific title details. This ready-state patch adds JustWatch/TMDB text credits, a provider name compatibility fix, and an explicit **rights confirmation gate**. It does **not** add licensed data, images, or streaming channels.

**Do not activate for paid/commercial TunelyTV until a written commercial TMDB agreement and required branding/credits are completed.** See `TMDB-SETUP-AND-RIGHTS.md`.


## v0.9.8 automated missing channel logos

See `V0.9.8-AUTOMATIC-CHANNEL-LOGOS.md` for the CSP fix, directory matcher, rights requirements and opt-in variables. Directory matching is OFF by default. Provider and XMLTV HTTPS logos load without it.
