// TunelyTV 0.9.8 optional missing-logo resolver: no bundled station artwork,
// no Google/image scraping, no user-provider credential transfer.
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const button=$('gfLogoRefresh'),status=$('gfLogoStatus');
let enabled=false,busy=false,pending=false,generation=0;
const announce=text=>{status.textContent=text;};
const bridge=()=>window.TunelyGuideBridge;
async function refresh(){
  const api=bridge();
  if(!enabled||!api)return;
  if(busy){pending=true;return;}
  const sourceId=api.sourceId();
  const channels=api.getChannels();
  const items=channels.map((ch,index)=>({ch,index})).filter(({ch})=>!ch.logo);
  if(!items.length){announce('All channels already have provider-supplied images.');return;}
  const requestGeneration=++generation;
  busy=true;button.disabled=true;
  announce('Matching '+items.length+' missing images by channel ID and exact name…');
  try{
    // Only anonymous channel name and TVG ID go to this app's own API.
    // No stream URL, playlist secret, or Xtream credential is transmitted.
    const data=await api.matchMissingLogos(items.slice(0,2000).map(({ch})=>({name:ch.name,tvgId:ch.tvgId||''})));
    if(generation!==requestGeneration||api.sourceId()!==sourceId)return;
    const matches=(data.matches||[]).map(m=>({index:items[m.index]?.index,url:m.url})).filter(m=>Number.isInteger(m.index));
    const added=api.applyLogoMatches(matches,sourceId);
    announce(added+' channel logo matches found. Unmatched channels retain initials; no guessed matches.');
  }catch(e){if(generation===requestGeneration)announce(String(e.message||'Logo lookup failed.'));}
  finally{busy=false;button.disabled=false;if(pending){pending=false;queueMicrotask(()=>void refresh());}}
}
async function start(){
  try{
    const resp=await fetch('/api/channel-logos/config',{credentials:'same-origin',cache:'no-store'});
    if(!resp.ok)throw new Error('Not signed in');
    const config=await resp.json();
    enabled=Boolean(config.enabled);
    button.hidden=!enabled;
    announce(enabled?'Automatic matching enabled for approved logo sources.':'External matching is disabled until artwork rights are confirmed. Playlist and XMLTV logos still work.');
    if(enabled&&bridge()?.getChannels()?.length)void refresh();
  }catch{announce('External logo matching unavailable. Playlist and XMLTV logos still work.');}
}
button.addEventListener('click',()=>void refresh());
window.addEventListener('tunely:playlist-loaded',()=>{generation++;if(enabled)void refresh();});
void start();
})();
