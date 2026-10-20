// TunelyTV v0.9.1 — immersive full-viewport direct-source Multi-View.
// No bundled streams, stream relay, credential capture, or access-control bypass.
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const bridge = window.TunelyMultiBridge;
  const main = byId('multiviewPanel');
  if (!main || !bridge) return;
  const grid = byId('mvGrid');
  const message = byId('mvAccess');
  const status = byId('mvStatus');
  const local = window.location.protocol === 'file:';
  let active = false, limit = 0, count = 2, audioPane = 0, access = null;
  let paneControllers = [];
  let returnFocus = null;

  function setStatus(s) { status.textContent = s; }
  function textNode(tag, cls, value) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    n.textContent = value;
    return n;
  }
  function validStream(raw) {
    try {
      const url = new URL(raw);
      if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return null;
      if (location.protocol === 'https:' && url.protocol === 'http:') return null;
      return url.href;
    } catch { return null; }
  }
  function dispose(p) {
    if (!p) return;
    p.ticket += 1;
    try { if (p.hls) p.hls.destroy(); } catch {}
    p.hls = null;
    p.video.pause();
    p.video.removeAttribute('src');
    p.video.load();
    p.video.hidden = true;
    p.current = null;
    p.empty.hidden = false;
    p.indicator.textContent = 'READY';
    p.title.textContent = 'Choose a channel';
    p.name.textContent = 'Select a channel below';
    p.select.value = '';
    p.root.classList.remove('is-choosing');
  }
  function updateAudio() {
    paneControllers.forEach((p, i) => {
      p.video.muted = i !== audioPane;
      p.audio.classList.toggle('is-selected', i === audioPane);
      p.audio.querySelector('.mv-action-label').textContent = i === audioPane ? 'Audio active' : 'Listen here';
      p.audio.setAttribute('title', i === audioPane ? 'Audio active' : 'Listen here');
      p.audio.setAttribute('aria-pressed', String(i === audioPane));
      p.audio.setAttribute('aria-label', 'Select audio from screen ' + (i + 1));
    });
  }
  function pane(index) {
    const root = textNode('article', 'mv-pane', '');
    root.setAttribute('aria-label', 'Multi-View screen ' + (index + 1));
    const frame = textNode('div', 'mv-frame', '');
    const video = document.createElement('video');
    video.setAttribute('playsinline','');
    video.setAttribute('preload','none');
    video.setAttribute('aria-label', 'Playback screen '+(index+1));
    video.controls = true; video.hidden = true;
    const empty = textNode('div','mv-empty','');
    empty.append(textNode('span','mv-empty-symbol','▣'),textNode('strong','', 'Screen '+(index+1)),textNode('span','', 'Choose a channel below'));
    const top = textNode('div','mv-overlay-head','');
    const label = textNode('strong','mv-screen-id','SCREEN 0'+(index+1));
    const indicator = textNode('span','mv-indicator','READY');
    top.append(label,indicator);
    const title = textNode('div','mv-video-title','Choose a channel');
    frame.append(video,empty,top,title);
    const ctl = textNode('div','mv-pane-controls','');
    const name = textNode('p','mv-selected-name','Select a channel below');
    const select = document.createElement('select');select.setAttribute('aria-label','Choose channel for screen '+(index+1));
    select.append(new Option('Select channel…',''));
    const row=textNode('div','mv-pane-actions','');
    function actionButton(cls, symbol, description) {
      const b=document.createElement('button');b.type='button';b.className=cls;
      b.append(textNode('span','mv-action-icon',symbol),textNode('span','mv-action-label',description));
      b.setAttribute('title',description); b.setAttribute('aria-label',description+' — screen '+(index+1));
      return b;
    }
    const pick=actionButton('mv-pick','☷','Channels');
    const audio=actionButton('mv-audio','♫','Listen here');
    const stop=actionButton('mv-stop','■','Stop');
    row.append(pick,audio,stop);ctl.append(name,select,row);root.append(frame,ctl);
    const p={root,video,empty,indicator,title,name,select,pick,audio,stop,hls:null,current:null,ticket:0};
    const showPicker=()=>{root.classList.toggle('is-choosing');if(root.classList.contains('is-choosing'))select.focus();};
    pick.addEventListener('click',showPicker);
    empty.addEventListener('click',showPicker);
    select.addEventListener('change', () => {
      if (select.value === '') { dispose(p); return; }
      root.classList.remove('is-choosing');
      const chosen=bridge.getChannels()[Number(select.value)];
      if (chosen) tune(p, chosen);
    });
    audio.addEventListener('click', () => {audioPane=paneControllers.indexOf(p);updateAudio();setStatus('Audio now plays from Screen '+(audioPane+1)+'.');});
    stop.addEventListener('click',()=>{dispose(p);setStatus('Screen '+(index+1)+' stopped.');});
    video.addEventListener('playing',()=>{p.indicator.textContent='LIVE';});
    video.addEventListener('waiting',()=>{if(p.current)p.indicator.textContent='BUFFERING';});
    video.addEventListener('error',()=>{if(!p.current||!video.currentSrc)return;reportFailure(p,'Stream failed. Check provider permissions, HTTPS/CORS and codecs.');});
    return p;
  }
  function reportFailure(p, msg) {p.indicator.textContent='UNAVAILABLE';setStatus('Screen '+(paneControllers.indexOf(p)+1)+': '+msg);}
  function optionsFor(p, previous) {
    const opts=[new Option('Select channel…','')];
    bridge.getChannels().forEach((ch,i)=>{opts.push(new Option(ch.name+' · '+(ch.group||'Other'),String(i)));});
    p.select.replaceChildren(...opts);
    if(previous){const idx=bridge.getChannels().findIndex(ch=>ch.url===previous.url && ch.name===previous.name);
      if(idx>=0)p.select.value=String(idx); else dispose(p);}
  }
  function tune(p, ch) {
    const url=validStream(ch.url);
    dispose(p);
    if(!url){reportFailure(p,'A browser-compatible HTTPS or HTTP source is required.');return;}
    p.current=ch;
    p.title.textContent=ch.name;p.name.textContent=ch.name;
    const idx=bridge.getChannels().findIndex(c=>c.url===ch.url&&c.name===ch.name);
    if(idx>=0)p.select.value=String(idx);
    p.indicator.textContent='CONNECTING';p.empty.hidden=true;p.video.hidden=false;
    p.video.muted=paneControllers.indexOf(p)!==audioPane;
    const ticket=p.ticket;
    const path=new URL(url).pathname.toLowerCase();
    const native=p.video.canPlayType('application/vnd.apple.mpegurl');
    const direct=/\.(mp4|m4v|webm|ogv|mov|mp3|aac)$/i.test(path);
    if(direct||native){
      p.video.src=url;
      p.video.play().catch(()=>{if(ticket===p.ticket)setStatus('Screen '+(paneControllers.indexOf(p)+1)+': press Play if browser autoplay is blocked.');});
    } else if(window.Hls && window.Hls.isSupported()) {
      let recovered=false;
      const hls=new window.Hls({enableWorker:true,maxBufferLength:16,backBufferLength:8});
      p.hls=hls;
      hls.on(window.Hls.Events.ERROR,(_evt,error)=>{
        if(ticket!==p.ticket || !error.fatal)return;
        if(error.type===window.Hls.ErrorTypes.MEDIA_ERROR&&!recovered){recovered=true;hls.recoverMediaError();return;}
        reportFailure(p, 'Playback failed ('+(error.details||'stream error')+'). Provider CORS, codec or connection limits may apply.');
      });
      hls.loadSource(url);hls.attachMedia(p.video);
      hls.on(window.Hls.Events.MANIFEST_PARSED,()=>{
        if(ticket!==p.ticket)return;
        p.video.play().catch(()=>setStatus('Select Play in Screen '+(paneControllers.indexOf(p)+1)+' to begin streaming.'));
      });
    } else reportFailure(p,'HLS playback is not supported by this browser.');
  }
  function renderLayout(target) {
    if(!active||limit<2)return;
    const chosen=target===4&&limit>=4?4:2;
    const retain=paneControllers.slice(0,chosen).map(p=>p.current);
    // Stop all connections during layout changes, then resume retained channels.
    paneControllers.forEach(dispose);
    paneControllers=[];grid.replaceChildren();count=chosen;
    if(audioPane>=count)audioPane=0;
    for(let i=0;i<count;i++){
      const p=pane(i);paneControllers.push(p);grid.append(p.root);
      optionsFor(p,retain[i]);
    }
    grid.classList.toggle('mv-grid-four',count===4);
    byId('mvTwo').classList.toggle('is-active',count===2);
    byId('mvFour').classList.toggle('is-active',count===4);
    byId('mvTwo').setAttribute('aria-pressed',String(count===2));
    byId('mvFour').setAttribute('aria-pressed',String(count===4));
    updateAudio();
    retain.forEach((ch,i)=>{if(ch && paneControllers[i])tune(paneControllers[i],ch);});
    setStatus(count+' screens ready · '+bridge.getChannels().length+' channels in your current playlist.');
  }
  async function getAccess() {
    if(local) return {max_panes:4,preview:true,plan:'standalone',feature_live:false};
    const resp=await fetch('/api/features/multiview',{credentials:'same-origin',cache:'no-store'});
    if(resp.status===401)throw new Error('Sign in to use Multi-View.');
    if(!resp.ok)throw new Error('Multi-View plan status unavailable. Try again later.');
    return await resp.json();
  }
  async function open(){
    if(active)return;
    message.textContent='Checking plan access…';
    byId('multiviewBtn').disabled=true;
    try {access=await getAccess();} catch(e) {message.textContent=e.message;bridge.announce(e.message,'warn');return;} finally {byId('multiviewBtn').disabled=false;}
    const allowed=Number(access.max_panes)||0;
    if(allowed<2){
      message.textContent='Multi-View is not included with Free. Plus supports 2 screens; Premium and Family are planned for up to 4. The 7-day Plus trial is not yet active in this build.';
      bridge.announce('Multi-View is locked for this account. Check your plan.','warn');
      return;
    }
    if(!bridge.getChannels().length){
      message.textContent='Load your authorized M3U playlist before opening Multi-View.';
      bridge.announce('Choose a playlist or import an authorized local M3U file first.','warn');
      return;
    }
    limit=allowed;
    const previous=bridge.getCurrent?.();
    bridge.stopMain();
    active=true;
    byId('playerCard').hidden=true;
    main.hidden=false;
    byId('mvFour').disabled=limit<4;
    message.textContent=access.preview?
      'PRIVATE STAGING PREVIEW · Layouts enabled for testing. No paid subscription granted.':
      'Plan: '+String(access.plan||'unknown').toUpperCase()+' · Up to '+limit+' screens. Provider connection limits still apply.';
    renderLayout(2);
    if(previous && paneControllers[0])tune(paneControllers[0],previous);
    returnFocus=document.activeElement;
    document.body.classList.add('mv-immersive-open');
    main.focus({preventScroll:true});
  }
  function close(){
    if(!active)return;
    paneControllers.forEach(dispose);paneControllers=[];
    grid.replaceChildren();active=false;
    main.hidden=true;byId('playerCard').hidden=false;
    document.body.classList.remove('mv-immersive-open');
    if(document.fullscreenElement === main && document.exitFullscreen) document.exitFullscreen().catch(()=>{});
    if(returnFocus && returnFocus.focus) returnFocus.focus({preventScroll:true});
    returnFocus=null;access=null;limit=0;
    setStatus('Multi-View stopped.');
  }
  window.TunelyMultiView={close,isActive:()=>active};
  byId('multiviewBtn').addEventListener('click',open);
  byId('mvExit').addEventListener('click',close);
  byId('mvStopAll').addEventListener('click',()=>{paneControllers.forEach(dispose);setStatus('All screens stopped.');});
  byId('mvTwo').addEventListener('click',()=>renderLayout(2));
  byId('mvFour').addEventListener('click',()=>renderLayout(4));
  const fsButton=byId('mvFullscreen');
  fsButton.addEventListener('click',async()=>{
    if(!active) return;
    try {
      if(document.fullscreenElement===main) await document.exitFullscreen();
      else if(main.requestFullscreen) await main.requestFullscreen();
      else setStatus('Immersive view is already active. Browser fullscreen is unavailable here.');
    } catch { setStatus('Immersive view is active; your browser did not allow native fullscreen.'); }
  });
  document.addEventListener('fullscreenchange',()=>{
    const fs=document.fullscreenElement===main;
    fsButton.setAttribute('aria-pressed',String(fs));
    fsButton.setAttribute('aria-label',fs?'Exit browser fullscreen':'Enter browser fullscreen');
    const label=fsButton.querySelector('.mv-fullscreen-label');
    if(label) label.textContent=fs?'Windowed':'Fullscreen';
  });
  document.addEventListener('keydown',ev=>{if(active&&ev.key==='Escape' && document.fullscreenElement !== main) close();});
})();
