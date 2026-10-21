from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_last_channel_uses_existing_recent_channel_history():
    js=(ROOT/'site/watch.js').read_text()
    assert 'restoreRecentChannel(id)' in js
    assert 'state.recent[0]' in js
    assert 'if(sourceId!==state.sourceId||!state.webPermitted||state.current' in js
    assert 'playChannel(last,{automatic:true})' in js
    assert 'video.muted=true' in js

def test_fullscreen_exits_before_opening_theater_guide():
    guide=(ROOT/'site/guide-focus-v093.js').read_text()
    assert 'if(document.fullscreenElement)' in guide
    assert 'document.exitFullscreen()).then(()=>open(auto))' in guide
    assert "guide.hidden=false;" in guide

def test_service_rails_link_to_approved_websites():
    home=(ROOT/'site/home-v095.js').read_text()
    assert "'Prime Video':'https://www.primevideo.com/'" in home
    assert "const selectedService=id==='serviceRail'" in home
    assert 'btn.target=\'_blank\'' in home
    assert 'provider-link' in home
    assert 'Provider buttons open official websites, not verified links to individual titles.' in home

def test_no_fake_direct_title_links_and_no_private_keys_in_docker():
    home=(ROOT/'site/home-v095.js').read_text()
    assert 'window.location="primevideo.com/movie/' not in home
    docker=(ROOT/'Dockerfile').read_text()
    assert 'COPY instance/' not in docker
