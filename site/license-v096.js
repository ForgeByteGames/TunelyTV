/* Private-stage licensing status: no card collection and no simulated purchase buttons. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  if(!$('licensePlan'))return;
  let refreshBusy=false;
  const api=async(route,body)=>{
    const response=await fetch('/api'+route,{
      method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',
      headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':window.tunelyGetCsrf?.()||''},
      body:body===undefined?undefined:JSON.stringify(body)
    });
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(typeof payload.detail==='string'?payload.detail:'Account license unavailable.');
    return payload;
  };
  const showDate=ts=>ts?new Date(ts*1000).toLocaleString():'Not applicable';
  const planLabel={free:'Free',plus:'Plus One-Time',premium:'Premium',family:'Family'};
  const set=(id,str)=>{if($(id))$(id).textContent=str;};
  const notice=(str)=>set('licenseTrialMessage',str);
  async function renderOwners(){
    const [people,history]=await Promise.all([api('/owner/users'),api('/owner/audit')]);
    const body=$('ownerUsers');body.replaceChildren();
    people.users.forEach(x=>{
      const tr=document.createElement('tr');
      [x.email,x.owner?'Owner preview':x.plan,x.trial_status,
       x.owned_plus_majors.join(', ')||'—',String(x.tv_slots)].forEach(value=>{
        const td=document.createElement('td');td.textContent=value;tr.appendChild(td);
      });body.appendChild(tr);
    });
    const events=$('ownerAudit');events.replaceChildren();
    history.events.forEach(evt=>{
      const entry=document.createElement('div');entry.className='owner-audit-item';
      entry.textContent=`${showDate(evt.at)} · ${evt.action} · ${evt.detail}`;events.appendChild(entry);
    });
    set('ownerSummary',`${people.users.length} most recent accounts. Read-only; no grants or charges issued.`);
  }
  async function refresh(){
    if(refreshBusy||!window.tunelyGetCsrf?.())return;
    refreshBusy=true;
    try{
      const state=await api('/license/me');
      set('licensePlan',state.owner?'Owner testing':planLabel[state.plan]);
      set('licenseVersion',state.owned_plus_majors.length?`Licensed major version(s): ${state.owned_plus_majors.join(', ')}`:
        `Plus One-Time version ${state.current_major}.x is not purchased`);
      set('licenseAccess',state.web_playback?'Web playback enabled':'TV-only Free plan');
      set('licenseExpiration',state.access_reason==='trial'?`Trial ends ${showDate(state.trial_ends_at)}`:
        state.owns_current_plus?'Purchased version does not expire':state.owner?'Owner-only preview':
        state.subscription_current_period_end?`Current period ends ${showDate(state.subscription_current_period_end)}`:'No active Plus or subscription');
      set('licenseSlots',String(state.tv_slots));
      const start=$('startPlusTrial');
      start.disabled=state.trial_status!=='eligible'||state.plan!=='free'||state.owner;
      if(state.trial_status==='eligible' && state.plan==='free' && !state.owner){
        start.textContent='Start my 7-day trial';
        notice('One trial per eligible account. No card and no automatic charge.');
      }else if(state.trial_status==='eligible'){
        start.textContent='Access already provided';
        notice(state.owner?'Owner preview is active.': 'Your purchased or subscribed plan already provides access.');
      }else if(state.trial_status==='active'){
        start.textContent='Trial active';
        notice(`Trial ends ${showDate(state.trial_ends_at)}. ${Math.ceil(state.trial_seconds_remaining/86400)} day(s) remaining. No automatic payment.`);
      }else{
        start.textContent=state.trial_status==='expired'?'Trial finished':'Trial unavailable';
        notice(state.owns_current_plus?'You own your purchased Plus major version.':
          state.owner?'Owner preview is active.':
          state.trial_status==='expired'?'Your trial has expired. Your playlists are saved; Free is TV-only.':
          'Your current plan already includes playback.');
      }
      $('ownerNav').hidden=!state.owner;
      $('ownerSetup').hidden=!state.owner_setup_available;
      if(state.owner && document.querySelector('#page-licenses.active'))await renderOwners();
      window.dispatchEvent(new CustomEvent('tunelyLicenseUpdated',{detail:state}));
    }catch(err){notice(err.message);}
    finally{refreshBusy=false;}
  }
  $('startPlusTrial').addEventListener('click',async()=>{
    if(!confirm('Start your one-time 7-day Plus trial now? It expires automatically and never charges you.'))return;
    $('startPlusTrial').disabled=true;
    try{await api('/license/trial/start',{});await refresh();}
    catch(e){notice(e.message);await refresh();}
  });
  $('ownerSetupForm').addEventListener('submit',async e=>{
    e.preventDefault();
    const token=$('ownerSetupToken').value;
    try{
      await api('/owner/bootstrap',{setup_token:token});
      $('ownerSetupToken').value='';
      set('ownerSetupStatus','Owner role verified. Remove TUNELY_ADMIN_SETUP_TOKEN from Railway now.');
      await refresh();
    }catch(err){set('ownerSetupStatus',err.message);}
  });
  document.addEventListener('click',e=>{
    const nav=e.target.closest('[data-page="licenses"], [data-page="billing"], #billingRefresh');
    if(nav) setTimeout(()=>refresh(),0);
  });
  // Wait for authenticated account shell. Does not store tokens or license state.
  const observer=new MutationObserver(()=>{
    if(!document.body.classList.contains('auth-locked'))void refresh();
  });
  observer.observe(document.body,{attributes:true,attributeFilter:['class']});
  if(!document.body.classList.contains('auth-locked'))void refresh();
  setInterval(()=>{if(document.visibilityState==='visible' && !document.body.classList.contains('auth-locked'))void refresh();},60000);
})();
