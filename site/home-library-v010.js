/* TunelyTV v0.10: private movie/series library. No channel or movie streams are bundled. */
(() => {
'use strict';
const $=id=>document.getElementById(id);
const kinds=['auto','live','movies','series'];
const state={movies:[],series:[],hls:null,active:null,hidden:[],csrf:null};
const box=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
const urlOk=raw=>{try{const u=new URL(raw);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password&&u.hostname?u.href:null}catch{return null}};
const imgOk=raw=>{try{const u=new URL(raw);return u.protocol==='https:'&&u.hostname?u.href:null}catch{return null}};
// A group like "Movies;Series" is not episode evidence. Some providers use it
// for linear channels (Pluto TV, HBO, etc.). Strong VOD/episode evidence wins;
// otherwise ambiguous playlist rows stay in Live TV.
const kindFor=(row,sourceKind='auto')=>{
 const name=String(row.name||''),group=String(row.group||''),hint=String(row.mediaHint||'').toLowerCase();
 const url=String(row.url||'');let path='';try{path=new URL(url).pathname.toLowerCase();}catch{}
 const episode=/(?:\bS\d{1,2}\s*E\d{1,3}\b|\bSeason\s*\d+\s*Episode\s*\d+\b|\b\d{1,2}x\d{2,3}\b)/i.test(name)
  || /^(episode|tv_episode)$/i.test(hint)
  || /\/series\/(?:[^/]+\/)*[^/]*(?:s\d{1,2}e\d{1,3}|\d+x\d+)[^/]*$/i.test(path);
 const liveHint=/^(live|channel|linear|broadcast|tv)$/i.test(hint)
  || /\/(?:live|channel|channels)\//i.test(path)
  || /(?:^|[\s;|,])(?:live tv|live channels?|24\/?7|news|sports|religious|pluto tv)(?:$|[\s;|,])/i.test(group)
  || /\b(?:channel|network|tv\s*channel)\b/i.test(name);
 // A tvg-id is common for real broadcast channels; do not let a broad group
 // or a source-wide "Series" override turn a named broadcast into an episode.
 const broadcast=liveHint || (Boolean(row.tvgId)&&!episode&&!row.standalone&&sourceKind==='auto');
 if(sourceKind==='live')return 'live';
 if(episode && !liveHint)return 'series';
 if(broadcast)return 'live';
 if(sourceKind==='series')return (row.standalone||/^(series|tvshow|tv_show)$/i.test(hint))?'series':'live';
 if(sourceKind==='movies')return 'movies';
 if(/^(movie|film|vod)$/i.test(hint)||/\/(?:movie|film|vod)\//i.test(path)||/\.(?:mp4|m4v|mov|webm)(?:$|\?)/i.test(path))return 'movies';
 // Bare HLS playlists are ambiguous and should not automatically be VOD.
 return 'live';
};
function parseM3U(text){
 const rows=[];let m={};const seen=new Set();
 for(const raw of String(text||'').split(/\r?\n/)){
  const line=raw.trim();if(line.startsWith('#EXTINF:')){
   let comma=-1,quoted=false;for(let i=0;i<line.length;i++){if(line[i]==='"')quoted=!quoted;else if(line[i]===','&&!quoted){comma=i;break;}}
   const attrs={};for(const match of (comma<0?line:line.slice(0,comma)).matchAll(/([a-z][a-z0-9-]*)\s*=\s*"([^"]*)"/gi))attrs[match[1].toLowerCase()]=match[2];
   m={name:(comma<0?attrs['tvg-name']:line.slice(comma+1))||'',group:attrs['group-title']||'Other',tvgId:attrs['tvg-id']||'',mediaHint:attrs['media-type']||attrs['tvg-type']||attrs['type']||'',logo:attrs['tvg-logo']||''};
  }else if(line&&!line.startsWith('#')){const url=urlOk(line);if(url){const key=(m.name||'')+'\0'+url;if(!seen.has(key)){seen.add(key);rows.push({name:m.name||'Item '+(rows.length+1),group:m.group||'Other',tvgId:m.tvgId||'',mediaHint:m.mediaHint||'',logo:m.logo||'',url});}}m={};if(rows.length>=5000)break;}
 }
 return rows;
}
async function remoteSource(data,source){
 const url=urlOk(data.url);if(!url)return [];
 const pathname=new URL(url).pathname.toLowerCase();
 if(/\.(m3u8|mp4|m4v|webm|mov)$/i.test(pathname))return [{name:source.name,url,group:'Standalone',standalone:true}];
 const ctl=new AbortController(),timeout=setTimeout(()=>ctl.abort(),12000);
 try{
  const response=await fetch(url,{mode:'cors',credentials:'omit',cache:'no-store',signal:ctl.signal});if(!response.ok)throw Error('Source unavailable');
  const max=3_000_000;if(Number(response.headers.get('content-length'))>max)throw Error('Playlist too large');
  const reader=response.body?.getReader();if(!reader)return [];
  let total=0,parts=[];while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>max){await reader.cancel();throw Error('Playlist too large')}parts.push(value);}
  let bytes=new Uint8Array(total),offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.length;}
  const text=new TextDecoder().decode(bytes);
  if(/#EXT-X-(STREAM-INF|TARGETDURATION|MEDIA-SEQUENCE)/i.test(text))return [{name:source.name,url,group:'Standalone',standalone:true}];
  return parseM3U(text);
 }finally{clearTimeout(timeout)}
}
function seriesGroupTitle(name){
 return String(name||'').replace(/\bS\d{1,2}\s*E\d{1,3}\b.*$/i,'').replace(/\bSeason\s+\d+\s+Episode\s+\d+\b.*$/i,'').replace(/\s*[-_:|]\s*$/,'').trim()||name;
}
function libraryPlaceholder(root,message,link){root.replaceChildren();const holder=box('div','rail-empty');holder.append(box('span','',message));if(link){const a=box('a','library-setup-link','Manage sources ↗');a.href='/account?section=sources';holder.append(a);}root.append(holder);}
async function mediaKey(url){
 const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(url));
 return [...new Uint8Array(digest)].map(n=>n.toString(16).padStart(2,'0')).join('');
}
async function ensureCsrf(){
 if(state.csrf)return state.csrf;
 const response=await fetch('/api/auth/csrf',{credentials:'same-origin',cache:'no-store'});
 if(!response.ok)throw Error('Sign in to manage your hidden library');
 state.csrf=(await response.json()).csrf_token;
 return state.csrf;
}
async function refreshHidden(){try{
 const r=await fetch('/api/library/hidden',{credentials:'same-origin'});
 if(r.ok)state.hidden=(await r.json()).items||[];
 }catch{/* Keep library visible on intermittent errors. */}
 renderHidden();}
