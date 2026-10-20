from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'site'
def test_fullscreen_guide_is_loaded_from_live_tv():
    html=(ROOT/'watch.html').read_text()
    assert 'id="theaterGuide"' in html and 'id="gfViewport"' in html
    assert 'guide-focus-v093.css' in html and 'guide-focus-v093.js' in html
    assert 'id="guideTopButton"' in html and 'id="theaterGuideBtn"' in html
    assert 'id="gfWatch"' in html and 'id="gfSearch"' in html

def test_guide_reuses_existing_xmltv_and_playlist_no_bundled_sources():
    js=(ROOT/'guide-focus-v093.js').read_text()
    watch=(ROOT/'watch.js').read_text()
    assert 'window.TunelyGuideBridge' in watch
    assert "getNowNext" in watch
    assert "$('guideGrid').querySelector" in js
    assert "document.querySelector('.quick[data-filter" in js
    assert 'getProgramsLoaded()' in js
    assert 'test-streams.mux.dev' not in js

def test_guide_is_viewport_filling_and_scroll_internal():
    css=(ROOT/'guide-focus-v093.css').read_text()
    assert 'position:fixed;inset:0' in css
    assert 'height:100dvh' in css
    assert '.gf-viewport .epg-scroll{height:100%;max-height:100%;overflow:auto' in css
    assert '.gf-viewport .epg-ruler{position:sticky;top:0' in css
