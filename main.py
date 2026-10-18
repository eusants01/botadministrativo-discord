import asyncio
import logging
import os
from pathlib import Path

import asyncpg
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from painel import start_painel
from utils.components_v2 import install_components_v2
from utils.monitoring import install_monitor

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('sants.bot')

BASE_DIR = Path(__file__).resolve().parent
COGS_DIR = BASE_DIR / 'cogs'

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
install_components_v2(bot)

status_list = [
    "Sant's Family 👑",
    "Primeira Família do E.B 🎖️",
    "Desenvolvido por Sant's 🛠️",
    "Bot Administrativo da Família Sant's 🤖",
    "Monitorando o Servidor 🕒",
]


@tasks.loop(seconds=30)
async def mudar_status():
    nome = status_list[mudar_status.current_loop % len(status_list)]
    await bot.change_presence(activity=discord.Game(name=nome))


@mudar_status.before_loop
async def antes_status():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    logger.info('✅ Bot %s online | ID: %s', bot.user, bot.user.id)
    logger.info('📊 Servidores conectados: %s', len(bot.guilds))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        logger.warning('Comando desconhecido: %s', ctx.message.content[:150])
        return
    logger.error('Erro no comando !%s: %r', ctx.command, error, exc_info=error)
    if isinstance(error, commands.CheckFailure):
        await ctx.send('❌ Você não tem permissão para executar este comando.')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('❌ Faltam argumentos para este comando.')
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f'⏳ Aguarde {error.retry_after:.1f} segundos.')
    else:
        await ctx.send('❌ Ocorreu um erro ao executar o comando.')


async def setup_hook():
    if not getattr(bot, "_sants_monitor_installed", False):
        bot._sants_monitor_installed = True
        bot._sants_monitor = install_monitor(asyncio.get_running_loop())

    url = os.getenv('DATABASE_URL')
    if not url:
        logger.error('❌ DATABASE_URL não encontrada no ambiente.')
    else:
        try:
            bot.pool = await asyncpg.create_pool(url, min_size=1, max_size=10)
            logger.info('🗄️ Pool PostgreSQL conectado')
        except Exception:
            logger.exception('❌ Falha ao conectar ao PostgreSQL')

    if not COGS_DIR.is_dir():
        logger.error('❌ Pasta de cogs não encontrada: %s', COGS_DIR)
    else:
        for arquivo in sorted(COGS_DIR.glob('*.py')):
            if arquivo.name.startswith('_'):
                continue
            extensao = f'cogs.{arquivo.stem}'
            try:
                await bot.load_extension(extensao)
                logger.info('📦 Cog carregado: %s', extensao)
            except Exception:
                logger.exception('❌ Erro ao carregar %s', extensao)

    logger.info('📦 Extensões carregadas: %s', list(bot.extensions))
    logger.info('🔎 Comandos !: %s', [c.qualified_name for c in bot.walk_commands()])

    # Slash commands desativados — o bot usa apenas prefixo !
    # (tree.sync removido para não publicar comandos / no Discord)

    if not mudar_status.is_running():
        mudar_status.start()

    try:
        await start_painel(bot)
        logger.info('🌐 Painel iniciado')
    except Exception:
        logger.exception('❌ Erro ao iniciar o painel')


bot.setup_hook = setup_hook

_close_original = bot.close


async def close_com_pool():
    try:
        if mudar_status.is_running():
            mudar_status.cancel()
        pool = getattr(bot, 'pool', None)
        if pool is not None:
            await pool.close()
    finally:
        await _close_original()


bot.close = close_com_pool

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN não encontrado no ambiente.')
    bot.run(token)
    
