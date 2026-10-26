"""Official CurseForge API client. Credentials and downloads stay on the host.

No catalog scraping, synthesized download URLs, or persistent catalog cache.
"""
import base64, hashlib, io, json, os, pathlib, re, stat, urllib.error, urllib.parse, urllib.request, zipfile

API = 'https://api.curseforge.com'
MAX_DOWNLOAD = 16 * 1024 * 1024
MAX_JSON = 4 * 1024 * 1024
CONFIG = pathlib.Path.home() / '.config/carvalholinks'

class ApiError(ValueError): pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def key():
    value=os.environ.get('CURSEFORGE_API_KEY','').strip()
    if not value:
        path=CONFIG/'curseforge.key'
        try:
            fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        except FileNotFoundError:return None
        except OSError:raise ApiError('Não foi possível ler a chave privada do CurseForge.')
        with os.fdopen(fd,'r') as f:
            info=os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or (os.name!='nt' and (info.st_mode&0o077 or info.st_uid!=os.getuid())):
                raise ApiError('A chave deve pertencer ao usuário do painel e ter permissão 600.')
            value=f.read(1025).strip()
    if not value:return None
    if len(value)>1024 or any(c.isspace() for c in value):raise ApiError('Formato da chave do CurseForge inválido.')
    return value

def connection():
    configured=bool(key())
    return dict(configured=configured,docs='https://docs.curseforge.com/rest-api/',message='Chave configurada; use Conectar para testar o catálogo.' if configured else 'Aguardando a aprovação da chave. O catálogo e os downloads pela API serão liberados após a configuração no servidor.')

def number(value,name='ID',minimum=1,maximum=2147483647):
    if type(value) is bool:raise ApiError(name+' inválido.')
    try:n=int(value)
    except (ValueError,TypeError):raise ApiError(name+' inválido.')
    if str(value)!=str(n) or not minimum<=n<=maximum:raise ApiError(name+' inválido.')
    return n

def cdn_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not p.hostname or not p.hostname.endswith('.forgecdn.net') or p.username or p.password or p.port not in (None,443) or not p.path.startswith('/files/'):
        raise ApiError('O endereço de download não pertence ao CDN autorizado do CurseForge.')
    return url

def public_url(url,kind='website'):
    try:
        p=urllib.parse.urlsplit(url or '')
        valid=p.scheme=='https' and not p.username and not p.password and p.port in (None,443)
        if kind=='image':valid=valid and p.hostname in ('media.forgecdn.net','mediafilez.forgecdn.net')
        else:valid=valid and p.hostname in ('www.curseforge.com','curseforge.com') and p.path.startswith('/minecraft-bedrock/')
        return url if valid else ''
    except ValueError:return ''

def status_error(code):
    return {401:'Chave do CurseForge inválida ou ainda não liberada.',403:'Acesso ou download não autorizado pelo CurseForge. Use a página oficial do projeto.',404:'Projeto ou arquivo não encontrado no CurseForge.',429:'Limite de consultas atingido. Aguarde antes de tentar novamente.'}.get(code,'O CurseForge está indisponível. Tente novamente mais tarde.')

