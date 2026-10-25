

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger("sants.bot.boas_vindas")
BASE_DIR = Path(__file__).resolve().parent.parent

# IDs padrão; o Railway pode sobrescrever cada um com uma variável de ambiente.
CHANNEL_IDS = {
    "WELCOME_CHANNEL_ID": 1563991142159360150,
    "ROYAL_RULES_CHANNEL_ID": 1553829609160835342,
    "ROYAL_ROLES_CHANNEL_ID": 1553820522322862200,
    "ROYAL_GIVEAWAYS_CHANNEL_ID": 1553829712621740103,
    "ROYAL_SUPPORT_CHANNEL_ID": 1553843978229522633,
}

BANNER_NAMES = (
    "boas_vindas_royal.png",  # nome recomendado
    "Família Royal_ Portal Celestial Dourado.png",
    "família_royal_portal_celestial_dourado.png",
)


def channel_id(key: str) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return CHANNEL_IDS[key]
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s incorreto (%r); usando ID padrão", key, raw)
        return CHANNEL_IDS[key]


def channel_ref(guild: discord.Guild, key: str, fallback_name: str) -> str:
    # Uma menção por ID funciona mesmo quando o canal não está no cache do bot.
    cid = channel_id(key)
    channel = guild.get_channel(cid)
    if isinstance(channel, discord.TextChannel):
        return channel.mention
    return f"<#{cid}>" if cid else f"#{fallback_name}"


def banner_path() -> Path | None:
    folder = BASE_DIR / "assets"
    for name in BANNER_NAMES:
        path = folder / name
        if path.is_file():
            return path
    return None


class BoasVindasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def enviar(self, member: discord.Member) -> tuple[bool, str]:
        guild = member.guild
        destination_id = channel_id("WELCOME_CHANNEL_ID")
        channel = guild.get_channel(destination_id)

        if not isinstance(channel, discord.TextChannel):
            reason = f"Canal de boas-vindas {destination_id} não encontrado neste servidor."
            logger.error("%s Guild=%s", reason, guild.id)
            return False, reason

        if not self.bot.user:
            return False, "Bot ainda não está pronto."

        me = guild.me or guild.get_member(self.bot.user.id)
        if me is None:
            try:
                me = await guild.fetch_member(self.bot.user.id)
            except discord.HTTPException as exc:
                logger.exception("Falha ao consultar permissões do bot")
                return False, f"Não consegui consultar as permissões do bot ({exc})."

        perms = channel.permissions_for(me)
        missing = []
        if not perms.view_channel:
            missing.append("Ver canal")
        if not perms.send_messages:
            missing.append("Enviar mensagens")
        if missing:
            reason = "Permissões ausentes: " + ", ".join(missing)
            logger.error("%s (canal %s)", reason, channel.id)
            return False, reason

        banner = banner_path()
        if banner is None:
            reason = (
                "Banner não encontrado na pasta assets/. "
                "Renomeie a imagem para boas_vindas_royal.png e faça push no GitHub."
            )
            logger.error(reason)
            return False, reason
        if not perms.attach_files:
            return False, "Falta a permissão Anexar arquivos no canal de boas-vindas."

        rules = channel_ref(guild, "ROYAL_RULES_CHANNEL_ID", "regras")
        giveaways = channel_ref(guild, "ROYAL_GIVEAWAYS_CHANNEL_ID", "sorteios")
        support = channel_ref(guild, "ROYAL_SUPPORT_CHANNEL_ID", "suporte")

        try:
            view = discord.ui.LayoutView(timeout=None)
            panel = discord.ui.Container(accent_colour=discord.Colour.from_rgb(190, 150, 79))
            panel.add_item(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media="attachment://boas_vindas_royal.png")
                )
            )
            panel.add_item(
                discord.ui.TextDisplay(
                    "## 👑・BEM-VINDO(A) À FAMÍLIA ROYAL\n"
                    f"> `🪽` Seja bem-vindo(a), {member.mention}! É uma honra receber você em nosso reino.\n\n"
                    f"> `📜` **Regras:** {rules}\n"
                    f"> `🎉` **Sorteios:** {giveaways}\n"
                    f"> `🎫` **Suporte:** {support}\n\n"
                    "> `⚜️` **Que sua jornada seja marcada pela união, respeito e lealdade.**"
                )
            )
            view.add_item(panel)
            # Uso de `with` garante o fechamento correto do arquivo após o envio.
            with banner.open("rb") as stream:
                attachment = discord.File(stream, filename="boas_vindas_royal.png")
                await channel.send(
                    view=view,
                    file=attachment,
                    allowed_mentions=discord.AllowedMentions(
                        users=[member], roles=False, everyone=False
                    ),
                )
            logger.info("Boas-vindas enviadas para %s no canal %s", member.id, channel.id)
            return True, "Prévia enviada com sucesso."
        except discord.Forbidden as exc:
            logger.exception("Discord recusou o envio (403) no canal %s", channel.id)
            return False, f"Discord recusou acesso (403): {exc}"
        except discord.HTTPException as exc:
            logger.exception(
                "Falha HTTP do Discord | status=%s | codigo=%s | texto=%s",
                exc.status, exc.code, exc.text,
            )
            return False, f"Discord HTTP {exc.status} / código {exc.code}: {str(exc)[:250]}"
        except Exception as exc:
            logger.exception("Erro inesperado no painel de boas-vindas")
            return False, f"Erro {type(exc).__name__}: {str(exc)[:250]}"

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        ok, detail = await self.enviar(member)
        if not ok:
            logger.error("Boas-vindas não enviadas para %s: %s", member.id, detail)

    @commands.command(name="testeboasvindas")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def teste_boas_vindas(self, ctx: commands.Context):
        ok, detail = await self.enviar(ctx.author)
        await ctx.reply(
            ("✅ " if ok else "❌ ") + detail,
            mention_author=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasRoyal(bot))
