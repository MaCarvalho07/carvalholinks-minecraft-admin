#!/usr/bin/env python3
"""Local Minecraft operations. Invoked by the authenticated Cockpit bridge, no listener."""
import base64, contextlib, datetime as dt, fcntl, hashlib, io, json, os, pathlib, re, shutil, stat, subprocess, sys, tarfile, tempfile, time, uuid, zipfile

ROOT = pathlib.Path(os.environ.get('CARV_MC_ROOT', str(pathlib.Path.home() / 'minecraft-bedrock')))
DATA = ROOT / 'data'
STATE = ROOT / 'admin-state'
CONTAINER = 'minecraft-bedrock'
BRIDGE = '89140f53-6fdc-43cd-8b5c-a5d51f824e80'
LIMIT = 16 * 1024 * 1024

def run(args, timeout=30, check=True):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise ValueError((p.stderr or p.stdout or 'Comando falhou')[-1600:])
    return p.stdout

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(tmp, path)

def properties():
    return dict(line.split('=', 1) for line in (DATA/'server.properties').read_text().splitlines() if '=' in line and not line.startswith('#'))

def world():
    p = (DATA/'worlds'/properties().get('level-name', 'Bedrock level')).resolve()
    if p.parent != (DATA/'worlds').resolve() or not p.is_dir():
        raise ValueError('Mundo principal inválido')
    return p

def refs(kind):
    p = world()/('world_'+kind+'.json')
    return json.loads(p.read_text()) if p.exists() else []

def inspect():
    return json.loads(run(['docker', 'inspect', CONTAINER]))[0]

def logs():
    p=subprocess.run(['docker','logs','--since','3m','--tail','1600',CONTAINER],capture_output=True,text=True,timeout=15)
    return p.stdout+p.stderr

def bridge_data(raw):
    latest = None
    for line in raw.splitlines():
        if '[CARV_ADMIN_V1]' not in line: continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(line.split('[CARV_ADMIN_V1]',1)[1].lstrip())
            if obj.get('schema') == 1 and isinstance(obj.get('players'),list): latest = obj
        except (ValueError, TypeError): pass
    if latest:
        age = max(0, time.time() - latest.get('at',0)/1000)
        return dict(available=age<45, age=round(age), snapshot=latest)
    return dict(available=False, age=None, snapshot=None)

def packs():
    result=[]
    for kind in ('behavior_packs','resource_packs'):
        active={r['pack_id']:r for r in refs(kind)}
        for p in sorted((DATA/kind).glob('*/manifest.json')):
            if p.parent.name.startswith(('vanilla','chemistry','education','experimental')):continue
            if p.parent.name in ('editor','server_library','server_ui_library','server_editor_library'):continue
            try:
                m=json.loads(p.read_text(encoding='utf-8-sig')); h=m['header']
                name=h['name']
                for lang in ('pt_BR','en_US'):
                    file=p.parent/'texts'/(lang+'.lang')
                    if file.is_file():
                        translated=next((s.split('=',1)[1] for s in file.read_text(encoding='utf-8-sig').splitlines() if s.startswith(name+'=')),None)
                        if translated:name=translated;break
                result.append(dict(uuid=h['uuid'],name=name,version=h['version'],kind=kind,active=h['uuid'] in active,dependencies=m.get('dependencies',[]),protected=h['uuid']==BRIDGE))
            except (ValueError,KeyError): continue
    return result

def backup_list():
    out=[]
    for p in sorted((ROOT/'backups').glob('panel-*'),reverse=True):
        a=p/'snapshot.tar.gz'
        if a.is_file() and (p/'metadata.json').is_file():
            out.append(dict(id=p.name,bytes=a.stat().st_size,**json.loads((p/'metadata.json').read_text())))
    return out[:100]

