"""Painel administrativo da Família Sant's (FastAPI + discord.py, no mesmo processo do bot)."""
import asyncio, os, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp, asyncpg, discord, uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

E = os.environ
GUILD_ID = int(E["GUILD_ID"])
LOG_CH = int(E.get("CANAL_LOGS_ID", 1556915094615752824))
AVISOS_CH = int(E.get("CANAL_AVISOS_ID", 0)) or LOG_CH
BASE = E["PUBLIC_URL"].rstrip("/")  # ex.: https://xxx.up.railway.app

# nome: (nível, id do cargo). Nível maior = mais autoridade.
CARGOS = {
    "Diretor Geral": (5, int(E.get("ROLE_DIRETOR", 1553923854877990945))),
    "Administrador": (4, int(E.get("ROLE_ADMIN", 1553832097255260260))),
    "Moderador": (3, int(E.get("ROLE_MOD", 1553832097905377422))),
    "Estagiário": (2, int(E.get("ROLE_ESTAGIARIO", 1553832098404499516))),
    "Supervisor de Famílias": (1, int(E.get("ROLE_SUPERVISOR", 1556295901293715486))),
}
# nível mínimo para cada ação (Estagiário e Supervisor só leem)
PERM = {"timeout": 3, "kick": 3, "ban": 4, "aviso": 4, "cargo_add": 5, "cargo_remove": 5,
        "post": 4, "historia": 5}

# Donos além do dono do servidor: acesso total ao painel e destaque no site
FUND = {697068974323793921: "Fundadora e integrante mais antiga",
        1455331305813311692: "Último fundador a entrar"}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=E["SESSION_SECRET"], https_only=True,
                   same_site="lax", max_age=60 * 60 * 8)
bot: discord.Client = None
pool: asyncpg.Pool = None
SQL = """create table if not exists audit(id serial primary key, ts timestamptz default now(),
ator_id bigint, ator text, acao text, alvo_id bigint, alvo text, detalhe text)"""


def cargo(m):
    if m.id == m.guild.owner_id or m.id in FUND:  # donos têm acesso total
        return (6, "Dono")
    ids = {r.id for r in m.roles}
    return max(((l, n) for n, (l, i) in CARGOS.items() if i in ids), default=(0, ""))


async def usuario(req: Request):
    uid = req.session.get("uid")
    if not uid:
        raise HTTPException(401, "Faça login.")
    try:  # confere os cargos ATUAIS a cada requisição
        m = await bot.get_guild(GUILD_ID).fetch_member(uid)
    except discord.NotFound:
        raise HTTPException(403, "Você não está no servidor.")
    if not cargo(m)[0]:
        raise HTTPException(403, "Seu cargo não tem acesso ao painel.")
    return m, cargo(m)[0]


async def registrar(m, acao, alvo=None, detalhe=""):
    await pool.execute("insert into audit(ator_id,ator,acao,alvo_id,alvo,detalhe) values($1,$2,$3,$4,$5,$6)",
                       m.id, str(m), acao, alvo.id if alvo else None, str(alvo) if alvo else None, detalhe)
    ch = bot.get_channel(LOG_CH)
    if ch:
        e = discord.Embed(title=f"Painel · {acao}", color=0x2F7BFF, timestamp=discord.utils.utcnow())
        e.add_field(name="Quem", value=f"{m.mention} ({cargo(m)[1]})", inline=False)
        if alvo:
            e.add_field(name="Alvo", value=f"{alvo.mention} ({alvo})", inline=False)
        if detalhe:
            e.add_field(name="Detalhes", value=detalhe[:1000], inline=False)
        await ch.send(embed=e)


HERE = Path(__file__).parent
app.mount("/assets", StaticFiles(directory=HERE / "assets", check_dir=False), name="assets")


@app.get("/", response_class=HTMLResponse)
async def home():
    return (HERE / "site.html").read_text(encoding="utf-8")


@app.get("/painel", response_class=HTMLResponse)
async def painel_page():
    return (HERE / "painel.html").read_text(encoding="utf-8")


@app.get("/login")
async def login(req: Request):
    req.session["state"] = s = secrets.token_urlsafe(24)
    q = f"client_id={E['DISCORD_CLIENT_ID']}&redirect_uri={BASE}/callback&response_type=code&scope=identify&state={s}"
    return RedirectResponse("https://discord.com/oauth2/authorize?" + q)


