(() => {
'use strict';
const by=id=>document.getElementById(id);
const officialServices={Netflix:'https://www.netflix.com/', 'Prime Video':'https://www.primevideo.com/', 'Disney+':'https://www.disneyplus.com/', Hulu:'https://www.hulu.com/', Max:'https://www.max.com/', 'Apple TV+':'https://tv.apple.com/', Peacock:'https://www.peacocktv.com/', 'Paramount+':'https://www.paramountplus.com/'};
const services=['Netflix','Prime Video','Disney+','Hulu','Max','Apple TV+','Peacock','Paramount+'];
const states={movies:[],series:[],service:[],status:null,serviceName:'Netflix',region:'US'};
const isDemo=Boolean(window.TUNELY_DEMO_PREVIEW);
const demos={movies:[['Blue Horizon','2026'],['Last Signal','2025'],['The City Below','2024'],['Northern Lights','2025'],['A Long Way Home','2024'],['The Glass Coast','2026'],['Midnight Crossing','2025'],['A Different Sky','2024'],['Final Orbit','2026']],series:[['Threshold','Series'],['Quiet Valley','Series'],['Voyager One','Series'],['Deep Currents','Series'],['The Archives','Series'],['Blue Hour','Series'],['After Tomorrow','Series'],['Highland Stories','Series'],['Beyond the Map','Series']]};
const make=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;return el};
const safeImage=url=>typeof url==='string'&&/^https:\/\/image\.tmdb\.org\/t\/p\/[^?#]+\.(?:jpg|jpeg|png|webp)(?:\?[^#]*)?$/i.test(url)?url:null;
const api=async path=>{const response=await fetch('/api/discover/'+path,{credentials:'same-origin'});const obj=await response.json();if(!response.ok)throw new Error(obj.detail||'Discovery is temporarily unavailable');return obj;};
function placeholder(text){const box=make('div','rail-empty',text);return box;}
function renderRail(id,items,empty){const root=by(id);root.replaceChildren();if(!items.length){root.append(placeholder(empty));return;}for(const entry of items){
 const btn=make('button','rail-card');btn.type='button';btn.title='View details and where to watch';
 const art=make('div','rail-art');const imgUrl=safeImage(entry.image);
 if(imgUrl){const img=make('img');img.src=imgUrl;img.alt='';img.loading='lazy';img.referrerPolicy='no-referrer';art.append(img);}
 const label=make('span','art-label',entry.title||'Untitled');art.append(label);btn.append(art);
 const sub=make('div','card-sub');sub.textContent=(entry.year?entry.year+' · ':'')+(entry.kind==='tv'?'Series':'Movie');btn.append(sub);
 btn.addEventListener('click',()=>{if(id==='serviceRail' && !entry.demo && officialServices[states.serviceName]){window.open(officialServices[states.serviceName],'_blank','noopener,noreferrer');}else openTitle(entry);});root.append(btn);
 }}
function demoEntries(kind){return (demos[kind]||demos.movies).map((x,i)=>({id:i+1,title:x[0],year:x[1],kind:kind==='series'?'tv':'movie',demo:true}));}
function showDemo(){states.movies=demoEntries('movies');states.series=demoEntries('series');states.service=demoEntries('movies').slice(0,7);renderRail('movieRail',states.movies,'');renderRail('seriesRail',states.series,'');renderRail('serviceRail',states.service,'');by('serviceRowLabel').textContent='Illustrative titles only';}
const disabled='Title discovery is being prepared. No catalog or programming is included with TunelyTV.';
async function boot(){
  void window.TunelyLibrary?.load();
  if(isDemo){states.service=demoEntries('movies').slice(0,7);renderRail('serviceRail',states.service,'');by('serviceRowLabel').textContent='Illustrative where-to-watch titles only';return;}
  try{states.status=await api('status');if(states.status.enabled)by('metadataCredits').hidden=false;
    if(!states.status.enabled){renderRail('serviceRail',[],'Title discovery is not enabled. Licensed metadata is required.');return;}
    await chooseService('Netflix');
  }catch{renderRail('serviceRail',[],'Where-to-watch discovery is temporarily unavailable.');}
}
const pills=by('servicePills');for(const name of services){const b=make('button','service-pill',name);b.type='button';b.dataset.service=name;b.classList.toggle('selected',name==='Netflix');b.addEventListener('click',()=>chooseService(name));pills.append(b);}
async function chooseService(name){states.serviceName=name;by('serviceRowTitle').textContent='Explore on '+name;
 for(const el of pills.children)el.classList.toggle('selected',el.dataset.service===name);
 if(isDemo){renderRail('serviceRail',demoEntries('movies'),'');by('serviceRowLabel').textContent='Illustrative titles only';return;}
 if(!states.status?.enabled){renderRail('serviceRail',[],disabled);return;}
 renderRail('serviceRail',[],'Finding licensed provider-discovery data…');
 try{const response=await api('provider?name='+encodeURIComponent(name)+'&region='+states.region);states.service=response.results||[];
 renderRail('serviceRail',states.service,'No provider availability results reported for '+name+'.');by('serviceRowLabel').textContent='Reported availability · '+states.region;
 }catch{renderRail('serviceRail',[],'Availability data currently unavailable.');}
}
const setOpen=(id,open)=>{by(id).hidden=!open;document.body.style.overflow=open?'hidden':'';};
function closeAll(){setOpen('searchDialog',false);setOpen('detailDialog',false);}
by('openSearch').addEventListener('click',()=>{setOpen('searchDialog',true);by('searchQuery').focus();});
by('serviceHelp').addEventListener('click',()=>{by('openSearch').click();by('searchMessage').textContent='Search a specific title to see reported subscription, free-with-ads, rental, and purchase options in your country. Provider availability is not a TunelyTV subscription.';});
document.querySelectorAll('[data-close]').forEach(el=>el.addEventListener('click',closeAll));
for(const layer of document.querySelectorAll('.dialog-layer'))layer.addEventListener('click',e=>{if(e.target===layer)closeAll();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeAll();if(e.key==='/'&&document.activeElement?.tagName!=='INPUT'&&!by('searchDialog').hidden){e.preventDefault();by('searchQuery').focus();}});
by('searchForm').addEventListener('submit',async e=>{
 e.preventDefault();const q=by('searchQuery').value.trim();if(q.length<2)return;
 const target=by('searchResults');target.replaceChildren();by('searchMessage').textContent='Searching…';
 if(isDemo){const all=[...states.movies,...states.series];const matching=all.filter(i=>i.title.toLowerCase().includes(q.toLowerCase()));showResults(matching);return;}
 try{const res=await api('search?q='+encodeURIComponent(q));showResults(res.results||[]);}catch(err){by('searchMessage').textContent='Title search is not available until licensed metadata access is configured.';}
});
function showResults(results){const target=by('searchResults');target.replaceChildren();by('searchMessage').textContent=results.length?`${results.length} matching title(s)`:'No matching titles found in the available catalog.';
 for(const t of results){const b=make('button','result-row');const left=make('strong','',t.title||'Untitled');const right=make('span','',`${t.year||'Year unknown'} · ${t.kind==='tv'?'Series':'Movie'}`);b.append(left,right);b.addEventListener('click',()=>openTitle(t));target.append(b);}}
async function openTitle(item){setOpen('searchDialog',false);setOpen('detailDialog',true);
 const t=by('detailTitle'),body=by('detailBody');t.textContent=(item.title||'Title')+(item.year?' ('+item.year+')':'');body.replaceChildren();
 if(item.demo){body.append(make('p','','This fictional title is used for design preview only. No streaming availability or access is claimed.'));return;}
 body.append(make('p','','Finding authorized where-to-watch information…'));
 try{const data=await api('title/'+encodeURIComponent(item.kind)+'/'+encodeURIComponent(item.id)+'?region='+states.region);
 body.replaceChildren();body.append(make('p','',data.overview||'No description available.'));
 let found=false;for(const [key,label] of [['flatrate','Included with subscription'],['free','Free'],['ads','Free with ads'],['rent','Rent'],['buy','Buy']]){
 const providers=data.providers?.[key]||[];if(!providers.length)continue;found=true;
 const group=make('div','provider-group');group.append(make('b','',label));const row=make('div','provider-list');providers.forEach(provider=>row.append(make('span','provider-label',provider.name)));group.append(row);body.append(group);}
 if(!found)body.append(make('p','','No viewing providers reported in '+states.region+' for this title.'));
 const link=data.watch_link;
 if(/^https:\/\/www\.themoviedb\.org\//.test(link||'')){const a=make('a','detail-external','View legal watching options ↗');a.href=link;a.target='_blank';a.rel='noopener noreferrer';body.append(a);}
 body.append(make('p','','Watch-provider availability is reported via TMDB using JustWatch data, may change, and is not a TunelyTV subscription. TunelyTV does not provide the movie or series.'));
 }catch{body.replaceChildren(make('p','','Availability details are temporarily unavailable.'))}
}
for(const button of document.querySelectorAll('[data-show-all]'))button.addEventListener('click',()=>{const name=button.dataset.showAll;const id=name==='movies'?'movieRail':'seriesRail';const rail=by(id);rail.classList.toggle('expanded');button.textContent=rail.classList.contains('expanded')?'Show less':'View all ›';});
by('navToggle').addEventListener('click',()=>{const nav=document.querySelector('.site-nav');const open=nav.classList.toggle('open');by('navToggle').setAttribute('aria-expanded',String(open));});
for(const link of document.querySelectorAll('.site-nav a'))link.addEventListener('click',()=>{document.querySelector('.site-nav').classList.remove('open');by('navToggle').setAttribute('aria-expanded','false');});
// A custom main domain directs Live TV to its dedicated subdomain; Railway testing stays same-origin.
if(['tunelytv.com','www.tunelytv.com'].includes(location.hostname))for(const a of document.querySelectorAll('[data-stream-link]'))a.href='https://stream.tunelytv.com/watch';
boot();
})();
