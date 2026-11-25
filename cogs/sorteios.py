from __future__ import annotations

import asyncio
import copy
import logging
import json
import os
import random
import re
import time
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

NOME_SERVIDOR = "Família Royal"
LOG = logging.getLogger("royal.sorteios")
FUSO = ZoneInfo("America/Sao_Paulo")
COR_AZUL = 0xBC9456  

CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,
]

CANAL_LOGS_SORTEIOS_ID = 1559312469959119039

CANAL_SORTEIOS_ID = 1553829712621740103

CARGO_PING_SORTEIOS_ID = 1555798698410377246

BASE_DIR = Path(__file__).resolve().parent.parent

BANNER_SORTEIO = BASE_DIR / "assets" / "ROYAL_SORTEIO_BANNER_URL.png"
BANNER_PAINEL = BASE_DIR / "assets" / "ROYAL_SORTEIO_PAINEL_BANNER_URL.png"


TEXTO_RESGATE = "Abra um ticket em <#1553843978229522633> para resgatar o seu prêmio."

AVISAR_GANHADORES_DM = True

MAX_VENCEDORES = 10
DURACAO_MIN = 60              
DURACAO_MAX = 60 * 86400     

TEMAS = {
    "azul": {"nome": "Royal", "emoji": "👑", "cor": COR_AZUL},
    "ouro": {"nome": "Ouro Imperial", "emoji": "⚜️", "cor": 0xCFAC6D},
    "neon": {"nome": "Relâmpago Royal", "emoji": "⚡", "cor": COR_AZUL},
    "rubi": {"nome": "Rubi", "emoji": "🔥", "cor": 0xC0392B},
    "esmeralda": {"nome": "Esmeralda", "emoji": "🍀", "cor": 0x1ABC9C},
    "galaxia": {"nome": "Galáxia", "emoji": "🌌", "cor": 0x6C3FC5},
}

BONUS_OPCOES = [2, 3, 5]
DIAS_OPCOES = [
    (0, "Sem exigência"),
    (1, "1 dia no servidor"),
    (3, "3 dias no servidor"),
    (7, "7 dias no servidor"),
    (30, "30 dias no servidor"),
]

PASTA_DADOS = os.getenv("ROYAL_SORTEIOS_DATA_DIR", "dados_sorteios")
os.makedirs(PASTA_DADOS, exist_ok=True)
F_SORTEIOS = os.path.join(PASTA_DADOS, "sorteios.json")

SUJOS: set[int] = set()        
ENCERRANDO: set[int] = set()  

