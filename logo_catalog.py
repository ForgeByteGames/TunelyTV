"""Optional external channel-logo matching for authorized TunelyTV playlists.

This module does not distribute channels, download/host logo images, or claim
broadcaster permissions. The open iptv-org *directory* contains links to
third-party artwork; its dataset license does not grant artwork rights.
Operator must separately confirm permission before enabling in production.
"""
from __future__ import annotations

import json
import ipaddress
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

CHANNELS_URL = 'https://iptv-org.github.io/api/channels.json'
LOGOS_URL = 'https://iptv-org.github.io/api/logos.json'
MAX_CATALOG_BYTES = 9_000_000
TTL_SECONDS = 24 * 3600
_lock = threading.Lock()
_catalog: tuple[float, dict, dict] | None = None


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Unexpected catalog redirect')


def _fetch_json(url: str) -> list:
    """Fetch only known public catalog URLs; never proxy user-supplied URLs."""
    if url not in (CHANNELS_URL, LOGOS_URL):
        raise ValueError('Unsupported catalog source')
    opener = build_opener(_NoRedirects())
    req = Request(url, headers={'User-Agent': 'TunelyTV-LogoLookup/0.9.8',
                                'Accept': 'application/json'})
    with opener.open(req, timeout=10) as response:
        if response.headers.get('Content-Length') and int(response.headers['Content-Length']) > MAX_CATALOG_BYTES:
            raise ValueError('Catalog exceeds size limit')
        raw = response.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError('Catalog exceeds size limit')
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError('Invalid directory response')
    return parsed


def normalize(raw: str) -> str:
    # No fuzzy guesses, region/suffix stripping, or search-engine scraping.
    return re.sub(r'[^a-z0-9]+', '', str(raw or '').casefold())[:180]


def safe_image_url(value) -> str:
    if not isinstance(value, str) or not value.startswith('https://') or len(value) > 2048:
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            return ''
    except (ValueError, TypeError):
        return ''
    host=parsed.hostname.lower().rstrip('.')
    if host in ('localhost',) or host.endswith(('.localhost', '.local', '.internal')):
        return ''
    try:
        if not ipaddress.ip_address(host).is_global:
            return ''
    except ValueError:
        pass
    return value


def _build_indexes(channels: list, logos: list) -> tuple[dict, dict]:
    """Build deterministic exact identifier and unique exact-name indexes."""
    by_id = {}
    ambiguous_names = set()
    name_to_ids = {}
    for row in channels:
        if not isinstance(row, dict):
            continue
        channel_id = str(row.get('id') or '').strip()
        if not channel_id:
            continue
        for name in [row.get('name'), *(row.get('alt_names') or [])]:
            if not isinstance(name, str):
                continue
            n = normalize(name)
            if not n:
                continue
            prev = name_to_ids.get(n)
            if prev and prev != channel_id:
                ambiguous_names.add(n)
            else:
                name_to_ids[n] = channel_id
    for name in ambiguous_names:
        name_to_ids.pop(name, None)
    candidates = {}
    for row in logos:
        if not isinstance(row, dict) or not row.get('in_use'):
            continue
        channel_id = str(row.get('channel') or '').strip()
        url = safe_image_url(row.get('url'))
        if not channel_id or not url:
            continue
        # Prefer a channel-wide logo, then feed-specific versions; no arbitrary
        # overwrite of a selected entry.
        priority = (0 if not row.get('feed') else 1,
                    0 if str(row.get('format') or '').upper() in ('PNG', 'WEBP') else 1,
                    url)
        candidates.setdefault(channel_id, []).append((priority, url))
    for channel_id, versions in candidates.items():
        by_id[channel_id.casefold()] = min(versions)[1]
    by_name = {}
    for name, channel_id in name_to_ids.items():
        if channel_id.casefold() in by_id:
            by_name[name] = by_id[channel_id.casefold()]
    return by_id, by_name


def _indexes() -> tuple[dict, dict]:
    global _catalog
    with _lock:
        if _catalog is not None and time.monotonic() - _catalog[0] < TTL_SECONDS:
            return _catalog[1], _catalog[2]
        # If fetching fails, do not invent matches. Previous cache expires.
        channels = _fetch_json(CHANNELS_URL)
        logos = _fetch_json(LOGOS_URL)
        by_id, by_name = _build_indexes(channels, logos)
        _catalog = (time.monotonic(), by_id, by_name)
        return by_id, by_name


class ChannelName(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    tvgId: str = Field(default='', max_length=140)


class MatchRequest(BaseModel):
    channels: list[ChannelName] = Field(min_length=1, max_length=2000)


def install_logo_catalog(app, *, current_user, csrf_user, throttle, db, account_access):
    # Explicit opt-in, BOTH switches required; not enabled by possession of an
    # API key, and NEVER imply a directory license includes trademark rights.
    import os
    enabled = (os.getenv('TUNELY_LOGO_AUTOMATCH_ENABLED', '').lower() == 'true'
               and os.getenv('TUNELY_EXTERNAL_LOGOS_RIGHTS_CONFIRMED', '').lower() == 'true')

    @app.get('/api/channel-logos/config')
    def logo_config(user=Depends(current_user)):
        return {'enabled': enabled,
                'source': 'iptv-org community channel directory' if enabled else None,
                'note': ('External logo matching available; only use with confirmed artwork rights.' if enabled
                         else 'External logo directory disabled pending artwork rights. Playlist and XMLTV images still work.')}

    @app.post('/api/channel-logos/match')
    def logo_match(payload: MatchRequest, request: Request, user=Depends(csrf_user)):
        if not enabled:
            raise HTTPException(403, 'External logo lookup is disabled pending source/artwork permission.')
        throttle(request, 'channel-logo-directory', 8, 60)
        with db() as con:
            if not account_access(con, user['user_id'])['web_playback']:
                raise HTTPException(403, 'Web playback is unavailable for this account.')
        try:
            by_id, by_name = _indexes()
        except Exception:
            raise HTTPException(503, 'Channel logo directory is temporarily unavailable.') from None
        matched = []
        for i, item in enumerate(payload.channels):
            ident = item.tvgId.strip().casefold()
            url = by_id.get(ident) if ident else None
            method = 'tvg-id' if url else ''
            if not url:
                url = by_name.get(normalize(item.name))
                method = 'exact-name' if url else ''
            if url:
                matched.append({'index': i, 'url': url, 'matched_by': method})
        return {'matches': matched, 'queried': len(payload.channels),
                'unmatched': len(payload.channels) - len(matched),
                'source': 'iptv-org public directory (third-party artwork)'}
