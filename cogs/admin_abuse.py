
from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger("royal.admin_abuse")

FAMILIA_GUILD_ID = 1553803921514963075
CANAL_DROPS_URL = "https://discord.com/channels/1553803921514963075/1553820479582769323"
BANNER = Path(__file__).resolve().parent.parent / "assets" / "admin_abuse_royal.png"
COR_ROYAL = discord.Colour.from_rgb(212, 175, 55)


class AnuncioAdminAbuse(discord.ui.LayoutView):
    """Painel de anúncio com banner, texto e botão de link."""

    def __init__(self):
        super().__init__(timeout=None)

        painel = discord.ui.Container(accent_colour=COR_ROYAL)
        painel.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=f"attachment://{BANNER.name}")
            )
        )
        painel.add_item(
            discord.ui.TextDisplay(
                "# <a:coroa:1564000189167960177> FAMÍLIA ROYAL | **EVENTO CAOS**\n"
                "A Família Royal tem o prazer de anunciar um dos eventos mais "
                "insanos já preparados para a nossa comunidade: **ADMIN ABUSE!** 🔥\n\n"
                "Preparem-se para uma tarde de caos, diversão, surpresas e "
                "premiações especiais! Durante o evento, a administração estará "
                "liberando recompensas exclusivas para os participantes."
            )
        )
        painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        painel.add_item(
            discord.ui.TextDisplay(
                "### <:versustrophy:1564669597440016485> Informações Básicas\n"
                "> - `📅` **Data:** Domingo, 08 de novembro de 2026  \n"
                "> - `⏰` **Horário:** 14h00  \n"
                "> - `🤔` **Onde:** Drops que serão lançados em "
                f"[dropzinhos]({CANAL_DROPS_URL})"
            )
        )
        painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        painel.add_item(
            discord.ui.TextDisplay(
                "### <a:Presenteghost:1553872045492797550> Possíveis Premiações\n"
                "> - `🎖️` **Candidato Divisional**: Qualquer divisão no jogo.\n"
                "> - `🤡` **Cargo exclusivo**: <@&1553837456585920624>\n"
                "> - `👑` **Vaga na Família**\n"
                "> - `💰` **Robux**"
            )
        )
        painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        painel.add_item(
            discord.ui.TextDisplay(
                "### ⚠️ Observações Importantes\n"
                "> - `🎲` A premiação de **Candidato Divisional** exige, "
                "obrigatoriamente, a patente mínima de **Aspirante a Oficial**.\n"
                "> - `🎲` A participação no evento não garante o recebimento de premiações.\n"
                "> - `🎲` Todas as recompensas estarão sujeitas a alterações."
            )
        )
        painel.add_item(
            discord.ui.ActionRow(
                discord.ui.Button(
                    label="Acessar canal de drops",
                    emoji="🎁",
                    style=discord.ButtonStyle.link,
                    url=CANAL_DROPS_URL,
                )
            )
        )
        painel.add_item(
            discord.ui.TextDisplay("-# 👑 Família Royal • Honra · União · Lealdade")
        )
        self.add_item(painel)


class AdminAbuse(commands.Cog):
    """Publicação do ADMIN ABUSE exclusivamente por comando de prefixo (!)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="admin_abuse", aliases=["adminabuse", "eventoabuse"])
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def admin_abuse(
        self,
        ctx: commands.Context,
        canal: discord.TextChannel,
        fixar: str = "nao",
    ):
        """!admin_abuse #canal [sim|nao] — publica o painel oficial."""

        fixar_normalizado = fixar.casefold().strip()
        positivos = {"sim", "s", "yes", "y", "true", "1"}
        negativos = {"nao", "não", "n", "no", "false", "0"}
        if fixar_normalizado not in positivos | negativos:
            await ctx.send(
                "❌ Para fixar o anúncio, informe `sim` ou `nao`.\n"
                "**Exemplo:** `!admin_abuse #anuncios sim`"
            )
            return
        deve_fixar = fixar_normalizado in positivos

        if ctx.guild is None or ctx.guild.id != FAMILIA_GUILD_ID:
            await ctx.send("❌ Este anúncio foi configurado apenas para a Família Royal.")
            return

        if canal.guild.id != FAMILIA_GUILD_ID:
            await ctx.send("❌ O canal escolhido não pertence ao servidor da Família Royal.")
            return

        if not BANNER.is_file():
            await ctx.send(
                "❌ Banner não encontrado em `assets/admin_abuse_royal.png`. "
                "Coloque a imagem nessa pasta e tente novamente."
            )
            return

        me = canal.guild.me
        if me is None and self.bot.user is not None:
            me = canal.guild.get_member(self.bot.user.id)
        if me is None and self.bot.user is not None:
            try:
                me = await canal.guild.fetch_member(self.bot.user.id)
            except discord.HTTPException:
                LOG.exception("Falha ao consultar permissões do bot no servidor %s", canal.guild.id)
        if me is None:
            await ctx.send("❌ Não consegui consultar minhas permissões neste servidor.")
            return

        perms = canal.permissions_for(me)
        if not (perms.view_channel and perms.send_messages and perms.attach_files):
            await ctx.send(
                "❌ Preciso das permissões **Ver Canal**, **Enviar Mensagens** "
                "e **Anexar Arquivos** no canal escolhido."
            )
            return

        try:
            with BANNER.open("rb") as arquivo:
                msg = await canal.send(
                    view=AnuncioAdminAbuse(),
                    file=discord.File(arquivo, filename=BANNER.name),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (OSError, discord.HTTPException):
            LOG.exception("Não foi possível publicar o ADMIN ABUSE em %s", canal.id)
            await ctx.send("❌ Não foi possível publicar o evento. Confira os logs do bot.")
            return

        fixado = False
        if deve_fixar:
            try:
                await msg.pin(reason="Anúncio oficial do evento ADMIN ABUSE — Família Royal")
                fixado = True
            except discord.HTTPException:
                LOG.warning("Não foi possível fixar o anúncio %s", msg.id, exc_info=True)

        extra = (
            " • 📌 Anúncio fixado."
            if fixado
            else " • ⚠️ Publicado, mas não foi possível fixar."
            if deve_fixar
            else ""
        )
        await ctx.send(
            f"✅ Anúncio publicado em {canal.mention}!\n"
            f"🔗 [Abrir anúncio]({msg.jump_url}){extra}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @admin_abuse.error
    async def admin_abuse_error(self, ctx: commands.Context, erro: commands.CommandError):
        """Mensagens claras para os erros mais comuns dos comandos com prefixo."""
        if isinstance(erro, commands.MissingPermissions):
            await ctx.send("⛔ Somente membros com **Gerenciar Servidor** podem publicar o evento.")
        elif isinstance(erro, commands.NoPrivateMessage):
            await ctx.send("❌ Use este comando em um canal do servidor.")
        elif isinstance(erro, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(
                "❌ Uso correto: `!admin_abuse #canal [sim|nao]`\n"
                "**Exemplo:** `!admin_abuse #anuncios sim`"
            )
        else:
            LOG.error(
                "Erro inesperado no comando !admin_abuse",
                exc_info=(type(erro), erro, erro.__traceback__),
            )
            await ctx.send("❌ Ocorreu um erro inesperado. Consulte os logs do bot.")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminAbuse(bot))
