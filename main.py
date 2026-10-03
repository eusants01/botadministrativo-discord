import discord
import os
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

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

bot.setup_hook = setup_hook

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: Token não encontrado.")