"""Test server-authoritative licensing, expiration, one-time trial and owner setup."""
import sqlite3

from fastapi.testclient import TestClient
from server import create_app
from licensing import award_verified_plus


def client(tmp_path):
    return TestClient(create_app(tmp_path/'licenses.sqlite',tmp_path/'key'))


def register(c, email='user@example.org'):
    r=c.post('/api/auth/register',json={'email':email,'password':'test-STRONG-PASSWORD-2026!'})
    assert r.status_code==201,r.text
    return {'X-CSRF-Token':r.json()['csrf_token']}


def saved(c, header):
    r=c.post('/api/playlists',headers=header,json={
        'name':'Authorized video','type':'m3u_file','filename':'test.m3u',
        'content':'#EXTM3U\n#EXTINF:-1,Example\nhttps://example.org/stream.m3u8\n'})
    assert r.status_code==201, r.text
    return r.json()['id']


def test_trial_activation_expiration_no_autocharge_and_saved_playlist(tmp_path, monkeypatch):
    c=client(tmp_path)
    h=register(c)
    pid=saved(c,h)
    before=c.get('/api/license/me').json()
    assert before['plan']=='free' and before['web_playback'] is False and before['tv_slots']==1
    assert before['trial_status']=='eligible'
    assert c.get('/api/playlists/'+pid+'/playable').status_code==403
    assert c.post('/api/license/trial/start').status_code==403  # CSRF
    active=c.post('/api/license/trial/start',headers=h)
    assert active.status_code==201,active.text
    state=active.json()
    assert state['trial_seconds_remaining']<=604800 and state['trial_seconds_remaining']>604790
    assert state['access_reason']=='trial' and state['plan']=='plus'
    assert state['web_playback'] is True and state['multiview_panes']==2 and state['tv_slots']==2
    assert c.get('/api/playlists/'+pid+'/playable').status_code==200
    assert c.post('/api/license/trial/start',headers=h).status_code==409
    # Simulates > 7 days after activation without a cron or background worker.
    monkeypatch.setattr('licensing.timestamp',lambda: state['trial_ends_at']+1)
    expired=c.get('/api/license/me').json()
    assert expired['trial_status']=='expired' and expired['plan']=='free'
    assert expired['trial_seconds_remaining']==0 and expired['tv_slots']==1
    assert not expired['web_playback'] and expired['owned_plus_majors']==[]
    assert c.get('/api/playlists/'+pid+'/playable').status_code==403
    assert c.get('/api/playlists').json()['playlists'][0]['id']==pid
    assert c.post('/api/license/trial/start',headers=h).status_code==409
    assert c.get('/api/billing/status').json()['payments_live'] is False
    with sqlite3.connect(tmp_path/'licenses.sqlite') as con:
        assert con.execute('SELECT COUNT(*) FROM plus_licenses').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM plus_trials').fetchone()[0]==1


def test_two_accounts_isolated_and_tv_limits(tmp_path):
    a=client(tmp_path); ah=register(a,'a@example.org')
    b=client(tmp_path);bh=register(b,'b@example.org')
    assert a.post('/api/license/trial/start',headers=ah).status_code==201
    assert b.get('/api/license/me').json()['trial_status']=='eligible'
    def device(c,h,name):
        return c.post('/api/devices',headers=h,json={'name':name,'platform':'Android TV',
            'method':'device_id','identifier':'someDevice'+name})
    assert device(a,ah,'1').status_code==201
    assert device(a,ah,'2').status_code==201
    assert device(a,ah,'3').status_code==403
    assert device(b,bh,'1').status_code==201
    assert device(b,bh,'2').status_code==403
    assert a.get('/api/owner/users').status_code==403
    assert b.get('/api/owner/users').status_code==403


def test_purchased_plus_version_survives_trial_and_subscription(tmp_path,monkeypatch):
    c=client(tmp_path);h=register(c)
    c.post('/api/license/trial/start',headers=h)
    with sqlite3.connect(tmp_path/'licenses.sqlite') as con:
        uid=con.execute('SELECT id FROM users').fetchone()[0]
        award_verified_plus(con,uid,'evt_validated_only',at=500)
        con.execute("UPDATE plus_trials SET started_at=1,ends_at=2 WHERE user_id=?", (uid,))
    state=c.get('/api/license/me').json()
    assert state['trial_status']=='expired' and state['owns_current_plus']
    assert state['plan']=='plus' and state['owned_plus_majors']==[1]
    assert state['web_playback']
    # A canceled Premium subscription returns to purchased Plus, not Free.
    with sqlite3.connect(tmp_path/'licenses.sqlite') as con:
        con.execute('''INSERT INTO billing_accounts(user_id,subscription_plan,subscription_status,updated_at)
            VALUES (?,'premium','active',?)''',(uid,100))
    assert c.get('/api/license/me').json()['plan']=='premium'
    with sqlite3.connect(tmp_path/'licenses.sqlite') as con:
        con.execute("UPDATE billing_accounts SET subscription_status='canceled' WHERE user_id=?",(uid,))
    assert c.get('/api/license/me').json()['plan']=='plus'
    # Upgrade across a major version does not silently grant a perpetual license for 2.x.
    monkeypatch.setenv('TUNELY_LICENSE_MAJOR','2')
    assert c.get('/api/license/me').json()['owned_plus_majors']==[1]
    assert c.get('/api/license/me').json()['plan']=='free'  # requires a separate 2.x purchase


