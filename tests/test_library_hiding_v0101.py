import hashlib
from fastapi.testclient import TestClient
from server import create_app


def client(tmp_path):
    return TestClient(create_app(tmp_path / 'hidden.sqlite', tmp_path / 'fernet.key'))


def signup(c, address):
    r = c.post('/api/auth/register', json={
        'email': address, 'password': 'test-passphrase-very-long-123'})
    assert r.status_code == 201, r.text
    return {'X-CSRF-Token': r.json()['csrf_token']}


def test_hidden_items_persist_across_sessions_and_are_restorable(tmp_path):
    c = client(tmp_path)
    headers = signup(c, 'hidden@example.com')
    r = c.post('/api/playlists', headers=headers, json={
        'name': 'Movies', 'type': 'm3u_url',
        'url': 'https://example.org/media/feature.m3u8', 'content_kind': 'movies'})
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    key = hashlib.sha256(b'https://example.org/media/feature.m3u8').hexdigest()
    assert c.post(f'/api/playlists/{pid}/library-hidden',json={
        'item_key': key,'title': 'Example Movie', 'reason': 'user_hidden'}).status_code == 403
    r=c.post(f'/api/playlists/{pid}/library-hidden',headers=headers,json={
        'item_key': key,'title': 'Example Movie', 'reason': 'user_hidden'})
    assert r.status_code == 201, r.text
    listing=c.get('/api/library/hidden').json()['items']
    assert len(listing)==1
    assert listing[0]['title']=='Example Movie'
    assert 'example.org' not in str(listing)
    assert listing[0]['playlist_id']==pid
    reinit=client(tmp_path)
    # Log in again, confirms the records are durable not tab-local.
    login=reinit.post('/api/auth/login',json={'email':'hidden@example.com','password':'test-passphrase-very-long-123'})
    assert login.status_code==200
    headers2={'X-CSRF-Token':login.json()['csrf_token']}
    assert len(reinit.get('/api/library/hidden').json()['items'])==1
    delete=reinit.delete(f'/api/playlists/{pid}/library-hidden/{key}',headers=headers2)
    assert delete.status_code==200,delete.text
    assert reinit.get('/api/library/hidden').json()['items']==[]


def test_hidden_items_private_and_validation(tmp_path):
    first=client(tmp_path); h1=signup(first,'h1@example.com')
    p=first.post('/api/playlists',headers=h1,json={'name':'Movies','type':'m3u_url','url':'https://example.org/movie.m3u8'}).json()['id']
    second=client(tmp_path);h2=signup(second,'h2@example.com')
    good='0'*64
    assert second.get('/api/library/hidden').json()['items']==[]
    assert second.post(f'/api/playlists/{p}/library-hidden',headers=h2,json={'item_key':good,'title':'Item'}).status_code==404
    assert first.post(f'/api/playlists/{p}/library-hidden',headers=h1,json={'item_key':'notahash','title':'Item'}).status_code==422
    assert second.delete(f'/api/playlists/{p}/library-hidden/{good}',headers=h2).status_code==404


def test_hidden_entries_removed_when_source_deleted(tmp_path):
    c=client(tmp_path);h=signup(c,'cleanup@example.com')
    p=c.post('/api/playlists',headers=h,json={'name':'Movies','type':'m3u_url','url':'https://example.org/movie.m3u8'}).json()['id']
    assert c.post(f'/api/playlists/{p}/library-hidden',headers=h,json={'item_key':'f'*64,'title':'Example'}).status_code==201
    assert c.delete(f'/api/playlists/{p}',headers=h).status_code==200
    assert c.get('/api/library/hidden').json()['items']==[]
