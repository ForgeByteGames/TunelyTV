"""Logo lookups are exact, rights-gated, isolated and never proxy streams."""
from pathlib import Path
from unittest.mock import patch
from test_api import setup, register, enable_web
from logo_catalog import _build_indexes, normalize, safe_image_url

ROOT=Path(__file__).resolve().parents[1]


def sample_indexes():
    channels=[
        {'id':'3ABNEnglish.us','name':'3ABN English','alt_names':['Three Angels Broadcasting English']},
        {'id':'NewYorkNews.us','name':'Local News','alt_names':[]},
        {'id':'BostonNews.us','name':'Local News','alt_names':[]},
    ]
    logos=[
        {'channel':'3ABNEnglish.us','in_use':True,'feed':None,'url':'https://example.com/3abn.png','format':'PNG'},
        {'channel':'NewYorkNews.us','in_use':True,'url':'https://example.com/ny.png','format':'PNG'},
        {'channel':'BostonNews.us','in_use':True,'url':'https://example.com/boston.png','format':'PNG'},
        {'channel':'3ABNEnglish.us','in_use':False,'url':'https://example.com/old.png','format':'PNG'}]
    return _build_indexes(channels,logos)


def test_exact_matching_and_ambiguous_names():
    ids,names=sample_indexes()
    assert ids['3abnenglish.us']=='https://example.com/3abn.png'
    assert names[normalize('3ABN English')]=='https://example.com/3abn.png'
    assert normalize('Local News') not in names
    assert normalize('3ABN English 1080p') not in names


def test_url_sanitization():
    assert safe_image_url('https://example.com/logo.png')
    for url in ('http://example.com/a.png','javascript:alert(1)',
                'https://x:y@example.com/a.png','https://127.0.0.1:8888/a.png'):
        assert not safe_image_url(url)


def test_rights_gate_default(monkeypatch,tmp_path):
    monkeypatch.delenv('TUNELY_LOGO_AUTOMATCH_ENABLED',raising=False)
    monkeypatch.delenv('TUNELY_EXTERNAL_LOGOS_RIGHTS_CONFIRMED',raising=False)
    cli=setup(tmp_path)
    key=register(cli)
    assert cli.get('/api/channel-logos/config').json()['enabled'] is False
    response=cli.post('/api/channel-logos/match',headers=key,json={'channels':[{'name':'3ABN English'}]})
    assert response.status_code==403


def test_enabled_matching_without_live_web(monkeypatch,tmp_path):
    monkeypatch.setenv('TUNELY_LOGO_AUTOMATCH_ENABLED','true')
    monkeypatch.setenv('TUNELY_EXTERNAL_LOGOS_RIGHTS_CONFIRMED','true')
    cli=setup(tmp_path)
    key=register(cli)
    enable_web(cli,key)
    ids,names=sample_indexes()
    with patch('logo_catalog._indexes',return_value=(ids,names)):
        response=cli.post('/api/channel-logos/match',headers=key,json={'channels':[
            {'name':'3ABN English','tvgId':'3ABNEnglish.us'},
            {'name':'3ABN English'},
            {'name':'Local News'},
            {'name':'Unmatched Channel'},
        ]})
    assert response.status_code==200,response.text
    data=response.json()
    assert data['queried']==4
    assert data['unmatched']==2
    assert [m['matched_by'] for m in data['matches']]==['tvg-id','exact-name']
    assert 'https://example.com/3abn.png' == data['matches'][0]['url']


def test_frontend_does_not_send_stream_urls():
    js=(ROOT/'site/logo-match-v098.js').read_text()
    html=(ROOT/'site/watch.html').read_text()
    player=(ROOT/'site/watch.js').read_text()
    assert 'api.matchMissingLogos(items.slice' in js
    assert 'name:ch.name,tvgId:ch.tvgId' in js
    assert 'streamUrl:' not in js
    assert 'id="gfLogoLookup"' in html
    assert "window.dispatchEvent(new CustomEvent('tunely:playlist-loaded'))" in player
    assert 'safeLogo(ch.externalLogo)' in player
