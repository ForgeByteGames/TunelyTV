import sqlite3

from fastapi.testclient import TestClient
from server import create_app


def setup(tmp_path):
    return TestClient(create_app(tmp_path/'api.sqlite',tmp_path/'vault.key'))


def register(client,email='first@example.com'):
    r=client.post('/api/auth/register',json={'email':email,'password':'myStrongPassw0rd!'})
    assert r.status_code==201,r.text
    return {'X-CSRF-Token':r.json()['csrf_token']}


def playlist(client,h,name='Source A',**kw):
    config={'name':name,'type':'m3u_url','url':'https://secure.example.org/private.m3u?token=S3CRET'}
    config.update(kw)
    r=client.post('/api/playlists',headers=h,json=config)
    assert r.status_code==201,r.text
    return r.json()['id']


def test_end_to_end_pairing_assignment_change_and_revocation(tmp_path):
    client=setup(tmp_path)
    headers=register(client)
    p=playlist(client,headers)
    raw=(tmp_path/'api.sqlite').read_bytes()
    assert b'S3CRET' not in raw
    assert b'secure.example.org' not in raw
    assert 'S3CRET' not in client.get('/api/playlists').text
    en=client.post('/api/device/enroll',json={'name':'Living Room TV','platform':'Android TV'})
    assert en.status_code==201,en.text
    code=en.json()['pairing_code']
    token=en.json()['device_token']
    dh={'Authorization':'Bearer '+token}
    assert client.get('/api/device/sync',headers=dh).json()['status']=='pending'
    claim=client.post('/api/pairings/claim',headers=headers,json={'code':code,'playlist_id':p})
    assert claim.status_code==200,claim.text
    d=claim.json()['device']
    assert d['paired'] is True
    sync=client.get('/api/device/sync',headers=dh).json()
    assert sync['playlist']['url'].endswith('token=S3CRET')
    assert sync['playlist']['name']=='Source A'
    revision=sync['revision']
    unchanged=client.get('/api/device/sync?since='+str(revision),headers=dh).json()
    assert unchanged['changed'] is False
    clear=client.patch('/api/devices/'+d['id']+'/playlist',headers=headers,json={'playlist_id':None})
    assert clear.status_code==200,clear.text
    assert clear.json()['revision']>revision
    sync=client.get('/api/device/sync?since='+str(revision),headers=dh).json()
    assert sync['playlist'] is None and sync['changed'] is True
    client.delete('/api/devices/'+d['id'],headers=headers)
    assert client.get('/api/device/sync',headers=dh).status_code==401


def test_manual_profile_pairing_and_owner_isolation(tmp_path):
    c1=setup(tmp_path)
    a1=register(c1)
    pid=playlist(c1,a1)
    m=c1.post('/api/devices',headers=a1,json={'name':'Hallway TV','platform':'Smart TV','method':'mac',
                        'identifier':'AA:BB:CC:DD:EE:FF','playlist_id':pid})
    assert m.status_code==201,m.text
    assert m.json()['identifier_mask'].startswith('AA:BB')
    manual_id=m.json()['id']
    assert not m.json()['paired']
    c2=setup(tmp_path)
    a2=register(c2,'second@example.com')
    assert c2.get('/api/playlists').json()['playlists']==[]
    assert c2.get('/api/devices').json()['devices']==[]
    assert c2.delete('/api/playlists/'+pid,headers=a2).status_code==404
    assert c2.patch('/api/devices/'+manual_id+'/playlist',headers=a2,json={'playlist_id':pid}).status_code==404
    tokenresp=c1.post('/api/device/enroll',json={'name':'Temporary TV','platform':'Simulator'}).json()
    link=c1.post('/api/pairings/claim',headers=a1,json={'code':tokenresp['pairing_code'], 'profile_id':manual_id})
    assert link.status_code==200,link.text
    assert link.json()['device']['id']==manual_id
    assert link.json()['device']['paired']
    assert c1.get('/api/device/sync',headers={'Authorization':'Bearer '+tokenresp['device_token']}).json()['playlist']['id']==pid
    assert c1.post('/api/pairings/claim',headers=a1,json={'code':tokenresp['pairing_code']}).status_code==400
    assert c1.get('/api/devices').json()['devices'][0]['id']==manual_id


