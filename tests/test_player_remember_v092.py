from test_api import setup, register, playlist


def test_last_selected_playlist_is_account_scoped_and_survives_login(tmp_path):
    first = setup(tmp_path)
    h = register(first)
    a = playlist(first,h,name='Demo One')
    b = playlist(first,h,name='Demo Two')
    assert first.get('/api/player/preferences').json()['playlist_id'] is None
    assert first.patch('/api/player/preferences', json={'playlist_id':b}).status_code == 403
    saved = first.patch('/api/player/preferences',headers=h,json={'playlist_id':b})
    assert saved.status_code==200 and saved.json()['playlist_id']==b
    assert first.get('/api/player/preferences').json()['playlist_id']==b
    second = setup(tmp_path)
    hs = register(second,'different@example.com')
    assert second.get('/api/player/preferences').json()['playlist_id'] is None
    assert second.patch('/api/player/preferences', headers=hs,json={'playlist_id':b}).status_code==404
    assert second.get('/api/player/preferences').json()['playlist_id'] is None
    first.delete('/api/playlists/'+b,headers=h)
    assert first.get('/api/player/preferences').json()['playlist_id'] is None
    assert first.patch('/api/player/preferences',headers=h,json={'playlist_id':a}).status_code==200
    relog=setup(tmp_path)
    r=relog.post('/api/auth/login',json={'email':'first@example.com','password':'myStrongPassw0rd!'})
    assert r.status_code==200
    assert relog.get('/api/player/preferences').json()['playlist_id']==a

def test_watch_restores_playlist_without_autoplay():
    from pathlib import Path
    js=(Path(__file__).resolve().parents[1]/'site/watch.js').read_text()
    assert 'await loadSource(preferred)' in js
    assert "'/api/player/preferences'" in js
    assert "sourcePick.value=preferred" in js
    assert 'video.play()' not in js.split('async function init(){')[1].split('window.TunelyMultiBridge')[0]
