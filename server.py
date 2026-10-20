"""TunelyTV local-development pairing & playlist-sync API.

A small, runnable FastAPI + SQLite staged web application. No media is supplied,
no provider activation is performed, and this is private staging, not a public-ready launch.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from billing import install_billing
from discovery import install_discovery
from licensing import account_access, install_licensing
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

BASE = Path(__file__).resolve().parent
INSTANCE = BASE / 'instance'
PH = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=2)
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
SESSION_AGE = 7 * 86400
PAIR_AGE = 10 * 60
MAX_FILE_CHARS = 750_000


def now() -> int:
    return int(time.time())


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def uid() -> str:
    return str(uuid4())


def valid_url(raw: str) -> str:
    if not raw or len(raw) > 4096 or any(x in raw for x in ('\n', '\r', '\t')):
        raise ValueError('Enter a valid HTTP(S) URL (max 4096 characters).')
    try:
        parsed = urlsplit(raw)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                not parsed.netloc):
            raise ValueError
        _ = parsed.port  # reject invalid ports
    except (ValueError, TypeError):
        raise ValueError('Enter an http:// or https:// URL without username:password@.') from None
    return raw



def extract_m3u_epg_candidates(content: str) -> list[str]:
    """Read provider-advertised XMLTV URLs from #EXTM3U; never fetch them server-side.

    No guessed guide endpoints or remote third-party catalogue are used. Only the
    browser will request these links when the signed-in user opens the playlist.
    """
    header = next((line.strip().lstrip('\ufeff') for line in content.splitlines()[:12]
                   if line.strip().lstrip('\ufeff').upper().startswith('#EXTM3U')), '')[:16000]
    if not header:
        return []
    candidates: list[str] = []
    pattern = r"(?i)(?:^|\s)(x-tvg-url|url-tvg|tvg-url)\s*=\s*([\"'])(.*?)\2"
    for match in re.finditer(pattern, header):
        for value in re.split(r'[,;]', match.group(3)):
            value = value.strip()
            try:
                link = valid_url(value)
            except ValueError:
                continue
            if link not in candidates:
                candidates.append(link)
            if len(candidates) >= 3:
                return candidates
    return candidates

def normalized_identifier(method: str, value: str) -> tuple[str, str]:
    v = value.strip()
    if method == 'mac':
        compact = re.sub('[:-]', '', v).upper()
        if not re.fullmatch(r'[A-F0-9]{12}', compact):
            raise ValueError('Use a valid MAC address such as AA:BB:CC:DD:EE:FF.')
        v = ':'.join(compact[i:i + 2] for i in range(0, 12, 2))
        masked = v[:5] + ':••:••:••:••'
    elif method == 'ip':
        try:
            addr = ipaddress.IPv4Address(v)
            if not addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError
        except ValueError:
            raise ValueError('Use a private local IPv4 address (for example, 192.168.1.50).') from None
        masked = '.'.join(v.split('.')[:2]) + '.••.••'
    else:
        if not re.fullmatch(r'[A-Za-z0-9_.:\-]{3,100}', v):
            raise ValueError('Device ID must contain 3–100 valid characters.')
        masked = '••••' + v[-4:]
    return v, masked


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    invite_code: str | None = Field(default=None, max_length=160)

    @field_validator('email')
    @classmethod
    def email_format(cls, val):
        val = val.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', val):
            raise ValueError('Please enter a valid email address.')
        return val


class PlaylistNew(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: Literal['m3u_url', 'm3u_file', 'xtream']
    url: str | None = Field(default=None, max_length=4096)
    content: str | None = Field(default=None, max_length=MAX_FILE_CHARS)
    filename: str | None = Field(default=None, max_length=140)
    server: str | None = Field(default=None, max_length=4096)
    username: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=512)

    @field_validator('name')
    @classmethod
    def name_format(cls, val):
        if not val.strip():
            raise ValueError('Playlist name required.')
        return val.strip()


class DeviceNew(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    platform: str = Field(min_length=1, max_length=60)
    method: Literal['mac', 'ip', 'device_id']
    identifier: str = Field(min_length=3, max_length=100)
    playlist_id: str | None = None


class Assign(BaseModel):
    playlist_id: str | None = None


class Enroll(BaseModel):
    name: str = Field(default='TunelyTV Device', min_length=1, max_length=60)
    platform: str = Field(default='TV App Simulator', min_length=1, max_length=60)


class ChannelKeyChange(BaseModel):
    channel_key: str = Field(min_length=3, max_length=195)
    favorite: bool = True

    @field_validator('channel_key')
    @classmethod
    def validate_key(cls, value):
        # Opaque per-channel identifier, not a stream URL or credentials.
        if (not value.startswith(('id:', 'n:')) or
                any(ord(char) < 32 or ord(char) == 127 for char in value) or
                '://' in value or '?' in value or '#' in value):
            raise ValueError('Invalid channel key.')
        return value


class GuideConfig(BaseModel):
    url: str | None = Field(default=None, max_length=4096)


class Claim(BaseModel):
    code: str = Field(min_length=8, max_length=11)
    profile_id: str | None = None
    playlist_id: str | None = None


class PlayerPreferenceUpdate(BaseModel):
    playlist_id: str | None = None


def create_app(db_path: str | Path | None = None, key_path: str | Path | None = None) -> FastAPI:
    prod = os.environ.get('TUNELY_ENV', 'development').lower() == 'production'
    configured_key = os.environ.get('TUNELY_FERNET_KEY')
    if prod and not configured_key:
        raise RuntimeError('Production requires TUNELY_FERNET_KEY from a secret manager.')
    signup_code = os.environ.get('TUNELY_SIGNUP_CODE', '')
    if prod and not signup_code:
        raise RuntimeError('Public staging requires TUNELY_SIGNUP_CODE. Disable open registration for safety.')
    file_key_path = Path(key_path) if key_path else INSTANCE / 'fernet.key'
    if configured_key:
        key = configured_key.encode()
    else:
        file_key_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_key_path.exists():
            try:
                with file_key_path.open('xb') as f:
                    os.chmod(file_key_path, 0o600)
                    f.write(Fernet.generate_key())
            except FileExistsError:
                pass
        key = file_key_path.read_bytes().strip()
    cipher = Fernet(key)
    database_path = Path(db_path) if db_path else Path(os.environ.get('TUNELY_DB', str(INSTANCE / 'tunelytv.db')))
    database_path.parent.mkdir(parents=True, exist_ok=True)

    def db():
        con = sqlite3.connect(database_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys = ON')
        con.execute('PRAGMA busy_timeout = 10000')
        return con

    with db() as con:
        con.executescript('''
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
              token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              csrf_hash TEXT NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS playlists (
              id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              name TEXT NOT NULL, type TEXT NOT NULL, config_encrypted BLOB NOT NULL,
              created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS devices (
              id TEXT PRIMARY KEY, owner_id TEXT REFERENCES users(id) ON DELETE CASCADE,
              name TEXT NOT NULL, platform TEXT NOT NULL,
              method TEXT NOT NULL, identifier_mask TEXT,
              identifier_enc BLOB, token_hash TEXT UNIQUE,
              code_hash TEXT UNIQUE, code_expires INTEGER,
              paired_at INTEGER, last_seen INTEGER,
              playlist_id TEXT REFERENCES playlists(id) ON DELETE SET NULL,
              revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_playlists_owner ON playlists(owner_id);
            CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices(owner_id);
            CREATE TABLE IF NOT EXISTS player_preferences (
              owner_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              playlist_id TEXT REFERENCES playlists(id) ON DELETE SET NULL,
              updated_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS favorite_channels (
              owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
              channel_key TEXT NOT NULL, created_at INTEGER NOT NULL,
              PRIMARY KEY (owner_id, playlist_id, channel_key));
            CREATE TABLE IF NOT EXISTS recent_channels (
              owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
              channel_key TEXT NOT NULL, played_at INTEGER NOT NULL,
              PRIMARY KEY (owner_id, playlist_id, channel_key));
            CREATE INDEX IF NOT EXISTS idx_recent_channels ON recent_channels(owner_id, playlist_id, played_at DESC);
        ''')
    app = FastAPI(title='TunelyTV Web Staging API', version='0.9.6', docs_url=None if prod else '/api/docs', redoc_url=None, openapi_url=None if prod else '/openapi.json')
    app.state.db_path = str(database_path)
    app.state.cipher = cipher
    app.state.production = prod
    # In-memory dev rate limiting; replace with shared Redis and IP/user thresholds in production.
    attempts: dict[tuple[str, str], list[float]] = {}

    def throttle(request: Request, name: str, limit: int, window: int):
        peer = request.client.host if request.client else 'unknown'
        key = (peer, name)
        t = time.monotonic()
        seq = [v for v in attempts.get(key, []) if t - v < window]
        if len(seq) >= limit:
            raise HTTPException(429, 'Too many attempts. Please try again later.')
        seq.append(t)
        attempts[key] = seq
        if len(attempts) > 10000:
            attempts.clear()

    def fail(msg: str, status: int = 400):
        raise HTTPException(status, msg)

    def auth_session(sid: str | None):
        if not sid:
            fail('Please sign in.', 401)
        with db() as con:
            row = con.execute('''SELECT sessions.user_id, sessions.csrf_hash, users.email
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash=? AND sessions.expires_at > ?''', (token_hash(sid), now())).fetchone()
        if not row:
            fail('Session expired. Please sign in again.', 401)
        return row

    def current_user(tunely_session: str | None = Cookie(default=None)):
        return auth_session(tunely_session)

    def csrf_user(request: Request, tunely_session: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        user = auth_session(tunely_session)
        if not x_csrf_token or not secrets.compare_digest(token_hash(x_csrf_token), user['csrf_hash']):
            fail('Invalid CSRF token. Refresh and retry.', 403)
        # Browser's SameSite cookie is not a replacement for a CSRF token.
        return user

    def set_session(response: Response, user_id: str):
        sid = secrets.token_urlsafe(40)
        csrf = secrets.token_urlsafe(32)
        with db() as con:
            con.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                        (token_hash(sid), user_id, token_hash(csrf), now() + SESSION_AGE))
        response.set_cookie('tunely_session', sid, max_age=SESSION_AGE, path='/',
                            httponly=True, samesite='lax', secure=prod)
        return csrf

    @app.middleware('http')
    async def protect(request: Request, call_next):
        # No cross-origin credential sharing. Production must be behind HTTPS.
        if request.url.path.startswith('/api/') and request.headers.get('content-length', '0').isdigit():
            if int(request.headers.get('content-length', '0')) > 1_500_000:
                return Response('Request too large', status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' https://cdn.jsdelivr.net; connect-src 'self' https: http:; media-src 'self' https: http: blob:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        if prod:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # Install license tables before any request and any billing migrations.
    # Billing tables are created at module install further down, so run after.
    @app.get('/api/public/config')
    def public_config():
        return {'invite_required': bool(signup_code), 'google_signin_enabled': False, 'google_signin_prepared': True, 'web_preview': True}

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'service': 'TunelyTV web staging', 'version': '0.9.6'}

    @app.get('/api/features/multiview')
    def multiview_access(user=Depends(current_user)):
        with db() as con:
            access = account_access(con, user['user_id'])
        # Only a securely bootstrapped owner gets preview access without a purchase.
        return {'plan': access['plan'], 'max_panes': access['multiview_panes'],
                'preview': access['owner'], 'feature_live': False,
                'note': 'Owner-only private testing' if access['owner'] else
                        'Account entitlement; provider stream limits still apply.'}

    @app.post('/api/auth/register', status_code=201)
    def register(inp: Credentials, response: Response, request: Request):
        throttle(request, 'register', 10, 3600)
        if signup_code and not secrets.compare_digest(inp.invite_code or '', signup_code):
            fail('A valid testing invitation code is required.', 403)
        try:
            with db() as con:
                user_id = uid()
                con.execute('INSERT INTO users VALUES (?,?,?,?)',
                            (user_id, inp.email, PH.hash(inp.password), now()))
        except sqlite3.IntegrityError:
            fail('An account with that email already exists.', 409)
        csrf = set_session(response, user_id)
        return {'email': inp.email, 'csrf_token': csrf}

    @app.post('/api/auth/login')
    def login(inp: Credentials, response: Response, request: Request):
        throttle(request, 'login', 15, 900)
        with db() as con:
            user = con.execute('SELECT * FROM users WHERE email=?', (inp.email,)).fetchone()
        try:
            if not user or not PH.verify(user['password_hash'], inp.password):
                fail('Invalid email or password.', 401)
        except (VerifyMismatchError, VerificationError):
            fail('Invalid email or password.', 401)
        csrf = set_session(response, user['id'])
        return {'email': user['email'], 'csrf_token': csrf}

    @app.get('/api/me')
    def me(user=Depends(current_user)):
        # CSRF is returned only for own session. Rotate on each new login.
        return {'email': user['email']}

    @app.get('/api/auth/csrf')
    def get_csrf(request: Request, tunely_session: str | None = Cookie(default=None)):
        # Tokens aren't recoverable from stored hashes; issue a new one per authenticated session.
        user = auth_session(tunely_session)
        csrf = secrets.token_urlsafe(32)
        with db() as con:
            con.execute('UPDATE sessions SET csrf_hash=? WHERE token_hash=?',
                        (token_hash(csrf), token_hash(tunely_session)))
        return {'csrf_token': csrf, 'email': user['email']}

    @app.post('/api/auth/logout')
    def logout(response: Response, user=Depends(csrf_user), tunely_session: str | None = Cookie(default=None)):
        with db() as con:
            con.execute('DELETE FROM sessions WHERE token_hash=? AND user_id=?',
                        (token_hash(tunely_session), user['user_id']))
        response.delete_cookie('tunely_session', path='/')
        return {'ok': True}

    def own_playlist(con, user_id: str, playlist_id: str):
        return con.execute('SELECT * FROM playlists WHERE id=? AND owner_id=?',
                           (playlist_id, user_id)).fetchone()

    def own_device(con, user_id: str, device_id: str):
        return con.execute('SELECT * FROM devices WHERE id=? AND owner_id=?',
                           (device_id, user_id)).fetchone()

    @app.get('/api/player/preferences')
    def player_preferences(user=Depends(current_user)):
        """Last account-selected playlist, never the plaintext playlist contents."""
        with db() as con:
            row = con.execute('''SELECT playlist_id FROM player_preferences
                WHERE owner_id=?''', (user['user_id'],)).fetchone()
        return {'playlist_id': row['playlist_id'] if row else None}

    @app.patch('/api/player/preferences')
    def update_player_preferences(inp: PlayerPreferenceUpdate, user=Depends(csrf_user)):
        with db() as con:
            if inp.playlist_id and not own_playlist(con, user['user_id'], inp.playlist_id):
                fail('Playlist not found.', 404)
            con.execute('''INSERT INTO player_preferences (owner_id, playlist_id, updated_at)
                VALUES (?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET
                playlist_id=excluded.playlist_id, updated_at=excluded.updated_at''',
                (user['user_id'], inp.playlist_id, now()))
        return {'playlist_id': inp.playlist_id}

    @app.get('/api/playlists')
    def playlists(user=Depends(current_user)):
        with db() as con:
            rows = con.execute('''SELECT id, name, type, created_at FROM playlists
                WHERE owner_id=? ORDER BY created_at DESC''', (user['user_id'],)).fetchall()
        return {'playlists': [dict(x) for x in rows]}

    @app.post('/api/playlists', status_code=201)
    def add_playlist(inp: PlaylistNew, user=Depends(csrf_user)):
        if inp.type == 'm3u_url':
            try:
                config = {'type': inp.type, 'url': valid_url(inp.url or '')}
            except ValueError as e:
                fail(str(e))
        elif inp.type == 'xtream':
            try:
                server = valid_url(inp.server or '')
            except ValueError as e:
                fail(str(e))
            if not inp.username or not inp.password:
                fail('Provider username and password are required.')
            config = {'type': inp.type, 'server': server, 'username': inp.username, 'password': inp.password}
        else:
            if not inp.filename or not inp.filename.lower().endswith(('.m3u', '.m3u8')):
                fail('Choose an .m3u or .m3u8 file.')
            content = inp.content or ''
            if not content.lstrip('\ufeff \r\n').startswith('#EXTM3U'):
                fail('The file must start with #EXTM3U.')
            if len(content.encode('utf-8')) > 1_000_000:
                fail('M3U file must be smaller than 1 MB.')
            config = {'type': inp.type, 'filename': inp.filename, 'content': content}
        with db() as con:
            count = con.execute('SELECT count(*) FROM playlists WHERE owner_id=?', (user['user_id'],)).fetchone()[0]
            if count >= 50:
                fail('Development limit reached: 50 playlists.')
            p_id = uid()
            con.execute('INSERT INTO playlists VALUES (?,?,?,?,?,?)',
                        (p_id, user['user_id'], inp.name, inp.type,
                         cipher.encrypt(json.dumps(config).encode()), now()))
        return {'id': p_id, 'name': inp.name, 'type': inp.type}

    @app.get('/api/playlists/{playlist_id}/playable')
    def playlist_for_browser(playlist_id: str, user=Depends(current_user)):
        """Owner-only playback configuration; no server-side URL fetching or proxying.

        Uploaded M3Us are locally parsed and returned to the owner's browser.
        A saved URL is either a direct HLS URL or a CORS-enabled remote M3U.
        Xtream profiles stay server-encrypted and are intentionally unsupported
        by the browser testing player in this milestone.
        """
        with db() as con:
            row = own_playlist(con, user['user_id'], playlist_id)
            if not row:
                fail('Playlist not found.', 404)
            if not account_access(con, user['user_id'])['web_playback']:
                fail('Your plan does not include web playback. Start your 7-day Plus trial or choose a paid plan.', 403)
        config = json.loads(cipher.decrypt(row['config_encrypted']).decode())
        if row['type'] == 'xtream':
            return {'id': row['id'], 'name': row['name'], 'type': 'xtream',
                    'supported': False, 'message': 'Xtream browser playback requires a separate, provider-compatible player integration. Credentials are not exposed.'}
        if row['type'] == 'm3u_url':
            return {'id': row['id'], 'name': row['name'], 'type': row['type'],
                    'supported': True, 'url': config['url'], 'epg_url': config.get('epg_url'),
                    'epg_candidates': []}
        # Strictly parsed only; do not fetch or proxy arbitrary user-controlled URLs.
        entries = []
        current_name = None
        current_group = 'Other'
        current_tvg_id = ''
        current_tvg_name = ''
        for line in config['content'].splitlines():
            line = line.strip()
            if line.startswith('#EXTINF:'):
                # Split at the first comma outside quoted attributes; a group-title
                # can contain a comma. Do not return untrusted logos or arbitrary HTML.
                in_quote = False
                comma = -1
                for index, char in enumerate(line):
                    if char == '"':
                        in_quote = not in_quote
                    elif char == ',' and not in_quote:
                        comma = index
                        break
                attrs = dict(re.findall(r'([A-Za-z][A-Za-z0-9-]*)\s*=\s*"([^"]*)"',
                                        line[:comma] if comma >= 0 else line))
                current_name = line[comma + 1:].strip()[:140] if comma >= 0 else attrs.get('tvg-name', '')[:140]
                current_group = attrs.get('group-title', 'Other')[:140] or 'Other'
                current_tvg_id = attrs.get('tvg-id', '')[:140]
                current_tvg_name = attrs.get('tvg-name', '')[:140]
            elif line and not line.startswith('#'):
                try:
                    source_url = valid_url(line)
                except ValueError:
                    current_name = None
                    current_group = 'Other'
                    current_tvg_id = ''
                    current_tvg_name = ''
                    continue
                if len(entries) >= 5000:
                    break
                entries.append({'name': current_name or 'Channel ' + str(len(entries) + 1),
                                'url': source_url,
                                'group': current_group,
                                'tvgId': current_tvg_id, 'tvgName': current_tvg_name})
                current_name = None
                current_group = 'Other'
                current_tvg_id = ''
                current_tvg_name = ''
        return {'id': row['id'], 'name': row['name'], 'type': 'm3u_file',
                'supported': True, 'channels': entries, 'total': len(entries), 'epg_url': config.get('epg_url'),
                'epg_candidates': extract_m3u_epg_candidates(config['content'])}

    @app.patch('/api/playlists/{playlist_id}/guide')
    def set_playlist_guide(playlist_id: str, inp: GuideConfig, user=Depends(csrf_user)):
        # Store encrypted guide URL; server never connects to submitted provider.
        try:
            url = valid_url(inp.url.strip()) if inp.url and inp.url.strip() else None
        except ValueError as error:
            fail(str(error))
        # Production web app needs HTTPS for CORS-compatible guide fetching.
        if prod and url and not url.startswith('https://'):
            fail('An HTTPS XMLTV guide URL is required on the hosted website.')
        with db() as con:
            row = own_playlist(con, user['user_id'], playlist_id)
            if not row:
                fail('Playlist not found.', 404)
            config = json.loads(cipher.decrypt(row['config_encrypted']).decode())
            if url:
                config['epg_url'] = url
            else:
                config.pop('epg_url', None)
            con.execute('UPDATE playlists SET config_encrypted=? WHERE id=? AND owner_id=?',
                        (cipher.encrypt(json.dumps(config).encode()), playlist_id, user['user_id']))
        return {'ok': True, 'configured': bool(url)}

    @app.get('/api/playlists/{playlist_id}/preferences')
    def get_channel_preferences(playlist_id: str, user=Depends(current_user)):
        with db() as con:
            if not own_playlist(con, user['user_id'], playlist_id):
                fail('Playlist not found.', 404)
            favorites = con.execute('''SELECT channel_key FROM favorite_channels
                  WHERE owner_id=? AND playlist_id=? ORDER BY created_at DESC''',
                  (user['user_id'], playlist_id)).fetchall()
            recent = con.execute('''SELECT channel_key FROM recent_channels
                  WHERE owner_id=? AND playlist_id=? ORDER BY played_at DESC, rowid DESC LIMIT 30''',
                  (user['user_id'], playlist_id)).fetchall()
        return {'favorites': [row['channel_key'] for row in favorites],
                'recent': [row['channel_key'] for row in recent]}

    @app.post('/api/playlists/{playlist_id}/favorites')
    def update_channel_favorite(playlist_id: str, inp: ChannelKeyChange, user=Depends(csrf_user)):
        with db() as con:
            if not own_playlist(con, user['user_id'], playlist_id):
                fail('Playlist not found.', 404)
            if inp.favorite:
                count = con.execute('SELECT COUNT(*) FROM favorite_channels WHERE owner_id=? AND playlist_id=?',
                                    (user['user_id'], playlist_id)).fetchone()[0]
                existing = con.execute('SELECT 1 FROM favorite_channels WHERE owner_id=? AND playlist_id=? AND channel_key=?',
                                       (user['user_id'], playlist_id, inp.channel_key)).fetchone()
                if count >= 250 and not existing:
                    fail('Limit reached: 250 favorites per playlist.')
                con.execute('''INSERT OR IGNORE INTO favorite_channels(owner_id,playlist_id,channel_key,created_at)
                               VALUES (?,?,?,?)''', (user['user_id'], playlist_id, inp.channel_key, now()))
            else:
                con.execute('DELETE FROM favorite_channels WHERE owner_id=? AND playlist_id=? AND channel_key=?',
                            (user['user_id'], playlist_id, inp.channel_key))
        return {'ok': True}

    @app.post('/api/playlists/{playlist_id}/recent')
    def update_recent_channel(playlist_id: str, inp: ChannelKeyChange, user=Depends(csrf_user)):
        with db() as con:
            if not own_playlist(con, user['user_id'], playlist_id):
                fail('Playlist not found.', 404)
            # Millisecond precision makes natural ordering stable for rapid switches.
            played_at = int(time.time() * 1000)
            con.execute('''INSERT INTO recent_channels(owner_id,playlist_id,channel_key,played_at)
                           VALUES (?,?,?,?) ON CONFLICT(owner_id,playlist_id,channel_key)
                           DO UPDATE SET played_at=excluded.played_at''',
                        (user['user_id'], playlist_id, inp.channel_key, played_at))
            con.execute('''DELETE FROM recent_channels WHERE owner_id=? AND playlist_id=? AND channel_key NOT IN (
                         SELECT channel_key FROM recent_channels WHERE owner_id=? AND playlist_id=?
                         ORDER BY played_at DESC, rowid DESC LIMIT 30)''',
                        (user['user_id'], playlist_id, user['user_id'], playlist_id))
        return {'ok': True}

    @app.delete('/api/playlists/{playlist_id}/preferences')
    def clear_channel_preferences(playlist_id: str, user=Depends(csrf_user)):
        with db() as con:
            if not own_playlist(con, user['user_id'], playlist_id):
                fail('Playlist not found.', 404)
            con.execute('DELETE FROM favorite_channels WHERE owner_id=? AND playlist_id=?',
                        (user['user_id'], playlist_id))
            con.execute('DELETE FROM recent_channels WHERE owner_id=? AND playlist_id=?',
                        (user['user_id'], playlist_id))
        return {'ok': True}

    @app.delete('/api/playlists/{playlist_id}')
    def delete_playlist(playlist_id: str, user=Depends(csrf_user)):
        with db() as con:
            if not own_playlist(con, user['user_id'], playlist_id):
                fail('Playlist not found.', 404)
            con.execute('UPDATE devices SET playlist_id=NULL, revision=revision+1 WHERE owner_id=? AND playlist_id=?',
                        (user['user_id'], playlist_id))
            con.execute('DELETE FROM playlists WHERE id=? AND owner_id=?',
                        (playlist_id, user['user_id']))
        return {'ok': True}

    def public_device(row):
        return {'id': row['id'], 'name': row['name'], 'platform': row['platform'],
                'method': row['method'], 'identifier_mask': row['identifier_mask'] or '—',
                'paired': bool(row['paired_at'] and row['token_hash']),
                'playlist_id': row['playlist_id'], 'revision': row['revision'],
                'last_seen': row['last_seen'], 'created_at': row['created_at']}

    @app.get('/api/devices')
    def devices(user=Depends(current_user)):
        with db() as con:
            rows = con.execute('SELECT * FROM devices WHERE owner_id=? ORDER BY created_at DESC',
                               (user['user_id'],)).fetchall()
        return {'devices': [public_device(d) for d in rows]}

    @app.post('/api/devices', status_code=201)
    def add_manual_device(inp: DeviceNew, user=Depends(csrf_user)):
        try:
            identifier, masked = normalized_identifier(inp.method, inp.identifier)
        except ValueError as e:
            fail(str(e))
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            registered = con.execute('SELECT count(*) FROM devices WHERE owner_id=?', (user['user_id'],)).fetchone()[0]
            limit = account_access(con, user['user_id'])['tv_slots']
            if registered >= limit:
                fail(f'TV limit reached ({limit} registered). Remove a TV or change plan.', 403)
            if inp.playlist_id and not own_playlist(con, user['user_id'], inp.playlist_id):
                fail('Playlist not found.', 404)
            d_id = uid()
            con.execute('''INSERT INTO devices (id,owner_id,name,platform,method,identifier_mask,identifier_enc,playlist_id,revision,created_at)
                  VALUES (?,?,?,?,?,?,?,?,1,?)''',
                        (d_id, user['user_id'], inp.name.strip(), inp.platform.strip(), inp.method,
                         masked, cipher.encrypt(identifier.encode()), inp.playlist_id, now()))
            row = own_device(con, user['user_id'], d_id)
        return public_device(row)

    @app.patch('/api/devices/{device_id}/playlist')
    def assign_playlist(device_id: str, inp: Assign, user=Depends(csrf_user)):
        with db() as con:
            if not own_device(con, user['user_id'], device_id):
                fail('Device not found.', 404)
            if inp.playlist_id and not own_playlist(con, user['user_id'], inp.playlist_id):
                fail('Playlist not found.', 404)
            con.execute('UPDATE devices SET playlist_id=?, revision=revision+1 WHERE id=? AND owner_id=?',
                        (inp.playlist_id, device_id, user['user_id']))
            row = own_device(con, user['user_id'], device_id)
        return public_device(row)

    @app.delete('/api/devices/{device_id}')
    def delete_device(device_id: str, user=Depends(csrf_user)):
        with db() as con:
            cur = con.execute('DELETE FROM devices WHERE id=? AND owner_id=?',
                              (device_id, user['user_id']))
            if not cur.rowcount:
                fail('Device not found.', 404)
        # Deletes device token. Previously paired app can no longer fetch its source.
        return {'ok': True}

    def app_device(auth: str | None):
        if not auth or not auth.startswith('Bearer '):
            fail('Device token required.', 401)
        value = auth.removeprefix('Bearer ')
        if len(value) < 40 or len(value) > 150:
            fail('Invalid device token.', 401)
        with db() as con:
            row = con.execute('SELECT * FROM devices WHERE token_hash=?', (token_hash(value),)).fetchone()
        if not row:
            fail('Device authorization revoked or invalid.', 401)
        return row

    @app.post('/api/device/enroll', status_code=201)
    def enroll(inp: Enroll, request: Request):
        throttle(request, 'enroll', 15, 3600)
        raw_token = secrets.token_urlsafe(48)
        expires = now() + PAIR_AGE
        with db() as con:
            for _ in range(10):
                code = ''.join(secrets.choice(ALPHABET) for _ in range(8))
                try:
                    con.execute('''INSERT INTO devices (id,owner_id,name,platform,method,token_hash,code_hash,code_expires,revision,created_at)
                      VALUES (?,?,?,?,?,?,?,?,1,?)''',
                                (uid(), None, inp.name.strip(), inp.platform.strip(), 'code',
                                 token_hash(raw_token), token_hash(code), expires, now()))
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                fail('Could not generate pairing code. Please retry.', 503)
        return {'pairing_code': code[:4] + '-' + code[4:], 'expires_in_seconds': PAIR_AGE,
                'device_token': raw_token, 'status': 'pending'}

    @app.post('/api/pairings/claim')
    def claim(inp: Claim, request: Request, user=Depends(csrf_user)):
        throttle(request, 'claim', 15, 900)
        code = re.sub(r'[\s\-]', '', inp.code).upper()
        if len(code) != 8 or any(char not in ALPHABET for char in code):
            fail('Invalid or expired pairing code.', 400)
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            pending = con.execute('SELECT * FROM devices WHERE code_hash=? AND owner_id IS NULL',
                                  (token_hash(code),)).fetchone()
            if not pending or not pending['code_expires'] or pending['code_expires'] <= now():
                fail('Invalid or expired pairing code.', 400)
            if not inp.profile_id:
                used = con.execute('SELECT count(*) FROM devices WHERE owner_id=?', (user['user_id'],)).fetchone()[0]
                limit = account_access(con, user['user_id'])['tv_slots']
                if used >= limit:
                    fail(f'TV limit reached ({limit} registered). Remove a TV or change plan.', 403)
            if inp.playlist_id and not own_playlist(con, user['user_id'], inp.playlist_id):
                fail('Playlist not found.', 404)
            if inp.profile_id:
                manual = own_device(con, user['user_id'], inp.profile_id)
                if not manual:
                    fail('Manual device profile not found.', 404)
                if manual['token_hash']:
                    fail('That device is already paired. Remove it before pairing again.', 409)
                # Release the unique pending token before transferring it atomically.
                # Both statements live inside the same BEGIN IMMEDIATE transaction.
                con.execute('DELETE FROM devices WHERE id=? AND owner_id IS NULL', (pending['id'],))
                con.execute('''UPDATE devices SET token_hash=?, paired_at=?, revision=revision+1,
                    playlist_id=COALESCE(?,playlist_id) WHERE id=? AND owner_id=?''',
                            (pending['token_hash'], now(), inp.playlist_id, manual['id'], user['user_id']))
                linked_id = manual['id']
            else:
                con.execute('''UPDATE devices SET owner_id=?, paired_at=?, code_hash=NULL,
                    code_expires=NULL, playlist_id=?, revision=revision+1
                    WHERE id=? AND owner_id IS NULL''',
                            (user['user_id'], now(), inp.playlist_id, pending['id']))
                linked_id = pending['id']
            row = own_device(con, user['user_id'], linked_id)
        return {'ok': True, 'device': public_device(row)}

    @app.get('/api/device/sync')
    def device_sync(authorization: str | None = Header(default=None), since: int = 0):
        d = app_device(authorization)
        if d['owner_id'] is None:
            if d['code_expires'] and d['code_expires'] <= now():
                return {'status': 'expired', 'paired': False}
            return {'status': 'pending', 'paired': False}
        with db() as con:
            slots = account_access(con, d['owner_id'])['tv_slots']
            assigned = con.execute('''SELECT id FROM devices WHERE owner_id=?
                ORDER BY created_at, id LIMIT ?''', (d['owner_id'], slots)).fetchall()
            if d['id'] not in {row['id'] for row in assigned}:
                fail('This device exceeds the account TV allowance.', 403)
            con.execute('UPDATE devices SET last_seen=? WHERE id=?', (now(), d['id']))
            if d['revision'] <= since:
                return {'status': 'paired', 'paired': True, 'changed': False,
                        'revision': d['revision'], 'device_name': d['name']}
            playlist = own_playlist(con, d['owner_id'], d['playlist_id']) if d['playlist_id'] else None
        if not playlist:
            return {'status': 'paired', 'paired': True, 'changed': True,
                    'revision': d['revision'], 'device_name': d['name'], 'playlist': None}
        config = json.loads(cipher.decrypt(playlist['config_encrypted']).decode())
        return {'status': 'paired', 'paired': True, 'changed': True,
                'revision': d['revision'], 'device_name': d['name'],
                'playlist': {'id': playlist['id'], 'name': playlist['name'], **config}}

    install_billing(app, db, current_user, csrf_user, fail, throttle, prod)
    install_licensing(app, db, current_user, csrf_user, fail, throttle, prod)
    install_discovery(app)

    # Serve same-origin browser UI and TV emulator; /api routes registered above.
    @app.get('/')
    def main_page(request: Request):
        if request.url.hostname == 'stream.tunelytv.com':
            return RedirectResponse('/watch',status_code=302)
        return FileResponse(BASE / 'site' / 'home.html')

    @app.get('/account')
    def account_home():
        return FileResponse(BASE / 'site' / 'index.html')

    @app.get('/tv')
    def tv_page():
        return FileResponse(BASE / 'site' / 'tv.html')

    @app.get('/watch')
    def watch_page():
        return FileResponse(BASE / 'site' / 'watch.html')

    app.mount('/static', StaticFiles(directory=BASE / 'site'), name='static')
    return app


app = create_app()