def transport_diagnostic(lines,transport,verified):
    """Classify only the known startup banner; retain unrelated errors verbatim."""
    known={
        'Your current connection type is not set to NetherNet. In this release, NetherNet is the only supported transport type.',
        'Players will not be able to connect to your game without NetherNet.',
        "To switch, set 'transport=nethernet' in server.properties.",
        'For more information, please reference the included bedrock_server_how_to.html file.',
    }
    banner=[];errors=[];inside=False
    for line in lines:
        message=re.sub(r'^\[[^\]]+\]\s*','',line).strip()
        if re.fullmatch(r'=+\s+TRANSPORT\s+TYPE\s+ERROR\s+=+',message):
            inside=True;banner.append(line);continue
        if inside and (message in known or not message or re.fullmatch(r'=+',message)):
            banner.append(line)
            if message and re.fullmatch(r'=+',message):inside=False
            continue
        # An interleaved error must never be hidden inside the compatibility notice.
        errors.append(line)
    diagnostic=None
    if banner:
        confirmed=transport=='raknet' and verified
        diagnostic=dict(severity='info' if confirmed else 'warning',confirmed=bool(confirmed),lines=banner,
            title='Transporte legado · entrada confirmada' if confirmed else 'Transporte · entrada ainda não confirmada',
            message='O servidor usa RakNet e uma entrada foi confirmada nesta execução. O banner de inicialização foi registrado; a migração para NetherNet exige revisar TCP e UDP no túnel.' if confirmed else 'O servidor registrou um aviso de transporte. Confira a configuração e confirme uma entrada real no mundo antes de considerar o acesso validado.')
    return errors,diagnostic

def status():
    info=inspect(); raw=logs(); b=bridge_data(raw)
    if info['State']['Status']!='running': b['available']=False
    if b['snapshot']:
        started=dt.datetime.fromisoformat(info['State']['StartedAt'].replace('Z','+00:00')).timestamp()
        if b['snapshot'].get('at',0)/1000<started:b['available']=False
    statdata={}
    if info['State']['Running']:
        try: statdata=json.loads(run(['docker','stats','--no-stream','--format','{{json .}}',CONTAINER],timeout=12).strip())
        except (ValueError,subprocess.TimeoutExpired): pass
    errors=[re.sub(r'\x1b\[[0-9;]*m','',s)[:600] for s in raw.splitlines() if (re.search(r'\bERROR\b|\bException\b|\[CARV_ADMIN_ERROR\]',s) or '[Scripting]' in s and '[error]' in s.lower()) and '[CARV_ADMIN_V1]' not in s]
    old=STATE/'warnings.json'
    remembered=json.loads(old.read_text()) if old.exists() else {}
    if remembered.get('started')==info['State']['StartedAt']:errors=list(dict.fromkeys([x for x in remembered.get('errors',[]) if "errorMessage=(null)" not in x]+errors))[-12:]
    connection_verified=(b['available'] and bool(b['snapshot']['players'])) or (remembered.get('started')==info['State']['StartedAt'] and remembered.get('connectionVerified',False))
    atomic(old,dict(started=info['State']['StartedAt'],errors=errors,connectionVerified=connection_verified))
    props=properties(); free=shutil.disk_usage(ROOT)
    actionable,transport_note=transport_diagnostic(errors,props.get('transport'),connection_verified)
    return dict(at=time.time(),connectionVerified=bool(connection_verified),server=dict(state=info['State']['Status'],health=info['State'].get('Health',{}).get('Status','unknown'),started=info['State']['StartedAt'],restarts=info['RestartCount'],version=info['Config'].get('Env',[])),metrics={k:statdata.get(k) for k in ('CPUPerc','MemUsage','MemPerc','NetIO','BlockIO')},world=world().name,capacity=props.get('max-players'),transport=props.get('transport'),transportDiagnostic=transport_note,disk=dict(free=free.free,total=free.total),bridge=b,packs=packs(),backups=backup_list(),errors=actionable[-12:])

def stop():
    active=inspect()['State']['Running']
    if active: run(['docker','stop','-t','120',CONTAINER],timeout=140)
    return active

def start():
    run(['docker','start',CONTAINER],timeout=30)

