"""Portal público da Família Royal; não expõe comandos administrativos."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import discord
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

LOG = logging.getLogger("royal.site")
BASE = Path(__file__).resolve().parent
GUILD_ID = int(os.getenv("GUILD_ID", "1553803921514963075"))
OFC_ID = 1554367619463913582
INFLUENCER_ID = 1565443626388164790

STAFF = [
    ("Manager", 1553923854877990945, "Direção e organização geral", "♛"),
    ("Administrador", 1562909560430264420, "Gestão e administração", "⚜"),
    ("Coordenador", 1553832097255260260, "Coordenação das equipes", "✦"),
    ("Supervisor", 1562950237117481000, "Acompanhamento operacional", "◆"),
    ("Moderador", 1553832097905377422, "Segurança e convivência", "◇"),
    ("Estagiário", 1553832098404499516, "Formação e apoio à equipe", "✧"),
]
OTHER = [
    ("Analista de Famílias", 1556295901293715486, "Fiscalização independente da hierarquia administrativa", "◎"),
    ("Organizador de Eventos", 1561231585993293864, "Planejamento de eventos e atividades", "✧"),
    ("Organizador de Leilões", 1559771638025691178, "Organização de leilões e premiações", "♢"),
]
BENEFITS = [
    ("Sorteios exclusivos", "Premiações reservadas aos integrantes oficiais.", "🎁"),
    ("Indicações familiares", "Recomende novos candidatos para avaliação.", "📜"),
    ("Perfil Royal", "Trajetória, reconhecimentos e insígnias pessoais.", "👤"),
    ("Eventos privativos", "Atividades e experiências exclusivas.", "🎭"),
    ("Conselho Royal", "Propostas e votações consultivas dos membros.", "⚖️"),
    ("Call privada", "Espaço de voz reservado aos integrantes oficiais.", "🎙️"),
    ("Permissões no E.B", "Vantagens do cargo Família no E.B do ALPHA, conforme regras locais.", "🛡️"),
]

app = FastAPI(title="Família Royal — Portal Oficial", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/assets", StaticFiles(directory=str(BASE / "assets")), name="assets")
_bot: discord.Client | None = None


def guild():
    return _bot.get_guild(GUILD_ID) if _bot and _bot.is_ready() else None


def member_data(m: discord.Member):
    return {"id": str(m.id), "nome": m.display_name,
            "usuario": m.name, "avatar": str(m.display_avatar.replace(size=128).url),
            "roles": [str(r.id) for r in m.roles],
            "ingresso_servidor": m.joined_at.isoformat() if m.joined_at else None}


def members_of(g, role_id):
    role = g.get_role(role_id)
    if not role:
        return []
    return sorted([member_data(m) for m in role.members if not m.bot], key=lambda m: m["nome"].casefold())


@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "royal_site.html").read_text(encoding="utf-8")


@app.get("/api/royal")
async def royal_data():
    g = guild()
    if g is None:
        return {"online": False, "membros": [], "influencers": [], "staff": [], "apoio": [],
                "beneficios": [{"nome": n, "descricao": d, "emoji": e} for n,d,e in BENEFITS],
                "insignias": insignias(), "error": "Sincronização com o Discord indisponível."}
    def group(entry):
        name, rid, desc, symbol = entry
        return {"nome": name, "id": str(rid), "descricao": desc, "simbolo": symbol,
                "pessoas": members_of(g, rid)}
    return {"online": True, "guild": g.name,
            "membros": members_of(g, OFC_ID), "influencers": members_of(g, INFLUENCER_ID),
            "staff": [group(r) for r in STAFF], "apoio": [group(r) for r in OTHER],
            "beneficios": [{"nome": n, "descricao": d, "emoji": e} for n,d,e in BENEFITS],
            "insignias": insignias()}


def insignias():
    # A configuração oficial é importada do cog, sem duplicar IDs ou descrições.
    try:
        from cogs.insignias_royal import INSIGNIAS
        return [{"nome": i["nome"], "cargo_id": str(i["cargo_id"]),
                 "emoji": i["emoji"], "descricao": i["descricao_curta"],
                 "destaque": i["nome"] in {"Bruna", "Pietra", "Kananda", "Tatah", "Lívia", "Livia", "Nathy"}}
                for i in INSIGNIAS]
    except Exception:
        LOG.exception("Não foi possível carregar as insígnias do cog")
        return []


@app.get("/api/royal/membro/{user_id}")
async def royal_member(user_id: int):
    g = guild()
    if g is None:
        raise HTTPException(503, "Discord indisponível")
    m = g.get_member(user_id)
    if m is None:
        try:
            m = await g.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden):
            raise HTTPException(404, "Membro não encontrado")
    data = member_data(m)
    data["oficial"] = any(r.id == OFC_ID for r in m.roles)
    data["influencer"] = any(r.id == INFLUENCER_ID for r in m.roles)
    data["insignias"] = [i for i in insignias() if int(i["cargo_id"]) in {r.id for r in m.roles}]
    return data


# Endereços legados: sem autenticação administrativa, apenas redirecionamento público.
for legacy, target in [('/membros', '/#membros'), ('/hierarquia', '/#equipe'),
                       ('/perfil', '/#membros'), ('/conta', '/#membros'),
                       ('/painel', '/'), ('/login', '/'), ('/logout', '/')]:
    async def redirect(destination=target):
        return RedirectResponse(destination, status_code=302)
    app.add_api_route(legacy, redirect, methods=['GET'], include_in_schema=False)


async def start_painel(client: discord.Client):
    global _bot
    _bot = client
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")),
                            log_level="warning", proxy_headers=True, forwarded_allow_ips="*")
    asyncio.create_task(uvicorn.Server(config).serve(), name="royal_public_portal")
    LOG.info("Portal público Royal iniciado, sem painel administrativo")