function renderHidden(){
 const root=$('libraryHiddenList');if(!root)return;root.replaceChildren();
 $('libraryHiddenCount').textContent=state.hidden.length+' hidden';
 if(!state.hidden.length){root.append(box('p','library-note','No hidden titles.'));return;}
 for(const item of state.hidden){const r=box('div','library-hidden-row');
  r.append(box('span','',item.title));const b=box('button','library-small-button','Restore');
  b.type='button';b.addEventListener('click',async()=>{try{
   const csrf=await ensureCsrf();const response=await fetch('/api/playlists/'+encodeURIComponent(item.playlist_id)+'/library-hidden/'+encodeURIComponent(item.item_key),
    {method:'DELETE',credentials:'same-origin',headers:{'X-CSRF-Token':csrf}});
   if(!response.ok)throw Error('Could not restore');await load();
  }catch{alert('Could not restore this item. Refresh your account login and try again.');}});
  r.append(b);root.append(r);
 }
}
function render(kind,items){const root=$(kind==='movies'?'movieRail':'seriesRail');root.replaceChildren();if(!items.length){libraryPlaceholder(root,kind==='movies'?'No movies found in your saved playlists. Choose Movies for a film source in Account → Sources.':'No TV series found in your saved playlists. Choose TV Series for episode sources in Account → Sources.',true);return;}
 for(const item of items.slice(0,250)){
  const btn=box('button','rail-card');btn.type='button';btn.title='Watch '+item.title+' from your own playlist';
  const art=box('div','rail-art');const image=imgOk(item.logo);if(image){const pic=box('img');pic.src=image;pic.alt='';pic.loading='lazy';pic.referrerPolicy='no-referrer';pic.addEventListener('error',()=>pic.remove());art.append(pic);}
  art.append(box('span','art-label',item.title));btn.append(art);
  btn.append(box('div','card-sub',kind==='movies'?'Movie · '+item.source:((item.episodes?.length||1)+' episode(s) · '+item.source)));
  btn.addEventListener('click',()=>open(item));root.append(btn);
 }
}
async function load(){
 const movieRail=$('movieRail'),seriesRail=$('seriesRail');
 document.querySelectorAll('.library-note.dynamic').forEach(n=>n.remove());
 libraryPlaceholder(movieRail,'Loading your movie library…');libraryPlaceholder(seriesRail,'Loading your TV series…');
 let sources;
 try{const response=await fetch('/api/playlists',{credentials:'same-origin',cache:'no-store'});if(response.status===401){for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'Sign in to browse movies and series from your own playlists.',true);return;}
  if(!response.ok)throw Error('Source list unavailable');sources=(await response.json()).playlists||[];
 }catch{for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'Unable to load your library right now.');return;}
 await refreshHidden();
 if(!sources.length){for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'Your library is empty. Add an authorized M3U source to get started.',true);return;}
 let blocked=false,remoteFailed=0,liveSkipped=0,entries=[];const hiddenSet=new Set(state.hidden.map(x=>x.playlist_id+'\0'+x.item_key));
 // Limit memory/network pressure; all requests are same-origin authorized, remote playlists are browser-fetched only.
 const candidates=sources.filter(s=>s.type!=='xtream').slice(0,30);
 for(let i=0;i<candidates.length;i+=4){await Promise.all(candidates.slice(i,i+4).map(async source=>{
  try{
   const r=await fetch('/api/playlists/'+encodeURIComponent(source.id)+'/playable',{credentials:'same-origin'});
   if(r.status===403){blocked=true;return}if(!r.ok)return;
   const data=await r.json();if(!data.supported)return;
   let rows=[];if(data.type==='m3u_file')rows=data.channels||[];
   else try{rows=await remoteSource(data,source);}catch{remoteFailed++;return;}
   const contentKind=kinds.includes(data.content_kind)?data.content_kind:'auto';
   for(const row of rows){const kind=kindFor(row,contentKind);if(kind!=='movies'&&kind!=='series'){if(['series','movies'].includes(contentKind))liveSkipped++;continue;}const url=urlOk(row.url);if(!url)continue;
    const item_key=await mediaKey(url);if(hiddenSet.has(source.id+'\0'+item_key))continue;
    entries.push({kind,url,item_key,title:String(row.name||source.name).slice(0,180),logo:row.logo||'',source:source.name,sourceId:source.id});
   }
  }catch{/* Keep other authorized sources usable. */}
 }));}
 if(blocked){for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'This account does not currently have web playback access. Check your plan or eligible trial.',true);return;}
 state.movies=entries.filter(x=>x.kind==='movies').slice(0,250);
 const series=new Map();for(const e of entries.filter(x=>x.kind==='series')){
  const title=seriesGroupTitle(e.title),key=e.sourceId+'\0'+title.toLowerCase();
  if(!series.has(key))series.set(key,{...e,title,episodes:[]});series.get(key).episodes.push(e);
 }
 state.series=[...series.values()].slice(0,250);
 render('movies',state.movies);render('series',state.series);
 if(liveSkipped && !state.series.length){
  const note=box('p','library-note dynamic',liveSkipped+' entries from sources labeled Movies/Series look like live channels, not episodes. Change that source to Automatic or Live TV in Account → Sources to see them in the guide.');
  $('seriesRail').after(note);
 }
 if(!state.movies.length&&!state.series.length&&remoteFailed){
  const extra=box('p','library-note dynamic','Some remote M3U playlists could not be read due to provider CORS or network restrictions. You can upload an authorized M3U file instead.');
  $('movieRail').after(extra);
 }
}
const video=$('libraryVideo'),dialog=$('libraryDialog');
function stop(){video.pause();if(state.hls){state.hls.destroy();state.hls=null;}video.removeAttribute('src');video.load();}
function play(entry){
 state.active=entry;stop();const url=urlOk(entry.url);if(!url)return;
 $('libraryMessage').textContent='Playing from '+entry.source+'. Playback depends on provider permission, HTTPS, CORS and compatible codecs.';
 if(/\.m3u8(?:[?#]|$)/i.test(new URL(url).pathname) && window.Hls?.isSupported()){
  state.hls=new Hls({enableWorker:true});state.hls.loadSource(url);state.hls.attachMedia(video);
  state.hls.on(Hls.Events.MANIFEST_PARSED,()=>{void video.play().catch(()=>{$('libraryMessage').textContent='Press Play to start this movie or episode.';});});
  state.hls.on(Hls.Events.ERROR,(_,data)=>{if(data?.fatal && !dialog.hidden){$('libraryMessage').textContent='The stream could not play. It may be temporarily offline, or blocked by your provider, browser CORS restrictions, or codecs. You can hide it from your library and restore it later.';}});
 }else{video.src=url;void video.play().catch(()=>{$('libraryMessage').textContent='Press Play to start; this browser may not support the source codec.';});}
}
function open(item){state.active=null;dialog.hidden=false;document.body.style.overflow='hidden';$('libraryTitle').textContent=item.title;
 const episodeRoot=$('libraryEpisodeList');episodeRoot.replaceChildren();if(item.episodes?.length){
  episodeRoot.append(box('h3','','Episodes'));for(const e of item.episodes){const b=box('button','library-episode-button',e.title);b.type='button';b.addEventListener('click',()=>{[...episodeRoot.querySelectorAll('button')].forEach(x=>x.classList.remove('selected'));b.classList.add('selected');play(e);});episodeRoot.append(b);}
  play(item.episodes[0]);episodeRoot.querySelector('button')?.classList.add('selected');
 }else play(item);
}
function close(){stop();state.active=null;dialog.hidden=true;document.body.style.overflow='';}
$('libraryClose').addEventListener('click',close);dialog.addEventListener('click',e=>{if(e.target===dialog)close();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!dialog.hidden)close();});
video.addEventListener('error',()=>{if(!dialog.hidden){$('libraryMessage').textContent='Playback failed. This can mean the link is unavailable, or your browser is blocked by CORS, region, authentication, or codec restrictions. You may hide this item without deleting the playlist.';}});
$('libraryHide').addEventListener('click',async()=>{
 const entry=state.active;if(!entry)return;
 if(!confirm('Hide this item from your library? This does not delete the source, and you can restore it later.'))return;
 try{
  await ensureCsrf();
  const r=await fetch('/api/playlists/'+encodeURIComponent(entry.sourceId)+'/library-hidden',
   {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},
    body:JSON.stringify({item_key:entry.item_key,title:entry.title,reason:'user_hidden'})});
  if(!r.ok)throw Error();close();await load();
 }catch{alert('Unable to hide item. Please sign in again and try.');}
});
$('libraryHiddenToggle').addEventListener('click',()=>{const p=$('libraryHiddenPanel');p.hidden=!p.hidden;});
window.TunelyLibrary={load,kindFor,parseM3U};
})();
