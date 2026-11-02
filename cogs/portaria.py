from __future__ import annotations

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.boas_vindas")
BASE_DIR = Path(__file__).resolve().parent.parent

# IDs originais preservados. Também aceitam substituição por variáveis de ambiente.
CHANNEL_IDS = {
    "WELCOME_CHANNEL_ID": 1563991142159360150,
    "ROYAL_RULES_CHANNEL_ID": 1553829609160835342,
    "ROYAL_ROLES_CHANNEL_ID": 1553820522322862200,
    "ROYAL_GIVEAWAYS_CHANNEL_ID": 1553829712621740103,
    "ROYAL_SUPPORT_CHANNEL_ID": 1553843978229522633,
}

# Novo banner das seis integrantes da Família Royal.
NOME_ANEXO = "boas_vindas_royal.png"
COR_ROYAL = discord.Colour.from_rgb(116, 66, 154)  # Roxo da nova identidade visual


def channel_id(key: str) -> int:
    value = os.getenv(key, "").strip()
    if value:
        try:
            return int(value)
        except ValueError:
            logger.warning("ID inválido para %s: %r; usando padrão", key, value)
    return CHANNEL_IDS[key]


def channel_ref(key: str) -> str:
    return f"<#{channel_id(key)}>"


def banner_path() -> Path | None:
    """Encontra exclusivamente o banner novo dentro da pasta assets/."""
    raiz_cog = Path(__file__).resolve().parent
    pastas = (
        BASE_DIR / "assets",          
        raiz_cog / "assets",      
        Path.cwd() / "assets",       
    )
    visitados: set[Path] = set()

    for pasta in pastas:
        pasta = pasta.resolve()
        if pasta in visitados:
            continue
        visitados.add(pasta)
        candidate = pasta / NOME_ANEXO
        if candidate.is_file():
            return candidate
    return None


def suporta_components_v2() -> bool:
    """Components V2 requer discord.py 2.6 ou superior."""
    return all(
        hasattr(discord.ui, atributo)
        for atributo in ("LayoutView", "Container", "MediaGallery", "TextDisplay", "Separator")
    ) and hasattr(discord, "MediaGalleryItem")


def montar_painel(member: discord.Member, *, com_banner: bool) -> discord.ui.LayoutView:
    """Painel de boas-vindas em Components V2, inspirado no novo banner."""
    view = discord.ui.LayoutView(timeout=None)
    panel = discord.ui.Container(accent_colour=COR_ROYAL)

    if com_banner:
        panel.add_item(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    media=f"attachment://{NOME_ANEXO}",
                    description="Boas-vindas à Família Royal com Bruna, Tatah, Kananda, Pietra, Lívia e Soso.",
                )
            )
        )

    panel.add_item(
        discord.ui.TextDisplay(
            "## 🌸 Um novo capítulo começa aqui!\n"
            f"Seja muito bem-vindo(a), {member.mention}! 👑\n"
            "Agora você faz parte da **Família Royal**, onde cada pessoa tem sua história, "
            "cada amizade importa e a diversão nunca fica de fora."
        )
    )
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(
        discord.ui.TextDisplay(
            "**🪽 Conheça a nossa Família**\n"
            "Fundada em **28/01/2026**, com raízes no **E.B. do ALPHA**, a Royal reúne "
            "amizades, resenhas, desafios, eventos e histórias inesquecíveis.\n"
            "**⚜️ Nossos pilares:** Honra • União • Lealdade"
        )
    )
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(
        discord.ui.TextDisplay(
            "**📚 Comece por aqui**\n"
            f"📜 **Regras:** {channel_ref('ROYAL_RULES_CHANNEL_ID')}\n"
            f"🎭 **Cargos:** {channel_ref('ROYAL_ROLES_CHANNEL_ID')}\n"
            f"🎁 **Sorteios:** {channel_ref('ROYAL_GIVEAWAYS_CHANNEL_ID')}\n"
            f"🎫 **Suporte:** {channel_ref('ROYAL_SUPPORT_CHANNEL_ID')}"
        )
    )
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(
        discord.ui.TextDisplay(
            "-# 👑 Família Royal — Honra, União e Lealdade. Aproveite sua chegada!"
        )
    )

    view.add_item(panel)
    return view


