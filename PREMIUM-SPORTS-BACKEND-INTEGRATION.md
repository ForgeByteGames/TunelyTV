# Android-compatible Premium TheSportsDB V2 backend (FastAPI staging)

## Scope
This is an additive integration into the original FastAPI **staging** repository.
It does not migrate or replace the **separate** production service currently
used by the Android app, and it does not sync Android profile records.

The routes are designed to match the contract already implemented by Android
versions 1.0.14–1.0.16. The existing staging app's authorization can use
either an authenticated browser session or the original paired-device Bearer
token, and checks that a device is paired, authorized, and within allowed slots.

**Do not treat the X-Nexa-Profile header as an identity assertion.** The
active Android backend has a distinct account/profile-token implementation:
these routes must be inserted into that service **using its own authentication
middleware** before the existing Android client can use them in production.

## Configuration
Set the Premium V2 key **only on the backend host** under the environment
variable `THESPORTSDB_PREMIUM_API_KEY`. Never add the value to this repo,
an APK, a config file committed to GitHub, a client header, or an upstream URL.
Without a key both routes intentionally return 503 after authentication.

## Endpoints
- `GET /api/sports/teams?league=NFL`
- `GET /api/sports/teams?league=NHL`
- `GET /api/sports/scores?leagues=NFL,NHL`
- `GET /api/sports/scores` (defaults NFL, NHL, NBA, MLB)

Supported fixed league names: NFL, NHL, NBA, MLB and EPL. These are server-side
provider IDs; arbitrary user-supplied URLs, hostnames or league IDs are rejected.
NFL/NHL standings remain separate and are not fabricated by this adapter.

Both routes require a real account or paired-device authentication. The
responses contain only public sports metadata, never the API key. Team JSON
matches `{league, leagueId, source, teams:[{id,name,badge,league}]}`.
Scores JSON matches the Android scoreboard's `games`, `finals` and
`upcoming` with flags `enabled`, `premium`, `partial`,
`unavailableLeagues`, `updatedAt`, and `loadingSchedule`.

Provider calls are HTTPS-only to fixed Premium V2 endpoints, reject redirects,
and use bounded responses and timeouts. Live scores are cached for 75 seconds,
fixtures for 10 minutes and rosters for 6 hours. Provider failures report 502
or partial data; no placeholder team rows or guessed scores are created.

## Verification before deployment
1. Confirm the live source, deployment branch and its existing Bearer/profile
   validation. Do not replace the live auth service with the staging one.
2. Deploy the adapter there, configured with the backend-only Premium key.
3. Sign in using a real **test account** and request the NFL/NHL team rosters;
   ensure both return actual provider teams and correct logos.
4. Request scores for NFL,NHL; confirm empty arrays are correctly shown when
   no games are active and that past/upcoming fixture data is real.
5. Check invalid/revoked tokens, unpaired devices, profile isolation, no key
   disclosure, and failures (401/403/400/502/503).
6. Install the Android 1.0.16 APK and verify switching profiles and leagues.
7. Confirm third-party sports data/artwork commercial permissions before launch.

All code changes are covered by
`PYTHONPATH=. python -m pytest -q tests/test_premium_sports.py
tests/test_api.py tests/test_qr_pairing_v0910.py`.
