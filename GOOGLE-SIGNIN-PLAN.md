# Google Sign-In implementation plan — NOT ACTIVE in v0.8

Approved for TunelyTV, but **a working Google login is not included**. The sign-in and Settings screens explicitly label it pending. Credentials are not yet configured.

Before enabling:

1. Create a Google Cloud project and configure the application's OAuth consent/branding, verified authorized domains and required OAuth Web client credentials.
2. Implement **OpenID Connect authorization-code flow** using a trusted, maintained library; enforce anti-CSRF `state` (and appropriate `nonce`/PKCE), server-side code exchange, signature/audience/issuer/expiry verification, and only accept **verified email** claims.
3. Use Google's immutable subject (`sub`) to bind an identity; do **not** auto-link a Google login to an existing TunelyTV password account based on matching email alone. Require signed-in reauthentication/account-linking approval to prevent takeover.
4. Add `google_identities` table keyed by `(issuer, sub)`, linked to an existing or newly invited TunelyTV account. Preserve current playlists, device assignments, favorites and paid entitlements by keeping the same internal user ID.
5. Keep private invitation signups enforced for new Google users during staging. Add secure unlink/recovery flows.
6. Test login, revoked identity, multiple Google accounts, signout, session expiry, account linking, anti-forgery protections, and mobile browser behavior.
7. Update Privacy Policy before launch to disclose Google account profile information used.

**Do not place a fake working Google button on the site.** Credentials will be added in the server environment only when this functionality is built and tested.

Google reference: https://developers.google.com/identity/openid-connect/openid-connect
