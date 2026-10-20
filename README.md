# TunelyTV Web v0.9.1 — Multi-View + Live Player + TEST Billing

**Status: complete staging source package, not yet uploaded to GitHub or deployed to Railway.** Based on v0.7, preserving M3U playback, authorized XMLTV grid/list/mini guide, favorites/recent channels API, local and saved playlists, account dashboard and device pairing simulator.

**TunelyTV is software, not an IPTV channel/provider subscription.** All streams are independently supplied by their authorized users. This package bundles no TV streams, third-party station logos, movies, premium sports channels, or retransmission proxy.

## v0.8.1 plan transparency update

- Plan & Billing now has detailed plan cards and a mobile-scrollable comparison matrix. Prices are unchanged.
- **Currently working in staging**: compatible browser live TV, user-supplied M3U, guide/mini guide, cloud favorites for saved playlists, web account management and the TV pairing simulator.
- **Proposed but not yet implemented/enforced**: Plus channel organization and additional allowances; Premium Tunely Home Windows DVR (subject to rights review), Family household profiles/favorites. These are **not yet available for purchase in live mode**.
- This is a feature-description / UI update only. No plan access rules or payments have been changed. Do not advertise or sell planned features before release.

## v0.8 additions (implemented)

- Branded **Plan & Billing** dashboard: Free $0, Plus Lifetime $19.99 one-time, Premium $4.99/month, Family $7.99/month, current plan, status, cancellation period and billing portal action when configured.
- `GET /api/billing/status`: authenticated, user-scoped subscription view, server-defined pricing, and whether **Stripe test** is available.
- `POST /api/billing/checkout`: authenticated CSRF-protected Stripe-hosted **test checkout**. Fixed server-side price IDs, live price configuration verification (USD cents + monthly interval), strictly allowlisted plans and rate limits. No card details pass through TunelyTV.
- `POST /api/billing/portal`: authenticated CSRF-protected Stripe **test customer portal** for existing accounts.
- `POST /api/billing/webhook`: raw-body Stripe signature verification with timestamp tolerance, event de-duplication, owner-scoped billing and entitlements. Successful redirect cannot itself unlock a plan.
- Plus Lifetime tracked independently from active monthly subscription; users may retain purchased Plus when a monthly subscription ends.
- **Google Sign-In preparation**: visible accurate pending state, provider configuration notes, recommended security architecture; actual Google login is *not implemented*. Existing password sign-in is preserved.
- Test mode disabled unless explicitly enabled and all test credentials supplied. **LIVE payment keys are intentionally rejected** by this build.
- Existing player v0.7 and app pairing system remain available at `/watch` and `/tv`.

## Prices

| Plan | Price | Billing | Tunely Home |
|---|---:|---|---|
| Free | $0 | None | No |
| Plus Lifetime | $19.99 | One-time purchase | No |
| Premium | $4.99 | Monthly | Planned, subject to recording-rights review |
| Family | $7.99 | Monthly | Planned, subject to recording-rights review |

**Important:** Definitive included features, device limits, Plus Lifetime scope, customer refunds, sales taxes, subscription disclosures, recording rights, and business/legal review remain to be finalized before selling. Stripe test entitlements are development data; the v0.8 player currently **does not enforce paid-tier entitlements on specific player features**. Do not turn on public paid sales with v0.8.1.

## Local launch

Python 3.11+ (Python 3.12 in Railway Dockerfile):

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate   |   Unix: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8765
```

Visit `http://127.0.0.1:8765`. Open dashboard → Plan & Billing. Checkout disabled by default. Run tests: `PYTHONPATH=. python -m pytest -q tests/test_api.py` (with pytest and httpx installed).

## Documentation

- `RAILWAY-DEPLOY.md`: hosting, domain, secrets, persistence, testing.
- `STRIPE-TEST-SETUP.md`: test-only activation and event configuration.
- `GOOGLE-SIGNIN-PLAN.md`: Google OAuth / account linking steps.
- `BEFORE-LAUNCH.md`: legal, security, privacy and operational blockers.

