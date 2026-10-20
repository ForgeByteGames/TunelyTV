from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]

def test_pricing_page_describes_all_plans_and_prices():
    page = BeautifulSoup((ROOT / 'site/index.html').read_text(), 'html.parser')
    cards = page.select('[data-plan-card]')
    assert [x['data-plan-card'] for x in cards] == ['free', 'plus', 'premium', 'family']
    assert ['$0', '$19.99', '$4.99', '$7.99'] == [card.select_one('h3').get_text(' ',strip=True).split(' ')[0] for card in cards]
    assert len(page.select('.feature-table tbody tr')) >= 8
    assert len(page.select('[data-billing-checkout]')) == 3


def test_planned_features_marked_and_not_included_in_free_plus():
    page = BeautifulSoup((ROOT / 'site/index.html').read_text(), 'html.parser')
    cards = {x['data-plan-card']:x.get_text(' ',strip=True).lower() for x in page.select('[data-plan-card]')}
    for plan in ['plus','premium','family']:
        assert 'proposed' in cards[plan]
    assert 'not included' in cards['free']
    assert 'dvr recording' in cards['plus'] and 'tunely home windows companion' in cards['plus']
    assert 'dvr recording through tunely home' in cards['premium']
    assert 'dvr recording through tunely home' in cards['family']
    assert 'no plan includes tv channels' in page.select_one('.feature-compare-footnote').get_text(' ',strip=True).lower()