class Client:
    def __init__(self):
        self.secret=key()
        if not self.secret:raise ApiError('Chave ainda não configurada. Os links oficiais continuam disponíveis.')
        self.opener=urllib.request.build_opener(NoRedirect())
        self.calls=0

    def get(self,path,params=None):
        self.calls+=1
        if self.calls>32:raise ApiError('Limite de consultas por operação atingido. Configure o ID do jogo Bedrock para reduzir a descoberta automática.')
        url=API+path
        if params:url+='?'+urllib.parse.urlencode({k:v for k,v in params.items() if v is not None and v!=''})
        req=urllib.request.Request(url,headers={'Accept':'application/json','x-api-key':self.secret,'User-Agent':'CarvalhoLinks-Minecraft-Admin/0.2'})
        try:
            with self.opener.open(req,timeout=18) as response:
                raw=response.read(MAX_JSON+1)
            if len(raw)>MAX_JSON:raise ApiError('Resposta do catálogo excedeu o limite esperado.')
            result=json.loads(raw)
            if not isinstance(result,dict) or 'data' not in result:raise ApiError('Resposta inesperada do CurseForge.')
            return result
        except urllib.error.HTTPError as e:raise ApiError(status_error(e.code)) from None
        except (urllib.error.URLError,TimeoutError,OSError):raise ApiError('Não foi possível conectar ao CurseForge. Verifique a rede e tente novamente.') from None
        except (ValueError,TypeError) as e:
            if isinstance(e,ApiError):raise
            raise ApiError('Resposta inválida do catálogo CurseForge.') from None

    def game(self,requested=None):
        configured=os.environ.get('CURSEFORGE_GAME_ID')
        if requested or configured:
            g=self.get('/v1/games/'+str(number(requested or configured,'Jogo')))['data']
            if g.get('slug')!='minecraft-bedrock':raise ApiError('Somente o catálogo Minecraft Bedrock é permitido.')
            return g['id']
        for index in range(0,1000,50):
            data=self.get('/v1/games',dict(index=index,pageSize=50))['data']
            found=next((g for g in data if g.get('slug')=='minecraft-bedrock'),None)
            if found:return found['id']
            if len(data)<50:break
        raise ApiError('O catálogo Bedrock não foi encontrado nesta chave. Confira o acesso aprovado pelo CurseForge.')

    def project(self,project_id,game_id):
        p=self.get('/v1/mods/'+str(number(project_id,'Projeto')))['data']
        if p.get('gameId')!=game_id:raise ApiError('Projeto fora do catálogo Minecraft Bedrock.')
        return p

    def projects(self,req):
        game=self.game(req.get('gameId'));page=number(req.get('page',0),'Página',0,99)
        query=str(req.get('query','')).strip()
        if len(query)>100:raise ApiError('Busca muito longa.')
        version=str(req.get('version','')).strip()
        if version and not re.fullmatch(r'[0-9][0-9.]{1,23}',version):raise ApiError('Versão inválida.')
        sort=req.get('sort','popular')
        if sort not in ('popular','updated','name'):raise ApiError('Ordenação inválida.')
        params=dict(gameId=game,searchFilter=query,gameVersion=version,sortField={'popular':6,'updated':3,'name':4}[sort],sortOrder='asc' if sort=='name' else 'desc',pageSize=12,index=page*12)
        if req.get('category'):params['categoryId']=number(req['category'],'Categoria')
        result=self.get('/v1/mods/search',params)
        return dict(gameId=game,projects=[project_view(p) for p in result['data'] if p.get('gameId')==game],pagination=result.get('pagination',{}))

    def categories(self,req):
        game=self.game(req.get('gameId'))
        items=self.get('/v1/categories',dict(gameId=game))['data']
        return dict(gameId=game,categories=[dict(id=x['id'],name=x.get('name',''),parent=x.get('parentCategoryId')) for x in items if x.get('gameId',game)==game])

    def files(self,req):
        game=self.game(req.get('gameId'));p=self.project(req.get('projectId'),game)
        page=number(req.get('page',0),'Página',0,99)
        result=self.get('/v1/mods/'+str(p['id'])+'/files',dict(index=page*20,pageSize=20))
        files=[file_view(f,p) for f in result['data']]
        return dict(gameId=game,project=project_view(p),files=files,pagination=result.get('pagination',{}))

    def download(self,p,file_id):
        fid=number(file_id,'Arquivo');f=self.get('/v1/mods/'+str(p['id'])+'/files/'+str(fid))['data']
        if f.get('id')!=fid or f.get('modId')!=p['id']:raise ApiError('Arquivo não pertence ao projeto selecionado.')
        meta=file_view(f,p)
        if not meta['eligible']:raise ApiError(meta['reason'])
        # The official resolver is authoritative; never construct or guess a CDN URL.
        url=self.get('/v1/mods/'+str(p['id'])+'/files/'+str(fid)+'/download-url')['data']
        if not url:raise ApiError('Download direto não disponibilizado pelo autor. Use a página oficial.')
        for attempt in range(4):
            cdn_url(url)
            request=urllib.request.Request(url,headers={'x-api-key':self.secret,'User-Agent':'CarvalhoLinks-Minecraft-Admin/0.2'})
            try:
                with self.opener.open(request,timeout=30) as response:
                    if int(response.headers.get('Content-Length','0'))>MAX_DOWNLOAD:raise ApiError('Arquivo excede o limite de 16 MB.')
                    blob=response.read(MAX_DOWNLOAD+1)
                break
            except urllib.error.HTTPError as e:
                if e.code in (301,302,303,307,308) and e.headers.get('Location') and attempt<3:
                    url=urllib.parse.urljoin(url,e.headers['Location']);continue
                raise ApiError(status_error(e.code)) from None
            except (urllib.error.URLError,TimeoutError,OSError):raise ApiError('Falha ao baixar o arquivo do CDN oficial.') from None
        if not blob or len(blob)>MAX_DOWNLOAD or len(blob)!=f.get('fileLength'):raise ApiError('Tamanho do download não confere com o arquivo anunciado.')
        checked=False
        for item in f.get('hashes',[]):
            algorithm={1:'sha1',2:'md5'}.get(item.get('algo'))
            if algorithm:
                if hashlib.new(algorithm,blob).hexdigest().lower()!=str(item.get('value','')).lower():raise ApiError('Checksum do download não confere. Instalação cancelada.')
                checked=True
        if not checked:raise ApiError('A API não forneceu checksum suportado para validar este download.')
        if not zipfile.is_zipfile(io.BytesIO(blob)):raise ApiError('O download não contém um pacote Bedrock válido.')
        return blob,meta

