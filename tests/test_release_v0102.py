from fastapi.testclient import TestClient
from server import create_app


def test_combined_version_has_all_required_routes(tmp_path):
    client = TestClient(create_app(tmp_path/'combined.db', tmp_path/'key'))
    assert client.get('/').status_code == 200
    assert client.get('/tv').status_code == 200
    assert client.get('/activate').status_code == 200
    html = client.get('/').text
    assert 'Movies from your playlists' in html
    assert 'TV Series from your playlists' in html
    assert 'Explore by streaming service' in html
    assert '/static/home-library-v010.js' in html
    assert client.get('/static/home-library-v010.js').status_code == 200
    assert 'pairing_code' in client.get('/static/tv.js').text
    assert client.get('/api/pairings/qr?code=INVALID').status_code == 404
    assert '0.10.2' in client.get('/api/health').text


def test_restored_library_and_qr_endpoints_coexist(tmp_path):
    client = TestClient(create_app(tmp_path/'combined.db', tmp_path/'key'))
    registration=client.post('/api/auth/register',json={'email':'both@example.com','password':'test-passphrase-very-long-123'})
    assert registration.status_code==201
    headers={'X-CSRF-Token':registration.json()['csrf_token']}
    r=client.post('/api/playlists',json={'type':'m3u_url','name':'Sintel','url':'https://example.org/movie/test.m3u8','content_kind':'movies'},headers=headers)
    assert r.status_code==201
    assert client.get('/api/playlists').json()['playlists'][0]['content_kind']=='movies'
    assert client.get('/api/library/hidden').json()['items']==[]
    assert client.get('/activate').status_code==200
    assert client.get('/tv').status_code==200
