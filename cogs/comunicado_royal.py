# -*- coding: utf-8 -*-

import logging
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.comunicado_royal")
ROOT = Path(__file__).resolve().parent.parent
BANNERS = [ROOT / "assets" / "anuncio_royal.png", ROOT / "assets" / "boas_vindas_royal.png"]


def criar_view(incluir_banner: bool) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    painel = discord.ui.Container(accent_colour=discord.Colour.from_rgb(187, 149, 82))
    if incluir_banner:
        painel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media="attachment://anuncio_royal.png")
        ))

    painel.add_item(discord.ui.TextDisplay(
        "# <a:coroa:1564000189167960177> ・COMUNICADO OFICIAL"
    ))
    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    painel.add_item(discord.ui.TextDisplay(
        "*Após um longo período utilizando o nome **__Família Sant's__**, "
        "comunico oficialmente a adoção da nova denominação "
        "**[Família Royal](https://discord.com/channels/1553803921514963075/1559309668499591218)**.*\n\n"
        "*A decisão marca uma nova etapa de modernização da nossa identidade, "
        "preservando a história, os valores e as conquistas construídas "
        "desde nossa fundação, em **28 de janeiro de 2026**.*"
    ))
    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    painel.add_item(discord.ui.TextDisplay(
        "**`⚙️` MODERNIZAÇÃO DO BOT OFICIAL**\n"
        "Iniciaremos uma nova fase de desenvolvimento do nosso bot, contemplando:\n\n"
        "> `📜` Novos comandos públicos para os membros.\n"
        "> `📜` Sistema de moderação automática (**AutoMod**).\n"
        "> `📜` Aprimoramento dos sistemas existentes.\n"
        "> `📜` Novas ferramentas e funcionalidades interativas."
    ))
    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    painel.add_item(discord.ui.TextDisplay(
        "**`⚜️` NOVAS PRIORIDADES DA FAMÍLIA**\n"
        "*Nossa principal prioridade será a **valorização dos membros**, "
        "com foco em benefícios, reconhecimento e novas oportunidades "
        "tanto no servidor do **E.B do ALPHA** quanto em nosso servidor oficial.*\n\n"
        "*Estabelecemos também a meta de **ampliar o quadro da Família para 20 membros "
        "até o final de 2026**, priorizando o comprometimento, a participação "
        "e a integração dos novos integrantes.*\n\n"
        "*Os **membros oficiais (OFC)** contarão, em breve, com benefícios e "
        "vantagens exclusivas, que serão anunciados oportunamente.*"
    ))
    painel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    painel.add_item(discord.ui.TextDisplay(
        "**`🪽` CONSIDERAÇÕES FINAIS**\n"
        "*A mudança não altera nossa essência, nossos princípios ou nossa atuação "
        "no **[E.B do ALPHA](https://discord.com/channels/1545550460419575918/1545550464651894898)**. "
        "Trata-se de uma reformulação voltada ao crescimento e à valorização da comunidade.*\n\n"
        "*O tema de Cuphead ficará temporariamente em segundo plano, enquanto o "
        "desenvolvimento do Expresso Fantasma será descontinuado, permitindo "
        "direcionar nossos esforços às novas prioridades.*"
    ))
    view.add_item(painel)
    return view


class ComunicadoRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def enviar(self, channel: discord.TextChannel) -> discord.Message:
        me = channel.guild.me
        if me is None and self.bot.user is not None:
            me = await channel.guild.fetch_member(self.bot.user.id)
        if me is None:
            raise RuntimeError("Não foi possível consultar as permissões do bot.")
        perms = channel.permissions_for(me)
        if not (perms.view_channel and perms.send_messages):
            raise RuntimeError("Faltam permissões Ver Canal ou Enviar Mensagens.")

        banner = next((p for p in BANNERS if p.is_file()), None)
        if banner and not perms.attach_files:
            raise RuntimeError("Falta a permissão Anexar Arquivos.")
        view = criar_view(banner is not None)
        if banner is None:
            logger.warning("Banner não encontrado em %s", BANNERS)
            return await channel.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        with banner.open("rb") as f:
            return await channel.send(
                view=view,
                file=discord.File(f, filename="anuncio_royal.png"),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def executar(self, ctx: commands.Context, channel: discord.TextChannel):
        try:
            message = await self.enviar(channel)
        except (discord.HTTPException, RuntimeError, OSError, ValueError) as exc:
            logger.exception("Falha ao publicar comunicado Royal")
            await ctx.reply(f"❌ Erro: {str(exc)[:300]}", mention_author=False)
            return
        await ctx.reply(f"✅ Comunicado enviado: {message.jump_url}", mention_author=False)

    @commands.command(name="previacomunicado")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def previa(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.reply("❌ Use o comando em um canal de texto.", mention_author=False)
            return
        await self.executar(ctx, ctx.channel)

    @commands.command(name="anuncioroyal")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def publicar(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.executar(ctx, channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(ComunicadoRoyal(bot))