## Testing

11 automated backend tests passed locally, including five v0.8-specific billing assertions within three new tests. **Real Stripe network transactions, a real registered payment account, Google OAuth, deployed site, browser streaming and production-grade security have not been tested.** Standalone offline plan preview passed desktop/mobile Chromium rendering and markup checks using injected HTML; this does not verify deployed server workflows or playback. Any supplied standalone preview is **UI-only**.

## v0.8.2 plan transparency update
The subscription screen and offline plan preview now explicitly mark **DVR recording, provider catch-up, Tunely Home Windows, and Multi-View** as either *Not included* or *Planned*. Free excludes all four. Proposed Plus includes authorized provider catch-up and 2-pane Multi-View, but excludes DVR and Tunely Home. Proposed Premium/Family include catch-up, enhanced Multi-View and Tunely Home DVR. The enhanced layout targets four panes but no four-stream playback entitlement is promised. **Update for v0.9.1: Multi-View has a working private browser prototype and a plan-access API. DVR, Tunely Home, and catch-up remain unimplemented. No plan is ready for public sale.** Details are in PLAN-FEATURES-REVIEW.md.


## v0.8.3 platform-neutral subscription language
Pricing descriptions no longer brand subscription tiers as "web-only". Plans apply to TunelyTV software benefits across compatible clients as supported apps are released. Current testing still runs in the browser and TV simulator; future native applications and enforcement are **not available yet**. No changes to pricing or payment behavior.


## v0.8.4 pricing and trial entitlement plan

Approved: 7-day free Plus Lifetime trial, no credit card and no automatic billing; after expiration return to TV-only Free (one registered TV, no web/phone/tablet playback). The pricing page now shows this policy as **planned, not yet active**. Paid plan TV slots 2/3/5 remain proposed. See `PLUS-TRIAL-AND-ENTITLEMENTS.md` for the full implementation and test checklist. **Do not interpret the preview UI as trial activation or enforced access.**

## v0.9.1 Multi-View (new)

- The web player has a **Multi-View** button that swaps the single-player view for independently selectable **2-screen** or **4-screen** layouts. Each pane has its own browser-native video controls, channel selector, error state, and Stop button.
- Only **one pane is unmuted at a time**; users select the audio source. Exiting Multi-View or changing playlists stops and releases every active connection.
- Browser sources remain customer-authorized HTTP(S)/HLS only. No bundled content, DRM circumvention, proxy or recording. Simultaneous provider streams can be blocked or billed by the user's provider.
- New authenticated `GET /api/features/multiview` reads per-account **Stripe TEST billing state**: Free 0 panes, Plus 2, Premium/Family 4. The current Plus **free-trial activation is not implemented**, so it does not yet grant access.
- **Private-test option**: set `TUNELY_MULTIVIEW_PRIVATE_PREVIEW=true` **with a nonempty `TUNELY_SIGNUP_CODE`** for 4-pane test access to signed-in invitees. Do not use the override in a public launch. Offline preview HTML allows the layout to be explored without a payment account.
- This is not production media license enforcement: streams are requested directly by the visitor's browser, not a TunelyTV relay. Subscription UI gate cannot itself enforce third-party provider simultaneous-connection rights.
- **Critical remaining work before release**: implement Plus trial activation/expiry, Free plan web access restrictions, TV slot counting, actual payment entitlement enforcement for production, legal/provider rights review, performance validation, native clients, and real licensed-source playback tests.

See `MULTIVIEW-TESTING.md` for test and staging setup.


### v0.9.1 immersive Multi-View
Multi-View now fills the entire browser viewport, hiding sidebars and TV guide while open. Two-pane desktop uses side-by-side video; portrait mobile stacks panes. Four-pane uses a large 2x2 grid. Channel controls overlay each pane to maximize video area. The optional Fullscreen button requests native fullscreen when supported, and Exit closes all video connections.
