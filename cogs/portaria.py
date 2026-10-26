import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger('sants.bot.boas_vindas')
BASE_DIR = Path(__file__).resolve().parent.parent

CHANNEL_IDS = {
    'WELCOME_CHANNEL_ID': 1563991142159360150,
    'ROYAL_RULES_CHANNEL_ID': 1553829609160835342,
    'ROYAL_ROLES_CHANNEL_ID': 1553820522322862200,
    'ROYAL_GIVEAWAYS_CHANNEL_ID': 1553829712621740103,
    'ROYAL_SUPPORT_CHANNEL_ID': 1553843978229522633,
}
BANNER_NAMES = (
    'boas_vindas_royal.png',
    'Família Royal_ Portal Celestial Dourado.png',
    'família_royal_portal_celestial_dourado.png',
)


def channel_id(key: str) -> int:
    value = os.getenv(key, '').strip()
    if value:
        try:
            return int(value)
        except ValueError:
            logger.warning('ID inválido para %s: %r; usando padrão', key, value)
    return CHANNEL_IDS[key]


def channel_ref(key: str) -> str:
    return f'<#{channel_id(key)}>'


def banner_path() -> Path | None:
    for name in BANNER_NAMES:
        path = BASE_DIR / 'assets' / name
        if path.is_file():
            return path
    return None


class BoasVindasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def enviar(self, member: discord.Member) -> tuple[bool, str]:
        guild = member.guild
        cid = channel_id('WELCOME_CHANNEL_ID')
        channel = guild.get_channel(cid)
        if not isinstance(channel, discord.TextChannel):
            try:
                channel = await guild.fetch_channel(cid)
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                channel = None

        if not isinstance(channel, discord.TextChannel):
            return False, f'Canal de boas-vindas {cid} não encontrado.'
        if self.bot.user is None:
            return False, 'Bot ainda não está pronto.'

        me = guild.me or guild.get_member(self.bot.user.id)
        if me is None:
            try:
                me = await guild.fetch_member(self.bot.user.id)
            except discord.HTTPException as exc:
                return False, f'Não foi possível conferir permissões: {exc}'

        permissions = channel.permissions_for(me)
        missing = []
        if not permissions.view_channel:
            missing.append('Ver canal')
        if not permissions.send_messages:
            missing.append('Enviar mensagens')
        if not permissions.attach_files:
            missing.append('Anexar arquivos')
        if missing:
            return False, 'Permissões ausentes: ' + ', '.join(missing)

        banner = banner_path()
        if banner is None:
            return False, 'Banner ausente em assets/. Use o nome boas_vindas_royal.png.'

        rules = channel_ref('ROYAL_RULES_CHANNEL_ID')
        roles = channel_ref('ROYAL_ROLES_CHANNEL_ID')
        giveaways = channel_ref('ROYAL_GIVEAWAYS_CHANNEL_ID')
        support = channel_ref('ROYAL_SUPPORT_CHANNEL_ID')

        view = discord.ui.LayoutView(timeout=None)
        panel = discord.ui.Container(accent_colour=discord.Colour.from_rgb(190, 150, 79))
        panel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media='attachment://boas_vindas_royal.png')
        ))
        panel.add_item(discord.ui.TextDisplay(
            '## <a:coroa:1564000189167960177> BOAS-VINDAS À FAMÍLIA ROYAL\n'
            f'Seja bem-vindo(a), {member.mention}. É uma satisfação receber você em nossa comunidade.'
        ))
        panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        panel.add_item(discord.ui.TextDisplay(
            '**⚜️ Sobre a Família Royal**\n'
            'Com raízes no E.B do ALPHA, a Família Royal é guiada pelos valores de '
            'união, respeito e lealdade. Que sua trajetória conosco seja marcada por boas conquistas.'
        ))
        panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        
        panel.add_item(discord.ui.TextDisplay(
            "**📜 Orientações Iniciais**\n"
            f"> `📜` Conheça nossas diretrizes em {rules}.\n"
          f"> `👑` Personalize sua experiência em {roles}.\n"
          f"> `🎉` Acompanhe as premiações em {giveaways}.\n"
          f"> `🎫` Solicite assistência à equipe em {support}."
))

        panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        panel.add_item(discord.ui.TextDisplay(
            '-# <:ImagemdoChatGPT25deoutde202615_4:1563986790753378424> Honrar a Família é nossa prioridade.\n'
        ))
        view.add_item(panel)

        try:
            with banner.open('rb') as image:
                await channel.send(
                    view=view,
                    file=discord.File(image, filename='boas_vindas_royal.png'),
                    allowed_mentions=discord.AllowedMentions(
                        users=[member], roles=False, everyone=False
                    ),
                )
            logger.info('Boas-vindas enviadas para %s em %s', member.id, cid)
            return True, 'Mensagem enviada ao canal de boas-vindas.'
        except discord.HTTPException as exc:
            logger.exception('Discord HTTP %s código %s: %s', exc.status, exc.code, exc.text)
            return False, f'Discord HTTP {exc.status} / código {exc.code}: {str(exc)[:250]}'
        except Exception as exc:
            logger.exception('Falha inesperada no envio de boas-vindas')
            return False, f'{type(exc).__name__}: {str(exc)[:250]}'

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            ok, detail = await self.enviar(member)
            if not ok:
                logger.error('Boas-vindas não enviadas para %s: %s', member.id, detail)

    @commands.command(name='testeboasvindas')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def teste_boas_vindas(self, ctx: commands.Context):
        ok, detail = await self.enviar(ctx.author)
        await ctx.reply(('✅ ' if ok else '❌ ') + detail, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasRoyal(bot))
