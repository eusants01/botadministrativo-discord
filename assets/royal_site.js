const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = (s='') => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

let data = null, shown = 8, me = null;
const DAMAS = new Set(['Bruna', 'Pietra', 'Kananda', 'Tatah', 'Lívia', 'Livia', 'Nathy']);
const FALLBACK = {
  online: false,
  membros: [],
  influencers: [],
  staff: [],
  apoio: [],
  insignias: [],
  beneficios: [
    { nome: 'Sorteios exclusivos', descricao: 'Premiações reservadas aos integrantes oficiais.', emoji: '🎁' },
    { nome: 'Indicações familiares', descricao: 'Sugestões de novos nomes para avaliação da família.', emoji: '📜' },
    { nome: 'Perfil Royal', descricao: 'Perfil público personalizado dentro do portal.', emoji: '👑' },
    { nome: 'Conselho Royal', descricao: 'Propostas públicas com participação e votação.', emoji: '⚖️' },
    { nome: 'Call privada', descricao: 'Canal de voz reservado aos membros oficiais da família.', emoji: '🎙️' },
    { nome: 'Permissões no E.B', descricao: 'Vantagens especiais por ter o cargo da Família no servidor do E.B.', emoji: '🛡️' },
    { nome: 'Eventos privativos', descricao: 'Experiências exclusivas e convites especiais.', emoji: '🎭' }
  ]
};

function empty(msg){ return `<p class="empty">${esc(msg)}</p>`; }
function nameOf(m){ return m?.perfil?.display_name || m?.nome || 'Integrante'; }
function titleOf(m){ return m?.perfil?.title || '@' + (m?.usuario || 'royal'); }
function mottoOf(m){ return m?.perfil?.motto || 'Presença reconhecida dentro da Família Royal.'; }
function badge(txt){ return txt ? `<span>${esc(txt)}</span>` : ''; }
function personCard(m){
  return `<button class="person reveal" data-person="${esc(m.id)}">
    <img src="${esc(m.avatar)}" alt="${esc(nameOf(m))}" loading="lazy">
    <strong>${esc(nameOf(m))}</strong>
    <small>${esc(titleOf(m))}</small>
    <p>${esc(mottoOf(m))}</p>
    <em>Conhecer perfil ↗</em>
  </button>`;
}
function staffCard(group){
  return `<article class="staff-card reveal">
    <span class="symbol">${esc(group.simbolo || '✦')}</span>
    <h3>${esc(group.nome)}</h3>
    <p>${esc(group.descricao || '')}</p>
    ${group.pessoas?.length ? group.pessoas.map(m => `<div class="staff-member"><img src="${esc(m.avatar)}" alt=""><span>${esc(nameOf(m))}</span></div>`).join('') : `<div class="staff-empty">Aguardando integrantes neste cargo.</div>`}
  </article>`;
}
function insigniaCard(i){
  return `<article class="insignia-card"><span class="insignia-emoji">${esc(i.emoji || '👑')}</span><div><strong>${esc(i.nome)}</strong><small>${esc(i.descricao || '')}</small></div></article>`;
}
function benefitCard(b){
  return `<article class="benefit reveal"><span class="emoji">${esc(b.emoji || '✦')}</span><h3>${esc(b.nome)}</h3><p>${esc(b.descricao)}</p></article>`;
}
function creatorCard(m){
  return `<button class="creator reveal" data-person="${esc(m.id)}"><img src="${esc(m.avatar)}" alt=""><div><strong>${esc(nameOf(m))}</strong><span>${esc(titleOf(m))}</span></div></button>`;
}

function renderMembers(){
  const q = ($('#member-search')?.value || '').trim().toLowerCase();
  const list = (data?.membros || []).filter(m => `${nameOf(m)} ${m.usuario} ${titleOf(m)}`.toLowerCase().includes(q));
  $('#members-grid').innerHTML = list.length ? list.slice(0, shown).map(personCard).join('') : empty(data?.online ? 'Nenhum integrante corresponde à busca.' : 'Os integrantes serão exibidos assim que a sincronização com o Discord estiver disponível.');
  $('#show-more').classList.toggle('hidden', list.length <= shown);
  $('#official-counter').textContent = data?.online ? `${list.length} integrantes` : 'Sincronização indisponível';
  $('#count-members').textContent = data?.online ? (data.membros?.length || 0) : '—';
  observeReveals();
}