_SORTEIOS_CACHE: dict[str, dict] = {}
_POOL = None
_GRAVACOES: set[asyncio.Task] = set()
_PENDENTE = False
_REVISAO = 0
SQL_CREATE = """CREATE TABLE IF NOT EXISTS royal_giveaways (
    message_id BIGINT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""
SQL_UPSERT = """INSERT INTO royal_giveaways (message_id, payload)
    VALUES ($1, $2::jsonb) ON CONFLICT (message_id)
    DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()"""

CONFIG_PADRAO = {
    "canal_id": CANAL_SORTEIOS_ID,
    "duracao": "2h",
    "vencedores": 1,
    "dias_min": 0,
    "cargo_exigido": None,
    "cargo_bonus": None,
    "bonus_mult": 2,
    "ping": 0,
    "tema": "azul",
}
_CONFIG_CACHE: dict[int, dict] = {}
SQL_CONFIG = """CREATE TABLE IF NOT EXISTS royal_giveaway_settings (
    guild_id BIGINT PRIMARY KEY, payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now())"""
SQL_CONFIG_UPSERT = """INSERT INTO royal_giveaway_settings(guild_id, payload)
    VALUES($1,$2::jsonb) ON CONFLICT(guild_id) DO UPDATE
    SET payload=EXCLUDED.payload, updated_at=now()"""


def configuracao(guild_id: int) -> dict:
    return {**CONFIG_PADRAO, **_CONFIG_CACHE.get(int(guild_id), {})}


async def salvar_config(guild_id: int, novos: dict):
    atual = {**configuracao(guild_id), **novos}
    if _POOL is None:
        raise RuntimeError("PostgreSQL não conectado. Preferências não foram salvas.")
    await _POOL.execute(SQL_CONFIG_UPSERT, guild_id, json.dumps(atual, ensure_ascii=False))
    _CONFIG_CACHE[int(guild_id)] = atual
    return atual



def _ler_arquivo() -> dict:
    try:
        with open(F_SORTEIOS, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_local():
    try:
        os.makedirs(PASTA_DADOS, exist_ok=True)
        arquivo = F_SORTEIOS + ".tmp"
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump(_SORTEIOS_CACHE, f, ensure_ascii=False, indent=2)
        os.replace(arquivo, F_SORTEIOS)
    except OSError:
        LOG.exception("Não foi possível salvar o backup JSON dos sorteios")


_LOCKS: dict[int, asyncio.Lock] = {}


async def _gravar_postgres(msg_id: int, payload: dict):
    if _POOL is not None:
        lock = _LOCKS.setdefault(msg_id, asyncio.Lock())
        async with lock:
            try:
                # Sempre recuperar a versão mais recente; evita gravações antigas
                # sobrescreverem o resultado de uma interação mais nova.
                atual = _SORTEIOS_CACHE.get(str(msg_id), payload)
                await _POOL.execute(SQL_UPSERT, msg_id, json.dumps(atual, ensure_ascii=False))
            except Exception:
                LOG.exception("Erro ao persistir sorteio %s no PostgreSQL", msg_id)


def _salvar_pendente(g: dict):
    global _REVISAO
    _REVISAO += 1
    if _POOL is not None:
        try:
            tarefa = asyncio.get_running_loop().create_task(
                _gravar_postgres(int(g["mensagem"]), copy.deepcopy(g)))
            _GRAVACOES.add(tarefa)
            tarefa.add_done_callback(_GRAVACOES.discard)
        except RuntimeError:
            LOG.warning("Loop indisponível para persistir sorteio")


async def iniciar_armazenamento(bot: commands.Bot):
    global _POOL, _SORTEIOS_CACHE
    pool = getattr(bot, "pool", None)
    legado = _ler_arquivo()
    if pool is None:
        LOG.warning("PostgreSQL indisponível: usando arquivo local (não persistente no Railway sem volume)")
        _SORTEIOS_CACHE = legado
        return
    await pool.execute(SQL_CREATE)
    await pool.execute(SQL_CONFIG)
    for linha in await pool.fetch("SELECT guild_id, payload FROM royal_giveaway_settings"):
        dados = linha["payload"]
        _CONFIG_CACHE[int(linha["guild_id"])] = json.loads(dados) if isinstance(dados, str) else dados
    linhas = await pool.fetch("SELECT message_id, payload FROM royal_giveaways")
    if linhas:
        _SORTEIOS_CACHE = {
            str(r["message_id"]): json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
            for r in linhas
        }
        LOG.info("%d sorteios recuperados do PostgreSQL", len(_SORTEIOS_CACHE))
    else:
        _SORTEIOS_CACHE = legado
        for chave, payload in legado.items():
            await pool.execute(SQL_UPSERT, int(chave), json.dumps(payload, ensure_ascii=False))
        LOG.info("%d sorteios legados migrados do JSON", len(legado))
    _POOL = pool


async def aguardar_gravacoes():
    if _GRAVACOES:
        await asyncio.gather(*list(_GRAVACOES), return_exceptions=True)


def todos() -> dict:
    return _SORTEIOS_CACHE


def obter(msg_id) -> dict | None:
    return _SORTEIOS_CACHE.get(str(msg_id))


def salvar(g: dict):
    _SORTEIOS_CACHE[str(g["mensagem"])] = copy.deepcopy(g)
    _gravar_local()
    _salvar_pendente(g)


def sorteios_da_guild(guild_id: int) -> list[dict]:
    return [g for g in todos().values() if g.get("guild") == guild_id]

def eh_staff(membro) -> bool:
    if not isinstance(membro, discord.Member):
        return False
    if membro.guild_permissions.administrator:
        return True
    ids = {r.id for r in membro.roles}
    return any(c in ids for c in CARGOS_STAFF)


def apenas_staff():
    async def predicate(ctx: commands.Context):
        if eh_staff(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def parse_duracao(txt: str) -> int | None:
    """'1d12h', '2h30m', '45m', '90' (minutos) -> segundos. None se inválido."""
    txt = txt.lower().replace(" ", "")
    if not txt:
        return None
    if txt.isdigit():
        return int(txt) * 60
    if not re.fullmatch(r"(?:\d+[dhms])+", txt):
        return None
    unidades = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    total = sum(int(n) * unidades[u] for n, u in re.findall(r"(\d+)([dhms])", txt))
    return total or None


def formatar_duracao(seg: float) -> str:
    seg = int(seg)
    d, seg = divmod(seg, 86400)
    h, seg = divmod(seg, 3600)
    m, s = divmod(seg, 60)
    partes = []
    if d:
        partes.append(f"{d}d")
    if h:
        partes.append(f"{h}h")
    if m:
        partes.append(f"{m}min")
    if not partes and s:
        partes.append(f"{s}s")
    return " ".join(partes) or "<1s"


def banner_valido(url) -> bool:
    """True apenas para imagens hospedadas em HTTP(S)."""
    return isinstance(url, str) and url.startswith(("https://", "http://"))


def arquivo_banner(local: Path) -> Path | None:
    """Localiza o banner dentro de assets/, sem depender do diretório de execução."""
    if local.is_file():
        return local
    LOG.warning("Banner local não encontrado: %s", local)
    return None


def banner_sorteio(g: dict):
    """Retorna (referência de mídia, arquivo local opcional)."""
    personalizado = (g.get("banner") or "").strip()
    if banner_valido(personalizado):
        return personalizado, None
    local = arquivo_banner(BANNER_SORTEIO)
    if local:
        return f"attachment://{local.name}", local
    return None, None


def banner_painel():
    local = arquivo_banner(BANNER_PAINEL)
    if local:
        return f"attachment://{local.name}", local
    return None, None


async def enviar_painel_com_banner(canal, view):
    """Anexa o PNG ao painel V2 em sua primeira publicação."""
    _, local = banner_painel()
    if local:
        with local.open("rb") as imagem:
            return await canal.send(
                view=view,
                file=discord.File(imagem, filename=local.name),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    return await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none())


def destino_sorteios(guild: discord.Guild, fallback_id: int | None = None):
    """Canal onde o sorteio será publicado (canal fixo; senão, o canal atual)."""
    preferencias = configuracao(guild.id)
    for cid in dict.fromkeys((preferencias.get("canal_id"), CANAL_SORTEIOS_ID, fallback_id)):
        if cid:
            c = guild.get_channel(cid)
            if isinstance(c, discord.TextChannel):
                return c
    return None


def opcoes_ping(guild: discord.Guild) -> list[tuple[str, str | None]]:
    """[(rótulo do botão, texto enviado junto da mensagem)]"""
    opcoes: list[tuple[str, str | None]] = [("Sem ping", None)]
    if CARGO_PING_SORTEIOS_ID:
        cargo = guild.get_role(CARGO_PING_SORTEIOS_ID)
        if cargo:
            opcoes.append((f"@{cargo.name}"[:30], cargo.mention))
    opcoes += [("@here", "@here"), ("@everyone", "@everyone")]
    return opcoes


def link_sorteio(g: dict) -> str:
    return f"https://discord.com/channels/{g['guild']}/{g['canal']}/{g['mensagem']}"


def texto_requisitos(g: dict) -> list[str]:
    """Só lista o que realmente existe (sem requisitos = lista vazia)."""
    linhas = []
    if g.get("cargo_exigido"):
        linhas.append(f"🎖️ Cargo <@&{g['cargo_exigido']}>")
    if g.get("dias_min"):
        linhas.append(f"📅 {g['dias_min']}+ dias no servidor")
    if g.get("cargo_bonus"):
        linhas.append(
            f"✨ <@&{g['cargo_bonus']}> vale **x{g.get('bonus_mult', 2)}** entradas"
        )
    return linhas


def checar_requisitos(membro: discord.Member, g: dict) -> str | None:
    if g.get("cargo_exigido"):
        if not any(r.id == int(g["cargo_exigido"]) for r in membro.roles):
            return f"🎖️ Você precisa do cargo <@&{g['cargo_exigido']}> para participar."
    dias = int(g.get("dias_min") or 0)
    if dias and membro.joined_at:
        if (datetime.now(timezone.utc) - membro.joined_at).days < dias:
            return f"📅 Você precisa estar há **{dias}+ dias** no servidor para participar."
    return None


def calcular_entradas(membro: discord.Member, g: dict) -> int:
    if g.get("cargo_bonus") and any(r.id == int(g["cargo_bonus"]) for r in membro.roles):
        return int(g.get("bonus_mult", 2))
    return 1


async def registrar(guild: discord.Guild, titulo: str, descricao: str, cor=COR_AZUL):
    canal = guild.get_channel(CANAL_LOGS_SORTEIOS_ID) if CANAL_LOGS_SORTEIOS_ID else None
    if not canal:
        return
    try:
        await canal.send(
            embed=discord.Embed(
                title=titulo,
                description=descricao,
                color=cor,
                timestamp=datetime.now(FUSO),
            )
        )
    except discord.HTTPException:
        pass

def montar_embed(g: dict, *, preview: bool = False) -> discord.Embed:
    tema = TEMAS.get(g.get("tema", "azul"), TEMAS["azul"])
    status = g.get("status", "ativo")
    n_part = len(g.get("participantes", {}))
    desc = (g.get("descricao") or "").strip()

    if status == "cancelado":
        embed = discord.Embed(
            description=f"## 🚫 {g['premio']}\nEste sorteio foi cancelado pela equipe.",
            color=0x95A5A6,
        )
    else:
        topo = f"## {tema['emoji']} {g['premio']}"
        embed = discord.Embed(
            description=topo + (f"\n{desc}" if desc else ""),
            color=tema["cor"],
        )
        if status == "ativo":
            embed.add_field(
                name="⏳ Termina", value=f"<t:{int(g['fim_ts'])}:R>", inline=True
            )
            embed.add_field(
                name="🏆 Vencedores", value=f"**{g['vencedores']}**", inline=True
            )
            embed.add_field(name="👥 Participantes", value=f"**{n_part}**", inline=True)
            reqs = texto_requisitos(g)
            if reqs:
                embed.add_field(
                    name="📋 Requisitos", value="\n".join(reqs), inline=False
                )
        else:
            ganh = g.get("ganhadores", [])
            txt = ", ".join(f"<@{u}>" for u in ganh) if ganh else "Ninguém participou 😕"
            embed.add_field(name="🏆 Vencedor(es)", value=txt[:1024], inline=False)
            embed.add_field(name="👥 Participantes", value=f"**{n_part}**", inline=True)
            embed.add_field(
                name="⏱️ Encerrado",
                value=f"<t:{int(g.get('encerrado_ts', g['fim_ts']))}:R>",
                inline=True,
            )

    banner = (g.get("banner") or "").strip()
    if banner_valido(banner):
        embed.set_image(url=banner)

    rodape = NOME_SERVIDOR
    if g.get("host_nome"):
        rodape += f" • Patrocinado por {g['host_nome']}"
    if preview:
        rodape = "Pré-visualização • " + rodape
    embed.set_footer(text=rodape)
    return embed


def info_embed(g: dict) -> discord.Embed:
    """Resumo para a staff (aba Gerenciar)."""
    icones = {"ativo": "🟢 Ativo", "encerrado": "🏁 Encerrado", "cancelado": "🚫 Cancelado"}
    entradas = sum(int(n) for n in g.get("participantes", {}).values())
    ganh = g.get("ganhadores", [])
    linhas = [
        f"**Prêmio:** {g['premio']}",
        f"**Status:** {icones.get(g.get('status'), '—')}",
        f"**Canal:** <#{g['canal']}> • [ir ao sorteio]({link_sorteio(g)})",
        f"**Criado por:** <@{g['host']}>",
        f"**Vencedores:** {g['vencedores']}",
        f"**Participantes:** {len(g.get('participantes', {}))} ({entradas} entradas)",
    ]
    if g.get("status") == "ativo":
        linhas.append(f"**Termina:** <t:{int(g['fim_ts'])}:R>")
    if ganh:
        linhas.append("**Ganhadores:** " + ", ".join(f"<@{u}>" for u in ganh))
    linhas.append("\n**Requisitos**\n" + ("\n".join(texto_requisitos(g)) or "Nenhum"))
    e = discord.Embed(
        title="🛠️ Gerenciar Sorteio",
        description="\n".join(linhas)[:4096],
        color=COR_AZUL,
    )
    e.set_footer(text=f"ID {g['mensagem']}")
    return e

async def sortear(guild: discord.Guild, g: dict, qtd: int, excluir=()) -> list[int]:
    """Sorteio ponderado (entradas extras = mais chance), sem repetir vencedor,
    usando o gerador criptográfico do sistema. Ignora quem saiu do servidor."""
    ignorar = {int(x) for x in excluir}
    pool = {
        int(u): int(n)
        for u, n in g.get("participantes", {}).items()
        if int(u) not in ignorar
    }
    rng = random.SystemRandom()
    ganhadores: list[int] = []
    while pool and len(ganhadores) < qtd:
        ids = list(pool)
        escolhido = rng.choices(ids, weights=[pool[i] for i in ids], k=1)[0]
        pool.pop(escolhido)
        membro = guild.get_member(escolhido)
        if membro is None:
            try:
                membro = await guild.fetch_member(escolhido)
            except discord.HTTPException:
                membro = None
        if membro is not None:
            ganhadores.append(escolhido)
    return ganhadores


async def buscar_mensagem(bot: commands.Bot, g: dict) -> discord.Message | None:
    canal = bot.get_channel(int(g["canal"]))
    if canal is None:
        try:
            canal = await bot.fetch_channel(int(g["canal"]))
        except discord.HTTPException:
            return None
    try:
        return await canal.fetch_message(int(g["mensagem"]))
    except discord.HTTPException:
        return None


async def atualizar_mensagem(bot: commands.Bot, g: dict):
    msg = await buscar_mensagem(bot, g)
    if msg is None:
        return
    try:
        if msg.flags.value & (1 << 15):
            await msg.edit(view=montar_sorteio_v2(g), attachments=msg.attachments)
        else:
            await msg.edit(embed=montar_embed(g), view=SorteioView(encerrado=g.get("status") != "ativo"))
    except discord.HTTPException:
        LOG.exception("Falha ao atualizar sorteio %s", g.get("mensagem"))


async def anunciar(
    bot: commands.Bot,
    g: dict,
    msg: discord.Message | None,
    ganhadores: list[int],
    reroll: bool = False,
):
    canal = bot.get_channel(int(g["canal"]))
    if canal is None:
        return
    tema = TEMAS.get(g.get("tema", "azul"), TEMAS["azul"])
    if ganhadores:
        mencoes = ", ".join(f"<@{u}>" for u in ganhadores)
        titulo = "🔁 Novo(s) vencedor(es)!" if reroll else "🎊 Sorteio finalizado!"
        embed = discord.Embed(
            description=(
                f"## {titulo}\n"
                f"**Prêmio:** {g['premio']}\n"
                f"**Vencedor(es):** {mencoes}\n\n"
                f"{TEXTO_RESGATE}"
            ),
            color=tema["cor"],
        )
        content = mencoes
    else:
        embed = discord.Embed(
            description=(
                "## 😕 Sorteio sem vencedores\n"
                f"**Prêmio:** {g['premio']}\n"
                "Não havia participantes elegíveis."
            ),
            color=0x95A5A6,
        )
        content = None
    embed.set_footer(text=NOME_SERVIDOR)

    view = None
    if msg is not None:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ver sorteio", url=msg.jump_url))
    try:
        await canal.send(
            content=content,
            embed=embed,
            view=view,
            reference=msg if msg is not None else None,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
    except discord.HTTPException:
        pass

    if AVISAR_GANHADORES_DM and ganhadores:
        guild = canal.guild
        for uid in ganhadores:
            membro = guild.get_member(uid)
            if membro is None:
                continue
            dm = discord.Embed(
                title="🎉 Você ganhou!",
                description=(
                    f"Parabéns, **{membro.display_name}**!\n"
                    f"Você foi sorteado em **{NOME_SERVIDOR}**.\n\n"
                    f"> `🎁` Prêmio: **{g['premio']}**\n"
                    f"> `🔗` [Ver sorteio]({link_sorteio(g)})\n\n"
                    f"{TEXTO_RESGATE}"
                ),
                color=tema["cor"],
            )
            dm.set_footer(text=NOME_SERVIDOR)
            try:
                await membro.send(embed=dm)
            except (discord.Forbidden, discord.HTTPException):
                pass


async def publicar(
    bot: commands.Bot,
    guild: discord.Guild,
    canal: discord.TextChannel,
    base: dict,
    autor: discord.Member,
) -> discord.Message:
    g = dict(base)
    g.update(
        guild=guild.id,
        canal=canal.id,
        host=autor.id,
        host_nome=autor.display_name,
        status="ativo",
        participantes={},
        ganhadores=[],
        criado_ts=int(time.time()),
        fim_ts=int(time.time()) + int(base["duracao_seg"]),
    )
    opcoes = opcoes_ping(guild)
    ping = int(base.get("ping", 0))
    content = opcoes[ping][1] if 0 <= ping < len(opcoes) else None
    if content:
        await canal.send(content, allowed_mentions=discord.AllowedMentions(everyone=True, roles=True))
    _, imagem_local = banner_sorteio(g)
    if imagem_local:
        with imagem_local.open("rb") as imagem:
            msg = await canal.send(
                view=montar_sorteio_v2(g),
                file=discord.File(imagem, filename=imagem_local.name),
                allowed_mentions=discord.AllowedMentions.none(),
            )
    else:
        msg = await canal.send(view=montar_sorteio_v2(g), allowed_mentions=discord.AllowedMentions.none())
    g["mensagem"] = msg.id
    salvar(g)
    await registrar(
        guild,
        "🎁 Sorteio Criado",
        f"{autor.mention} criou **{g['premio']}** em {canal.mention}\n"
        f"**Termina:** <t:{g['fim_ts']}:R> • **Vencedores:** {g['vencedores']}\n"
        f"[Ir ao sorteio]({msg.jump_url})",
    )
    return msg


async def encerrar_sorteio(bot: commands.Bot, msg_id: int, quem=None) -> list[int] | None:
    g = obter(msg_id)
    if not g or g.get("status") != "ativo" or msg_id in ENCERRANDO:
        return None
    ENCERRANDO.add(msg_id)
    try:
        guild = bot.get_guild(int(g["guild"]))
        ganhadores = await sortear(guild, g, int(g["vencedores"])) if guild else []
        g["status"] = "encerrado"
        g["ganhadores"] = ganhadores
        g["encerrado_ts"] = int(time.time())
        salvar(g)
        SUJOS.discard(msg_id)

        msg = await buscar_mensagem(bot, g)
        if msg is not None:
            try:
                await atualizar_mensagem(bot, g)
            except discord.HTTPException:
                pass
        await anunciar(bot, g, msg, ganhadores)

        if guild:
            por = quem.mention if quem else "automaticamente"
            await registrar(
                guild,
                "🏁 Sorteio Encerrado",
                f"**{g['premio']}** foi encerrado {por}.\n"
                f"**Ganhadores:** "
                + (", ".join(f"<@{u}>" for u in ganhadores) or "ninguém")
                + f"\n[Ir ao sorteio]({link_sorteio(g)})",
            )
        return ganhadores
    finally:
        ENCERRANDO.discard(msg_id)


async def cancelar_sorteio(bot: commands.Bot, msg_id: int, quem=None) -> bool:
    g = obter(msg_id)
    if not g or g.get("status") != "ativo":
        return False
    g["status"] = "cancelado"
    g["encerrado_ts"] = int(time.time())
    salvar(g)
    SUJOS.discard(msg_id)
    await atualizar_mensagem(bot, g)
    guild = bot.get_guild(int(g["guild"]))
    if guild:
        por = quem.mention if quem else "o sistema"
        await registrar(
            guild,
            "🚫 Sorteio Cancelado",
            f"**{g['premio']}** foi cancelado por {por}.",
            0xE74C3C,
        )
    return True


async def rerolar_sorteio(bot: commands.Bot, msg_id: int, quem=None, qtd: int = 1) -> list[int]:
    g = obter(msg_id)
    if not g or g.get("status") != "encerrado":
        return []
    guild = bot.get_guild(int(g["guild"]))
    if not guild:
        return []
    novos = await sortear(guild, g, qtd, excluir=g.get("ganhadores", []))
    if not novos:
        return []
    g["ganhadores"] = list(g.get("ganhadores", [])) + novos
    salvar(g)
    msg = await buscar_mensagem(bot, g)
    if msg is not None:
        try:
            await atualizar_mensagem(bot, g)
        except discord.HTTPException:
            pass
    await anunciar(bot, g, msg, novos, reroll=True)
    por = quem.mention if quem else "o sistema"
    await registrar(
        guild,
        "🔁 Reroll de Sorteio",
        f"{por} rerolou **{g['premio']}**\n"
        f"**Novo(s):** {', '.join(f'<@{u}>' for u in novos)}",
    )
    return novos


class RoyalSorteioBotao(discord.ui.Button):
    def __init__(self, acao: str, encerrado: bool = False):
        super().__init__(
            label={"entrar": "Participar", "lista": "Participantes"}[acao],
            emoji={"entrar": "🎟️", "lista": "👥"}[acao],
            style=discord.ButtonStyle.success if acao == "entrar" else discord.ButtonStyle.secondary,
            custom_id=f"royal:sorteio:{acao}:v1",
            disabled=encerrado and acao == "entrar",
        )
        self.acao = acao

    async def callback(self, interaction: discord.Interaction):
        if self.acao == "entrar":
            await entrar_royal(interaction)
        else:
            await participantes_royal(interaction)


class RoyalSorteioView(discord.ui.LayoutView):
    def __init__(self, g: dict | None = None):
        super().__init__(timeout=None)
        if g is None:
            g = {"premio": "Sorteio Royal", "vencedores": 1, "fim_ts": 0,
                 "participantes": {}, "status": "ativo"}
        self.add_item(_container_sorteio(g))


def _container_sorteio(g: dict) -> discord.ui.Container:
    status = g.get("status", "ativo")
    banner, _ = banner_sorteio(g)
    componentes = []
    if banner:
        componentes.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner)))
    if status == "ativo":
        descricao = [
            f"## <a:Presenteghost:1553872045492797550> {str(g.get('premio', 'Sorteio Royal'))[:120]}",
            f"{str(g.get('descricao') or '').strip()[:700]}",
            f"> `⏳` Encerramento: <t:{int(g.get('fim_ts', 0))}:R>",
            f"> `🏆` Vencedores: **{g.get('vencedores', 1)}**",
            f"> `👥` Participantes: **{len(g.get('participantes', {}))}**",
        ]
        reqs = texto_requisitos(g)
        if reqs:
            descricao += ["", "**⚜️ CONDIÇÕES DE PARTICIPAÇÃO**"] + [f"> {r}" for r in reqs]
        descricao += ["", "-# <a:coroa:1564000189167960177> Família Royal • Boa sorte a todos!!"]
    else:
        descricao = [
            f"## {'<a:coroa:1564000189167960177> SORTEIO ENCERRADO' if status == 'encerrado' else '🚫 SORTEIO CANCELADO'}",
            f"**{g.get('premio', 'Sorteio Royal')}**",
        ]
        if status == "encerrado":
            nomes = ", ".join(f"<@{uid}>" for uid in g.get("ganhadores", [])) or "Nenhum participante elegível"
            descricao.append(f"> `🏆` Vencedores: {nomes}")
    componentes.append(discord.ui.TextDisplay("\n".join(x for x in descricao if x is not None)[:3600]))
    componentes.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    componentes.append(discord.ui.ActionRow(
        RoyalSorteioBotao("entrar", encerrado=status != "ativo"),
        RoyalSorteioBotao("lista", encerrado=False),
    ))
    return discord.ui.Container(*componentes, accent_colour=discord.Colour(COR_AZUL))


def montar_sorteio_v2(g: dict) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(_container_sorteio(g))
    return view


async def entrar_royal(interaction: discord.Interaction):
    g = obter(interaction.message.id)
    if not g or g.get("status") != "ativo" or time.time() >= int(g["fim_ts"]):
        return await interaction.response.send_message("⚠️ Este sorteio não aceita novas entradas.", ephemeral=True)
    membro = interaction.user
    if not isinstance(membro, discord.Member):
        return await interaction.response.send_message("❌ Participe pelo servidor.", ephemeral=True)
    erro = checar_requisitos(membro, g)
    if erro:
        return await interaction.response.send_message(erro, ephemeral=True)
    uid = str(membro.id)
    participantes = g.setdefault("participantes", {})
    if uid in participantes:
        return await interaction.response.send_message(
            "✅ Você já participa deste sorteio. Para desistir, use o botão abaixo.",
            view=SairView(interaction.message.id), ephemeral=True)
    entradas = calcular_entradas(membro, g)
    participantes[uid] = entradas
    salvar(g)
    SUJOS.add(interaction.message.id)
    return await interaction.response.send_message(
        f"✅ Participação confirmada! Você possui **{entradas}** entrada(s). Boa sorte!",
        ephemeral=True)


async def participantes_royal(interaction: discord.Interaction):
    g = obter(interaction.message.id)
    if not g:
        return await interaction.response.send_message("⚠️ Sorteio não encontrado.", ephemeral=True)
    participantes = g.get("participantes", {})
    valor = participantes.get(str(interaction.user.id), 0)
    texto = f"**Participantes:** {len(participantes)}\n**Sua situação:** " + (
        f"participando com {valor} entrada(s)" if valor else "não está participando")
    if eh_staff(interaction.user) and participantes:
        texto += "\n\n**Inscritos (equipe):**\n" + "\n".join(
            f"• <@{uid}>" for uid in list(participantes)[:40])
    return await interaction.response.send_message(texto[:1900], ephemeral=True)



class SairView(discord.ui.View):
    def __init__(self, msg_id: int):
        super().__init__(timeout=120)
        self.msg_id = msg_id

    @discord.ui.button(label="Sair do sorteio", emoji="🚪", style=discord.ButtonStyle.danger)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = obter(self.msg_id)
        if not g or g.get("status") != "ativo":
            return await interaction.response.edit_message(
                content="⚠️ Este sorteio já foi encerrado.", embed=None, view=None
            )
        g.get("participantes", {}).pop(str(interaction.user.id), None)
        salvar(g)
        SUJOS.add(self.msg_id)
        await interaction.response.edit_message(
            content="🚪 Você saiu do sorteio. Pode voltar a participar quando quiser!",
            embed=None,
            view=None,
        )


class SorteioView(discord.ui.View):
    def __init__(self, encerrado: bool = False):
        super().__init__(timeout=None)
        if encerrado:
            for item in self.children:
                item.disabled = True

    @discord.ui.button(
        label="Participar",
        emoji="<:ImagemdoChatGPT25deoutde202615_4:1563986790753378424>",
        style=discord.ButtonStyle.success,
        custom_id="sants_sorteio_entrar",
    )
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = obter(interaction.message.id)
        if not g or g.get("status") != "ativo" or time.time() >= int(g["fim_ts"]):
            return await interaction.response.send_message(
                "⚠️ Este sorteio já foi encerrado.", ephemeral=True
            )
        membro = interaction.user
        if not isinstance(membro, discord.Member):
            return await interaction.response.send_message(
                "❌ Use dentro do servidor.", ephemeral=True
            )

        erro = checar_requisitos(membro, g)
        if erro:
            return await interaction.response.send_message(erro, ephemeral=True)

        uid = str(membro.id)
        participantes = g.setdefault("participantes", {})
        if uid in participantes:
            return await interaction.response.send_message(
                "✅ Você **já está participando**! Quer sair?",
                view=SairView(interaction.message.id),
                ephemeral=True,
            )

        entradas = calcular_entradas(membro, g)
        participantes[uid] = entradas
        salvar(g)
        SUJOS.add(interaction.message.id)

        total = sum(int(n) for n in participantes.values())
        chance = None  
        extra = " ✨ (bônus de cargo!)" if entradas > 1 else ""
        embed = discord.Embed(
            description=(
                "**🎉 Você está dentro!**\n"
                f"> `🎟️` Suas entradas: **{entradas}**{extra}\n"
                f"> `👥` Participantes agora: **{len(participantes)}**\n"
                "\n"
                "*Boa sorte!* ⚜️"
            ),
            color=TEMAS.get(g.get("tema", "azul"), TEMAS["azul"])["cor"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Participantes",
        emoji="👥",
        style=discord.ButtonStyle.secondary,
        custom_id="sants_sorteio_lista",
    )
    async def lista(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = obter(interaction.message.id)
        if not g:
            return await interaction.response.send_message(
                "⚠️ Sorteio não encontrado.", ephemeral=True
            )
        participantes = g.get("participantes", {})
        dentro = str(interaction.user.id) in participantes
        linhas = [
            f"**Participantes:** {len(participantes)}",
            "**Você:** "
            + (
                f"✅ participando ({participantes[str(interaction.user.id)]} entrada(s))"
                if dentro
                else "❌ ainda não entrou"
            ),
        ]
        if eh_staff(interaction.user) and participantes:
            lista = "\n".join(
                f"• <@{u}>" + (f" x{n}" if int(n) > 1 else "")
                for u, n in list(participantes.items())[:60]
            )
            linhas.append("\n**Lista (staff)**\n" + lista)
            if len(participantes) > 60:
                linhas.append(f"*+{len(participantes) - 60} não exibido(s)*")
        embed = discord.Embed(description="\n".join(linhas)[:4096], color=COR_AZUL)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class CriarView(discord.ui.View):
    """Tela de opções com pré-visualização ao vivo."""

    def __init__(self, bot, autor: discord.Member, fallback_id: int | None, dados: dict):
        super().__init__(timeout=900)
        self.bot = bot
        self.autor = autor
        self.fallback_id = fallback_id
        self.dados = dados
        conf = configuracao(autor.guild.id)
        self.cargo_exigido: int | None = conf.get("cargo_exigido")
        self.cargo_bonus: int | None = conf.get("cargo_bonus")
        self.bonus_mult = int(conf.get("bonus_mult", 2))
        self.dias_min = int(conf.get("dias_min", 0))
        self.tema = conf.get("tema", "azul") if conf.get("tema") in TEMAS else "azul"
        self.ping = int(conf.get("ping", 0))
        self._atualizar_botoes()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.autor.id:
            return True
        await interaction.response.send_message(
            "❌ Só quem iniciou a criação pode mexer aqui.", ephemeral=True
        )
        return False

    def montar_dados(self) -> dict:
        g = dict(self.dados)
        g.update(
            tema=self.tema,
            ping=self.ping,
            cargo_exigido=self.cargo_exigido,
            cargo_bonus=self.cargo_bonus,
            bonus_mult=self.bonus_mult,
            dias_min=self.dias_min,
        )
        return g

    def embed_preview(self) -> discord.Embed:
        g = self.montar_dados()
        g.update(
            status="ativo",
            host=self.autor.id,
            host_nome=self.autor.display_name,
            participantes={},
            fim_ts=int(time.time()) + int(g["duracao_seg"]),
        )
        return montar_embed(g, preview=True)

    def _atualizar_botoes(self):
        opcoes = opcoes_ping(self.autor.guild)
        self.ping %= len(opcoes)
        self.btn_tema.label = f"Tema: {TEMAS[self.tema]['nome']}"
        self.btn_ping.label = opcoes[self.ping][0]
        self.btn_bonus.label = f"Bônus: x{self.bonus_mult}"
        self.btn_bonus.disabled = self.cargo_bonus is None

    async def _refresh(self, interaction: discord.Interaction):
        self._atualizar_botoes()
        await interaction.response.edit_message(
            content=self._texto_topo(), embed=self.embed_preview(), view=self
        )

    def _texto_topo(self) -> str:
        canal = destino_sorteios(self.autor.guild, self.fallback_id)
        destino = canal.mention if canal else "**canal não configurado**"
        return (
            "🧪 **Pré-visualização** — ajuste as opções e clique em **Publicar**.\n"
            f"📢 Será publicado em {destino} • "
            f"⏱️ Duração: **{formatar_duracao(self.dados['duracao_seg'])}**"
        )

    # ── Linha 0: cargo obrigatório ──
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="🎖️ Cargo obrigatório (opcional)",
        min_values=0,
        max_values=1,
        row=0,
    )
    async def sel_cargo(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.cargo_exigido = select.values[0].id if select.values else None
        await self._refresh(interaction)

    # ── Linha 1: cargo com bônus ──
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="✨ Cargo com bônus de entradas (opcional)",
        min_values=0,
        max_values=1,
        row=1,
    )
    async def sel_bonus(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.cargo_bonus = select.values[0].id if select.values else None
        await self._refresh(interaction)

    # ── Linha 2: tempo mínimo no servidor ──
    @discord.ui.select(
        placeholder="📅 Tempo mínimo no servidor",
        row=2,
        options=[
            discord.SelectOption(label=nome, value=str(dias), emoji="📅")
            for dias, nome in DIAS_OPCOES
        ],
    )
    async def sel_dias(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.dias_min = int(select.values[0])
        await self._refresh(interaction)

    # ── Linha 3: botões ──
    @discord.ui.button(label="Tema", emoji="🎨", style=discord.ButtonStyle.secondary, row=3)
    async def btn_tema(self, interaction: discord.Interaction, button: discord.ui.Button):
        chaves = list(TEMAS)
        self.tema = chaves[(chaves.index(self.tema) + 1) % len(chaves)]
        await self._refresh(interaction)

    @discord.ui.button(label="Sem ping", emoji="🔔", style=discord.ButtonStyle.secondary, row=3)
    async def btn_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.ping = (self.ping + 1) % len(opcoes_ping(self.autor.guild))
        await self._refresh(interaction)

    @discord.ui.button(label="Bônus: x2", emoji="✨", style=discord.ButtonStyle.secondary, row=3)
    async def btn_bonus(self, interaction: discord.Interaction, button: discord.ui.Button):
        i = BONUS_OPCOES.index(self.bonus_mult)
        self.bonus_mult = BONUS_OPCOES[(i + 1) % len(BONUS_OPCOES)]
        await self._refresh(interaction)

    @discord.ui.button(label="Publicar", emoji="🚀", style=discord.ButtonStyle.success, row=3)
    async def btn_publicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = destino_sorteios(interaction.guild, self.fallback_id)
        if canal is None:
            return await interaction.response.send_message(
                "❌ Não encontrei o canal de sorteios. "
                "Defina o canal em `!painelconfigsorteio`.",
                ephemeral=True,
            )
        perms = canal.permissions_for(interaction.guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            return await interaction.response.send_message(
                f"❌ Não tenho permissão para enviar embeds em {canal.mention}.",
                ephemeral=True,
            )
        await interaction.response.defer()
        try:
            msg = await publicar(
                self.bot, interaction.guild, canal, self.montar_dados(), self.autor
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(
                f"❌ Não consegui publicar ({e.text}).", ephemeral=True
            )
        await interaction.edit_original_response(
            content=f"✅ Sorteio publicado em {canal.mention}: {msg.jump_url}",
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=3)
    async def btn_cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Criação cancelada.", embed=None, view=None
        )
        self.stop()


class CriarModal(discord.ui.Modal, title="🎁 Novo Sorteio"):
    premio = discord.ui.TextInput(
        label="Prêmio",
        placeholder="Ex: Nitro Classic, 100 reais, Cargo VIP...",
        max_length=100,
    )
    duracao = discord.ui.TextInput(
        label="Duração",
        placeholder="Ex: 30m, 2h, 1d, 1d12h",
        max_length=20,
    )
    vencedores = discord.ui.TextInput(
        label="Quantidade de vencedores",
        default="1",
        max_length=2,
    )
    descricao = discord.ui.TextInput(
        label="Descrição (opcional)",
        style=discord.TextStyle.paragraph,
        placeholder="Regras, detalhes, agradecimentos ao patrocinador...",
        required=False,
        max_length=400,
    )
    banner = discord.ui.TextInput(
        label="Banner próprio (opcional)",
        placeholder="Vazio = usa o banner padrão dos sorteios",
        required=False,
        max_length=400,
    )

    def __init__(self, bot, guild_id: int | None = None):
        super().__init__(timeout=600)
        self.bot = bot
        conf = configuracao(guild_id) if guild_id else CONFIG_PADRAO
        self.duracao.default = str(conf.get("duracao", "2h"))
        self.vencedores.default = str(conf.get("vencedores", 1))

    async def on_submit(self, interaction: discord.Interaction):
        seg = parse_duracao(str(self.duracao))
        if seg is None or not (DURACAO_MIN <= seg <= DURACAO_MAX):
            return await interaction.response.send_message(
                "❌ Duração inválida. Use algo como `30m`, `2h`, `1d` ou `1d12h` "
                f"(mínimo 1 minuto, máximo {DURACAO_MAX // 86400} dias).",
                ephemeral=True,
            )
        try:
            qtd = int(str(self.vencedores).strip())
            if not (1 <= qtd <= MAX_VENCEDORES):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                f"❌ Vencedores deve ser um número de 1 a {MAX_VENCEDORES}.",
                ephemeral=True,
            )
        banner = str(self.banner).strip()
        if banner and not banner_valido(banner):
            return await interaction.response.send_message(
                "❌ O link da imagem precisa começar com `http`.", ephemeral=True
            )

        dados = {
            "premio": str(self.premio).strip(),
            "descricao": str(self.descricao).strip(),
            "banner": banner,
            "vencedores": qtd,
            "duracao_seg": seg,
        }
        atual = interaction.channel
        fallback = atual.id if isinstance(atual, discord.TextChannel) else None
        view = CriarView(self.bot, interaction.user, fallback, dados)
        await interaction.response.send_message(
            content=view._texto_topo(),
            embed=view.embed_preview(),
            view=view,
            ephemeral=True,
        )

class RelampagoModal(discord.ui.Modal, title="⚡ Sorteio Relâmpago"):
    premio = discord.ui.TextInput(label="Prêmio", max_length=100)
    duracao = discord.ui.TextInput(
        label="Duração", default="10m", placeholder="Ex: 5m, 30m, 1h", max_length=20
    )
    vencedores = discord.ui.TextInput(
        label="Quantidade de vencedores", default="1", max_length=2
    )

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        atual = interaction.channel
        fallback = atual.id if isinstance(atual, discord.TextChannel) else None
        canal = destino_sorteios(interaction.guild, fallback)
        if canal is None:
            return await interaction.response.send_message(
                "❌ Não encontrei o canal de sorteios. "
                "Defina o canal em `!painelconfigsorteio`.",
                ephemeral=True,
            )
        perms = canal.permissions_for(interaction.guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            return await interaction.response.send_message(
                f"❌ Não tenho permissão para enviar embeds em {canal.mention}.",
                ephemeral=True,
            )
        seg = parse_duracao(str(self.duracao))
        if seg is None or not (DURACAO_MIN <= seg <= DURACAO_MAX):
            return await interaction.response.send_message(
                "❌ Duração inválida. Use algo como `5m`, `30m` ou `1h`.", ephemeral=True
            )
        try:
            qtd = int(str(self.vencedores).strip())
            if not (1 <= qtd <= MAX_VENCEDORES):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                f"❌ Vencedores deve ser um número de 1 a {MAX_VENCEDORES}.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        base = {
            "premio": str(self.premio).strip(),
            "descricao": "",
            "banner": "",
            "vencedores": qtd,
            "duracao_seg": seg,
            "tema": "neon",
            "ping": configuracao(interaction.guild.id).get("ping", 0),
            "cargo_exigido": configuracao(interaction.guild.id).get("cargo_exigido"),
            "cargo_bonus": configuracao(interaction.guild.id).get("cargo_bonus"),
            "bonus_mult": configuracao(interaction.guild.id).get("bonus_mult", 2),
            "dias_min": configuracao(interaction.guild.id).get("dias_min", 0),
        }
        try:
            msg = await publicar(self.bot, interaction.guild, canal, base, interaction.user)
        except discord.HTTPException as e:
            return await interaction.followup.send(
                f"❌ Não consegui publicar ({e.text}).", ephemeral=True
            )
        await interaction.followup.send(
            f"⚡ Relâmpago no ar em {canal.mention}: {msg.jump_url}", ephemeral=True
        )


class GerenciarView(discord.ui.View):
    def __init__(self, bot, g: dict):
        super().__init__(timeout=600)
        self.bot = bot
        self.msg_id = int(g["mensagem"])
        self.confirmar_cancelar = False
        status = g.get("status")

        if status == "ativo":
            b = discord.ui.Button(label="Encerrar agora", emoji="🏁", style=discord.ButtonStyle.success)
            b.callback = self.cb_encerrar
            self.add_item(b)
            self.btn_cancelar = discord.ui.Button(
                label="Cancelar sorteio", emoji="🗑️", style=discord.ButtonStyle.danger
            )
            self.btn_cancelar.callback = self.cb_cancelar
            self.add_item(self.btn_cancelar)
        elif status == "encerrado":
            b = discord.ui.Button(label="Rerolar (+1 vencedor)", emoji="🔁", style=discord.ButtonStyle.primary)
            b.callback = self.cb_rerolar
            self.add_item(b)

        b = discord.ui.Button(label="Participantes", emoji="👥", style=discord.ButtonStyle.secondary)
        b.callback = self.cb_participantes
        self.add_item(b)
        self.add_item(discord.ui.Button(label="Ir ao sorteio", url=link_sorteio(g)))

    async def _recarregar(self, interaction: discord.Interaction):
        g = obter(self.msg_id)
        if not g:
            return await interaction.edit_original_response(
                content="⚠️ Sorteio não encontrado.", embed=None, view=None
            )
        await interaction.edit_original_response(
            embed=info_embed(g), view=GerenciarView(self.bot, g)
        )

    async def cb_encerrar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await encerrar_sorteio(self.bot, self.msg_id, interaction.user)
        await self._recarregar(interaction)

    async def cb_cancelar(self, interaction: discord.Interaction):
        if not self.confirmar_cancelar:
            self.confirmar_cancelar = True
            self.btn_cancelar.label = "Clique de novo para confirmar"
            return await interaction.response.edit_message(view=self)
        await interaction.response.defer()
        await cancelar_sorteio(self.bot, self.msg_id, interaction.user)
        await self._recarregar(interaction)

    async def cb_rerolar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        novos = await rerolar_sorteio(self.bot, self.msg_id, interaction.user, 1)
        await self._recarregar(interaction)
        if not novos:
            await interaction.followup.send(
                "😕 Não há mais participantes elegíveis para rerolar.", ephemeral=True
            )

    async def cb_participantes(self, interaction: discord.Interaction):
        g = obter(self.msg_id)
        participantes = (g or {}).get("participantes", {})
        if not participantes:
            return await interaction.response.send_message(
                "📭 Ninguém participou ainda.", ephemeral=True
            )
        lista = "\n".join(
            f"• <@{u}>" + (f" x{n}" if int(n) > 1 else "")
            for u, n in list(participantes.items())[:80]
        )
        if len(participantes) > 80:
            lista += f"\n*+{len(participantes) - 80} não exibido(s)*"
        embed = discord.Embed(
            title=f"👥 Participantes ({len(participantes)})",
            description=lista[:4096],
            color=COR_AZUL,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class GerenciarSelectView(discord.ui.View):
    def __init__(self, bot, itens: list[dict]):
        super().__init__(timeout=300)
        self.bot = bot
        icones = {"ativo": "🟢", "encerrado": "🏁", "cancelado": "🚫"}
        opcoes = [
            discord.SelectOption(
                label=f"{g['premio']}"[:100],
                value=str(g["mensagem"]),
                description=(
                    f"{g.get('status', '—')} • {len(g.get('participantes', {}))} part. "
                    f"• ID {g['mensagem']}"
                )[:100],
                emoji=icones.get(g.get("status"), "🎁"),
            )
            for g in itens[:25]
        ]
        sel = discord.ui.Select(placeholder="🎁 Escolha um sorteio...", options=opcoes)
        sel.callback = self.escolher
        self.add_item(sel)

    async def escolher(self, interaction: discord.Interaction):
        msg_id = int(interaction.data["values"][0])
        g = obter(msg_id)
        if not g:
            return await interaction.response.edit_message(
                content="⚠️ Sorteio não encontrado.", embed=None, view=None
            )
        await interaction.response.edit_message(
            content=None, embed=info_embed(g), view=GerenciarView(self.bot, g)
        )


def linhas_ativos(guild: discord.Guild, limite: int = 5) -> list[str]:
    ativos = [g for g in sorteios_da_guild(guild.id) if g.get("status") == "ativo"]
    ativos.sort(key=lambda g: g["fim_ts"])
    linhas = []
    for g in ativos[:limite]:
        tema = TEMAS.get(g.get("tema", "azul"), TEMAS["azul"])
        linhas.append(
            f"{tema['emoji']} [{g['premio'][:40]}]({link_sorteio(g)}) • "
            f"<t:{int(g['fim_ts'])}:R> • 👥 {len(g.get('participantes', {}))}"
        )
    if len(ativos) > limite:
        linhas.append(f"*+{len(ativos) - limite} outro(s)*")
    return linhas


def embed_estatisticas(guild: discord.Guild) -> discord.Embed:
    lista = sorteios_da_guild(guild.id)
    ativos = [g for g in lista if g.get("status") == "ativo"]
    encerrados = [g for g in lista if g.get("status") == "encerrado"]
    cancelados = [g for g in lista if g.get("status") == "cancelado"]

    unicos: set[str] = set()
    total_part = 0
    total_ganhadores = 0
    for g in lista:
        parts = g.get("participantes", {})
        total_part += len(parts)
        unicos.update(parts.keys())
        total_ganhadores += len(g.get("ganhadores", []))

    maior = max(lista, key=lambda g: len(g.get("participantes", {})), default=None)
    media = total_part / len(lista) if lista else 0

    embed = discord.Embed(title=f"📊 Estatísticas — {NOME_SERVIDOR}", color=COR_AZUL)
    embed.add_field(name="🎁 Sorteios (registrados)", value=str(len(lista)), inline=True)
    embed.add_field(name="🟢 Ativos agora", value=str(len(ativos)), inline=True)
    embed.add_field(name="🏁 Encerrados", value=str(len(encerrados)), inline=True)
    embed.add_field(name="🚫 Cancelados", value=str(len(cancelados)), inline=True)
    embed.add_field(name="🏆 Vencedores", value=str(total_ganhadores), inline=True)
    embed.add_field(name="🙋 Pessoas diferentes", value=str(len(unicos)), inline=True)
    embed.add_field(name="👥 Média por sorteio", value=f"{media:.1f}", inline=True)
    ativos_txt = linhas_ativos(guild)
    embed.add_field(
        name="🟢 Rolando agora",
        value="\n".join(ativos_txt) if ativos_txt else "Nenhum sorteio ativo.",
        inline=False,
    )
    if maior and maior.get("participantes"):
        embed.add_field(
            name="🔥 Mais disputado",
            value=(
                f"[{maior['premio']}]({link_sorteio(maior)}) — "
                f"{len(maior['participantes'])} participantes"
            ),
            inline=False,
        )
    return embed

class ConfiguracaoModal(discord.ui.Modal, title="Padrões dos próximos sorteios"):
    duracao = discord.ui.TextInput(label="Duração padrão", placeholder="Ex.: 2h ou 1d", max_length=20)
    vencedores = discord.ui.TextInput(label="Vencedores padrão", max_length=2)
    dias = discord.ui.TextInput(label="Dias mínimos no servidor", max_length=4)
    bonus = discord.ui.TextInput(label="Entradas do cargo bônus (2, 3 ou 5)", max_length=1)

    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        conf = configuracao(guild_id)
        self.duracao.default = str(conf["duracao"])
        self.vencedores.default = str(conf["vencedores"])
        self.dias.default = str(conf["dias_min"])
        self.bonus.default = str(conf["bonus_mult"])

    async def on_submit(self, interaction: discord.Interaction):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message("Acesso restrito.", ephemeral=True)
        seg = parse_duracao(str(self.duracao))
        try:
            qtd = int(str(self.vencedores))
            dias = int(str(self.dias))
            bonus = int(str(self.bonus))
            assert seg and DURACAO_MIN <= seg <= DURACAO_MAX
            assert 1 <= qtd <= MAX_VENCEDORES and 0 <= dias <= 3650
            assert bonus in BONUS_OPCOES
        except (ValueError, AssertionError):
            return await interaction.response.send_message(
                "Valores inválidos. Duração mínima: 1min; vencedores: 1–10; "
                "dias: 0–3650; bônus: 2, 3 ou 5.", ephemeral=True)
        try:
            await salvar_config(self.guild_id, {
                "duracao": str(self.duracao).strip(), "vencedores": qtd,
                "dias_min": dias, "bonus_mult": bonus})
        except Exception:
            LOG.exception("Falha ao salvar padrões de sorteio")
            return await interaction.response.send_message("Não foi possível salvar no PostgreSQL.", ephemeral=True)
        await interaction.response.send_message("✅ Padrões atualizados para os próximos sorteios.", ephemeral=True)


class ConfigSelectView(discord.ui.View):
    """Configuração privada; cada seletor abre somente ao administrador."""
    def __init__(self, guild_id: int):
        super().__init__(timeout=240)
        self.guild_id = guild_id
        canal = discord.ui.ChannelSelect(
            placeholder="Selecionar canal dos próximos sorteios",
            channel_types=[discord.ChannelType.text], min_values=1, max_values=1)
        cargo = discord.ui.RoleSelect(placeholder="Cargo obrigatório (opcional)", min_values=0, max_values=1)
        bonus = discord.ui.RoleSelect(placeholder="Cargo com bônus (opcional)", min_values=0, max_values=1)
        canal.callback = self.canal_cb
        cargo.callback = self.cargo_cb
        bonus.callback = self.bonus_cb
        self.canal_sel, self.cargo_sel, self.bonus_sel = canal, cargo, bonus
        self.add_item(canal); self.add_item(cargo); self.add_item(bonus)

    async def interaction_check(self, interaction):
        if interaction.guild_id == self.guild_id and eh_staff(interaction.user):
            return True
        await interaction.response.send_message("⛔ Acesso restrito à equipe.", ephemeral=True)
        return False

    async def _salvar(self, interaction, dados):
        try:
            await salvar_config(self.guild_id, dados)
        except Exception:
            LOG.exception("Falha ao atualizar configuração dos sorteios")
            return await interaction.response.send_message("Falha ao salvar no PostgreSQL.", ephemeral=True)
        await interaction.response.send_message("✅ Configuração salva para futuros sorteios.", ephemeral=True)

    async def canal_cb(self, interaction):
        await self._salvar(interaction, {"canal_id": self.canal_sel.values[0].id})

    async def cargo_cb(self, interaction):
        await self._salvar(interaction, {"cargo_exigido": self.cargo_sel.values[0].id if self.cargo_sel.values else None})

    async def bonus_cb(self, interaction):
        await self._salvar(interaction, {"cargo_bonus": self.bonus_sel.values[0].id if self.bonus_sel.values else None})


class PainelConfigRoyal(discord.ui.LayoutView):
    """Painel administrativo V2, independente do painel de criação."""
    def __init__(self):
        super().__init__(timeout=None)
        elementos = []
        media, _ = banner_painel()
        if media:
            elementos.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=media)))
        elementos.append(discord.ui.TextDisplay(
            "## <a:coroa:1564000189167960177> CONFIGURAÇÕES DOS SORTEIOS\n"
            "Defina os padrões utilizados nas próximas premiações. "
            "Sorteios em andamento não serão modificados.\n\n"
            "> `⚙️` **Padrões** — duração, ganhadores e requisitos\n"
            "> `🏰` **Canal e cargos** — local da publicação e elegibilidade\n"
            "> `🔔` **Avisos** — menções e identidade visual\n"
            "> `📋` **Consultar** — confira as definições atuais"))
        elementos.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        linha = []
        for acao, rotulo, emoji in (
            ("padroes", "Padrões", "⚙️"), ("canais", "Canal e cargos", "🏰"),
            ("avisos", "Avisos", "🔔"), ("consultar", "Consultar", "📋"),
        ):
            botao = discord.ui.Button(label=rotulo, emoji=emoji,
                  style=discord.ButtonStyle.secondary,
                  custom_id=f"royal:sorteio:config:{acao}:v1")
            async def cb(interaction, escolha=acao):
                if not interaction.guild or not eh_staff(interaction.user):
                    return await interaction.response.send_message("⛔ Acesso exclusivo da equipe.", ephemeral=True)
                gid = interaction.guild.id
                if escolha == "padroes":
                    return await interaction.response.send_modal(ConfiguracaoModal(gid))
                if escolha == "canais":
                    return await interaction.response.send_message(
                        "<a:coroa:1564000189167960177> **Canal e requisitos** — selecione as opções abaixo.",
                        view=ConfigSelectView(gid), ephemeral=True)
                if escolha == "avisos":
                    return await interaction.response.send_message(
                        "**Avisos e tema para novos sorteios**", view=ConfigAvisosView(gid), ephemeral=True)
                conf = configuracao(gid)
                canal = f"<#{conf['canal_id']}>" if conf.get('canal_id') else "Padrão do servidor"
                return await interaction.response.send_message(
                    "**⚜️ CONFIGURAÇÃO ATUAL**\n"
                    f"> `🏰` Canal: {canal}\n"
                    f"> `⏳` Duração: **{conf['duracao']}**\n"
                    f"> `🏆` Vencedores: **{conf['vencedores']}**\n"
                    f"> `📅` Dias mínimos: **{conf['dias_min']}**\n"
                    f"> `🎖️` Cargo: {('<@&%s>' % conf['cargo_exigido']) if conf.get('cargo_exigido') else 'Nenhum'}\n"
                    f"> `✨` Bônus: **x{conf['bonus_mult']}**\n"
                    f"> `🔔` Notificação: **{conf['ping']}**\n"
                    f"> `👑` Tema: **{TEMAS[conf['tema']]['nome']}**", ephemeral=True)
            botao.callback = cb
            linha.append(botao)
        elementos.append(discord.ui.ActionRow(*linha))
        elementos.append(discord.ui.TextDisplay("-# Família Royal • Preferências salvas no PostgreSQL"))
        self.add_item(discord.ui.Container(*elementos, accent_colour=discord.Colour(COR_AZUL)))


class ConfigAvisosView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=240)
        self.guild_id = guild_id
        self.add_item(ConfigAvisosSelect(guild_id, "ping"))
        self.add_item(ConfigAvisosSelect(guild_id, "tema"))


class ConfigAvisosSelect(discord.ui.Select):
    def __init__(self, guild_id: int, campo: str):
        self.guild_id = guild_id
        self.campo = campo
        if campo == "ping":
            options = [
                discord.SelectOption(label="Sem aviso", value="0"),
                discord.SelectOption(label="Cargo de sorteios", value="1"),
                discord.SelectOption(label="@here", value="2"),
                discord.SelectOption(label="@everyone", value="3"),
            ]
        else:
            options = [discord.SelectOption(label=v["nome"], value=k, emoji=v["emoji"])
                       for k, v in TEMAS.items()]
        super().__init__(placeholder="Notificações" if campo == "ping" else "Estilo do sorteio",
                         options=options)

    async def callback(self, interaction):
        if interaction.guild_id != self.guild_id or not eh_staff(interaction.user):
            return await interaction.response.send_message("⛔ Acesso restrito.", ephemeral=True)
        valor = int(self.values[0]) if self.campo == "ping" else self.values[0]
        if self.campo == "ping" and valor >= len(opcoes_ping(interaction.guild)):
            return await interaction.response.send_message("Cargo de ping indisponível. Confira a configuração.", ephemeral=True)
        try:
            await salvar_config(self.guild_id, {self.campo: valor})
            await interaction.response.send_message("✅ Preferência atualizada.", ephemeral=True)
        except Exception:
            LOG.exception("Erro ao salvar avisos de sorteios")
            await interaction.response.send_message("❌ Falha ao salvar.", ephemeral=True)


class PainelSorteioRoyal(discord.ui.LayoutView):
    """Painel administrativo Royal (Components V2); preserva controles anteriores."""

    def __init__(self):
        super().__init__(timeout=None)
        componentes = []
        media, _ = banner_painel()
        if media:
            componentes.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=media)))
        componentes.append(discord.ui.TextDisplay(
            "## 👑 CENTRAL DE SORTEIOS ROYAL\n"
            "Gerencie premiações e eventos da Família Royal com segurança.\n\n"
            "> `🎁` **Criar** — premiação, duração e condições\n"
            "> `⚡` **Relâmpago** — publicação imediata\n"
            "> `🛡️` **Gerenciar** — encerrar, cancelar ou sortear novamente\n"
            "> `📊` **Estatísticas** — acompanhamento administrativo"
        ))
        componentes.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        botoes = []
        for label, emoji, style, action in (
            ("Criar", "🎁", discord.ButtonStyle.primary, "criar"),
            ("Relâmpago", "⚡", discord.ButtonStyle.primary, "rapido"),
            ("Gerenciar", "🛡️", discord.ButtonStyle.secondary, "gerenciar"),
            ("Estatísticas", "📊", discord.ButtonStyle.secondary, "stats"),
            ("Configurar", "⚙️", discord.ButtonStyle.secondary, "config"),
        ):
            botao = discord.ui.Button(label=label, emoji=emoji, style=style,
                                      custom_id=f"royal:sorteio:painel:{action}:v1")
            async def clique(interaction: discord.Interaction, acao=action):
                if not eh_staff(interaction.user):
                    return await interaction.response.send_message("⛔ Acesso exclusivo da equipe.", ephemeral=True)
                if acao == "config":
                    return await interaction.response.send_message(
                        "⚜️ Abra ou publique o painel administrativo com `!painelconfigsorteio`.", ephemeral=True)
                if acao == "criar":
                    return await interaction.response.send_modal(CriarModal(interaction.client, interaction.guild.id))
                if acao == "rapido":
                    return await interaction.response.send_modal(RelampagoModal(interaction.client))
                if acao == "stats":
                    return await interaction.response.send_message(
                        embed=embed_estatisticas(interaction.guild), ephemeral=True)
                itens = sorteios_da_guild(interaction.guild.id)
                if not itens:
                    return await interaction.response.send_message("Nenhum sorteio registrado.", ephemeral=True)
                ativos = sorted((x for x in itens if x.get("status") == "ativo"),
                                key=lambda x: x.get("fim_ts", 0))
                outros = sorted((x for x in itens if x.get("status") != "ativo"),
                                key=lambda x: x.get("encerrado_ts", 0), reverse=True)
                return await interaction.response.send_message(
                    "**Gerenciar sorteios da Família Royal**",
                    view=GerenciarSelectView(interaction.client, ativos + outros), ephemeral=True)
            botao.callback = clique
            botoes.append(botao)
        componentes.append(discord.ui.ActionRow(*botoes))
        componentes.append(discord.ui.TextDisplay("-# ⚜️ Família Royal • Administração de sorteios"))
        self.add_item(discord.ui.Container(*componentes, accent_colour=discord.Colour(COR_AZUL)))


class PainelSorteioView(discord.ui.View):
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if eh_staff(interaction.user):
            return True
        await interaction.response.send_message(
            "❌ Apenas a equipe pode usar este painel.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Criar", emoji="➕", style=discord.ButtonStyle.primary, custom_id="sants_sorteio_criar")
    async def criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CriarModal(interaction.client, interaction.guild.id))

    @discord.ui.button(label="Relâmpago", emoji="⚡", style=discord.ButtonStyle.primary, custom_id="sants_sorteio_rapido")
    async def rapido(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RelampagoModal(interaction.client))

    @discord.ui.button(label="Gerenciar", emoji="🛠️", style=discord.ButtonStyle.secondary, custom_id="sants_sorteio_gerenciar")
    async def gerenciar(self, interaction: discord.Interaction, button: discord.ui.Button):
        lista = sorteios_da_guild(interaction.guild.id)
        if not lista:
            return await interaction.response.send_message(
                "📭 Ainda não há sorteios registrados.", ephemeral=True
            )
        ativos = sorted(
            (g for g in lista if g.get("status") == "ativo"), key=lambda g: g["fim_ts"]
        )
        outros = sorted(
            (g for g in lista if g.get("status") != "ativo"),
            key=lambda g: g.get("encerrado_ts", 0),
            reverse=True,
        )
        await interaction.response.send_message(
            "🛠️ **Qual sorteio você quer gerenciar?** *(ativos primeiro, depois os mais recentes)*",
            view=GerenciarSelectView(interaction.client, ativos + outros),
            ephemeral=True,
        )

    @discord.ui.button(label="Estatísticas", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="sants_sorteio_stats")
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_estatisticas(interaction.guild), ephemeral=True
        )


# ════════════════════════════════════════════════════════════════
#                                  COG
# ════════════════════════════════════════════════════════════════


class SorteiosCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await iniciar_armazenamento(self.bot)
        self.bot.add_view(PainelSorteioView(self.bot))
        self.bot.add_view(PainelSorteioRoyal())
        self.bot.add_view(PainelConfigRoyal())
        self.bot.add_view(SorteioView())  # painéis antigos
        self.bot.add_view(RoyalSorteioView())  # sorteios novos (Components V2)
        self.monitorar.start()

    async def cog_unload(self):
        self.monitorar.cancel()
        await aguardar_gravacoes()

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "❌ Você não tem permissão para usar este comando.", delete_after=5
            )
        else:
            raise error

    # ── Loop: encerra sorteios no horário e atualiza contadores ──
    @tasks.loop(seconds=15)
    async def monitorar(self):
        agora = int(time.time())
        for chave, g in list(todos().items()):
            if g.get("status") != "ativo":
                continue
            try:
                msg_id = int(chave)
                if agora >= int(g["fim_ts"]):
                    await encerrar_sorteio(self.bot, msg_id)
                elif msg_id in SUJOS:
                    SUJOS.discard(msg_id)
                    atual = obter(msg_id)
                    if atual:
                        await atualizar_mensagem(self.bot, atual)
            except Exception as e:  # noqa: BLE001 - o monitor nunca deve parar
                print(f"[sorteios] erro no monitoramento: {e}")

    @monitorar.before_loop
    async def antes_monitorar(self):
        await self.bot.wait_until_ready()

    # ── Comandos ────────────────────────────────────────────────
    @commands.command(name="painelsorteio")
    @apenas_staff()
    async def painelsorteio(self, ctx: commands.Context):
        """Cria o painel de sorteios (use num canal privado da equipe)."""
        destino = (
            f"<#{CANAL_SORTEIOS_ID}>" if CANAL_SORTEIOS_ID else "o canal onde você criar"
        )
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await enviar_painel_com_banner(ctx, PainelSorteioRoyal())

    @commands.command(name="painelconfigsorteio", aliases=["configsorteio"])
    @commands.guild_only()
    @apenas_staff()
    async def painelconfigsorteio(self, ctx: commands.Context):
        """Publica o painel separado de preferências para sorteios futuros."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await enviar_painel_com_banner(ctx, PainelConfigRoyal())

    @commands.command(name="sorteioajuda")
    @apenas_staff()
    async def sorteioajuda(self, ctx: commands.Context):
        """Lista os comandos do sistema de sorteios."""
        p = ctx.clean_prefix
        embed = discord.Embed(
            title="📖 Comandos de Sorteios",
            description=(
                f"`{p}painelsorteio` — cria o painel da equipe\n"
                f"`{p}sorteioajuda` — mostra esta ajuda\n"
                f"`{p}painelconfigsorteio` — configura os próximos sorteios\n\n"
                "**Tudo o resto é feito pelo painel:** criar, relâmpago, "
                "gerenciar (encerrar, cancelar, rerolar) e estatísticas.\n\n"
                "**Formatos de duração:** `30m` • `2h` • `1d` • `1d12h` • `90` (minutos)"
            ),
            color=COR_AZUL,
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        g = obter(payload.message_id)
        if g and g.get("status") == "ativo":
            g["status"] = "cancelado"
            g["encerrado_ts"] = int(time.time())
            salvar(g)
            SUJOS.discard(payload.message_id)
            guild = self.bot.get_guild(int(g["guild"]))
            if guild:
                await registrar(
                    guild,
                    "🚫 Sorteio Cancelado",
                    f"A mensagem de **{g['premio']}** foi apagada, então o sorteio "
                    "foi cancelado automaticamente.",
                    0xE74C3C,
                )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        for g in sorteios_da_guild(member.guild.id):
            if g.get("status") == "ativo" and str(member.id) in g.get("participantes", {}):
                g["participantes"].pop(str(member.id), None)
                salvar(g)
                SUJOS.add(int(g["mensagem"]))


async def setup(bot: commands.Bot):
    await bot.add_cog(SorteiosCog(bot))