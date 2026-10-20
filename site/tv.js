// Browser-only TV simulator. Real TV app should use OS-protected credential storage.
(()=>{
'use strict';
const $=id=>document.getElementById(id);
let deviceToken=sessionStorage.getItem('tunely_tv_sim_token')||'',expiresAt=0,revision=0;
function error(message){$('err').textContent=message;}
async function poll(){if(!deviceToken)return;
 try{const resp=await fetch('/api/device/sync?since='+revision,{headers:{Authorization:'Bearer '+deviceToken},cache:'no-store'});
 if(!resp.ok){if(resp.status===401){error('This device token was revoked. Reset to pair again.');$('connection').textContent='Device disconnected';deviceToken='';sessionStorage.removeItem('tunely_tv_sim_token');return;}throw Error('Sync request failed ('+resp.status+').');}
 const payload=await resp.json();error('');
 if(payload.status==='expired'){$('expires').textContent='Code expired. Reset and generate a new code.';$('connection').textContent='Pairing code expired';return;}
 if(!payload.paired){$('connection').textContent='Waiting for the dashboard to claim this code…';return;}
 $('pairPanel').hidden=true;$('pairedPanel').hidden=false;$('eyebrow').textContent='CONNECTED & SYNCHRONIZING';$('statusHeading').innerHTML='You’re paired.<br><span>Ready to sync.</span>';
 $('statusDesc').textContent='Your paired TunelyTV application has received its account authorization.';
 $('deviceName').textContent=payload.device_name;
 $('connection').textContent='Connected • Checking for playlist updates every 4 seconds';
 if(payload.changed){revision=payload.revision;$('revision').textContent=revision;$('playlistName').textContent=payload.playlist?.name||'No playlist assigned';$('playlistType').textContent=({m3u_file:'M3U file',m3u_url:'M3U URL',xtream:'Xtream-compatible'})[payload.playlist?.type]||'—';}
 $('syncedAt').textContent=new Date().toLocaleTimeString();
 }catch(ex){$('connection').textContent='Retrying connection';error(ex.message);}
}
$('startButton').addEventListener('click',async()=>{const b=$('startButton');b.disabled=true;error('');try{const resp=await fetch('/api/device/enroll',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'My TunelyTV Simulator',platform:'Web TV Simulator'})});const data=await resp.json();if(!resp.ok)throw Error(data.detail||'Could not create code');deviceToken=data.device_token;sessionStorage.setItem('tunely_tv_sim_token',deviceToken);expiresAt=Date.now()+data.expires_in_seconds*1000;$('pairCode').textContent=data.pairing_code;$('connection').textContent='Pairing code ready • Awaiting web dashboard';await poll();}catch(ex){error(ex.message);b.disabled=false;}});
$('reset').addEventListener('click',()=>{if(confirm('Reset this simulator? If paired, remove the old device on your dashboard to revoke its token.')){sessionStorage.removeItem('tunely_tv_sim_token');location.reload();}});
setInterval(()=>{if(deviceToken)poll();},4000);
setInterval(()=>{if(expiresAt && !$('pairPanel').hidden){const remaining=Math.max(0,Math.ceil((expiresAt-Date.now())/1000));$('expires').textContent=remaining?`Code expires in ${Math.floor(remaining/60)}:${String(remaining%60).padStart(2,'0')}`:'Code expired. Reset to pair again.';}},1000);
if(deviceToken){$('pairCode').textContent='Session saved';$('expires').textContent='Checking existing device connection';$('startButton').disabled=true;poll();}
})();
