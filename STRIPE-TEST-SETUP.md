# Stripe preparation and safe test-mode configuration

**No Stripe account exists yet. This feature is intentionally disabled until a Stripe account and valid TEST-mode API credentials are supplied. The v0.8 integration refuses live keys and will never process real charges.**

1. Create or connect a legitimate Stripe merchant account when you are ready; Stripe eligibility for a bring-your-own-authorized-source IPTV *software* product must be reviewed with Stripe. Do not imply that TunelyTV carries or sells channels.
2. In Stripe **test mode**, create three Price objects in **USD**:
   - `Plus Lifetime`: $19.99 **one time**, test Price ID e.g. `price_...`.
   - `Premium`: $4.99 **per month**.
   - `Family`: $7.99 **per month**.
   Check unit amount and billing interval carefully; v0.8 backend independently validates Stripe Price data before opening Checkout.
3. In the test dashboard configure a Customer Portal for test customers. Decide allowed plan changes and cancellation settings.
4. Create a test webhook endpoint at `https://stream.tunelytv.com/api/billing/webhook` with these events:
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Add these variables to Railway **Variables**, never GitHub:

```text
TUNELY_ENABLE_STRIPE_TEST=true
TUNELY_PUBLIC_URL=https://stream.tunelytv.com
STRIPE_SECRET_KEY=sk_test_...                       # secret test key
STRIPE_WEBHOOK_SECRET=whsec_...                     # test endpoint signing secret
STRIPE_PRICE_PLUS=price_...
STRIPE_PRICE_PREMIUM=price_...
STRIPE_PRICE_FAMILY=price_...
```

6. Deploy; sign in with a private testing account. The billing page changes from `PAYMENTS NOT CONNECTED` to `STRIPE TEST MODE ONLY`. The buttons open Stripe-hosted *test* Checkout pages. Use only Stripe-documented **test payment methods**. No real money is charged.
7. Confirm valid Stripe events reach Railway logs without exposing credentials. New plan appears in `GET /api/billing/status` **only after** verified webhook handling. Test: plus checkout, premium monthly checkout, family monthly checkout, portal cancellation, upgrades/downgrades, duplicate webhook, rejected bad signature.

## Rules this build enforces

- Account login and anti-CSRF header required to start checkout or portal.
- The browser sends a plan key only. Server selects a fixed configured Price ID and verifies the amount, currency and renewal interval with Stripe.
- TunelyTV never stores raw payment card data.
- Stripe webhook HMAC SHA-256 signature validation with five-minute timestamp tolerance; event IDs recorded for duplicate rejection.
- Checkout return URLs cannot update entitlements. Test webhook is the source of truth.
- Test payments are disabled unless all six required environment values are populated and `STRIPE_SECRET_KEY` begins `sk_test_`.
- **Live keys are rejected**; this is *not* a live-payment release.

## Open items before any real paid launch

Legally vetted Terms, Privacy and Refund policies; actual plan entitlements enforcement; Plus Lifetime support promise; billing verification/reconciliation jobs; out-of-order subscription event handling with Stripe retrieval; account deletion/refund and reversal handling; tax/VAT and regional compliance; receipt/dispute management; production secrets, monitoring, rate limiting; Stripe business review. **Do not flip a live key into this project or claim payments are launched.**

Reference: https://docs.stripe.com/api/checkout/sessions/create