def backup(reason='manual'):
    # Caller has stopped the process: LevelDB and pack references are consistent.
    name='panel-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    folder=ROOT/'backups'/name; folder.mkdir(parents=True,mode=0o700)
    paths=[DATA/n for n in ('worlds','behavior_packs','resource_packs','server.properties','permissions.json','allowlist.json') if (DATA/n).exists()]+[ROOT/'compose.yml']
    size=sum(f.stat().st_size for p in paths for f in ([p] if p.is_file() else p.rglob('*')) if f.is_file())
    if shutil.disk_usage(ROOT).free < size*1.2+100*1024*1024: raise ValueError('Espaço insuficiente para backup seguro')
    archive=folder/'snapshot.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for p in paths: tar.add(p,arcname=str(p.relative_to(ROOT)))
    with tarfile.open(archive) as tar:
        if not any(x.name.endswith('/level.dat') for x in tar): raise ValueError('Backup sem level.dat')
    with archive.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    meta=dict(created=dt.datetime.now(dt.timezone.utc).isoformat(),reason=reason,sha256=digest)
    atomic(folder/'metadata.json',meta)
    return dict(id=name,bytes=archive.stat().st_size,**meta)

def unpack(blob, stage, depth=0):
    if depth>2: raise ValueError('Arquivos compactados aninhados demais')
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if len(z.infolist())>12000: raise ValueError('Pacote com arquivos demais')
        for entry in z.infolist():
            name=entry.filename.replace('\\','/')
            rel=pathlib.PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts or ':' in name or stat.S_ISLNK(entry.external_attr>>16): raise ValueError('Caminho inseguro no pacote')
            if entry.is_dir(): continue
            budget[0]+=entry.file_size
            if entry.file_size>64*1024*1024 or budget[0]>160*1024*1024: raise ValueError('Pacote descompactado grande demais')
            if name.lower().endswith(('.mcpack','.mcaddon')):
                unpack(z.read(entry),stage/uuid.uuid4().hex,depth+1)
            else:
                dst=stage.joinpath(*rel.parts);dst.parent.mkdir(parents=True,exist_ok=True)
                if dst.exists(): raise ValueError('Arquivo duplicado no pacote')
                dst.write_bytes(z.read(entry))

def validate_stage(stage):
    found=[];ids=set()
    for f in stage.rglob('manifest.json'):
        try: m=json.loads(f.read_text(encoding='utf-8-sig'))
        except ValueError: raise ValueError('manifest.json inválido; use um pacote com JSON padrão')
        h=m.get('header',{}); uid=str(uuid.UUID(h['uuid'])); version=h['version']
        if uid in ids or not isinstance(version,list) or len(version)!=3 or not all(type(x)==int and x>=0 for x in version): raise ValueError('UUID/versão inválida ou repetida')
        ids.add(uid); types={x.get('type') for x in m.get('modules',[])}
        if types <= {'resources'} and types:kind='resource_packs'
        elif types <= {'data','script'} and types:kind='behavior_packs'
        else:raise ValueError('Tipo de pacote não suportado')
        if m.get('capabilities'): raise ValueError('Pacote pede capacidades adicionais; revisão manual necessária')
        for dep in m.get('dependencies',[]):
            if dep.get('module_name') and (dep['module_name'] not in ('@minecraft/server','@minecraft/server-ui') or 'beta' in str(dep.get('version',''))):raise ValueError('API experimental ou permissão adicional: revisão manual necessária')
        for mod in m.get('modules',[]):
            if mod.get('type')=='script':
                mod['language']='javascript'
                entry=mod.get('entry',''); target=(f.parent/entry).resolve()
                if not target.is_relative_to(f.parent.resolve()) or not target.is_file():raise ValueError('Entrada do script ausente ou insegura')
        if uid==BRIDGE:raise ValueError('Integração administrativa protegida')
        f.write_text(json.dumps(m,ensure_ascii=False,indent=2))
        engine=h.get('min_engine_version',[])
        if engine and (not isinstance(engine,list) or len(engine)!=3 or not all(type(v)==int and v>=0 for v in engine)):raise ValueError('Versão mínima do motor inválida')
        found.append(dict(uuid=uid,name=h.get('name',uid),version=version,kind=kind,dependencies=m.get('dependencies',[]),min_engine=engine,source=f.parent))
    if not found:raise ValueError('Nenhum pacote Bedrock válido encontrado')
    if len(found)>20:raise ValueError('Máximo de 20 packs por envio')
    # Parent and child manifests must never overlap.
    for a in found:
        if any(a is not b and b['source'].is_relative_to(a['source']) for b in found):raise ValueError('Manifests sobrepostos')
    return found

