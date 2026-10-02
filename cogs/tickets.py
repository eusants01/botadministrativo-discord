from __future__ import annotations

import asyncio
import html
import io
import json
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

NOME_SERVIDOR = "Família Sant's"
FUSO = ZoneInfo("America/Sao_Paulo")

COR_AZUL = 0x1A3C8C  

CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,

]

CARGOS_NOTIFICAR = [1553832098404499516]


CATEGORIA_TICKETS_ID = 1555449984453972009

CANAL_LOGS_ID = 1555446279033589770

CANAL_AVALIACOES_ID = 1555453132387913728

MAX_TICKETS_POR_USUARIO = 1
TEMPO_PARA_APAGAR = 3
COOLDOWN_CHAMAR_EQUIPE = 100
ALERTA_SEM_ATENDENTE_MINUTOS = 5


INATIVIDADE_AVISO_HORAS = 24
INATIVIDADE_FECHAR_APOS_AVISO_HORAS = 12

# ── 3) Visual ───────────────────────────────────────────────────

BANNER_PRINCIPAL = "https://cdn.discordapp.com/attachments/961677475191078992/1555452137499271249/content.png?backend=b2&ex=6ac09330&is=6abf41b0&hm=69fd6e5a44be95e298fc5f9c2cad885291bec77f1a1919a0343f275f2820c8cd&"

# Texto do painel principal (!painelticket). Pode editar à vontade —
# aceita a formatação do Discord (negrito, `código`, > citação).
PAINEL_DESCRICAO = """\
# <a:sino:1555469607341654047> **Central de Atendimento**
Escolha no menu abaixo uma categoria que deseja receber o suporte necessário.

**Escolha a sua Categoria**
> `🛠️` **Suporte** — Dúvidas e ajuda em geral.
> `☎️` **Denúncia** — Reportar jogadores ou comportamentos.
> `💼` **Parcerias** — Assuntos sobre parcerias.
> `🎖️` **Solicitar Cargos** — Solicite um cargo.

**Horário de Funcionamento.**
> `⏳` Segunda a Sexta: das **09:00 até 23:59h**
> `⏳` Sábado e Domingo: das **12:00 até 19:00h**

**Aviso**
> `⚠️` O uso abusivo desnecessário acarretará em punição.
"""

# Prioridades que a staff pode definir no painel do ticket
PRIORIDADES = {
    "baixa": ("🟢", "Baixa"),
    "normal": ("🟡", "Normal"),
    "alta": ("🟠", "Alta"),
    "urgente": ("🔴", "Urgente"),
}

