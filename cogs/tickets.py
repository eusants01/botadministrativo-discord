import asyncio
import html
import io
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# ════════════════════════════════════════════════════════════════
#                     CONFIGURAÇÃO — FAMÍLIA SANT'S
# ════════════════════════════════════════════════════════════════

NOME_SERVIDOR = "Família Sant's"
FUSO = ZoneInfo("America/Sao_Paulo")

# IDs dos cargos que podem usar os comandos administrativos e atender tickets
CARGOS_STAFF = [
    1553944794957615175, 
    1553923854877990945, 
    1553832097255260260, 
    1553832097905377422,
    1553832098404499516
]

# Canal onde os logs (transcripts) de todos os tickets serão enviados
CANAL_LOGS_ID = 1555446279033589770

# Máximo de tickets abertos ao mesmo tempo por usuário
MAX_TICKETS_POR_USUARIO = 1

# Segundos de espera antes de apagar o canal após fechar
TEMPO_PARA_APAGAR = 5

# Arquivo que guarda o contador de tickets (ticket #0001, #0002...)
ARQUIVO_CONTADOR = "tickets_contador.json"

# Banner do painel principal (onde o usuário escolhe a categoria)
BANNER_PRINCIPAL = "https://i.imgur.com/link_do_banner_principal.jpg"

CATEGORIAS = {
    "suporte": {
        "nome": "Suporte",
        "emoji": "🛠️",
        "descricao": "Dúvidas e ajuda em geral",
        "cor": 0x3498DB,
        "banner": "https://i.imgur.com/link_do_banner_suporte.jpg",
        "mensagem": (
            "Olá, {usuario}! 👋\n\n"
            "Seja bem-vindo ao **Suporte da Família Sant's**.\n"
            "Descreva sua dúvida ou problema com o máximo de detalhes "
            "possível que a nossa equipe já vai te atender."
        ),
        "categoria_discord_id": None,  # ID da categoria do Discord (ou None)
        "cargos_ping": [],             # IDs de cargos a marcar (ou [])
    },
    "denuncia": {
        "nome": "Denúncia",
        "emoji": "🚨",
        "descricao": "Reportar jogadores ou comportamentos",
        "cor": 0xE74C3C,
        "banner": "https://i.imgur.com/link_do_banner_denuncia.jpg",
        "mensagem": (
            "Olá, {usuario}.\n\n"
            "Sua denúncia será tratada com **sigilo e seriedade**.\n"
            "Envie:\n"
            "• Nome/ID de quem você está denunciando\n"
            "• O que aconteceu\n"
            "• Provas (prints, vídeos, links)"
        ),
        "categoria_discord_id": None,
        "cargos_ping": [],
    },
    "cargos": {
        "nome": "Solicitar Cargos",
        "emoji": "🎖️",
        "descricao": "Peça um cargo dentro da Família",
        "cor": 0xF1C40F,
        "banner": "https://i.imgur.com/link_do_banner_cargos.jpg",
        "mensagem": (
            "Olá, {usuario}! 🎖️\n\n"
            "Para solicitar um cargo, informe:\n"
            "• Qual cargo você deseja\n"
            "• Por que você merece esse cargo\n"
            "• Seu tempo e atividade na Família"
        ),
        "categoria_discord_id": None,
        "cargos_ping": [],
    },
    "parceria": {
        "nome": "Parcerias",
        "emoji": "🤝",
        "descricao": "Assuntos sobre parcerias e alianças",
        "cor": 0x2ECC71,
        "banner": "https://i.imgur.com/link_do_banner_parceria.jpg",
        "mensagem": (
            "Olá, {usuario}! 🤝\n\n"
            "Que bom ter interesse em uma parceria com a **Família Sant's**.\n"
            "Envie o nome do seu servidor/grupo, o link de convite, "
            "quantidade de membros e o que você propõe."
        ),
        "categoria_discord_id": None,
        "cargos_ping": [],
    },
}

# ════════════════════════════════════════════════════════════════
#                           FUNÇÕES AUXILIARES
# ════════════════════════════════════════════════════════════════


