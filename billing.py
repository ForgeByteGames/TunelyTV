"""TunelyTV optional Stripe TEST-MODE billing routes.

No Stripe account is required to run the site. This module intentionally rejects
live keys and never awards privileges based on browser redirects. User entitlements
are derived from authenticated, signature-verified Stripe webhooks only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from licensing import account_access, award_verified_plus

PLAN_INFO = {
    'free': {'label': 'Free', 'amount_cents': 0, 'interval': None},
    'plus': {'label': 'Plus One-Time', 'amount_cents': 1999, 'interval': None},
    'premium': {'label': 'Premium', 'amount_cents': 499, 'interval': 'month'},
    'family': {'label': 'Family', 'amount_cents': 799, 'interval': 'month'},
}
PRICE_ENV = {'plus': 'STRIPE_PRICE_PLUS', 'premium': 'STRIPE_PRICE_PREMIUM', 'family': 'STRIPE_PRICE_FAMILY'}
ACTIVE_STATUSES = ('active', 'trialing')


class PlanRequest(BaseModel):
    plan: str


def stripe_http(method: str, path: str, secret: str, fields: dict[str, str] | None = None):
    """Stripe REST client with a fixed hostname (no arbitrary URL fetching)."""
    assert path.startswith('/v1/') and '://' not in path
    encoded = urlencode(fields or {}).encode()
    url = 'https://api.stripe.com' + path
    req = URLRequest(url, data=encoded if method == 'POST' else None,
                     headers={'Authorization': 'Bearer ' + secret,
                              'Content-Type': 'application/x-www-form-urlencoded'}, method=method)
    try:
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read(180_000))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        # No raw provider body or sensitive query values exposed to clients.
        raise HTTPException(502, 'Stripe test service unavailable or payment configuration invalid.') from exc


def verify_webhook(payload: bytes, signature: str, secret: str) -> dict:
    if len(payload) > 512_000 or not signature or not secret:
        raise HTTPException(400, 'Invalid webhook payload.')
    entries = [piece.strip().split('=', 1) for piece in signature.split(',') if '=' in piece]
    timestamp = next((value for k, value in entries if k == 't'), None)
    v1s = [value for k, value in entries if k == 'v1']
    if not timestamp or not timestamp.isdigit() or abs(int(time.time()) - int(timestamp)) > 300 or not v1s:
        raise HTTPException(400, 'Invalid webhook signature.')
    expected = hmac.new(secret.encode(), timestamp.encode() + b'.' + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, value) for value in v1s):
        raise HTTPException(400, 'Invalid webhook signature.')
    try:
        event = json.loads(payload)
        if not isinstance(event, dict) or not isinstance(event.get('type'), str) or not isinstance(event.get('id'), str):
            raise ValueError
        return event
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, 'Invalid webhook event.') from exc


def install_billing(app, db, current_user, csrf_user, fail, throttle, prod: bool) -> None:
    with db() as con:
        con.executescript('''
          CREATE TABLE IF NOT EXISTS billing_accounts (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            stripe_customer_id TEXT UNIQUE,
            stripe_subscription_id TEXT UNIQUE,
            subscription_plan TEXT,
            subscription_status TEXT,
            cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
            current_period_end INTEGER,
            plus_lifetime INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS billing_events (
            event_id TEXT PRIMARY KEY, processed_at INTEGER NOT NULL);
        ''')
    secret = os.environ.get('STRIPE_SECRET_KEY', '')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    origin = os.environ.get('TUNELY_PUBLIC_URL', '').rstrip('/')
    prices = {key: os.environ.get(var, '') for key, var in PRICE_ENV.items()}
    enabled = (os.environ.get('TUNELY_ENABLE_STRIPE_TEST', 'false').lower() == 'true'
               and secret.startswith('sk_test_') and webhook_secret.startswith('whsec_')
               and origin.startswith('https://') and not origin.endswith('/')
               and all(re.fullmatch(r'price_[A-Za-z0-9_-]{4,128}', value) for value in prices.values()))
    # Environment flag cannot enable production-mode payments in this release.
    # A future version needs explicit readiness approval before supporting sk_live_*.
    app.state.stripe_test_enabled = enabled

    def get_billing(con, user_id: str):
        return con.execute('SELECT * FROM billing_accounts WHERE user_id=?', (user_id,)).fetchone()

    def entitlement(row):
        if row and row['subscription_status'] in ACTIVE_STATUSES and row['subscription_plan'] in ('premium', 'family'):
            return row['subscription_plan']
        return 'plus' if row and row['plus_lifetime'] else 'free'

    @app.get('/api/billing/status')
    def billing_status(user=Depends(current_user)):
        with db() as con:
            row = get_billing(con, user['user_id'])
            license_state = account_access(con, user['user_id'])
        plan = license_state['plan']
        return {
            'plan': plan, 'label': PLAN_INFO[plan]['label'],
            'access_reason': license_state['access_reason'],
            'trial_status': license_state['trial_status'],
            'trial_ends_at': license_state['trial_ends_at'],
            'owned_plus_majors': license_state['owned_plus_majors'],
            'current_major': license_state['current_major'],
            'owner_preview': license_state['owner'],
            'plus_lifetime': license_state['owns_current_plus'],
            'subscription_status': row['subscription_status'] if row else None,
            'subscription_plan': row['subscription_plan'] if row else None,
            'cancel_at_period_end': bool(row['cancel_at_period_end']) if row else False,
            'current_period_end': row['current_period_end'] if row else None,
            'can_manage_billing': bool(row and row['stripe_customer_id'] and enabled),
            'stripe_test_enabled': enabled, 'payments_live': False,
            'plans': [{'id': k, 'name': v['label'], 'price_cents': v['amount_cents'],
                       'interval': v['interval']} for k, v in PLAN_INFO.items()],
        }

    def require_test_mode():
        if not enabled:
            fail('Stripe test checkout is not configured. No payments can be taken.', 503)

    def verified_price(price_id, plan):
        # Defense in depth: prevent configuration mistakes from charging the wrong amount.
        obj = stripe_http('GET', '/v1/prices/' + price_id, secret)
        info = PLAN_INFO[plan]
        recurring = obj.get('recurring') or {}
        if (obj.get('id') != price_id or obj.get('active') is not True or
                obj.get('currency') != 'usd' or obj.get('unit_amount') != info['amount_cents'] or
                (recurring.get('interval') if info['interval'] else bool(recurring)) != (info['interval'] if info['interval'] else False)):
            fail('Stripe test Price configuration does not match the approved TunelyTV plan.', 503)

    @app.post('/api/billing/checkout')
    def checkout(inp: PlanRequest, request: Request, user=Depends(csrf_user)):
        throttle(request, 'billing-checkout', 8, 600)
        if inp.plan not in prices:
            fail('Choose Plus, Premium, or Family.')
        require_test_mode()
        with db() as con:
            row = get_billing(con, user['user_id'])
        if inp.plan == 'plus':
            with db() as con:
                if account_access(con,user['user_id'])['owns_current_plus']:
                    fail('Plus One-Time is already owned for this major version.', 409)
        if row and row['subscription_status'] in ACTIVE_STATUSES and row['stripe_subscription_id']:
            fail('You already have an active monthly subscription. Manage changes through the billing portal.', 409)
        price_id = prices[inp.plan]
        verified_price(price_id, inp.plan)
        fields = {
            'mode': 'payment' if inp.plan == 'plus' else 'subscription',
            'line_items[0][price]': price_id, 'line_items[0][quantity]': '1',
            'client_reference_id': user['user_id'],
            'metadata[user_id]': user['user_id'], 'metadata[plan]': inp.plan,
            'success_url': origin + '/?billing=return',
            'cancel_url': origin + '/?billing=cancel',
            'billing_address_collection': 'auto',
        }
        if inp.plan == 'plus':
            from licensing import major_version
            fields['metadata[license_major]'] = str(major_version())
        if inp.plan in ('premium', 'family'):
            fields['subscription_data[metadata][user_id]'] = user['user_id']
            fields['subscription_data[metadata][plan]'] = inp.plan
        if row and row['stripe_customer_id']:
            fields['customer'] = row['stripe_customer_id']
        else:
            fields['customer_email'] = user['email']
        result = stripe_http('POST', '/v1/checkout/sessions', secret, fields)
        url = result.get('url', '')
        if not (url.startswith('https://checkout.stripe.com/') or url.startswith('https://billing.stripe.com/')):
            fail('Stripe did not provide a valid checkout URL.', 502)
        return {'url': url, 'test_mode': True}

    @app.post('/api/billing/portal')
    def portal(user=Depends(csrf_user)):
        require_test_mode()
        with db() as con:
            row = get_billing(con, user['user_id'])
        if not row or not row['stripe_customer_id']:
            fail('No Stripe test billing account is connected yet.', 404)
        result = stripe_http('POST', '/v1/billing_portal/sessions', secret,
                             {'customer': row['stripe_customer_id'], 'return_url': origin + '/?billing=return'})
        url = result.get('url', '')
        if not url.startswith('https://billing.stripe.com/'):
            fail('Stripe did not provide a billing portal URL.', 502)
        return {'url': url, 'test_mode': True}

    @app.post('/api/billing/webhook')
    async def stripe_webhook(request: Request):
        require_test_mode()
        payload = await request.body()
        event = verify_webhook(payload, request.headers.get('stripe-signature', ''), webhook_secret)
        event_id = event['id']
        kind = event['type']
        obj = (event.get('data') or {}).get('object') or {}
        if not isinstance(obj, dict):
            fail('Invalid event format.')
        # Stripe duplicates/retries events; all local updates and event id are one transaction.
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT 1 FROM billing_events WHERE event_id=?', (event_id,)).fetchone():
                return {'received': True, 'duplicate': True}
            if kind in ('checkout.session.completed', 'checkout.session.async_payment_succeeded'):
                uid = obj.get('client_reference_id') or (obj.get('metadata') or {}).get('user_id')
                plan = (obj.get('metadata') or {}).get('plan')
                customer = obj.get('customer')
                if (isinstance(uid, str) and isinstance(customer, str) and customer.startswith('cus_')
                    and con.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone()):
                    # Do not silently remap a customer belonging to another TunelyTV user.
                    taken = con.execute('SELECT user_id FROM billing_accounts WHERE stripe_customer_id=?', (customer,)).fetchone()
                    if not taken or taken['user_id'] == uid:
                        con.execute('''INSERT INTO billing_accounts(user_id,stripe_customer_id,updated_at)
                          VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                          stripe_customer_id=excluded.stripe_customer_id,updated_at=excluded.updated_at''', (uid, customer, int(time.time())))
                        if (plan == 'plus' and obj.get('mode') == 'payment' and obj.get('payment_status') == 'paid'
                                and obj.get('amount_total') == 1999 and obj.get('currency') == 'usd'):
                            con.execute('UPDATE billing_accounts SET plus_lifetime=1 WHERE user_id=?', (uid,))
                            original_major = (obj.get('metadata') or {}).get('license_major','1')
                            try:
                                original_major = int(original_major)
                            except (ValueError,TypeError):
                                original_major = 0
                            if not 1 <= original_major <= 999:
                                fail('Invalid purchased license metadata.', 400)
                            award_verified_plus(con, uid, event_id, purchased_major=original_major)
                            intent=obj.get('payment_intent')
                            if isinstance(intent,str) and intent.startswith('pi_'):
                                con.execute('''INSERT OR IGNORE INTO plus_payments
                                   (payment_intent,user_id,major_version,purchased_at)
                                   VALUES (?,?,?,?)''',
                                   (intent,uid,original_major,int(time.time())))
            elif kind == 'charge.refunded':
                # Revoke a license ONLY after a signed event for an exact previously
                # recorded test payment intent and a full refund. No email matching.
                intent = obj.get('payment_intent')
                amount = obj.get('amount')
                refunded = obj.get('amount_refunded')
                if (isinstance(intent,str) and intent.startswith('pi_') and
                        isinstance(amount,int) and amount>0 and
                        isinstance(refunded,int) and refunded>=amount):
                    item=con.execute('''SELECT * FROM plus_payments
                         WHERE payment_intent=? AND refunded_at IS NULL''',(intent,)).fetchone()
                    if item:
                        con.execute('UPDATE plus_payments SET refunded_at=? WHERE payment_intent=?',
                                    (int(time.time()),intent))
                        con.execute('''UPDATE plus_licenses SET revoked_at=?
                             WHERE user_id=? AND major_version=? AND event_id IS NOT NULL''',
                                    (int(time.time()),item['user_id'],item['major_version']))
                        con.execute('''UPDATE billing_accounts SET plus_lifetime=0,updated_at=? WHERE user_id=?''',
                                    (int(time.time()),item['user_id']))
                        con.execute('''INSERT INTO license_audit(actor_id,target_id,action,detail,at)
                             VALUES (NULL,?,'plus_full_refund',?,?)''',
                                    (item['user_id'],f'Stripe TEST refund {event_id}',int(time.time())))
            elif kind in ('customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'):
                meta = obj.get('metadata') or {}
                uid = meta.get('user_id')
                customer = obj.get('customer')
                sid = obj.get('id')
                # Independently verify Stripe price maps to our configured plan.
                items = ((obj.get('items') or {}).get('data') or [])
                price_ids = [((item.get('price') or {}).get('id')) for item in items if isinstance(item, dict)]
                # Derive the current tier from the actual subscription item, not stale
                # metadata: plan changes through Stripe Portal update the price.
                plan = next((p for p in ('premium', 'family') if len(price_ids) == 1
                             and price_ids[0] == prices[p]), None)
                prior = get_billing(con, uid) if isinstance(uid, str) else None
                # A real signed deletion must revoke access even if Stripe omits
                # subscription items; unsupported portal prices also cannot keep
                # an old Premium entitlement active.
                unrecognized_price = not plan
                if unrecognized_price and prior and prior['stripe_subscription_id'] == sid and prior['stripe_customer_id'] == customer:
                    plan = prior['subscription_plan']
                if (isinstance(uid, str) and plan in ('premium', 'family') and
                    isinstance(customer, str) and customer.startswith('cus_') and
                    isinstance(sid, str) and sid.startswith('sub_') and (prices[plan] in price_ids or (unrecognized_price and prior and prior['stripe_subscription_id'] == sid)) and
                    con.execute('SELECT id FROM users WHERE id=?', (uid,)).fetchone()):
                    taken = con.execute('SELECT user_id FROM billing_accounts WHERE stripe_customer_id=?', (customer,)).fetchone()
                    if not taken or taken['user_id'] == uid:
                        existing = get_billing(con, uid)
                        # Don't let stale subscriptions overwrite an unrelated active subscription.
                        if not existing or not existing['stripe_subscription_id'] or existing['stripe_subscription_id'] == sid or existing['subscription_status'] not in ACTIVE_STATUSES:
                            status = 'canceled' if kind.endswith('.deleted') else ('incomplete' if unrecognized_price else obj.get('status', 'incomplete'))
                            period_end = obj.get('current_period_end')
                            con.execute('''INSERT INTO billing_accounts(user_id,stripe_customer_id,stripe_subscription_id,
                                subscription_plan,subscription_status,cancel_at_period_end,current_period_end,updated_at)
                                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                                stripe_customer_id=excluded.stripe_customer_id,
                                stripe_subscription_id=excluded.stripe_subscription_id,
                                subscription_plan=excluded.subscription_plan,
                                subscription_status=excluded.subscription_status,
                                cancel_at_period_end=excluded.cancel_at_period_end,
                                current_period_end=excluded.current_period_end,
                                updated_at=excluded.updated_at''',
                                (uid, customer, sid, plan, status,
                                 int(bool(obj.get('cancel_at_period_end'))),
                                 period_end if isinstance(period_end, int) else None, int(time.time())))
            con.execute('INSERT INTO billing_events(event_id,processed_at) VALUES(?,?)', (event_id, int(time.time())))
        return {'received': True}
