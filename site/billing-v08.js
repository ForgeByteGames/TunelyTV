/* Stripe test-only billing UI; no plan grants from local storage or return URL. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('billingCurrentPlan')) return;
  const info = {free:'Free',plus:'Plus Lifetime',premium:'Premium',family:'Family'};
  let billing = null;
  async function jsonApi(path, options={}) {
    const headers = options.method ? {'Content-Type':'application/json','X-CSRF-Token':(window.tunelyGetCsrf?.() || '')} : {};
    const response = await fetch('/api'+path,{credentials:'same-origin',...options,headers});
    const data=await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Billing service unavailable.');
    return data;
  }
  function notice(text, error=false) { const n=$('billingNotice'); n.textContent=text; n.style.borderColor=error?'rgba(255,99,99,.5)':''; }
  async function refreshBilling() {
    try {
      billing = await jsonApi('/billing/status');
      const plan=billing.plan || 'free';
      $('billingCurrentPlan').textContent = info[plan] || 'Free';
      if($('dashboardPlan')) $('dashboardPlan').textContent = info[plan] || 'Free';
      if($('profilePlan')) $('profilePlan').textContent = `${info[plan] || 'Free'} · Private staging`;
      $('billingPlanStatus').textContent = billing.subscription_status ? `Monthly: ${billing.subscription_status}` : billing.plus_lifetime ? 'Lifetime owned' : 'Free account';
      $('billingModeBadge').textContent = billing.stripe_test_enabled ? 'STRIPE TEST MODE ONLY' : 'PAYMENTS NOT CONNECTED';
      $('billingSummary').textContent = billing.stripe_test_enabled ? 'Test checkout available. Only Stripe test cards can be used; no real purchases.' : 'Your account is ready. Payments are not configured, so your Free plan remains active.';
      const end=billing.current_period_end ? new Date(billing.current_period_end*1000).toLocaleDateString() : null;
      $('billingRenewal').textContent=end ? (billing.cancel_at_period_end ? `Scheduled to end: ${end}` : `Current period ends: ${end}`) : '';
      $('billingManage').disabled=!billing.can_manage_billing;
      document.querySelectorAll('[data-plan-card]').forEach(el=>el.classList.toggle('current',el.dataset.planCard===plan));
      document.querySelectorAll('[data-billing-checkout]').forEach(btn=>{
        const id=btn.dataset.billingCheckout;
        const owned=id==='plus' && billing.plus_lifetime;
        const monthlyActive=['active','trialing'].includes(billing.subscription_status) && ['premium','family'].includes(billing.subscription_plan);
        btn.disabled=!billing.stripe_test_enabled || owned || monthlyActive;
        btn.textContent=owned?'Already owned':monthlyActive?'Manage existing plan':billing.stripe_test_enabled?'Test checkout ↗':'Stripe not connected';
      });
      notice(billing.stripe_test_enabled ? 'TEST MODE: only Stripe test transactions are supported. Payment success is verified by Stripe webhooks; returning to this page does not grant access.' : 'Stripe is not connected yet. Pricing is approved for the future; no payments or live charges are enabled.');
      if(new URLSearchParams(location.search).has('billing')) {
        notice('Returned from Stripe test checkout or cancellation. Your plan updates only after a verified webhook; refresh to check status.');
      }
    } catch(e) { notice(e.message,true); }
  }
  async function action(route, body) {
    const button=document.activeElement;
    try{
      if(!window.tunelyGetCsrf?.()) throw new Error('Please sign in to manage billing.');
      if(button instanceof HTMLButtonElement) button.disabled=true;
      const payload=await jsonApi('/billing/'+route,{method:'POST',body:JSON.stringify(body||{})});
      if(payload.url) location.assign(payload.url);
    }catch(e){notice(e.message,true);await refreshBilling().catch(()=>{});}
    finally{if(button instanceof HTMLButtonElement && button.id==='billingManage') button.disabled=false;}
  }
  document.addEventListener('click',e=>{
    const checkout=e.target.closest('[data-billing-checkout]');
    if(checkout&&!checkout.disabled){action('checkout',{plan:checkout.dataset.billingCheckout});return;}
    if(e.target.closest('#billingManage')&&!$('billingManage').disabled){action('portal');return;}
    if(e.target.closest('#billingRefresh')) refreshBilling();
    if(e.target.closest('[data-page="billing"]')) refreshBilling();
  });
  // Login may be pending during page initialization; only fetch when panel opened.
  window.addEventListener('pageshow',()=>{if(location.search.includes('billing='))setTimeout(refreshBilling,50);});
})();
