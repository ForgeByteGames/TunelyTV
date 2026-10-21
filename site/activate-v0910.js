/* Phone activation uses the existing account session + CSRF-protected claim API. */
(()=>{
'use strict';const $=id=>document.getElementById(id);
let csrf='';
const valid=c=>{const s=c.replace(/[\s-]/g,'').toUpperCase();return /^[A-HJ-NP-Z2-9]{8}$/.test(s)?s.slice(0,4)+'-'+s.slice(4):null;};
const msg=text=>{$('error').textContent=text||'';};
async function request(path,{method='GET',body,csrfHeader=false}={}){
 const headers={};if(body!==undefined)headers['Content-Type']='application/json';if(csrfHeader)headers['X-CSRF-Token']=csrf;
 const resp=await fetch('/api'+path,{method,headers,credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});
 const data=await resp.json().catch(()=>({}));
 if(!resp.ok){const detail=typeof data.detail==='string'?data.detail:'Request failed ('+resp.status+')';throw Error(detail);}
 return data;
}
async function loadPlaylists(){
 const data=await request('/playlists');
 const select=$('playlist');select.replaceChildren(new Option('Set up a playlist later',''));
 for(const p of data.playlists||[])select.add(new Option(p.name,p.id));
}
async function signedIn(account){
 $('loginArea').hidden=true;$('linkArea').hidden=false;$('accountEmail').textContent=account||'TunelyTV account';
 try{await loadPlaylists();msg('');}catch(e){msg(e.message);}
}
async function checkAuth(){
 try{const data=await request('/auth/csrf');csrf=data.csrf_token;await signedIn(data.email);}
 catch{$('loginArea').hidden=false;$('linkArea').hidden=true;}
}
$('loginForm').addEventListener('submit',async e=>{
 e.preventDefault();const btn=$('loginButton');btn.disabled=true;msg('');
 try{const d=await request('/auth/login',{method:'POST',body:{email:$('email').value.trim(),password:$('password').value}});csrf=d.csrf_token;$('password').value='';await signedIn(d.email);}
 catch(ex){msg(ex.message);}finally{btn.disabled=false;}
});
$('confirm').addEventListener('click',async()=>{
 const code=valid($('code').value);if(!code){msg('Enter the 8-character code shown on your TV.');return;}
 const btn=$('confirm');btn.disabled=true;msg('');
 try{
  await request('/pairings/claim',{method:'POST',csrfHeader:true,body:{code,playlist_id:$('playlist').value||null}});
  $('activationView').hidden=true;$('successView').hidden=false;history.replaceState(null,'','/activate');
 }catch(ex){msg(ex.message);}finally{btn.disabled=false;}
});
$('reloadPlaylists').addEventListener('click',async()=>{try{await loadPlaylists();msg('');}catch(e){msg(e.message);}});
$('signOut').addEventListener('click',async()=>{try{await request('/auth/logout',{method:'POST',csrfHeader:true});csrf='';$('linkArea').hidden=true;$('loginArea').hidden=false;msg('');}catch(ex){msg(ex.message);}});
$('code').addEventListener('input',()=>{let raw=$('code').value.toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,8);$('code').value=raw.length>4?raw.slice(0,4)+'-'+raw.slice(4):raw;});
const qp=new URLSearchParams(location.search).get('code')||'';const given=valid(qp);
if(given)$('code').value=given;
checkAuth();
})();