def test_csrf_expiry_validation_and_passwords(tmp_path):
    c=setup(tmp_path)
    h=register(c)
    assert c.post('/api/playlists',json={'name':'no csrf','type':'m3u_url','url':'https://ok.example'}).status_code==403
    bad=c.post('/api/playlists',headers=h,json={'name':'bad','type':'m3u_url','url':'file:///etc/passwd'})
    assert bad.status_code==400,bad.text
    bad=c.post('/api/playlists',headers=h,json={'name':'bad','type':'m3u_url','url':'https://user:pass@example.com/playlist'})
    assert bad.status_code==400
    bad=c.post('/api/playlists',headers=h,json={'name':'bad','type':'m3u_file','filename':'my.m3u','content':'garbage'})
    assert bad.status_code==400
    p=playlist(c,h,name='Local M3U',type='m3u_file',filename='channels.m3u',content='#EXTM3U\n#EXTINF:-1,Demo\nhttps://example.net/media')
    assert p
    q=playlist(c,h,name='Provider profile',type='xtream',server='https://provider.example',username='u',password='p')
    assert q
    en=c.post('/api/device/enroll',json={'name':'TV','platform':'Linux'}).json()
    with sqlite3.connect(tmp_path/'api.sqlite') as conn:
        conn.execute('UPDATE devices SET code_expires=1 WHERE code_hash IS NOT NULL')
    assert c.post('/api/pairings/claim',headers=h,json={'code':en['pairing_code']}).status_code==400
    login=c.post('/api/auth/login',json={'email':'first@example.com','password':'wrong-password'})
    assert login.status_code==401
    assert c.post('/api/auth/logout',headers=h).status_code==200
    assert c.get('/api/playlists').status_code==401
    login=c.post('/api/auth/login',json={'email':'first@example.com','password':'myStrongPassw0rd!'})
    assert login.status_code==200
    assert 'csrf_token' in login.json()


def test_owner_scoped_web_playback_config_and_parsing(tmp_path):
    a=setup(tmp_path)
    h=register(a)
    uploaded=playlist(a,h,name='Own uploaded list', type='m3u_file', filename='own.m3u',
       content='#EXTM3U\n#EXTINF:-1 tvg-id="a",Licensed Demo\nhttps://licensed.example/live/a.m3u8\n#EXTINF:-1,Skip local file\nfile:///etc/passwd\n#EXTINF:-1,Second stream\nhttps://licensed.example/live/b.m3u8\n')
    r=a.get('/api/playlists/'+uploaded+'/playable')
    assert r.status_code==200,r.text
    j=r.json()
    assert j['type']=='m3u_file' and len(j['channels'])==2
    assert j['channels'][0]['name']=='Licensed Demo'
    assert j['channels'][0]['url']=='https://licensed.example/live/a.m3u8'
    assert 'file://' not in r.text
    direct=playlist(a,h,name='Direct',url='https://secure.example/live.m3u8?secret=token123')
    resp=a.get('/api/playlists/'+direct+'/playable')
    assert resp.status_code==200 and 'token123' in resp.text
    other=setup(tmp_path)
    register(other,'outsider@example.com')
    assert other.get('/api/playlists/'+uploaded+'/playable').status_code==404
    assert other.get('/api/playlists/'+direct+'/playable').status_code==404
    anonymous=setup(tmp_path)
    assert anonymous.get('/api/playlists/'+uploaded+'/playable').status_code==401


