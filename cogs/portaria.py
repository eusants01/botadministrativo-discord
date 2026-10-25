"""Boas-vindas da FamÃ­lia Royal â€” Discord Components V2 (discord.py >= 2.6)."""

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.boas_vindas")
BASE_DIR = Path(__file__).resolve().parent.parent

CHANNEL_IDS = {
    "WELCOME_CHANNEL_ID": 1563991142159360150,
    "ROYAL_RULES_CHANNEL_ID": 1553829609160835342,
    "ROYAL_ROLES_CHANNEL_ID": 1553820522322862200,
    "ROYAL_GIVEAWAYS_CHANNEL_ID": 1553829712621740103,
    "ROYAL_SUPPORT_CHANNEL_ID": 1553843978229522633,
}

BANNER_NAMES = (
    "boas_vindas_royal.png",
    "FamÃ­lia Royal_ Portal Celestial Dourado.png",
    "famÃ­lia_royal_portal_celestial_dourado.png",
)
BANNER_ATTACHMENT = "boas_vindas_royal.png"


def channel_id(key: str) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return CHANNEL_IDS[key]
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError("ID precisa ser positivo")
        return value
    except ValueError:
        logger.warning("%s invÃ¡lido: %r. Usando ID padrÃ£o.", key, raw)
        return CHANNEL_IDS[key]


def find_banner() -> Path | None:
    directory = BASE_DIR / "assets"
    for filename in BANNER_NAMES:
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def link_to_channel(guild_id: int, key: str) -> str:
    # BotÃµes de link levam diretamente ao canal, sem callback e sem expirar.
    return f"https://discord.com/channels/{guild_id}/{channel_id(key)}"


def make_welcome_view(member: discord.Member) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    panel = discord.ui.Container(accent_colour=discord.Colour.from_rgb(182, 132, 59))

    panel.add_item(
        discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{BANNER_ATTACHMENT}")
        )
    )
    panel.add_item(
        discord.ui.TextDisplay(
            "## ðŸ‘‘ãƒ»BOAS-VINDAS Ã€ FAMÃLIA ROYAL\n"
            f"{member.mention}, as portas do nosso reino estÃ£o abertas para vocÃª."
        )
    )
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(
        discord.ui.TextDisplay(
            "**âšœï¸ NOSSO REINO**\n"
            "Uma comunidade de **uniÃ£o, respeito e lealdade**, "
            "com raÃ­zes no **E.B do ALPHA**. "
            "Aqui, cada integrante faz parte da nossa histÃ³ria."
        )
    )
    panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    panel.add_item(
        discord.ui.TextDisplay(
            "**âœ¦ COMECE SUA JORNADA**\n"
            "Use os botÃµes abaixo para conhecer as regras, escolher cargos, "
            "participar dos sorteios ou solicitar suporte."
        )
    )

    row = discord.ui.ActionRow()
    for label, emoji, key in (
        ("Regras", "ðŸ“œ", "ROYAL_RULES_CHANNEL_ID"),
        ("Cargos", "ðŸ‘‘", "ROYAL_ROLES_CHANNEL_ID"),
        ("Sorteios", "ðŸŽ‰", "ROYAL_GIVEAWAYS_CHANNEL_ID"),
        ("Suporte", "ðŸŽ«", "ROYAL_SUPPORT_CHANNEL_ID"),
    ):
        row.add_item(
            discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.link,
                url=link_to_channel(member.guild.id, key),
            )
        )
    panel.add_item(row)
    view.add_item(panel)
    return view


class BoasVindasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def enviar(self, member: discord.Member) -> tuple[bool, str]:
        guild = member.guild
        destination_id = channel_id("WELCOME_CHANNEL_ID")
        channel = guild.get_channel(destination_id)
        if not isinstance(channel, discord.TextChannel):
            try:
                channel = await self.bot.fetch_channel(destination_id)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                channel = None
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != guild.id:
            return False, f"Canal de boas-vindas {destination_id} nÃ£o encontrado neste servidor."

        me = guild.me
        if me is None and self.bot.user:
            me = guild.get_member(self.bot.user.id)
        if me is None and self.bot.user:
            try:
                me = await guild.fetch_member(self.bot.user.id)
            except discord.HTTPException:
                return False, "NÃ£o consegui verificar as permissÃµes do bot."
        if me is None:
            return False, "Bot ainda nÃ£o estÃ¡ pronto."

        perms = channel.permissions_for(me)
        missing = []
        if not perms.view_channel:
            missing.append("Ver canal")
        if not perms.send_messages:
            missing.append("Enviar mensagens")
        if not perms.attach_files:
            missing.append("Anexar arquivos")
        if missing:
            return False, "PermissÃµes ausentes: " + ", ".join(missing)

        banner = find_banner()
        if banner is None:
            return False, "Banner ausente: coloque boas_vindas_royal.png na pasta assets/."

        try:
            view = make_welcome_view(member)
            with banner.open("rb") as stream:
                attachment = discord.File(stream, filename=BANNER_ATTACHMENT)
                await channel.send(
                    view=view,
                    file=attachment,
                    allowed_mentions=discord.AllowedMentions(
                        users=[member], roles=False, everyone=False
                    ),
                )
            logger.info("Boas-vindas enviadas a %s no canal %s", member.id, channel.id)
            return True, f"Mensagem enviada em {channel.mention}."
        except discord.Forbidden as exc:
            logger.exception("Envio de boas-vindas recusado (403)")
            return False, f"Discord recusou o envio (403): {exc}"
        except discord.HTTPException as exc:
            logger.exception("Falha HTTP ao enviar boas-vindas")
            return False, f"Discord HTTP {exc.status}, cÃ³digo {exc.code}: {str(exc)[:180]}"
        except Exception as exc:
            logger.exception("Erro inesperado ao enviar boas-vindas")
            return False, f"{type(exc).__name__}: {str(exc)[:180]}"

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        ok, detail = await self.enviar(member)
        if not ok:
            logger.error("NÃ£o foi possÃ­vel enviar boas-vindas a %s: %s", member.id, detail)

    @commands.command(name="testeboasvindas")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def teste_boas_vindas(self, ctx: commands.Context):
        """Envia uma prÃ©via das boas-vindas para o canal oficial."""
        ok, detail = await self.enviar(ctx.author)
        await ctx.reply(("âœ… " if ok else "âŒ ") + detail, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasRoyal(bot))