/* Portal Sant's — dados públicos vindos do FastAPI existente.
   Renderização por textContent e createElement: textos dos posts nunca entram como HTML. */
(() => {
  'use strict';
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => Array.from((typeof root==='string' ? document.querySelector(root) : root).querySelectorAll(s));
  const LABELS = {noticia:'Notícia',novidade:'Comunidade',tecnologia:'Tecnologia',projeto:'Projeto',guia:'Guia',jogos:'Jogos',evento:'Evento',sorteio:'Sorteio',embreve:'Em breve'};
  const EDITORIAIS = new Set(['noticia','novidade','tecnologia','projeto','guia','jogos']);
  const CONTEUDOS = new Set(['tecnologia','projeto','guia','jogos']);
  const DEFAULT_INVITE = 'https://discord.gg/evsYVUsJAk';
  let state = { posts:[], grupos:[], casino:[], historia:'', convite:DEFAULT_INVITE };
  let feedFilter = 'todos';
  let teamFilter = 'adm';

  const make = (tag, cls='', txt) => {const node=document.createElement(tag);if(cls)node.className=cls;if(txt!==undefined)node.textContent=txt;return node;};
  const safeUrl = (value, fallback='') => {try {const url=new URL(value,location.origin);if(url.protocol==='https:' || (url.origin===location.origin && url.protocol===location.protocol)) return url.href;}catch{}return fallback;};
  const imageUrl = value => {if(!value || typeof value!=='string')return '';return safeUrl(value,'');};
  const date = (d,opts={day:'2-digit',month:'short',year:'numeric'}) => {const n=new Date(d);return Number.isNaN(n.getTime())?'Data a definir':n.toLocaleDateString('pt-BR',opts);};
  const fmt = n => Number(n||0).toLocaleString('pt-BR');
  const appendEmpty = (root,msg) => root.replaceChildren(make('div','empty-state',msg));
  const isUpcoming = p => !p.fim || new Date(p.fim).getTime() > Date.now();
  const trimmed = (v,n) => {const s=String(v||'').trim();return s.length>n?s.slice(0,n).trimEnd()+'…':s;};
  const type = p => LABELS[p.tipo]||'Publicação';

  function dialog(post){
    const d=$('#post-dialog');if(!d)return;
    $('#dialog-tag').textContent=type(post);
    $('#dialog-title').textContent=post.titulo||'Publicação';
    const when=(post.fim && ['evento','sorteio','embreve'].includes(post.tipo)) ? ` · ${post.tipo==='embreve'?'Previsto para':post.tipo==='evento'?'Data/encerramento':'Encerra'} ${date(post.fim,{day:'2-digit',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'})}` : '';
    $('#dialog-meta').textContent=`${post.autor||'Equipe Sant\'s'} · ${date(post.ts)}${when}`;
    $('#dialog-copy').textContent=post.texto||'';
    const img=$('#dialog-image');img.replaceChildren();const url=imageUrl(post.banner);
    if(url){const picture=make('img');picture.src=url;picture.alt=`Imagem da publicação ${post.titulo||''}`;picture.loading='lazy';img.append(picture);}img.hidden=!url;
    if(!d.open)d.showModal();
  }
  $('#dialog-close')?.addEventListener('click',()=>$('#post-dialog').close());
  $('#dialog-ok')?.addEventListener('click',()=>$('#post-dialog').close());
  $('#post-dialog')?.addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.close()});

  function postCard(p){
    const card=make('button','post-card');card.type='button';card.setAttribute('aria-label',`Ler ${type(p)}: ${p.titulo}`);
    const media=make('div','post-media');const url=imageUrl(p.banner);
    if(url){media.classList.add('has-image');const picture=make('img');picture.loading='lazy';picture.src=url;picture.alt='';media.append(picture);}else{media.append(make('span','post-monogram',p.tipo==='tecnologia'?'⌘':p.tipo==='guia'?'✦':p.tipo==='projeto'?'◇':p.tipo==='jogos'?'♠':'S'))};
    const body=make('div','post-body');const top=make('div','post-top');top.append(make('span','post-category',type(p)),make('span','',date(p.ts)));
    body.append(top,make('h3','',p.titulo||'Sem título'),make('p','',trimmed(p.texto,210)),make('span','post-arrow','Ler publicação ↗'));
    card.append(media,body);card.addEventListener('click',()=>dialog(p));return card;
  }
  function feed(){
    const root=$('#feed');if(!root)return;root.replaceChildren();
    const query=($('#feed-search')?.value||'').trim().toLocaleLowerCase('pt-BR');
    const posts=state.posts.filter(p=>EDITORIAIS.has(p.tipo) && (feedFilter==='todos'||p.tipo===feedFilter) && (!query||`${p.titulo||''} ${p.texto||''} ${type(p)}`.toLocaleLowerCase('pt-BR').includes(query)));
    if(!posts.length){appendEmpty(root,query?'Nenhuma publicação encontrada para sua busca.':'Ainda não há publicações nesta categoria.');return;}
    posts.forEach(p=>root.append(postCard(p)));
  }
  $('#feed-filters')?.addEventListener('click',e=>{
    const button=e.target.closest('[data-feed]');if(!button)return;feedFilter=button.dataset.feed;
    $$('[data-feed]','#feed-filters').forEach(b=>{const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});feed();
  });
  $('#feed-search')?.addEventListener('input',feed);

  function rank(){const root=$('#ranking');root.replaceChildren();
    if(!state.casino.length){appendEmpty(root,'O ranking aparecerá quando houver carteiras com saldo registrado.');return;}
    state.casino.slice(0,5).forEach((player,index)=>{
      const row=make('div','rank-row');row.append(make('strong','',String(index+1).padStart(2,'0')));
      const url=imageUrl(player.avatar);const pic=url?make('img'):make('div','rank-placeholder','S');if(url){pic.src=url;pic.alt='';pic.loading='lazy';}row.append(pic,make('span','rank-name',player.nome||'Membro'),make('span','rank-score',`${fmt(player.moedas)} SC`));root.append(row);
    });
  }
  function eventRow(post){const b=make('button','agenda-item');b.type='button';const info=make('div');info.append(make('span','agenda-item-title',post.titulo||'Atividade'));
    const end=post.fim?`${post.tipo==='embreve'?'Previsto':'Até'} ${date(post.fim,{day:'2-digit',month:'short',year:'numeric'})}`:'Data a definir';info.append(make('span','agenda-item-date',end));b.append(info,make('span','agenda-open','↗'));b.addEventListener('click',()=>dialog(post));return b;}
  function events(){const a=$('#eventos-lista'),b=$('#sorteios-lista');a.replaceChildren();b.replaceChildren();
    const upcoming=state.posts.filter(p=>p.tipo==='evento' && isUpcoming(p));const future=state.posts.filter(p=>['sorteio','embreve'].includes(p.tipo) && isUpcoming(p));
    if(!upcoming.length)appendEmpty(a,'Nenhum evento ativo anunciado no momento.');else upcoming.slice(0,5).forEach(p=>a.append(eventRow(p)));
    if(!future.length)appendEmpty(b,'Nenhum sorteio ou lançamento anunciado no momento.');else future.slice(0,5).forEach(p=>b.append(eventRow(p)));
  }
  function editorial(){const root=$('#conteudos-lista');root.replaceChildren();const posts=state.posts.filter(p=>CONTEUDOS.has(p.tipo)).slice(0,4);
    if(!posts.length){appendEmpty(root,'Em preparação: a equipe poderá publicar guias, tecnologia, Roblox e projetos pelo painel administrativo.');return;}
    posts.forEach(p=>{const item=make('button','editorial-item');item.type='button';
      const icon=make('span','editorial-item-icon',p.tipo==='guia'?'✎':p.tipo==='tecnologia'?'⌘':p.tipo==='jogos'?'♠':'◇');const content=make('span','editorial-item-content');content.append(make('small','',type(p).toUpperCase()),make('strong','',p.titulo));item.append(icon,content,make('span','editorial-item-arrow','↗'));item.addEventListener('click',()=>dialog(p));root.append(item);
    });
  }
  function team(){const root=$('#team-grid');root.replaceChildren();const groups=state.grupos.filter(g=>teamFilter==='adm'?g.kind==='staff':g.chave===teamFilter);const people=groups.flatMap(g=>(g.membros||[]).map(m=>({...m,grupo:g.nome})));
    const total=groups.reduce((n,g)=>n+Number(g.total||0),0);$('#team-total').textContent=`${fmt(total)} ${total===1?'integrante':'integrantes'}`;
    if(!people.length){appendEmpty(root,'Este grupo não possui integrantes exibidos no momento.');return;}
    people.slice(0,12).forEach(member=>{const card=make('div','team-person');const url=imageUrl(member.avatar);const avatar=url?make('img'):make('div','team-avatar','S');if(url){avatar.src=url;avatar.alt='';avatar.loading='lazy';}const text=make('div');text.append(make('b','',member.nome||'Membro'),make('small','',member.titulo||member.grupo));card.append(avatar,text);root.append(card);});
    if(people.length>12)root.append(make('div','empty-state',`Exibindo 12 de ${fmt(people.length)} integrantes. Consulte o Discord para a lista completa.`));
  }
  $('#team-tabs')?.addEventListener('click',e=>{const b=e.target.closest('[data-team]');if(!b)return;teamFilter=b.dataset.team;$$('[data-team]','#team-tabs').forEach(x=>{const on=x===b;x.classList.toggle('active',on);x.setAttribute('aria-pressed',String(on));});team();});

  function history(){const root=$('#historia-texto');root.replaceChildren();const history=(state.historia||'').trim();
    if(!history){root.append(make('p','','Nossa história será publicada pela administração em breve.'));return;}
    history.split(/\n\s*\n/).slice(0,6).forEach(s=>root.append(make('p','',s.trim())));
  }
  function stats(){const count=state.posts.length,events=state.posts.filter(p=>p.tipo==='evento').length;
    $('#stat-membros').textContent=fmt(state.membros||0);$('#stat-posts').textContent=fmt(count);$('#stat-eventos').textContent=fmt(events);
  }
  function links(){const invite=safeUrl(state.convite,DEFAULT_INVITE);$$('[data-invite]').forEach(a=>a.href=invite);
    const game=safeUrl(state.cassino_url,invite);$('#cassino-link').href=game;
  }
  function menu(){const button=$('#menu-toggle'),menu=$('#menu-principal');if(!button||!menu)return;
    const close=()=>{menu.classList.remove('open');button.setAttribute('aria-expanded','false');button.setAttribute('aria-label','Abrir menu');};
    button.addEventListener('click',()=>{const open=button.getAttribute('aria-expanded')!=='true';menu.classList.toggle('open',open);button.setAttribute('aria-expanded',String(open));button.setAttribute('aria-label',open?'Fechar menu':'Abrir menu');});
    $$('a',menu).forEach(a=>a.addEventListener('click',close));window.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
    window.addEventListener('resize',()=>{if(innerWidth>820)close();});
  }
  async function load(){
    try{
      const timeout=new AbortController();const timer=setTimeout(()=>timeout.abort(),12000);
      let res;try{res=await fetch('/api/public',{signal:timeout.signal,headers:{'Accept':'application/json'}})}finally{clearTimeout(timer)}
      if(!res.ok)throw new Error(`API ${res.status}`);const data=await res.json();
      state={posts:Array.isArray(data.posts)?data.posts:[],grupos:Array.isArray(data.grupos)?data.grupos:[],casino:Array.isArray(data.cassino)?data.cassino:[],historia:typeof data.historia==='string'?data.historia:'',convite:data.convite||DEFAULT_INVITE,membros:Number(data.membros||0),cassino_url:data.cassino_url||''};
      links();stats();feed();events();editorial();team();rank();history();
    }catch(err){console.warn('Portal Sant\'s: dados indisponíveis:',err);
      appendEmpty($('#feed'),'Não foi possível carregar as notícias. Atualize a página para tentar novamente.');
      appendEmpty($('#ranking'),'Ranking temporariamente indisponível.');
      appendEmpty($('#eventos-lista'),'Agenda temporariamente indisponível.');
      appendEmpty($('#sorteios-lista'),'Agenda temporariamente indisponível.');
      appendEmpty($('#conteudos-lista'),'Conteúdos temporariamente indisponíveis.');
      appendEmpty($('#team-grid'),'Equipe temporariamente indisponível.');
      history();
    }
  }
  $('#ano').textContent=new Date().getFullYear();menu();load();
})();
