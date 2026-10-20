"""Optional TMDb metadata discovery for TunelyTV. No movies/TV streams supplied.

Requires explicit license/terms review and an operator-supplied token. Metadata API
returns title information and reported external watch providers, never stream URLs.
"""
from __future__ import annotations
import json, os, re, threading, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from fastapi import HTTPException

API='https://api.themoviedb.org/3'
SERVICES={'Netflix':'netflix','Prime Video':'amazon prime video','Disney+':'disney plus','Hulu':'hulu',
          'Max':'max','Apple TV+':'apple tv plus','Peacock':'peacock','Paramount+':'paramount plus'}

def install_discovery(app):
    # Token is never returned to frontend. Explicit opt-in prevents accidental commercial use.
    token=os.getenv('TUNELY_TMDB_READ_TOKEN','').strip()
    api_key=os.getenv('TUNELY_TMDB_API_KEY','').strip()
    enabled=os.getenv('TUNELY_METADATA_ENABLED','').lower()=='true' and bool(token or api_key)
    cache={};lock=threading.Lock()
    def fetch(path,params=None,ttl=1200):
        if not enabled:raise HTTPException(status_code=503,detail='Metadata discovery is not configured.')
        args=dict(params or {});args.setdefault('language','en-US')
        if not token:args['api_key']=api_key
        cache_key=(path,tuple(sorted(args.items())))
        with lock:
            entry=cache.get(cache_key)
            if entry and time.time()-entry[0]<ttl:return entry[1]
        address=API+path+'?'+urlencode(args)
        req=Request(address,headers={'Accept':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        try:
            with urlopen(req,timeout=7) as res:
                raw=res.read(1_200_001)
                if len(raw)>1_200_000:raise ValueError('Metadata reply too large')
                data=json.loads(raw)
        except (HTTPError,URLError,TimeoutError,ValueError) as exc:
            raise HTTPException(status_code=502,detail='Metadata provider unavailable') from exc
        with lock:
            if len(cache)>160:cache.clear()
            cache[cache_key]=(time.time(),data)
        return data
    def region_ok(region):
        if not re.fullmatch(r'[A-Z]{2}',region):raise HTTPException(422,'Choose a two-letter country code')
        return region
    def safeimage(raw):
        return 'https://image.tmdb.org/t/p/w500'+raw if isinstance(raw,str) and re.fullmatch(r'/[a-zA-Z0-9_/-]+\.(?:jpg|png|webp)',raw) else None
    def serialize(item,kind=None):
        kind=kind or item.get('media_type','movie')
        if kind not in ('movie','tv'):return None
        date=str(item.get('release_date') or item.get('first_air_date') or '')
        return {'id':item.get('id'),'kind':kind,'title':item.get('title') or item.get('name') or 'Untitled',
                'year':date[:4] if len(date)>=4 else '', 'image':safeimage(item.get('backdrop_path') or item.get('poster_path'))}
    def normalized(items,kind=None):
        result=[]
        for item in items:
            obj=serialize(item,kind)
            if obj and isinstance(obj['id'],int):result.append(obj)
        return result[:20]
    def providers(kind):
        return fetch('/watch/providers/'+kind,{'watch_region':'US'},ttl=86400).get('results',[])
    def find_service_id(label):
        if label not in SERVICES:raise HTTPException(404,'Unknown service')
        needle=SERVICES[label]
        for item in providers('movie'):
            normalized_name=re.sub(r'[^a-z0-9]','',str(item.get('provider_name','')).lower())
            if normalized_name==re.sub(r'[^a-z0-9]','',needle):return item['provider_id']
        return None

    @app.get('/api/discover/status')
    def status():return {'enabled':enabled,'provider':'TMDb' if enabled else None,'country':'US','notice':'No content provided by TunelyTV'}

    @app.get('/api/discover/home')
    def home(region:str='US'):
        region_ok(region)
        movies=normalized(fetch('/trending/movie/week',{'region':region}).get('results',[]),'movie')
        series=normalized(fetch('/trending/tv/week',{}).get('results',[]),'tv')
        return {'movies':movies,'series':series,'region':region,'data_source':'TMDb discovery; not available through TunelyTV'}

    @app.get('/api/discover/provider')
    def provider(name:str='Netflix',region:str='US'):
        region_ok(region)
        provider_id=find_service_id(name)
        if provider_id is None:return {'results':[],'provider':name,'region':region}
        # Explicit provider + paid-subscription availability in the chosen country;
        # NOT official provider "Top 10" rankings.
        data=fetch('/discover/movie',{'sort_by':'popularity.desc','watch_region':region,
            'with_watch_providers':str(provider_id),'with_watch_monetization_types':'flatrate','include_adult':'false'})
        return {'results':normalized(data.get('results',[]),'movie'),'provider':name,'region':region,'label':'Reported availability, not provider ranking'}

    @app.get('/api/discover/search')
    def search(q:str):
        query=q.strip()
        if len(query)<2 or len(query)>100:raise HTTPException(422,'Search must contain 2–100 characters')
        data=fetch('/search/multi',{'query':query,'include_adult':'false'},ttl=300)
        return {'results':normalized(data.get('results',[])),'query':query}

    @app.get('/api/discover/title/{kind}/{title_id}')
    def detail(kind:str,title_id:int,region:str='US'):
        if kind not in ('movie','tv'):raise HTTPException(404,'Unsupported title kind')
        if title_id<=0:raise HTTPException(404,'Invalid title')
        region_ok(region)
        title=fetch('/'+kind+'/'+str(title_id),{},ttl=3600)
        raw=fetch('/'+kind+'/'+str(title_id)+'/watch/providers',{},ttl=1800).get('results',{}).get(region,{})
        provider_groups={key:[{'name':str(p.get('provider_name',''))} for p in raw.get(key,[]) if p.get('provider_name')][:25]
                         for key in ['flatrate','free','ads','rent','buy']}
        link=raw.get('link','')
        if not isinstance(link,str) or not link.startswith('https://www.themoviedb.org/'):
            link=''
        return {'kind':kind,'id':title_id,'overview':str(title.get('overview') or '')[:2000],
                'providers':provider_groups,'watch_link':link,'region':region,
                'note':'Provider information is third-party data, not TunelyTV stream access.'}
