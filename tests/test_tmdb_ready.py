"""Offline tests for licensed TMDB integration. No live TMDB requests."""
import json
from fastapi.testclient import TestClient
from server import create_app
import discovery


def test_rights_gate_prevents_automatic_commercial_activation(tmp_path, monkeypatch):
    monkeypatch.setenv('TUNELY_METADATA_ENABLED', 'true')
    monkeypatch.setenv('TUNELY_TMDB_READ_TOKEN', 'TEST_TOKEN_NOT_FOR_NETWORK')
    monkeypatch.delenv('TUNELY_TMDB_RIGHTS_CONFIRMED', raising=False)
    app = create_app(tmp_path/'test.sqlite', tmp_path/'test.key')
    client = TestClient(app)
    status = client.get('/api/discover/status')
    assert status.status_code == 200
    assert status.json()['enabled'] is False
    assert 'TEST_TOKEN_NOT_FOR_NETWORK' not in str(status.json())
    assert client.get('/api/discover/home').status_code == 503


def test_mocked_metadata_discovery_and_credits(tmp_path, monkeypatch):
    monkeypatch.setenv('TUNELY_METADATA_ENABLED', 'true')
    monkeypatch.setenv('TUNELY_TMDB_READ_TOKEN', 'FAKE-SECRET')
    monkeypatch.setenv('TUNELY_TMDB_RIGHTS_CONFIRMED', 'true')
    calls = []

    class Result:
        def __init__(self, body): self.body = json.dumps(body).encode('utf-8')
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _limit): return self.body

    def fake_open(req, timeout=7):
        calls.append((req.full_url, req.get_header('Authorization')))
        path = req.full_url.split('?', 1)[0]
        if path.endswith('/trending/movie/week'):
            return Result({'results':[{'id':101,'title':'Example Film', 'release_date':'2026-02-10', 'backdrop_path':'/sample.jpg'}]})
        if path.endswith('/trending/tv/week'):
            return Result({'results':[{'id':202,'name':'Example Show', 'first_air_date':'2025-11-20'}]})
        if path.endswith('/watch/providers/movie'):
            return Result({'results':[{'provider_id':8,'provider_name':'Netflix'}]})
        if path.endswith('/discover/movie'):
            return Result({'results':[{'id':101,'title':'Example Film'}]})
        if path.endswith('/search/multi'):
            return Result({'results':[{'id':101,'media_type':'movie','title':'Example Film','release_date':'2026-02-10'}]})
        if path.endswith('/movie/101/watch/providers'):
            return Result({'results':{'US':{'flatrate':[{'provider_name':'Netflix'}], 'link':'https://www.themoviedb.org/movie/101-example/watch'}}})
        if path.endswith('/movie/101'):
            return Result({'overview':'Mock film description'})
        raise AssertionError(f'Unexpected mocked TMDB request: {path}')
    monkeypatch.setattr(discovery, 'urlopen', fake_open)
    client = TestClient(create_app(tmp_path/'test.sqlite', tmp_path/'test.key'))
    status = client.get('/api/discover/status').json()
    assert status['enabled'] is True and status['watch_provider_source'] == 'JustWatch'
    home = client.get('/api/discover/home')
    assert home.status_code == 200
    assert home.json()['movies'][0]['image'] == 'https://image.tmdb.org/t/p/w500/sample.jpg'
    assert home.json()['series'][0]['kind'] == 'tv'
    search = client.get('/api/discover/search', params={'q':'Example Film'})
    assert search.json()['results'][0]['year'] == '2026'
    provider = client.get('/api/discover/provider', params={'name':'Netflix'})
    assert provider.json()['results'][0]['title'] == 'Example Film'
    details = client.get('/api/discover/title/movie/101').json()
    assert details['providers']['flatrate'][0]['name']=='Netflix'
    assert details['watch_link'].startswith('https://www.themoviedb.org/')
    html = client.get('/').text
    assert 'This product uses the TMDB API but is not endorsed or certified by TMDB.' in html
    assert 'JustWatch' in html
    assert all(header == 'Bearer FAKE-SECRET' for _, header in calls)
    assert all('FAKE-SECRET' not in url for url, _ in calls)


def test_bad_region_and_unrecognized_service(tmp_path, monkeypatch):
    monkeypatch.setenv('TUNELY_METADATA_ENABLED', 'true')
    monkeypatch.setenv('TUNELY_TMDB_READ_TOKEN', 'FAKE-SECRET')
    monkeypatch.setenv('TUNELY_TMDB_RIGHTS_CONFIRMED', 'true')
    client = TestClient(create_app(tmp_path/'test.sqlite',tmp_path/'test.key'))
    assert client.get('/api/discover/home?region=UnitedStates').status_code == 422
    assert client.get('/api/discover/provider?name=FakeStreamingNetwork').status_code == 404
    assert client.get('/api/discover/search?q=x').status_code == 422
