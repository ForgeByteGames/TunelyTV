"""TunelyTV private-stage licensing and entitlement rules.

Server time decides trials and subscription access. No browser flag or checkout
redirect can grant a license. All permanent grants require a verified purchase
(or an audited migration of previously verified test billing state).
"""
from __future__ import annotations

import os
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import Depends, Request
from pydantic import BaseModel, Field

TRIAL_SECONDS = 7 * 86400
# Staging policy. Paid TV slots require final business approval before public sales.
TV_SLOTS = {'free': 1, 'plus': 2, 'premium': 3, 'family': 5}
MULTIVIEW_PANES = {'free': 0, 'plus': 2, 'premium': 4, 'family': 4}
ACTIVE_STATUSES = ('active', 'trialing')


def timestamp() -> int:
    return int(time.time())


def major_version() -> int:
    raw = os.environ.get('TUNELY_LICENSE_MAJOR', '1')
    if not re.fullmatch(r'[1-9][0-9]{0,2}', raw):
        raise RuntimeError('TUNELY_LICENSE_MAJOR must be an integer from 1 to 999.')
    return int(raw)


def setup_schema(db):
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS plus_licenses (
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          major_version INTEGER NOT NULL CHECK(major_version >= 1),
          source TEXT NOT NULL CHECK(source IN ('stripe_test','legacy_stripe_test')),
          event_id TEXT, granted_at INTEGER NOT NULL, revoked_at INTEGER,
          PRIMARY KEY (user_id, major_version));
        CREATE TABLE IF NOT EXISTS plus_payments (
          payment_intent TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          major_version INTEGER NOT NULL,
          purchased_at INTEGER NOT NULL,
          refunded_at INTEGER);
        CREATE TABLE IF NOT EXISTS plus_trials (
          user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          started_at INTEGER NOT NULL, ends_at INTEGER NOT NULL,
          CHECK(ends_at > started_at));
        CREATE TABLE IF NOT EXISTS owners (
          user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          granted_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS license_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor_id TEXT REFERENCES users(id) ON DELETE SET NULL,
          target_id TEXT REFERENCES users(id) ON DELETE SET NULL,
          action TEXT NOT NULL, detail TEXT NOT NULL, at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_license_audit_created ON license_audit(at DESC);
        ''')
        # Legacy PLUS test purchases were awarded only by Stripe-signature-verified
        # checkout webhooks in older builds. Preserve those test rights; no new
        # paid license is created by an ordinary login or browser action.
        legacy = con.execute('''SELECT ba.user_id, ba.updated_at FROM billing_accounts ba
            WHERE ba.plus_lifetime=1 AND NOT EXISTS
              (SELECT 1 FROM plus_licenses l WHERE l.user_id=ba.user_id)''').fetchall()
        for row in legacy:
            con.execute('''INSERT OR IGNORE INTO plus_licenses
                (user_id,major_version,source,event_id,granted_at)
                VALUES (?,1,'legacy_stripe_test',NULL,?)''',
                (row['user_id'], row['updated_at']))


def award_verified_plus(con, user_id: str, event_id: str, at: int | None = None, purchased_major: int | None = None):
    """Must be invoked only INSIDE a verified Stripe webhook transaction."""
    moment = at if at is not None else timestamp()
    major = purchased_major if purchased_major is not None else major_version()
    if not isinstance(major,int) or major<1 or major>999:
        raise ValueError("Invalid purchased license major.")
    con.execute('''INSERT OR IGNORE INTO plus_licenses
       (user_id,major_version,source,event_id,granted_at)
       VALUES (?,?,'stripe_test',?,?)''',
       (user_id, major, event_id, moment))
    con.execute('''INSERT INTO license_audit(actor_id,target_id,action,detail,at)
       VALUES (NULL,?,'verified_plus_purchase',?,?)''',
       (user_id, f'major {major}, Stripe TEST event {event_id}', moment))


def account_access(con, user_id: str, at: int | None = None) -> dict:
    t = timestamp() if at is None else at
    major = major_version()
    trial = con.execute('SELECT * FROM plus_trials WHERE user_id=?', (user_id,)).fetchone()
    grants = con.execute('''SELECT major_version,granted_at,source FROM plus_licenses
       WHERE user_id=? AND revoked_at IS NULL ORDER BY major_version''', (user_id,)).fetchall()
    versions = [row['major_version'] for row in grants]
    billing = con.execute('''SELECT subscription_plan,subscription_status,current_period_end,
       cancel_at_period_end, plus_lifetime FROM billing_accounts WHERE user_id=?''', (user_id,)).fetchone()
    owner = bool(con.execute('SELECT 1 FROM owners WHERE user_id=?', (user_id,)).fetchone())
    # Explicitly do not let a stale 'active' status grant access indefinitely
    # if period_end has elapsed without a renewal webhook.
    subscription_valid = bool(billing and billing['subscription_plan'] in ('premium','family')
        and billing['subscription_status'] in ACTIVE_STATUSES
        and (billing['current_period_end'] is None or billing['current_period_end'] > t))
    owns_current = major in versions
    active_trial = bool(trial and trial['started_at'] <= t < trial['ends_at'])
    if subscription_valid:
        tier = billing['subscription_plan']
        reason = 'subscription'
    elif owns_current:
        tier,reason = 'plus','perpetual_version'
    elif active_trial:
        tier,reason = 'plus','trial'
    else:
        tier,reason = 'free','free'
    # Owner preview is separate from paid state; no transaction is implied.
    effective = 'family' if owner else tier
    if trial is None: trial_status = 'eligible'
    elif t < trial['started_at']: trial_status = 'scheduled'
    elif t < trial['ends_at']: trial_status = 'active'
    else: trial_status = 'expired'
    return {
      'plan': tier, 'effective_plan': effective,
      'access_reason': 'owner_preview' if owner else reason,
      'owner': owner, 'current_major': major,
      'owned_plus_majors': versions, 'owns_current_plus': owns_current,
      'trial_status': trial_status,
      'trial_started_at': trial['started_at'] if trial else None,
      'trial_ends_at': trial['ends_at'] if trial else None,
      'trial_seconds_remaining': max(0, trial['ends_at'] - t) if trial and active_trial else 0,
      'subscription_status': billing['subscription_status'] if billing else None,
      'subscription_plan': billing['subscription_plan'] if billing else None,
      'subscription_current_period_end': billing['current_period_end'] if billing else None,
      'tv_slots': TV_SLOTS[effective],
      'web_playback': effective != 'free',
      'phone_tablet_playback': effective != 'free',
      'multiview_panes': MULTIVIEW_PANES[effective],
      'tunely_home_available': False,  # not built / recording-rights review pending
      'payments_live': False,
    }


class OwnerClaim(BaseModel):
    setup_token: str = Field(min_length=24, max_length=256)


def install_licensing(app, db, current_user, csrf_user, fail, throttle, prod):
    setup_schema(db)
    owner_email = os.environ.get('TUNELY_OWNER_EMAIL', '').strip().lower()
    owner_token = os.environ.get('TUNELY_ADMIN_SETUP_TOKEN', '')

    @app.get('/api/license/me')
    def license_me(user=Depends(current_user)):
        with db() as con:
            state = account_access(con, user['user_id'])
            setup_available = (bool(owner_email and owner_token and len(owner_token) >= 24)
                and user['email'].lower() == owner_email
                and not con.execute('SELECT 1 FROM owners LIMIT 1').fetchone())
        return {**state, 'owner_setup_available': setup_available}

    @app.post('/api/license/trial/start', status_code=201)
    def start_trial(request: Request, user=Depends(csrf_user)):
        throttle(request, 'license-trial', 5, 3600)
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            state = account_access(con, user['user_id'])
            if state['trial_status'] != 'eligible':
                fail('Your introductory trial has already been used.', 409)
            if state['owns_current_plus'] or state['plan'] in ('premium', 'family'):
                fail('An active purchase or subscription already provides access.', 409)
            t = timestamp()
            con.execute('INSERT INTO plus_trials(user_id,started_at,ends_at) VALUES (?,?,?)',
                        (user['user_id'], t, t + TRIAL_SECONDS))
            con.execute('''INSERT INTO license_audit(actor_id,target_id,action,detail,at)
                 VALUES (?,?,'trial_started','7 days, no card or renewal',?)''',
                 (user['user_id'], user['user_id'], t))
            state = account_access(con, user['user_id'], at=t)
        return state

    @app.post('/api/owner/bootstrap')
    def claim_owner(inp: OwnerClaim, request: Request, user=Depends(csrf_user)):
        throttle(request, 'owner-bootstrap', 5, 3600)
        if (not owner_email or not owner_token or len(owner_token) < 24 or
                user['email'].lower() != owner_email or
                not secrets.compare_digest(inp.setup_token, owner_token)):
            fail('Owner verification failed.', 403)
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            existing = con.execute('SELECT user_id FROM owners LIMIT 1').fetchone()
            if existing:
                fail('An owner has already been established.', 409)
            t = timestamp()
            con.execute('INSERT INTO owners(user_id,granted_at) VALUES (?,?)', (user['user_id'], t))
            con.execute('''INSERT INTO license_audit(actor_id,target_id,action,detail,at)
                 VALUES (?,?,'owner_bootstrap','one-time verified owner setup',?)''',
                 (user['user_id'], user['user_id'], t))
        return {'owner': True, 'note': 'Owner access established. Remove TUNELY_ADMIN_SETUP_TOKEN from Railway.'}

    @app.get('/api/owner/users')
    def owner_users(limit: int = 50, user=Depends(current_user)):
        with db() as con:
            if not account_access(con, user['user_id'])['owner']:
                fail('Owner access required.', 403)
            rows = con.execute('''SELECT id,email,created_at FROM users
                 ORDER BY created_at DESC, id DESC LIMIT ?''', (min(max(1,limit),100),)).fetchall()
            out=[]
            for row in rows:
                state=account_access(con,row['id'])
                out.append({
                    'user_id':row['id'], 'email':row['email'], 'created_at':row['created_at'],
                    'plan':state['plan'], 'owner':state['owner'],
                    'access_reason':state['access_reason'],
                    'trial_status':state['trial_status'], 'trial_ends_at':state['trial_ends_at'],
                    'owned_plus_majors':state['owned_plus_majors'],
                    'subscription_status':state['subscription_status'],
                    'tv_slots':state['tv_slots'], 'web_playback':state['web_playback']})
        return {'users':out, 'payments_live':False, 'view_only':True}

    @app.get('/api/owner/audit')
    def owner_audit(limit: int = 25, user=Depends(current_user)):
        with db() as con:
            if not account_access(con, user['user_id'])['owner']:
                fail('Owner access required.', 403)
            rows=con.execute('''SELECT action,detail,at,target_id FROM license_audit
                 ORDER BY id DESC LIMIT ?''', (min(max(1,limit),100),)).fetchall()
        return {'events': [dict(r) for r in rows]}
