> **v0.9.6 update:** Parts of this earlier development document describe a prior version. Current implementation details and new Railway instructions are in [V0.9.6-LICENSE-AND-ENTITLEMENTS.md](V0.9.6-LICENSE-AND-ENTITLEMENTS.md).

# TunelyTV v0.8.4 — Pricing, Trial & Feature Allocation (current plan)

**Status:** The 7-day Plus Lifetime trial rules and the TV-only Free restrictions are approved for future implementation. The stage app is NOT enforcing these access rules yet. All listed paid features are proposals until implemented and confirmed. See `PLUS-TRIAL-AND-ENTITLEMENTS.md` for backend requirements.

| Feature / entitlement | Free $0 | Plus Lifetime $19.99 once | Premium $4.99/mo | Family $7.99/mo |
|---|---|---|---|---|
| Registered TVs | **1 (approved)** | **2 proposed** | **3 proposed** | **5 proposed** |
| Web playback | **Not included** | Included | Included | Included |
| Phone and tablet playback | **Not included** | Included | Included | Included |
| 7-day Plus Lifetime trial | Eligible new accounts can opt in | Trial includes current Plus benefits | — | — |
| Channel favorites, EPG & M3U | TV app functionality to be finalized | Web build supports core features | Web build supports core features | Web build supports core features |
| Catch-up (if authorized source supports) | Not included | Planned | Planned | Planned |
| Multi-View | Not included | 2-pane private browser test, unreleased | Up to 4-pane private browser test, unreleased | Up to 4-pane private browser test, unreleased |
| Tunely Home Windows companion | Not included | Not included | Planned | Planned |
| DVR recording via Tunely Home | Not included | Not included | Planned; recording rights review | Planned; recording rights review |
| TunelyTV-hosted cloud DVR storage | Not included | Not included | Not included | Not included |
| Household profiles | Not included | Not included | Not included | Planned |

## Approved Plus trial rules

- **7 days**, starting from explicit account-level activation; one introductory trial per eligible account.
- **No credit card required** and **no automatic charge or purchase**; Stripe must not be needed for free activation.
- During the trial, users receive currently available Plus plan functionality (including browser playback).
- On expiry, return to **Free with 1 registered TV and no phone/tablet/web playback** unless the user voluntarily purchases a paid plan.
- Save playlist/account configurations after expiry; don't delete customer preferences.
- Web-only first release: expired users can sign in/manage their accounts, but cannot watch until purchasing eligible access or a compatible Free TV app is available.
- The TV app is unreleased; DVR, catch-up and Tunely Home are not built; Multi-View is a private browser-testing feature, not a launched paid benefit. Device slot enforcement, simultaneous playback limits, and native app integration still need engineering and testing.

## Implementation state

The current staging web UI demonstrates compatible browser streaming with authorized sources and displays these new pricing rules for review. It **does not yet activate a trial**, **does not enforce Free restrictions or TV-slot limits**, and **does not charge users**. Public launch and payments remain disabled until business/legal review, entitlements, and feature-specific security tests are completed.