def mensagem_simples(member: discord.Member) -> str:
    """Texto alternativo para instalações sem suporte a Components V2."""
    return (
        "**🌸 BOAS-VINDAS À FAMÍLIA ROYAL!**\n"
        f"Seja muito bem-vindo(a), {member.mention}! 👑\n"
        "Aqui cada pessoa tem sua história, cada amizade importa e a diversão nunca fica de fora.\n\n"
        "**🪽 Nossa Família**\n"
        "Fundada em **28/01/2026**, com raízes no **E.B. do ALPHA**, a Royal "
        "é feita de amizades, eventos, desafios e boas histórias.\n"
        "**⚜️ Honra • União • Lealdade**\n\n"
        "**📚 Comece por aqui**\n"
        f"📜 Regras: {channel_ref('ROYAL_RULES_CHANNEL_ID')}\n"
        f"🎭 Cargos: {channel_ref('ROYAL_ROLES_CHANNEL_ID')}\n"
        f"🎁 Sorteios: {channel_ref('ROYAL_GIVEAWAYS_CHANNEL_ID')}\n"
        f"🎫 Suporte: {channel_ref('ROYAL_SUPPORT_CHANNEL_ID')}\n\n"
        "-# 👑 Família Royal — Aproveite sua chegada!"
    )


class BoasVindasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ultima_falha: str | None = None

    async def cog_load(self) -> None:
        if not self.bot.intents.members:
            logger.error(
                "Boas-vindas: intents.members desativada no bot principal. "
                "Ative intents.members=True e Server Members Intent no Developer Portal."
            )

        if not suporta_components_v2():
            logger.warning(
                "discord.py %s sem Components V2; será utilizado texto convencional com banner.",
                getattr(discord, "__version__", "desconhecida"),
            )

        if banner_path() is None:
            logger.warning(
                "Novo banner não encontrado: coloque assets/%s no projeto. "
                "As boas-vindas funcionarão sem imagem.",
                NOME_ANEXO,
            )

        logger.info("Boas-vindas Royal carregadas; canal=%s", channel_id("WELCOME_CHANNEL_ID"))

    async def _canal(self, guild: discord.Guild) -> discord.TextChannel | None:
        cid = channel_id("WELCOME_CHANNEL_ID")
        channel = guild.get_channel(cid)
        if not isinstance(channel, discord.TextChannel):
            try:
                channel = await guild.fetch_channel(cid)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
                logger.warning("Não foi possível obter canal Royal %s: %r", cid, exc)
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def enviar(self, member: discord.Member) -> tuple[bool, str]:
        guild = member.guild
        cid = channel_id("WELCOME_CHANNEL_ID")
        channel = await self._canal(guild)
        if channel is None:
            self.ultima_falha = f"Canal de boas-vindas {cid} não encontrado ou inacessível."
            return False, self.ultima_falha

        if self.bot.user is None:
            self.ultima_falha = "Bot ainda não está pronto."
            return False, self.ultima_falha

        me = guild.me or guild.get_member(self.bot.user.id)
        if me is None:
            try:
                me = await guild.fetch_member(self.bot.user.id)
            except discord.HTTPException as exc:
                self.ultima_falha = f"Não foi possível conferir permissões: {exc}"
                return False, self.ultima_falha

        perms = channel.permissions_for(me)
        missing = []
        if not perms.view_channel:
            missing.append("Ver canal")
        if not perms.send_messages:
            missing.append("Enviar mensagens")
        if missing:
            self.ultima_falha = "Permissões ausentes: " + ", ".join(missing)
            return False, self.ultima_falha

        banner = banner_path()
        pode_anexar = bool(perms.attach_files)
        usar_banner = banner is not None and pode_anexar
        mentions = discord.AllowedMentions(users=[member], roles=False, everyone=False)

        if not pode_anexar:
            logger.warning("Bot sem permissão 'Anexar arquivos' no canal %s", cid)
        if banner is None:
            logger.warning("Arquivo assets/%s não encontrado; enviando sem banner", NOME_ANEXO)

        async def enviar_texto_com_banner() -> bool:
            """Fallback que mantém a imagem mesmo sem Components V2, se possível."""
            if usar_banner and banner is not None:
                try:
                    with banner.open("rb") as image:
                        await channel.send(
                            content=mensagem_simples(member),
                            file=discord.File(image, filename=NOME_ANEXO),
                            allowed_mentions=mentions,
                        )
                    return True
                except OSError as exc:
                    logger.warning("Não foi possível abrir o banner: %r", exc)
                except discord.HTTPException as exc:
                    if exc.status != 400:
                        raise
                    logger.warning("Discord recusou o anexo (HTTP 400); usando texto: %s", exc)

            await channel.send(content=mensagem_simples(member), allowed_mentions=mentions)
            return False

        async def enviar_v2_sem_banner() -> bool:
            """Evita perder a saudação caso um painel V2 seja recusado."""
            try:
                await channel.send(
                    view=montar_painel(member, com_banner=False),
                    allowed_mentions=mentions,
                )
                return False
            except discord.HTTPException as exc:
                if exc.status != 400:
                    raise
                logger.warning("Discord recusou Components V2; tentando texto comum: %s", exc)
                return await enviar_texto_com_banner()

        try:
            if suporta_components_v2():
                if usar_banner and banner is not None:
                    try:
                        with banner.open("rb") as image:
                            await channel.send(
                                view=montar_painel(member, com_banner=True),
                                file=discord.File(image, filename=NOME_ANEXO),
                                allowed_mentions=mentions,
                            )
                        banner_enviado = True
                    except OSError as exc:
                        logger.warning("Falha ao abrir banner (%r); tentando painel sem imagem", exc)
                        banner_enviado = await enviar_v2_sem_banner()
                    except discord.HTTPException as exc:
                        if exc.status != 400:
                            raise
                        logger.warning("Banner V2 recusado (HTTP 400); tentando formato alternativo: %s", exc)
                        # Não tenta enviar o mesmo arquivo repetidamente em V2.
                        banner_enviado = await enviar_v2_sem_banner()
                else:
                    banner_enviado = await enviar_v2_sem_banner()
            else:
                banner_enviado = await enviar_texto_com_banner()

            self.ultima_falha = None
            logger.info("Boas-vindas enviadas para %s no canal %s", member.id, cid)
            estado = "com banner" if banner_enviado else "sem banner"
            return True, f"Mensagem de boas-vindas enviada {estado}."

        except discord.HTTPException as exc:
            logger.exception("Discord HTTP %s / código %s: %s", exc.status, exc.code, exc.text)
            self.ultima_falha = f"Discord HTTP {exc.status} / código {exc.code}: {str(exc)[:250]}"
            return False, self.ultima_falha
        except (OSError, ValueError, TypeError) as exc:
            logger.exception("Erro ao montar ou enviar boas-vindas")
            self.ultima_falha = f"{type(exc).__name__}: {str(exc)[:250]}"
            return False, self.ultima_falha
        except Exception as exc:
            logger.exception("Falha inesperada no envio de boas-vindas")
            self.ultima_falha = f"{type(exc).__name__}: {str(exc)[:250]}"
            return False, self.ultima_falha

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        logger.info(
            "Evento on_member_join: guild=%s member=%s bot=%s",
            member.guild.id,
            member.id,
            member.bot,
        )
        if member.bot:
            return
        ok, detail = await self.enviar(member)
        if not ok:
            logger.error("Boas-vindas não enviadas para %s: %s", member.id, detail)

    @commands.command(name="testeboasvindas")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def teste_boas_vindas(self, ctx: commands.Context):
        """Testa o painel novo com o autor do comando, sem entrada real no servidor."""
        ok, detail = await self.enviar(ctx.author)
        await ctx.reply(("✅ " if ok else "❌ ") + detail, mention_author=False)

    @commands.command(name="statusboasvindas")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def status_boas_vindas(self, ctx: commands.Context):
        """Confere intents, Components V2, banner, canal e permissões."""
        canal = await self._canal(ctx.guild)
        banner = banner_path()
        me = ctx.guild.me
        if me is None and self.bot.user is not None:
            try:
                me = await ctx.guild.fetch_member(self.bot.user.id)
            except discord.HTTPException:
                me = None

        permissoes = "indisponíveis"
        if canal is not None and me is not None:
            p = canal.permissions_for(me)
            permissoes = (
                f"ver={p.view_channel}, enviar={p.send_messages}, "
                f"anexar={p.attach_files}"
            )

        diagnostico = (
            "**👑 Diagnóstico das boas-vindas Royal**\n"
            f"• discord.py: `{getattr(discord, '__version__', 'desconhecida')}`\n"
            f"• Components V2: `{'sim' if suporta_components_v2() else 'não'}`\n"
            f"• Intents members (código): `{'ativada' if self.bot.intents.members else 'DESATIVADA'}`\n"
            f"• Canal: `{channel_id('WELCOME_CHANNEL_ID')}` (`{'encontrado' if canal else 'NÃO encontrado'}`)\n"
            f"• Permissões: `{permissoes}`\n"
            f"• Banner: `{banner.name if banner else 'NÃO encontrado'}`\n"
            f"• Última falha: `{self.ultima_falha or 'nenhuma registrada'}`\n\n"
            "-# A intenção Server Members também precisa estar ativada no Discord Developer Portal."
        )
        await ctx.reply(diagnostico, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasRoyal(bot))
