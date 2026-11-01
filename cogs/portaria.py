from __future__ import annotations

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.boas_vindas")
BASE_DIR = Path(__file__).resolve().parent.parent

# IDs e nomes originais: preservados.
CHANNEL_IDS = {
    "WELCOME_CHANNEL_ID": 1563991142159360150,
    "ROYAL_RULES_CHANNEL_ID": 1553829609160835342,
    "ROYAL_ROLES_CHANNEL_ID": 1553820522322862200,
    "ROYAL_GIVEAWAYS_CHANNEL_ID": 1553829712621740103,
    "ROYAL_SUPPORT_CHANNEL_ID": 1553843978229522633,
}
BANNER_NAMES = (
    "boas_vindas_royal.png",
    "Família Royal_ Portal Celestial Dourado.png",
    "família_royal_portal_celestial_dourado.png",
)
COR_ROYAL = discord.Colour.from_rgb(190, 150, 79)
NOME_ANEXO = "boas_vindas_royal.png"


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
    """Preserva a pasta original e tolera diferentes posições do cog no projeto."""
    raiz_cog = Path(__file__).resolve().parent
    pastas = (
        BASE_DIR / "assets",            # Estrutura habitual: cogs/ + assets/
        raiz_cog / "assets",             # Caso o arquivo esteja na raiz do bot
        Path.cwd() / "assets",           # Alternativa para hospedagens
    )
    visitados: set[Path] = set()
    for pasta in pastas:
        pasta = pasta.resolve()
        if pasta in visitados:
            continue
        visitados.add(pasta)
        for name in BANNER_NAMES:
            path = pasta / name
            if path.is_file():
                return path
    return None


def suporta_components_v2() -> bool:
    """Evita crash de importação/criação ao usar discord.py anterior a 2.6."""
    return all(
        hasattr(discord.ui, atributo)
        for atributo in ("LayoutView", "Container", "MediaGallery", "TextDisplay", "Separator")
    ) and hasattr(discord, "MediaGalleryItem")


def montar_painel(member: discord.Member, *, com_banner: bool) -> discord.ui.LayoutView:
    """Mesmo conteúdo visual da versão original, com anexo opcional."""
    view = discord.ui.LayoutView(timeout=None)
    panel = discord.ui.Container(accent_colour=COR_ROYAL)

    if com_banner:
        panel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{NOME_ANEXO}")
        ))

    panel.add_item(discord.ui.TextDisplay(
        "## <a:coroa:1564000189167960177> BOAS-VINDAS À FAMÍLIA ROYAL\n"
        f"Seja bem-vindo(a), {member.mention}. É uma satisfação receber você em nossa comunidade."
    ))
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(discord.ui.TextDisplay(
        "**⚜️ Sobre a Família Royal**\n"
        "Com raízes no E.B do ALPHA, a Família Royal é guiada pelos valores de "
        "união, respeito e lealdade. Que sua trajetória conosco seja marcada por boas conquistas."
    ))
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(discord.ui.TextDisplay(
        "**📜 Orientações Iniciais**\n"
        f'> `📜` Conheça nossas diretrizes em {channel_ref("ROYAL_RULES_CHANNEL_ID")}.\n'
        f'> `👑` Personalize sua experiência em {channel_ref("ROYAL_ROLES_CHANNEL_ID")}.\n'
        f'> `🎉` Acompanhe as premiações em {channel_ref("ROYAL_GIVEAWAYS_CHANNEL_ID")}.\n'
        f'> `🎫` Solicite assistência à equipe em {channel_ref("ROYAL_SUPPORT_CHANNEL_ID")}.'
    ))
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(discord.ui.TextDisplay(
        "-# <:ImagemdoChatGPT25deoutde202615_4:1563986790753378424> Honrar a Família é nossa prioridade."
    ))
    view.add_item(panel)
    return view


