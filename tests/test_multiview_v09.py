"""Multi-View plan access stays owner-specific, test-only and off for Free by default."""
import sqlite3

from fastapi.testclient import TestClient
from server import create_app


def app_client(tmp_path):
    return TestClient(create_app(tmp_path/'multi.sqlite',tmp_path/'multi.key'))


def login(client, email):
    resp=client.post('/api/auth/register',json={'email':email,'password':'StrongPassword_2026!'})
    assert resp.status_code==201,resp.text
    return client.get('/api/features/multiview')


def test_multiview_rejects_unauth_and_free_has_no_access(tmp_path,monkeypatch):
    monkeypatch.delenv('TUNELY_MULTIVIEW_PRIVATE_PREVIEW',raising=False)
    client=app_client(tmp_path)
    assert client.get('/api/features/multiview').status_code==401
    result=login(client,'free@example.org').json()
    assert result['plan']=='free' and result['max_panes']==0 and result['preview'] is False
    assert result['feature_live'] is False


def test_test_paid_entitlements_and_expiration(tmp_path,monkeypatch):
    monkeypatch.delenv('TUNELY_MULTIVIEW_PRIVATE_PREVIEW',raising=False)
    client=app_client(tmp_path)
    login(client,'subscriber@example.org')
    with sqlite3.connect(tmp_path/'multi.sqlite') as con:
        uid=con.execute("SELECT id FROM users WHERE email='subscriber@example.org'").fetchone()[0]
        con.execute('INSERT INTO billing_accounts(user_id,plus_lifetime,updated_at) VALUES(?,?,?)',(uid,1,1))
    assert client.get('/api/features/multiview').json()['max_panes']==2
    with sqlite3.connect(tmp_path/'multi.sqlite') as con:
        con.execute("UPDATE billing_accounts SET subscription_plan='premium', subscription_status='active' WHERE user_id=?",(uid,))
    assert client.get('/api/features/multiview').json()['max_panes']==4
    with sqlite3.connect(tmp_path/'multi.sqlite') as con:
        con.execute("UPDATE billing_accounts SET subscription_plan='family', subscription_status='active' WHERE user_id=?",(uid,))
    assert client.get('/api/features/multiview').json()['plan']=='family'
    with sqlite3.connect(tmp_path/'multi.sqlite') as con:
        con.execute("UPDATE billing_accounts SET subscription_status='canceled',plus_lifetime=0 WHERE user_id=?",(uid,))
    assert client.get('/api/features/multiview').json()['max_panes']==0


def test_preview_only_with_invite_code(tmp_path,monkeypatch):
    monkeypatch.setenv('TUNELY_MULTIVIEW_PRIVATE_PREVIEW','true')
    monkeypatch.delenv('TUNELY_SIGNUP_CODE',raising=False)
    no_invite=app_client(tmp_path/'noinvite')
    assert login(no_invite,'trial1@example.org').json()['max_panes']==0
    monkeypatch.setenv('TUNELY_SIGNUP_CODE','my-private-staging-code')
    invited=app_client(tmp_path/'invited')
    r=invited.post('/api/auth/register',json={'email':'private@example.org','password':'StrongPassword_2026!','invite_code':'my-private-staging-code'})
    assert r.status_code==201
    result=invited.get('/api/features/multiview').json()
    assert result['max_panes']==4 and result['preview'] is True and result['feature_live'] is False


def test_source_contains_multiview_and_no_bundled_media(tmp_path):
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'site/watch.html').read_text()
    js=(root/'site/multiview.js').read_text()
    assert 'id="multiviewBtn"' in html and 'id="mvGrid"' in html
    assert 'multiview.js' in html and 'hls.js' in html
    assert 'getAccess' in js and 'max_panes' in js and 'stopAll' not in js
    assert 'stream proxy' not in js.lower() and 'window.Hls' in js
