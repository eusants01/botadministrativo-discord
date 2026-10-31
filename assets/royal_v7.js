(()=>{'use strict';
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches,fine=matchMedia('(hover:hover) and (pointer:fine)').matches;
/* ---- sons (opcional, com mute) ---- */
let sound=localStorage.getItem('royal_sound')==='1',ac;
function beep(f=660,d=.12){if(!sound)return;try{ac=ac||new AudioContext();const o=ac.createOscillator(),g=ac.createGain();o.frequency.value=f;o.type='sine';g.gain.setValueAtTime(.05,ac.currentTime);g.gain.exponentialRampToValueAtTime(.0001,ac.currentTime+d);o.connect(g).connect(ac.destination);o.start();o.stop(ac.currentTime+d)}catch{}}
const sb=$('#sound-btn');const paint=()=>{sb.textContent=sound?'🔊':'🔇';sb.setAttribute('aria-label',sound?'Silenciar sons':'Ativar sons')};paint();
sb.onclick=()=>{sound=!sound;localStorage.setItem('royal_sound',sound?'1':'0');paint();beep(880)};
/* ---- notificações ---- */
window.royalToast=(title,msg='')=>{const t=document.createElement('div');t.className='toast';t.innerHTML=`<b></b><span></span>`;t.firstChild.textContent=title;t.lastChild.textContent=msg;$('#toasts').append(t);beep(784,.2);setTimeout(()=>{t.classList.add('out');setTimeout(()=>t.remove(),400)},4500)};
/* ---- loader: fênix em partículas ---- */
function loader(){
 const L=$('#loader'),c=$('#loader-canvas'),x=c.getContext('2d'),end=()=>{L.classList.add('done');setTimeout(()=>L.remove(),1000)};
 if(reduce){return end()}
 const W=c.width=innerWidth,H=c.height=innerHeight,img=new Image();img.src='/assets/royal_logo.png';
 const fail=setTimeout(end,4500);
 img.onload=()=>{
  const s=Math.min(W,H)*.5,o=document.createElement('canvas');o.width=o.height=200;const ox=o.getContext('2d');ox.drawImage(img,0,0,200,200);
  const d=ox.getImageData(0,0,200,200).data,P=[];
  for(let y=0;y<200;y+=3)for(let X=0;X<200;X+=3){const i=(y*200+X)*4;if(d[i+3]>140)P.push({tx:W/2+(X-100)*s/200,ty:H/2+(y-100)*s/200,x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.6+.6,h:38+Math.random()*14})}
  let t=0;(function f(){t++;x.fillStyle='rgba(5,2,7,.25)';x.fillRect(0,0,W,H);
   for(const p of P){p.x+=(p.tx-p.x)*.06;p.y+=(p.ty-p.y)*.06;x.fillStyle=`hsl(${p.h},95%,${60+Math.sin(t/8+p.x)*12}%)`;x.beginPath();x.arc(p.x,p.y,p.r,0,7);x.fill()}
   if(t<150)requestAnimationFrame(f);else{clearTimeout(fail);setTimeout(end,500)}})();
 };img.onerror=()=>{clearTimeout(fail);end()};
}
loader();
/* ---- hero: partículas flutuando + luz que segue o mouse ---- */
(()=>{const c=$('#hero-canvas'),x=c.getContext('2d'),hero=$('.hero');let W,H;const rs=()=>{W=c.width=hero.offsetWidth;H=c.height=hero.offsetHeight};rs();addEventListener('resize',rs);
 const P=Array.from({length:reduce?0:70},()=>({x:Math.random()*W,y:Math.random()*H,v:Math.random()*.5+.15,r:Math.random()*2+.5,a:Math.random()}));
 (function f(){x.clearRect(0,0,W,H);for(const p of P){p.y-=p.v;if(p.y<-5){p.y=H+5;p.x=Math.random()*W}x.fillStyle=`rgba(255,${200+p.a*40|0},110,${.25+p.a*.5})`;x.beginPath();x.arc(p.x+Math.sin(p.y/40)*8,p.y,p.r,0,7);x.fill()}requestAnimationFrame(f)})();
 hero.addEventListener('pointermove',e=>{const r=hero.getBoundingClientRect();hero.style.setProperty('--mx',e.clientX-r.left+'px');hero.style.setProperty('--my',e.clientY-r.top+'px')},{passive:true});
})();
/* ---- cursor com rastro dourado ---- */
if(fine&&!reduce){const c=$('#trail'),x=c.getContext('2d'),pts=[];const rs=()=>{c.width=innerWidth;c.height=innerHeight};rs();addEventListener('resize',rs);
 addEventListener('pointermove',e=>pts.push({x:e.clientX,y:e.clientY,l:1}),{passive:true});
 (function f(){x.clearRect(0,0,c.width,c.height);for(let i=pts.length-1;i>=0;i--){const p=pts[i];p.l-=.045;if(p.l<=0){pts.splice(i,1);continue}x.fillStyle=`rgba(245,196,81,${p.l*.8})`;x.shadowColor='#f5c451';x.shadowBlur=12;x.beginPath();x.arc(p.x,p.y,p.l*5+1,0,7);x.fill()}requestAnimationFrame(f)})()}
/* ---- brilho nos cartões + parallax ---- */
document.addEventListener('pointermove',e=>{const c=e.target.closest?.('.bento-card');if(c){const r=c.getBoundingClientRect();c.style.setProperty('--gx',e.clientX-r.left+'px');c.style.setProperty('--gy',e.clientY-r.top+'px')}},{passive:true});
if(!reduce)addEventListener('scroll',()=>{const y=scrollY;$('.hero-emblem-wrap').style.translate=`0 ${y*.12}px`;$('#hero-canvas').style.translate=`0 ${y*.25}px`},{passive:true});
/* ---- contadores animados ---- */
function count(el){const n=parseInt(el.textContent);if(isNaN(n)||el.dataset.n===String(n))return;el.dataset.n=n;if(reduce)return;const t0=performance.now();(function f(t){const k=Math.min((t-t0)/1200,1);el.textContent=Math.round(n*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(f)})(t0)}
['#total-members','#total-staff','#members-number'].forEach(s=>{const el=$(s);if(el)new MutationObserver(()=>count(el)).observe(el,{childList:true,characterData:true,subtree:true})});
/* ---- som nos botões ---- */
document.addEventListener('click',e=>{if(e.target.closest('.button,.person-card,.bento-card'))beep(520,.08)});
/* ---- perfil: prévia (moldura/efeito), barra de completude, autosave ---- */
const form=$('#profile-form'),card=$('#profile-preview');let timer;
function sync(){if(!form)return;const d=Object.fromEntries(new FormData(form));card.dataset.frame=d.frame||'gold';card.dataset.fx=d.fx||'sparks';
 const keys=['display_name','title','motto','bio','link','badge_a','badge_b','signature'],ok=keys.filter(k=>(d[k]||'').trim()).length,p=Math.round(ok/keys.length*100);
 $('#meter-pct').textContent=p+'%';$('#meter-bar').style.width=p+'%';return p}
form?.addEventListener('input',()=>{sync();$('#saved-note').textContent='Editando…';clearTimeout(timer);timer=setTimeout(()=>form.requestSubmit(),2200)});
form?.addEventListener('change',sync);
new MutationObserver(()=>{if($('#profile-form').classList.contains('hidden'))return;sync()}).observe(form,{attributes:true});
const fb=$('#profile-feedback');if(fb)new MutationObserver(()=>{const t=fb.textContent;if(t.includes('✓')){$('#saved-note').textContent='✓ Salvo automaticamente';royalToast('Perfil salvo','Seu cartão Royal foi atualizado.');if(sync()===100&&!localStorage.getItem('royal_complete')){localStorage.setItem('royal_complete','1');royalToast('Você ganhou uma insígnia!','Identidade Completa 👑')}}}).observe(fb,{childList:true,characterData:true,subtree:true});
/* ---- easter egg: toque 7x no emblema ---- */
let hits=0,hitT;$('#hero-crest')?.addEventListener('click',()=>{hits++;clearTimeout(hitT);hitT=setTimeout(()=>hits=0,1500);if(hits>=7){hits=0;if(localStorage.getItem('royal_secret')){royalToast('A Fênix já te reconhece','Você já tem esta insígnia.')}else{localStorage.setItem('royal_secret','1');document.body.animate([{filter:'brightness(2.2)'},{filter:'none'}],{duration:900});royalToast('Você ganhou uma insígnia!','🔥 Chama Secreta da Fênix')}}});
/* ---- transição suave entre âncoras ---- */
$$('a[href^="#"]').forEach(a=>a.addEventListener('click',e=>{const t=$(a.getAttribute('href'));if(!t)return;e.preventDefault();t.scrollIntoView({behavior:reduce?'auto':'smooth'})}));
})();