# ── 4) Categorias ───────────────────────────────────────────────
# Cada categoria tem: banner, mensagem de boas-vindas, cor, emoji, cargos
# marcados e um FORMULÁRIO (perguntas) que o usuário responde ao abrir.
#   • "mensagem": texto que aparece dentro do ticket. Use {usuario} para
#     mencionar quem abriu e a formatação do Discord (**negrito**, `código`,
#     > citação), no mesmo estilo do painel principal.
#   • "perguntas": até 5. Deixe [] para não ter formulário.
#   • "categoria_discord_id": só preencha se esta categoria específica
#     precisar ir para OUTRA categoria do Discord (senão deixe None).
CATEGORIAS = {
    "suporte": {
        "nome": "Suporte",
        "emoji": "🛠️",
        "descricao": "Dúvidas e ajuda em geral",
        "cor": COR_AZUL,
        "banner": "https://i.imgur.com/link_do_banner_suporte.jpg",
        "mensagem": """Olá, {usuario}! 👋
Seja bem-vindo ao **Suporte da Família Sant's**.

**Como funciona**
> `📝` Explique a sua dúvida ou problema com detalhes.
> `📎` Se puder, envie prints ou vídeos que ajudem.
> `⏳` Aguarde um momento — a equipe já foi avisada.
""",
        "perguntas": [
            {
                "label": "Qual é a sua dúvida ou problema?",
                "placeholder": "Explique com o máximo de detalhes possível...",
                "longo": True,
                "obrigatorio": True,
            },
        ],
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
    "denuncia": {
        "nome": "Denúncia",
        "emoji": "☎️",
        "descricao": "Reportar jogadores ou comportamentos",
        "cor": COR_AZUL,
        "banner": "https://i.imgur.com/link_do_banner_denuncia.jpg",
        "mensagem": """Olá, {usuario}.
Sua denúncia será tratada com **sigilo e seriedade**.

**O que enviar**
> `👤` Nome, ID ou @ de quem você está denunciando.
> `📅` Quando e onde aconteceu.
> `📎` Provas: prints, vídeos ou links.

**Aviso**
> `⚠️` Denúncias falsas ou sem provas podem gerar punição.
""",
        "perguntas": [
            {
                "label": "Quem você está denunciando?",
                "placeholder": "Nome, ID ou @ do denunciado",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "O que aconteceu?",
                "placeholder": "Conte o que ocorreu, quando e onde...",
                "longo": True,
                "obrigatorio": True,
            },
            {
                "label": "Provas (links)",
                "placeholder": "Links de prints/vídeos (ou envie aqui no ticket)",
                "longo": False,
                "obrigatorio": False,
            },
        ],
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
    "parceria": {
        "nome": "Parcerias",
        "emoji": "💼",
        "descricao": "Assuntos sobre parcerias",
        "cor": COR_AZUL,
        "banner": "https://i.imgur.com/link_do_banner_parceria.jpg",
        "mensagem": """Olá, {usuario}! 🤝
Que bom ter interesse em uma parceria com a **Família Sant's**.

**Como funciona**
> `📋` Um responsável vai analisar a sua proposta.
> `💬` A resposta será enviada aqui mesmo, neste ticket.
> `⏳` Aguarde — a equipe já foi avisada.
""",
        "perguntas": [
            {
                "label": "Nome do servidor/grupo",
                "placeholder": "Ex: Comunidade X",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Link de convite",
                "placeholder": "https://discord.gg/...",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Quantidade de membros",
                "placeholder": "Ex: 500",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Qual é a sua proposta?",
                "placeholder": "Como seria a parceria?",
                "longo": True,
                "obrigatorio": True,
            },
        ],
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
    "cargos": {
        "nome": "Solicitar Cargos",
        "emoji": "🎖️",
        "descricao": "Solicite um cargo",
        "cor": COR_AZUL,
        "banner": "https://i.imgur.com/link_do_banner_cargos.jpg",
        "mensagem": """Olá, {usuario}! 🎖️
Recebemos o seu pedido de cargo.

**Como funciona**
> `🔎` A equipe vai analisar a sua atividade e o seu tempo na Família.
> `💬` A resposta será enviada aqui mesmo, neste ticket.
> `⏳` Aguarde — a equipe já foi avisada.
""",
        "perguntas": [
            {
                "label": "Qual cargo você deseja?",
                "placeholder": "Ex: Membro Oficial",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Por que você merece esse cargo?",
                "placeholder": "Fale do seu tempo e atividade na Família...",
                "longo": True,
                "obrigatorio": True,
            },
        ],
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
}

# ╔══════════════════════════════════════════════════════════════╗
# ║              DAQUI PARA BAIXO NÃO PRECISA MEXER              ║
# ╚══════════════════════════════════════════════════════════════╝

PASTA_DADOS = "dados_tickets"
os.makedirs(PASTA_DADOS, exist_ok=True)
F_CONTADOR = os.path.join(PASTA_DADOS, "contador.json")
F_ESTADOS = os.path.join(PASTA_DADOS, "tickets_abertos.json")
F_HISTORICO = os.path.join(PASTA_DADOS, "historico.json")
F_AVALIACOES = os.path.join(PASTA_DADOS, "avaliacoes.json")
F_BLOQUEIOS = os.path.join(PASTA_DADOS, "bloqueados.json")

# Migra arquivos da versão anterior, se existirem
for _antigo, _novo in (
    ("tickets_contador.json", F_CONTADOR),
    ("tickets_avaliacoes.json", F_AVALIACOES),
):
    if os.path.exists(_antigo) and not os.path.exists(_novo):
        os.replace(_antigo, _novo)

CANAIS_FECHANDO: set[int] = set()
COOLDOWN_CHAMAR: dict[int, float] = {}


# ════════════════════════════════════════════════════════════════
#                         ARMAZENAMENTO (JSON)
# ════════════════════════════════════════════════════════════════


def _ler_json(caminho: str, padrao):
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return padrao


def _salvar_json(caminho: str, dados):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def proximo_numero() -> int:
    dados = _ler_json(F_CONTADOR, {"contador": 0})
    dados["contador"] = int(dados.get("contador", 0)) + 1
    _salvar_json(F_CONTADOR, dados)
    return dados["contador"]


def estados() -> dict:
    return _ler_json(F_ESTADOS, {})


def salvar_estado(canal_id: int, **campos) -> dict:
    dados = estados()
    est = dados.setdefault(str(canal_id), {})
    est.update(campos)
    _salvar_json(F_ESTADOS, dados)
    return est


def remover_estado(canal_id):
    dados = estados()
    if str(canal_id) in dados:
        dados.pop(str(canal_id))
        _salvar_json(F_ESTADOS, dados)


def salvar_avaliacao(registro: dict):
    dados = _ler_json(F_AVALIACOES, [])
    dados.append(registro)
    _salvar_json(F_AVALIACOES, dados)


def registrar_historico(registro: dict):
    dados = _ler_json(F_HISTORICO, [])
    dados.append(registro)
    _salvar_json(F_HISTORICO, dados)


def ler_topico(canal) -> dict:
    """O tópico guarda (só na criação): owner=ID;cat=chave;num=N"""
    info = {}
    if getattr(canal, "topic", None):
        for parte in canal.topic.split(";"):
            if "=" in parte:
                k, v = parte.split("=", 1)
                info[k.strip()] = v.strip()
    return info


def ler_ticket(canal, cache: dict | None = None) -> dict:
    """Dados do ticket (estado salvo + tópico). Retorna {} se não for ticket."""
    info = ler_topico(canal)
    if not info.get("owner") and str(canal.id) not in (cache or estados()):
        return {}
    t = {
        "owner": int(info["owner"]) if info.get("owner") else None,
        "cat": info.get("cat", ""),
        "num": int(info.get("num", 0) or 0),
        "prio": "normal",
        "claim": int(info["claim"]) if info.get("claim") else None,
        "locked": False,
        "respostas": [],
        "notas": [],
        "card_id": None,
    }
    t.update((cache if cache is not None else estados()).get(str(canal.id), {}))
    return t if t.get("owner") else {}


def listar_tickets(guild: discord.Guild) -> list[tuple[discord.TextChannel, dict]]:
    cache = estados()
    out = []
    for c in guild.text_channels:
        t = ler_ticket(c, cache)
        if t:
            out.append((c, t))
    return out


# ════════════════════════════════════════════════════════════════
#                              AUXILIARES
# ════════════════════════════════════════════════════════════════


def eh_staff(membro) -> bool:
    """Staff = quem tem a permissão Administrador (em qualquer cargo, ou o dono
    do servidor) OU algum dos cargos de CARGOS_STAFF."""
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


def agora() -> str:
    return datetime.now(FUSO).strftime("%d/%m/%Y %H:%M:%S")


def banner_valido(url) -> bool:
    return bool(url) and str(url).startswith("http") and "link_do_banner" not in url


def estrelas(nota: int) -> str:
    return "⭐" * nota + "☆" * (5 - nota)


def formatar_duracao(seg: float) -> str:
    seg = int(seg)
    d, seg = divmod(seg, 86400)
    h, seg = divmod(seg, 3600)
    m, _ = divmod(seg, 60)
    partes = []
    if d:
        partes.append(f"{d}d")
    if h:
        partes.append(f"{h}h")
    if m:
        partes.append(f"{m}min")
    return " ".join(partes) or "<1min"


def cargos_para_notificar(chave: str) -> list[int]:
    ids = list(CARGOS_NOTIFICAR) + list(CATEGORIAS.get(chave, {}).get("cargos_ping", []))
    return list(dict.fromkeys(ids))


def resolver_categoria(guild, cat: dict, fallback):
    for cid in (cat.get("categoria_discord_id"), CATEGORIA_TICKETS_ID):
        if cid:
            c = guild.get_channel(cid)
            if isinstance(c, discord.CategoryChannel):
                return c
    return fallback


async def buscar_membro(bot, guild: discord.Guild, user_id: int):
    m = guild.get_member(user_id)
    if m:
        return m
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        pass
    try:
        return await bot.fetch_user(user_id)
    except discord.HTTPException:
        return None


async def registrar(guild: discord.Guild, titulo: str, descricao: str, cor=COR_AZUL):
    """Envia um log para o canal de logs."""
    canal = guild.get_channel(CANAL_LOGS_ID) if CANAL_LOGS_ID else None
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


async def aviso_no_ticket(canal: discord.TextChannel, texto: str, cor=COR_AZUL):
    try:
        await canal.send(embed=discord.Embed(description=texto, color=cor))
    except discord.HTTPException:
        pass


def checar_pode_abrir(guild: discord.Guild, user: discord.abc.User) -> str | None:
    bloqueios = _ler_json(F_BLOQUEIOS, {})
    if str(user.id) in bloqueios:
        motivo = bloqueios[str(user.id)].get("motivo", "Não informado")
        return f"🚫 Você está bloqueado de abrir tickets.\n**Motivo:** {motivo}"
    abertos = [c for c, t in listar_tickets(guild) if t.get("owner") == user.id]
    if len(abertos) >= MAX_TICKETS_POR_USUARIO:
        return f"❌ Você já possui um ticket aberto: {abertos[0].mention}"
    return None


# ════════════════════════════════════════════════════════════════
#                       CARD DO TICKET (mensagem principal)
# ════════════════════════════════════════════════════════════════


def montar_card(guild: discord.Guild, canal, t: dict) -> discord.Embed:
    cat = CATEGORIAS.get(t["cat"], {})
    p_emoji, p_nome = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])

    cabecalho = f"**{cat.get('emoji', '🎫')} {cat.get('nome', 'Ticket')} • Ticket #{t['num']:04d}**"
    mensagem = cat.get("mensagem", "").replace("{usuario}", f"<@{t['owner']}>").strip()
    partes = [f"{cabecalho}\n{mensagem}"]

    # Seção: solicitação do usuário (respostas do formulário)
    respostas = t.get("respostas", [])
    if respostas:
        blocos = []
        for label, valor in respostas:
            linhas = [f"> `📝` **{label}**"]
            linhas += [f"> {l}" if l.strip() else ">" for l in valor.splitlines()]
            blocos.append("\n".join(linhas))
        partes.append("**Sua solicitação**\n" + "\n>\n".join(blocos))

    # Seção: atendimento (só mostra o que é relevante)
    linhas = [
        f"> `🙋` Atendente: <@{t['claim']}>"
        if t.get("claim")
        else "> `⏳` Aguardando um atendente"
    ]
    if t.get("prio", "normal") != "normal":
        linhas.append(f"> `{p_emoji}` Prioridade **{p_nome}**")
    if t.get("locked"):
        linhas.append("> `🔒` Ticket trancado pela equipe")
    partes.append("**Atendimento**\n" + "\n".join(linhas))

    embed = discord.Embed(
        description="\n\n".join(partes)[:4096],
        color=cat.get("cor", COR_AZUL),
        timestamp=canal.created_at,
    )
    if banner_valido(cat.get("banner")):
        embed.set_image(url=cat["banner"])
    embed.set_footer(text=NOME_SERVIDOR)
    return embed


async def atualizar_card(canal: discord.TextChannel):
    t = ler_ticket(canal)
    if not t or not t.get("card_id"):
        return
    try:
        msg = await canal.fetch_message(t["card_id"])
        await msg.edit(
            embed=montar_card(canal.guild, canal, t),
            view=TicketControls(assumido=bool(t.get("claim"))),
        )
    except discord.HTTPException:
        pass


# ════════════════════════════════════════════════════════════════
#                               TRANSCRIPT
# ════════════════════════════════════════════════════════════════


async def gerar_transcript_html(canal: discord.TextChannel, t: dict) -> tuple[str, int]:
    linhas = []
    total = 0
    async for msg in canal.history(limit=None, oldest_first=True):
        total += 1
        hora = msg.created_at.astimezone(FUSO).strftime("%d/%m/%Y %H:%M:%S")
        conteudo = html.escape(msg.clean_content).replace("\n", "<br>")
        extras = ""
        for a in msg.attachments:
            extras += (
                f'<div class="anexo">📎 <a href="{html.escape(a.url)}" '
                f'target="_blank">{html.escape(a.filename)}</a></div>'
            )
        for e in msg.embeds:
            if e.title or e.description or e.fields:
                corpo = f"<b>{html.escape(e.title or '')}</b><br>"
                corpo += html.escape(e.description or "").replace("\n", "<br>")
                for f in e.fields:
                    corpo += (
                        f"<br><b>{html.escape(f.name)}</b>: "
                        f"{html.escape(f.value).replace(chr(10), '<br>')}"
                    )
                extras += f'<div class="embed">{corpo}</div>'
        linhas.append(
            f'<div class="msg"><img src="{msg.author.display_avatar.url}">'
            f'<div><span class="autor">{html.escape(str(msg.author))}</span> '
            f'<span class="hora">{hora}</span><br>{conteudo}{extras}</div></div>'
        )

    cat = CATEGORIAS.get(t.get("cat", ""), {}).get("nome", "—")
    pagina = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Logs — {html.escape(canal.name)}</title>
<style>
body{{background:#1e1f22;color:#dbdee1;font-family:Segoe UI,Arial,sans-serif;margin:0;padding:20px}}
h1{{color:#fff;margin-bottom:0}} .sub{{color:#949ba4;margin-bottom:20px}}
.msg{{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #2b2d31}}
.msg img{{width:40px;height:40px;border-radius:50%}}
.autor{{color:#fff;font-weight:600}} .hora{{color:#949ba4;font-size:12px}}
.anexo{{margin-top:4px;font-size:13px}} a{{color:#00a8fc}}
.embed{{border-left:4px solid #5865f2;background:#2b2d31;padding:6px 10px;margin-top:4px;border-radius:4px}}
</style></head><body>
<h1>📑 {html.escape(NOME_SERVIDOR)} — Logs do Ticket</h1>
<div class="sub">Canal: #{html.escape(canal.name)} · Categoria: {html.escape(cat)} ·
Mensagens: {total} · Gerado em {agora()}</div>
{''.join(linhas)}
</body></html>"""
    return pagina, total


# ════════════════════════════════════════════════════════════════
#                          FECHAMENTO DO TICKET
# ════════════════════════════════════════════════════════════════


async def fechar_ticket(
    bot: commands.Bot,
    canal: discord.TextChannel,
    quem_fechou: discord.Member,
    motivo: str,
):
    if canal.id in CANAIS_FECHANDO:
        return
    CANAIS_FECHANDO.add(canal.id)
    apagado = False

    try:
        guild = canal.guild
        t = ler_ticket(canal)
        dono_id = t.get("owner")
        dono = await buscar_membro(bot, guild, dono_id) if dono_id else None
        cat_key = t.get("cat", "")
        cat = CATEGORIAS.get(cat_key, {})
        numero = int(t.get("num", 0) or 0)
        staff_id = int(t.get("claim") or 0)
        p_emoji, p_nome = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])
        duracao = (datetime.now(timezone.utc) - canal.created_at).total_seconds()

        await aviso_no_ticket(
            canal,
            f"🔒 Ticket sendo fechado por {quem_fechou.mention}.\n"
            f"Gerando logs... o canal será apagado em **{TEMPO_PARA_APAGAR}s**.",
            discord.Color.orange().value,
        )

        pagina, total_msgs = await gerar_transcript_html(canal, t)
        dados = pagina.encode("utf-8")
        nome_arquivo = f"logs_{canal.name}.html"

        def base_embed() -> discord.Embed:
            e = discord.Embed(
                title=f"📑 Ticket #{numero:04d} Fechado",
                color=cat.get("cor", COR_AZUL),
                timestamp=datetime.now(FUSO),
            )
            e.add_field(name="Ticket", value=f"`{canal.name}`", inline=True)
            e.add_field(name="Categoria", value=cat.get("nome", "—"), inline=True)
            e.add_field(
                name="Aberto por",
                value=dono.mention if dono else f"<@{dono_id}>",
                inline=True,
            )
            e.add_field(name="Fechado por", value=quem_fechou.mention, inline=True)
            e.add_field(
                name="Atendente",
                value=f"<@{staff_id}>" if staff_id else "Ninguém",
                inline=True,
            )
            e.add_field(name="Duração", value=formatar_duracao(duracao), inline=True)
            e.add_field(name="Motivo", value=motivo or "Não informado", inline=False)
            e.set_footer(text=NOME_SERVIDOR)
            return e

        # DM para quem abriu: UMA mensagem (resumo + logs + avaliação)
        dm_ok = False
        if dono:
            try:
                staff_membro = guild.get_member(staff_id) if staff_id else None
                atendente = (
                    f" com **{staff_membro.display_name}**"
                    if staff_membro
                    else " com a nossa equipe"
                )
                embed_av = discord.Embed(
                    title="⭐ Avalie o seu atendimento",
                    description=(
                        f"Olá, **{dono.display_name}**!\n\n"
                        f"Seu ticket **#{numero:04d}** "
                        f"({cat.get('nome', 'Ticket')}) foi finalizado.\n"
                        f"Como foi o seu atendimento{atendente}?\n\n"
                        "Clique em uma das notas abaixo. 💙"
                    ),
                    color=0xF1C40F,
                )
                embed_av.set_footer(text=f"{NOME_SERVIDOR} • Sua opinião importa!")
                view = discord.ui.View(timeout=None)
                for n in range(1, 6):
                    view.add_item(
                        BotaoNota(n, guild.id, numero, staff_id, cat_key or "x")
                    )
                await dono.send(
                    content=f"📑 Aqui estão os logs do seu ticket em "
                    f"**{NOME_SERVIDOR}**:",
                    embeds=[base_embed(), embed_av],
                    file=discord.File(io.BytesIO(dados), filename=nome_arquivo),
                    view=view,
                )
                dm_ok = True
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Log completo para a staff: UMA mensagem (embed + arquivo)
        embed_staff = base_embed()
        embed_staff.insert_field_at(
            5, name="Prioridade", value=f"{p_emoji} {p_nome}", inline=True
        )
        embed_staff.add_field(name="Mensagens", value=str(total_msgs), inline=True)
        notas = t.get("notas", [])
        if notas:
            texto_notas = "\n".join(f"• **{n['autor']}**: {n['texto']}" for n in notas)
            embed_staff.add_field(
                name="📝 Notas internas", value=texto_notas[:1024], inline=False
            )
        if dono and not dm_ok:
            embed_staff.add_field(
                name="⚠️ DM",
                value="Não foi possível enviar logs/avaliação (DMs fechadas).",
                inline=False,
            )

        canal_logs = guild.get_channel(CANAL_LOGS_ID) if CANAL_LOGS_ID else None
        if canal_logs:
            try:
                await canal_logs.send(
                    embed=embed_staff,
                    file=discord.File(io.BytesIO(dados), filename=nome_arquivo),
                )
            except discord.HTTPException:
                pass

        registrar_historico(
            {
                "num": numero,
                "cat": cat_key,
                "owner": dono_id,
                "claim": staff_id,
                "prio": t.get("prio", "normal"),
                "duracao_seg": int(duracao),
                "mensagens": total_msgs,
                "fechado_por": quem_fechou.id,
                "motivo": motivo,
                "fechado_ts": int(time.time()),
            }
        )

        await asyncio.sleep(TEMPO_PARA_APAGAR)
        try:
            await canal.delete(reason=f"Ticket fechado por {quem_fechou}")
            apagado = True
        except discord.HTTPException:
            pass
    finally:
        CANAIS_FECHANDO.discard(canal.id)
        if apagado:
            remover_estado(canal.id)


# ════════════════════════════════════════════════════════════════
#                     AVALIAÇÃO (DM) — BOTÕES PERSISTENTES
# ════════════════════════════════════════════════════════════════


class ComentarioModal(discord.ui.Modal):
    comentario = discord.ui.TextInput(
        label="Quer deixar um comentário? (opcional)",
        placeholder="Conte como foi sua experiência...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, nota, guild_id, numero, staff_id, cat_key):
        super().__init__(title=f"Sua nota: {nota} de 5", timeout=300)
        self.nota = nota
        self.guild_id = guild_id
        self.numero = numero
        self.staff_id = staff_id
        self.cat_key = cat_key

    async def on_submit(self, interaction: discord.Interaction):
        comentario = str(self.comentario).strip()
        cat = CATEGORIAS.get(self.cat_key, {})

        salvar_avaliacao(
            {
                "nota": self.nota,
                "staff": self.staff_id,
                "categoria": self.cat_key,
                "ticket": self.numero,
                "usuario": interaction.user.id,
                "comentario": comentario,
                "data": agora(),
            }
        )

        guild = interaction.client.get_guild(self.guild_id)
        canal = (
            guild.get_channel(CANAL_AVALIACOES_ID or CANAL_LOGS_ID) if guild else None
        )
        if canal:
            embed = discord.Embed(
                title="⭐ Nova Avaliação de Atendimento",
                color=0xF1C40F,
                timestamp=datetime.now(FUSO),
            )
            embed.add_field(name="Nota", value=estrelas(self.nota), inline=True)
            embed.add_field(
                name="Ticket",
                value=f"#{self.numero:04d} • {cat.get('nome', '—')}",
                inline=True,
            )
            embed.add_field(
                name="Atendente",
                value=f"<@{self.staff_id}>" if self.staff_id else "Ninguém assumiu",
                inline=True,
            )
            embed.add_field(
                name="Avaliado por", value=interaction.user.mention, inline=True
            )
            embed.add_field(
                name="Comentário", value=comentario or "*Sem comentário*", inline=False
            )
            embed.set_footer(text=NOME_SERVIDOR)
            try:
                await canal.send(embed=embed)
            except discord.HTTPException:
                pass

        agradecimento = discord.Embed(
            title="💙 Obrigado pela sua avaliação!",
            description=f"Sua nota: {estrelas(self.nota)}\n\n"
            f"Ela nos ajuda a melhorar o atendimento da **{NOME_SERVIDOR}**.",
            color=0x2ECC71,
        )
        await interaction.response.edit_message(embed=agradecimento, view=None)


class BotaoNota(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"sants_nota:(?P<nota>[1-5]):(?P<guild>\d+):(?P<num>\d+):(?P<staff>\d+):(?P<cat>\w+)",
):
    """Botão de nota 1-5. Os dados ficam no custom_id, então continua
    funcionando mesmo depois de o bot reiniciar."""

    def __init__(self, nota, guild_id, numero, staff_id, cat_key):
        estilo = (
            discord.ButtonStyle.danger
            if nota <= 2
            else discord.ButtonStyle.secondary
            if nota == 3
            else discord.ButtonStyle.success
        )
        super().__init__(
            discord.ui.Button(
                label=str(nota),
                emoji="⭐",
                style=estilo,
                custom_id=f"sants_nota:{nota}:{guild_id}:{numero}:{staff_id}:{cat_key}",
            )
        )
        self.nota = nota
        self.guild_id = guild_id
        self.numero = numero
        self.staff_id = staff_id
        self.cat_key = cat_key

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(
            int(match["nota"]),
            int(match["guild"]),
            int(match["num"]),
            int(match["staff"]),
            match["cat"],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ComentarioModal(
                self.nota, self.guild_id, self.numero, self.staff_id, self.cat_key
            )
        )


# ════════════════════════════════════════════════════════════════
#                         CRIAÇÃO DO TICKET
# ════════════════════════════════════════════════════════════════


async def criar_ticket(
    interaction: discord.Interaction, chave: str, respostas: list[list[str]]
):
    """Chamar DEPOIS de interaction.response.defer(ephemeral=True)."""
    guild = interaction.guild
    user = interaction.user
    cat = CATEGORIAS[chave]

    erro = checar_pode_abrir(guild, user)
    if erro:
        return await interaction.followup.send(erro, ephemeral=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_permissions=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
        ),
    }
    for cargo_id in dict.fromkeys(list(CARGOS_STAFF) + list(CARGOS_NOTIFICAR)):
        cargo = guild.get_role(cargo_id)
        if cargo:
            overwrites[cargo] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
                manage_messages=True,
            )

    categoria_discord = resolver_categoria(guild, cat, interaction.channel.category)
    numero = proximo_numero()
    try:
        canal = await guild.create_text_channel(
            name=f"{chave}-{numero:04d}",
            category=categoria_discord,
            overwrites=overwrites,
            topic=f"owner={user.id};cat={chave};num={numero}",
            reason=f"Ticket de {user} ({cat['nome']})",
        )
    except discord.HTTPException as e:
        return await interaction.followup.send(
            f"❌ Não consegui criar o ticket ({e.text}). "
            "Avise a staff — a categoria pode estar cheia (limite de 50 canais).",
            ephemeral=True,
        )

    t = salvar_estado(
        canal.id,
        owner=user.id,
        cat=chave,
        num=numero,
        prio="normal",
        claim=None,
        locked=False,
        respostas=respostas,
        notas=[],
        card_id=None,
    )

    await interaction.followup.send(
        f"✅ Seu ticket foi criado: {canal.mention}", ephemeral=True
    )

    pings = " ".join(f"<@&{r}>" for r in cargos_para_notificar(chave))
    card = await canal.send(
        content=f"{user.mention} {pings}".strip(),
        embed=montar_card(guild, canal, ler_ticket(canal)),
        view=TicketControls(),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )
    salvar_estado(canal.id, card_id=card.id)
    # (Sem log de abertura no canal de logs: só uma mensagem, ao fechar.)


class PerguntasModal(discord.ui.Modal):
    def __init__(self, chave: str):
        cat = CATEGORIAS[chave]
        super().__init__(title=f"{cat['emoji']} {cat['nome']}"[:45], timeout=600)
        self.chave = chave
        self.campos: list[tuple[str, discord.ui.TextInput]] = []
        for p in cat["perguntas"][:5]:
            longo = p.get("longo", False)
            campo = discord.ui.TextInput(
                label=p["label"][:45],
                placeholder=p.get("placeholder", "")[:100] or None,
                style=discord.TextStyle.paragraph if longo else discord.TextStyle.short,
                required=p.get("obrigatorio", True),
                max_length=800 if longo else 200,
            )
            self.add_item(campo)
            self.campos.append((p["label"], campo))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        respostas = [
            [label, str(campo).strip()]
            for label, campo in self.campos
            if str(campo).strip()
        ]
        await criar_ticket(interaction, self.chave, respostas)


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=c["nome"],
                value=chave,
                description=c["descricao"],
                emoji=c["emoji"],
            )
            for chave, c in CATEGORIAS.items()
        ]
        super().__init__(
            placeholder="📩 Selecione a categoria do seu ticket...",
            options=options,
            custom_id="sants_ticket_select",
        )

    async def _resetar(self, interaction: discord.Interaction):
        # Reseta o menu para a opção poder ser escolhida de novo
        try:
            await interaction.message.edit(view=TicketView())
        except discord.HTTPException:
            pass

    async def callback(self, interaction: discord.Interaction):
        chave = self.values[0]
        cat = CATEGORIAS[chave]

        erro = checar_pode_abrir(interaction.guild, interaction.user)
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return await self._resetar(interaction)

        if cat.get("perguntas"):
            await interaction.response.send_modal(PerguntasModal(chave))
            return await self._resetar(interaction)

        await interaction.response.defer(ephemeral=True)
        await self._resetar(interaction)
        await criar_ticket(interaction, chave, [])


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ════════════════════════════════════════════════════════════════
#                  CONTROLES DENTRO DO TICKET (público)
# ════════════════════════════════════════════════════════════════


class MotivoFechamentoModal(discord.ui.Modal, title="Fechar Ticket"):
    motivo = discord.ui.TextInput(
        label="Motivo do fechamento",
        placeholder="Ex: Problema resolvido",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "🔒 Fechando o ticket...", ephemeral=True
        )
        await fechar_ticket(
            interaction.client, interaction.channel, interaction.user, str(self.motivo)
        )


class TicketControls(discord.ui.View):
    def __init__(self, assumido: bool = False):
        super().__init__(timeout=None)
        self.assumir.disabled = assumido
        if assumido:
            self.assumir.label = "Assumido"

    @discord.ui.button(
        label="Assumir",
        style=discord.ButtonStyle.green,
        custom_id="sants_assumir_ticket",
        emoji="🙋",
    )
    async def assumir(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode assumir tickets.", ephemeral=True
            )
        t = ler_ticket(interaction.channel)
        if t.get("claim"):
            return await interaction.response.send_message(
                f"⚠️ Este ticket já foi assumido por <@{t['claim']}>.\n"
                "Use o **Painel Staff** para transferir.",
                ephemeral=True,
            )
        await interaction.response.defer()
        salvar_estado(interaction.channel.id, claim=interaction.user.id)
        await atualizar_card(interaction.channel)
        await aviso_no_ticket(
            interaction.channel,
            f"🙋 {interaction.user.mention} assumiu este ticket e vai te atender!",
            discord.Color.green().value,
        )
        await registrar(
            interaction.guild,
            "🙋 Ticket Assumido",
            f"{interaction.user.mention} assumiu {interaction.channel.mention}",
            0x2ECC71,
        )

    @discord.ui.button(
        label="Fechar",
        style=discord.ButtonStyle.red,
        custom_id="sants_fechar_ticket",
        emoji="🔒",
    )
    async def fechar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        t = ler_ticket(interaction.channel)
        eh_dono = t.get("owner") == interaction.user.id
        if not (eh_dono or eh_staff(interaction.user)):
            return await interaction.response.send_message(
                "❌ Você não pode fechar este ticket.", ephemeral=True
            )
        await interaction.response.send_modal(MotivoFechamentoModal())

    @discord.ui.button(
        label="Chamar Equipe",
        style=discord.ButtonStyle.secondary,
        custom_id="sants_chamar_equipe",
        emoji="🔔",
    )
    async def chamar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        t = ler_ticket(interaction.channel)
        if eh_staff(interaction.user):
            return await interaction.response.send_message(
                "ℹ️ Você já faz parte da equipe.", ephemeral=True
            )
        if t.get("owner") != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Apenas quem abriu o ticket pode chamar a equipe.", ephemeral=True
            )
        restante = COOLDOWN_CHAMAR_EQUIPE - (
            time.time() - COOLDOWN_CHAMAR.get(interaction.channel.id, 0)
        )
        if restante > 0:
            return await interaction.response.send_message(
                f"⏳ Aguarde **{formatar_duracao(restante)}** para chamar de novo.",
                ephemeral=True,
            )
        COOLDOWN_CHAMAR[interaction.channel.id] = time.time()

        if t.get("claim"):
            mencao = f"<@{t['claim']}>"
        else:
            ids = cargos_para_notificar(t.get("cat", "")) or list(CARGOS_STAFF)
            mencao = " ".join(f"<@&{r}>" for r in ids)
        await interaction.channel.send(
            content=mencao or None,
            embed=discord.Embed(
                description=f"🔔 {interaction.user.mention} está chamando a equipe!",
                color=0xE67E22,
            ),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
        await interaction.response.send_message("✅ Equipe chamada!", ephemeral=True)

    @discord.ui.button(
        label="Painel Staff",
        style=discord.ButtonStyle.blurple,
        custom_id="sants_painel_staff_ticket",
        emoji="🛠️",
    )
    async def painel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode abrir o painel staff.", ephemeral=True
            )
        t = ler_ticket(interaction.channel)
        await interaction.response.send_message(
            embed=embed_info_painel(interaction.channel, t),
            view=PainelTicketView(interaction.channel),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════
#                  PAINEL STAFF DO TICKET (somente staff)
# ════════════════════════════════════════════════════════════════


def embed_info_painel(canal, t: dict) -> discord.Embed:
    cat = CATEGORIAS.get(t.get("cat", ""), {})
    p_emoji, p_nome = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])
    e = discord.Embed(
        title=f"🛠️ Painel Staff — Ticket #{t.get('num', 0):04d}",
        description=(
            f"**Categoria:** {cat.get('nome', '—')}\n"
            f"**Aberto por:** <@{t.get('owner')}>\n"
            f"**Atendente:** "
            f"{('<@' + str(t['claim']) + '>') if t.get('claim') else 'Ninguém'}\n"
            f"**Prioridade:** {p_emoji} {p_nome}\n"
            f"**Status:** {'🔒 Trancado' if t.get('locked') else '🟢 Aberto'}\n"
            f"**Notas internas:** {len(t.get('notas', []))}"
        ),
        color=COR_AZUL,
    )
    e.set_footer(text="Use as opções abaixo para gerenciar este ticket.")
    return e


class RenomearModal(discord.ui.Modal, title="Renomear Ticket"):
    nome = discord.ui.TextInput(label="Novo nome do canal", max_length=90)

    def __init__(self, canal):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        antigo = self.canal.name
        try:
            await asyncio.wait_for(self.canal.edit(name=str(self.nome)), timeout=8)
        except asyncio.TimeoutError:
            return await interaction.response.send_message(
                "⏳ O Discord limita a 2 renomeações a cada 10 minutos. "
                "Tente novamente mais tarde.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "❌ Não consegui renomear.", ephemeral=True
            )
        await interaction.response.send_message("✅ Ticket renomeado.", ephemeral=True)
        await aviso_no_ticket(
            self.canal, f"✏️ {interaction.user.mention} renomeou o ticket."
        )
        await registrar(
            interaction.guild,
            "✏️ Ticket Renomeado",
            f"{interaction.user.mention}: `{antigo}` → {self.canal.mention}",
        )


class AvisoDMModal(discord.ui.Modal, title="Avisar usuário por DM"):
    mensagem = discord.ui.TextInput(
        label="Mensagem para o usuário",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Precisamos de mais informações no seu ticket.",
        max_length=800,
    )

    def __init__(self, canal):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        t = ler_ticket(self.canal)
        dono = await buscar_membro(interaction.client, interaction.guild, t["owner"])
        if not dono:
            return await interaction.response.send_message(
                "❌ Não encontrei o usuário.", ephemeral=True
            )
        embed = discord.Embed(
            title=f"📨 Aviso da equipe — {NOME_SERVIDOR}",
            description=f"{self.mensagem}\n\n➡️ Acesse seu ticket: {self.canal.mention}",
            color=COR_AZUL,
            timestamp=datetime.now(FUSO),
        )
        embed.set_footer(text=f"Enviado por {interaction.user.display_name}")
        try:
            await dono.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.response.send_message(
                "❌ O usuário está com a DM fechada.", ephemeral=True
            )
        await interaction.response.send_message("✅ DM enviada!", ephemeral=True)
        await aviso_no_ticket(
            self.canal, f"📨 {interaction.user.mention} avisou o usuário por DM."
        )


class NotaInternaModal(discord.ui.Modal, title="Nota interna (só staff)"):
    texto = discord.ui.TextInput(
        label="Anotação",
        style=discord.TextStyle.paragraph,
        placeholder="Visível apenas nos logs da staff.",
        max_length=400,
    )

    def __init__(self, canal):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        t = ler_ticket(self.canal)
        notas = list(t.get("notas", []))
        notas.append(
            {
                "autor": interaction.user.display_name,
                "texto": str(self.texto),
                "data": agora(),
            }
        )
        salvar_estado(self.canal.id, notas=notas)
        await interaction.response.send_message(
            "📝 Nota salva! Ela aparece só no log da staff ao fechar o ticket.",
            ephemeral=True,
        )


class PainelTicketView(discord.ui.View):
    def __init__(self, canal: discord.TextChannel):
        super().__init__(timeout=600)
        self.canal = canal
        t = ler_ticket(canal)
        self.btn_trancar.label = "Destrancar" if t.get("locked") else "Trancar"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if eh_staff(interaction.user):
            return True
        await interaction.response.send_message("❌ Apenas a equipe.", ephemeral=True)
        return False

    # ── Linha 0: prioridade ──
    @discord.ui.select(
        placeholder="🚦 Definir prioridade",
        row=0,
        options=[
            discord.SelectOption(label=n, value=k, emoji=e)
            for k, (e, n) in PRIORIDADES.items()
        ],
    )
    async def sel_prioridade(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        valor = select.values[0]
        emoji, nome = PRIORIDADES[valor]
        salvar_estado(self.canal.id, prio=valor)
        await atualizar_card(self.canal)
        await interaction.response.send_message(
            f"✅ Prioridade: {emoji} **{nome}**", ephemeral=True
        )
        await aviso_no_ticket(
            self.canal,
            f"🚦 {interaction.user.mention} definiu a prioridade como "
            f"{emoji} **{nome}**.",
        )
        await registrar(
            interaction.guild,
            "🚦 Prioridade Alterada",
            f"{interaction.user.mention} → {emoji} {nome} em {self.canal.mention}",
        )

    # ── Linha 1: adicionar membro ──
    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="➕ Adicionar membro ao ticket",
        min_values=1,
        max_values=5,
        row=1,
    )
    async def sel_adicionar(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        adicionados = []
        for u in select.values:
            m = u if isinstance(u, discord.Member) else interaction.guild.get_member(u.id)
            if not m or m.bot:
                continue
            await self.canal.set_permissions(
                m,
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            )
            adicionados.append(m.mention)
        if not adicionados:
            return await interaction.response.send_message(
                "❌ Nenhum membro válido selecionado.", ephemeral=True
            )
        await interaction.response.send_message("✅ Adicionado(s)!", ephemeral=True)
        await aviso_no_ticket(
            self.canal,
            f"➕ {interaction.user.mention} adicionou {', '.join(adicionados)} "
            "ao ticket.",
            discord.Color.green().value,
        )
        await registrar(
            interaction.guild,
            "➕ Membro Adicionado",
            f"{interaction.user.mention} adicionou {', '.join(adicionados)} "
            f"em {self.canal.mention}",
        )

    # ── Linha 2: remover membro ──
    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="➖ Remover membro do ticket",
        min_values=1,
        max_values=5,
        row=2,
    )
    async def sel_remover(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        t = ler_ticket(self.canal)
        removidos = []
        for u in select.values:
            if u.id == t.get("owner"):
                continue
            m = u if isinstance(u, discord.Member) else interaction.guild.get_member(u.id)
            if not m:
                continue
            await self.canal.set_permissions(m, overwrite=None)
            removidos.append(m.mention)
        if not removidos:
            return await interaction.response.send_message(
                "❌ Nenhum membro removível (quem abriu o ticket não pode ser "
                "removido).",
                ephemeral=True,
            )
        await interaction.response.send_message("✅ Removido(s)!", ephemeral=True)
        await aviso_no_ticket(
            self.canal,
            f"➖ {interaction.user.mention} removeu {', '.join(removidos)} do ticket.",
            discord.Color.red().value,
        )
        await registrar(
            interaction.guild,
            "➖ Membro Removido",
            f"{interaction.user.mention} removeu {', '.join(removidos)} "
            f"de {self.canal.mention}",
        )

    # ── Linha 3: transferir atendimento ──
    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="🔁 Transferir atendimento para...",
        min_values=1,
        max_values=1,
        row=3,
    )
    async def sel_transferir(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        alvo = select.values[0]
        if not eh_staff(alvo):
            return await interaction.response.send_message(
                "❌ Só é possível transferir para alguém da equipe.", ephemeral=True
            )
        salvar_estado(self.canal.id, claim=alvo.id)
        await atualizar_card(self.canal)
        await interaction.response.send_message("✅ Transferido!", ephemeral=True)
        await aviso_no_ticket(
            self.canal,
            f"🔁 {interaction.user.mention} transferiu o atendimento para "
            f"{alvo.mention}.",
            discord.Color.blurple().value,
        )
        await registrar(
            interaction.guild,
            "🔁 Atendimento Transferido",
            f"{interaction.user.mention} → {alvo.mention} em {self.canal.mention}",
        )

    # ── Linha 4: botões ──
    @discord.ui.button(label="Renomear", emoji="✏️", style=discord.ButtonStyle.secondary, row=4)
    async def btn_renomear(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(RenomearModal(self.canal))

    @discord.ui.button(label="Trancar", emoji="🔐", style=discord.ButtonStyle.secondary, row=4)
    async def btn_trancar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        t = ler_ticket(self.canal)
        dono = await buscar_membro(interaction.client, interaction.guild, t["owner"])
        if not isinstance(dono, discord.Member):
            return await interaction.response.send_message(
                "❌ O usuário não está mais no servidor.", ephemeral=True
            )
        trancar = not t.get("locked")
        ow = self.canal.overwrites_for(dono)
        ow.send_messages = not trancar
        await self.canal.set_permissions(dono, overwrite=ow)
        salvar_estado(self.canal.id, locked=trancar)
        await atualizar_card(self.canal)
        button.label = "Destrancar" if trancar else "Trancar"
        await interaction.response.edit_message(view=self)
        await aviso_no_ticket(
            self.canal,
            f"🔒 {interaction.user.mention} **trancou** o ticket. "
            "Você não pode enviar mensagens por enquanto."
            if trancar
            else f"🔓 {interaction.user.mention} **destrancou** o ticket.",
            discord.Color.orange().value if trancar else discord.Color.green().value,
        )
        await registrar(
            interaction.guild,
            "🔐 Ticket " + ("Trancado" if trancar else "Destrancado"),
            f"{interaction.user.mention} em {self.canal.mention}",
        )

    @discord.ui.button(label="Avisar DM", emoji="📨", style=discord.ButtonStyle.secondary, row=4)
    async def btn_dm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(AvisoDMModal(self.canal))

    @discord.ui.button(label="Nota", emoji="📝", style=discord.ButtonStyle.secondary, row=4)
    async def btn_nota(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(NotaInternaModal(self.canal))

    @discord.ui.button(label="Transcript", emoji="📄", style=discord.ButtonStyle.secondary, row=4)
    async def btn_transcript(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        t = ler_ticket(self.canal)
        pagina, total = await gerar_transcript_html(self.canal, t)
        await interaction.followup.send(
            content=f"📄 Transcript parcial ({total} mensagens):",
            file=discord.File(
                io.BytesIO(pagina.encode("utf-8")),
                filename=f"parcial_{self.canal.name}.html",
            ),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════
#                 EMBEDS DE ESTATÍSTICA / CONFIG / RANKING
# ════════════════════════════════════════════════════════════════


def embed_avaliacoes() -> discord.Embed | None:
    dados = _ler_json(F_AVALIACOES, [])
    if not dados:
        return None
    media = sum(d["nota"] for d in dados) / len(dados)
    por_staff: dict[int, list[int]] = {}
    por_cat: dict[str, list[int]] = {}
    for d in dados:
        por_staff.setdefault(d["staff"], []).append(d["nota"])
        por_cat.setdefault(d["categoria"], []).append(d["nota"])

    ranking = sorted(
        por_staff.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True
    )[:10]
    txt_staff = "\n".join(
        f"**{i}.** "
        + (f"<@{sid}>" if sid else "Sem atendente")
        + f" — {sum(n) / len(n):.2f} ⭐ ({len(n)})"
        for i, (sid, n) in enumerate(ranking, 1)
    )
    txt_cat = "\n".join(
        f"{CATEGORIAS.get(k, {}).get('emoji', '📁')} "
        f"{CATEGORIAS.get(k, {}).get('nome', k)} — "
        f"{sum(n) / len(n):.2f} ⭐ ({len(n)})"
        for k, n in por_cat.items()
    )
    embed = discord.Embed(
        title=f"🏆 Avaliações — {NOME_SERVIDOR}",
        description=f"**Média geral:** {media:.2f} / 5 ⭐\n"
        f"**Total de avaliações:** {len(dados)}",
        color=0xF1C40F,
    )
    embed.add_field(name="Ranking de atendentes", value=txt_staff, inline=False)
    embed.add_field(name="Por categoria", value=txt_cat or "—", inline=False)
    return embed


def embed_estatisticas(guild: discord.Guild) -> discord.Embed:
    abertos = listar_tickets(guild)
    historico = _ler_json(F_HISTORICO, [])
    avaliacoes = _ler_json(F_AVALIACOES, [])
    contador = _ler_json(F_CONTADOR, {"contador": 0}).get("contador", 0)

    inicio_dia = datetime.now(FUSO).replace(hour=0, minute=0, second=0, microsecond=0)
    fechados_hoje = sum(1 for h in historico if h.get("fechado_ts", 0) >= inicio_dia.timestamp())
    sem_atendente = sum(1 for _, t in abertos if not t.get("claim"))
    urgentes = sum(1 for _, t in abertos if t.get("prio") == "urgente")
    tempo_medio = (
        sum(h.get("duracao_seg", 0) for h in historico) / len(historico)
        if historico
        else 0
    )
    media_av = (
        sum(a["nota"] for a in avaliacoes) / len(avaliacoes) if avaliacoes else 0
    )

    por_cat = {k: 0 for k in CATEGORIAS}
    for _, t in abertos:
        if t.get("cat") in por_cat:
            por_cat[t["cat"]] += 1
    txt_cat = "\n".join(
        f"{c['emoji']} {c['nome']}: **{por_cat[k]}** aberto(s)"
        for k, c in CATEGORIAS.items()
    )

    embed = discord.Embed(title=f"📊 Estatísticas — {NOME_SERVIDOR}", color=COR_AZUL)
    embed.add_field(name="🎫 Criados (total)", value=str(contador), inline=True)
    embed.add_field(name="🟢 Abertos agora", value=str(len(abertos)), inline=True)
    embed.add_field(name="✅ Fechados (total)", value=str(len(historico)), inline=True)
    embed.add_field(name="📅 Fechados hoje", value=str(fechados_hoje), inline=True)
    embed.add_field(name="⏳ Sem atendente", value=str(sem_atendente), inline=True)
    embed.add_field(name="🔴 Urgentes", value=str(urgentes), inline=True)
    embed.add_field(
        name="⏱️ Tempo médio de ticket",
        value=formatar_duracao(tempo_medio) if historico else "—",
        inline=True,
    )
    embed.add_field(
        name="⭐ Nota média",
        value=f"{media_av:.2f} ({len(avaliacoes)})" if avaliacoes else "—",
        inline=True,
    )
    embed.add_field(name="📂 Por categoria", value=txt_cat, inline=False)
    return embed


def embed_lista_tickets(guild: discord.Guild) -> discord.Embed:
    abertos = listar_tickets(guild)
    ordem = {k: i for i, k in enumerate(reversed(list(PRIORIDADES)))}
    abertos.sort(key=lambda x: (ordem.get(x[1].get("prio", "normal"), 9), x[0].created_at))
    embed = discord.Embed(title="📋 Tickets Abertos", color=COR_AZUL)
    if not abertos:
        embed.description = "✨ Nenhum ticket aberto no momento."
        return embed
    linhas = []
    for canal, t in abertos[:20]:
        cat = CATEGORIAS.get(t.get("cat", ""), {})
        p_emoji = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])[0]
        atendente = f"🙋 <@{t['claim']}>" if t.get("claim") else "⏳ sem atendente"
        linhas.append(
            f"{p_emoji} {canal.mention} • {cat.get('emoji', '')} {cat.get('nome', '')} "
            f"• <@{t['owner']}> • {atendente} • <t:{int(canal.created_at.timestamp())}:R>"
        )
    embed.description = "\n".join(linhas)
    if len(abertos) > 20:
        embed.set_footer(text=f"+{len(abertos) - 20} ticket(s) não exibido(s)")
    return embed


def embed_config(guild: discord.Guild, bot: commands.Bot) -> discord.Embed:
    embed = discord.Embed(title="⚙️ Verificação da Configuração", color=COR_AZUL)

    # Categoria dos tickets
    if not CATEGORIA_TICKETS_ID:
        cat_txt = "⚠️ Não definida — usa a categoria do canal do painel"
    else:
        c = guild.get_channel(CATEGORIA_TICKETS_ID)
        cat_txt = (
            f"✅ **{c.name}**"
            if isinstance(c, discord.CategoryChannel)
            else f"❌ ID `{CATEGORIA_TICKETS_ID}` não é uma categoria deste servidor"
        )
    embed.add_field(name="📁 Categoria dos tickets", value=cat_txt, inline=False)

    # Canais
    def canal_txt(cid, opcional=False):
        if not cid:
            return "⚠️ Não definido" if opcional else "❌ Não definido"
        c = guild.get_channel(cid)
        return f"✅ {c.mention}" if c else f"❌ ID `{cid}` não encontrado"

    embed.add_field(name="📑 Canal de logs", value=canal_txt(CANAL_LOGS_ID), inline=True)
    embed.add_field(
        name="⭐ Canal de avaliações",
        value=canal_txt(CANAL_AVALIACOES_ID, True)
        if CANAL_AVALIACOES_ID
        else "ℹ️ Usa o canal de logs",
        inline=True,
    )

    # Cargos
    def cargos_txt(ids):
        if not ids:
            return "—"
        out = []
        for rid in ids:
            r = guild.get_role(rid)
            out.append(f"✅ {r.mention}" if r else f"❌ `{rid}` não encontrado")
        return "\n".join(out)

    embed.add_field(name="🛡️ Cargos staff", value=cargos_txt(CARGOS_STAFF), inline=False)
    if CARGOS_NOTIFICAR:
        embed.add_field(
            name="🔔 Cargos notificados", value=cargos_txt(CARGOS_NOTIFICAR), inline=False
        )

    # Categorias
    linhas = []
    for k, c in CATEGORIAS.items():
        banner = "✅" if banner_valido(c.get("banner")) else "⚠️ banner de exemplo"
        extra = ""
        if c.get("categoria_discord_id"):
            ok = isinstance(guild.get_channel(c["categoria_discord_id"]), discord.CategoryChannel)
            extra = " • categoria própria " + ("✅" if ok else "❌")
        linhas.append(
            f"{c['emoji']} **{c['nome']}** — banner {banner} • "
            f"{len(c.get('perguntas', []))} pergunta(s){extra}"
        )
    embed.add_field(name="📂 Categorias", value="\n".join(linhas), inline=False)
    embed.add_field(
        name="🖼️ Banner principal",
        value="✅" if banner_valido(BANNER_PRINCIPAL) else "⚠️ link de exemplo",
        inline=True,
    )

    # Permissões do bot
    exigidas = {
        "manage_channels": "Gerenciar Canais",
        "manage_roles": "Gerenciar Permissões/Cargos",
        "manage_messages": "Gerenciar Mensagens",
        "view_channel": "Ver Canais",
        "send_messages": "Enviar Mensagens",
        "embed_links": "Inserir Links",
        "attach_files": "Anexar Arquivos",
        "read_message_history": "Ler Histórico",
    }
    perms = guild.me.guild_permissions
    faltando = [nome for attr, nome in exigidas.items() if not getattr(perms, attr)]
    embed.add_field(
        name="🤖 Permissões do bot",
        value="✅ Tudo certo" if not faltando else "❌ Faltando: " + ", ".join(faltando),
        inline=True,
    )
    embed.add_field(
        name="👥 Intent Members",
        value="✅ Ativada" if bot.intents.members else "⚠️ Desativada (recomendado ativar)",
        inline=True,
    )
    return embed


# ════════════════════════════════════════════════════════════════
#                     PAINEL DA EQUIPE (global, persistente)
# ════════════════════════════════════════════════════════════════


class PainelStaffView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if eh_staff(interaction.user):
            return True
        await interaction.response.send_message(
            "❌ Apenas a equipe pode usar este painel.", ephemeral=True
        )
        return False

    @discord.ui.button(label="Tickets Abertos", emoji="📋", style=discord.ButtonStyle.primary, custom_id="sants_staff_lista", row=0)
    async def lista(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_lista_tickets(interaction.guild), ephemeral=True
        )

    @discord.ui.button(label="Estatísticas", emoji="📊", style=discord.ButtonStyle.primary, custom_id="sants_staff_stats", row=0)
    async def stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_estatisticas(interaction.guild), ephemeral=True
        )

    @discord.ui.button(label="Ranking", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="sants_staff_rank", row=1)
    async def ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = embed_avaliacoes()
        if not embed:
            return await interaction.response.send_message(
                "📭 Ainda não há avaliações.", ephemeral=True
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Configuração", emoji="⚙️", style=discord.ButtonStyle.secondary, custom_id="sants_staff_config", row=1)
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_config(interaction.guild, interaction.client), ephemeral=True
        )


# ════════════════════════════════════════════════════════════════
#                                  COG
# ════════════════════════════════════════════════════════════════


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketControls())
        self.bot.add_view(PainelStaffView())
        self.bot.add_dynamic_items(BotaoNota)
        self.monitorar.start()

    async def cog_unload(self):
        self.monitorar.cancel()

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "❌ Você não tem permissão para usar este comando.", delete_after=5
            )
        elif isinstance(
            error, (commands.MissingRequiredArgument, commands.BadArgument)
        ):
            await ctx.send(
                f"⚠️ Uso incorreto. Veja `{ctx.clean_prefix}ticketajuda`.",
                delete_after=7,
            )
        else:
            raise error

    # ── Monitoramento: alerta sem atendente + inatividade ───────
    @tasks.loop(minutes=5)
    async def monitorar(self):
        agora_utc = datetime.now(timezone.utc)
        for cid in list(estados().keys()):
            try:
                canal = self.bot.get_channel(int(cid))
                if canal is None:
                    remover_estado(cid)
                    continue
                if canal.id in CANAIS_FECHANDO:
                    continue
                t = ler_ticket(canal)
                if not t:
                    continue
                guild = canal.guild

                # 1) Ninguém assumiu
                if (
                    ALERTA_SEM_ATENDENTE_MINUTOS
                    and not t.get("claim")
                    and not t.get("alertado")
                    and (agora_utc - canal.created_at).total_seconds()
                    >= ALERTA_SEM_ATENDENTE_MINUTOS * 60
                ):
                    salvar_estado(canal.id, alertado=True)
                    ids = cargos_para_notificar(t.get("cat", "")) or list(CARGOS_STAFF)
                    await canal.send(
                        content=" ".join(f"<@&{r}>" for r in ids) or None,
                        embed=discord.Embed(
                            description="⏰ **Ticket sem atendente** há "
                            f"{ALERTA_SEM_ATENDENTE_MINUTOS}+ minutos. "
                            "Alguém pode assumir?",
                            color=0xE67E22,
                        ),
                        allowed_mentions=discord.AllowedMentions(roles=True),
                    )

                # 2) Inatividade
                if INATIVIDADE_AVISO_HORAS:
                    ultima = (
                        discord.utils.snowflake_time(canal.last_message_id)
                        if canal.last_message_id
                        else canal.created_at
                    )
                    parado = (agora_utc - ultima).total_seconds()
                    aviso_id = t.get("aviso_msg_id")
                    if aviso_id:
                        if canal.last_message_id != aviso_id:
                            salvar_estado(canal.id, aviso_msg_id=None)
                        elif (
                            INATIVIDADE_FECHAR_APOS_AVISO_HORAS
                            and parado >= INATIVIDADE_FECHAR_APOS_AVISO_HORAS * 3600
                        ):
                            asyncio.create_task(
                                fechar_ticket(
                                    self.bot,
                                    canal,
                                    guild.me,
                                    "Fechado automaticamente por inatividade.",
                                )
                            )
                    elif parado >= INATIVIDADE_AVISO_HORAS * 3600:
                        extra = (
                            f" Se ninguém responder em "
                            f"**{INATIVIDADE_FECHAR_APOS_AVISO_HORAS}h**, ele será "
                            "fechado automaticamente."
                            if INATIVIDADE_FECHAR_APOS_AVISO_HORAS
                            else ""
                        )
                        msg = await canal.send(
                            content=f"<@{t['owner']}>",
                            embed=discord.Embed(
                                description="💤 Este ticket está **parado** há "
                                f"{INATIVIDADE_AVISO_HORAS}h." + extra,
                                color=0x95A5A6,
                            ),
                        )
                        salvar_estado(canal.id, aviso_msg_id=msg.id)
            except Exception as e:  # noqa: BLE001 - o monitor nunca deve parar
                print(f"[tickets] erro no monitoramento: {e}")

    @monitorar.before_loop
    async def antes_monitorar(self):
        await self.bot.wait_until_ready()

    # ── Painéis ─────────────────────────────────────────────────
    @commands.command(name="painelticket")
    @apenas_staff()
    async def painelticket(self, ctx: commands.Context):
        """Cria o painel público de tickets no canal atual."""
        embed = discord.Embed(description=PAINEL_DESCRICAO, color=COR_AZUL)
        if banner_valido(BANNER_PRINCIPAL):
            embed.set_image(url=BANNER_PRINCIPAL)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=embed, view=TicketView())

    @commands.command(name="painelstaff")
    @apenas_staff()
    async def painelstaff(self, ctx: commands.Context):
        """Cria o painel de controle da equipe (use num canal privado)."""
        embed = discord.Embed(
            title=f"🛡️ Painel da Equipe — {NOME_SERVIDOR}",
            description=(
                "Controle rápido do sistema de tickets:\n\n"
                "📋 **Tickets Abertos** — lista por prioridade\n"
                "📊 **Estatísticas** — números gerais do atendimento\n"
                "🏆 **Ranking** — avaliações dos atendentes\n"
                "⚙️ **Configuração** — confere se os IDs e permissões estão certos\n\n"
                "*Dentro de cada ticket, use o botão* **🛠️ Painel Staff** *para "
                "prioridade, transferir, trancar, adicionar membros e mais.*"
            ),
            color=COR_AZUL,
        )
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=embed, view=PainelStaffView())

    @commands.command(name="configticket")
    @apenas_staff()
    async def configticket(self, ctx: commands.Context):
        """Verifica se IDs, cargos e permissões estão corretos."""
        await ctx.send(embed=embed_config(ctx.guild, self.bot))

    @commands.command(name="ticketajuda")
    @apenas_staff()
    async def ticketajuda(self, ctx: commands.Context):
        """Lista os comandos do sistema de tickets."""
        p = ctx.clean_prefix
        embed = discord.Embed(
            title="📖 Comandos de Tickets",
            description=(
                f"`{p}painelticket` — cria o painel público\n"
                f"`{p}painelstaff` — cria o painel da equipe\n"
                f"`{p}configticket` — verifica a configuração\n"
                f"`{p}avaliacoes` — ranking de avaliações\n"
                f"`{p}bloquear @membro [motivo]` — impede de abrir tickets\n"
                f"`{p}desbloquear @membro` — libera de novo\n\n"
                "**Dentro de um ticket:**\n"
                f"`{p}fechar [motivo]` • `{p}adicionar @membro` • "
                f"`{p}remover @membro` • `{p}renomear nome`"
            ),
            color=COR_AZUL,
        )
        await ctx.send(embed=embed)

    # ── Comandos dentro do ticket ───────────────────────────────
    def _eh_ticket(self, ctx: commands.Context) -> bool:
        return bool(ler_ticket(ctx.channel))

    @commands.command(name="fechar")
    @apenas_staff()
    async def fechar(self, ctx: commands.Context, *, motivo: str = "Não informado"):
        """Fecha o ticket atual por comando."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        await fechar_ticket(self.bot, ctx.channel, ctx.author, motivo)

    @commands.command(name="adicionar")
    @apenas_staff()
    async def adicionar(self, ctx: commands.Context, membro: discord.Member):
        """Adiciona um membro ao ticket atual."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        await ctx.channel.set_permissions(
            membro,
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        )
        await ctx.send(f"✅ {membro.mention} foi adicionado ao ticket.")

    @commands.command(name="remover")
    @apenas_staff()
    async def remover(self, ctx: commands.Context, membro: discord.Member):
        """Remove um membro do ticket atual."""
        t = ler_ticket(ctx.channel)
        if not t:
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        if t.get("owner") == membro.id:
            return await ctx.send(
                "❌ Não dá para remover quem abriu o ticket.", delete_after=5
            )
        await ctx.channel.set_permissions(membro, overwrite=None)
        await ctx.send(f"✅ {membro.mention} foi removido do ticket.")

    @commands.command(name="renomear")
    @apenas_staff()
    async def renomear(self, ctx: commands.Context, *, nome: str):
        """Renomeia o ticket atual."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        try:
            await asyncio.wait_for(ctx.channel.edit(name=nome[:90]), timeout=8)
        except asyncio.TimeoutError:
            return await ctx.send(
                "⏳ Limite do Discord: 2 renomeações a cada 10 minutos.",
                delete_after=8,
            )
        await ctx.send(f"✅ Ticket renomeado para **{nome[:90]}**.")

    # ── Avaliações / bloqueios ──────────────────────────────────
    @commands.command(name="avaliacoes")
    @apenas_staff()
    async def avaliacoes(self, ctx: commands.Context):
        """Mostra a média geral e o ranking de atendentes."""
        embed = embed_avaliacoes()
        if not embed:
            return await ctx.send("📭 Ainda não há avaliações.", delete_after=10)
        await ctx.send(embed=embed)

    @commands.command(name="bloquear")
    @apenas_staff()
    async def bloquear(
        self, ctx: commands.Context, membro: discord.Member, *, motivo: str = "Não informado"
    ):
        """Impede um membro de abrir tickets."""
        dados = _ler_json(F_BLOQUEIOS, {})
        dados[str(membro.id)] = {"motivo": motivo, "por": ctx.author.id, "data": agora()}
        _salvar_json(F_BLOQUEIOS, dados)
        await ctx.send(f"🚫 {membro.mention} não pode mais abrir tickets.\n**Motivo:** {motivo}")
        await registrar(
            ctx.guild,
            "🚫 Usuário Bloqueado de Tickets",
            f"{ctx.author.mention} bloqueou {membro.mention}\n**Motivo:** {motivo}",
            0xE74C3C,
        )

    @commands.command(name="desbloquear")
    @apenas_staff()
    async def desbloquear(self, ctx: commands.Context, membro: discord.Member):
        """Libera um membro bloqueado."""
        dados = _ler_json(F_BLOQUEIOS, {})
        if str(membro.id) not in dados:
            return await ctx.send("ℹ️ Esse membro não está bloqueado.", delete_after=6)
        dados.pop(str(membro.id))
        _salvar_json(F_BLOQUEIOS, dados)
        await ctx.send(f"✅ {membro.mention} pode abrir tickets novamente.")
        await registrar(
            ctx.guild,
            "✅ Usuário Desbloqueado",
            f"{ctx.author.mention} desbloqueou {membro.mention}",
            0x2ECC71,
        )

    # ── Membro saiu do servidor: fecha o ticket dele ────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        for canal, t in listar_tickets(member.guild):
            if t.get("owner") == member.id:
                await aviso_no_ticket(
                    canal,
                    "👋 O membro saiu do servidor. Este ticket será encerrado "
                    "automaticamente.",
                    discord.Color.orange().value,
                )
                asyncio.create_task(
                    fechar_ticket(
                        self.bot, canal, member.guild.me, "O membro saiu do servidor."
                    )
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))