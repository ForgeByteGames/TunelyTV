"""0.9.7 guide-video and channel logo regression tests."""
from pathlib import Path
from test_api import setup,register,enable_web

ROOT=Path(__file__).resolve().parents[1]


def test_uploaded_playlist_retains_https_channel_logos(tmp_path):
    cli=setup(tmp_path)
    key=register(cli)
    enable_web(cli,key)
    playlist='''#EXTM3U
#EXTINF:-1 tvg-id="science" tvg-logo="https://media.example.org/logos/science.png" group-title="Education",Science Channel
https://media.example.org/sci.m3u8
#EXTINF:-1 tvg-logo="javascript:alert(1)",Bad Icon
https://media.example.org/a.m3u8
#EXTINF:-1,No Icon
https://media.example.org/b.m3u8
'''
    response=cli.post('/api/playlists',headers=key,json={'name':'My logos','type':'m3u_file','filename':'logos.m3u','content':playlist})
    assert response.status_code==201,response.text
    data=cli.get('/api/playlists/'+response.json()['id']+'/playable').json()
    assert data['channels'][0]['logo']=='https://media.example.org/logos/science.png'
    assert data['channels'][1]['logo']==''
    assert data['channels'][2]['logo']==''
    assert data['channels'][0]['tvgId']=='science'


def test_guide_uses_same_video_element_and_settings_are_reachable():
    html=(ROOT/'site/watch.html').read_text()
    js=(ROOT/'site/guide-preview-v097.js').read_text()
    source=(ROOT/'site/watch.js').read_text()
    assert html.count('id="video"')==1
    assert 'id="gfPreviewSlot"' in html and 'id="gfGuideSettings"' in html
    assert 'slot.append(video)' in js and 'home.insertBefore(video' in js
    assert 'createElement(\'video\')' not in js
    assert "safeLogo(att['tvg-logo'])" in source
    assert 'channelAvatar(ch' in source
    assert 'guideLogos' in source
