

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands


LOGGER = logging.getLogger("royal.historia")
BASE_DIR = Path(__file__).resolve().parent.parent
BANNER_PATH = BASE_DIR / "assets" / "historia_royal.png"
BANNER_NAME = "historia_royal.png"
COR_ROYAL = discord.Colour.from_rgb(187, 145, 81)



HISTORIA = (
    "## <a:coroa:1564000189167960177> NOSSA TRAJETÓRIA\n"
    "A **Família Royal** foi fundada em **28 de janeiro de 2026**, "
    "inicialmente sob o nome **Família Sant’s**, no E.B do DELTA, "
    "no Roblox. Idealizada por **Sant’s**, a Família nasceu com o "
    "propósito de reunir pessoas por meio da confiança, do respeito "
    "e do companheirismo.\n\n"

    "Em seus primeiros dias, a Família era composta apenas por "
    "**Sant’s**, **Bruna** e **Pinguim**, que participaram diretamente "
    "de sua formação inicial. Mesmo com poucos integrantes, foram "
    "estabelecidas as primeiras bases de uma comunidade que, "
    "posteriormente, passaria por importantes transformações.\n\n"

    "Com o desenvolvimento da Família, **Kael** passou a integrar "
    "o grupo e, em reconhecimento à sua participação e contribuição "
    "para sua consolidação, tornou-se um de seus fundadores. "
    "**Pinguim**, embora tenha feito parte das origens da Família, "
    "posteriormente se desligou de suas atividades, permanecendo "
    "como parte de sua trajetória histórica.\n\n"

    "Ao longo dos meses, a Família Sant’s ampliou sua presença, "
    "estabeleceu novos vínculos e enfrentou mudanças em sua "
    "estrutura. Após o encerramento de sua atuação no **E.B do DELTA**, "
    "encontrou no **E.B do ALPHA** a oportunidade de iniciar uma "
    "nova etapa, preservando os princípios estabelecidos desde "
    "sua fundação.\n\n"

    "Em **25 de outubro de 2026**, foi anunciada oficialmente a "
    "adoção do nome **Família Royal**, marcando um período de "
    "renovação de sua identidade, reorganização interna e "
    "fortalecimento dos integrantes oficiais.\n\n"

    "Atualmente, a **Família Royal** mantém suas atividades com "
    "o compromisso de valorizar seus membros, preservar sua história "
    "e desenvolver iniciativas que contribuam para o crescimento "
    "da comunidade. Independentemente das mudanças ocorridas ao "
    "longo do tempo, permanecem os princípios que fundamentaram "
    "sua criação: **lealdade, respeito e união**.\n\n"

    "*Família Royal — Diferentes histórias, o mesmo lar.*"
)

class HistoriaRoyal(commands.Cog):
    """Publica uma única mensagem com o banner e a história da Família."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def criar_painel() -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        painel = discord.ui.Container(accent_colour=COR_ROYAL)
        painel.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=f"attachment://{BANNER_NAME}")
            )
        )
        painel.add_item(discord.ui.TextDisplay(HISTORIA))
        painel.add_item(
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small)
        )
        painel.add_item(
            discord.ui.TextDisplay(
                "-# ✦ **Família Royal** • Fundada em 28/01/2026 • "
                "Diferentes histórias, o mesmo lar."
            )
        )
        view.add_item(painel)
        return view

    @commands.command(name="painelhistoria")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def publicar(
        self,
        ctx: commands.Context,
        canal: discord.TextChannel | None = None,
    ):
        """Uso: !painelhistoria #canal (ou sem canal para publicar no atual)."""
        destino = canal or ctx.channel
        if not isinstance(destino, discord.TextChannel):
            await ctx.reply(
                "❌ Escolha um canal de texto do servidor.",
                mention_author=False,
                delete_after=12,
            )
            return

        if not BANNER_PATH.is_file():
            await ctx.reply(
                f"❌ Banner não encontrado: `assets/{BANNER_NAME}`.",
                mention_author=False,
                delete_after=12,
            )
            return

        bot_membro = destino.guild.me
        if bot_membro is None and self.bot.user is not None:
            try:
                bot_membro = await destino.guild.fetch_member(self.bot.user.id)
            except discord.HTTPException:
                bot_membro = None
        if bot_membro is None:
            await ctx.reply(
                "❌ Não foi possível verificar as permissões do bot.",
                mention_author=False,
                delete_after=12,
            )
            return

        perms = destino.permissions_for(bot_membro)
        if not (perms.view_channel and perms.send_messages and perms.attach_files):
            await ctx.reply(
                "❌ Preciso das permissões **Ver canal**, **Enviar mensagens** "
                "e **Anexar arquivos** no canal escolhido.",
                mention_author=False,
                delete_after=12,
            )
            return

        try:
            with BANNER_PATH.open("rb") as imagem:
                await destino.send(
                    view=self.criar_painel(),
                    file=discord.File(imagem, filename=BANNER_NAME),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException:
            LOGGER.exception("Falha ao publicar história no canal %s", destino.id)
            await ctx.reply(
                "❌ Não foi possível publicar a história. Confira as permissões "
                "e os logs do bot.",
                mention_author=False,
                delete_after=12,
            )
            return

        LOGGER.info("História Royal publicada no canal %s", destino.id)
        if ctx.channel.id != destino.id:
            await ctx.reply(
                f"✅ História publicada em {destino.mention}.",
                mention_author=False,
                delete_after=12,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(HistoriaRoyal(bot))