def project_view(p):
    return dict(id=p['id'],name=str(p.get('name',''))[:200],summary=str(p.get('summary',''))[:700],authors=[dict(name=str(a.get('name',''))[:120]) for a in p.get('authors',[])[:8]],image=public_url((p.get('logo') or {}).get('thumbnailUrl'),'image'),website=public_url((p.get('links') or {}).get('websiteUrl')),downloads=p.get('downloadCount',0),updated=p.get('dateModified'),distribution=p.get('allowModDistribution'),categories=[str(c.get('name',''))[:80] for c in p.get('categories',[])[:5]])

def file_view(f,p):
    name=str(f.get('fileName',''));reason=''
    if p.get('allowModDistribution') is False:reason='O autor desativou downloads por ferramentas externas. Use a página oficial.'
    elif not f.get('isAvailable',False):reason='Arquivo indisponível para download.'
    elif f.get('isEarlyAccessContent'):reason='Conteúdo em acesso antecipado: consulte a página oficial.'
    elif not name.lower().endswith(('.mcpack','.mcaddon')):reason='Formato fora do escopo: selecione .mcpack ou .mcaddon.'
    elif not 0<f.get('fileLength',0)<=MAX_DOWNLOAD:reason='Arquivo excede o limite de 16 MB ou tem tamanho inválido.'
    return dict(id=f['id'],name=str(f.get('displayName',name))[:200],filename=pathlib.PurePosixPath(name.replace('\\','/')).name,size=f.get('fileLength',0),release=f.get('releaseType'),date=f.get('fileDate'),versions=f.get('gameVersions',[])[:20],dependencies=[dict(projectId=d['modId'],type=d.get('relationType')) for d in f.get('dependencies',[])[:30]],eligible=not reason,reason=reason)

def handle(req,admin):
    action=req['action']
    if action=='cf_status':return connection()
    client=Client()
    if action=='cf_search':return client.projects(req)
    if action=='cf_categories':return client.categories(req)
    if action=='cf_files':return client.files(req)
    if action not in ('cf_download','cf_install'):raise ApiError('Ação CurseForge não permitida.')
    game=client.game(req.get('gameId'));p=client.project(req.get('projectId'),game)
    ids=req.get('fileIds',[])
    if not isinstance(ids,list) or not 1<=len(ids)<=4 or len(set(map(str,ids)))!=len(ids):raise ApiError('Selecione de um a quatro arquivos diferentes do mesmo projeto.')
    if action=='cf_download' and len(ids)!=1:raise ApiError('Selecione um arquivo para baixar.')
    downloaded=[];total=0
    for fid in ids:
        blob,meta=client.download(p,fid);total+=len(blob)
        if total>MAX_DOWNLOAD:raise ApiError('Os arquivos selecionados juntos excedem 16 MB.')
        downloaded.append((blob,meta))
    if action=='cf_download':
        blob,meta=downloaded[0]
        return dict(data=base64.b64encode(blob).decode(),filename=meta['filename'],message='Download oficial validado por checksum.')
    combined=io.BytesIO()
    with zipfile.ZipFile(combined,'w',zipfile.ZIP_STORED) as z:
        for blob,meta in downloaded:z.writestr('part-'+str(meta['id'])+pathlib.Path(meta['filename']).suffix.lower(),blob)
    # Reuse the archive validation, dependency checks, offline backup and rollback.
    result=admin.mutate(dict(action='install',data=base64.b64encode(combined.getvalue()).decode()))
    result['message']='Addon do CurseForge instalado com backup. Confira os logs e a interface dentro do jogo.'
    return result