def test_invite_only_signup_in_staging(tmp_path,monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('TUNELY_ENV','production')
    monkeypatch.setenv('TUNELY_SIGNUP_CODE','private-testing-code')
    monkeypatch.setenv('TUNELY_FERNET_KEY',Fernet.generate_key().decode())
    c=TestClient(create_app(tmp_path/'stage.sqlite'),base_url='https://stream.tunelytv.com')
    details={'email':'stage@example.com','password':'randomPASSWORD123!'}
    assert c.post('/api/auth/register',json=details).status_code==403
    assert c.post('/api/auth/register',json={**details,'invite_code':'incorrect'}).status_code==403
    response=c.post('/api/auth/register',json={**details,'invite_code':'private-testing-code'})
    assert response.status_code==201,response.text
    assert 'Secure' in response.headers.get('set-cookie','')
    assert c.get('/api/me').status_code==200
    assert c.get('/api/docs').status_code==404
    assert c.get('/watch').status_code==200


def test_xmltv_matching_fields_preserved_from_uploaded_m3u(tmp_path):
    client=setup(tmp_path)
    headers=register(client)
    uploaded=playlist(client,headers,name='Curated playlist',type='m3u_file',filename='own.m3u',
        content='#EXTM3U\n#EXTINF:-1 tvg-id="my.demo" group-title="Local, News",Station One\nhttps://licensed.example/live/a.m3u8\n'
                '#EXTINF:-1 group-title="Sports",Station Two\nhttps://licensed.example/live/b.m3u8\n')
    resp=client.get('/api/playlists/'+uploaded+'/playable')
    assert resp.status_code==200, resp.text
    entries=resp.json()['channels']
    assert len(entries)==2
    assert entries[0]['name']=='Station One'
    assert entries[0]['group']=='Local, News'
    assert entries[0]['tvgId']=='my.demo'
    assert entries[1]['group']=='Sports'
    assert entries[1]['tvgId']==''


def test_v07_cloud_preferences_owner_scope_persistence_and_clear(tmp_path):
    c1 = setup(tmp_path)
    h1 = register(c1)
    playlist_id = playlist(c1, h1)
    base = '/api/playlists/' + playlist_id + '/preferences'
    fav = '/api/playlists/' + playlist_id + '/favorites'
    recent = '/api/playlists/' + playlist_id + '/recent'
    key = 'id:abc123-def456'
    assert c1.get(base).json() == {'favorites': [], 'recent': []}
    assert c1.post(fav, json={'channel_key': key, 'favorite': True}).status_code == 403
    assert c1.post(fav, headers=h1, json={'channel_key': key, 'favorite': True}).status_code == 200
    assert c1.post(fav, headers=h1, json={'channel_key': key, 'favorite': True}).status_code == 200
    assert c1.post(recent, headers=h1, json={'channel_key': key}).status_code == 200
    assert c1.post(recent, headers=h1, json={'channel_key': 'n:xyz123-abc999'}).status_code == 200
    assert c1.get(base).json()['favorites'] == [key]
    assert set(c1.get(base).json()['recent']) == {key, 'n:xyz123-abc999'}
    assert c1.post(fav, headers=h1, json={'channel_key': 'https://secret.net?a=1'}).status_code == 422

    c2 = setup(tmp_path)
    h2 = register(c2, 'private@example.net')
    assert c2.get(base).status_code == 404
    assert c2.post(fav, headers=h2, json={'channel_key': key}).status_code == 404
    assert c2.delete(base, headers=h2).status_code == 404
    assert c2.get('/api/playlists/'+playlist_id+'/playable').status_code == 404

    c3 = setup(tmp_path)
    login = c3.post('/api/auth/login', json={'email': 'first@example.com','password': 'myStrongPassw0rd!'})
    assert login.status_code == 200
    assert c3.get(base).json()['favorites'] == [key]
    assert c3.delete(base, headers={'X-CSRF-Token': login.json()['csrf_token']}).status_code == 200
    assert c1.get(base).json() == {'favorites': [], 'recent': []}
    assert c1.post(fav, headers=h1, json={'channel_key': key}).status_code == 200
    assert c1.delete('/api/playlists/'+playlist_id, headers=h1).status_code == 200
    with sqlite3.connect(tmp_path/'api.sqlite') as con:
        assert con.execute('SELECT COUNT(*) FROM favorite_channels').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM recent_channels').fetchone()[0] == 0


def test_v07_encrypted_epg_guide_url_and_no_remote_fetch(tmp_path, monkeypatch):
    c = setup(tmp_path)
    h = register(c)
    playlist_id = playlist(c, h)
    secret_url = 'https://licensed.example/epg.xml?private-token=THIS_MUST_NOT_LEAK'
    route = '/api/playlists/' + playlist_id + '/guide'
    assert c.patch(route, json={'url': secret_url}).status_code == 403
    assert c.patch(route, headers=h, json={'url': secret_url}).status_code == 200
    assert c.get('/api/playlists/' + playlist_id + '/playable').json()['epg_url'] == secret_url
    assert secret_url.encode() not in (tmp_path/'api.sqlite').read_bytes()
    assert b'THIS_MUST_NOT_LEAK' not in (tmp_path/'api.sqlite').read_bytes()
    assert 'THIS_MUST_NOT_LEAK' not in c.get('/api/playlists').text
    assert c.patch(route, headers=h, json={'url': 'file:///etc/passwd'}).status_code == 400
    assert c.patch(route, headers=h, json={'url': None}).status_code == 200
    assert c.get('/api/playlists/' + playlist_id + '/playable').json()['epg_url'] is None
    another=setup(tmp_path)
    otherheaders=register(another,'another@example.org')
    assert another.patch(route, headers=otherheaders, json={'url': secret_url}).status_code == 404


def test_v08_default_billing_is_safe_and_prices_correct(tmp_path):
    c = setup(tmp_path)
    h = register(c)
    status = c.get('/api/billing/status')
    assert status.status_code == 200
    j = status.json()
    assert j['plan'] == 'free' and j['stripe_test_enabled'] is False
    assert j['payments_live'] is False
    assert {p['id']:p['price_cents'] for p in j['plans']} == {
        'free':0,'plus':1999,'premium':499,'family':799}
    assert c.post('/api/billing/checkout',headers=h,json={'plan':'plus'}).status_code == 503
    assert c.post('/api/billing/portal',headers=h).status_code == 503
    assert c.post('/api/billing/checkout',json={'plan':'premium'}).status_code == 403
    assert c.get('/api/billing/status').status_code == 200
    c.post('/api/auth/logout',headers=h)
    assert c.get('/api/billing/status').status_code == 401


def stripe_testing_setup(tmp_path, monkeypatch):
    monkeypatch.setenv('TUNELY_ENABLE_STRIPE_TEST','true')
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_test_placeholder_only')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_test_secret')
    monkeypatch.setenv('STRIPE_PRICE_PLUS','price_plus_test')
    monkeypatch.setenv('STRIPE_PRICE_PREMIUM','price_premium_test')
    monkeypatch.setenv('STRIPE_PRICE_FAMILY','price_family_test')
    monkeypatch.setenv('TUNELY_PUBLIC_URL','https://stream.tunelytv.com')
    return setup(tmp_path)


