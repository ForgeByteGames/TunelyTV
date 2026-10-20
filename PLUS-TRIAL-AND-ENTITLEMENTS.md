> **v0.9.6 update:** Parts of this earlier development document describe a prior version. Current implementation details and new Railway instructions are in [V0.9.6-LICENSE-AND-ENTITLEMENTS.md](V0.9.6-LICENSE-AND-ENTITLEMENTS.md).

# TunelyTV — Approved Plus Trial & Device Entitlements (v0.8.4 plan)

**Status:** Pricing and trial policy APPROVED by project owner on 2026-10-20. This file specifies behavior for implementation; v0.8.4 does **not** implement live trial activation or entitlement gates. Do not deploy this as a working paid authorization system or advertise unavailable device apps.

## Approved pricing / intended access

| Plan | Price | Registered TV slots | Phone, tablet and web playback | Notes |
|---|---|---:|---|---|
| Free | $0 | **1** | **Not included** | TV-only plan. Hold the consumer-facing Free offering until a supported TV app ships. |
| Plus Lifetime | $19.99 one-time | **2 proposed** | Included | Lifetime purchase scope/terms still require finalization. |
| Premium | $4.99/month | **3 proposed** | Included | Tunely Home / DVR planned, not active. |
| Family | $7.99/month | **5 proposed** | Included | Household profiles planned, not active. |

**TV allowances 2/3/5 are proposed, not yet explicitly signed off; Free 1 TV and no phone/tablet/web are approved.** Platform limits count authenticated registered **TV apps** only. Web browser, phone and tablet apps do not consume TV slots for entitled plans. Simultaneous stream limits are a separate, unresolved policy and subject to third-party provider permissions.

## Approved introductory trial

- Eligible account holder can **opt in** to **one seven-day trial of the Plus Lifetime feature tier**.
- Trial begins when they intentionally activate it (not automatically on account creation).
- Seven consecutive 24-hour periods from backend-recorded UTC `trial_started_at`; `trial_ends_at = started + 7 days`.
- **No payment card required or collected. Never charge or create a recurring subscription automatically.** Do not require Stripe to activate or expire the free trial.
- While active, trial users get the Plus tier's currently released features, including eligible web, phone and tablet access, and up to the **proposed** Plus TV limit once supported apps exist. The trial does **not** unlock Premium/Family, Tunely Home, DVR, or features not yet built.
- After expiration, access automatically **reverts to the Free tier**: 1 TV slot and **no web/phone/tablet playback**, unless user voluntarily buys another plan. Show clear end date beforehand.
- Saved playlist configurations, preferences, and account records remain; revoke playback/access to non-entitled device apps instead of deleting user content.
- If more TV devices were registered than the Free limit, preserve records but mark overflow TV profiles inactive until user chooses one permitted TV. Implement deterministic selection UI; do not silently erase devices.
- Because the first release is a web-only build and Free lacks web playback, expired trial users can still **sign in to manage account, playlists, and purchase options** but cannot play streams in browser. The supported Free TV playback will become usable only when the TV application is released.
- No automatic purchase of $19.99 Plus Lifetime, no automatic downgrade charge, and no opt-in by silent prechecked box.

## Implementation requirements (NOT YET BUILT)

1. **Database:** per-account trial state (`never_started`, `active`, `expired`), timestamps (UTC), immutable first-use record, audit log, account-level unique eligibility rule. Preserve records after upgrade/deletion per retention/privacy policy.
2. **API:** authenticated, CSRF-protected `POST /api/trial/activate`; idempotent safe activation; `GET /api/entitlements` returns effective plan, trial clock, supported clients, TV cap, features, restrictions; single eligibility decision computed server side.
3. **Server enforcement:** check entitlements on ALL playback config grants, playlist access endpoints exposing stream secrets, registered TV pairing/activation, device sync, and app session issuance. Do not rely on JavaScript hiding buttons or stale cached entitlements. Re-evaluate expiration on every protected request; optional periodic cleanup or notifications are supplementary only.
4. **Risk controls:** limit trials to one per eligible account, prevent obvious re-enrollment abuse, rate-limit trial signup and pairing. Apply reasonable anti-fraud safeguards and transparent privacy treatment; do not claim this prevents every multi-account signup.
5. **Checkout:** trial is distinct from Stripe one-time Plus purchase. A trial cannot transition to billing without a deliberate user-initiated purchase/confirmation. Account subscription status should not claim Plus Lifetime is owned during trial.
6. **Account UX:** display countdown, explicit trial start and end, upgrade button, no-card/no-auto-charge notices and a clear expired state. Do not show a working “Start trial” button until endpoint, enforcement, and cancellation/expiration behavior are tested.
7. **TV apps:** bind registered TV slot to a verified TunelyTV app installation/pairing, not arbitrary MAC/IP. Provider device IDs are setup metadata, not access tokens.
8. **Plan lifecycle:** if purchased Plus or subscribed Premium/Family during trial, take the greater valid entitlement as defined by a future precedence policy, and never reactivate trial after expiration. Clarify cancellation, refunds, paid monthly downgrades, and lifetime update scope before charging.

## Acceptance tests before enablement

- Starting trial with no card returns a 7-day UTC expiration and Plus trial entitlements; cannot start twice.
- A brand-new account that does not start trial stays Free; Free web playback blocked once gates are enabled.
- During the trial, authorized browser playback can occur; 7 days later it is denied from browser, phone and tablet, but account management and saved playlist data remain.
- Clock changed on phone/browser cannot extend or restart trial; backend determines time.
- Other accounts cannot see or change trial state/playlist data.
- Expiring trial with 2 TVs returns to Free allowance of 1 registered TV without deleting saved TV records.
- No payment method stored or Stripe subscription created merely by starting/completing trial.
- Purchased Plus Lifetime continues after trial expires; Premium/Family rules are not mistakenly overwritten by an expired trial.
- Provider-provided content rights, EPG access and stream limits are still required on every tier.

## Current v0.8.4 deliverable

Updated **pricing UI copy and comparison table only**, plus this approved development specification. It does **not** activate a real trial, enforce device slots, gate Free web viewing or change Stripe operations. App remains private staging. Do not promise full functionality until backend checks are implemented and deployed.


**v0.9 update:** Multi-View is implemented as a **private web staging prototype only**, with a test plan-check endpoint and optional invitation-only preview. Trial activation/expiry and production entitlement enforcement are still not implemented.
