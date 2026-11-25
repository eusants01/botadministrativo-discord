

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

LOG = logging.getLogger("royal.admin_abuse")

FAMILIA_GUILD_ID = 1553803921514963075
CANAL_DROPS_URL = (
    "https://discord.com/channels/1553803921514963075/1553820479582769323"
)
BANNER = Path(__file__).resolve().parent.parent / "assets" / "admin_abuse_royal.png"
COR_ROYAL = discord.Colour.from_rgb(212, 175, 55)


class AnuncioAdminAbuse(discord.ui.LayoutView):
    """Anúncio estático com banner e botão de link (não exige persistência)."""

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
        painel.add_item(discord.ui.TextDisplay("-# 👑 Família Royal • Honra · União · Lealdade"))
        self.add_item(painel)


class AdminAbuse(commands.Cog):
    """Publicação do evento Royal por slash command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="admin_abuse",
        description="Publica o banner e o anúncio do evento ADMIN ABUSE.",
    )
    @app_commands.describe(
        canal="Canal onde o anúncio deve ser publicado",
        fixar="Fixar a publicação no canal? (opcional)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def admin_abuse(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        fixar: bool = False,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild_id != FAMILIA_GUILD_ID:
            return await interaction.followup.send(
                "❌ Este anúncio foi configurado apenas para a Família Royal.",
                ephemeral=True,
            )

        if canal.guild.id != FAMILIA_GUILD_ID:
            return await interaction.followup.send(
                "❌ O canal escolhido não pertence ao servidor da Família Royal.",
                ephemeral=True,
            )

        if not BANNER.is_file():
            return await interaction.followup.send(
                "❌ Banner não encontrado em `assets/admin_abuse_royal.png`. "
                "Coloque a imagem nessa pasta e tente novamente.",
                ephemeral=True,
            )

        me = canal.guild.me
        if me is None and self.bot.user is not None:
            me = canal.guild.get_member(self.bot.user.id)
        if me is None:
            return await interaction.followup.send(
                "❌ Não consegui consultar minhas permissões neste servidor.",
                ephemeral=True,
            )

        perms = canal.permissions_for(me)
        if not (perms.view_channel and perms.send_messages and perms.attach_files):
            return await interaction.followup.send(
                "❌ Preciso das permissões **Ver Canal**, **Enviar Mensagens** "
                "e **Anexar Arquivos** no canal escolhido.",
                ephemeral=True,
            )

        try:
            with BANNER.open("rb") as arquivo:
                msg = await canal.send(
                    view=AnuncioAdminAbuse(),
                    file=discord.File(arquivo, filename=BANNER.name),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (OSError, discord.HTTPException):
            LOG.exception("Não foi possível publicar o ADMIN ABUSE em %s", canal.id)
            return await interaction.followup.send(
                "❌ Não foi possível publicar o evento. Confira os logs do bot.",
                ephemeral=True,
            )

        fixado = False
        if fixar:
            try:
                await msg.pin(reason="Anúncio oficial do evento ADMIN ABUSE — Família Royal")
                fixado = True
            except discord.HTTPException:
                LOG.warning("Não foi possível fixar o anúncio %s", msg.id, exc_info=True)

        extra = " • 📌 Anúncio fixado." if fixado else (
            " • ⚠️ Publicado, mas não foi possível fixar." if fixar else ""
        )
        await interaction.followup.send(
            f"✅ Anúncio publicado em {canal.mention}!\n"
            f"🔗 [Abrir anúncio]({msg.jump_url}){extra}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminAbuse(bot))
