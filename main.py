import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ O bot {bot.user} está online com a nova estrutura!')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong! 🏓 A nova estrutura está a funcionar perfeitamente!')

# Executa o bot usando a token escondida
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: Token não encontrada. Verifique o ficheiro .env")