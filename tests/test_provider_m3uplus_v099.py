"""No live provider access: fake URLs, stubbed upstream metadata, per-user auth tests."""
from __future__ import annotations

import gzip
import ipaddress

import pytest
from fastapi.testclient import TestClient

import provider_metadata as pm
import server


SOURCE = 'https://tv.fixture.example/get.php?username=DEMOUSER&password=DEMOPASS&type=m3u_plus&output=ts'
SAMPLE = b'''#EXTM3U x-tvg-url="https://tv.fixture.example/epg.xml"
#EXTINF:-1 tvg-id="news.alpha" tvg-logo="https://logos.fixture.example/news.png" group-title="News",Alpha News
http://tv.fixture.example/live/DEMOUSER/DEMOPASS/1.ts
#EXTINF:-1 tvg-id="sports.beta" tvg-name="Beta Sports",Beta Sports
https://tv.fixture.example/live/2.m3u8
'''
XMLTV = b'<?xml version="1.0"?><tv><channel id="news.alpha"><display-name>Alpha</display-name></channel><programme channel="news.alpha" start="20261020120000 +0000" stop="20261020130000 +0000"><title>Sample Program</title></programme></tv>'


def make_client(tmp_path):
    return TestClient(server.create_app(tmp_path/'testing.sqlite', tmp_path/'fernet.key'))


def register(client, email='owner@fixture.example'):
    r = client.post('/api/auth/register', json={'email': email, 'password': 'notRealPassword12345!'})
    assert r.status_code == 201, r.text
    return {'X-CSRF-Token': r.json()['csrf_token']}


def save(client, headers, url=SOURCE):
    resp=client.post('/api/playlists', headers=headers, json={'type':'m3u_url', 'name':'My licensed fixture', 'url':url})
    assert resp.status_code == 201, resp.text
    return resp.json()['id']


def test_recognizes_only_get_php_with_both_credentials():
    assert pm.is_m3u_plus(SOURCE)
    assert not pm.is_m3u_plus('https://fixture.example/get.php?username=ok&type=m3u_plus')
    assert not pm.is_m3u_plus('https://fixture.example/xmltv.php?username=x&password=y&type=m3u_plus')
    assert not pm.is_m3u_plus('https://fixture.example/get.php?username=x&username=z&password=y&type=m3u_plus')
    assert not pm.is_m3u_plus('https://fixture.example/get.php?username=x&password=y&type=m3u')
    guide=pm.derive_xmltv_url(SOURCE)
    assert guide=='https://tv.fixture.example/xmltv.php?username=DEMOUSER&password=DEMOPASS'
    assert pm.derive_xmltv_url('https://fixture.example/a.m3u') is None


def test_parses_logos_groups_and_epg_ids():
    entries, guides=pm.parse_remote_playlist(SAMPLE)
    assert len(entries)==2
    assert entries[0]['tvgId']=='news.alpha'
    assert entries[0]['group']=='News'
    assert entries[0]['logo']=='https://logos.fixture.example/news.png'
    assert entries[1]['logo']==''
    assert guides==['https://tv.fixture.example/epg.xml']


def test_validates_guide_and_bounded_compression():
    assert 'Sample Program' in pm.decode_xmltv(gzip.compress(XMLTV))
    with pytest.raises(pm.ProviderError): pm.decode_xmltv(b'<!doctype html><html>Error</html>')
    with pytest.raises(pm.ProviderError): pm.decode_xmltv(gzip.compress(XMLTV), max_output=8)


def test_credentials_encrypted_no_anonymous_or_cross_account_fetch(tmp_path,monkeypatch):
    client=make_client(tmp_path)
    h=register(client)
    pid=save(client,h)
    endpoint='/api/playlists/'+pid
    anonymous=make_client(tmp_path)
    assert anonymous.get(endpoint+'/provider-channels').status_code==401
    assert anonymous.get(endpoint+'/provider-guide').status_code==401
    monkeypatch.setattr(server,'fetch_metadata',lambda *_args,**_kwargs: (_ for _ in ()).throw(AssertionError('Unexpected fetch')))
    assert client.get(endpoint+'/provider-channels').status_code==403
    trial=client.post('/api/license/trial/start',headers=h)
    assert trial.status_code==201,trial.text
    conf=client.get(endpoint+'/playable')
    assert conf.status_code==200
    assert conf.json()['type']=='m3u_plus'
    assert 'url' not in conf.json()
    assert 'DEMOUSER' not in conf.text and 'DEMOPASS' not in conf.text
    monkeypatch.setattr(server,'fetch_metadata',lambda url,max_bytes=8_000_000: XMLTV if 'xmltv.php' in url else SAMPLE)
    channels=client.get(endpoint+'/provider-channels')
    assert channels.status_code==200, channels.text
    assert channels.json()['total']==2
    assert channels.json()['epg_candidates']==[endpoint+'/provider-guide']
    assert 'no-store' in channels.headers['cache-control']
    assert 'DEMOUSER' not in channels.json()['epg_candidates'][0]
    guide=client.get(endpoint+'/provider-guide')
    assert guide.status_code==200 and 'Sample Program' in guide.text
    assert 'no-store' in guide.headers['cache-control']
    assert b'DEMOPASS' not in (tmp_path/'testing.sqlite').read_bytes()
    assert b'DEMOUSER' not in (tmp_path/'testing.sqlite').read_bytes()
    other=make_client(tmp_path)
    register(other,'different@fixture.example')
    assert other.get(endpoint+'/provider-channels').status_code==404
    assert other.get(endpoint+'/provider-guide').status_code==404


def test_not_any_user_supplied_url_becomes_a_server_fetch(tmp_path,monkeypatch):
    client=make_client(tmp_path)
    h=register(client)
    assert client.post('/api/license/trial/start',headers=h).status_code==201
    pid=save(client,h,'https://tv.fixture.example/general.m3u')
    called=[]
    monkeypatch.setattr(server,'fetch_metadata',lambda *args,**kwargs: called.append(args))
    assert client.get('/api/playlists/'+pid+'/provider-channels').status_code==400
    assert client.get('/api/playlists/'+pid+'/provider-guide').status_code==400
    assert called==[]


def test_ssrf_private_ip_rejected_before_socket_connection(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *args,**kwargs:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',80))])
    with pytest.raises(pm.ProviderError, match='public Internet'):
        pm.fetch_metadata('http://example.org/get.php?username=u&password=p&type=m3u_plus')
