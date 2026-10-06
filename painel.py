"""Painel administrativo da Família Sant's (FastAPI + discord.py, no mesmo processo do bot)."""
import asyncio, os, secrets
from datetime import timedelta
from pathlib import Path

import aiohttp, asyncpg, discord, uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
PERM = {"timeout": 3, "kick": 3, "ban": 4, "aviso": 4, "cargo_add": 5, "cargo_remove": 5}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=E["SESSION_SECRET"], https_only=True,
                   same_site="lax", max_age=60 * 60 * 8)
bot: discord.Client = None
pool: asyncpg.Pool = None
SQL = """create table if not exists audit(id serial primary key, ts timestamptz default now(),
ator_id bigint, ator text, acao text, alvo_id bigint, alvo text, detalhe text)"""


def cargo(m):
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


@app.get("/", response_class=HTMLResponse)
async def home():
    return (Path(__file__).parent / "painel.html").read_text(encoding="utf-8")


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
    return RedirectResponse("/")


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
    if a not in PERM or lvl < PERM[a]:
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
    await pool.execute(SQL)
    cfg = uvicorn.Config(app, host="0.0.0.0", port=int(E.get("PORT", 8000)), log_level="warning",
                         proxy_headers=True, forwarded_allow_ips="*")
    asyncio.create_task(uvicorn.Server(cfg).serve())