def mensagem_simples(member: discord.Member) -> str:
    """Fallback apenas quando Components V2 não está disponível."""
    return (
        "**👑 BOAS-VINDAS À FAMÍLIA ROYAL**\n"
        f"Seja bem-vindo(a), {member.mention}. É uma satisfação receber você em nossa comunidade.\n\n"
        "**⚜️ Sobre a Família Royal**\n"
        "Com raízes no E.B do ALPHA, a Família Royal é guiada pelos valores de "
        "união, respeito e lealdade. Que sua trajetória conosco seja marcada por boas conquistas.\n\n"
        "**📜 Orientações Iniciais**\n"
        f"> 📜 Conheça nossas diretrizes em {channel_ref('ROYAL_RULES_CHANNEL_ID')}.\n"
        f"> 👑 Personalize sua experiência em {channel_ref('ROYAL_ROLES_CHANNEL_ID')}.\n"
        f"> 🎉 Acompanhe as premiações em {channel_ref('ROYAL_GIVEAWAYS_CHANNEL_ID')}.\n"
        f"> 🎫 Solicite assistência à equipe em {channel_ref('ROYAL_SUPPORT_CHANNEL_ID')}.\n\n"
        "-# Honrar a Família é nossa prioridade."
    )


class BoasVindasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ultima_falha: str | None = None

    async def cog_load(self) -> None:
        if not self.bot.intents.members:
            logger.error(
                "Boas-vindas: intents.members está DESATIVADA no bot principal. "
                "Ative intents.members=True e Server Members Intent no Developer Portal."
            )
        if not suporta_components_v2():
            logger.warning(
                "discord.py %s sem Components V2; será utilizado texto simples.",
                getattr(discord, "__version__", "desconhecida"),
            )
        if banner_path() is None:
            logger.warning(
                "Banner Royal não encontrado. Verifique a pasta assets/ e os nomes: %s. "
                "Boas-vindas serão enviadas sem imagem.",
                ", ".join(BANNER_NAMES),
            )
        logger.info("Sistema de boas-vindas Royal carregado; canal=%s", channel_id("WELCOME_CHANNEL_ID"))

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
        usar_banner = banner is not None and pode_anexar and suporta_components_v2()
        if banner and not pode_anexar:
            logger.warning("Sem permissão Anexar arquivos no canal %s; enviando sem banner.", cid)
        if banner is None:
            logger.warning("Nenhum banner encontrado; enviando boas-vindas sem imagem.")

        mentions = discord.AllowedMentions(users=[member], roles=False, everyone=False)
        banner_enviado = False

        async def enviar_sem_banner() -> None:
            """Se V2 for rejeitado por formato (HTTP 400), usa texto como último recurso."""
            try:
                await channel.send(
                    view=montar_painel(member, com_banner=False),
                    allowed_mentions=mentions,
                )
            except discord.HTTPException as exc:
                if exc.status != 400:
                    raise
                logger.warning("Discord recusou Components V2 (HTTP 400); usando texto simples: %s", exc)
                await channel.send(content=mensagem_simples(member), allowed_mentions=mentions)

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
                        logger.warning("Falha ao abrir banner (%r); tentando sem imagem.", exc)
                        await enviar_sem_banner()
                    except discord.HTTPException as exc:
                        if exc.status != 400:
                            raise
                        logger.warning("Banner rejeitado pelo Discord (HTTP 400): %s. Tentando sem imagem.", exc)
                        await enviar_sem_banner()
                else:
                    await enviar_sem_banner()
            else:
                await channel.send(content=mensagem_simples(member), allowed_mentions=mentions)

            self.ultima_falha = None
            logger.info("Boas-vindas enviadas para membro %s em canal %s", member.id, cid)
            if banner_enviado:
                return True, "Mensagem de boas-vindas enviada com banner."
            return True, "Mensagem de boas-vindas enviada sem banner."

        except discord.HTTPException as exc:
            logger.exception("Discord HTTP %s código %s: %s", exc.status, exc.code, exc.text)
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
        logger.info("Evento on_member_join: guild=%s member=%s bot=%s", member.guild.id, member.id, member.bot)
        if member.bot:
            return
        ok, detail = await self.enviar(member)
        if not ok:
            logger.error("Boas-vindas não enviadas para %s: %s", member.id, detail)

    @commands.command(name="testeboasvindas")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def teste_boas_vindas(self, ctx: commands.Context):
        """Envia a mesma mensagem para o autor do comando, sem esperar uma entrada real."""
        ok, detail = await self.enviar(ctx.author)
        await ctx.reply(("✅ " if ok else "❌ ") + detail, mention_author=False)

    @commands.command(name="statusboasvindas")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def status_boas_vindas(self, ctx: commands.Context):
        """Diagnóstico rápido de intents, versão, banner, canal e permissões."""
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
