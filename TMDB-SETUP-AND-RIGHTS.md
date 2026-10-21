# TunelyTV TMDB discovery — setup & rights checklist

**Status:** Implementation ready for approved integration. Disabled by default. No API token or commercial usage rights included.

## Purpose

- Populates the Home page's compact 16:9 Trending Movies / TV Series / reported service-availability rows.
- Enables movie and TV title search, descriptions, and country-specific Where-to-Watch links to TMDB.
- Does **not** host or transmit movie/TV streams, unlock third-party subscriptions, guarantee browser playback, or show provider-owned Top 10 charts.
- Account M3U/Xtream sources and Live TV playback remain separate from discovery.

## Important: TMDB commercial rights

TunelyTV intends to charge for software. TMDB's developer key is for noncommercial use; commercial integrations need a **written commercial agreement** from TMDB. Review the license covering API data **and artwork**. Contact TMDB through their official API sales / licensing channel: https://developer.themoviedb.org/docs/faq

Provider availability uses TMDB's JustWatch-sourced data; JustWatch attribution is required. Before public activation, add **an official, unmodified, approved TMDB logo** in the About/Credits area; this package includes credits text but not an unlicensed or improvised logo. Confirm TMDB/JustWatch license terms and branding expectations with the licensors.

## Railway variables — only AFTER licensing and attribution ready

```
TUNELY_METADATA_ENABLED=true
TUNELY_TMDB_RIGHTS_CONFIRMED=true
TUNELY_TMDB_READ_TOKEN=<your actual private bearer token>
```

Or provide `TUNELY_TMDB_API_KEY=<private key>` in place of the read token. Set variables in Railway > TunelyTV service > Variables, **not GitHub or an uploaded `.env`**. Keep existing `TUNELY_DB`, `TUNELY_FERNET_KEY`, and mounted Railway volume unchanged.

`TUNELY_TMDB_RIGHTS_CONFIRMED=true` is an operator acknowledgement, not a license grant. Do not set it before rights are secured. The integration stays disabled unless *all three* (metadata toggle, rights acknowledgement, token/key) are present.

## Test after Railway restores deployments

1. Deploy the newest GitHub commit to the existing Railway service, retaining the database and secrets.
2. Open `/api/discover/status`; it should return `enabled:false` until the license/configuration is complete.
3. Once enabled lawfully, verify `/api/discover/home` has real titles and proper image cards, `/api/discover/search?q=The%20Accountant` returns correct match/year, title detail has JustWatch-attributed watch providers and TMDB URL, and `/api/discover/provider?name=Netflix&region=US` reports available titles rather than 'Netflix Top 10'.
4. Verify missing providers/errors show honest empty states, never made-up streams. Check TMDB credits and approved logo.

**Sources**
- API developer FAQ and licensing: https://developer.themoviedb.org/docs/faq
- TMDB terms: https://www.themoviedb.org/api-terms-of-use
- Authentication: https://developer.themoviedb.org/docs/authentication-application
- JustWatch attribution: https://developer.themoviedb.org/reference/tv-series-watch-providers