def signed_webhook(client, kind, event_id, obj, timestamp=None):
    import time, json, hmac, hashlib
    payload = json.dumps({'id':event_id,'type':kind,'data':{'object':obj}}).encode()
    ts = timestamp if timestamp is not None else int(time.time())
    signature = hmac.new(b'whsec_test_secret',str(ts).encode()+b'.'+payload,hashlib.sha256).hexdigest()
    return client.post('/api/billing/webhook',content=payload,
            headers={'stripe-signature':f't={ts},v1={signature}','content-type':'application/json'})


def test_v08_checkout_webhooks_entitlements_and_isolation(tmp_path, monkeypatch):
    import billing
    c = stripe_testing_setup(tmp_path,monkeypatch)
    h = register(c)
    with sqlite3.connect(tmp_path/'api.sqlite') as con:
        u1=con.execute('SELECT id FROM users WHERE email=?',('first@example.com',)).fetchone()[0]
    captured=[]
    def fake_stripe(method,path,secret,fields=None):
        captured.append((method,path,fields))
        if method == 'GET':
            plan = path.split('price_',1)[1].split('_test')[0]
            amounts={'plus':1999,'premium':499,'family':799}
            return {'id':'price_'+plan+'_test','active':True,'currency':'usd','unit_amount':amounts[plan],
                    'recurring': {'interval':'month'} if plan!='plus' else None}
        if path == '/v1/checkout/sessions':
            return {'url':'https://checkout.stripe.com/c/pay/test_example'}
        return {'url':'https://billing.stripe.com/p/session_test'}
    monkeypatch.setattr(billing,'stripe_http',fake_stripe)
    checkout=c.post('/api/billing/checkout',headers=h,json={'plan':'premium'})
    assert checkout.status_code==200, checkout.text
    assert checkout.json()['test_mode'] is True
    assert captured[-1][2]['line_items[0][price]']=='price_premium_test'
    assert captured[-1][2]['client_reference_id']==u1
    assert c.get('/api/billing/status').json()['plan']=='free'  # redirect is not proof of payment
    assert c.post('/api/billing/webhook',content=b'{}',headers={'stripe-signature':'t=1,v1=bad'}).status_code==400
    sub={'id':'sub_test_123','customer':'cus_test_abc','status':'active',
        'metadata':{'user_id':u1,'plan':'premium'},
        'items':{'data':[{'price':{'id':'price_premium_test'}}]},
        'current_period_end':2000000000,'cancel_at_period_end':False}
    ok=signed_webhook(c,'customer.subscription.created','evt_test_1',sub)
    assert ok.status_code==200,ok.text
    assert c.get('/api/billing/status').json()['plan']=='premium'
    assert signed_webhook(c,'customer.subscription.created','evt_test_1',sub).json()['duplicate'] is True
    assert c.post('/api/billing/portal',headers=h).status_code == 200
    # No unauthorized cross-account visibility.
    c2=setup(tmp_path)
    register(c2,'second@example.com')
    assert c2.get('/api/billing/status').json()['plan']=='free'
    canceled={**sub,'status':'canceled'}
    assert signed_webhook(c,'customer.subscription.deleted','evt_test_2',canceled).status_code==200
    assert c.get('/api/billing/status').json()['plan']=='free'
    paid={'customer':'cus_test_abc','client_reference_id':u1,'mode':'payment',
          'metadata':{'user_id':u1,'plan':'plus'},'amount_total':1999,'currency':'usd','payment_status':'paid'}
    assert signed_webhook(c,'checkout.session.completed','evt_test_3',paid).status_code==200
    assert c.get('/api/billing/status').json()['plan']=='plus'
    assert c.post('/api/billing/checkout',headers=h,json={'plan':'plus'}).status_code==409
    wrong={**paid,'amount_total':99}
    signed_webhook(c,'checkout.session.completed','evt_test_4',wrong)
    assert c.get('/api/billing/status').json()['plus_lifetime'] is True


