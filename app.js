'use strict';
const $=s=>document.querySelector(s), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let pending=false,last=null,selected=null;
const nice=x=>String(x??'').replace(/§./g,'').replace(/^minecraft:/,'').replaceAll('_',' ');
const bytes=n=>n>=1073741824?(n/1073741824).toFixed(1)+' GB':(n/1048576).toFixed(1)+' MB';
const when=x=>new Date(x).toLocaleString('pt-BR');
const reason=x=>({'manual':'Manual','install-addon':'Instalação de addon','toggle-addon':'Alteração de addon','before-restore':'Antes da restauração','before-admin-bridge':'Antes da integração'}[x]||x);
async function rpc(req){
 if(!window.cockpit)throw Error('Abra este painel pelo Cockpit e faça login.');
 const user=await cockpit.user();
 const proc=cockpit.spawn(['/usr/bin/python3',user.home+'/minecraft-bedrock/admin/admin.py'],{err:'message'});
 proc.input(JSON.stringify(req));proc.input(null);
 const text=await proc;let res;
 try{res=JSON.parse(text);}catch{throw Error('Resposta inválida do servidor. Confira a sessão e as permissões do Docker.');}
 if(!res.ok)throw Error(res.error||'Operação não concluída.');return res.result;
}
function notice(text,error=false){$('#notice').hidden=false;$('#notice').textContent=text;$('#notice').classList.toggle('error',error);}
function busy(on){pending=on;$('#busy').hidden=!on;document.querySelectorAll('button').forEach(b=>b.disabled=on);$('#install').disabled=on||!selected;}
function confirmAction(title,body){return new Promise(resolve=>{const d=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-body').textContent=body;d.returnValue='cancel';d.onclose=()=>resolve(d.returnValue==='yes');d.showModal();});}
function metric(label,value,note){return `<div class="metric"><label>${esc(label)}</label><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`;}
function render(s){
 const expanded=new Set([...document.querySelectorAll('.player details[open]')].map(d=>d.closest('.player').dataset.player));
 last=s;const b=s.bridge, snap=b.snapshot;const online=b.available?snap.players.length:'—';
 $('#fresh').textContent='Última leitura: '+when(s.at*1000)+' · atualização automática a cada 15 s';
 $('#metrics').innerHTML=metric('SERVIDOR',s.server.state==='running'?'Em execução':s.server.state==='exited'?'Parado':s.server.state,'Saúde: '+s.server.health)+metric('JOGADORES',online+(s.capacity?' / '+s.capacity:''),b.available?'Leitura confirmada pelo mundo':'Aguardando integração do mundo')+metric('CPU',s.metrics.CPUPerc||'—','Uso do container Minecraft')+metric('MEMÓRIA',s.metrics.MemUsage||'—','Disco livre: '+bytes(s.disk.free));
 $('#world').textContent=s.world;$('#runtime').textContent='Bedrock '+s.server.version+' · '+(s.transport||'transporte padrão')+' · '+s.server.restarts+' reinícios inesperados';
 $('#bridge-state').textContent=b.available?'Integração ativa':snap?'Leitura desatualizada':'Sem leitura do mundo';
 $('#player-list').classList.toggle('stale',!b.available);
 if(!b.available){$('#player-list').innerHTML='<div class="panel empty">'+(s.server.state!=='running'?'Servidor parado. Inicie para consultar os jogadores.':snap?'A última leitura expirou. Nenhum jogador será apresentado como online até a integração responder.':'Aguardando o primeiro sinal da integração. Os jogadores, vida e inventários aparecerão aqui quando o mundo enviar dados.')+'</div>';}
 else if(!snap.players.length){$('#player-list').innerHTML='<div class="panel empty">Ninguém conectado neste momento. A integração está respondendo.</div>';}
 else {$('#player-list').innerHTML=snap.players.map(player).join('');document.querySelectorAll('.player').forEach(p=>{if(expanded.has(p.dataset.player))p.querySelector('details').open=true;});}
 $('#pack-count').textContent=s.packs.filter(p=>p.active).length+' ativos / '+s.packs.length+' instalados';
 $('#pack-list').innerHTML=s.packs.map(p=>`<article class="pack"><div><h3>${esc(nice(p.name))}</h3><p>${p.kind==='behavior_packs'?'Comportamento':'Recursos'} · v${esc(p.version.join('.'))} · ${p.active?'Ativo':'Inativo'}</p></div>${p.protected?'<span class="tag">Integração</span>':`<button data-toggle="${esc(p.uuid)}" data-enabled="${!p.active}">${p.active?'Desativar':'Ativar'}</button>`}</article>`).join('')||'<div class="empty">Nenhum pack encontrado.</div>';
 $('#backup-list').innerHTML=s.backups.map(b=>`<div class="backup"><div><h3>${esc(when(b.created))} · ${esc(bytes(b.bytes))}</h3><p>${esc(reason(b.reason))} · ${esc(b.id)}</p><p>SHA-256: ${esc(b.sha256)}</p></div><div class="actions"><button data-download="${esc(b.id)}">↓ Baixar</button><button data-restore="${esc(b.id)}">Restaurar</button></div></div>`).join('')||'<div class="empty">Crie o primeiro backup pelo painel. Cópias anteriores do servidor continuam preservadas.</div>';
 const warnings=[];
 if(s.errors.length)warnings.push(...s.errors.map(e=>`<div class="diag warn">${esc(e)}</div>`));
 if(s.transport==='raknet'&&s.errors.some(x=>/TRANSPORT|NetherNet/i.test(x)))warnings.unshift(s.connectionVerified?'<div class="diag warn"><strong>Aviso de transporte registrado.</strong> Apesar do aviso de NetherNet, a integração confirmou um jogador conectado nesta execução. O log foi preservado para acompanhamento.</div>':'<div class="diag warn"><strong>Acesso de jogadores ainda não confirmado.</strong> O servidor registra incompatibilidade de transporte. Um ping positivo não confirma que seja possível entrar no mundo.</div>');
 if(!b.available)warnings.push('<div class="diag warn">Vida, fome e inventários ainda não validados com um jogador conectado. Nenhum dado de exemplo é exibido.</div>');
 warnings.push(`<div class="diag">Última inicialização: ${esc(when(s.server.started))}. Transporte: ${esc(s.transport)}.</div>`);
 if(b.available)warnings.push('<div class="diag ok">Integração de leitura respondendo. Inventários são somente consulta nesta versão.</div>');
 $('#diagnostic-list').innerHTML=warnings.join('');
 document.querySelector('[data-action="start"]').disabled=s.server.state==='running';document.querySelector('[data-action="stop"]').disabled=s.server.state!=='running';
}
function player(p){
 const slots=Array.from({length:36},(_,i)=>{const x=(p.inventory||[]).find(v=>v.slot===i);return `<div class="slot ${x?'':'empty-slot'}" title="${esc(x?JSON.stringify(x):'Slot vazio')}"><span class="slotnum">${i+1}</span>${x?`${esc(nice(x.name||x.type))}<b>×${esc(x.amount)}</b>${x.durability?`<span>${esc(x.durability.remaining)} / ${esc(x.durability.max)}</span>`:''}`:'·'}</div>`;}).join('');
 const pos=p.position?`${p.position.x}, ${p.position.y}, ${p.position.z}`:'indisponível';
 return `<article class="player" data-player="${esc(p.name)}"><div class="player-head"><div class="player-name">♙ ${esc(p.name)}</div><span class="tag">${esc(nice(p.dimension))}</span></div><div class="vitals"><span>♥ Vida: ${esc(p.health?.current??'—')} / ${esc(p.health?.max??'—')}</span><span>♨ Fome: ${esc(p.hunger?.current??'indisponível')} / ${esc(p.hunger?.max??'—')}</span><span>⌖ ${esc(pos)}</span><span>${esc(nice(p.gamemode))}</span></div>${p.error?`<p class="hint warn">Leitura parcial: ${esc(p.error)}</p>`:''}<details><summary>Ver inventário · ${(p.inventory||[]).length} slots ocupados</summary><div class="inventory">${slots}</div><p class="hint">Equipamento: ${esc((p.equipment||[]).map(x=>x.slot+': '+nice(x.type)).join(' · ')||'nenhum')}</p><p class="hint">Passe o cursor sobre um item para consultar durabilidade e encantamentos disponíveis.</p></details></article>`;
}
async function refresh(){if(pending)return;try{render(await rpc({action:'status'}));}catch(e){$('#fresh').textContent='Falha na leitura — '+e.message;}}
async function operate(req,title,body){
 if(pending||!await confirmAction(title,body))return;
 busy(true);try{const result=await rpc(req);notice(result.message||'Operação concluída.');}catch(e){notice(e.message,true);}finally{busy(false);await refresh();}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.action){const a=b.dataset.action;const texts={start:['Iniciar servidor?','O mundo principal será iniciado.'],stop:['Parar servidor?','Os jogadores serão desconectados. O mundo será salvo antes do encerramento.'],restart:['Reiniciar servidor?','Os jogadores serão desconectados durante o reinício.'],backup:['Criar backup?','O servidor será parado para copiar o mundo e os packs com consistência. Se estava em execução, será iniciado novamente.']};await operate({action:a},...texts[a]);}
 if(b.dataset.toggle)await operate({action:'toggle',uuid:b.dataset.toggle,enabled:b.dataset.enabled==='true'},'Alterar addon?', 'O painel verificará as dependências, criará um backup e aplicará a alteração. Os jogadores serão desconectados se o servidor estiver em execução. Alterar addons pode afetar blocos e itens do mundo.');
 if(b.dataset.restore)await operate({action:'restore',id:b.dataset.restore},'Restaurar este backup?','O mundo e os packs voltarão à data desta cópia. Antes, o painel fará um backup do estado atual. Os jogadores serão desconectados. A versão do servidor será mantida.');
 if(b.dataset.download){busy(true);try{const r=await rpc({action:'download',id:b.dataset.download});const raw=atob(r.data),arr=Uint8Array.from(raw,c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([arr],{type:'application/gzip'}));const a=document.createElement('a');a.href=url;a.download=r.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){notice(e.message,true);}finally{busy(false);}}
});
$('#refresh').addEventListener('click',refresh);
$('#addon-file').addEventListener('change',e=>{selected=e.target.files[0]||null;$('#file-name').textContent=selected?selected.name+' · '+bytes(selected.size):'Nenhum arquivo escolhido';$('#install').disabled=!selected;});
$('#install').addEventListener('click',async()=>{
 if(!selected||pending)return;
 if(!/\.(mcaddon|mcpack)$/i.test(selected.name)||selected.size>16*1048576){notice('Escolha .mcaddon ou .mcpack de até 16 MB.',true);return;}
 if(!await confirmAction('Instalar '+selected.name+'?','Confirme que você confia na origem deste pacote. Scripts de addons podem alterar o mundo. O painel verificará a estrutura e as dependências, fará backup e instalará no mundo principal. Os jogadores serão desconectados.'))return;
 busy(true);try{const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=reject;r.readAsDataURL(selected);});const r=await rpc({action:'install',data});notice(r.message);selected=null;$('#addon-file').value='';$('#file-name').textContent='Nenhum arquivo escolhido';}catch(e){notice(e.message||'Falha no envio',true);}finally{busy(false);await refresh();}
});
refresh();setInterval(refresh,15000);
