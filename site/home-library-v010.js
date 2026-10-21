/* TunelyTV v0.10.2: authenticated, source-only movie and episode library. */
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const state={movies:[],series:[],hidden:[],csrf:null,hls:null,active:null};
const make=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=txt;return n;};
const safeUrl=value=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&u.hostname&&!u.username&&!u.password?u.href:null;}catch{return null;}};
const safeImage=value=>{try{const u=new URL(value);return u.protocol==='https:'&&u.hostname&&!u.username&&!u.password?u.href:null;}catch{return null;}};
const hashKey=async url=>{const data=new TextEncoder().encode(url);return [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(n=>n.toString(16).padStart(2,'0')).join('');};
function classify(row,override='auto'){
 const name=String(row.name||''),group=String(row.group||''),hint=String(row.mediaHint||'').toLowerCase(),url=String(row.url||'');
 let path='';try{path=new URL(url).pathname.toLowerCase();}catch{}
 const episode=/(?:\bS\d{1,2}\s*E\d{1,3}\b|\bSeason\s*\d+\s*Episode\s*\d+\b|\b\d{1,2}x\d{2,3}\b)/i.test(name)
  || /^(episode|tv_episode)$/i.test(hint) || /\/series\/(?:[^/]+\/)*[^/]*(?:s\d{1,2}e\d{1,3}|\d+x\d+)[^/]*$/i.test(path);
 const live=/^(live|channel|linear|broadcast|tv)$/i.test(hint)||/\/(?:live|channel|channels)\//i.test(path)
  ||/(?:^|[\s;|,])(?:live tv|live channels?|24\/?7|news|sports|religious|pluto tv)(?:$|[\s;|,])/i.test(group)
  || /\b(?:channel|network|tv\s*channel)\b/i.test(name);
 if(override==='live')return 'live';
 if(episode&&!live)return 'series';
 if(live||(row.tvgId&&!episode&&!row.standalone&&override==='auto'))return 'live';
 if(override==='series')return (row.standalone||/^(series|tvshow|tv_show)$/i.test(hint))?'series':'live';
 if(override==='movies')return 'movies';
 if(/^(movie|film|vod)$/i.test(hint)||/\/(?:movie|film|vod)\//i.test(path)||/\.(?:mp4|m4v|mov|webm)$/i.test(path))return 'movies';
 return 'live';
}
function parseM3U(text){
 const rows=[];let meta={};const seen=new Set();
 for(const raw of String(text||'').split(/\r?\n/)){
  const line=raw.trim();
  if(line.startsWith('#EXTINF:')){
   let comma=-1,quoted=false;for(let i=0;i<line.length;i++){if(line[i]==='"')quoted=!quoted;else if(line[i]===','&&!quoted){comma=i;break;}}
   const attrs={};for(const m of (comma<0?line:line.slice(0,comma)).matchAll(/([a-z][a-z0-9-]*)\s*=\s*"([^"]*)"/gi))attrs[m[1].toLowerCase()]=m[2];
   meta={name:(comma<0?attrs['tvg-name']:line.slice(comma+1))||'',group:attrs['group-title']||'Other',tvgId:attrs['tvg-id']||'',logo:attrs['tvg-logo']||'',mediaHint:attrs['media-type']||attrs['tvg-type']||attrs['type']||''};
  }else if(line&&!line.startsWith('#')){
   const url=safeUrl(line);if(url){const key=(meta.name||'')+'\0'+url;if(!seen.has(key)){seen.add(key);rows.push({...meta,url,name:meta.name||'Item '+(rows.length+1)});}}
   meta={};if(rows.length>=5000)break;
  }
 }
 return rows;
}
async function remoteRows(data,source){
 if(data.type==='m3u_plus'){
  const r=await fetch('/api/playlists/'+encodeURIComponent(source.id)+'/provider-channels',{credentials:'same-origin',cache:'no-store'});
  if(!r.ok)throw Error('Provider metadata unavailable');return (await r.json()).channels||[];
 }
 const url=safeUrl(data.url);if(!url)return [];
 const path=new URL(url).pathname.toLowerCase();
 if(/\.(m3u8|mp4|m4v|webm|mov)$/i.test(path))return [{name:source.name,url,group:'Standalone',standalone:true}];
 const ctrl=new AbortController(),timeout=setTimeout(()=>ctrl.abort(),12000);
 try{
  const r=await fetch(url,{credentials:'omit',mode:'cors',signal:ctrl.signal,cache:'no-store'});
  if(!r.ok)throw Error('Source unavailable');const len=Number(r.headers.get('content-length'));
  if(len>3000000)throw Error('Playlist too large');const reader=r.body?.getReader();if(!reader)return [];
  let size=0,parts=[];while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>3000000){await reader.cancel();throw Error('Playlist too large');}parts.push(value);}
  const buf=new Uint8Array(size);let offset=0;for(const p of parts){buf.set(p,offset);offset+=p.length;}
  const text=new TextDecoder().decode(buf);
  if(/#EXT-X-(STREAM-INF|TARGETDURATION|MEDIA-SEQUENCE)/i.test(text))return [{name:source.name,url,group:'Standalone',standalone:true}];
  return parseM3U(text);
 }finally{clearTimeout(timeout);}
}
function placeholder(root,message,manage=false){root.replaceChildren();const d=make('div','rail-empty');d.append(make('span','',message));if(manage){const a=make('a','library-setup-link','Manage sources ↗');a.href='/account?section=sources';d.append(a);}root.append(d);}
async function csrf(){if(state.csrf)return state.csrf;const r=await fetch('/api/auth/csrf',{credentials:'same-origin'});if(!r.ok)throw Error('Sign in required');state.csrf=(await r.json()).csrf_token;return state.csrf;}
async function refreshHidden(){try{const r=await fetch('/api/library/hidden',{credentials:'same-origin'});if(r.ok)state.hidden=(await r.json()).items||[];}catch{}renderHidden();}
function renderHidden(){const root=$('libraryHiddenList');if(!root)return;root.replaceChildren();$('libraryHiddenCount').textContent=state.hidden.length+' hidden';if(!state.hidden.length){root.append(make('p','library-note','No hidden titles.'));return;}
 for(const item of state.hidden){const row=make('div','library-hidden-row');row.append(make('span','',item.title));const btn=make('button','library-small-button','Restore');btn.type='button';btn.addEventListener('click',async()=>{try{const token=await csrf(),r=await fetch('/api/playlists/'+encodeURIComponent(item.playlist_id)+'/library-hidden/'+encodeURIComponent(item.item_key),{method:'DELETE',credentials:'same-origin',headers:{'X-CSRF-Token':token}});if(!r.ok)throw Error();await load();}catch{alert('Unable to restore title.');}});row.append(btn);root.append(row);}
}
function render(kind,items){const root=$(kind==='movies'?'movieRail':'seriesRail');if(!root)return;root.replaceChildren();if(!items.length){placeholder(root,kind==='movies'?'No movies found in your saved sources. Choose Movies for a film source in Account → Sources.':'No series found. Choose TV Series for episode sources in Account → Sources.',true);return;}
 for(const item of items.slice(0,250)){const btn=make('button','rail-card');btn.type='button';btn.title='Watch '+item.title+' from your own playlist';const art=make('div','rail-art');const image=safeImage(item.logo);if(image){const img=make('img');img.src=image;img.loading='lazy';img.alt='';img.referrerPolicy='no-referrer';img.addEventListener('error',()=>img.remove());art.append(img);}art.append(make('span','art-label',item.title));btn.append(art);btn.append(make('div','card-sub',kind==='movies'?'Movie · '+item.source:(item.episodes?.length||1)+' episode(s) · '+item.source));btn.addEventListener('click',()=>open(item));root.append(btn);}
}
async function load(){const mr=$('movieRail'),sr=$('seriesRail');if(!mr||!sr)return;placeholder(mr,'Loading your movie library…');placeholder(sr,'Loading your TV series…');let sources;
 try{const r=await fetch('/api/playlists',{credentials:'same-origin',cache:'no-store'});if(r.status===401){placeholder(mr,'Sign in to browse your movie library.',true);placeholder(sr,'Sign in to browse your series.',true);return;}if(!r.ok)throw Error();sources=(await r.json()).playlists||[];}catch{placeholder(mr,'Unable to load library.');placeholder(sr,'Unable to load library.');return;}
 await refreshHidden();if(!sources.length){placeholder(mr,'Add an authorized playlist to get started.',true);placeholder(sr,'Add an authorized playlist to get started.',true);return;}
 let blocked=false,failed=0,skipped=0,entries=[];const hidden=new Set(state.hidden.map(x=>x.playlist_id+'\0'+x.item_key));
 const candidates=sources.filter(s=>s.type!=='xtream').slice(0,30);
 for(let i=0;i<candidates.length;i+=4){await Promise.all(candidates.slice(i,i+4).map(async source=>{try{
  const r=await fetch('/api/playlists/'+encodeURIComponent(source.id)+'/playable',{credentials:'same-origin'});if(r.status===403){blocked=true;return;}if(!r.ok)return;const data=await r.json();if(!data.supported)return;
  let rows=[];if(data.type==='m3u_file')rows=data.channels||[];else try{rows=await remoteRows(data,source);}catch{failed++;return;}
  const kind=['auto','live','movies','series'].includes(data.content_kind)?data.content_kind:'auto';
  for(const row of rows){const category=classify(row,kind);if(!['movies','series'].includes(category)){if(['movies','series'].includes(kind))skipped++;continue;}const url=safeUrl(row.url);if(!url)continue;const key=await hashKey(url);if(hidden.has(source.id+'\0'+key))continue;entries.push({kind:category,url,item_key:key,title:String(row.name||source.name).slice(0,180),logo:row.logo||'',source:source.name,sourceId:source.id});}
 }catch{}}));}
 if(blocked){placeholder(mr,'Web playback is not currently included on your plan. Check eligible trials in Account.',true);placeholder(sr,'Web playback is not currently included on your plan.',true);return;}
 state.movies=entries.filter(e=>e.kind==='movies').slice(0,250);const series=new Map();for(const e of entries.filter(e=>e.kind==='series')){const title=String(e.title).replace(/\bS\d{1,2}\s*E\d{1,3}\b.*$/i,'').replace(/\s*[-_:|]\s*$/,'').trim()||e.title;const key=e.sourceId+'\0'+title.toLowerCase();if(!series.has(key))series.set(key,{...e,title,episodes:[]});series.get(key).episodes.push(e);}
 state.series=[...series.values()].slice(0,250);render('movies',state.movies);render('series',state.series);
 document.querySelectorAll('.library-note.dynamic').forEach(n=>n.remove());if(skipped&&!state.series.length){const p=make('p','library-note dynamic',skipped+' items labeled Movies/Series look like live channels. Change their source type in Account → Sources.');sr.after(p);}if(!state.movies.length&&!state.series.length&&failed){mr.after(make('p','library-note dynamic','Some providers block browser playlist access. Use an authorized M3U file if needed.'));}
}
const video=$('libraryVideo'),dialog=$('libraryDialog');
function stop(){if(!video)return;video.pause();if(state.hls){state.hls.destroy();state.hls=null;}video.removeAttribute('src');video.load();}
function play(item){state.active=item;stop();const url=safeUrl(item.url);if(!url)return;$('libraryMessage').textContent='Playing from '+item.source+'. Compatible codec, HTTPS, and provider authorization are required.';
 if(/\.m3u8(?:[?#]|$)/i.test(new URL(url).pathname)&&window.Hls?.isSupported()){state.hls=new Hls({enableWorker:true});state.hls.loadSource(url);state.hls.attachMedia(video);state.hls.on(Hls.Events.MANIFEST_PARSED,()=>void video.play().catch(()=>{$('libraryMessage').textContent='Press Play to start playback.';}));}
 else{video.src=url;void video.play().catch(()=>{$('libraryMessage').textContent='Press Play. This browser might not support this codec.';});}
}
function open(item){dialog.hidden=false;document.body.style.overflow='hidden';$('libraryTitle').textContent=item.title;const root=$('libraryEpisodeList');root.replaceChildren();if(item.episodes?.length){root.append(make('h3','','Episodes'));for(const e of item.episodes){const b=make('button','library-episode-button',e.title);b.type='button';b.addEventListener('click',()=>{root.querySelectorAll('button').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');play(e);});root.append(b);}play(item.episodes[0]);root.querySelector('button')?.classList.add('selected');}else play(item);}
function close(){stop();state.active=null;dialog.hidden=true;document.body.style.overflow='';}
if(dialog){$('libraryClose').addEventListener('click',close);dialog.addEventListener('click',e=>{if(e.target===dialog)close();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!dialog.hidden)close();});video.addEventListener('error',()=>{if(!dialog.hidden)$('libraryMessage').textContent='Playback failed. The provider might be unavailable, or this browser may block the stream.';});
 $('libraryHide').addEventListener('click',async()=>{const item=state.active;if(!item||!confirm('Hide this item? It can be restored later.'))return;try{const token=await csrf();const r=await fetch('/api/playlists/'+encodeURIComponent(item.sourceId)+'/library-hidden',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({item_key:item.item_key,title:item.title,reason:'user_hidden'})});if(!r.ok)throw Error();close();await load();}catch{alert('Unable to hide item. Please sign in again.');}});
 $('libraryHiddenToggle').addEventListener('click',()=>{const panel=$('libraryHiddenPanel');panel.hidden=!panel.hidden;});
}
window.TunelyLibrary={load,kindFor:classify,parseM3U};
})();
