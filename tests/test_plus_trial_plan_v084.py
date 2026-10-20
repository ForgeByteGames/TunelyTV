from pathlib import Path
from bs4 import BeautifulSoup
ROOT = Path(__file__).resolve().parents[1]

def test_trial_card_and_disclosures():
    soup = BeautifulSoup((ROOT/'site/index.html').read_text(),'html.parser')
    callout=soup.select_one('.trial-callout')
    assert callout
    label=callout.get_text(' ',strip=True).lower()
    for phrase in ('7 days', 'no credit card', 'no automatic charges', 'checking your trial eligibility'):
        assert phrase in label
    assert callout.select_one('button#startPlusTrial')

def test_free_is_tv_only_and_plus_is_paid_web():
    soup=BeautifulSoup((ROOT/'site/index.html').read_text(),'html.parser')
    free=soup.select_one('[data-plan-card="free"]').get_text(' ',strip=True).lower()
    assert '1 registered tv' in free
    assert 'phone, tablet and web playback' in free
    table=soup.select_one('.feature-table').get_text(' ',strip=True).lower()
    assert 'phone, tablet and web playback not included included included included' in table
    assert 'eligible once' in table

def test_entitlement_spec_not_fake_implementation():
    p=(ROOT/'PLUS-TRIAL-AND-ENTITLEMENTS.md').read_text().lower()
    for phrase in ['server enforcement','trial_started_at','trial_ends_at','free tier']:
        assert phrase in p