def validate_refs(candidate):
    active={p['uuid']:p for p in candidate if p['active']}
    for p in active.values():
        for dep in p['dependencies']:
            if 'uuid' in dep and (dep['uuid'] not in active or active[dep['uuid']]['version']!=dep['version']):raise ValueError('Dependência ausente/inativa: '+p['name']+' → '+dep['uuid'])

def validate_engine(candidate,version):
    if not any(p.get('min_engine') for p in candidate):return
    if not re.fullmatch(r'\d+\.\d+\.\d+(\.\d+)?',version):raise ValueError('Não foi possível confirmar a versão do servidor para validar estes packs')
    current=tuple(int(v) for v in version.split('.')[:3])
    for p in candidate:
        if p.get('min_engine') and tuple(p['min_engine'])>current:raise ValueError('O pacote '+p['name']+' exige Bedrock '+'.'.join(map(str,p['min_engine']))+' ou superior')

def audit(action,ok,detail):
    STATE.mkdir(exist_ok=True)
    with (STATE/'audit.jsonl').open('a') as f:f.write(json.dumps(dict(at=dt.datetime.now(dt.timezone.utc).isoformat(),user=os.environ.get('USER','unknown'),action=action,ok=ok,detail=detail),ensure_ascii=False)+'\n')

def mutate(req):
    action=req['action']; active=False; b=None
    if action=='start': start();return {'message':'Inicialização solicitada. Aguarde a próxima leitura.'}
    if action=='stop':stop();return {'message':'Servidor parado.'}
    if action=='restart':run(['docker','restart','-t','120',CONTAINER],timeout=150);return {'message':'Servidor reiniciado; confira os avisos e a entrada pelo jogo.'}
    if action=='backup':
        active=stop()
        try:b=backup()
        finally:
            if active:start()
        return dict(message='Backup consistente criado e verificado.',backup=b)
    if action=='toggle':
        uid=str(uuid.UUID(req['uuid'])); enable=req.get('enabled') is True
        if uid==BRIDGE:raise ValueError('Integração administrativa protegida')
        current=packs(); selected=next((p for p in current if p['uuid']==uid),None)
        if not selected:raise ValueError('Pacote não encontrado')
        selected['active']=enable;validate_refs(current)
        active=stop()
        try:
            b=backup('toggle-addon');kind=selected['kind'];r=[v for v in refs(kind) if v['pack_id']!=uid]
            if enable:r.append(dict(pack_id=uid,version=selected['version']))
            atomic(world()/('world_'+kind+'.json'),r)
        finally:
            if active:start()
        return dict(message='Pacote '+('ativado.' if enable else 'desativado.'),backup=b)
    if action=='install':
        blob=base64.b64decode(req.get('data',''),validate=True)
        if not blob or len(blob)>LIMIT:raise ValueError('Limite de upload: 16 MB')
        with tempfile.TemporaryDirectory(prefix='carv-addon-') as temp:
            stage=pathlib.Path(temp);budget[0]=0;unpack(blob,stage);found=validate_stage(stage)
            version=next((v.split('=',1)[1] for v in inspect()['Config'].get('Env',[]) if v.startswith('VERSION=')),'unknown')
            validate_engine(found,version)
            current=packs(); newids={p['uuid'] for p in found}
            # Updates are explicit installs; archives are preserved by the backup.
            candidate=[p for p in current if p['uuid'] not in newids]+[dict(p,active=True) for p in found]
            validate_refs(candidate)
            active=stop()
            try:
                b=backup('install-addon')
                for p in found:
                    dest=DATA/p['kind']/p['uuid']
                    if dest.exists():shutil.rmtree(dest)
                    shutil.copytree(p['source'],dest)
                for kind in ('behavior_packs','resource_packs'):
                    r=[v for v in refs(kind) if v['pack_id'] not in newids]
                    r.extend(dict(pack_id=p['uuid'],version=p['version']) for p in found if p['kind']==kind)
                    atomic(world()/('world_'+kind+'.json'),r)
            except Exception:
                if b:restore_files(b['id'])
                raise
            finally:
                if active:start()
        return dict(message='Pacotes instalados. Confira os logs e entre no jogo para validar a interface.',backup=b)
    if action=='restore':
        target=req.get('id',''); checked_backup(target)
        active=stop()
        try:
            b=backup('before-restore');restore_files(target)
        finally:
            if active:start()
        return dict(message='Mundo, packs e configurações restaurados. Cópia anterior preservada.',backup=b)
    raise ValueError('Ação não permitida')

