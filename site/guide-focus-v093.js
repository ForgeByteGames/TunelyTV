// TunelyTV full-screen TV Guide v0.9.3. Uses the EXISTING authorized M3U/XMLTV
// parser/guide; no extra provider requests, no bundled content, no proxy.
(()=>{
'use strict';
const $ = id => document.getElementById(id);
const guide=$('theaterGuide');
const panel=$('panel-guide');
const origin=panel.parentElement;
const marker=document.createComment('epg-original-position');
origin.insertBefore(marker,panel);
const api=()=>window.TunelyGuideBridge;
let isOpen=false;
let lastFocus=null;
let chosenProgram=null;
let chosenChannel=null;
const safeStorage=(key,value)=>{try{if(value!==undefined)localStorage.setItem(key,value);return localStorage.getItem(key);}catch{return null;}};
const stamp=n=>new Date(n).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
function labelSelected(){
 const bridge=api();if(!bridge)return;
 const ch=chosenChannel||bridge.getCurrent();
 let program=chosenProgram;
 if(!ch){$('gfTitle').textContent='Your TV guide';$('gfChannel').textContent='Browse your playlist';$('gfTiming').textContent='';$('gfLabel').textContent='YOUR TV GUIDE';$('gfDesc').textContent='Pick a channel below to start watching. Program listings appear when an authorized XMLTV source is available.';$('gfProgress').hidden=true;return;}
 const {live}=bridge.getNowNext(ch);
 if(!program)program=live;
 const now=Date.now();
 $('gfLabel').textContent=program?(program.start<=now&&program.end>now?'ON NOW':'PROGRAM DETAILS'):'CURRENT CHANNEL';
 $('gfTitle').textContent=program?.title||ch.name;
 $('gfChannel').textContent=ch.name;
 $('gfTiming').textContent=program?(stamp(program.start)+' – '+stamp(program.end)):'';
 $('gfDesc').textContent=program?(program.desc||'No program description provided by your guide.'):'No XMLTV listing available for this channel. Select Watch TV to return to the player.';
 if(program){$('gfProgress').hidden=false;$('gfProgressFill').style.width=Math.max(0,Math.min(100,(now-program.start)/(program.end-program.start)*100))+'%';}
 else $('gfProgress').hidden=true;
}
function syncToolbar(){
 const src=$('sourcePick'),mirror=$('gfSource');
 const selected=src.value;
 mirror.replaceChildren();
 for(const opt of src.options)mirror.add(new Option(opt.textContent,opt.value));
 mirror.value=selected;
 if(!mirror.value&&selected)mirror.value=selected;
 const fav=document.querySelector('.quick[data-filter="favorites"]');
 const active=fav?.getAttribute('aria-pressed')==='true';
 $('gfFavorite').classList.toggle('is-selected',active);
 $('gfFavorite').setAttribute('aria-pressed',String(active));
 $('gfSearch').value=$('filter').value;
 const bridge=api(),count=bridge?.getChannels().length||0;
 $('gfStatus').textContent=count?`${count} channels in this playlist · ${bridge.getProgramsLoaded()?'Program listings from your XMLTV source':'No XMLTV loaded — channel selection is still available'}`:'Add an authorized playlist through your dashboard to see channels.';
}
function open(auto=false){
 if(isOpen||window.TunelyMultiView?.isActive())return;
 // The guide is outside #videoArea. Browser fullscreen hides all siblings,
 // so exit video fullscreen before presenting the guide (retaining playback).
 if(document.fullscreenElement){
   if(typeof document.exitFullscreen==='function'){
     Promise.resolve(document.exitFullscreen()).then(()=>open(auto)).catch(()=>{
       const status=$('gfStatus');if(status)status.textContent='Exit fullscreen, then open TV Guide.';
     });
   }
   return;
 }
 const bridge=api();if(!bridge)return;
 lastFocus=document.activeElement;isOpen=true;
 guide.hidden=false;document.body.classList.add('gf-open');document.querySelector('.app-shell').inert=true;
 closeSidebar();
 panel.hidden=false;
 $('gfViewport').append(panel);
 bridge.setGuideView('grid');
 chosenChannel=bridge.getCurrent();chosenProgram=null;
 syncToolbar();labelSelected();
 if(!auto)safeStorage('tunelytv.guide.lastmode.v1','guide');
 guide.focus({preventScroll:true});
}
function closeSidebar(){
 $('channelBrowser')?.classList.remove('drawer-open');
 if($('channelBackdrop'))$('channelBackdrop').hidden=true;
}
function close(){
 if(!isOpen)return;
 isOpen=false;guide.hidden=true;document.body.classList.remove('gf-open');document.querySelector('.app-shell').inert=false;
 marker.parentNode.insertBefore(panel,marker.nextSibling);
 // Preserve original tab state so the ordinary page remains functional.
 const guideSelected=document.querySelector('[data-tab="guide"]')?.getAttribute('aria-selected')==='true';
 if(!guideSelected)panel.hidden=true;
 chosenChannel=null;chosenProgram=null;
 safeStorage('tunelytv.guide.lastmode.v1','player');
 if(lastFocus?.isConnected)lastFocus.focus({preventScroll:true});
}
function toggle(){isOpen?close():open();}
function maybeStartInGuide(){
 // Guide-first navigation is useful for IPTV. Users can choose Watch TV and
 // that preference persists, so the guide doesn't forcibly reopen next visit.
 if(safeStorage('tunelytv.guide.lastmode.v1')!=='player')open(true);
}
$('theaterGuideBtn').addEventListener('click',()=>open());
$('guideTopButton').addEventListener('click',()=>open());
$('gfWatch').addEventListener('click',close);
$('gfClose').addEventListener('click',close);
$('gfEarlier').addEventListener('click',()=>$('guidePrev').click());
$('gfNow').addEventListener('click',()=>$('guideNow').click());
$('gfLater').addEventListener('click',()=>$('guideNext').click());
$('gfFavorite').addEventListener('click',()=>{
 const active=document.querySelector('.quick[data-filter="favorites"]')?.getAttribute('aria-pressed')==='true';
 document.querySelector(active?'.quick[data-filter="all"]':'.quick[data-filter="favorites"]')?.click();
 syncToolbar();
});
$('gfSearch').addEventListener('input',()=>{$('filter').value=$('gfSearch').value;$('filter').dispatchEvent(new Event('input',{bubbles:true}));});
$('gfSource').addEventListener('change',()=>{$('sourcePick').value=$('gfSource').value;$('sourcePick').dispatchEvent(new Event('change',{bubbles:true}));chosenProgram=null;chosenChannel=null;labelSelected();});
// The guide's existing event handlers tune channels and show details. Read the
// selected channel/program AFTER those handlers run; don't invent guide data.
$('guideGrid').addEventListener('click',event=>{
 if(!event.target.closest('.epg-channel-button,.epg-program'))return;
 queueMicrotask(()=>{
  const bridge=api();if(!bridge)return;
  chosenChannel=bridge.getCurrent();
  chosenProgram=bridge.getDetail()?.program||null;
  labelSelected();
 });
});
$('guideList').addEventListener('click',()=>queueMicrotask(()=>{chosenChannel=api()?.getCurrent();chosenProgram=null;labelSelected();}));
$('sourcePick').addEventListener('change',()=>{chosenChannel=null;chosenProgram=null;setTimeout(()=>{syncToolbar();labelSelected();},50);});
// Renders happen after remote M3U/XMLTV imports and search changes.
window.addEventListener('tunely:guide-rendered',()=>{if(isOpen){syncToolbar();labelSelected();}});
$('gfViewport').addEventListener('click',e=>{if(e.target.closest('.file-label'))setTimeout(close,0);});
document.addEventListener('keydown',e=>{
 if(!isOpen)return;
 if(e.key==='Escape'||e.key.toLowerCase()==='g'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)){
  e.preventDefault();e.stopImmediatePropagation();close();return;
 }
 if(e.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName)){
  e.preventDefault();e.stopImmediatePropagation();$('gfSearch').focus();return;
 }
 if(['ArrowDown','ArrowUp'].includes(e.key)&&!['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement?.tagName)){
  e.preventDefault();$('guideGrid').querySelector('.epg-scroll')?.scrollBy({top:e.key==='ArrowDown'?60:-60,behavior:'smooth'});
 }
});
window.TunelyGuideFocus={open,close,toggle,isOpen:()=>isOpen,maybeStartInGuide,refresh:()=>{if(isOpen){syncToolbar();labelSelected();}}};
})();