function renderAll(){
  renderMembers();
  $('#staff-grid').innerHTML = (data?.staff || []).map(staffCard).join('') || empty('Sem cargos administrativos carregados.');
  $('#support-grid').innerHTML = (data?.apoio || []).map(staffCard).join('') || empty('Sem cargos de apoio carregados.');
  const staffCount = new Set([...(data?.staff || []), ...(data?.apoio || [])].flatMap(g => (g.pessoas || []).map(p => p.id))).size;
  $('#count-staff').textContent = data?.online ? staffCount : '—';
  const insignias = data?.insignias || [];
  $('#insignias-damas').innerHTML = insignias.filter(i => i.destaque || DAMAS.has(i.nome)).map(insigniaCard).join('') || empty('Sem insígnias em destaque no momento.');
  $('#insignias-cavalheiros').innerHTML = insignias.filter(i => !(i.destaque || DAMAS.has(i.nome))).map(insigniaCard).join('') || empty('Sem outras insígnias no momento.');
  $('#benefits-grid').innerHTML = (data?.beneficios || []).map(benefitCard).join('');
  $('#influencers-grid').innerHTML = (data?.influencers || []).length ? data.influencers.map(creatorCard).join('') : empty('Criadores serão listados automaticamente pelo cargo de influenciador.');
  observeReveals();
}

async function loadData(){
  try {
    const res = await fetch('./api/royal', { cache: 'no-store' });
    if (!res.ok) throw new Error(String(res.status));
    data = await res.json();
  } catch (err) {
    console.warn('Portal Royal:', err);
    data = JSON.parse(JSON.stringify(FALLBACK));
  }
  renderAll();
}

async function openMember(id){
  $('#member-modal').classList.remove('hidden');
  $('#member-modal').setAttribute('aria-hidden','false');
  $('#modal-body').innerHTML = '<p>Consultando integrante...</p>';
  try {
    const res = await fetch(`./api/royal/membro/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error('membro');
    const m = await res.json();
    const p = m.perfil || {};
    const chips = [
      badge('👑 ' + (m.oficial ? 'Membro oficial' : 'Comunidade Royal')),
      m.influencer ? badge('🎥 Influenciador') : '',
      p.badge_a ? badge('✦ ' + p.badge_a) : '',
      p.badge_b ? badge('✦ ' + p.badge_b) : ''
    ].join('');
    const insignias = (m.insignias || []).length ? m.insignias.map(i => `<span class="role-tag">${esc(i.emoji)} ${esc(i.nome)}</span>`).join('') : empty('Nenhuma insígnia registrada.');
    $('#modal-body').innerHTML = `
      <img src="${esc(m.avatar)}" alt="${esc(nameOf(m))}">
      <h3>${esc(p.display_name || m.nome)}</h3>
      <p class="verified">@${esc(m.usuario)}</p>
      <div class="profile-badges">${chips}</div>
      ${p.title ? `<p class="verified">${esc(p.title)}</p>` : ''}
      ${p.motto ? `<p><em>${esc(p.motto)}</em></p>` : ''}
      ${p.bio ? `<p>${esc(p.bio)}</p>` : ''}
      <h4>Insígnias reconhecidas</h4>
      <div class="profile-badges">${insignias}</div>
      ${p.link ? `<p><a class="cta-button" href="${esc(p.link)}" target="_blank" rel="noopener noreferrer">Abrir link público ↗</a></p>` : ''}
      ${p.signature ? `<p class="verified">${esc(p.signature)}</p>` : ''}
    `;
  } catch (err) {
    $('#modal-body').innerHTML = '<p>Não foi possível consultar este integrante agora.</p>';
  }
}

function applyTheme(theme='gold'){
  const preview = $('#preview-card');
  preview.classList.remove('theme-gold','theme-ivory','theme-rose','theme-onyx');
  preview.classList.add(`theme-${theme}`);
}

function preview(profile={}, member={}){
  const form = $('#profile-form');
  const get = name => form?.elements?.namedItem(name)?.value?.trim?.() ?? profile?.[name] ?? '';
  $('#profile-preview-name').textContent = get('display_name') || member.nome || 'Seu nome aqui';
  $('#profile-preview-title').textContent = get('title') || 'Integrante da comunidade';
  $('#profile-preview-motto').textContent = get('motto') || 'Seu lema aparece aqui.';
  $('#profile-preview-bio').textContent = get('bio') || 'Sua descrição pública aparece aqui.';
  const tags = [get('badge_a'), get('badge_b')].filter(Boolean);
  $('#profile-preview-tags').innerHTML = tags.length ? tags.map(t => `<span>${esc(t)}</span>`).join('') : '<span>✦ Perfil Royal</span>';
  const baseBadges = [member.roles?.includes('1554367619463913582') ? '👑 Membro oficial' : '✦ Comunidade Royal'];
  if (member.roles?.includes('1565443626388164790')) baseBadges.push('🎥 Influenciador');
  $('#profile-preview-badges').innerHTML = baseBadges.map(b => `<span>${esc(b)}</span>`).join('');
  if (member.avatar) $('#profile-avatar').src = member.avatar;
  const link = get('link');
  const linkEl = $('#profile-preview-link');
  if (link.startsWith('https://')) {
    linkEl.href = link; linkEl.classList.remove('hidden');
  } else { linkEl.classList.add('hidden'); linkEl.removeAttribute('href'); }
  applyTheme(get('color') || 'gold');
}

async function loadMe(){
  const loginBox = $('#profile-login');
  const form = $('#profile-form');
  try {
    const res = await fetch('./api/royal/me', { cache: 'no-store', credentials: 'same-origin' });
    if (!res.ok) throw new Error(String(res.status));
    me = await res.json();
    if (!me.authenticated) {
      loginBox.classList.remove('hidden');
      form.classList.add('hidden');
      preview();
      return;
    }
    loginBox.classList.add('hidden');
    form.classList.remove('hidden');
    const profile = me.profile || {};
    ['display_name','bio','title','motto','color','link','badge_a','badge_b','signature'].forEach(key => {
      const input = form.elements.namedItem(key);
      if (input) input.value = profile[key] || (key === 'color' ? 'gold' : '');
    });
    preview(profile, me.member);
  } catch (err) {
    console.warn('Royal profile unavailable', err);
    loginBox.querySelector('p').textContent = 'Não foi possível carregar sua sessão. Confira as variáveis OAuth2 e PostgreSQL no Railway e tente entrar novamente.';
    loginBox.classList.remove('hidden');
    form.classList.add('hidden');
    preview();
  }
}

function observeReveals(){
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) { $$('.reveal').forEach(el => el.classList.add('visible')); return; }
  if (!window.__royalObserver) window.__royalObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        window.__royalObserver.unobserve(entry.target);
      }
    });
  }, { threshold: .08 });
  $$('.reveal').forEach(el => window.__royalObserver.observe(el));
}

function initTilt(){
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  $$('[data-tilt]').forEach(card => {
    card.addEventListener('mousemove', e => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      const rx = (py - .5) * -8;
      const ry = (px - .5) * 8;
      card.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-2px)`;
    });
    card.addEventListener('mouseleave', () => { card.style.transform = ''; });
  });
}

