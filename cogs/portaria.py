"""Boas-vindas oficiais da Família Royal (discord.py >= 2.6, Components V2).

Variáveis opcionais no Railway:
WELCOME_CHANNEL_ID = 1563991142159360150 
ROYAL_RULES_CHANNEL_ID = 1553829609160835342 
ROYAL_ROLES_CHANNEL_ID = 1553820522322862200 
ROYAL_GIVEAWAYS_CHANNEL_ID = 1553829712621740103 
ROYAL_SUPPORT_CHANNEL_ID = 1553843978229522633 

"""

import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

logger = logging.getLogger('sants.bot.boas_vindas')
BASE_DIR = Path(__file__).resolve().parent.parent
BANNER = BASE_DIR / 'assets' / 'Família Royal_ Portal Celestial Dourado.png'


def _id_env(key: str):
    raw = os.getenv(key, '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning('%s inválido (esperado ID numérico): %r', key, raw)
        return None


def _canal(guild: discord.Guild, key: str, name: str):
    cid = _id_env(key)
    channel = guild.get_channel(cid) if cid else None
    if channel is None:
        channel = discord.utils.get(guild.text_channels, name=name)
    return channel if isinstance(channel, discord.TextChannel) else None


def _referencia(guild: discord.Guild, key: str, name: str) -> str:
    channel = _canal(guild, key, name)
    return channel.mention if channel else f'#{name}'


class BoasVindasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def enviar(self, member: discord.Member) -> bool:
        guild = member.guild
        channel = _canal(guild, 'WELCOME_CHANNEL_ID', 'boas-vindas')
        if channel is None:
            logger.warning('Canal de boas-vindas não encontrado em %s (%s)', guild.name, guild.id)
            return False

        eu = guild.me or guild.get_member(self.bot.user.id)
        if eu is None:
            logger.warning('Não foi possível verificar permissões em %s', guild.name)
            return False
        perms = channel.permissions_for(eu)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            logger.warning('Permissões insuficientes para enviar boas-vindas em %s', channel.id)
            return False

        rules = _referencia(guild, 'ROYAL_RULES_CHANNEL_ID', 'regras')
        giveaways = _referencia(guild, 'ROYAL_GIVEAWAYS_CHANNEL_ID', 'sorteios')
        support = _referencia(guild, 'ROYAL_SUPPORT_CHANNEL_ID', 'suporte')

        # Components V2: uma única mensagem, sem embed e sem texto externo.
        view = discord.ui.LayoutView(timeout=None)
        painel = discord.ui.Container(accent_colour=discord.Colour.from_rgb(190, 150, 79))
        arquivo = None
        if BANNER.is_file() and perms.attach_files:
            arquivo = discord.File(BANNER, filename='Família Royal_ Portal Celestial Dourado.png')
            painel.add_item(discord.ui.MediaGallery(
                discord.MediaGalleryItem(media='attachment://Família Royal_ Portal Celestial Dourado.png')
            ))
        elif not BANNER.is_file():
            logger.warning('Banner ausente: %s', BANNER)

        painel.add_item(discord.ui.TextDisplay(
            '## <:ImagemdoChatGPT25deoutde202615_4:1563986681332236520>・BEM-VINDO(A) À FAMÍLIA ROYAL\n'
            f'> `🪽` Seja muito bem-vindo(a), {member.mention}! É uma honra receber você em nosso reino.\n\n'
            f'> `📜` **Regras:** {rules}\n'
            f'> `🎉` **Sorteios:** {giveaways}\n'
            f'> `🎫` **Suporte:** {support}\n\n'
            '> `⚜️` **Que sua jornada seja marcada pela união, respeito e lealdade.**'
        ))
        view.add_item(painel)

        try:
            await channel.send(
                view=view,
                file=arquivo,
                allowed_mentions=discord.AllowedMentions(users=[member], roles=False, everyone=False),
            )
            return True
        except (discord.Forbidden, discord.HTTPException):
            logger.exception('Falha ao enviar boas-vindas no canal %s', channel.id)
            return False

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            await self.enviar(member)

    @commands.command(name='testeboasvindas')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def teste_boas_vindas(self, ctx: commands.Context):
        """Envia uma prévia para o canal de boas-vindas. Uso: !testeboasvindas"""
        sucesso = await self.enviar(ctx.author)
        await ctx.reply('✅ Prévia enviada ao canal de boas-vindas.' if sucesso
                        else '❌ Não consegui enviar. Confira canal, permissões e logs.',
                        mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasRoyal(bot))
