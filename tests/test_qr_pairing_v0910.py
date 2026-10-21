"""Native-ready QR handoff: the phone authorizes; TV never receives account password."""
import sqlite3

from fastapi.testclient import TestClient

from server import create_app, token_hash
from test_api import register, playlist


def setup(tmp_path):
    return TestClient(create_app(tmp_path/'qr.sqlite',tmp_path/'key'))


def enroll(client):
    r=client.post('/api/device/enroll',json={'name':'Living Room','platform':'Android TV'})
    assert r.status_code==201,r.text
    return r.json()


def test_tv_and_phone_pages_are_present_and_mobile_friendly(tmp_path):
    c=setup(tmp_path)
    tv=c.get('/tv');phone=c.get('/activate?code=ABCD-EFGH')
    assert tv.status_code==phone.status_code==200
    assert 'id="pairQr"' in tv.text
    assert 'id="pairCode"' in tv.text
    assert 'name="viewport"' in phone.text
    assert 'id="loginForm"' in phone.text and 'id="playlist"' in phone.text
    assert c.get('/static/activate-v0910.js').status_code==200


def test_qr_is_self_hosted_with_no_tokens_and_is_short_lived(tmp_path,monkeypatch):
    c=setup(tmp_path)
    e=enroll(c)
    import server
    real=server.qrcode.QRCode.add_data
    data_added=[]
    def spy(self,value,*args,**kwargs):
        data_added.append(value)
        return real(self,value,*args,**kwargs)
    monkeypatch.setattr(server.qrcode.QRCode,'add_data',spy)
    res=c.get('/api/pairings/qr',params={'code':e['pairing_code']})
    assert res.status_code==200,res.text
    assert res.headers['content-type'].startswith('image/svg+xml')
    assert b'<svg' in res.content and b'<path' in res.content
    assert data_added==['http://testserver/activate?code='+e['pairing_code']]
    assert e['device_token'] not in res.text
    assert res.headers['cache-control']=='no-store'
    with sqlite3.connect(tmp_path/'qr.sqlite') as db:
        db.execute('UPDATE devices SET code_expires=1 WHERE code_hash=?',
                   (token_hash(e['pairing_code'].replace('-','')),))
    assert c.get('/api/pairings/qr',params={'code':e['pairing_code']}).status_code==404


def test_activation_uses_existing_authenticated_claim_and_rejects_replays(tmp_path):
    tv=setup(tmp_path)
    owner=setup(tmp_path)
    h=register(owner)
    source=playlist(owner,h)
    e=enroll(tv)
    anonymous=setup(tmp_path)
    payload={'code':e['pairing_code'],'playlist_id':source}
    assert anonymous.post('/api/pairings/claim',json=payload).status_code in (401,403)
    # Real phone browser signs in with its *own* cookie and CSRF.
    mobile=setup(tmp_path)
    signin=mobile.post('/api/auth/login',json={'email':'first@example.com','password':'myStrongPassw0rd!'})
    assert signin.status_code==200,signin.text
    headers={'X-CSRF-Token':signin.json()['csrf_token']}
    assert mobile.get('/api/playlists').json()['playlists'][0]['id']==source
    claim=mobile.post('/api/pairings/claim',headers=headers,json=payload)
    assert claim.status_code==200,claim.text
    auth={'Authorization':'Bearer '+e['device_token']}
    sync=tv.get('/api/device/sync',headers=auth)
    assert sync.status_code==200 and sync.json()['playlist']['id']==source
    assert tv.get('/api/pairings/qr',params={'code':e['pairing_code']}).status_code==404
    assert mobile.post('/api/pairings/claim',headers=headers,json=payload).status_code==400


def test_invalid_code_and_untrusted_public_origin_rejected(tmp_path,monkeypatch):
    c=setup(tmp_path)
    e=enroll(c)
    assert c.get('/api/pairings/qr',params={'code':'WRONG'}).status_code==404
    monkeypatch.setenv('TUNELY_PAIRING_PUBLIC_URL','https://attacker.example/login?x=1')
    assert c.get('/api/pairings/qr',params={'code':e['pairing_code']}).status_code==503


def test_trusted_public_url_can_override_proxy_origin(tmp_path,monkeypatch):
    c=setup(tmp_path)
    e=enroll(c)
    import server
    values=[]
    original=server.qrcode.QRCode.add_data
    def spy(self,value,*args,**kwargs):
        values.append(value);return original(self,value,*args,**kwargs)
    monkeypatch.setattr(server.qrcode.QRCode,'add_data',spy)
    monkeypatch.setenv('TUNELY_PAIRING_PUBLIC_URL','https://tunelytv.com')
    assert c.get('/api/pairings/qr',params={'code':e['pairing_code']}).status_code==200
    assert values==['https://tunelytv.com/activate?code='+e['pairing_code']]
