/* Novas experiências na home. Todas as informações remotas são inseridas como texto. */
(() => {'use strict';
const $=s=>document.querySelector(s);const safe=u=>{try{const x=new URL(u,location.origin);return x.protocol==='https:'||x.origin===location.origin?x.href:''}catch{return ''}};
const node=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!==undefined)e.textContent=txt;return e};
async function init(){try{
 const [resp,brandResp]=await Promise.all([fetch('/api/portal/membros?pagina=1'),fetch('/api/portal/brand')]);
 if(resp.ok){const d=await resp.json();const box=$('#s3-member-list');box.replaceChildren();const people=d.membros||[];if(!people.length)box.append(node('div','empty-state','Os perfis aparecerão após a sincronização do Discord.'));people.slice(0,5).forEach(p=>{const a=node('a','s3-member-card');a.href='/perfil?id='+encodeURIComponent(p.id);const img=node('img');img.src=safe(p.avatar)||'/assets/logo.webp';img.alt='Avatar de '+p.nome;img.loading='lazy';a.append(img,node('strong','',p.nome),node('small','',p.cargos?.[0]?.nome||'Integrante da Família'));box.append(a)})}
 if(brandResp.ok){const d=await brandResp.json();if(d.hero_banner){const u=safe(d.hero_banner);if(u){const hero=document.querySelector('.hero-art');hero.style.backgroundImage=`linear-gradient(90deg,#07101df5 3%,#07131fdc 35%,#07111c66 69%,#05111bc7 100%),url("${u}")`}}
 const art=$('#s3-event-art'),url=safe(d.evento_banner);if(art&&url)art.style.backgroundImage=`linear-gradient(90deg,#130c17 3%,#1a0d1590 30%,transparent 75%),url("${url}")`;
 $('#s3-promotor').textContent=d.evento_promotor||'Kael';if(d.evento_titulo)$(`#evento-secreto h2`).textContent=d.evento_titulo;if(d.evento_subtitulo)$(`#evento-secreto .s3-event-copy>p`).textContent=d.evento_subtitulo;$('#s3-secret-text').textContent=d.spoiler_texto||'';if(!d.spoiler_ativo)$('#s3-spoiler').hidden=true;
 }
}catch(e){console.warn('Atualizações do Portal:',e)} }
const button=$('#s3-spoiler');button?.addEventListener('click',()=>{const el=$('#s3-secret');const open=el.hidden;el.hidden=!open;button.setAttribute('aria-expanded',String(open));button.textContent=open?'✦ O segredo foi revelado — ocultar':'◈ Há algo escondido aqui…'});
init();
})();