@app.get("/callback")
async def callback(req: Request, code: str = "", state: str = ""):
    if not code or state != req.session.pop("state", None):
        raise HTTPException(400, "Login inválido. Tente de novo.")
    async with aiohttp.ClientSession() as s:
        async with s.post("https://discord.com/api/oauth2/token", data={
            "client_id": E["DISCORD_CLIENT_ID"], "client_secret": E["DISCORD_CLIENT_SECRET"],
            "grant_type": "authorization_code", "code": code, "redirect_uri": f"{BASE}/callback"}) as r:
            tok = (await r.json()).get("access_token")
        if not tok:
            raise HTTPException(400, "Não foi possível entrar com o Discord.")
        async with s.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {tok}"}) as r:
            req.session["uid"] = int((await r.json())["id"])
    return RedirectResponse("/painel")


@app.get("/logout")
async def logout(req: Request):
    req.session.clear()
    return RedirectResponse("/")


@app.get("/api/me")
async def me(req: Request):
    m, lvl = await usuario(req)
    return {"nome": m.display_name, "cargo": cargo(m)[1], "nivel": lvl,
            "acoes": [a for a, n in PERM.items() if lvl >= n],
            "cargos": [n for n, (l, _) in CARGOS.items() if l < lvl]}


@app.get("/api/members")
async def members(req: Request, q: str = ""):
    m, _ = await usuario(req)
    q = q.lower().strip()
    r = [{"id": str(x.id), "nome": x.display_name, "user": x.name, "cargo": cargo(x)[1]}
         for x in m.guild.members if not x.bot and q in f"{x.name} {x.display_name}".lower()]
    r.sort(key=lambda x: (not x["cargo"], x["nome"].lower()))
    return r[:30]


@app.get("/api/audit")
async def audit(req: Request):
    await usuario(req)
    rows = await pool.fetch("select ts,ator,acao,alvo,detalhe from audit order by id desc limit 50")
    return [{"ts": r["ts"].isoformat(), "ator": r["ator"], "acao": r["acao"],
             "alvo": r["alvo"], "detalhe": r["detalhe"]} for r in rows]


@app.post("/api/action")
async def action(req: Request):
    m, lvl = await usuario(req)
    if req.headers.get("x-panel") != "1":
        raise HTTPException(403, "Requisição inválida.")
    d = await req.json()
    a = d.get("acao")
    if a not in PERM or a in ("post", "historia") or lvl < PERM[a]:
        raise HTTPException(403, "Seu cargo não permite esta ação.")
    motivo = (d.get("motivo") or "").strip()[:300]
    razao = f"{m} via painel" + (f": {motivo}" if motivo else "")
    try:
        if a == "aviso":
            txt = (d.get("texto") or "").strip()[:1800]
            if not txt:
                raise HTTPException(400, "Escreva o aviso.")
            await bot.get_channel(AVISOS_CH).send(txt)
            await registrar(m, a, None, txt[:300])
            return {"ok": "Aviso enviado."}
        try:
            alvo = await m.guild.fetch_member(int(d.get("alvo")))
        except (discord.NotFound, TypeError, ValueError):
            raise HTTPException(404, "Membro não encontrado.")
        if alvo.bot or alvo.id in (m.id, m.guild.owner_id) or cargo(alvo)[0] >= lvl:
            raise HTTPException(403, "Você não pode agir sobre este membro.")
        det = motivo
        if a == "timeout":
            mins = min(max(int(d.get("minutos") or 10), 1), 40320)
            await alvo.timeout(timedelta(minutes=mins), reason=razao)
            det = f"{mins} min. {motivo}".strip()
        elif a == "kick":
            await alvo.kick(reason=razao)
        elif a == "ban":
            await alvo.ban(reason=razao, delete_message_days=0)
        else:
            nome = d.get("cargo")
            if nome not in CARGOS or CARGOS[nome][0] >= lvl:
                raise HTTPException(403, "Você não pode mexer neste cargo.")
            role = m.guild.get_role(CARGOS[nome][1])
            await (alvo.add_roles if a == "cargo_add" else alvo.remove_roles)(role, reason=razao)
            det = f"{nome}. {motivo}".strip()
        await registrar(m, a, alvo, det)
        return {"ok": "Ação concluída e registrada."}
    except discord.Forbidden:
        raise HTTPException(400, "O bot não tem permissão. Confira as permissões e a posição do cargo do bot.")


async def start_painel(client: discord.Client):
    """Chame dentro do setup_hook do bot."""
    global bot, pool
    bot = client
    pool = await asyncpg.create_pool(E["DATABASE_URL"])
    await pool.execute(SQL + SQL2)
    await semear()
    cfg = uvicorn.Config(app, host="0.0.0.0", port=int(E.get("PORT", 8000)), log_level="warning",
                         proxy_headers=True, forwarded_allow_ips="*")
    asyncio.create_task(uvicorn.Server(cfg).serve())


SQL2 = """;create table if not exists posts(id serial primary key, ts timestamptz default now(), tipo text,
titulo text, texto text, banner text, autor text, fim timestamptz, destaque boolean default false);
create table if not exists config(chave text primary key, valor text)"""
TIPOS = {"evento": "Evento", "noticia": "Notícia", "novidade": "Novidade", "embreve": "Em breve", "sorteio": "Sorteio"}


