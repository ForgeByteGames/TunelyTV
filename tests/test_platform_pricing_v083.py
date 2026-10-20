from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]

def test_plan_copy_platform_neutral_and_honest():
    soup=BeautifulSoup((ROOT/'site/index.html').read_text(encoding='utf-8'),'html.parser')
    cards=soup.select('[data-plan-card]')
    assert len(cards)==4
    for card in cards:
        text=card.get_text(' ',strip=True).lower()
        assert 'browser' not in text
        assert 'web player' not in text
        assert 'web-only subscription' not in text
        assert 'browser-only subscription' not in text
    header=soup.select_one('.plan-intro').get_text(' ',strip=True).lower()
    assert 'supported apps and devices' in header
    footnote=soup.select_one('.feature-compare-footnote').get_text(' ',strip=True).lower()
    assert 'native tv applications are not yet released' in footnote
    assert 'browser playback' in footnote
    assert 'no plan includes tv channels' in footnote
    assert 'live tv playback (compatible streams)' in soup.select_one('.feature-table').get_text(' ',strip=True).lower()
