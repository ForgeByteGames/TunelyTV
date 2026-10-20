# TunelyTV v0.9.1 deployment — Railway trial

**This package has not been deployed. Use the full v0.9.1 ZIP in preference to older 0.7 ZIPs.**

## A. GitHub

1. Open your **private** GitHub repository `ForgeByteGames/TunelyTV` from a computer.
2. Unzip the v0.9.1 package and upload the **contents** of the extracted directory (not the ZIP file itself). Keep `site/` and `tests/` folder paths and root files exactly as included.
3. Check GitHub carefully: never commit `.env`, credentials, local database/keys, or actual user playlists. Use the included `.gitignore`.
4. Commit `Initial TunelyTV v0.9.1 staging`.

## B. Railway

1. In Railway choose **Deploy from GitHub Repo** and connect the existing TunelyTV repository.
2. Railway detects the root `Dockerfile`. Root Docker service uses Python 3.12, uvicorn and the included entrypoint.
3. Add a persistent **Railway volume mounted at `/app/instance`**. Keep 1 replica and 1 worker while using SQLite; backups are your responsibility.
4. Set these required Railway Variables (values are examples; generate actual random secrets locally and enter directly in Railway):

| Key | Example / required behavior |
|---|---|
| `TUNELY_ENV` | `production` |
| `TUNELY_DB` | `/app/instance/tunelytv.db` |
| `TUNELY_FERNET_KEY` | Random Fernet key generated with `cryptography.fernet.Fernet.generate_key().decode()` |
| `TUNELY_SIGNUP_CODE` | Your own strong invitation-only registration code |
| `TUNELY_ENABLE_STRIPE_TEST` | `false` (default and recommended until Stripe setup) |

**Never change the Fernet key without migrating encrypted saved playlists; permanent loss of that key loses the ability to decrypt existing data.** Secure backups must include the SQLite volume and separate protected key copy.

5. Railway can assign a temporary `*.up.railway.app` domain for first HTTPS testing. Private invitation signups only.
6. Once working, add `stream.tunelytv.com` as a Railway custom domain; add the **exact DNS records Railway shows** to GoDaddy (or the authoritative DNS provider). Do not invent server addresses or modify your domain apex DNS.
7. Confirm `/api/health` returns version `0.9`, then test registration, pairing simulator `/tv`, playback `/watch` with *your own authorized* browser-compatible HLS source.

## C. Stripe is optional on Railway

If you don't have a Stripe account, **skip all Stripe variables**. The billing page still displays official plan prices, but checkout and billing management remain disabled. The app runs normally.

When ready to test Stripe, follow `STRIPE-TEST-SETUP.md`; Stripe webhooks are at `https://stream.tunelytv.com/api/billing/webhook`. This edition accepts **test keys only** and cannot collect live payments.

## D. Google Sign-In

Visible as **pending**; it is not functional. See `GOOGLE-SIGNIN-PLAN.md`. Do not advertise Google login as available until implemented and verified.

## E. Before external launch

Staging has private invite codes but needs production review of abuse controls, authentication, session handling, data protection, payment reconciliation, plan enforcement, incident response, copyright process, business/tax obligations, and customer legal documents. See `BEFORE-LAUNCH.md`.

## Plan comparison
The plan comparison labels staging features versus proposed benefits. The Multi-View private browser prototype has account-scoped plan API (Free 0, Plus 2, Premium/Family 4), but the **7-day trial, general paid-feature rules, TV slot restrictions and production playback authorization** are not yet implemented. No live checkout.

### v0.8.2 pricing information
The pricing screen includes explicit inclusion/exclusion statuses for DVR, provider catch-up, Tunely Home and Multi-View; DVR, catch-up and Tunely Home are still only proposals. Multi-View has a **private web prototype**, but is not publicly released. Do not advertise them as active subscriptions or accept live payments before implementation, entitlement enforcement, and legal review.

### v0.9.1 Multi-View private staging

The signed-in web player has a **▦ Multi-View** button in the toolbar. To try 2/4 panes without Stripe on an **invite-only private test environment**, set an optional variable:

`TUNELY_MULTIVIEW_PRIVATE_PREVIEW=true`

**Security condition:** `TUNELY_SIGNUP_CODE` must also be set to a nonempty private invitation code. Do not enable the preview flag for an unrestricted/public launch. The flag grants 4-pane **staging preview only**, not purchase, lifetime licenses, or production entitlements. Remove this flag before general availability.

Without that flag, `GET /api/features/multiview` requires an authenticated account with an existing test billing entitlement (Plus=2; Premium/Family=4; Free=0); the seven-day Plus trial is not activated by this version.

Open `/watch` → import an authorized M3U → select **Multi-View** → choose 2 or 4 screens and one channel per pane. Select **Listen here** for the single audio stream. Test with a source explicitly permitting concurrent browser streams. Verify all media stops after **Exit** or **Stop all**.

The standalone v0.9.1 preview can be opened without Railway; it accepts user-supplied local M3U files and shows test layouts. It does not grant production access.


The v0.9.1 Multi-View theater takes over the viewport and supports optional browser Fullscreen API. No infrastructure changes are required from v0.9.