def test_owner_bootstrap_security_private_preview_and_read_only_list(tmp_path,monkeypatch):
    monkeypatch.setenv('TUNELY_OWNER_EMAIL','owner@example.org')
    monkeypatch.setenv('TUNELY_ADMIN_SETUP_TOKEN','a-owner-setup-token-of-40-characters-2026')
    monkeypatch.setenv('TUNELY_MULTIVIEW_PRIVATE_PREVIEW','true')
    c=client(tmp_path); h=register(c,'owner@example.org')
    other=client(tmp_path); oh=register(other,'tester@example.org')
    assert c.get('/api/license/me').json()['owner_setup_available']
    assert other.get('/api/license/me').json()['owner_setup_available'] is False
    secret={'setup_token':'a-owner-setup-token-of-40-characters-2026'}
    assert c.post('/api/owner/bootstrap',json=secret).status_code==403
    assert other.post('/api/owner/bootstrap',headers=oh,json=secret).status_code==403
    assert c.post('/api/owner/bootstrap',headers=h,json={'setup_token':'wrong'*6}).status_code==403
    good=c.post('/api/owner/bootstrap',headers=h,json=secret)
    assert good.status_code==200,good.text
    assert c.post('/api/owner/bootstrap',headers=h,json=secret).status_code==409
    assert c.get('/api/features/multiview').json()['max_panes']==4
    assert c.get('/api/features/multiview').json()['preview'] is True
    assert c.get('/api/license/me').json()['plan']=='free'  # not a fake paid purchase
    assert c.get('/api/license/me').json()['access_reason']=='owner_preview'
    assert other.get('/api/features/multiview').json()['max_panes']==0
    assert other.get('/api/owner/users').status_code==403
    assert len(c.get('/api/owner/users').json()['users'])==2
    assert c.get('/api/owner/audit').json()['events'][0]['action']=='owner_bootstrap'
    # Revoking the environment token does not revoke persisted owner access.
    monkeypatch.delenv('TUNELY_ADMIN_SETUP_TOKEN')
    another=client(tmp_path)
    login=another.post('/api/auth/login',json={'email':'owner@example.org','password':'test-STRONG-PASSWORD-2026!'})
    assert login.status_code==200
    assert another.get('/api/license/me').json()['owner']


def test_trial_cannot_be_extended_by_restarting_server(tmp_path):
    c=client(tmp_path);h=register(c)
    initial=c.post('/api/license/trial/start',headers=h).json()['trial_ends_at']
    fresh=client(tmp_path)
    r=fresh.post('/api/auth/login',json={'email':'user@example.org','password':'test-STRONG-PASSWORD-2026!'})
    assert r.status_code==200
    assert fresh.get('/api/license/me').json()['trial_ends_at']==initial
    assert fresh.post('/api/license/trial/start',headers={'X-CSRF-Token':r.json()['csrf_token']}).status_code==409


def test_signed_test_payment_full_refund_and_idempotency(tmp_path,monkeypatch):
    import billing
    from test_api import signed_webhook
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_fake')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_test_secret')
    monkeypatch.setenv('STRIPE_PRICE_PLUS','price_plus_test')
    monkeypatch.setenv('STRIPE_PRICE_PREMIUM','price_premium_test')
    monkeypatch.setenv('STRIPE_PRICE_FAMILY','price_family_test')
    monkeypatch.setenv('TUNELY_ENABLE_STRIPE_TEST','true')
    monkeypatch.setenv('TUNELY_PUBLIC_URL','https://example.up.railway.app')
    c=client(tmp_path);h=register(c)
    with sqlite3.connect(tmp_path/'licenses.sqlite') as con:
        uid=con.execute('SELECT id FROM users').fetchone()[0]
    original={'id':'cs_test_accepted','customer':'cus_approved','client_reference_id':uid,
      'mode':'payment','metadata':{'plan':'plus','user_id':uid,'license_major':'1'},
      'amount_total':1999,'currency':'usd','payment_status':'paid','payment_intent':'pi_paid_123'}
    r=signed_webhook(c,'checkout.session.completed','evt_paid_123',original)
    assert r.status_code==200,r.text
    assert c.get('/api/license/me').json()['owned_plus_majors']==[1]
    assert signed_webhook(c,'checkout.session.completed','evt_paid_123',original).json()['duplicate'] is True
    # A partial refund doesn't remove the perpetual license.
    partial={'payment_intent':'pi_paid_123','amount':1999,'amount_refunded':500}
    assert signed_webhook(c,'charge.refunded','evt_partial_123',partial).status_code==200
    assert c.get('/api/license/me').json()['owns_current_plus']
    # A fully refunded purchase loses that grant, but never deletes the account.
    full={'payment_intent':'pi_paid_123','amount':1999,'amount_refunded':1999}
    assert signed_webhook(c,'charge.refunded','evt_full_123',full).status_code==200
    assert not c.get('/api/license/me').json()['owns_current_plus']
    assert c.get('/api/license/me').json()['plan']=='free'
    assert len(c.get('/api/playlists').json()['playlists'])==0
    assert signed_webhook(c,'charge.refunded','evt_full_123',full).json()['duplicate'] is True
    assert c.get('/api/owner/users').status_code==403


def test_stale_paid_subscription_does_not_stay_active(tmp_path):
    c=client(tmp_path); register(c)
    with sqlite3.connect(tmp_path/'licenses.sqlite') as con:
        uid=con.execute('SELECT id FROM users').fetchone()[0]
        con.execute('''INSERT INTO billing_accounts(user_id,subscription_plan,subscription_status,current_period_end,updated_at)
          VALUES (?,'family','active',1,2)''',(uid,))
    state=c.get('/api/license/me').json()
    assert state['plan']=='free' and state['multiview_panes']==0


def test_deployment_includes_licensing_module():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    docker=(root/'Dockerfile').read_text()
    assert 'licensing.py' in docker
    assert (root/'site/license-v096.js').exists()
    assert (root/'site/license-v096.css').exists()
    assert (root/'V0.9.6-LICENSE-AND-ENTITLEMENTS.md').exists()
