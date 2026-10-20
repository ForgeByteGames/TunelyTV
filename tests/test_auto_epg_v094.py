"""EPG discovery integration: source-advertised URLs only, account isolation."""
import sqlite3
from server import extract_m3u_epg_candidates
from test_api import setup, register, enable_web

SAMPLE = '''#EXTM3U x-tvg-url="https://epg.example.net/guide.xml,https://backup.example.net/schedule.xml.gz"
#EXTINF:-1 tvg-id="demo.alpha" tvg-name="Alpha Demo" group-title="Testing",Alpha Channel
https://cdn.example.org/a/index.m3u8
#EXTINF:-1 tvg-name="Beta Demo" group-title="Testing",Beta Channel
https://cdn.example.org/b/index.m3u8
'''


def test_extract_provider_advertised_header_links():
    assert extract_m3u_epg_candidates(SAMPLE) == [
        'https://epg.example.net/guide.xml', 'https://backup.example.net/schedule.xml.gz'
    ]
    assert extract_m3u_epg_candidates("#EXTM3U url-tvg='https://provider.example/epg.xml'\n#EXTINF:-1,X\nhttps://x.example/hls") == ['https://provider.example/epg.xml']
    assert extract_m3u_epg_candidates('#EXTM3U\n#EXTINF:-1,No guide\nhttps://cdn.example/play') == []


def test_reject_unsafe_urls_and_ignore_channel_metadata():
    data = '''#EXTM3U url-tvg="file:///etc/passwd,http://evil:pw@example.net/guide.xml,https://safe.example/guide.xml"
#EXTINF:-1 url-tvg="https://not-from-header.example/guide",Channel
https://cdn.example/watch
'''
    assert extract_m3u_epg_candidates(data) == ['https://safe.example/guide.xml']
    assert extract_m3u_epg_candidates('#EXTM3U x-tvg-url="javascript:alert(1)"') == []


def test_saved_m3u_file_exposes_header_epg_to_owner_only(tmp_path):
    owner = setup(tmp_path)
    token = register(owner)
    enable_web(owner,token)
    upload = owner.post('/api/playlists', headers=token, json={
        'name': 'Authorized fixture', 'type': 'm3u_file', 'filename': 'local.m3u', 'content': SAMPLE
    })
    assert upload.status_code == 201, upload.text
    pid = upload.json()['id']
    result = owner.get('/api/playlists/' + pid + '/playable')
    assert result.status_code == 200
    data = result.json()
    assert len(data['channels']) == 2
    assert data['channels'][0]['tvgId'] == 'demo.alpha'
    assert data['channels'][0]['tvgName'] == 'Alpha Demo'
    assert data['epg_candidates'] == ['https://epg.example.net/guide.xml', 'https://backup.example.net/schedule.xml.gz']
    assert 'epg_candidates' not in owner.get('/api/playlists').json()['playlists'][0]
    other = setup(tmp_path)
    register(other, 'other@example.net')
    assert other.get('/api/playlists/' + pid + '/playable').status_code == 404
    raw = (tmp_path/'api.sqlite').read_bytes()
    assert b'https://epg.example.net/guide.xml' not in raw


def test_manual_override_does_not_destroy_embedded_links(tmp_path):
    client = setup(tmp_path)
    token = register(client)
    enable_web(client,token)
    pid = client.post('/api/playlists', headers=token, json={
        'name':'Test','type':'m3u_file','filename':'authorized.m3u','content':SAMPLE
    }).json()['id']
    endpoint = '/api/playlists/' + pid
    resp = client.patch(endpoint+'/guide', headers=token, json={'url': 'https://manual.example/guide.xml'})
    assert resp.status_code == 200, resp.text
    conf = client.get(endpoint+'/playable').json()
    assert conf['epg_url'] == 'https://manual.example/guide.xml'
    assert len(conf['epg_candidates']) == 2
    assert client.patch(endpoint+'/guide', headers=token, json={'url': None}).status_code == 200
    conf = client.get(endpoint+'/playable').json()
    assert conf['epg_url'] is None and len(conf['epg_candidates']) == 2
