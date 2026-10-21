/* TunelyTV v0.10: private movie/series library. No channel or movie streams are bundled. */
(() => {
'use strict';
const $=id=>document.getElementById(id);
const kinds=['auto','live','movies','series'];
const state={movies:[],series:[],hls:null};
const box=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
const urlOk=raw=>{try{const u=new URL(raw);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password&&u.hostname?u.href:null}catch{return null}};
const imgOk=raw=>{try{const u=new URL(raw);return u.protocol==='https:'&&u.hostname?u.href:null}catch{return null}};
const kindFor=(row,sourceKind='auto')=>{
 if(['live','movies','series'].includes(sourceKind))return sourceKind;
 const name=String(row.name||''),group=String(row.group||''),hint=String(row.mediaHint||'').toLowerCase(),url=String(row.url||'');
 if(/^(series|episode|tvshow|tv_show)$/i.test(hint)||/\bs\d{1,2}e\d{1,3}\b/i.test(name)||/\/(?:series|episode)\//i.test(url)||/\b(?:series|episodes?|tv shows?)\b/i.test(group))return 'series';
 if(/^(movie|film|vod)$/i.test(hint)||/\/(?:movie|film|vod)\//i.test(url)||/\b(?:vod|on[ -]?demand|films?)\b/i.test(group)||/\.(?:mp4|m4v|mov|webm)(?:\?|$)/i.test(url))return 'movies';
 // Standalone group "Movies" often means LIVE movie channels. Don't misclassify it.
 return 'live';
};
function parseM3U(text){
 const rows=[];let m={};
 for(const raw of String(text||'').split(/\r?\n/)){
  const line=raw.trim();if(line.startsWith('#EXTINF:')){
   let comma=-1,quoted=false;for(let i=0;i<line.length;i++){if(line[i]==='"')quoted=!quoted;else if(line[i]===','&&!quoted){comma=i;break;}}
   const attrs={};for(const match of (comma<0?line:line.slice(0,comma)).matchAll(/([a-z][a-z0-9-]*)\s*=\s*"([^"]*)"/gi))attrs[match[1].toLowerCase()]=match[2];
   m={name:(comma<0?attrs['tvg-name']:line.slice(comma+1))||'',group:attrs['group-title']||'Other',mediaHint:attrs['media-type']||attrs['tvg-type']||attrs['type']||'',logo:attrs['tvg-logo']||''};
  }else if(line&&!line.startsWith('#')){const url=urlOk(line);if(url)rows.push({name:m.name||'Item '+(rows.length+1),group:m.group||'Other',mediaHint:m.mediaHint||'',logo:m.logo||'',url});m={};if(rows.length>=5000)break;}
 }
 return rows;
}
async function remoteSource(data,source){
 const url=urlOk(data.url);if(!url)return [];
 const pathname=new URL(url).pathname.toLowerCase();
 if(/\.(m3u8|mp4|m4v|webm|mov)$/i.test(pathname))return [{name:source.name,url,group:source.content_kind==='series'?'Series':'Movies'}];
 const ctl=new AbortController(),timeout=setTimeout(()=>ctl.abort(),12000);
 try{
  const response=await fetch(url,{mode:'cors',credentials:'omit',cache:'no-store',signal:ctl.signal});if(!response.ok)throw Error('Source unavailable');
  const max=3_000_000;if(Number(response.headers.get('content-length'))>max)throw Error('Playlist too large');
  const reader=response.body?.getReader();if(!reader)return [];
  let total=0,parts=[];while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>max){await reader.cancel();throw Error('Playlist too large')}parts.push(value);}
  let bytes=new Uint8Array(total),offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.length;}
  const text=new TextDecoder().decode(bytes);
  if(/#EXT-X-(STREAM-INF|TARGETDURATION|MEDIA-SEQUENCE)/i.test(text))return [{name:source.name,url,group:source.content_kind==='series'?'Series':'Movies'}];
  return parseM3U(text);
 }finally{clearTimeout(timeout)}
}
function seriesGroupTitle(name){
 return String(name||'').replace(/\bS\d{1,2}\s*E\d{1,3}\b.*$/i,'').replace(/\bSeason\s+\d+\s+Episode\s+\d+\b.*$/i,'').replace(/\s*[-_:|]\s*$/,'').trim()||name;
}
function libraryPlaceholder(root,message,link){root.replaceChildren();const holder=box('div','rail-empty');holder.append(box('span','',message));if(link){const a=box('a','library-setup-link','Manage sources ↗');a.href='/account?section=sources';holder.append(a);}root.append(holder);}
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
 libraryPlaceholder(movieRail,'Loading your movie library…');libraryPlaceholder(seriesRail,'Loading your TV series…');
 let sources;
 try{const response=await fetch('/api/playlists',{credentials:'same-origin',cache:'no-store'});if(response.status===401){for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'Sign in to browse movies and series from your own playlists.',true);return;}
  if(!response.ok)throw Error('Source list unavailable');sources=(await response.json()).playlists||[];
 }catch{for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'Unable to load your library right now.');return;}
 if(!sources.length){for(const r of [movieRail,seriesRail])libraryPlaceholder(r,'Your library is empty. Add an authorized M3U source to get started.',true);return;}
 let blocked=false,remoteFailed=0,entries=[];
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
   for(const row of rows){const kind=kindFor(row,contentKind);if(kind!=='movies'&&kind!=='series')continue;const url=urlOk(row.url);if(!url)continue;
    entries.push({kind,url,title:String(row.name||source.name).slice(0,180),logo:row.logo||'',source:source.name,sourceId:source.id});
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
 if(!state.movies.length&&!state.series.length&&remoteFailed){
  const extra=box('p','library-note','Some remote M3U playlists could not be read due to provider CORS or network restrictions. You can upload an authorized M3U file instead.');
  $('movieRail').after(extra);
 }
}
const video=$('libraryVideo'),dialog=$('libraryDialog');
function stop(){video.pause();if(state.hls){state.hls.destroy();state.hls=null;}video.removeAttribute('src');video.load();}
function play(entry){
 stop();const url=urlOk(entry.url);if(!url)return;
 $('libraryMessage').textContent='Playing from '+entry.source+'. Playback depends on provider permission, HTTPS, CORS and compatible codecs.';
 if(/\.m3u8(?:[?#]|$)/i.test(new URL(url).pathname) && window.Hls?.isSupported()){
  state.hls=new Hls({enableWorker:true});state.hls.loadSource(url);state.hls.attachMedia(video);
  state.hls.on(Hls.Events.MANIFEST_PARSED,()=>{void video.play().catch(()=>{$('libraryMessage').textContent='Press Play to start this movie or episode.';});});
 }else{video.src=url;void video.play().catch(()=>{$('libraryMessage').textContent='Press Play to start; this browser may not support the source codec.';});}
}
function open(item){dialog.hidden=false;document.body.style.overflow='hidden';$('libraryTitle').textContent=item.title;
 const episodeRoot=$('libraryEpisodeList');episodeRoot.replaceChildren();if(item.episodes?.length){
  episodeRoot.append(box('h3','','Episodes'));for(const e of item.episodes){const b=box('button','library-episode-button',e.title);b.type='button';b.addEventListener('click',()=>{[...episodeRoot.querySelectorAll('button')].forEach(x=>x.classList.remove('selected'));b.classList.add('selected');play(e);});episodeRoot.append(b);}
  play(item.episodes[0]);episodeRoot.querySelector('button')?.classList.add('selected');
 }else play(item);
}
function close(){stop();dialog.hidden=true;document.body.style.overflow='';}
$('libraryClose').addEventListener('click',close);dialog.addEventListener('click',e=>{if(e.target===dialog)close();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!dialog.hidden)close();});
window.TunelyLibrary={load,kindFor,parseM3U};
})();
