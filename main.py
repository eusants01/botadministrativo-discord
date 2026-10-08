import discord
import os
import asyncpg
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

from painel import start_painel

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)


status_list = [
    "Sant's Family 👑",
    "Primeira Família do E.B 🎖️",
    "Desenvolvido por Sant's 🛠️",
    "Bot Administrativo da Família Sant's 🤖",
    "Monitorando o Servidor 🕒"
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
    print(f'✅ O bot {bot.user} está online!')


async def setup_hook():
    # Pool do PostgreSQL (Railway), compartilhado por todos os cogs.
    # Precisa ser criado ANTES de carregar os cogs.
    url = os.getenv('DATABASE_URL')
    if not url:
        print('❌ DATABASE_URL não encontrada no ambiente.')
    else:
        try:
            bot.pool = await asyncpg.create_pool(url, min_size=1, max_size=10)
            print('🗄️ Pool PostgreSQL conectado')
        except Exception as e:
            print(f'❌ Erro ao conectar no PostgreSQL: {type(e).__name__}: {e}')

    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')

    for filename in sorted(os.listdir('./cogs')):
        if filename.endswith('.py') and not filename.startswith('_'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'📦 Cog carregado: {filename}')
            except Exception as e:
                print(f'❌ Erro ao carregar {filename}: {type(e).__name__}: {e}')

    if not mudar_status.is_running():
        mudar_status.start()

    try:
        await start_painel(bot)
        print('🌐 Painel iniciado')
    except Exception as e:
        print(f'❌ Erro ao iniciar o painel: {type(e).__name__}: {e}')


# Fecha o pool do PostgreSQL ao desligar o bot
_close_original = bot.close


async def close_com_pool():
    pool = getattr(bot, 'pool', None)
    if pool is not None:
        await pool.close()
    await _close_original()


bot.close = close_com_pool
bot.setup_hook = setup_hook

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: Token não encontrado.")