def checked_backup(name):
    if not re.fullmatch(r'panel-\d{8}-\d{6}-[0-9a-f]{6}',name):raise ValueError('Backup inválido')
    folder=ROOT/'backups'/name;a=folder/'snapshot.tar.gz';m=json.loads((folder/'metadata.json').read_text())
    with a.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    if digest!=m['sha256']:raise ValueError('Checksum do backup não confere')
    return a

def restore_files(name):
    archive=checked_backup(name)
    with tempfile.TemporaryDirectory(dir=ROOT,prefix='restore-') as temp:
        temp=pathlib.Path(temp)
        with tarfile.open(archive) as tar:
            for m in tar:
                p=temp/m.name
                if not p.resolve().is_relative_to(temp.resolve()) or m.issym() or m.islnk() or not (m.isfile() or m.isdir()):raise ValueError('Backup contém caminho inválido')
            tar.extractall(temp,filter='data')
        for key in ('worlds','behavior_packs','resource_packs'):
            src=temp/'data'/key;dst=DATA/key
            if not src.exists():continue
            old=temp/('old-'+key)
            if dst.exists():os.replace(dst,old)
            os.replace(src,dst)
        for name in ('server.properties','permissions.json','allowlist.json'):
            src=temp/'data'/name
            if src.exists():shutil.copy2(src,DATA/name)
        # Keep current compose/runtime image: never silently downgrade or accept EULAs.

budget=[0]
def main():
    STATE.mkdir(parents=True,exist_ok=True)
    raw=sys.stdin.read(24*1024*1024);req=json.loads(raw);action=req.get('action')
    # Catalog reads never hold the world-maintenance lock during network calls.
    if isinstance(action,str) and action.startswith('cf_') and action!='cf_install':
        import curseforge
        try:
            value=curseforge.handle(req,sys.modules[__name__])
            if action=='cf_download':audit(action,True,'Projeto '+str(req.get('projectId'))+'; arquivos '+str(req.get('fileIds')))
        except Exception as e:
            if action=='cf_download':audit(action,False,str(e))
            raise
        print(json.dumps(dict(ok=True,result=value),ensure_ascii=False));return
    with (STATE/'operations.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if action=='status':
            value=status()
            # Only expose selected values; container environment can contain credentials.
            value['server']['version']=next((x.split('=',1)[1] for x in value['server']['version'] if x.startswith('VERSION=')),'desconhecida')
        elif action=='download':
            a=checked_backup(req.get('id',''))
            if a.stat().st_size>64*1024*1024:raise ValueError('Backup maior que 64 MB: baixe pelo terminal/Cockpit')
            value=dict(data=base64.b64encode(a.read_bytes()).decode(),filename=a.parent.name+'.tar.gz')
        elif isinstance(action,str) and action.startswith('cf_'):
            import curseforge
            try:
                value=curseforge.handle(req,sys.modules[__name__])
                if action in ('cf_install','cf_download'):audit(action,True,'Projeto '+str(req.get('projectId'))+'; arquivos '+str(req.get('fileIds')))
            except Exception as e:
                if action in ('cf_install','cf_download'):audit(action,False,str(e))
                raise
        else:
            try:value=mutate(req);audit(action,True,value.get('message',''))
            except Exception as e:audit(action,False,str(e));raise
        print(json.dumps(dict(ok=True,result=value),ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except BlockingIOError:print(json.dumps(dict(ok=False,error='Outra operação está em andamento. Aguarde.')))
    except Exception as e:print(json.dumps(dict(ok=False,error=str(e)[:2000]),ensure_ascii=False))