def test_v08_rejects_stripe_misconfiguration_and_fake_webhooks(tmp_path,monkeypatch):
    import time
    c=stripe_testing_setup(tmp_path,monkeypatch)
    h=register(c)
    with sqlite3.connect(tmp_path/'api.sqlite') as con:
        u=con.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
    assert signed_webhook(c,'customer.subscription.updated','evt_fake_0',{},timestamp=int(time.time())-400).status_code==400
    forged={'id':'sub_false','customer':'cus_false','status':'active','metadata':{'user_id':u,'plan':'family'},
            'items':{'data':[{'price':{'id':'price_unapproved'}}]}}
    assert signed_webhook(c,'customer.subscription.created','evt_approved_1',forged).status_code==200
    assert c.get('/api/billing/status').json()['plan']=='free'
    # A bogus or tampered signature cannot provision a subscription.
    assert c.post('/api/billing/webhook',content=b'{"hey":"there"}',headers={'stripe-signature':'t=9999999999999,v1=00'}).status_code==400
    monkeypatch.setenv('STRIPE_SECRET_KEY','sk_live_not_allowed')
    forbidden=setup(tmp_path)
    login=forbidden.post('/api/auth/login',json={'email':'first@example.com','password':'myStrongPassw0rd!'})
    fh={'X-CSRF-Token':login.json()['csrf_token']}
    assert forbidden.get('/api/billing/status').json()['stripe_test_enabled'] is False
    assert forbidden.post('/api/billing/checkout',headers=fh,json={'plan':'family'}).status_code == 503
