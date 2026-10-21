from fastapi.testclient import TestClient
from server import create_app


def create(tmp_path):
    return TestClient(create_app(tmp_path/'library.sqlite',tmp_path/'key.key'))


def signup(client, email):
    r=client.post('/api/auth/register',json={'email':email,'password':'test-passphrase-very-long-123'})
    assert r.status_code==201,r.text
    return {'X-CSRF-Token':r.json()['csrf_token']}


def test_m3u8_movie_source_can_be_reclassified_without_readding(tmp_path):
    client=create(tmp_path)
    headers=signup(client,'librarytest@example.com')
    sample='https://bitdash-a.akamaihd.net/content/sintel/hls/playlist.m3u8'
    posted=client.post('/api/playlists',json={'name':'Sintel test','type':'m3u_url','url':sample},headers=headers)
    assert posted.status_code==201,posted.text
    source_id=posted.json()['id']
    assert client.get('/api/playlists').json()['playlists'][0]['content_kind']=='auto'
    patch=client.patch(f'/api/playlists/{source_id}/content-kind',json={'content_kind':'movies'},headers=headers)
    assert patch.status_code==200,patch.text
    assert client.get('/api/playlists').json()['playlists'][0]['content_kind']=='movies'
    assert sample not in client.get('/api/playlists').text
    assert client.get(f'/api/playlists/{source_id}/playable').status_code==403
    trial=client.post('/api/license/trial/start',headers=headers)
    assert trial.status_code==201,trial.text
    playable=client.get(f'/api/playlists/{source_id}/playable')
    assert playable.status_code==200,playable.text
    assert playable.json()['content_kind']=='movies'
    assert playable.json()['url']==sample


def test_uploaded_playlist_media_hints_and_account_isolation(tmp_path):
    first=create(tmp_path);h1=signup(first,'firstlibrary@example.com')
    content=('''#EXTM3U
#EXTINF:-1 group-title="VOD Films" tvg-logo="https://images.example.org/film.png",Example Movie
https://media.example.org/movie/1.m3u8
#EXTINF:-1 group-title="Series" media-type="episode",Example Show S01E02
https://media.example.org/series/1.m3u8
#EXTINF:-1 group-title="Sports",Sports Channel
https://media.example.org/live.m3u8
''')
    response=first.post('/api/playlists',headers=h1,json={'name':'Mixed authorized library','type':'m3u_file','filename':'movies.m3u','content':content,'content_kind':'auto'})
    assert response.status_code==201,response.text
    pid=response.json()['id']
    first.post('/api/license/trial/start',headers=h1)
    rows=first.get(f'/api/playlists/{pid}/playable').json()['channels']
    assert len(rows)==3
    assert rows[0]['logo']=='https://images.example.org/film.png'
    assert rows[1]['mediaHint']=='episode'
    second=create(tmp_path);h2=signup(second,'secondlibrary@example.com')
    assert second.get('/api/playlists').json()['playlists']==[]
    assert second.patch(f'/api/playlists/{pid}/content-kind',headers=h2,json={'content_kind':'movies'}).status_code==404
    assert second.get(f'/api/playlists/{pid}/playable').status_code==404


def test_public_sections_correctly_separated(tmp_path):
    client=create(tmp_path)
    html=client.get('/').text
    assert 'Movies from your playlists' in html
    assert 'TV Series from your playlists' in html
    assert 'Explore by streaming service' in html
    assert 'Trending movies</h2>' not in html
    assert '/static/home-library-v010.js' in html
    assert client.get('/static/home-library-v010.js').status_code==200
    assert client.get('/static/home-library-v010.css').status_code==200
    assert 'TUNELY_TMDB_READ_TOKEN' not in html