def _csrf(req: Request):
    if req.headers.get("x-panel") != "1":
        raise HTTPException(403, "Requisição inválida.")


def _post(r):
    return {"id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"], "texto": r["texto"], "banner": r["banner"],
            "autor": r["autor"], "ts": r["ts"].isoformat(), "destaque": r["destaque"],
            "fim": r["fim"].isoformat() if r["fim"] else None}


@app.get("/api/public")  # aberto a todos: alimenta o site público
async def publico():
    g = bot.get_guild(GUILD_ID)
    rows = await pool.fetch("select * from posts order by destaque desc, id desc limit 40")
    h = await pool.fetchval("select valor from config where chave='historia'")
    staff = sorted(({"nome": m.display_name, "cargo": cargo(m)[1], "nivel": cargo(m)[0],
                     "titulo": FUND.get(m.id) or ("Dono do servidor" if m.id == g.owner_id else cargo(m)[1]),
                     "avatar": m.display_avatar.replace(size=128).url}
                    for m in g.members if not m.bot and cargo(m)[0]), key=lambda x: (-x["nivel"], x["nome"].lower()))
    return {"membros": g.member_count, "convite": E.get("INVITE_URL", "https://discord.gg/evsYVUsJAk"), "staff": staff,
            "posts": [_post(r) for r in rows], "historia": h or "",
            "grupos": grupos(g), "cassino": top_cassino(g),
            "cassino_url": f"https://discord.com/channels/{GUILD_ID}/{CASSINO_CH}"}