def eh_staff(membro: discord.abc.User) -> bool:
    """True se o membro tiver algum dos cargos de staff configurados."""
    if not isinstance(membro, discord.Member):
        return False
    ids = {r.id for r in membro.roles}
    return any(c in ids for c in CARGOS_STAFF)


def apenas_staff():
    """Check para comandos: só cargos selecionados em CARGOS_STAFF."""

    async def predicate(ctx: commands.Context):
        if eh_staff(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def proximo_numero() -> int:
    dados = {"contador": 0}
    if os.path.exists(ARQUIVO_CONTADOR):
        try:
            with open(ARQUIVO_CONTADOR, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    dados["contador"] = int(dados.get("contador", 0)) + 1
    with open(ARQUIVO_CONTADOR, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    return dados["contador"]


def ler_topico(canal: discord.TextChannel) -> dict:
    """O tópico do canal guarda: owner=ID;cat=chave;claim=ID"""
    info = {}
    if canal.topic:
        for parte in canal.topic.split(";"):
            if "=" in parte:
                k, v = parte.split("=", 1)
                info[k.strip()] = v.strip()
    return info


def montar_topico(info: dict) -> str:
    return ";".join(f"{k}={v}" for k, v in info.items() if v)


def agora() -> str:
    return datetime.now(FUSO).strftime("%d/%m/%Y %H:%M:%S")


async def gerar_transcript_html(canal: discord.TextChannel, info: dict) -> str:
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
        if msg.embeds:
            extras += f'<div class="anexo">🧩 {len(msg.embeds)} embed(s)</div>'
            for e in msg.embeds:
                if e.title or e.description:
                    t = html.escape(e.title or "")
                    d = html.escape(e.description or "").replace("\n", "<br>")
                    extras += f'<div class="embed"><b>{t}</b><br>{d}</div>'
        linhas.append(
            f'<div class="msg"><img src="{msg.author.display_avatar.url}">'
            f'<div><span class="autor">{html.escape(str(msg.author))}</span> '
            f'<span class="hora">{hora}</span><br>{conteudo}{extras}</div></div>'
        )

    cat = CATEGORIAS.get(info.get("cat", ""), {}).get("nome", "—")
    return f"""<!DOCTYPE html>
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
Total de mensagens: {total} · Gerado em {agora()}</div>
{''.join(linhas)}
</body></html>"""


async def fechar_ticket(
    canal: discord.TextChannel, quem_fechou: discord.Member, motivo: str
):
    guild = canal.guild
    info = ler_topico(canal)
    dono_id = int(info["owner"]) if info.get("owner") else None
    dono = guild.get_member(dono_id) if dono_id else None
    cat = CATEGORIAS.get(info.get("cat", ""), {})
    assumido_por = f"<@{info['claim']}>" if info.get("claim") else "Ninguém"

    await canal.send(
        embed=discord.Embed(
            description=f"🔒 Ticket sendo fechado por {quem_fechou.mention}.\n"
            f"Gerando logs... o canal será apagado em **{TEMPO_PARA_APAGAR}s**.",
            color=discord.Color.orange(),
        )
    )

    conteudo = await gerar_transcript_html(canal, info)
    dados = conteudo.encode("utf-8")
    nome_arquivo = f"logs_{canal.name}.html"

    embed_log = discord.Embed(
        title="📑 Ticket Fechado",
        color=cat.get("cor", discord.Color.dark_grey().value),
        timestamp=datetime.now(FUSO),
    )
    embed_log.add_field(name="Ticket", value=f"`{canal.name}`", inline=True)
    embed_log.add_field(name="Categoria", value=cat.get("nome", "—"), inline=True)
    embed_log.add_field(
        name="Aberto por", value=dono.mention if dono else f"<@{dono_id}>", inline=True
    )
    embed_log.add_field(name="Fechado por", value=quem_fechou.mention, inline=True)
    embed_log.add_field(name="Assumido por", value=assumido_por, inline=True)
    embed_log.add_field(name="Motivo", value=motivo or "Não informado", inline=False)
    embed_log.set_footer(text=NOME_SERVIDOR)

    # Logs no canal de logs do servidor
    canal_logs = guild.get_channel(CANAL_LOGS_ID)
    if canal_logs:
        try:
            await canal_logs.send(
                embed=embed_log,
                file=discord.File(io.BytesIO(dados), filename=nome_arquivo),
            )
        except discord.HTTPException:
            pass

    # Logs na DM de quem abriu o ticket
    if dono:
        try:
            await dono.send(
                content=f"📑 Aqui estão os logs do seu ticket em **{NOME_SERVIDOR}**:",
                embed=embed_log,
                file=discord.File(io.BytesIO(dados), filename=nome_arquivo),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    await asyncio.sleep(TEMPO_PARA_APAGAR)
    try:
        await canal.delete(reason=f"Ticket fechado por {quem_fechou}")
    except discord.HTTPException:
        pass


# ════════════════════════════════════════════════════════════════
#                       VIEWS / MODAIS / COMPONENTES
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
        await fechar_ticket(interaction.channel, interaction.user, str(self.motivo))


class TicketControls(discord.ui.View):
    def __init__(self, assumido: bool = False):
        super().__init__(timeout=None)
        self.assumir.disabled = assumido

    @discord.ui.button(
        label="Assumir Ticket",
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
        info = ler_topico(interaction.channel)
        info["claim"] = str(interaction.user.id)
        await interaction.channel.edit(topic=montar_topico(info))
        await interaction.response.edit_message(view=TicketControls(assumido=True))
        await interaction.channel.send(
            embed=discord.Embed(
                description=f"🙋 {interaction.user.mention} assumiu este ticket e "
                f"vai te atender!",
                color=discord.Color.green(),
            )
        )

    @discord.ui.button(
        label="Fechar Ticket",
        style=discord.ButtonStyle.red,
        custom_id="sants_fechar_ticket",
        emoji="🔒",
    )
    async def fechar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        info = ler_topico(interaction.channel)
        eh_dono = info.get("owner") == str(interaction.user.id)
        if not (eh_dono or eh_staff(interaction.user)):
            return await interaction.response.send_message(
                "❌ Você não pode fechar este ticket.", ephemeral=True
            )
        await interaction.response.send_modal(MotivoFechamentoModal())


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=c["nome"], value=chave, description=c["descricao"], emoji=c["emoji"]
            )
            for chave, c in CATEGORIAS.items()
        ]
        super().__init__(
            placeholder="📩 Selecione a categoria do seu ticket...",
            options=options,
            custom_id="sants_ticket_select",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        chave = self.values[0]
        cat = CATEGORIAS[chave]

        # Reseta o menu para o usuário poder escolher a mesma opção de novo
        try:
            await interaction.message.edit(view=TicketView())
        except discord.HTTPException:
            pass

        # Limite de tickets por usuário
        abertos = [
            c
            for c in guild.text_channels
            if ler_topico(c).get("owner") == str(user.id)
        ]
        if len(abertos) >= MAX_TICKETS_POR_USUARIO:
            return await interaction.followup.send(
                f"❌ Você já possui um ticket aberto: {abertos[0].mention}",
                ephemeral=True,
            )

        # Permissões
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
                embed_links=True,
                attach_files=True,
            ),
        }
        for cargo_id in CARGOS_STAFF:
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

        # Categoria do Discord onde o canal vai ser criado
        categoria_discord = None
        if cat.get("categoria_discord_id"):
            categoria_discord = guild.get_channel(cat["categoria_discord_id"])
        if categoria_discord is None:
            categoria_discord = interaction.channel.category

        numero = proximo_numero()
        topico = montar_topico({"owner": user.id, "cat": chave})
        canal = await guild.create_text_channel(
            name=f"{chave}-{numero:04d}",
            category=categoria_discord,
            overwrites=overwrites,
            topic=topico,
            reason=f"Ticket de {user} ({cat['nome']})",
        )

        await interaction.followup.send(
            f"✅ Seu ticket foi criado: {canal.mention}", ephemeral=True
        )

        # Mensagem de boas-vindas da categoria com banner próprio
        embed = discord.Embed(
            title=f"{cat['emoji']} {cat['nome']} • Ticket #{numero:04d}",
            description=cat["mensagem"].format(usuario=user.mention),
            color=cat["cor"],
            timestamp=datetime.now(FUSO),
        )
        embed.set_image(url=cat["banner"])
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="👤 Aberto por", value=user.mention, inline=True)
        embed.add_field(name="📂 Categoria", value=cat["nome"], inline=True)
        embed.set_footer(text=f"{NOME_SERVIDOR} • Atendimento")

        pings = " ".join(f"<@&{r}>" for r in cat.get("cargos_ping", []))
        await canal.send(
            content=f"{user.mention} {pings}".strip(),
            embed=embed,
            view=TicketControls(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )

        # Log de abertura
        canal_logs = guild.get_channel(CANAL_LOGS_ID)
        if canal_logs:
            log = discord.Embed(
                title="📩 Ticket Aberto",
                description=f"{user.mention} abriu {canal.mention}\n"
                f"**Categoria:** {cat['nome']}",
                color=cat["cor"],
                timestamp=datetime.now(FUSO),
            )
            try:
                await canal_logs.send(embed=log)
            except discord.HTTPException:
                pass


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ════════════════════════════════════════════════════════════════
#                                 COG
# ════════════════════════════════════════════════════════════════


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Mantém os componentes funcionando após reiniciar o bot
        self.bot.add_view(TicketView())
        self.bot.add_view(TicketControls())

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "❌ Você não tem permissão para usar este comando.", delete_after=5
            )
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("⚠️ Uso incorreto do comando.", delete_after=5)
        else:
            raise error

    @commands.command(name="painelticket")
    @apenas_staff()
    async def painelticket(self, ctx: commands.Context):
        """Cria o painel de tickets no canal atual."""
        descricao = (
            f"Bem-vindo à **Central de Atendimento da {NOME_SERVIDOR}**!\n\n"
            "Escolha no menu abaixo a categoria que melhor combina com o "
            "seu assunto:\n\n"
        )
        for c in CATEGORIAS.values():
            descricao += f"{c['emoji']} **{c['nome']}** — {c['descricao']}\n"
        descricao += "\n⚠️ Abuso do sistema de tickets pode gerar punição."

        embed = discord.Embed(
            title=f"🏠 Central de Atendimento — {NOME_SERVIDOR}",
            description=descricao,
            color=0x2B2D31,
        )
        embed.set_image(url=BANNER_PRINCIPAL)
        embed.set_footer(text=f"{NOME_SERVIDOR} • Atendimento")

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=embed, view=TicketView())

    def _ticket_atual(self, ctx: commands.Context):
        info = ler_topico(ctx.channel)
        return info if info.get("owner") else None

    @commands.command(name="adicionar")
    @apenas_staff()
    async def adicionar(self, ctx: commands.Context, membro: discord.Member):
        """Adiciona um membro ao ticket atual."""
        if not self._ticket_atual(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        await ctx.channel.set_permissions(
            membro,
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
        )
        await ctx.send(f"✅ {membro.mention} foi adicionado ao ticket.")

    @commands.command(name="remover")
    @apenas_staff()
    async def remover(self, ctx: commands.Context, membro: discord.Member):
        """Remove um membro do ticket atual."""
        info = self._ticket_atual(ctx)
        if not info:
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        if info.get("owner") == str(membro.id):
            return await ctx.send(
                "❌ Não dá para remover quem abriu o ticket.", delete_after=5
            )
        await ctx.channel.set_permissions(membro, overwrite=None)
        await ctx.send(f"✅ {membro.mention} foi removido do ticket.")

    @commands.command(name="renomear")
    @apenas_staff()
    async def renomear(self, ctx: commands.Context, *, nome: str):
        """Renomeia o ticket atual."""
        if not self._ticket_atual(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        await ctx.channel.edit(name=nome[:90])
        await ctx.send(f"✅ Ticket renomeado para **{nome[:90]}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))