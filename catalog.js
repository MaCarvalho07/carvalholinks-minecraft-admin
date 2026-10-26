'use strict';
const cf={configured:false,connected:false,gameId:null,page:0,filePage:0,query:'',category:'',version:'',sort:'popular',projects:[],files:[],project:null,busy:false};
const cfSeeds=[
 {name:'RyzenMap+',summary:'Mapa, radar e navegação para explorar o mundo.',icon:'⌖',art:'map',category:'Exploração',website:'https://www.curseforge.com/minecraft-bedrock/addons/ryzenmap'},
 {name:'WEI · Without Enough Items',summary:'Consulta de itens, receitas e informações de crafting.',icon:'▦',art:'craft',category:'Utilidades',website:'https://www.curseforge.com/minecraft-bedrock/addons/wei-without-enough-items'},
 {name:'Durability Viewer',summary:'Indicadores de durabilidade para acompanhar suas ferramentas.',icon:'⚒',art:'tools',category:'Interface',website:'https://www.curseforge.com/minecraft-bedrock/texture-packs/durability-viewer'},
 {name:'JEI Recipe Book Layout',summary:'Outra organização visual para o livro de receitas.',icon:'▤',art:'recipes',category:'Interface',website:'https://www.curseforge.com/minecraft-bedrock/texture-packs/jei-recipe-book-layout'}
];
const cfNumber=n=>new Intl.NumberFormat('pt-BR',{notation:'compact',maximumFractionDigits:1}).format(Number(n)||0);
function cfError(text){$('#cf-error').hidden=!text;$('#cf-error').textContent=text||'';}
function cfSetBusy(on){cf.busy=on;$('#cf-search-button').disabled=on;$('#cf-connect').disabled=on||!cf.configured;$('#cf-search-button').textContent=on?'Consultando…':'Buscar ↗';}
function cfCard(p,seed=false){
 const image=p.image?`<img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer">`:`<div class="cf-art ${esc(p.art||'craft')}"><span>${esc(p.icon||'▦')}</span><i></i><i></i><i></i></div>`;
 const author=seed?'Link oficial · projeto usado no lab':(p.authors||[]).map(a=>a.name).join(', ')||'Autor informado no projeto';
 return `<article class="cf-card"><div class="cf-cover">${image}<span class="cf-cover-tag">${seed?'LINK DO LAB':'CURSEFORGE'}</span></div><div class="cf-card-body"><div class="cf-category-label">${esc(seed?p.category:(p.categories||[]).slice(0,2).join(' / '))}</div><h3>${esc(p.name)}</h3><div class="cf-author">${esc(author)}</div><p>${esc(p.summary)}</p>${seed?'<div class="cf-meta">API pendente · download integrado indisponível</div>':`<div class="cf-meta"><span>↓ ${esc(cfNumber(p.downloads))}</span><span>${p.distribution===false?'Download direto restrito':'Permissão conferida no download'}</span></div>`}<div class="cf-card-actions">${seed?'<button disabled>Versões · aguardando API</button>':`<button class="primary" data-cf-project="${esc(p.id)}">Versões e download</button>`}${p.website?`<a href="${esc(p.website)}" target="_blank" rel="noopener noreferrer">Ver no CurseForge ↗</a>`:''}</div></div></article>`;
}
function cfShowSeeds(){
 const q=$('#cf-query').value.trim().toLocaleLowerCase('pt-BR');const items=cfSeeds.filter(p=>(p.name+' '+p.summary).toLocaleLowerCase('pt-BR').includes(q));
 $('#cf-cards').innerHTML=items.map(p=>cfCard(p,true)).join('')||'<div class="panel empty">Nenhum link do lab corresponde à busca. O catálogo completo depende da chave.</div>';
 $('#cf-result-label').textContent='Links de projetos do lab';$('#cf-result-note').textContent='Esta seleção é local; não são resultados da API.';$('#cf-pagination').hidden=true;
}
async function cfStatus(){
 try{const s=await rpc({action:'cf_status'});cf.configured=s.configured;$('#cf-status').textContent=s.configured?'Chave configurada · catálogo ainda não testado':'Aguardando chave do CurseForge';$('#cf-description').textContent=s.message;$('#cf-connect').disabled=!s.configured;$('#cf-dot').classList.toggle('cf-pending',!s.configured);$('#cf-category').disabled=!s.configured;$('#cf-version').disabled=!s.configured;$('#cf-sort').disabled=!s.configured;}
 catch(e){$('#cf-status').textContent='Integração precisa de atenção';$('#cf-description').textContent=e.message;$('#cf-connect').disabled=true;}
 cfShowSeeds();
}
async function cfSearch(page=0){
 if(cf.busy||pending)return;
 if(!cf.configured){cfShowSeeds();return;}
 cfError('');cfSetBusy(true);
 try{
  const result=await rpc({action:'cf_search',gameId:cf.gameId,page,query:cf.query,category:cf.category,version:cf.version,sort:cf.sort});
  cf.gameId=result.gameId;cf.page=page;cf.connected=true;cf.projects=result.projects;
  $('#cf-status').textContent='Catálogo oficial conectado';$('#cf-description').textContent='Minecraft Bedrock · consultas sob demanda, sem atualização automática do catálogo.';$('#cf-dot').classList.remove('cf-pending');
  $('#cf-cards').innerHTML=result.projects.map(p=>cfCard(p)).join('')||'<div class="panel empty">Nenhum projeto encontrado. Tente outra busca ou remova o filtro de versão.</div>';
  $('#cf-result-label').textContent=result.projects.length+' projetos nesta página';$('#cf-result-note').textContent='Dados do CurseForge · autoria e links preservados';
  const p=result.pagination;$('#cf-pagination').hidden=!p.totalCount;$('#cf-page').textContent='Página '+(page+1);$('#cf-prev').disabled=page===0;$('#cf-next').disabled=(p.index||0)+(p.resultCount||0)>=(p.totalCount||0);
 }catch(e){cfError(e.message);}finally{cfSetBusy(false);}
}
async function cfConnect(){
 if(cf.busy||pending||!cf.configured)return;cfSetBusy(true);cfError('');
 try{const result=await rpc({action:'cf_categories',gameId:cf.gameId});cf.gameId=result.gameId;$('#cf-category').innerHTML='<option value="">Todas as categorias</option>'+result.categories.sort((a,b)=>a.name.localeCompare(b.name)).map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');}
 catch(e){cfError(e.message);cfSetBusy(false);return;}
 cfSetBusy(false);await cfSearch(0);
}
async function cfFiles(projectId,page=0){
 if(cf.busy||pending)return;cfSetBusy(true);const d=$('#cf-dialog');if(!d.open)d.showModal();$('#cf-files-status').textContent='Consultando arquivos oficiais…';$('#cf-install').disabled=true;$('#cf-files-prev').disabled=true;$('#cf-files-next').disabled=true;cf.files=[];$('#cf-files').innerHTML='';
 try{const r=await rpc({action:'cf_files',gameId:cf.gameId,projectId,page});cf.gameId=r.gameId;cf.project=r.project;cf.files=r.files;cf.filePage=page;$('#cf-project-name').textContent=r.project.name;$('#cf-project-summary').textContent=r.project.summary;
  $('#cf-project-info').innerHTML=`<span>Por ${esc(r.project.authors.map(a=>a.name).join(', '))}</span>${r.project.website?`<a href="${esc(r.project.website)}" target="_blank" rel="noopener noreferrer">Página oficial ↗</a>`:''}`;
  $('#cf-files').innerHTML=r.files.map(f=>`<article class="cf-file"><label class="cf-file-choice"><input type="checkbox" data-cf-file="${esc(f.id)}" ${f.eligible?'':'disabled'}><span><strong>${esc(f.name)}</strong><small>${esc(f.filename)} · ${esc(bytes(f.size))} · ${esc(({1:'Release',2:'Beta',3:'Alpha'})[f.release]||'Sem classificação')}</small><small>Versões declaradas: ${esc(f.versions.join(', ')||'não informadas')}</small></span></label>${f.reason?`<p class="hint warn">${esc(f.reason)}</p>`:''}${f.dependencies.filter(x=>x.type===3).length?`<div class="cf-deps">Dependências exigidas: ${f.dependencies.filter(x=>x.type===3).map(x=>`<button data-cf-project="${esc(x.projectId)}">Projeto #${esc(x.projectId)} ↗</button>`).join('')}</div>`:''}<button data-cf-download="${esc(f.id)}" ${f.eligible?'':'disabled'}>↓ Baixar arquivo</button></article>`).join('')||'<div class="empty">Nenhum arquivo disponível nesta página.</div>';
  $('#cf-files-status').textContent=r.project.distribution===false?'O autor não permite downloads por ferramentas externas. Use a página oficial.':'Escolha até quatro arquivos, totalizando no máximo 16 MB. Nenhuma instalação foi iniciada.';
  $('#cf-files-page').textContent='Página '+(page+1);$('#cf-files-prev').disabled=page===0;const p=r.pagination;$('#cf-files-next').disabled=(p.index||0)+(p.resultCount||0)>=(p.totalCount||0);cfSelection();
 }catch(e){$('#cf-files-status').textContent=e.message;$('#cf-files').innerHTML='';cf.files=[];cf.project=null;$('#cf-files-prev').disabled=true;$('#cf-files-next').disabled=true;}
 finally{cfSetBusy(false);}
}
function cfSelected(){return [...document.querySelectorAll('[data-cf-file]:checked')].map(x=>Number(x.dataset.cfFile));}
function cfSelection(){const ids=cfSelected(),size=cf.files.filter(f=>ids.includes(f.id)).reduce((sum,f)=>sum+f.size,0);$('#cf-selected').textContent=ids.length+' arquivo(s) · '+bytes(size);$('#cf-install').disabled=ids.length<1||ids.length>4||size>16*1048576;}
function cfSaveDownload(result){const raw=atob(result.data),arr=Uint8Array.from(raw,c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([arr],{type:'application/octet-stream'}));const a=document.createElement('a');a.href=url;a.download=result.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
async function cfDownload(id){
 if(pending||cf.busy||!cf.project||!cf.files.some(f=>f.id===id&&f.eligible))return;
 cf.busy=true;$('#cf-files-status').textContent='Baixando do CDN oficial e verificando checksum…';
 try{const r=await rpc({action:'cf_download',gameId:cf.gameId,projectId:cf.project.id,fileIds:[id]});cfSaveDownload(r);$('#cf-files-status').textContent=r.message;}catch(e){$('#cf-files-status').textContent=e.message;}finally{cf.busy=false;}
}
async function cfInstall(){
 if(pending||cf.busy||!cf.project)return;const ids=cfSelected();if(!ids.length||ids.length>4)return;
 const p=cf.project;$('#cf-dialog').close();
 await operate({action:'cf_install',gameId:cf.gameId,projectId:p.id,fileIds:ids},'Instalar '+p.name+' no mundo principal?','Os arquivos selecionados serão baixados pelo servidor e verificados por checksum. O painel verificará os packs e suas dependências, criará um backup e reiniciará o servidor. Os jogadores serão desconectados. Instale apenas projetos em que você confia.');
}
$('#cf-search').addEventListener('submit',e=>{e.preventDefault();cf.query=$('#cf-query').value.trim();cf.category=$('#cf-category').value;cf.version=$('#cf-version').value.trim();cf.sort=$('#cf-sort').value;cfSearch(0);});
$('#cf-connect').addEventListener('click',cfConnect);$('#cf-help').addEventListener('click',()=>{$('#cf-setup').hidden=!$('#cf-setup').hidden;});$('#cf-prev').addEventListener('click',()=>cfSearch(Math.max(0,cf.page-1)));$('#cf-next').addEventListener('click',()=>cfSearch(cf.page+1));$('#cf-close').addEventListener('click',()=>$('#cf-dialog').close());$('#cf-install').addEventListener('click',cfInstall);$('#cf-files-prev').addEventListener('click',()=>cfFiles(cf.project.id,Math.max(0,cf.filePage-1)));$('#cf-files-next').addEventListener('click',()=>cfFiles(cf.project.id,cf.filePage+1));
document.addEventListener('click',e=>{const p=e.target.closest('[data-cf-project]'),d=e.target.closest('[data-cf-download]');if(p)cfFiles(Number(p.dataset.cfProject));if(d)cfDownload(Number(d.dataset.cfDownload));});document.addEventListener('change',e=>{if(e.target.matches('[data-cf-file]'))cfSelection();});
cfStatus();