@app.post("/api/post")
async def salvar_post(req: Request):
    m, lvl = await usuario(req)
    _csrf(req)
    if lvl < PERM["post"]:
        raise HTTPException(403, "Seu cargo não permite publicar.")
    d = await req.json()
    tipo, titulo = d.get("tipo"), (d.get("titulo") or "").strip()[:120]
    texto, banner = (d.get("texto") or "").strip()[:4000], (d.get("banner") or "").strip()[:500] or None
    if tipo not in TIPOS or not titulo or not texto:
        raise HTTPException(400, "Preencha tipo, título e texto.")
    if banner and not banner.startswith(("https://", "/assets/")):
        raise HTTPException(400, "O banner precisa ser um link https:// ou um arquivo em /assets/")
    fim = None
    if d.get("fim"):
        try:
            fim = datetime.fromisoformat(d["fim"].replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Data inválida.")
    dest = bool(d.get("destaque"))
    if d.get("id"):
        await pool.execute("update posts set tipo=$1,titulo=$2,texto=$3,banner=$4,fim=$5,destaque=$6 where id=$7",
                           tipo, titulo, texto, banner, fim, dest, int(d["id"]))
        acao = "post_editar"
    else:
        await pool.execute("insert into posts(tipo,titulo,texto,banner,autor,fim,destaque) values($1,$2,$3,$4,$5,$6,$7)",
                           tipo, titulo, texto, banner, m.display_name, fim, dest)
        acao = "post_criar"
        if d.get("discord"):
            e = discord.Embed(title=titulo, description=texto[:1500], color=0x2F7BFF, url=BASE)
            e.set_footer(text=f"Família Sant's · {TIPOS[tipo]}")
            if banner:
                e.set_image(url=banner)
            try:
                await bot.get_channel(AVISOS_CH).send(embed=e)
            except discord.HTTPException:
                pass
    await registrar(m, acao, None, f"{TIPOS[tipo]}: {titulo}")
    return {"ok": "Publicado no site."}


@app.post("/api/post/delete")
async def apagar_post(req: Request):
    m, lvl = await usuario(req)
    _csrf(req)
    if lvl < PERM["post"]:
        raise HTTPException(403, "Seu cargo não permite excluir.")
    d = await req.json()
    r = await pool.fetchrow("delete from posts where id=$1 returning titulo", int(d.get("id") or 0))
    if not r:
        raise HTTPException(404, "Publicação não encontrada.")
    await registrar(m, "post_excluir", None, r["titulo"])
    return {"ok": "Excluído."}


@app.post("/api/historia")
async def salvar_historia(req: Request):
    m, lvl = await usuario(req)
    _csrf(req)
    if lvl < PERM["historia"]:
        raise HTTPException(403, "Só o Diretor Geral edita a história.")
    t = ((await req.json()).get("texto") or "").strip()[:8000]
    await pool.execute("insert into config(chave,valor) values('historia',$1) "
                       "on conflict(chave) do update set valor=$1", t)
    await registrar(m, "historia_editar", None, f"{len(t)} caracteres")
    return {"ok": "História salva."}


CASSINO_CH = int(E.get("CANAL_CASSINO_ID", 1502025561445240982))
EXTRAS = {"Criadores": int(E.get("ROLE_CRIADORES", 1553944794957615175)),
          "Membros Oficiais": int(E.get("ROLE_OFICIAIS", 1554367619463913582))}
# Edite os textos abaixo à vontade: aparecem no site, em "Cargos da Família"
DESC = {
    "Dono": "Fundadores e donos da Família. Decidem o rumo da Família e têm acesso total aos sistemas.",
    "Diretor Geral": "Maior cargo da administração. Define projetos e sistemas, nomeia a equipe e resolve os conflitos mais sérios.",
    "Administrador": "Cuida da gestão do servidor, analisa denúncias e orienta moderadores e estagiários.",
    "Moderador": "Mantém a ordem, aplica as regras e ajuda os membros no dia a dia.",
    "Estagiário": "Em aprendizado: apoia a equipe e acompanha os atendimentos.",
    "Supervisor de Famílias": "Função externa do E.B do Alpha. Fiscaliza e reporta, sem autoridade sobre os membros.",
    "Criadores": "Membros que criam conteúdo e dão vida à comunidade da Família.",
    "Membros Oficiais": "Integrantes oficiais da Família Sant's.",
}


def _mem(m, titulo=""):
    return {"nome": m.display_name, "titulo": titulo, "avatar": m.display_avatar.replace(size=128).url}


def _grupo(chave, role, ms, kind, limite=None, cor="#2f7bff"):
    ms = sorted(ms, key=lambda m: m.display_name.lower())
    c = f"#{role.color.value:06x}" if role and role.color.value else cor
    return {"chave": chave, "nome": role.name if role else chave + "s", "cor": c, "desc": DESC[chave], "kind": kind,
            "total": len(ms), "membros": [_mem(m, FUND.get(m.id) or ("Dono do servidor" if m.id == m.guild.owner_id else ""))
                                          for m in ms[:limite]]}


def grupos(g):
    """Monta os grupos do site direto dos cargos do Discord (muda no servidor, muda no site)."""
    out, vivos = [], [m for m in g.members if not m.bot]
    out.append(_grupo("Dono", None, [m for m in vivos if cargo(m)[0] == 6], "staff", cor="#ffd166"))
    for nome, (lvl, rid) in sorted(CARGOS.items(), key=lambda x: -x[1][0]):
        out.append(_grupo(nome, g.get_role(rid), [m for m in vivos if cargo(m)[1] == nome], "staff"))
    for nome, rid in EXTRAS.items():
        r = g.get_role(rid)
        todos = [m for m in vivos if r and r in m.roles]
        gr = _grupo(nome, r, [m for m in todos if not cargo(m)[0]], "comum", limite=60)
        gr["total"] = len(todos)
        out.append(gr)
    return [x for x in out if x["total"]]


def top_cassino(g):
    try:
        from utils.cassino_db import ranking_ricos
        rows = ranking_ricos(5)
    except Exception:
        return []
    res = []
    for uid, moedas in rows:
        m = g.get_member(int(uid))
        res.append({"nome": m.display_name if m else "Membro", "moedas": int(moedas),
                    "avatar": m.display_avatar.replace(size=64).url if m else ""})
    return res


EV_TEXTO = """Durante uma semana, você terá a oportunidade de convidar novos membros para a Família e disputar prêmios incríveis.

Início: 04/10/2026

Premiação:
1º lugar: 1000 Robux
2º lugar: 400 Robux
3º lugar: Classic N1TR0

Durante o período do evento, os membros deverão convidar novas pessoas para o servidor. Ao final, os participantes com maior número de convites válidos ocuparão as primeiras posições do ranking e receberão suas premiações.

Regras:
• Convites por DM sem autorização: não é permitido enviar convite do servidor por mensagem privada para outra pessoa sem a autorização prévia da mesma. O objetivo é evitar spam e convites indesejados.
• Contas alternativas (ALTS): não será permitida a utilização de contas alternativas para aumentar a quantidade de convites. Contas identificadas como falsas ou utilizadas para benefício próprio poderão ser desconsideradas.
• Convites válidos: somente serão contabilizados convites reais e válidos, realizados por pessoas que realmente tenham entrado no servidor através do convite do participante."""


async def semear():
    """Na primeira vez, publica o Evento de Convites que está rolando (edite a data no painel)."""
    if await pool.fetchval("select count(*) from posts"):
        return
    await pool.execute("insert into posts(tipo,titulo,texto,banner,autor,fim,destaque) values('evento',$1,$2,$3,$4,$5,true)",
                       "Evento de Convites", EV_TEXTO, "/assets/evento-convites.jpg", "Administração",
                       datetime(2026, 10, 11, 23, 59, tzinfo=timezone(timedelta(hours=-3))))