import discord
import os
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


status_list = [
    "Protegendo a Família Sant's 🛡️",
    "Primeira Família do E.B 🎖️",
    "Desenvolvido por Sant's 🛠️",
    "Bot Administrativo da Família Sant's 🤖",
    "Monitorizar o Servidor 🕒"
]

@tasks.loop(seconds=5)
async def mudar_status():
    
    await bot.change_presence(activity=discord.Game(name=status_list[mudar_status.current_loop % len(status_list)]))

@bot.event
async def on_ready():
    mudar_status.start()
    print(f'✅ O bot {bot.user} está online!')


async def setup_hook():
    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')

bot.setup_hook = setup_hook

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: Token não encontrada.")