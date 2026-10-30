"""Premium Android sports relay: identity, parsing, caching and fallback security."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from server import create_app
from sports_premium import PremiumSportsService, SportsSourceError


def client(tmp_path):
    return TestClient(create_app(tmp_path / "sports.sqlite", tmp_path / "vault.key"))


def login(c):
    result = c.post("/api/auth/register", json={
        "email": "sports@example.org", "password": "long-safe-passphrase-123!"
    })
    assert result.status_code == 201, result.text
    return {"X-CSRF-Token": result.json()["csrf_token"]}


def sample_event(eid="104", league="4391", status="2Q"):
    timestamp = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    return {
        "idEvent": eid, "idLeague": league, "strHomeTeam": "Buffalo Bills",
        "strAwayTeam": "Miami Dolphins", "intHomeScore": "21",
        "intAwayScore": "14", "strStatus": status, "strTimestamp": timestamp
    }


def test_requires_account_and_paired_device_and_does_not_trust_profile_header(tmp_path, monkeypatch):
    monkeypatch.setenv("THESPORTSDB_PREMIUM_API_KEY", "test-secret-value")
    def fake(self, path):
        return {"list": [{"idTeam": "9", "strTeam": "Buffalo Bills",
                          "strBadge": "https://images.example/bills.png"}]}
    monkeypatch.setattr(PremiumSportsService, "_get_json", fake)
    c = client(tmp_path)
    url = "/api/sports/teams?league=NFL"
    assert c.get(url, headers={"X-Nexa-Profile": "untrusted"}).status_code == 401
    device = c.post("/api/device/enroll", json={
        "name": "Test TV", "platform": "Android TV"
    }).json()
    bearer = {"Authorization": "Bearer " + device["device_token"]}
    assert c.get(url, headers=bearer).status_code == 403
    csrf = login(c)
    # The web account session may browse; the same team's badge is not a secret.
    first = c.get(url)
    assert first.status_code == 200, first.text
    assert first.json()["teams"][0]["name"] == "Buffalo Bills"
    assert "test-secret-value" not in first.text
    paired = c.post("/api/pairings/claim", headers=csrf, json={
        "code": device["pairing_code"]
    })
    assert paired.status_code == 200, paired.text
    d = c.get(url, headers=bearer)
    assert d.status_code == 200, d.text
    assert len(d.json()["teams"]) == 1
    device_id = paired.json()["device"]["id"]
    assert c.delete("/api/devices/" + device_id, headers=csrf).status_code == 200
    assert c.get(url, headers=bearer).status_code == 401


def test_scores_contract_and_cache_with_only_real_games(tmp_path, monkeypatch):
    monkeypatch.setenv("THESPORTSDB_PREMIUM_API_KEY", "test-secret-value")
    calls = []
    def fake(self, path):
        calls.append(path)
        if "/livescore/" in path:
            return {"livescore": [sample_event()]}
        if "/previous/" in path:
            return {"schedule": [sample_event("105", status="Final")]}
        return {"schedule": [dict(sample_event("106", status=""),
                                  intHomeScore=None, intAwayScore=None)]}
    monkeypatch.setattr(PremiumSportsService, "_get_json", fake)
    c = client(tmp_path)
    login(c)
    r = c.get("/api/sports/scores?leagues=NFL")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "TheSportsDB Premium V2"
    assert body["premium"] is True and body["enabled"] is True
    assert body["leagues"] == ["NFL"]
    assert len(body["games"]) == len(body["finals"]) == len(body["upcoming"]) == 1
    assert body["games"][0]["away"] == "Miami Dolphins"
    assert body["games"][0]["homeScore"] == "21"
    assert body["upcoming"][0]["kind"] == "upcoming"
    assert "test-secret-value" not in r.text
    assert len(calls) == 3
    assert c.get("/api/sports/scores?leagues=NFL").status_code == 200
    assert len(calls) == 3
    assert c.get("/api/sports/scores?leagues=INVALID").status_code == 400
    assert len(calls) == 3


def test_missing_key_and_upstream_errors_do_not_leak_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("THESPORTSDB_PREMIUM_API_KEY", raising=False)
    c = client(tmp_path)
    login(c)
    assert c.get("/api/sports/teams?league=NHL").status_code == 503
    assert c.get("/api/sports/scores?leagues=NHL").status_code == 503
    monkeypatch.setenv("THESPORTSDB_PREMIUM_API_KEY", "private-test-key")
    def bad(self, path):
        raise SportsSourceError("irrelevant internal provider URL")
    monkeypatch.setattr(PremiumSportsService, "_get_json", bad)
    r = c.get("/api/sports/teams?league=NHL")
    assert r.status_code == 502
    assert "irrelevant" not in r.text and "private-test-key" not in r.text
    r = c.get("/api/sports/scores?leagues=NFL,NHL")
    assert r.status_code == 502
    assert "private-test-key" not in r.text


def test_partial_source_response_is_reported_not_faked(tmp_path, monkeypatch):
    monkeypatch.setenv("THESPORTSDB_PREMIUM_API_KEY", "secret-test-key")
    def partial(self, path):
        if "/previous/" in path:
            raise SportsSourceError("offline")
        if "/livescore/" in path:
            return {"livescore": []}
        return {"schedule": []}
    monkeypatch.setattr(PremiumSportsService, "_get_json", partial)
    c = client(tmp_path)
    login(c)
    response = c.get("/api/sports/scores?leagues=NHL")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["partial"] is True and data["unavailableLeagues"] == []
    assert data["games"] == data["finals"] == data["upcoming"] == []


def test_bad_upstream_team_names_are_not_invented(tmp_path, monkeypatch):
    monkeypatch.setenv("THESPORTSDB_PREMIUM_API_KEY", "test-key")
    def bad(self, path):
        return {"list": [
            {"idTeam": "1", "strTeam": "Buffalo Bills", "strBadge": "http://unsafe.example/img"},
            {"idTeam": "1", "strTeam": "duplicate"},
            {"idTeam": "", "strTeam": "Not a team"},
            {"idTeam": "2", "strTeam": "Buffalo Sabres", "strBadge": "https://safe.example/a.png"},
        ]}
    monkeypatch.setattr(PremiumSportsService, "_get_json", bad)
    c = client(tmp_path)
    login(c)
    j = c.get("/api/sports/teams?league=NFL").json()
    assert [t["name"] for t in j["teams"]] == ["Buffalo Bills", "Buffalo Sabres"]
    assert j["teams"][0]["badge"] == ""
