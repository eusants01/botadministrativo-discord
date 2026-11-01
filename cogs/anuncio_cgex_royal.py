"""Comunicado oficial da Central CGEx da Família Royal.

Módulo isolado: preserva todos os comandos, configurações, IDs e emojis dos outros cogs.
Publicação única por servidor, com menção @everyone autorizada apenas na ação de publicar.

!previacgex                     -> prévia no privado, sem notificar ninguém.
!anunciocgex #canal             -> publica o comunicado e @everyone uma vez.
!anunciocgex #canal republicar  -> permite uma nova publicação intencional.
"""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger("royal.cgex.anuncio")
ROOT = Path(__file__).resolve().parent.parent
BANNER = ROOT / "assets" / "anuncio_cgex_royal.png"
BANNER_FILENAME = "anuncio_cgex_royal.png"
COR_DOURADA = discord.Colour.from_rgb(212, 175, 55)

CANAL_CGEX = 1566470789178331286
BOT_ASSISTENTE_ID = 1554370626343542784

# Opcional: deixe 0 para escolher o canal através da menção #canal no comando.
# Não foi definido um ID fixo para anúncios administrativos, pois ele não
# consta das informações disponíveis e não deve ser presumido.
CANAL_ANUNCIOS_ADMIN_ID = 0


# Textos oficiais fornecidos pela Diretoria da Família Royal.
# Corrigido apenas o lapso "inteligente teste, interativo" -> "inteligente, interativo".
CABECALHO = (
    "# <:CGEx:1560374896138256524>・CENTRAL CGEx\n"
    "**ASSISTENTE INSTITUCIONAL ROYAL**"
)

INTRODUCAO = (
    "A **Diretoria da Família Royal** tem a satisfação de anunciar a implementação "
    "de um novo sistema de assistência institucional, desenvolvido especialmente "
    "para fortalecer a comunicação e a cooperação com os integrantes da "
    "**Corregedoria-Geral do Exército (CGEx)** do E.B do ALPHA.\n\n"
    "Com a chegada do **Assistente Royal**, os representantes autorizados da "
    "Corregedoria passam a contar com um atendimento inteligente, interativo "
    "e integrado aos nossos sistemas administrativos."
)

FUNCIONALIDADES = (
    "**<:escudeiro:1566331170914959402>・FUNCIONALIDADES DISPONÍVEIS**\n"
    "> `🔍` Acompanhamento Administrativo\n"
    "> `🔍` Assistência Inteligente\n"
    "> `🔍` Integração Institucional"
)

ATENDIMENTO = (
    "**<:duque:1566331234110410762>・COMUNICAÇÃO E ATENDIMENTO**\n"
    "O Assistente Royal também foi desenvolvido para proporcionar uma experiência "
    "mais próxima e dinâmica, podendo interagir com os representantes da CGEx, "
    "responder dúvidas, participar de conversas e realizar comunicações "
    "institucionais periódicas.\n\n"
    f"Para utilizá-lo, basta mencionar <@{BOT_ASSISTENTE_ID}> no canal "
    f"<#{CANAL_CGEX}> ou consultar suas funcionalidades por meio do comando `!cgex`."
)

CONSIDERACOES = (
    "**<:cavalheiroreal:1566331202737152091>・DISPOSIÇÕES FINAIS**\n"
    "> `⚜️` Ressaltamos que os procedimentos de banimento permanecem sujeitos à "
    "apresentação de comprovação e à análise de um representante autorizado "
    "da Diretoria, garantindo maior segurança, transparência e responsabilidade "
    "administrativa.\n\n"
    "> `⚜️` Esta implementação representa mais um avanço no processo de modernização "
    "da Família Royal e reafirma nosso compromisso com a organização, a inovação "
    "e o fortalecimento das relações institucionais."
)


