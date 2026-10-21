/* TunelyTV pairing demo. Native apps must store device tokens in OS-secure storage. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const STORAGE='tunely_tv_sim_token';
let deviceToken=sessionStorage.getItem(STORAGE)||'';
let expiresAt=0, revision=0, polling=false, creating=false, expired=false;
function error(message){$('err').textContent=message||'';}
function countdown(){
 if(!expiresAt || $('pairPanel').hidden)return;
 const remaining=Math.max(0,Math.ceil((expiresAt-Date.now())/1000));
 $('expires').textContent=remaining?`Expires in ${Math.floor(remaining/60)}:${String(remaining%60).padStart(2,'0')}`:'Code expired. Refresh to pair again.';
 if(!remaining && !expired){expired=true;$('pairQr').hidden=true;$('qrLoading').hidden=false;$('qrLoading').textContent='Code expired';$('startButton').disabled=false;}
}
async function poll(){
 if(!deviceToken || polling)return;polling=true;
 try{
  const resp=await fetch('/api/device/sync?since='+revision,{headers:{Authorization:'Bearer '+deviceToken},cache:'no-store'});
  if(resp.status===401){deviceToken='';sessionStorage.removeItem(STORAGE);error('This device was removed. Generate a new QR code.');$('startButton').disabled=false;return;}
  if(!resp.ok)throw Error('Connection unavailable ('+resp.status+').');
  const payload=await resp.json();error('');
  if(payload.status==='expired'){$('expires').textContent='Pairing code expired';$('connection').textContent='Code expired';$('startButton').disabled=false;return;}
  if(!payload.paired){$('connection').textContent='Waiting for approval from your phone…';return;}
  $('pairPanel').hidden=true;$('pairedPanel').hidden=false;
  $('eyebrow').textContent='CONNECTED & READY';$('statusHeading').innerHTML='Your TV is <span>connected.</span>';
  $('statusDesc').textContent='Your account approved this device. Updates from your dashboard sync automatically.';
  $('deviceName').textContent=payload.device_name||'TunelyTV';
  $('connection').textContent='Connected · Checking for changes every 4 seconds';
  if(payload.changed){
   revision=payload.revision;$('revision').textContent=revision;
   $('playlistName').textContent=payload.playlist?.name||'No playlist assigned yet';
   $('playlistType').textContent=({m3u_file:'M3U file',m3u_url:'M3U URL',xtream:'Xtream-compatible'})[payload.playlist?.type]||'—';
  }
  $('syncedAt').textContent=new Date().toLocaleTimeString();
 }catch(ex){$('connection').textContent='Retrying secure connection';error(ex.message);}finally{polling=false;}
}
async function enroll(){
 if(creating)return;creating=true;$('startButton').disabled=true;error('');
 try{
  const resp=await fetch('/api/device/enroll',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'TunelyTV Living Room',platform:'Web TV Pairing Preview'})});
  const data=await resp.json();if(!resp.ok)throw Error(data.detail||'Unable to create pairing code.');
  deviceToken=data.device_token;sessionStorage.setItem(STORAGE,deviceToken);
  expiresAt=Date.now()+data.expires_in_seconds*1000;expired=false;
  $('pairPanel').hidden=false;$('pairedPanel').hidden=true;
  $('pairCode').textContent=data.pairing_code;
  $('pairQr').hidden=true;$('qrLoading').hidden=false;$('qrLoading').textContent='Preparing secure QR…';
  $('pairQr').src='/api/pairings/qr?code='+encodeURIComponent(data.pairing_code);
  $('qrStatus').textContent='Scan with your phone camera. The code expires in 10 minutes.';
  $('activationHint').textContent=location.host+'/activate';
  $('connection').textContent='Waiting for approval from your phone…';
  $('startButton').textContent='Generate a new code ↻';$('startButton').disabled=false;
  countdown();await poll();
 }catch(ex){error(ex.message);$('startButton').disabled=false;}
 finally{creating=false;}
}
$('pairQr').addEventListener('load',()=>{$('pairQr').hidden=false;$('qrLoading').hidden=true;});
$('pairQr').addEventListener('error',()=>{$('pairQr').hidden=true;$('qrLoading').hidden=false;$('qrLoading').textContent='QR unavailable; enter the code manually.';});
$('startButton').addEventListener('click',enroll);
$('reset').addEventListener('click',()=>{if(confirm('Disconnect this TV preview? Remove the old paired device under Account → Devices to revoke its server token.')){sessionStorage.removeItem(STORAGE);location.reload();}});
setInterval(poll,4000);setInterval(countdown,1000);
if(deviceToken){
 $('pairCode').textContent='Session remembered';$('qrLoading').textContent='Checking device status…';
 $('expires').textContent='If still pending, generate a new code.';$('startButton').disabled=false;
 poll().then(()=>{if(!$('pairedPanel').hidden)return;enroll();});
}else enroll();
})();