function initCursorGlow(){
  const glow = $('#cursor-glow');
  if (!glow) return;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || matchMedia('(pointer: coarse)').matches) return;
  window.addEventListener('pointermove', e => {
    glow.style.left = `${e.clientX}px`;
    glow.style.top = `${e.clientY}px`;
  });
}

document.addEventListener('click', e => {
  const btn = e.target.closest('[data-person]');
  if (btn) openMember(btn.dataset.person);
});
$('#member-search')?.addEventListener('input', () => { shown = 8; renderMembers(); });
$('#show-more')?.addEventListener('click', () => { shown += 8; renderMembers(); });
const closeModal = () => { $('#member-modal').classList.add('hidden'); $('#member-modal').setAttribute('aria-hidden','true'); };
$('#modal-close')?.addEventListener('click', closeModal);
$('#modal-shade')?.addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
$('#menu-btn')?.addEventListener('click', () => {
  const nav = $('#nav');
  nav.classList.toggle('open');
  $('#menu-btn').setAttribute('aria-expanded', nav.classList.contains('open') ? 'true' : 'false');
});
$$('#nav a').forEach(a => a.addEventListener('click', () => { $('#nav').classList.remove('open'); $('#menu-btn').setAttribute('aria-expanded','false'); }));
$('#profile-form')?.addEventListener('input', () => preview({}, me?.member || {}));
$('#profile-form')?.addEventListener('change', () => preview({}, me?.member || {}));
$('#profile-form')?.addEventListener('submit', async e => {
  e.preventDefault();
  const feedback = $('#profile-feedback');
  const btn = e.currentTarget.querySelector('[type="submit"]');
  btn.disabled = true;
  feedback.textContent = 'Salvando...';
  try {
    const payload = Object.fromEntries(new FormData(e.currentTarget));
    const res = await fetch('./api/royal/me', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || 'Falha ao salvar');
    feedback.textContent = '✓ Perfil atualizado com sucesso.';
    await loadData();
    await loadMe();
  } catch (err) {
    feedback.textContent = '⚠ ' + err.message;
  } finally { btn.disabled = false; }
});
$('#profile-logout')?.addEventListener('click', async () => {
  await fetch('./auth/logout', { method: 'POST', credentials: 'same-origin' });
  await loadMe();
});
$('#year').textContent = new Date().getFullYear();

initCursorGlow();
initTilt();
loadData();
loadMe();
setInterval(loadData, 90000);