def criar_anuncio() -> discord.ui.LayoutView:
    """Um único painel V2, com banner, conteúdo e @everyone explícito."""
    view = discord.ui.LayoutView(timeout=None)
    caixa = discord.ui.Container(accent_colour=COR_DOURADA)
    if BANNER.is_file():
        caixa.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{BANNER_FILENAME}")
        ))
    caixa.add_item(discord.ui.TextDisplay(
        "@everyone\n" + CABECALHO
    ))
    for texto in (INTRODUCAO, FUNCIONALIDADES, ATENDIMENTO, CONSIDERACOES):
        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        caixa.add_item(discord.ui.TextDisplay(texto))
    caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    caixa.add_item(discord.ui.TextDisplay(
        "-# <a:coroa:1564000189167960177> Família Royal • Honra · União · Lealdade"
    ))
    view.add_item(caixa)
    return view


def mencoes_para_envio(*, publicar: bool) -> discord.AllowedMentions:
    """Somente @everyone no anúncio; sem pingar o bot ou cargos por acidente."""
    return discord.AllowedMentions(
        everyone=publicar, users=False, roles=False, replied_user=False
    )


class AnuncioCGExRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def pool(self):
        return getattr(self.bot, "pool", None)

    async def cog_load(self):
        pool = self.pool()
        if pool is None:
            LOG.warning("Anúncio CGEx: PostgreSQL ainda indisponível; publicação ficará bloqueada.")
            return
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_cgex_announcement_publications (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                message_id BIGINT,
                author_id BIGINT NOT NULL,
                published_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    @staticmethod
    async def _apagar_comando(ctx: commands.Context):
        me = ctx.guild.me if ctx.guild else None
        if me is None or not ctx.channel.permissions_for(me).manage_messages:
            return
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            LOG.info("Não foi possível apagar a invocação do anúncio CGEx.")

    @commands.command(name="previacgex")
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def previa(self, ctx: commands.Context):
        """Envia ao DM do administrador a prévia sem qualquer notificação."""
        try:
            if BANNER.is_file():
                with BANNER.open("rb") as f:
                    await ctx.author.send(
                        view=criar_anuncio(),
                        file=discord.File(f, filename=BANNER_FILENAME),
                        allowed_mentions=mencoes_para_envio(publicar=False),
                    )
            else:
                await ctx.author.send(view=criar_anuncio(),
                                      allowed_mentions=mencoes_para_envio(publicar=False))
        except discord.Forbidden:
            await ctx.send("⚠️ Não consegui enviar sua prévia por DM. Habilite mensagens privadas.",
                           allowed_mentions=discord.AllowedMentions.none(), delete_after=15)
            return
        except (discord.HTTPException, OSError):
            LOG.exception("Falha ao enviar prévia CGEx")
            await ctx.send("❌ Não foi possível enviar a prévia. Confira os logs.",
                           allowed_mentions=discord.AllowedMentions.none(), delete_after=15)
            return
        await self._apagar_comando(ctx)

    @commands.command(name="anunciocgex", aliases=["publicarcgex"])
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def publicar(self, ctx: commands.Context, canal: discord.TextChannel | None = None,
                       opcao: str = ""):
        """!anunciocgex #anuncios-administrativos [republicar]"""
        if opcao and opcao.casefold() != "republicar":
            return await ctx.send("❌ Opção inválida. Use `!anunciocgex #canal` ou `!anunciocgex #canal republicar`.",
                                  delete_after=15, allowed_mentions=discord.AllowedMentions.none())
        if canal is None and CANAL_ANUNCIOS_ADMIN_ID:
            candidato = ctx.guild.get_channel(CANAL_ANUNCIOS_ADMIN_ID)
            canal = candidato if isinstance(candidato, discord.TextChannel) else None
        if canal is None:
            return await ctx.send("📌 Informe o canal de anúncios: `!anunciocgex #anuncios-administrativos`.",
                                  delete_after=15, allowed_mentions=discord.AllowedMentions.none())
        if canal.guild.id != ctx.guild.id:
            return await ctx.send("❌ O canal precisa pertencer ao servidor da Família Royal.", delete_after=15)
        if self.pool() is None:
            return await ctx.send("❌ PostgreSQL indisponível. Publicação bloqueada para evitar anúncios duplicados.",
                                  delete_after=15)
        me = ctx.guild.me
        if me is None:
            return await ctx.send("❌ Não consegui verificar as permissões do bot.", delete_after=15)
        permissoes = canal.permissions_for(me)
        faltando = []
        if not permissoes.view_channel: faltando.append("Ver canal")
        if not permissoes.send_messages: faltando.append("Enviar mensagens")
        if not permissoes.mention_everyone: faltando.append("Mencionar @everyone")
        if BANNER.is_file() and not permissoes.attach_files: faltando.append("Anexar arquivos")
        if faltando:
            return await ctx.send("❌ Permissões ausentes no canal: " + ", ".join(faltando),
                                  delete_after=15, allowed_mentions=discord.AllowedMentions.none())
        pool = self.pool()
        try:
            if opcao.casefold() == "republicar":
                await pool.execute("""
                    INSERT INTO royal_cgex_announcement_publications
                        (guild_id, channel_id, author_id, message_id, published_at)
                    VALUES ($1,$2,$3,NULL,NOW())
                    ON CONFLICT (guild_id) DO UPDATE SET channel_id=EXCLUDED.channel_id,
                        author_id=EXCLUDED.author_id, message_id=NULL, published_at=NOW()
                """, ctx.guild.id, canal.id, ctx.author.id)
            else:
                reservado = await pool.fetchval("""
                    INSERT INTO royal_cgex_announcement_publications
                        (guild_id, channel_id, author_id)
                    VALUES ($1,$2,$3)
                    ON CONFLICT (guild_id) DO NOTHING RETURNING guild_id
                """, ctx.guild.id, canal.id, ctx.author.id)
                if reservado is None:
                    return await ctx.send(
                        "⚠️ Este comunicado já foi publicado ou reservado. Para publicar novamente, use "
                        "`!anunciocgex #canal republicar` (marcará @everyone outra vez).",
                        delete_after=25, allowed_mentions=discord.AllowedMentions.none(),
                    )
        except Exception:
            LOG.exception("Falha ao reservar a publicação CGEx")
            return await ctx.send("❌ Não consegui reservar a publicação no banco. Veja os logs.", delete_after=15)
        try:
            if BANNER.is_file():
                with BANNER.open("rb") as f:
                    mensagem = await canal.send(
                        view=criar_anuncio(), file=discord.File(f, filename=BANNER_FILENAME),
                        allowed_mentions=mencoes_para_envio(publicar=True),
                    )
            else:
                mensagem = await canal.send(view=criar_anuncio(),
                                            allowed_mentions=mencoes_para_envio(publicar=True))
        except (discord.HTTPException, OSError):
            LOG.exception("Falha ao publicar comunicado CGEx")
            try:
                await pool.execute("""
                    DELETE FROM royal_cgex_announcement_publications
                    WHERE guild_id=$1 AND message_id IS NULL AND author_id=$2
                """, ctx.guild.id, ctx.author.id)
            except Exception:
                LOG.exception("Falha ao liberar reserva CGEx")
            return await ctx.send("❌ Não foi possível publicar. Nenhuma nova marcação foi confirmada.",
                                  delete_after=15, allowed_mentions=discord.AllowedMentions.none())
        await pool.execute("""
            UPDATE royal_cgex_announcement_publications SET message_id=$2, channel_id=$3
            WHERE guild_id=$1
        """, ctx.guild.id, mensagem.id, canal.id)
        await self._apagar_comando(ctx)
        try:
            await ctx.author.send(f"✅ Comunicado CGEx publicado em {canal.mention}: {mensagem.jump_url}.",
                                  allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            pass

    async def cog_command_error(self, ctx: commands.Context, erro: commands.CommandError):
        if isinstance(erro, commands.MissingPermissions):
            await ctx.send("⛔ Apenas administradores podem publicar o comunicado CGEx.",
                           allowed_mentions=discord.AllowedMentions.none(), delete_after=15)
        elif isinstance(erro, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send("❌ Canal inválido. Use `!anunciocgex #anuncios-administrativos`.",
                           allowed_mentions=discord.AllowedMentions.none(), delete_after=15)
        else:
            LOG.error("Falha no comando anúncio CGEx", exc_info=(type(erro), erro, erro.__traceback__))
            await ctx.send("❌ Erro no comando. Consulte os logs do bot.",
                           allowed_mentions=discord.AllowedMentions.none(), delete_after=15)


async def setup(bot: commands.Bot):
    await bot.add_cog(AnuncioCGExRoyal(bot))
