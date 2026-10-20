from fastapi.testclient import TestClient
from server import create_app


def c(tmp_path):
    return TestClient(create_app(tmp_path/'home-test.sqlite',tmp_path/'home-test.key'))


def test_public_home_and_private_account_retained(tmp_path,monkeypatch):
    monkeypatch.delenv('TUNELY_METADATA_ENABLED',raising=False)
    test=c(tmp_path)
    root=test.get('/')
    assert root.status_code==200
    assert 'Your media.' in root.text and 'Streaming service' in root.text
    assert 'Live TV categories' in root.text
    assert 'tunely<strong>TV' in root.text
    account=test.get('/account')
    assert account.status_code==200
    assert 'authForm' in account.text
    assert 'page-sources' in account.text and 'page-devices' in account.text
    assert test.get('/watch').status_code==200
    assert 'tv-mode-v095' in test.get('/watch').text
    assert test.get('/static/home-v095.css').status_code==200
    assert test.get('/static/blue-shell-v095.css').status_code==200
    assert test.get('/static/tunely-icon.webp').status_code==200


def test_no_provider_credentials_no_metadata_or_titles(tmp_path,monkeypatch):
    monkeypatch.delenv('TUNELY_METADATA_ENABLED',raising=False)
    monkeypatch.delenv('TUNELY_TMDB_READ_TOKEN',raising=False)
    monkeypatch.delenv('TUNELY_TMDB_API_KEY',raising=False)
    test=c(tmp_path)
    response=test.get('/api/discover/status')
    assert response.json()['enabled'] is False
    assert test.get('/api/discover/home').status_code==503
    assert test.get('/api/discover/search',params={'q':'The Accountant'}).status_code==503


def test_stream_subdomain_routes_into_clean_watch(tmp_path,monkeypatch):
    monkeypatch.delenv('TUNELY_METADATA_ENABLED',raising=False)
    app=create_app(tmp_path/'split-test.sqlite',tmp_path/'split-test.key')
    test=TestClient(app,base_url='https://stream.tunelytv.com',follow_redirects=False)
    response=test.get('/')
    assert response.status_code==302 and response.headers['location']=='/watch'


def test_ui_routes_are_settings_first_and_no_bundled_content(tmp_path):
    test=c(tmp_path)
    home=test.get('/').text
    assert 'href="/account?section=sources"' in home
    assert 'Streaming services are independent' in home
    assert 'No catalog or programming is included' not in home  # displayed only by client
    watch=test.get('/watch').text
    assert 'href="/account?section=sources"' in watch
    assert 'id="sourcePick"' in watch  # existing hidden player bridge preserved
    assert 'id="theaterGuide"' in watch
