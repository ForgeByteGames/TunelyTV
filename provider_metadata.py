"""Authenticated M3U Plus *metadata* retrieval. Never restream media.

Only operates on a user's stored, encrypted get.php M3U Plus source. DNS pinning,
public-IP checks, no redirects, bounded reads, strict timeouts and no credential
or upstream URL logging reduce the danger of arbitrary server-side fetches.
"""
from __future__ import annotations

import gzip
import http.client
import ipaddress
import io
import re
import socket
import ssl
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


class ProviderError(Exception):
    """A non-sensitive, user-displayable provider metadata error."""


def is_m3u_plus(url: str) -> bool:
    try:
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or p.username or p.password or not p.hostname:
            return False
        q = parse_qs(p.query, keep_blank_values=False)
        return (p.path.rsplit('/', 1)[-1].lower() == 'get.php'
                and len(q.get('username', [])) == 1 and bool(q['username'][0])
                and len(q.get('password', [])) == 1 and bool(q['password'][0])
                and q.get('type', [''])[0].lower() == 'm3u_plus')
    except (ValueError, KeyError):
        return False


def derive_xmltv_url(url: str) -> str | None:
    """Only same-host provider's conventional xmltv.php for verified M3U Plus."""
    if not is_m3u_plus(url):
        return None
    p = urlsplit(url)
    q = parse_qs(p.query)
    guide_path = p.path.rsplit('/', 1)[0] + '/xmltv.php'
    return urlunsplit((p.scheme, p.netloc, guide_path,
                       urlencode({'username': q['username'][0], 'password': q['password'][0]}), ''))


def fetch_metadata(url: str, max_bytes: int = 8_000_000) -> bytes:
    """Bounded public-IP-only fetch, no redirect, no proxy, pinned resolved address.

    This is deliberately not a general URL fetcher: the caller must first
    check the encrypted account source is a recognized get.php M3U Plus link,
    or derive this exact same-provider XMLTV URL from that link.
    """
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ProviderError('The provider URL is invalid.')
    host = p.hostname
    if not host.isascii() or host.lower().endswith(('.local', '.internal')) or host.lower() == 'localhost':
        raise ProviderError('Only public provider hostnames are allowed.')
    try:
        port = p.port or (443 if p.scheme == 'https' else 80)
        endpoints = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = [result[4][0] for result in endpoints]
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ProviderError('The provider must resolve only to public Internet addresses.')
    except (OSError, ValueError):
        raise ProviderError('Unable to resolve the provider hostname.') from None

    # Connect to the *checked* IP, not a second DNS lookup (DNS-rebinding guard).
    conn = None
    try:
        remote = socket.create_connection((addresses[0], port), timeout=10)
        remote.settimeout(10)
        if p.scheme == 'https':
            remote = ssl.create_default_context().wrap_socket(remote, server_hostname=host)
            conn = http.client.HTTPSConnection(host, port, timeout=10)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=10)
        conn.sock = remote
        endpoint = p.path or '/'
        if p.query:
            endpoint += '?' + p.query
        host_header = host if (p.scheme, port) in (('https', 443), ('http', 80)) else f'{host}:{port}'
        conn.request('GET', endpoint, headers={
            'Host': host_header, 'Accept': 'application/xml, text/xml, audio/x-mpegurl, text/plain, */*',
            'Accept-Encoding': 'identity', 'Connection': 'close', 'User-Agent': 'TunelyTV-metadata/0.9.9'
        })
        response = conn.getresponse()
        if response.status != 200:
            raise ProviderError(f'Provider metadata unavailable (HTTP {response.status}).')
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ProviderError('Provider metadata exceeds the supported size limit.')
        return content
    except ProviderError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, TimeoutError):
        # Never expose URLs, tokens, passwords or underlying exceptions.
        raise ProviderError('Provider metadata is unreachable or timed out.') from None
    finally:
        if conn is not None:
            conn.close()


def parse_remote_playlist(raw: bytes) -> tuple[list[dict], list[str]]:
    """Parse authorized playlist metadata; do not download listed media URLs."""
    from server import extract_m3u_epg_candidates, valid_url
    content = raw.decode('utf-8-sig', errors='replace')
    if not content.lstrip().startswith('#EXTM3U'):
        raise ProviderError('Provider response was not a valid extended M3U playlist.')
    guide_urls = extract_m3u_epg_candidates(content)
    results: list[dict] = []
    attrs: dict[str, str] = {}
    title = ''
    for original in content.splitlines():
        line = original.strip()
        if line.startswith('#EXTINF:'):
            comma = -1
            quote = False
            for i, char in enumerate(line):
                if char == '"': quote = not quote
                elif char == ',' and not quote:
                    comma = i
                    break
            before = line if comma < 0 else line[:comma]
            attrs = {k.lower(): v[:2048] for k, v in re.findall(r'([A-Za-z][A-Za-z0-9-]*)\s*=\s*"([^"]*)"', before)}
            title = (line[comma+1:] if comma >= 0 else attrs.get('tvg-name', '')).strip()[:140]
        elif line and not line.startswith('#'):
            try:
                stream = valid_url(line)
            except ValueError:
                attrs = {};title = '';continue
            logo = attrs.get('tvg-logo', '')
            if not logo.startswith('https://'):
                logo = ''
            else:
                try: logo = valid_url(logo)
                except ValueError: logo = ''
            results.append({
                'name': title or f'Channel {len(results)+1}', 'url': stream,
                'group': attrs.get('group-title', 'Other')[:140] or 'Other',
                'tvgId': attrs.get('tvg-id', '')[:140],
                'tvgName': attrs.get('tvg-name', '')[:140], 'logo': logo
            })
            attrs = {};title = ''
            if len(results) >= 5000: break
    if not results:
        raise ProviderError('The provider playlist contains no usable channel URLs.')
    return results, guide_urls


def decode_xmltv(raw: bytes, max_output: int = 22_000_000) -> str:
    if raw[:2] == b'\x1f\x8b':
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as reader:
                raw = reader.read(max_output + 1)
        except (OSError, EOFError):
            raise ProviderError('Provider guide compression is invalid.') from None
    if len(raw) > max_output:
        raise ProviderError('Provider XMLTV guide exceeds the supported size limit.')
    text = raw.decode('utf-8-sig', errors='replace')
    if '<tv' not in text[:500]:
        raise ProviderError('Provider did not return a valid XMLTV guide.')
    return text
