"""Authenticated, server-only Premium TheSportsDB V2 team and score relay.

This module supports the JSON contracts used by TunelyTV Android, but does NOT
replace the separate, currently deployed Android account/profile auth service.
Consumers must supply a real account/device authorization dependency.

No Premium credential is ever placed in URL/query strings, logs or JSON output.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import re
import threading
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import Cookie, FastAPI, Header, HTTPException, Query

BASE = "https://www.thesportsdb.com/api/v2/json"
# Verified league identifiers; never accept a remote URL or arbitrary provider ID.
LEAGUES = {"NFL": "4391", "NHL": "4380", "NBA": "4387",
           "MLB": "4424", "EPL": "4328"}
DEFAULT_LEAGUES = ("NFL", "NHL", "NBA", "MLB")
MAX_LEAGUES = 5
MAX_BYTES = 2_000_000

class SportsSourceError(Exception):
    """An upstream failure; never expose raw provider or key details."""

def _text(value) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""

def _items(data, fields) -> list[dict]:
    if not isinstance(data, dict):
        raise SportsSourceError("Invalid upstream JSON")
    for name in fields:
        value = data.get(name)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    if any(name in data and data[name] is None for name in fields):
        return []
    raise SportsSourceError("Unknown upstream response")

def _league(value: str) -> str:
    label = value.strip().upper()
    if label not in LEAGUES:
        raise HTTPException(400, "unsupported_league")
    return label

def _selected(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_LEAGUES
    parts = [part.strip().upper() for part in value.split(",")]
    if not parts or len(parts) > MAX_LEAGUES or any(part not in LEAGUES for part in parts):
        raise HTTPException(400, "invalid_leagues")
    return tuple(dict.fromkeys(parts))

def _start_millis(event: dict) -> int:
    raw = _text(event.get("strTimestamp"))
    if raw:
        try:
            iso = raw.replace(" ", "T").replace("Z", "+00:00")
            value = datetime.fromisoformat(iso)
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return int(value.timestamp() * 1000)
        except (ValueError, OverflowError):
            pass
    day, clock = _text(event.get("dateEvent")), (
        _text(event.get("strEventTime")) or _text(event.get("strTime")) or "00:00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        try:
            return int(datetime.fromisoformat(day + "T" + clock).replace(
                tzinfo=timezone.utc).timestamp() * 1000)
        except (ValueError, OverflowError):
            pass
    return 0

def _done(status: str) -> bool:
    return status.strip().lower() in {
        "final", "ft", "match finished", "game finished", "finished",
        "completed", "aet", "after overtime", "after penalties", "full time"
    }

def _scores(raw, league: str, kind: str, current_ms: int) -> list[dict]:
    options = ("livescore", "events", "list") if kind == "live" else (
        "schedule", "events", "list")
    results: dict[str, dict] = {}
    for item in _items(raw, options)[:500]:
        ident = _text(item.get("idEvent"))
        away, home = _text(item.get("strAwayTeam")), _text(item.get("strHomeTeam"))
        if not re.fullmatch(r"\d{1,15}", ident) or not home or not away:
            continue
        provider_league = _text(item.get("idLeague"))
        if provider_league and provider_league != LEAGUES[league]:
            continue
        start = _start_millis(item)
        status = _text(item.get("strStatus"))
        home_score = item.get("intHomeScore")
        away_score = item.get("intAwayScore")
        home_score = _text(home_score) if home_score is not None else None
        away_score = _text(away_score) if away_score is not None else None
        finished = _done(status)
        if kind == "final" and not finished and (
            home_score is None or away_score is None):
            continue
        if kind == "upcoming" and (finished or (start and start < current_ms - 21_600_000)):
            continue
        actual = "final" if finished else kind
        record = {
            "id": ident, "league": league, "away": away, "home": home,
            "awayScore": away_score, "homeScore": home_score, "start": start,
            "clock": status or _text(item.get("strProgress")),
            "kind": actual, "done": actual == "final"
        }
        results.setdefault(ident, record)
    return sorted(results.values(), key=lambda row: row["start"])

def _teams(raw, league: str) -> list[dict]:
    teams = {}
    for item in _items(raw, ("list", "teams"))[:100]:
        ident = _text(item.get("idTeam") or item.get("id"))
        name = _text(item.get("strTeam") or item.get("name"))
        if not re.fullmatch(r"\d{1,12}", ident) or not name or len(name) > 120:
            continue
        badge = _text(item.get("strBadge") or item.get("strTeamBadge") or item.get("badge"))
        # Provider image metadata is an HTTPS URL, never a URL used for server fetch.
        if not re.match(r"^https://[^/@]+(?:/|$)", badge, re.I):
            badge = ""
        teams.setdefault(ident, {
            "id": ident, "name": name, "badge": badge, "league": league
        })
    return sorted(teams.values(), key=lambda row: row["name"].casefold())

class PremiumSportsService:
    def __init__(self, key: str | None = None, clock: Callable[[], float] = time.time):
        self._key = key  # None means read the host environment only at request time.
        self._clock = clock
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.RLock()

    def _premium_key(self) -> str:
        key = self._key if self._key is not None else os.environ.get(
            "THESPORTSDB_PREMIUM_API_KEY", "")
        if not key:
            raise HTTPException(503, "premium_provider_not_configured")
        return key

    def _get_json(self, path: str):
        # All paths are generated using the fixed LEAGUES allowlist.
        if not re.fullmatch(
            r"/(?:list/teams/\d{4}|livescore/\d{4}|"
            r"schedule/(?:previous|next)/league/\d{4})", path
        ):
            raise SportsSourceError("Invalid provider path")
        request = Request(BASE + path, method="GET", headers={
            "Accept": "application/json",
            "X-API-KEY": self._premium_key(),
            "User-Agent": "tunelyTV-backend/1"
        })
        try:
            with urlopen(request, timeout=9) as response:
                if response.status != 200:
                    raise SportsSourceError("Provider unavailable")
                if response.geturl().split("/")[2] != "www.thesportsdb.com":
                    raise SportsSourceError("Untrusted redirect")
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise SportsSourceError("Provider response too large")
                return json.loads(data.decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError, UnicodeError) as exc:
            raise SportsSourceError("Provider unavailable") from exc

    def _cached(self, path: str, ttl: int):
        with self._lock:
            hit = self._cache.get(path)
            if hit and hit[0] > self._clock():
                return hit[1]
        data = self._get_json(path)
        with self._lock:
            self._cache[path] = (self._clock() + ttl, data)
            if len(self._cache) > 180:
                for key in list(self._cache)[:30]:
                    self._cache.pop(key, None)
        return data

    def teams(self, league: str):
        self._premium_key()
        code = _league(league)
        try:
            raw = self._cached("/list/teams/" + LEAGUES[code], 6 * 3600)
            return {"league": code, "leagueId": LEAGUES[code],
                    "source": "TheSportsDB Premium V2", "teams": _teams(raw, code)}
        except SportsSourceError:
            raise HTTPException(502, "premium_source_unavailable") from None

    def scores(self, leagues: str | None):
        self._premium_key()
        selected = _selected(leagues)
        current_ms = int(self._clock() * 1000)

        def read_league(league: str):
            ident = LEAGUES[league]
            operations = (
                ("games", "/livescore/" + ident, 75, "live"),
                ("finals", "/schedule/previous/league/" + ident, 600, "final"),
                ("upcoming", "/schedule/next/league/" + ident, 600, "upcoming")
            )
            data: dict[str, list] = {}
            errors: list[str] = []
            for key, path, ttl, kind in operations:
                try:
                    data[key] = _scores(self._cached(path, ttl), league, kind, current_ms)
                except SportsSourceError:
                    data[key] = []
                    errors.append(key)
            return league, data, errors

        with ThreadPoolExecutor(max_workers=min(5, len(selected))) as pool:
            results = list(pool.map(read_league, selected))
        unavailable = [league for league, _, errors in results if len(errors) == 3]
        if len(unavailable) == len(selected):
            raise HTTPException(502, "premium_source_unavailable")
        games, finals, upcoming = {}, {}, {}
        partial = False
        for league, result, errors in results:
            if errors:
                partial = True
            for game in result["games"]:
                target = finals if game["done"] else games
                target.setdefault(league + ":" + game["id"], game)
            for game in result["finals"]:
                finals.setdefault(league + ":" + game["id"], game)
            for game in result["upcoming"]:
                upcoming.setdefault(league + ":" + game["id"], game)
        return {
            "enabled": True, "premium": True, "source": "TheSportsDB Premium V2",
            "leagues": list(selected),
            "games": list(games.values()), "finals": list(finals.values()),
            "upcoming": list(upcoming.values()),
            "partial": partial, "unavailableLeagues": unavailable,
            "updatedAt": datetime.fromtimestamp(
                self._clock(), tz=timezone.utc).isoformat(),
            "loadingSchedule": False
        }

def install_premium_sports(
    app: FastAPI, authorize: Callable[[str | None, str | None], object],
    service: PremiumSportsService | None = None
):
    """Install Android-compatible routes, reusing host account/device auth.

    The caller is responsible for validating Bearer token ownership or the
    browser's secure cookie. No self-asserted profile ID grants access.
    """
    provider = service or PremiumSportsService()

    @app.get("/api/sports/teams")
    def league_teams(
        league: str = Query(default=""),
        authorization: str | None = Header(default=None),
        tunely_session: str | None = Cookie(default=None)
    ):
        authorize(authorization, tunely_session)
        return provider.teams(league)

    @app.get("/api/sports/scores")
    def league_scores(
        leagues: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
        tunely_session: str | None = Cookie(default=None)
    ):
        authorize(authorization, tunely_session)
        return provider.scores(leagues)
