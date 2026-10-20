# TunelyTV release checklist — NOT cleared for public paid launch

- [ ] Test the full Railway HTTPS app and actual authorized stream playback (CORS/codec limitations still apply).
- [ ] Configure persistent SQLite volume; backup, restore, encryption-key rotation plan; restrict trial accounts.
- [ ] Complete Google Sign-In backend or keep its UI explicitly pending.
- [ ] Set up Stripe and test webhooks; independently review Stripe eligibility, terms, business identity and merchant requirements.
- [ ] Implement server-side plan feature/device-limit enforcement. Current tests grant a plan label only, not a meaningful commercial entitlement contract.
- [ ] Define exact Free/Plus/Premium/Family feature matrices. Tunely Home access only Premium/Family, subject to legal review of recording rights.
- [ ] Define Plus Lifetime scope (product life/version/support), cancellations, returns, refund and chargeback entitlements.
- [ ] Production-grade Stripe reconciliation: refunds, disputes, payment failures, stale/out-of-order events, portal plan changes and verified state retrieval.
- [ ] Confirm business formation/licensing/taxes where applicable; have legal counsel review the actual streaming model and the Terms, Privacy, copyright/DMCA process.
- [ ] Implement account deletion, deletion/retention of encrypted media credentials and billing logs, password reset, email verification and incident response.
- [ ] Production monitoring, backups, shared rate limiting, session management, invite abuse controls, request logging scrubbing, security review.
- [ ] Ship no streams or copyrighted channel logos and never advertise included content rights.

This v0.8 code is an **experimental private staging release**, not a statement that TunelyTV has legal immunity or that an LLC is always legally required.


## Multi-View v0.9 pre-launch gates

Confirm multi-device plan counts and provider concurrent-stream permissions. Disable `TUNELY_MULTIVIEW_PRIVATE_PREVIEW` before a public launch. Verify Plus trial and Free browser restrictions server-side; integrate real released client policies; test HLS playback/codec and CORS behavior with actual authorized streams and realistic network/CPU limitations. Browser-side gating alone does not prevent a sophisticated user from opening direct provider URLs outside TunelyTV.
