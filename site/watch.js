// TunelyTV private web player v0.7. User-authorized sources only: no bundled content,
// server-side proxy, playlist token logging, or DRM / CORS circumvention.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const sourcePick = $('sourcePick');
  const listNode = $('channelList');
  const video = $('video');
  const tabs = [...document.querySelectorAll('[data-tab]')];
  const quicks = [...document.querySelectorAll('[data-filter]')];
  const localPreview = location.protocol === 'file:';
  const state = { sources: [], channels: [], current: null, sourceId: '', filter: 'all', category: 'all', favorites: new Set(), recent: [], programs: new Map(), guideChannels: new Map(), guideLogos: new Map(), hls: null, requestId: 0, localEntries: [], guideView: 'grid', guideStart: Math.floor(Date.now()/1800000)*1800000, gridLimit: 120, loggedIn:false, webPermitted:localPreview, prefsSerial:0, guideUrl:'', guideSaveId:'', lastEpgRefresh:0, detectedGuideUrls:[], localGuideUrls:[], epgOrigin:'none', cloudReady:false, activeDetail:null };

  const warning = 'Playback requires HTTPS, provider browser/CORS permission, and a compatible codec. TunelyTV does not supply, proxy, or restream any content.';
  const setNotice = (text, kind='') => { const n=$('notice'); n.textContent=text; n.className='notice'+(kind?' '+kind:''); };
  const decodeName = name => String(name || '').trim().slice(0, 140);
  const safeUrl = value => { try { const u = new URL(value); return ['https:','http:'].includes(u.protocol) && !u.username && !u.password ? u.href : null; } catch { return null; } };
  const requestAllowed = href => !(location.protocol === 'https:' && href.startsWith('http:'));
  // Same-origin authenticated XMLTV reader is allowed only for a saved
  // M3U Plus playlist. An arbitrary external HTTP guide remains blocked.
  const providerGuidePath = /^\/api\/playlists\/[0-9a-f-]{36}\/provider-guide$/i;
  const safeGuideUrl = raw => {
    const text=String(raw||'').trim();
    if(providerGuidePath.test(text))return new URL(text,location.origin).href;
    const external=safeUrl(text);
    if(!external)return null;
    const parsed=new URL(external);
    if(parsed.origin===location.origin && providerGuidePath.test(parsed.pathname) && !parsed.search)return parsed.href;
    return external;
  };
  const isInternalGuide = raw => {try{const u=new URL(raw,location.origin);return u.origin===location.origin && providerGuidePath.test(u.pathname) && !u.search;}catch{return false;}};
  const norm = s => String(s || '').trim().toLowerCase().replace(/\s+/g,' ');
  const hash = raw => { let h = 2166136261; for(let i=0;i<raw.length;i++){h ^= raw.charCodeAt(i);h = Math.imul(h,16777619);}return (h>>>0).toString(36); };
  const safeRead = key => { try { const x=JSON.parse(localStorage.getItem(key)||'[]'); return Array.isArray(x) ? x.filter(a=>typeof a==='string').slice(0,200) : []; } catch { return []; } };
  const safeSave = (key,value) => { try { localStorage.setItem(key,JSON.stringify(value)); } catch { setNotice('Browser storage is blocked. Favorites will only last until this page closes.','warn'); } };
  const favKey = () => 'tunelytv.player.favorites.v1.'+state.sourceId;
  const recentKey = () => 'tunelytv.player.recent.v1.'+state.sourceId;
  const cid = c => { const raw=c.tvgId ? norm(c.tvgId) : norm((c.group||'Other')+'|'+c.name); return (c.tvgId?'id:':'n:')+hash(raw)+'-'+hash([...raw].reverse().join('')); };
  function cloudEnabled(id=state.sourceId){return state.loggedIn && id && id!=='local';}
  function updateSyncStatus(message){$('syncStatus').textContent=message;}
  // The existing backend rotates the session CSRF token. Serialize mutations
  // to prevent simultaneous favorite/recent saves invalidating each other.
  let mutationQueue=Promise.resolve();
  function apiMutation(url, method, body){
    const queued=mutationQueue.then(async()=>{
      const csrfResp=await fetch('/api/auth/csrf',{credentials:'same-origin',cache:'no-store'});
      if(!csrfResp.ok)throw new Error('Sign in again to save account changes.');
      const {csrf_token}=await csrfResp.json();
      const result=await fetch(url,{method,credentials:'same-origin',headers:{'X-CSRF-Token':csrf_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
      if(!result.ok){let message='Saving failed ('+result.status+').';try{message=(await result.json()).detail||message;}catch{}throw new Error(String(message));}
      return result.json();
    });
    mutationQueue=queued.catch(()=>{});
    return queued;
  }
  async function loadCloudPreferences(id){
    if(!cloudEnabled(id)){updateSyncStatus('Favorites and recents stored on this browser.');return;}
    const serial=++state.prefsSerial;
    updateSyncStatus('Loading your cloud favorites & recents…');
    try{
      const resp=await fetch('/api/playlists/'+encodeURIComponent(id)+'/preferences',{credentials:'same-origin',cache:'no-store'});
      if(!resp.ok)throw new Error('Preferences service returned '+resp.status);
      const data=await resp.json();
      if(serial!==state.prefsSerial||id!==state.sourceId)return;
      state.favorites=new Set(data.favorites||[]);state.recent=(data.recent||[]).slice(0,30);
      safeSave(favKey(),[...state.favorites]);safeSave(recentKey(),state.recent);
      state.cloudReady=true;renderChannels();renderGuide();updateFavoriteButton();
      updateSyncStatus('✓ Favorites & recents synced to this account.');
    }catch(e){if(serial!==state.prefsSerial||id!==state.sourceId)return;state.cloudReady=false;updateSyncStatus('Cloud sync unavailable; showing browser preferences.');setNotice('Cloud preferences could not be loaded. '+e.message,'warn');}
  }
  async function persistFavorite(channel,selected,sourceId){
    if(!cloudEnabled(sourceId))return;
    try{await apiMutation('/api/playlists/'+encodeURIComponent(sourceId)+'/favorites','POST',{channel_key:cid(channel),favorite:selected});if(sourceId===state.sourceId)updateSyncStatus('✓ Favorites synced to your account.');}
    catch(e){if(sourceId===state.sourceId){updateSyncStatus('Cloud save failed. Your browser still has this selection.');setNotice(e.message,'warn');}}
  }
  async function persistRecent(channel,sourceId){
    if(!cloudEnabled(sourceId))return;
    try{await apiMutation('/api/playlists/'+encodeURIComponent(sourceId)+'/recent','POST',{channel_key:cid(channel)});}
    catch(e){if(sourceId===state.sourceId)updateSyncStatus('Recent-channel cloud save failed; browser history is intact.');}
  }
  const logoText = name => (name||'TV').trim().split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase().slice(0,2);
  // Treat playlist and XMLTV logo links as untrusted data. Never embed HTML or
  // fetch through our servers. HTTPS only; text initials remain when unavailable.
  const safeLogo = value => {
    const raw=String(value||'').trim();
    if(!raw||raw.length>2048)return '';
    const url=safeUrl(raw);
    return url&&url.startsWith('https://')?url:'';
  };
  function logoFor(ch){
    if(ch.logo)return safeLogo(ch.logo);
    const guideId=ch.tvgId||state.guideChannels.get(norm(ch.tvgName))||state.guideChannels.get(norm(ch.name));
    return safeLogo(state.guideLogos.get(guideId))||safeLogo(ch.externalLogo);
  }
  function channelAvatar(ch, css){
    const wrap=node('span',css);
    const fallback=node('span','channel-avatar-fallback',logoText(ch.name));
    wrap.append(fallback);
    const url=logoFor(ch);
    if(url){
      const img=document.createElement('img');img.className='channel-avatar-image';
      img.loading='lazy';img.decoding='async';img.referrerPolicy='no-referrer';
      img.alt='';img.hidden=true;
      img.addEventListener('load',()=>{img.hidden=false;fallback.hidden=true;});
      img.addEventListener('error',()=>{img.remove();fallback.hidden=false;});
      img.src=url;wrap.append(img);
    }
    return wrap;
  }
  const node = (tag, css, text) => { const el=document.createElement(tag); if(css)el.className=css; if(text!==undefined)el.textContent=text; return el; };

  function setTab(which){
    tabs.forEach(t => { const selected=t.dataset.tab===which; t.classList.toggle('active',selected); t.setAttribute('aria-selected',String(selected)); });
    document.querySelectorAll('.tab-panel').forEach(p=>{const show=p.id==='panel-'+which;p.hidden=!show;p.classList.toggle('active',show);});
  }
  tabs.forEach(t=>t.addEventListener('click',()=>setTab(t.dataset.tab)));
  const mobileChannels=()=>window.matchMedia('(max-width: 790px)').matches;
  function closeMobileChannels(){
    $('channelBrowser').classList.remove('drawer-open');
    $('channelBackdrop').hidden=true;
    $('browseButton').setAttribute('aria-expanded','false');
  }
  function scrollBrowser(){
    if(mobileChannels()){
      $('channelBrowser').classList.add('drawer-open');
      $('channelBackdrop').hidden=false;
      $('browseButton').setAttribute('aria-expanded','true');
      $('filter').focus({preventScroll:true});
    }else $('channelBrowser').scrollIntoView({behavior:'smooth',block:'start'});
  }
  $('browseButton').setAttribute('aria-expanded','false');
  $('browseButton').setAttribute('aria-controls','channelBrowser');
  $('browseButton').addEventListener('click',()=>{
    if(mobileChannels()&&$('channelBrowser').classList.contains('drawer-open'))closeMobileChannels();
    else scrollBrowser();
  });
  $('emptyBrowse').addEventListener('click',()=>window.TunelyGuideFocus?.open());
  $('closeMobileChannels').addEventListener('click',closeMobileChannels);
  $('channelBackdrop').addEventListener('click',closeMobileChannels);
  window.addEventListener('resize',()=>{if(!mobileChannels())closeMobileChannels();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMobileChannels();});
  const showSetup = () => {setTab('setup');document.querySelector('.below-player').scrollIntoView({behavior:'smooth',block:'start'});};

  function setSource(id){
    state.prefsSerial++;state.cloudReady=false;state.sourceId=id;state.favorites=new Set(safeRead(favKey()));state.recent=safeRead(recentKey());updateSyncStatus(cloudEnabled()?'Account playlist: loading cloud preferences…':'Local browser preferences.');
    if(!id){state.favorites=new Set();state.recent=[];}renderChannels();
  }
  function toggleFavorite(channel){
    if(!channel)return;
    const key=cid(channel);
    if(state.favorites.has(key))state.favorites.delete(key);else state.favorites.add(key);
    safeSave(favKey(),[...state.favorites]);void persistFavorite(channel,state.favorites.has(key),state.sourceId);updateFavoriteButton();renderChannels();renderGuide();renderMiniGuide();
  }
  function updateFavoriteButton(){
    const button=$('currentFavorite');const exists=!!state.current;button.disabled=!exists;
    const on=exists&&state.favorites.has(cid(state.current));button.classList.toggle('is-favorite',on);button.textContent=on?'♥':'♡';button.setAttribute('aria-label',on?'Remove channel from favorites':'Add channel to favorites');
  }
  function markRecent(channel){ const key=cid(channel);state.recent=[key,...state.recent.filter(x=>x!==key)].slice(0,30);safeSave(recentKey(),state.recent);void persistRecent(channel,state.sourceId); }
  quicks.forEach(btn=>btn.addEventListener('click',()=>{state.filter=btn.dataset.filter;quicks.forEach(x=>{const on=x===btn;x.classList.toggle('active',on);x.setAttribute('aria-pressed',String(on));});renderChannels();renderGuide();}));
  $('filter').addEventListener('input',()=>{renderChannels();renderGuide();});$('categoryPick').addEventListener('change',()=>{state.category=$('categoryPick').value;renderChannels();renderGuide();});
  $('clearPrefs').addEventListener('click',async()=>{
    if(!state.sourceId){setNotice('Choose a playlist first.','warn');return;}
    if(!confirm('Clear favorites and recent channels for this playlist'+(cloudEnabled()?' across your signed-in browsers':' on this browser')+'?'))return;
    state.favorites.clear();state.recent=[];safeSave(favKey(),[]);safeSave(recentKey(),[]);renderChannels();renderGuide();renderMiniGuide();updateFavoriteButton();
    if(cloudEnabled()){try{await apiMutation('/api/playlists/'+encodeURIComponent(state.sourceId)+'/preferences','DELETE');updateSyncStatus('✓ Cloud preferences cleared.');}catch(e){setNotice('Cloud clear failed: '+e.message,'error');return;}}
    setNotice('Favorites and recent-channel selections cleared.');
  });
  function renderCategories(){
    const pick=$('categoryPick'); const names=[...new Set(state.channels.map(x=>x.group||'Other'))].sort((a,b)=>a.localeCompare(b));
    pick.replaceChildren(new Option('All categories','all'));names.forEach(g=>pick.add(new Option(g,g)));
    if(!names.includes(state.category))state.category='all';pick.value=state.category;
  }
  function visibleChannels(){
    const q=norm($('filter').value);
    let values=state.channels.filter(x=>
      (state.category==='all'||(x.group||'Other')===state.category) &&
      (!q||norm(x.name+' '+x.group).includes(q)) &&
      (state.filter!=='favorites'||state.favorites.has(cid(x))) &&
      (state.filter!=='recent'||state.recent.includes(cid(x)))
    );
    if(state.filter==='recent')values.sort((a,b)=>state.recent.indexOf(cid(a))-state.recent.indexOf(cid(b)));
    return values;
  }
  function renderChannels(){
    $('channelCount').textContent=String(state.channels.length);
    $('favCount').textContent=String(state.channels.filter(x=>state.favorites.has(cid(x))).length);
    listNode.replaceChildren();
    const filtered=visibleChannels();
    if(!filtered.length){
      const empty=node('div','empty',state.channels.length ? (state.filter==='favorites'?'No favorites yet. Tap ♡ beside a channel.':state.filter==='recent'?'Your recently played channels will appear here.':'No channels match these filters.') : 'No channels yet. Choose a playlist above, or add one from the setup tab.');
      listNode.append(empty);return;
    }
    const fragment=document.createDocumentFragment();
    for(const ch of filtered.slice(0,900)){
      const ico=channelAvatar(ch,'channel-icon');ico.setAttribute('aria-hidden','true');
      const info=node('div','channel-info');info.append(node('strong','channel-name',ch.name),node('small','channel-group',ch.group||'Other'));
      const play=node('button','channel-play','');play.type='button';play.className='channel'; // replace wrapper with actual button for keyboard
      play.append(ico,info);if(state.current&&cid(state.current)===cid(ch))play.classList.add('selected');
      play.setAttribute('aria-label','Play '+ch.name);play.addEventListener('click',()=>playChannel(ch));
      const fav=node('button','favorite-btn'+(state.favorites.has(cid(ch))?' saved':''),state.favorites.has(cid(ch))?'♥':'♡');fav.type='button';fav.setAttribute('aria-label',(state.favorites.has(cid(ch))?'Remove ':'Add ')+ch.name+(state.favorites.has(cid(ch))?' from':' to')+' favorites');fav.addEventListener('click',()=>toggleFavorite(ch));
      const wrap=node('div','channel-wrap');wrap.append(play,fav);fragment.append(wrap);
    }
    listNode.append(fragment);
    if(filtered.length>900)listNode.append(node('p','empty','Showing the first 900 matching channels. Refine your search to find others.'));
  }

  function stop(){
    if(state.hls){state.hls.destroy();state.hls=null;}
    video.pause();video.removeAttribute('src');video.load();video.hidden=true;$('placeholder').hidden=false;
    state.current=null;$('playingName').textContent='Select a channel';$('playingStatus').textContent='No stream selected';updateFavoriteButton();renderChannels();renderAbout();renderGuide();renderMiniGuide();
  }
  function playChannel(ch){
    if(!state.webPermitted){setNotice('Web playback requires an eligible Plus trial or paid account. Open Account → Plans & Billing.','warn');return;}
    window.TunelyMultiView?.close();
    const href=safeUrl(ch.url);
    if(!href){setNotice('This channel has an invalid stream URL.','error');return;}
    if(!requestAllowed(href)){setNotice('This stream uses HTTP, which browsers typically block on HTTPS websites. Ask your licensed provider for an HTTPS URL.','warn');return;}
    stop();state.current=ch;markRecent(ch);renderChannels();updateFavoriteButton();renderAbout();renderGuide();renderMiniGuide();resetTrackSettings();
    $('playingName').textContent=ch.name;$('playingStatus').textContent='Connecting…';$('placeholder').hidden=true;video.hidden=false;
    if(mobileChannels()&&!window.TunelyGuideFocus?.isOpen()){closeMobileChannels();$('videoArea').scrollIntoView({behavior:'smooth',block:'start'});}
    setNotice('Connecting directly to the source. '+warning);
    const path=new URL(href).pathname.toLowerCase();
    const directMedia=/\.(mp4|m4v|webm|ogv|mov|mp3|aac)$/i.test(path);
    if(directMedia || video.canPlayType('application/vnd.apple.mpegurl')){
      video.src=href;video.play().catch(()=>setNotice('Use the video controls to begin playback. Autoplay may be blocked.','warn'));
    } else if (window.Hls && window.Hls.isSupported()){
      let recovered=false;
      const player=new window.Hls({enableWorker:true,maxBufferLength:24,backBufferLength:15});state.hls=player;
      player.on(window.Hls.Events.ERROR,(_event,error)=>{
        if(!error.fatal)return;
        $('playingStatus').textContent='Playback unavailable';
        setNotice('Stream unavailable ('+(error.details||'playback error')+'). Check provider permission, HTTPS, CORS, and codec support. No bypass or proxy is available.','error');
        if(error.type===window.Hls.ErrorTypes.MEDIA_ERROR&&!recovered){recovered=true;player.recoverMediaError();}
      });
      player.loadSource(href);player.attachMedia(video);
      player.on(window.Hls.Events.MANIFEST_PARSED,()=>{updateTrackSettings();video.play().catch(()=>setNotice('Press play to start the stream. Your browser may block autoplay.','warn'));});
      player.on(window.Hls.Events.AUDIO_TRACKS_UPDATED,updateTrackSettings);
      player.on(window.Hls.Events.SUBTITLE_TRACKS_UPDATED,updateTrackSettings);
    } else {
      $('playingStatus').textContent='Browser playback unsupported';
      setNotice('HLS playback is not available. Check browser HLS support and that hls.js loaded, or use another browser.','error');
    }
  }
  $('stopBtn').addEventListener('click',()=>{stop();setNotice(warning);});
  $('fullscreen').addEventListener('click',()=>{const el=$('videoArea');if(document.fullscreenElement){document.exitFullscreen?.();return;}if(!video.hidden&&video.webkitEnterFullscreen&&/iPad|iPhone/.test(navigator.userAgent)){video.webkitEnterFullscreen();return;}el.requestFullscreen?.().catch(()=>setNotice('Fullscreen is unavailable in this browser.','warn'));});
  $('currentFavorite').addEventListener('click',()=>toggleFavorite(state.current));
  video.addEventListener('playing',()=>{$('playingStatus').textContent='Playing live';});
  video.addEventListener('volumechange',()=>{$('muteBtn').textContent=video.muted?'♩':'♫';$('muteBtn').setAttribute('aria-label',video.muted?'Unmute video':'Mute video');});
  video.addEventListener('waiting',()=>{if(state.current)$('playingStatus').textContent='Buffering…';});
  video.addEventListener('error',()=>{if(!video.currentSrc)return;$('playingStatus').textContent='Playback failed';setNotice('Browser playback failed. Confirm your provider permits playback via HTTPS/CORS and supports this browser’s video codecs.','error');});

  function parseAttributes(extinf){
    const result={};const patt=/([A-Za-z][A-Za-z0-9-]*)\s*=\s*"([^"]*)"/g;let match;
    while((match=patt.exec(extinf))){const key=match[1].toLowerCase();result[key]=match[2].slice(0,key==='tvg-logo'?2048:160);}
    return result;
  }
  // Only use XMLTV links explicitly advertised in the user's own M3U header.
  // No provider URL guessing, central guide scraping, or server-side proxying.
  function discoverM3uGuideUrls(text){
    const header=String(text||'').split(/\r?\n/).slice(0,12).map(s=>s.trim().replace(/^\uFEFF/,''))
      .find(s=>s.toUpperCase().startsWith('#EXTM3U'))?.slice(0,16000)||'';
    const out=[];
    const pattern=/(?:^|\s)(?:x-tvg-url|url-tvg|tvg-url)\s*=\s*(["'])(.*?)\1/gi;
    for(const attr of header.matchAll(pattern)){
      for(const part of attr[2].split(/[,;]/)){
        const url=safeUrl(part.trim());
        if(url&&!out.includes(url))out.push(url);
        if(out.length>=3)return out;
      }
    }
    return out;
  }
  function parseM3U(text){
    const results=[];let meta=null;
    for(const raw of text.split(/\r?\n/)){
      const line=raw.trim();
      if(line.startsWith('#EXTINF:')){
        let quoted=false, comma=-1; for(let i=0;i<line.length;i++){if(line[i]==='\"')quoted=!quoted;else if(line[i]===','&&!quoted){comma=i;break;}}
        const att=parseAttributes(comma<0?line:line.slice(0,comma));
        meta={name:decodeName(comma>=0?line.slice(comma+1):att['tvg-name']),group:decodeName(att['group-title']||'Other'),tvgId:decodeName(att['tvg-id']||''),tvgName:decodeName(att['tvg-name']||''),logo:safeLogo(att['tvg-logo'])};
      } else if(line && !line.startsWith('#')){
        const url=safeUrl(line);
        if(url)results.push({name:(meta?.name||'Channel '+(results.length+1)),url,group:meta?.group||'Other',tvgId:meta?.tvgId||'',tvgName:meta?.tvgName||'',logo:meta?.logo||''});
        meta=null;if(results.length>=5000)break;
      }
    }
    return results;
  }
  // Read network playlists with an upper bound while downloading. Never proxy sources.
  async function fetchTextLimited(url, maxBytes){
    const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),14000);
    try{
      const resp=await fetch(url,{credentials:'omit',mode:'cors',signal:ctl.signal,cache:'no-store'});
      if(!resp.ok)throw new Error('Provider returned HTTP '+resp.status);
      const len=Number(resp.headers.get('content-length')||'0');if(len>maxBytes)throw new Error('Playlist is too large');
      if(!resp.body||!resp.body.getReader){const txt=await resp.text();if(txt.length>maxBytes)throw new Error('Playlist is too large');return txt;}
      let total=0;const chunks=[];const reader=resp.body.getReader();
      while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>maxBytes){await reader.cancel();throw new Error('Playlist is too large');}chunks.push(value);}
      const merged=new Uint8Array(total);let off=0;for(const part of chunks){merged.set(part,off);off+=part.length;}return new TextDecoder().decode(merged);
    }finally{clearTimeout(timer);}
  }
  async function loadRemote(href){
    const url=safeUrl(href);if(!url)throw new Error('Invalid playlist URL.');
    if(!requestAllowed(url))throw new Error('HTTPS page cannot load this HTTP playlist. Ask your provider for an HTTPS source.');
    const path=new URL(url).pathname.toLowerCase();
    if(path.endsWith('.m3u8')||/\.(mp4|webm|ogv)$/i.test(path))return {channels:[{name:'Direct stream',url,group:'Live stream',tvgId:''}],epgCandidates:[]};
    let raw;
    try{raw=await fetchTextLimited(url,3_000_000);}catch(err){throw new Error('Could not read the remote playlist. The provider must allow cross-origin (CORS) browser requests. You can also upload an authorized M3U file. ('+(err.message||'Network error')+')');}
    if(/#EXT-X-(STREAM-INF|TARGETDURATION|MEDIA-SEQUENCE)/.test(raw))return {channels:[{name:'Direct HLS stream',url,group:'Live stream',tvgId:''}],epgCandidates:[]};
    const channels=parseM3U(raw);if(!channels.length)throw new Error('No playable HTTP(S) entries were found in that playlist.');return {channels,epgCandidates:discoverM3uGuideUrls(raw)};
  }
  function applyChannels(channels, sourceText){
    state.channels=channels.slice(0,5000).map((ch,i)=>({name:decodeName(ch.name)||'Channel '+(i+1),url:safeUrl(ch.url)||'',group:decodeName(ch.group||'Other')||'Other',tvgId:decodeName(ch.tvgId||''),tvgName:decodeName(ch.tvgName||''),logo:safeLogo(ch.logo)})).filter(c=>c.url);
    state.category='all';$('filter').value='';state.filter='all';quicks.forEach(x=>{const active=x.dataset.filter==='all';x.classList.toggle('active',active);x.setAttribute('aria-pressed',String(active));});
    renderCategories();renderChannels();renderGuide();$('sourceStatus').textContent=state.channels.length+' channels loaded · '+sourceText;
    setNotice('Loaded '+state.channels.length+' channels. Playback depends on permission, HTTPS/CORS access, and compatible codecs.');
    void loadCloudPreferences(state.sourceId);renderMiniGuide();
    // Companion (optional, rights-gated) logo resolver reacts to playlist loads.
    window.dispatchEvent(new CustomEvent('tunely:playlist-loaded')); 
  }
  async function loadSource(id){
    window.TunelyMultiView?.close();
    const n=++state.requestId;epgFetchCounter++;stop();state.channels=[];state.programs=new Map();state.guideChannels=new Map();state.guideLogos=new Map();state.activeDetail=null;$('epgStatus').textContent='No guide selected';state.guideUrl='';state.guideSaveId='';state.detectedGuideUrls=[];state.epgOrigin='none';$('epgUrl').value='';$('epgAutoBadge').textContent='Guide: checking playlist…';updateGuideUi();setSource(id);renderCategories();renderGuide();renderAbout();
    if(!id){$('sourceStatus').textContent='Choose a playlist to browse channels.';return;}
    if(id==='local'){applyChannels(state.localEntries,'local file · not uploaded');void useDetectedGuide(state.localGuideUrls,null,n);return;}
    $('sourceStatus').textContent='Loading playlist…';
    try{
      const response=await fetch('/api/playlists/'+encodeURIComponent(id)+'/playable',{credentials:'same-origin',cache:'no-store'});
      if(response.status===401){setNotice('Sign in on the dashboard to load your saved playlists.','warn');return;}
      if(!response.ok)throw new Error('Could not access this playlist (HTTP '+response.status+').');
      const data=await response.json();if(n!==state.requestId)return;
      if(!data.supported){$('sourceStatus').textContent='This source needs a compatible provider integration.';setNotice(data.message||'Provider login is not yet supported in this web player.','warn');return;}
      let feed;
      if(data.type==='m3u_file')feed={channels:data.channels,epgCandidates:data.epg_candidates||[]};
      else if(data.type==='m3u_plus'){
        const result=await fetch('/api/playlists/'+encodeURIComponent(id)+'/provider-channels',
          {credentials:'same-origin',cache:'no-store'});
        if(!result.ok){let msg='Provider channel list is unavailable.';try{msg=(await result.json()).detail||msg;}catch{}throw new Error(msg);}
        feed=await result.json();
      }else feed=await loadRemote(data.url);
      if(n!==state.requestId)return;
      applyChannels(feed.channels,'saved source');
      if(feed.playback_note)setNotice(feed.playback_note,'warn');
      void useDetectedGuide(feed.epgCandidates||[],data.epg_url||null,n);
    }catch(err){if(n!==state.requestId)return;$('sourceStatus').textContent='Playlist unavailable';setNotice(err.message||'Unable to load playlist.','error');}
  }
  sourcePick.addEventListener('change',()=>{
    const id=sourcePick.value;
    void loadSource(id);
    // Persist the selection per account, not globally per browser. Local M3U imports are session only.
    if(state.loggedIn && id && id!=='local')void apiMutation('/api/player/preferences','PATCH',{playlist_id:id})
      .catch(()=>setNotice('Playlist loaded, but its selection could not be saved for next time.','warn'));
  });
  $('localM3u').addEventListener('change',async ev=>{
    if(!state.webPermitted){setNotice('Start a Plus trial to use browser playback.','warn');ev.target.value='';return;}
    const file=ev.target.files?.[0];if(!file)return;
    if(!$('localAuthorized').checked){setNotice('Confirm that you have permission to access this playlist before importing it.','warn');ev.target.value='';return;}
    if(file.size>3_000_000){setNotice('M3U files are limited to 3 MB for this browser test.','warn');return;}
    try{
      const raw=await file.text();const entries=parseM3U(raw);const epgCandidates=discoverM3uGuideUrls(raw);if(!entries.length)throw new Error('No valid HTTP(S) stream URLs found in that file.');
      if(![...sourcePick.options].some(o=>o.value==='local'))sourcePick.add(new Option('Local session playlist','local'));
      sourcePick.value='local';state.requestId++;window.TunelyMultiView?.close();stop();state.localEntries=entries;state.localGuideUrls=epgCandidates;state.programs=new Map();state.guideChannels=new Map();state.guideLogos=new Map();state.guideUrl='';state.guideSaveId='';state.epgOrigin='none';$('epgUrl').value='';$('epgAutoBadge').textContent='Guide: checking playlist…';setSource('local');applyChannels(entries,'local file · not uploaded');void useDetectedGuide(epgCandidates,null,state.requestId);
      setTab('guide');$('channelBrowser').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(err){setNotice(err.message,'error');}
    ev.target.value='';
  });
  $('directForm').addEventListener('submit',ev=>{
    ev.preventDefault();if(!state.webPermitted){setNotice('Web playback is not included on Free. Start a Plus trial from Account.','warn');return;}if(!$('authorized').checked){setNotice('Confirm that you are authorized to access this stream before playing it.','warn');return;}
    const url=safeUrl($('directUrl').value.trim());if(!url){setNotice('Enter a valid HTTP(S) stream URL.','error');return;}
    playChannel({name:'Direct browser stream',url,group:'Direct',tvgId:''});
  });

  const epgDate = raw => {
    const m=String(raw||'').match(/^(\d{4})(\d\d)(\d\d)(\d\d)(\d\d)(\d\d)?(?:\s*([+-])(\d\d)(\d\d))?/);
    if(!m)return NaN;
    let time=Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+(m[6]||0));
    if(m[7])time+=(m[7]==='+'?-1:1)*((+m[8])*60+(+m[9]))*60_000;
    return time;
  };
  const formatTime = ts => Number.isFinite(ts)?new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date(ts)):'—';
  const first = (el,tag) => el.getElementsByTagName(tag)[0]?.textContent?.trim()||'';
  function parseXMLTV(txt){
    if(/<!DOCTYPE|<!ENTITY/i.test(txt))throw new Error('XMLTV containing DTDs or entities is not supported.');
    const doc=new DOMParser().parseFromString(txt,'text/xml');
    if(doc.querySelector('parsererror'))throw new Error('Invalid XMLTV file.');
    const guides=new Map(),names=new Map(),logos=new Map();
    for(const chan of [...doc.getElementsByTagName('channel')].slice(0,10000)){
      const id=chan.getAttribute('id');if(id){const logo=safeLogo(chan.getElementsByTagName('icon')[0]?.getAttribute('src'));if(logo)logos.set(id,logo);for(const display of [...chan.getElementsByTagName('display-name')].slice(0,5)){const key=norm(display.textContent);if(key&&!names.has(key))names.set(key,id);}}
    }
    for(const entry of [...doc.getElementsByTagName('programme')].slice(0,30000)){
      const id=entry.getAttribute('channel'),start=epgDate(entry.getAttribute('start')),end=epgDate(entry.getAttribute('stop'));
      if(!id||!Number.isFinite(start)||!Number.isFinite(end)||end<=start)continue;
      if(!guides.has(id))guides.set(id,[]);
      const programs=guides.get(id);if(programs.length>=600)continue;
      programs.push({start,end,title:decodeName(first(entry,'title'))||'Untitled program',desc:first(entry,'desc').slice(0,280)});
    }
    for(const programs of guides.values())programs.sort((a,b)=>a.start-b.start);
    state.programs=guides;state.guideChannels=names;state.guideLogos=logos;
    return [...guides.values()].reduce((sum,x)=>sum+x.length,0);
  }
  $('xmltvFile').addEventListener('change',async ev=>{
    const file=ev.target.files?.[0];if(!file)return;
    if(file.size>10_000_000){setNotice('Please choose an XMLTV file under 10 MB.','warn');ev.target.value='';return;}
    try{
      const txt=await file.text();const count=parseXMLTV(txt);
      state.guideUrl='';state.guideSaveId='';state.epgOrigin='file';state.lastEpgRefresh=0;updateGuideUi();
      $('epgStatus').textContent='Local guide · '+count+' programs (no automatic file refresh)';
      renderGuide();renderAbout();renderMiniGuide();setTab('guide');setNotice('XMLTV file loaded locally. The file was not uploaded.');
    }catch(err){setNotice('Could not open guide: '+err.message,'error');}
    ev.target.value='';
  });
  function updateGuideUi(){
    $('saveEpgUrl').disabled=!cloudEnabled() || isInternalGuide(state.guideUrl);
    $('removeEpgUrl').disabled=!cloudEnabled() || !state.guideSaveId;
    if(!state.guideUrl)$('epgRefreshStatus').textContent='Automatic EPG: waiting for playlist metadata';
  }
  // Guard decompression of XMLTV .gz; browsers transparently handle HTTP
  // Content-Encoding: gzip, but some providers serve raw gzip files.
  async function fetchGuideText(url){
    const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),15000);
    const maxInput=10_000_000,maxOutput=20_000_000;
    async function collect(stream,limit){
      const reader=stream.getReader();let size=0;const parts=[];
      while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
        if(size>limit){await reader.cancel();throw new Error('Guide exceeds size limit');}parts.push(value);}
      const buf=new Uint8Array(size);let off=0;for(const part of parts){buf.set(part,off);off+=part.length;}return buf;
    }
    try{
      const response=await fetch(url,{credentials:isInternalGuide(url)?'same-origin':'omit',mode:'cors',cache:'no-store',signal:ctl.signal});
      if(!response.ok)throw new Error('Guide server returned HTTP '+response.status);
      if(Number(response.headers.get('content-length')||0)>maxInput)throw new Error('Guide exceeds size limit');
      const bytes=await collect(response.body,maxInput);
      const gzip=bytes[0]===0x1f&&bytes[1]===0x8b;
      if(!gzip)return new TextDecoder().decode(bytes);
      if(typeof DecompressionStream==='undefined')throw new Error('Compressed XMLTV is unsupported in this browser');
      const output=await collect(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')),maxOutput);
      return new TextDecoder().decode(output);
    }finally{clearTimeout(timer);}
  }
  let epgFetchCounter=0;
  async function loadRemoteEpg(automatic=false,quiet=false){
    const url=safeGuideUrl(state.guideUrl);if(!url)return false;
    if(!requestAllowed(url)){$('epgRefreshStatus').textContent='Automatic EPG: HTTPS required on this website';return false;}
    const serial=++epgFetchCounter,source=state.sourceId;
    state.lastEpgRefresh=Date.now();
    $('epgRefreshStatus').textContent=automatic?'Checking provider guide…':'Loading authorized XMLTV guide…';
    $('epgAutoBadge').textContent='Guide: loading from provider…';
    try{
      const txt=await fetchGuideText(url);
      if(serial!==epgFetchCounter||source!==state.sourceId)return false;
      const count=parseXMLTV(txt);if(count===0)throw new Error('No valid XMLTV programmes found');
      state.lastEpgRefresh=Date.now();
      const time=new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date());
      $('epgRefreshStatus').textContent=(state.epgOrigin==='auto'?'Auto EPG':'EPG')+' · updated '+time+' · '+count+' programmes · refresh hourly while open';
      $('epgStatus').textContent=count+' programs from authorized XMLTV ('+(state.epgOrigin==='auto'?'automatic':'selected')+')';
      $('epgAutoBadge').textContent='Guide: '+count+' listings · '+(state.epgOrigin==='auto'?'automatic':'manual');
      renderGuide();renderAbout();renderMiniGuide();
      if(!automatic)setNotice('Guide loaded from your authorized source.');
      return true;
    }catch(err){if(serial!==epgFetchCounter||source!==state.sourceId)return false;
      $('epgRefreshStatus').textContent='EPG unavailable: '+(err.message||'Network/CORS error');
      $('epgAutoBadge').textContent='Guide: unavailable';
      if(!quiet)setNotice('Guide unavailable: provider HTTPS, CORS, format or browser support may prevent access. '+(err.message||''),'warn');
      return false;
    }
  }
  async function useDetectedGuide(candidates,manualUrl,requestId){
    const options=[...new Set((candidates||[]).map(safeGuideUrl).filter(Boolean))].slice(0,3);
    state.detectedGuideUrls=options;
    if(manualUrl&&safeUrl(manualUrl)&&requestAllowed(manualUrl)){
      state.guideUrl=safeUrl(manualUrl);state.guideSaveId=state.sourceId;state.epgOrigin='manual';
      $('epgUrl').value=state.guideUrl;updateGuideUi();await loadRemoteEpg(true);return;
    }
    if(!options.length){$('epgRefreshStatus').textContent='No EPG link advertised by this playlist · advanced manual setup available';$('epgAutoBadge').textContent='Guide: none provided';return;}
    const source=state.sourceId;
    const available=options.filter(requestAllowed);
    if(!available.length){$('epgRefreshStatus').textContent='Provider only advertises HTTP EPG; HTTPS required';$('epgAutoBadge').textContent='Guide: HTTPS required';return;}
    for(const url of available){
      if(requestId!==state.requestId||source!==state.sourceId)return;
      state.guideUrl=url;state.epgOrigin='auto';updateGuideUi();
      if(await loadRemoteEpg(true,true))return;
    }
    if(requestId===state.requestId&&source===state.sourceId){
      $('epgRefreshStatus').textContent='Auto EPG found, but provider access failed (HTTPS / CORS / XMLTV). Advanced manual setup available';
      $('epgStatus').textContent='No compatible program listings';
      $('epgAutoBadge').textContent='Guide: unavailable';
    }
  }
  $('loadEpgUrl').addEventListener('click',()=>{
    const url=safeUrl($('epgUrl').value.trim());
    if(!url||!requestAllowed(url)){setNotice('Enter a valid HTTPS XMLTV guide URL.','warn');return;}
    if(!$('epgAuthorized').checked){setNotice('Confirm you have permission to access this guide.','warn');return;}
    state.guideUrl=url;state.epgOrigin='manual';state.lastEpgRefresh=0;updateGuideUi();void loadRemoteEpg(false);
  });
  $('saveEpgUrl').addEventListener('click',async()=>{
    if(!cloudEnabled()||!state.guideUrl||isInternalGuide(state.guideUrl)){setNotice('Automatic provider guides do not need to be saved. Choose a manual HTTPS XMLTV URL to save an override.','warn');return;}
    const id=state.sourceId,url=state.guideUrl;
    try{await apiMutation('/api/playlists/'+encodeURIComponent(id)+'/guide','PATCH',{url});
      if(id===state.sourceId){state.guideSaveId=id;updateGuideUi();setNotice('Encrypted XMLTV URL saved with this account playlist. Guide is fetched only by your browser.');}
    }catch(err){setNotice('Unable to save guide URL: '+err.message,'error');}
  });
  $('removeEpgUrl').addEventListener('click',async()=>{
    if(!cloudEnabled())return;
    const id=state.sourceId;
    try{await apiMutation('/api/playlists/'+encodeURIComponent(id)+'/guide','PATCH',{url:null});
      if(id===state.sourceId){state.guideSaveId='';state.guideUrl='';state.epgOrigin='none';$('epgUrl').value='';updateGuideUi();void useDetectedGuide(state.detectedGuideUrls,null,state.requestId);setNotice('Manual guide removed. Provider-advertised automatic EPG will be used when available.');}
    }catch(err){setNotice('Unable to remove guide URL: '+err.message,'error');}
  });
  // The guide refreshes while the tab is visible. M3U Plus guide metadata is
  // retrieved from a bounded, authenticated server endpoint; streams are never proxied.
  setInterval(()=>{if(state.guideUrl&&document.visibilityState==='visible'&&Date.now()-state.lastEpgRefresh>=60*60*1000)void loadRemoteEpg(true);},60_000);
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible'&&state.guideUrl&&Date.now()-state.lastEpgRefresh>=60*60*1000)void loadRemoteEpg(true);
  });
  function programsFor(channel){
    if(!channel)return [];
    const ids=[channel.tvgId,state.guideChannels.get(norm(channel.tvgName)),state.guideChannels.get(norm(channel.name))];
    for(const id of ids){if(!id)continue;const found=state.programs.get(id)||state.programs.get(norm(id));if(found?.length)return found;}
    return [];
  }
  function currentNext(channel){
    const now=Date.now(),values=programsFor(channel);
    const live=values.find(p=>p.start<=now&&p.end>now)||null;
    const next=values.find(p=>p.start>now)||null;
    return {live,next};
  }
  function progressOf(program){
    if(!program)return 0;
    return Math.max(0,Math.min(100,100*(Date.now()-program.start)/(program.end-program.start)));
  }
  function progressElement(program){const outer=node('div','program-progress');
    const inner=node('div','progress-fill');inner.style.width=progressOf(program).toFixed(1)+'%';outer.append(inner);return outer;
  }
  function renderMiniGuide(){
    const root=$('miniChannelList');root.replaceChildren();
    const current=state.current;
    if(current){const {live,next}=currentNext(current);
      $('miniCurrent').textContent='NOW · '+current.name+' · '+(live?live.title:'No guide data')+(next?' | NEXT · '+next.title:'');
    }else $('miniCurrent').textContent='Choose a channel to begin playback.';
    const channels=visibleChannels().slice(0,60);
    if(!channels.length){root.append(node('p','empty','Choose an authorized playlist to browse channels.'));return;}
    for(const ch of channels){
      const {live,next}=currentNext(ch),button=node('button','mini-channel');button.type='button';
      if(current&&cid(current)===cid(ch))button.classList.add('active');
      button.append(node('strong','',ch.name),node('small','',live?'Now: '+live.title:'No guide data'));
      if(live)button.append(progressElement(live));
      if(next)button.append(node('small','', 'Next: '+next.title));
      button.addEventListener('click',()=>{playChannel(ch);$('miniGuide').hidden=true;$('miniGuideBtn').setAttribute('aria-expanded','false');});
      root.append(button);
    }
    if(visibleChannels().length>60)root.append(node('p','empty','Showing first 60 matching channels. Use the main browser to search.'));
  }
  function toggleMiniGuide(){const mini=$('miniGuide');mini.hidden=!mini.hidden;
    $('miniGuideBtn').setAttribute('aria-expanded',String(!mini.hidden));
    if(!mini.hidden){$('playerSettings').hidden=true;$('settingsBtn').setAttribute('aria-expanded','false');renderMiniGuide();}
  }
  $('miniGuideBtn').addEventListener('click',toggleMiniGuide);
  $('closeMiniGuide').addEventListener('click',()=>{$('miniGuide').hidden=true;$('miniGuideBtn').setAttribute('aria-expanded','false');});
  const channelsForNavigation=()=>visibleChannels();
  function switchChannel(step){const available=channelsForNavigation();if(!available.length){setNotice('Choose a playlist first.','warn');return;}
    const i=state.current?available.findIndex(ch=>cid(ch)===cid(state.current)):-1;
    const next=i<0?0:(i+step+available.length)%available.length;playChannel(available[next]);
  }
  $('prevChannel').addEventListener('click',()=>switchChannel(-1));
  $('nextChannel').addEventListener('click',()=>switchChannel(1));
  $('muteBtn').addEventListener('click',()=>{video.muted=!video.muted;});
  $('pipBtn').addEventListener('click',async()=>{
    if(video.hidden||!document.pictureInPictureEnabled||typeof video.requestPictureInPicture!=='function'){setNotice('Picture-in-picture is not supported by this browser or stream.','warn');return;}
    try{if(document.pictureInPictureElement)await document.exitPictureInPicture();else await video.requestPictureInPicture();}
    catch{setNotice('Picture-in-picture was blocked by your browser.','warn');}
  });
  $('settingsBtn').addEventListener('click',()=>{const root=$('playerSettings');root.hidden=!root.hidden;
    $('settingsBtn').setAttribute('aria-expanded',String(!root.hidden));
    if(!root.hidden){$('miniGuide').hidden=true;$('miniGuideBtn').setAttribute('aria-expanded','false');updateTrackSettings();}
  });
  $('closeSettings').addEventListener('click',()=>{$('playerSettings').hidden=true;$('settingsBtn').setAttribute('aria-expanded','false');});
  function resetTrackSettings(){
    for(const id of ['qualityPick','audioPick','subtitlePick'])$(id).replaceChildren();
    $('qualityPick').add(new Option('Auto / Source default','auto'));
    $('audioPick').add(new Option('Source default','default'));
    $('subtitlePick').add(new Option('Off / Source default','off'));
    for(const id of ['qualityPick','audioPick','subtitlePick'])$(id).disabled=true;
  }
  function updateTrackSettings(){
    const hls=state.hls;resetTrackSettings();if(!hls)return;
    if(hls.levels?.length){const pick=$('qualityPick');
      hls.levels.forEach((level,i)=>pick.add(new Option((level.height?level.height+'p':'Level '+(i+1))+' · '+Math.round((level.bitrate||0)/1000)+' kbps',String(i))));
      pick.value=hls.autoLevelEnabled?'auto':String(hls.currentLevel);pick.disabled=false;
    }
    if(hls.audioTracks?.length>1){const pick=$('audioPick');
      hls.audioTracks.forEach((track,i)=>pick.add(new Option((track.name||track.lang||'Audio '+(i+1)),String(i))));
      pick.value=String(hls.audioTrack);pick.disabled=false;
    }
    if(hls.subtitleTracks?.length){const pick=$('subtitlePick');
      hls.subtitleTracks.forEach((track,i)=>pick.add(new Option(track.name||track.lang||'Subtitle '+(i+1),String(i))));
      pick.value=hls.subtitleDisplay?String(hls.subtitleTrack):'off';pick.disabled=false;
    }
  }
  $('qualityPick').addEventListener('change',()=>{if(state.hls)state.hls.currentLevel=$('qualityPick').value==='auto'?-1:Number($('qualityPick').value);});
  $('audioPick').addEventListener('change',()=>{if(state.hls&&$('audioPick').value!=='default')state.hls.audioTrack=Number($('audioPick').value);});
  $('subtitlePick').addEventListener('change',()=>{if(!state.hls)return;
    state.hls.subtitleDisplay=$('subtitlePick').value!=='off';if(state.hls.subtitleDisplay)state.hls.subtitleTrack=Number($('subtitlePick').value);
  });
  function renderListGuide(){
    const root=$('guideList');root.replaceChildren();$('guideClock').textContent=new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date())+' · Local time';
    if(state.programs.size===0){
      const emp=node('div','guide-empty');emp.append(node('span','guide-empty-icon','▤'),node('b','', 'No listings available from this provider'),node('p','', 'TunelyTV checks the playlist for its provider-supplied guide automatically. You can also use the advanced manual guide settings.'));
      const btn=node('button','file-label','Load an XMLTV file →');btn.type='button';btn.addEventListener('click',showSetup);emp.append(btn);root.append(emp);return;
    }
    if(!state.channels.length){root.append(node('p','empty','Choose a playlist. TunelyTV will check its EPG automatically.'));return;}
    for(const ch of state.channels.slice(0,200)){
      const {live,next}=currentNext(ch),button=node('button','guide-row');button.type='button';
      if(state.current&&cid(state.current)===cid(ch))button.classList.add('current');
      button.setAttribute('aria-label','Play '+ch.name);
      const channel=node('span','guide-channel');channel.append(channelAvatar(ch,'guide-channel-icon'));
      const cInfo=node('span');cInfo.append(node('b','',ch.name),node('small','',ch.group||'Other'));channel.append(cInfo);
      const now=node('span','guide-program');now.append(node('b','',live?live.title:'Guide unavailable'),node('span','',live?formatTime(live.start)+' – '+formatTime(live.end):'No current listing'));
      const future=node('span','guide-program next');future.append(node('b','',next?next.title:'No next program'),node('span','',next?formatTime(next.start):'—'));
      button.append(channel,now,future);button.addEventListener('click',()=>playChannel(ch));root.append(button);
    }
    if(state.channels.length>200)root.append(node('p','empty','Guide showing first 200 channels. Use the channel search to find others.'));
  }

  // Timeline is derived exclusively from user-provided XMLTV. Gaps are explicit
  // 'No guide data' placeholders — never generated program titles or schedules.
  const GRID_MINUTES = 180;
  const GRID_STEP = 30;
  const GRID_PX_PER_MIN = 3.35;
  const GRID_WIDTH = GRID_MINUTES * GRID_PX_PER_MIN;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const dateLabel = ts => new Intl.DateTimeFormat(undefined,{weekday:'short',month:'short',day:'numeric'}).format(new Date(ts));
  function setGuideView(view) {
    state.guideView = view === 'list' ? 'list' : 'grid';
    for(const btn of document.querySelectorAll('[data-guide-view]')) {
      const active=btn.dataset.guideView===state.guideView;
      btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active));
    }
    $('guideGrid').hidden=state.guideView!=='grid';
    $('guideList').hidden=state.guideView!=='list';
    $('guideHint').hidden=state.guideView!=='grid';
    const gridNav=state.guideView==='grid';
    for (const el of ['guidePrev','guideNow','guideNext']) $(el).disabled=!gridNav;
    renderGuide();
  }
  document.querySelectorAll('[data-guide-view]').forEach(btn=>btn.addEventListener('click',()=>setGuideView(btn.dataset.guideView)));
  $('guidePrev').addEventListener('click',()=>{state.guideStart-=90*60_000;$('guideGrid').replaceChildren();renderGuide();});
  $('guideNext').addEventListener('click',()=>{state.guideStart+=90*60_000;$('guideGrid').replaceChildren();renderGuide();});
  $('guideNow').addEventListener('click',()=>{state.guideStart=Math.floor(Date.now()/1800000)*1800000;$('guideGrid').replaceChildren();renderGuide();});

  function showGuideDetail(ch, program) {
    const root=$('epgDetails');root.replaceChildren();
    if(!program){root.hidden=true;state.activeDetail=null;return;}
    root.hidden=false;
    const info=node('div','epg-detail-text');
    info.append(node('span','epg-detail-kicker',ch.name+' · '+formatTime(program.start)+' – '+formatTime(program.end)),node('strong','',program.title));
    if(program.desc)info.append(node('p','',program.desc));
    const until=Math.max(0,Math.ceil((program.end-Date.now())/60000));
    info.append(node('p','program-meta',program.start<=Date.now()&&program.end>Date.now()?until+' minutes remaining':'Starts '+formatTime(program.start)));
    info.append(progressElement(program));
    state.activeDetail={ch,program};
    const btn=node('button','epg-detail-close','Close');btn.type='button';btn.addEventListener('click',()=>{root.hidden=true;state.activeDetail=null;root.replaceChildren();});
    root.append(info,btn);
  }
  function renderGridGuide() {
    const root=$('guideGrid');
    const previousScroll=root.querySelector('.epg-scroll')?.scrollLeft||0;
    const previousTop=root.querySelector('.epg-scroll')?.scrollTop||0;
    root.replaceChildren();
    const start=state.guideStart, end=start+GRID_MINUTES*60_000;
    $('guideClock').textContent=dateLabel(start)+' · '+formatTime(start)+'–'+formatTime(end);
    const filtered=visibleChannels();
    if(!state.channels.length) {
      const wrap=node('div','epg-grid-empty');wrap.append(node('span','epg-empty-mark','▦'),node('h3','', 'Your TV guide starts here'),node('p','', 'Choose a playlist to see channels. TunelyTV loads available provider EPG automatically.'));
      const btn=node('button','file-label','Add a source →');btn.type='button';btn.addEventListener('click',showSetup);wrap.append(btn);root.append(wrap);return;
    }
    if(!filtered.length) {root.append(node('div','epg-grid-empty','No channels match the selected search, category, or favorites filter.'));return;}
    const scroll=node('div','epg-scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','Guide timeline; scroll horizontally to see all programs');
    const grid=node('div','epg-layout');
    const header=node('div','epg-ruler');
    const topLeft=node('div','epg-sticky-head','CHANNELS');header.append(topLeft);
    const ticks=node('div','epg-ticks');ticks.style.width=GRID_WIDTH+'px';
    for(let min=0;min<GRID_MINUTES;min+=GRID_STEP){
      const tick=node('div','epg-tick',formatTime(start+min*60_000));
      tick.style.width=(GRID_STEP*GRID_PX_PER_MIN)+'px';ticks.append(tick);
    }
    const now=Date.now();
    if(now>=start && now<end){
      const marker=node('div','epg-now-marker');marker.style.left=((now-start)/60000*GRID_PX_PER_MIN)+'px';
      marker.append(node('span','', 'NOW'));ticks.append(marker);
    }
    header.append(ticks);grid.append(header);
    for(const ch of filtered.slice(0,state.gridLimit)){
      const row=node('div','epg-row');
      if(state.current && cid(state.current)===cid(ch))row.classList.add('tuned');
      const label=node('button','epg-channel-button');label.type='button';label.setAttribute('aria-label','Play '+ch.name);label.title='Play '+ch.name;
      label.append(channelAvatar(ch,'epg-channel-avatar'));
      const sub=node('span','epg-channel-meta');sub.append(node('strong','',ch.name),node('small','',ch.group||'Other'));label.append(sub);
      label.addEventListener('click',()=>{playChannel(ch);showGuideDetail(ch,null);});row.append(label);
      const track=node('div','epg-track');track.style.width=GRID_WIDTH+'px';
      const programs=programsFor(ch).filter(p=>p.end>start && p.start<end);
      // Sort and clip to the requested window. Skip overlaps rather than cover other listings.
      programs.sort((a,b)=>a.start-b.start||a.end-b.end);
      let cursor=start;
      function block(from,to,program){
        if(to<=from)return;
        const left=(from-start)/60000*GRID_PX_PER_MIN;
        const width=(to-from)/60000*GRID_PX_PER_MIN;
        const cell=node('button',program?'epg-program':'epg-program epg-missing');cell.type='button';
        cell.style.left=left+'px';cell.style.width=Math.max(0,width-2)+'px';
        const label=program?program.title:'No guide data';
        cell.setAttribute('aria-label',ch.name+': '+label+', '+formatTime(from)+' to '+formatTime(to)+'. Play channel');
        cell.title=ch.name+' — '+label+' ('+formatTime(from)+'–'+formatTime(to)+')';
        cell.append(node('strong','',label));
        if(width>125)cell.append(node('small','',program?(formatTime(program.start)+' – '+formatTime(program.end)):'Tune to channel'));
        if(program && program.start<=Date.now() && program.end>Date.now())cell.classList.add('on-now');
        cell.addEventListener('click',()=>{playChannel(ch);showGuideDetail(ch,program);});
        track.append(cell);
      }
      for(const p of programs){
        const from=clamp(p.start,start,end),to=clamp(p.end,start,end);
        if(to<=cursor)continue;
        if(from>cursor)block(cursor,from,null);
        block(Math.max(cursor,from),to,p);cursor=to;
        if(cursor>=end)break;
      }
      if(cursor<end)block(cursor,end,null);
      if(now>=start&&now<end){const liveLine=node('span','epg-live-line');liveLine.style.left=((now-start)/60000*GRID_PX_PER_MIN)+'px';track.append(liveLine);}
      row.append(track);grid.append(row);
    }
    scroll.append(grid);root.append(scroll);scroll.scrollLeft=previousScroll;scroll.scrollTop=previousTop;
    if(filtered.length>state.gridLimit)root.append(node('p','epg-truncated','Showing the first '+state.gridLimit+' matching channels. Refine the channel search or category to see others.'));
    if(state.programs.size===0)root.append(node('p','epg-no-xmltv','No XMLTV guide loaded. The timeline shows empty schedule slots, not fabricated programming. Open “Add a source” to import a guide.'));
  }
  function renderGuide(){
    if(state.guideView==='grid')renderGridGuide();
    else renderListGuide();
    window.dispatchEvent(new Event('tunely:guide-rendered'));
  }
  function renderAbout(){
    const root=$('programCards');root.replaceChildren();const ch=state.current;
    $('aboutChannel').textContent=ch?ch.name:'Select a channel to see its schedule.';
    if(!ch){root.append(node('div','guide-empty','Select a channel to view its schedule.'));return;}
    const {live,next}=currentNext(ch);
    for(const [label,p] of [['ON NOW',live],['UP NEXT',next]]){
      const card=node('article','program-card');card.append(node('small','',label),node('h3','',p?p.title:'No guide information'),node('p','',p?(formatTime(p.start)+' – '+formatTime(p.end)):'Load an XMLTV file with matching channel IDs for listings.'));
      if(p&&p.desc)card.append(node('p','',p.desc));
      if(p){if(p.start<=Date.now()&&p.end>Date.now())card.append(node('p','program-meta',Math.max(0,Math.ceil((p.end-Date.now())/60000))+' minutes left'));
        card.append(progressElement(p));}
      root.append(card);
    }
  }
  document.addEventListener('keydown',ev=>{if(ev.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){ev.preventDefault();if(window.TunelyGuideFocus?.isOpen()){ $('gfSearch').focus();return; }$('filter').focus();scrollBrowser();}});
  document.addEventListener('keydown',ev=>{
    if(window.TunelyMultiView?.isActive()||window.TunelyGuideFocus?.isOpen())return;
    if(ev.altKey||ev.ctrlKey||ev.metaKey||['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;
    const key=ev.key.toLowerCase();
    if(key==='g'){ev.preventDefault();if(window.TunelyGuideFocus)window.TunelyGuideFocus.toggle();else toggleMiniGuide();}
    else if(key==='m'){ev.preventDefault();video.muted=!video.muted;}
    else if(key==='f'){ev.preventDefault();$('fullscreen').click();}
    else if(ev.key==='ArrowUp'){ev.preventDefault();switchChannel(-1);}
    else if(ev.key==='ArrowDown'){ev.preventDefault();switchChannel(1);}
    else if(ev.key==='Escape'){$('miniGuide').hidden=true;$('playerSettings').hidden=true;}
  });
  // Check expiry even if the viewer leaves the page open across the trial deadline.
  // Revoking the in-app playback state cannot revoke provider URLs copied externally.
  setInterval(async()=>{
    if(localPreview||!state.loggedIn||document.visibilityState!=='visible')return;
    try{
      const response=await fetch('/api/license/me',{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)return;
      const license=await response.json();
      if(!license.web_playback && state.webPermitted){
        state.webPermitted=false;document.body.classList.add('license-web-locked');
        window.TunelyMultiView?.close();stop();
        setNotice('Your Plus trial or subscription has ended. Saved playlists remain available in Account. Free is TV-only.','warn');
      }
    }catch{}
  },60000);
  setInterval(()=>{
    if(document.visibilityState==='visible'){
      renderAbout();if(!$('miniGuide').hidden)renderMiniGuide();
      if(state.activeDetail&&!$('epgDetails').hidden)showGuideDetail(state.activeDetail.ch,state.activeDetail.program);
    }
  },30000);
  async function init(){
    resetTrackSettings();renderChannels();renderGuide();renderAbout();renderMiniGuide();updateGuideUi();
    if(localPreview){updateSyncStatus('Standalone preview: browser-only preferences.');sourcePick.replaceChildren(new Option('Local preview — import a file',''));$('sourceStatus').textContent='Standalone preview: import a local M3U in Add a source, or test a direct URL.';setNotice('Standalone preview mode. Select Add a source to import a local playlist; saved account playlists require Railway.');return;}
    try{
      const me=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});
      if(!me.ok){sourcePick.replaceChildren(new Option('Sign in to see saved playlists',''));$('sourceStatus').textContent='Please sign in on the dashboard. You can still import a local M3U file.';setNotice('Sign in on the dashboard for saved playlists, or use a local session M3U file.','warn');return;}
      state.loggedIn=true;updateGuideUi();
      const licenseResponse=await fetch('/api/license/me',{credentials:'same-origin',cache:'no-store'});
      if(!licenseResponse.ok)throw new Error('Unable to verify this account’s viewing permissions.');
      const license=await licenseResponse.json();
      if(!license.web_playback){
        sourcePick.replaceChildren(new Option('Web playback unavailable on Free',''));
        $('sourceStatus').textContent='Free is TV-only. Start your 7-day Plus trial from Account → Plans & Billing.';
        setNotice('Your Free plan includes one TV, but web playback requires an eligible Plus trial or paid plan. Open Account → Plans & Billing.','warn');
        document.body.classList.add('license-web-locked');
        return;
      }
      state.webPermitted=true;document.body.classList.remove('license-web-locked');
      updateSyncStatus('Sign in confirmed. Your account can access supported web playback.');
      const response=await fetch('/api/playlists',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw new Error('Unable to load your account playlists.');
      const data=await response.json();state.sources=data.playlists||[];
      sourcePick.replaceChildren(new Option(state.sources.length?'Select a saved playlist':'No saved playlists yet',''));
      state.sources.forEach(p=>sourcePick.add(new Option(p.name+' · '+p.type,p.id)));
      $('sourceStatus').textContent=state.sources.length?'Restoring your last saved playlist…':'No playlists yet. Add one from the dashboard.';
      if(state.sources.length){
        let preferred='';
        try{
          const pref=await fetch('/api/player/preferences',{credentials:'same-origin',cache:'no-store'});
          if(pref.ok){const saved=await pref.json();preferred=saved.playlist_id||'';}
        }catch{}
        // The server clears deleted playlist IDs; if none exists, use the first available.
        if(!state.sources.some(p=>p.id===preferred))preferred=state.sources[0].id;
        sourcePick.value=preferred;
        await loadSource(preferred);
        window.TunelyGuideFocus?.maybeStartInGuide();
        // Save the chosen default, too, so it follows the user to another browser.
        void apiMutation('/api/player/preferences','PATCH',{playlist_id:preferred}).catch(()=>{});
      }
    }catch{sourcePick.replaceChildren(new Option('Account playlists unavailable',''));$('sourceStatus').textContent='Sign in or use local session import.';setNotice('Account playlist service is unavailable. Local file import and direct stream testing remain available.','warn');}
  }
  window.TunelyGuideBridge={
    matchMissingLogos:channels=>apiMutation('/api/channel-logos/match','POST',{channels}),
    applyLogoMatches:(matches,sourceId)=>{
      if(sourceId!==state.sourceId)return 0;
      let count=0;
      for(const match of matches){
        const ch=state.channels[match.index];
        if(!ch||ch.logo||!safeLogo(match.url))continue;
        ch.externalLogo=safeLogo(match.url);count++;
      }
      if(count){renderChannels();renderGuide();renderMiniGuide();}
      return count;
    },
    getCurrent:()=>state.current,getChannels:()=>state.channels, getDetail:()=>state.activeDetail, getNowNext:ch=>ch?currentNext(ch):{live:null,next:null},formatTime, setGuideView, renderGuide, getProgramsLoaded:()=>state.programs.size, sourceId:()=>state.sourceId};
  window.TunelyMultiBridge={
    getChannels:()=>state.channels.slice(),
    getCurrent:()=>state.current,
    stopMain:()=>stop(),
    sourceName:()=>sourcePick.selectedOptions?.[0]?.textContent||'Your playlist',
    isLoggedIn:()=>state.loggedIn,
    announce:(message,kind)=>setNotice(message,kind||'')
  };
  renderCategories();setGuideView('grid');init();
})();
