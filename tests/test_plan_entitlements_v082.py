from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]

def matrix():
    soup=BeautifulSoup((ROOT/'site/index.html').read_text(), 'html.parser')
    rows={r.select_one('th').get_text(' ',strip=True):[c.get_text(' ',strip=True) for c in r.select('td')] for r in soup.select('.feature-table tbody tr')}
    return soup, rows

def test_four_requested_feature_rows_are_explicit():
    _,rows=matrix()
    for name in ['DVR recording (via Tunely Home)*','Provider-supported catch-up TV*','Tunely Home Windows companion*','Multi-View split-screen playback*']:
        assert name in rows
    assert rows['DVR recording (via Tunely Home)*']==['Not included','Not included','Planned','Planned']
    assert rows['Tunely Home Windows companion*']==['Not included','Not included','Planned','Planned']
    assert rows['Provider-supported catch-up TV*']==['Not included','Planned','Planned','Planned']
    assert rows['Multi-View split-screen playback*']==['Not included','Private test · 2 panes','Private test · up to 4','Private test · up to 4']

def test_plan_cards_have_truthful_not_included():
    soup,rows=matrix()
    cards={c['data-plan-card']:c.get_text(' ',strip=True).lower() for c in soup.select('[data-plan-card]')}
    assert all('not included' in cards[p] for p in cards)
    assert 'catch-up' in cards['plus'] and '2-screen multi-view' in cards['plus']
    assert 'cloud dvr storage' in cards['premium'] and 'cloud dvr storage' in cards['family']
    assert 'no plan includes tv channels' in soup.select_one('.feature-compare-footnote').get_text(' ',strip=True).lower()
    assert 'private browser-testing prototype' in soup.select_one('.feature-compare-footnote').get_text(' ',strip=True).lower()
    assert rows['Hosted/cloud DVR storage']==['Not included']*4
