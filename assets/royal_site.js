(() => {
  'use strict';
  document.documentElement.classList.add('js-ready');
  const $ = (selector, root=document) => root.querySelector(selector);
  const $$ = (selector, root=document) => Array.from(root.querySelectorAll(selector));
  const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const safeLink = url => {try {const u=new URL(String(url));return u.protocol==='https:' ? u.href : null;} catch{return null;}};
  const DEFAULT_AVATAR='/assets/royal_logo.png';
  const OFC_ID='1554367619463913582', INFLUENCER_ID='1565443626388164790';
  const RESERVE_BENEFITS = [
    ['Sorteios exclusivos','Premiações e oportunidades reservadas aos integrantes oficiais.','🎁'],
    ['Indicações familiares','Recomende novos candidatos à avaliação dos fundadores.','📜'],
    ['Conselho Royal','Apresente propostas e participe das votações da comunidade.','⚖️'],
    ['Perfil Royal','Seu nome, título e apresentação personalizada no portal.','👑'],
    ['Call privada','Um espaço de voz exclusivo no servidor da Família.','🎙️'],
    ['Permissões no E.B','Acesso a permissões especiais pelo cargo da Família no servidor do E.B.','🛡️'],
    ['Eventos e experiências','Atividades especiais reservadas aos integrantes oficiais.','🎭']
  ].map(([nome,descricao,emoji])=>({nome,descricao,emoji}));
  const cache = {data:null, shown:8, session:null};
  function show(el,visible=true){if(el) el.classList.toggle('hidden', !visible);}
  function observe(){
    const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(reduced || !('IntersectionObserver' in window)){$$('.reveal').forEach(e=>e.classList.add('is-visible'));return;}
    if(!window.royalObserver){window.royalObserver=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');window.royalObserver.unobserve(entry.target);}}),{threshold:.08,rootMargin:'0px 0px 40px 0px'});}
    $$('.reveal:not(.is-visible)').forEach(e=>window.royalObserver.observe(e));
  }
  function memberName(m){return m?.perfil?.display_name||m?.nome||'Integrante';}
  function memberTitle(m){return m?.perfil?.title||`@${m?.usuario||'royal'}`;}
  function memberButton(m){return `<button type="button" class="person-card reveal" data-member="${html(m.id)}" aria-label="Abrir perfil de ${html(memberName(m))}"><img src="${html(m.avatar||DEFAULT_AVATAR)}" alt="" loading="lazy"><div class="person-info"><strong>${html(memberName(m))}</strong><small>${html(memberTitle(m))}</small><span class="person-action">CONHECER PERFIL ↗</span></div></button>`;}
  function empty(message){return `<div class="empty-state">✦ ${html(message)}</div>`;}
  function renderMembers(){
    const list=cache.data?.membros||[];const q=($('#member-search')?.value||'').trim().toLowerCase();
    const selected=list.filter(m=>[memberName(m),m.usuario,m?.perfil?.title].join(' ').toLocaleLowerCase('pt-BR').includes(q));
    $('#members-grid').innerHTML=selected.length?selected.slice(0,cache.shown).map(memberButton).join(''):empty(cache.data?.online?'Nenhum membro encontrado para essa busca.':'A lista estará disponível quando o Discord terminar de sincronizar.');
    show($('#load-more'),selected.length>cache.shown);
    $('#members-number').textContent=cache.data?.online?String(list.length):'—';
    $('#total-members').textContent=cache.data?.online?String(list.length):'—';
    $('#directory-status').textContent=cache.data?.online?'Diretório oficial sincronizado':'Discord temporariamente indisponível';
    observe();
  }
  function teamCard(g){return `<article class="team-role reveal"><span class="team-symbol">${html(g.simbolo||'✦')}</span><div><h3>${html(g.nome)}</h3><p>${html(g.descricao||'')}</p><div class="team-mini-members">${(g.pessoas||[]).length?g.pessoas.map(m=>`<button type="button" data-member="${html(m.id)}"><img src="${html(m.avatar||DEFAULT_AVATAR)}" alt=""><span>${html(memberName(m))}</span></button>`).join(''):'<span class="team-placeholder">Nenhum integrante listado agora</span>'}</div></div></article>`;}
  function insignia(i){return `<div class="insignia-item"><span class="insignia-emoji">${html(i.emoji||'✦')}</span><div><strong>${html(i.nome)}</strong><span>${html(i.descricao||'Distinção pessoal da Família Royal.')}</span></div></div>`;}
  function renderAll(){
    const d=cache.data||{};
    renderMembers();
    $('#staff-grid').innerHTML=(d.staff||[]).map(teamCard).join('')||empty('Equipe em atualização.');
    $('#support-grid').innerHTML=(d.apoio||[]).map(teamCard).join('')||empty('Funções de apoio em atualização.');
    const staffIds=new Set((d.staff||[]).flatMap(g=>(g.pessoas||[]).map(m=>m.id)));
    $('#total-staff').textContent=d.online?String(staffIds.size):'—';
    const records=d.insignias||[];const featured=records.filter(i=>i.destaque);
    $('#insignias-damas').innerHTML=featured.length?featured.map(insignia).join(''):empty('Nenhuma distinção nesta galeria.');
    $('#insignias-cavalheiros').innerHTML=records.filter(i=>!i.destaque).map(insignia).join('')||empty('Nenhuma distinção nesta galeria.');
    const benefits=d.beneficios?.length?d.beneficios:RESERVE_BENEFITS;
    $('#benefits-grid').innerHTML=benefits.map(b=>`<article class="benefit-card reveal"><span class="benefit-symbol">${html(b.emoji)}</span><h3>${html(b.nome)}</h3><p>${html(b.descricao)}</p></article>`).join('');
    $('#influencers-grid').innerHTML=(d.influencers||[]).length?d.influencers.map(m=>`<button type="button" class="creator-card" data-member="${html(m.id)}"><img src="${html(m.avatar||DEFAULT_AVATAR)}" alt=""><span><strong>${html(memberName(m))}</strong><small>${html(memberTitle(m))}</small></span></button>`).join(''):empty('Criadores aparecerão aqui conforme seus cargos no Discord.');
    observe();
  }
  async function loadCommunity(){
    try{const res=await fetch('/api/royal',{cache:'no-store'});if(!res.ok)throw new Error(`HTTP ${res.status}`);cache.data=await res.json();}
    catch(error){console.warn('Royal Community:',error);cache.data={online:false,membros:[],staff:[],apoio:[],influencers:[],insignias:[],beneficios:RESERVE_BENEFITS};}
    renderAll();
  }
  async function openMember(id){
    const modal=$('#member-modal');show(modal,true);document.body.style.overflow='hidden';
    $('#modal-content').innerHTML='<p>Consultando integrante...</p>';
    $('#modal-content').focus?.();
    try {
      const r=await fetch(`/api/royal/membro/${encodeURIComponent(id)}`,{cache:'no-store'});if(!r.ok)throw new Error('Membro indisponível');
      const m=await r.json(),p=m.perfil||{};
      const link=safeLink(p.link),insignias=m.insignias||[];
      $('#modal-content').innerHTML=`<img class="modal-avatar" src="${html(m.avatar||DEFAULT_AVATAR)}" alt=""><h3>${html(p.display_name||m.nome)}</h3><p>@${html(m.usuario)}</p><div class="modal-chips"><span>${m.oficial?'👑 Membro oficial da Família Royal':'✦ Integrante da comunidade'}</span>${m.influencer?'<span>🎥 Influenciador Royal</span>':''}</div>${p.title?`<p><strong>${html(p.title)}</strong></p>`:''}${p.motto?`<p><em>“${html(p.motto)}”</em></p>`:''}${p.bio?`<p>${html(p.bio)}</p>`:''}<h4>Insígnias reconhecidas</h4><div class="modal-chips">${insignias.length?insignias.map(i=>`<span>${html(i.emoji)} ${html(i.nome)}</span>`).join(''):'<span>Sem insígnias registradas</span>'}</div>${link?`<p><a class="modal-link" href="${html(link)}" target="_blank" rel="noopener noreferrer">Visitar link público ↗</a></p>`:''}${p.signature?`<p>${html(p.signature)}</p>`:''}`;
    } catch {$('#modal-content').innerHTML='<h3>Perfil indisponível</h3><p>Não foi possível consultar esse integrante agora. Tente novamente depois.</p>';}
    $('.modal-close')?.focus();
  }
  function closeModal(){show($('#member-modal'),false);document.body.style.overflow='';}
  function preview(){
    const form=$('#profile-form'),data=form?Object.fromEntries(new FormData(form)):{};const mem=cache.session?.member||{};
    $('#preview-name').textContent=data.display_name||mem.nome||'Seu nome Royal';
    $('#preview-title').textContent=data.title||'Seu título especial';
    $('#preview-motto').textContent=data.motto?`“${data.motto}”`:'“Sua história merece ser contada.”';
    $('#preview-bio').textContent=data.bio||'Uma breve descrição sobre você aparecerá aqui.';
    $('#preview-avatar').src=mem.avatar||DEFAULT_AVATAR;
    const badges=[];
    if((mem.roles||[]).includes(OFC_ID))badges.push('👑 Membro oficial');
    else badges.push('✧ Comunidade Royal');
    if((mem.roles||[]).includes(INFLUENCER_ID))badges.push('🎥 Influenciador oficial');
    $('#preview-verified').textContent=badges.join(' · ');
    $('#preview-chips').innerHTML=[data.badge_a,data.badge_b].filter(Boolean).map(s=>`<span>${html(s)}</span>`).join('');
    $('#profile-preview').dataset.theme=data.color||'gold';
    const link=safeLink(data.link);show($('#preview-link'),Boolean(link));if(link)$('#preview-link').href=link;
  }
  async function authStatus(){
    try{
      const r=await fetch('/api/royal/oauth-status',{cache:'no-store'});if(!r.ok)throw Error();
      const status=await r.json();const el=$('#login-status');
      if(!status.ready){el.textContent='O login precisa ser configurado no Railway: '+status.missing.join(', ')+'. Acesse as instruções do pacote para ativá-lo.';}
      else el.textContent='Autenticação pronta para conectar sua conta do Discord.';
    } catch{$('#login-status').textContent='É necessário configurar o OAuth2 do Discord no Railway para ativar o editor.';}
  }
  async function loadMe(){
    try{
      const r=await fetch('/api/royal/me',{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw Error('Sessão indisponível');
      const response=await r.json();cache.session=response;
      show($('#profile-login'),!response.authenticated);show($('#profile-form'),!!response.authenticated);
      if(response.authenticated){
        const form=$('#profile-form');
        for(const el of Array.from(form.elements))if(el.name){el.value=response.profile?.[el.name]??(el.name==='color'?'gold':'');}
      } else authStatus();
      preview();
    }catch(err){console.warn('Royal Auth:',err);show($('#profile-login'),true);show($('#profile-form'),false);$('#login-status').textContent='Serviço de perfis temporariamente indisponível.';preview();}
  }
  async function saveProfile(e){
    e.preventDefault();const button=$('#profile-form button[type="submit"]'),feedback=$('#profile-feedback');
    const data=Object.fromEntries(new FormData(e.currentTarget));button.disabled=true;feedback.textContent='Salvando alterações...';
    try{
      const res=await fetch('/api/royal/me',{method:'PUT',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(data)});
      const result=await res.json();if(!res.ok)throw new Error(result.detail||'Não foi possível salvar');
      feedback.textContent='✓ Seu perfil Royal foi salvo.';await loadMe();await loadCommunity();
    }catch(error){feedback.textContent=`⚠ ${error.message}`;}finally{button.disabled=false;}
  }
  function setupMotion(){
    observe();if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    const halo=$('#cursor-halo');if(halo)window.addEventListener('pointermove',e=>{halo.style.left=e.clientX+'px';halo.style.top=e.clientY+'px';},{passive:true});
    // 3D suave apenas em dispositivos com hover real.
    if(matchMedia('(hover: hover) and (pointer: fine)').matches){
      const emblem=$('#hero-crest'), area=$('.hero-emblem-wrap');
      area?.addEventListener('pointermove',e=>{const r=area.getBoundingClientRect();const x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;emblem.style.transform=`perspective(800px) rotateY(${x*14}deg) rotateX(${-y*12}deg) translateZ(12px)`;});
      area?.addEventListener('pointerleave',()=>{emblem.style.transform='';});
      $$('[data-tilt]').forEach(card=>{card.addEventListener('pointermove',e=>{const r=card.getBoundingClientRect();const x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;card.style.transform=`perspective(950px) rotateY(${x*4}deg) rotateX(${-y*4}deg) translateY(-3px)`;});card.addEventListener('pointerleave',()=>{card.style.transform='';});});
    }
  }
  function bind(){
    $('#year').textContent=String(new Date().getFullYear());
    $('#menu-toggle').addEventListener('click',()=>{const nav=$('#main-nav'),expanded=$('#menu-toggle').getAttribute('aria-expanded')==='true';nav.classList.toggle('open',!expanded);$('#menu-toggle').setAttribute('aria-expanded',String(!expanded));});
    $$('#main-nav a').forEach(a=>a.addEventListener('click',()=>{$('#main-nav').classList.remove('open');$('#menu-toggle').setAttribute('aria-expanded','false');}));
    addEventListener('scroll',()=>$('#site-header').classList.toggle('is-scrolled',scrollY>12),{passive:true});
    $('#member-search').addEventListener('input',()=>{cache.shown=8;renderMembers();});
    $('#load-more').addEventListener('click',()=>{cache.shown+=8;renderMembers();});
    document.addEventListener('click',event=>{const btn=event.target.closest('[data-member]');if(btn)openMember(btn.dataset.member);if(event.target.closest('[data-close-modal]'))closeModal();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
    $('#profile-form').addEventListener('input',preview);
    $('#profile-form').addEventListener('change',preview);
    $('#profile-form').addEventListener('submit',saveProfile);
    $('#profile-logout').addEventListener('click',async()=>{await fetch('/auth/logout',{method:'POST',credentials:'same-origin'});await loadMe();});
    setupMotion();loadCommunity();loadMe();setInterval(loadCommunity,120000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
})();
