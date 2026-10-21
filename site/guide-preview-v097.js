// TunelyTV 0.9.7: Single-source live guide preview + accessible guide setup.
// The original media element moves between two views, so we do not open a
// second connection or clone licensed streams.
(()=>{
'use strict';
const $=id=>document.getElementById(id);
const video=$('video'),home=$('videoArea'),slot=$('gfPreviewSlot'),guide=$('theaterGuide');
const advanced=document.querySelector('.epg-advanced-settings'),settingsHome=advanced?.parentElement;
const anchor=document.createComment('advanced-guide-settings-home');
if(settingsHome&&advanced)settingsHome.insertBefore(anchor,advanced);
let settingsVisible=false;
function syncPreview(){
 const hasMedia=!video.hidden;
 const empty=$('gfArtEmpty'),label=$('gfPreviewState'),art=$('gfArt');
 empty.hidden=hasMedia;
 label.hidden=!hasMedia;
 art.classList.toggle('is-live',hasMedia);
 // Do not trigger play/reconnect just to show a preview: use the same player.
}
function previewToGuide(){
 if(video.parentElement!==slot)slot.append(video);
 syncPreview();
}
function previewToPlayer(){
 if(video.parentElement!==home)home.insertBefore(video,home.firstChild);
 // Remove guide-specific styling without interrupting playback.
 syncPreview();
}
function showSettings(show){
 settingsVisible=!!show;
 $('gfSetupPanel').hidden=!show;
 $('gfGuideSettings').setAttribute('aria-expanded',String(!!show));
 if(show){
   if(advanced){$('gfSetupContent').append(advanced);advanced.open=true;}
 }else if(advanced&&settingsHome){
   anchor.parentNode.insertBefore(advanced,anchor.nextSibling);
 }
}
function refresh(){
 if(!guide.hidden)previewToGuide();
 else {previewToPlayer();showSettings(false);}
}
// The guide script is loaded before this enhancement. Wrap open/close through
// its public interface to support guide-first autostart and all exit paths.
const bridge=window.TunelyGuideFocus;
if(bridge){
 for(const name of ['open','close','toggle','maybeStartInGuide']){
   const orig=bridge[name];
   if(typeof orig==='function')bridge[name]=function(...args){
     const out=orig(...args);refresh();return out;
   };
 }
}
// Existing buttons capture the original close() function in their handlers;
// defer a sync after any guide button/key interaction. MutationObserver covers
// channel changes, script-triggered open/close and browser back/focus paths.
const observer=new MutationObserver(refresh);
observer.observe(guide,{attributes:true,attributeFilter:['hidden']});
const vidObserver=new MutationObserver(syncPreview);
vidObserver.observe(video,{attributes:true,attributeFilter:['hidden']});
$('gfGuideSettings').addEventListener('click',()=>showSettings(!settingsVisible));
$('gfSetupClose').addEventListener('click',()=>showSettings(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&settingsVisible){showSettings(false);}});
// Synchronize after the original guide-first startup is evaluated.
queueMicrotask(refresh);
})();
