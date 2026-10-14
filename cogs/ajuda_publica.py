import logging
import os

import discord
from discord.ext import commands

LOG = logging.getLogger(__name__)
COR = 0x2375C8
BANNER_URL = os.getenv('AJUDA_BANNER_URL', 'https://cdn.discordapp.com/attachments/961677475191078992/1559807635270934588/Samurai_mask_glowing_blue_flames_20261014025530.gif?ex=6ad06b90&is=6acf1a10&hm=b1b189ae19d523c4eed1b09251e04071578ee6486a2de1d68cbcacc0ef0aff9d&').strip()
RODAPE = "Família Sant's • Central de Ajuda"

SECOES = {
    'economia': ('🪙 Economia', [
        ('Carteira', '`!saldo` — Consultar moedas\n`!extrato` — Ver movimentações\n`!diario` — Coletar recompensa diária'),
        ('Transferências', '`!transferir @membro 100` — Enviar 100 moedas'),
    ]),
    'cassino': ('🎲 Cassino', [
        ('Jogos', '`!cara 100 cara` — Cara ou coroa\n`!dados 100 4` — Apostar no número 4\n`!roleta 100 vermelho` — Apostar no vermelho'),
        ('Atenção', 'As apostas utilizam Sant’s Coins e podem gerar perdas.'),
    ]),
    'leiloes': ('🔨 Leilões', [
        ('Comandos', '`!leiloes` — Consultar leilões\n`!leilaosaldo` — Consultar saldo'),
        ('Participação', 'Abra um leilão ativo e utilize os botões para dar seu lance.'),
    ]),
    'tickets': ('🎟️ Atendimento', [
        ('Como solicitar', 'Acesse o painel de tickets, escolha a categoria e descreva seu pedido.'),
    ]),
    'sorteios': ('🎁 Sorteios', [
        ('Como participar', 'Acesse um sorteio ativo, confira as regras e use o botão de participação.'),
    ]),
    'notificacoes': ('🔔 Notificações', [
        ('Preferências', 'Acesse o painel de notificações e selecione os cargos de avisos desejados.'),
    ]),
}

OPCOES = [
    discord.SelectOption(label='Economia', value='economia', emoji='🪙', description='Saldo, diário e transferências'),
    discord.SelectOption(label='Cassino', value='cassino', emoji='🎲', description='Jogos e apostas'),
    discord.SelectOption(label='Leilões', value='leiloes', emoji='🔨', description='Lances e consultas'),
    discord.SelectOption(label='Tickets', value='tickets', emoji='🎟️', description='Atendimento e suporte'),
    discord.SelectOption(label='Sorteios', value='sorteios', emoji='🎁', description='Participação em sorteios'),
    discord.SelectOption(label='Notificações', value='notificacoes', emoji='🔔', description='Cargos de avisos'),
]


def criar_embed(pagina='inicio'):
    if pagina == 'inicio':
        embed = discord.Embed(
            title='📘 Central de Ajuda',
            description=(
                "<a:animated_Settings:1556187476177981440> Bem-vindo à central de informações da **Família Sant's**.\n\n"
                'Selecione uma categoria no menu abaixo para consultar os comandos e suas funcionalidades.\n\n'
                '**Categorias disponíveis**\n'
                '> `🪙` Economia e Cassino\n'
                '> `🔨` Leilões\n'
                '> `🎟️` Atendimento\n'
                '> `🎁` Sorteios\n'
                '> `🔔` Notificações'
            ),
            color=COR,
        )
        if BANNER_URL.startswith(('https://', 'http://')):
            embed.set_image(url=BANNER_URL)
    else:
        titulo, campos = SECOES.get(pagina, SECOES['economia'])
        embed = discord.Embed(title=titulo, color=COR)
        for nome, valor in campos:
            embed.add_field(name=nome, value=valor, inline=False)
    embed.set_footer(text=RODAPE)
    return embed


class MenuAjuda(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder='Selecione uma categoria',
            custom_id='sants:ajuda_publica:categoria',
            min_values=1,
            max_values=1,
            options=OPCOES,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=criar_embed(self.values[0]),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class PainelAjuda(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuAjuda())


class AjudaPublica(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PainelAjuda())
        LOG.info('Painel público de ajuda registrado como view persistente')

    @commands.command(name='ajuda', aliases=['comandos', 'helpme'])
    @commands.guild_only()
    async def ajuda(self, ctx):
        await ctx.send(embed=criar_embed(), view=PainelAjuda(),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='publicarajuda')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def publicar_ajuda(self, ctx):
        await ctx.send(embed=criar_embed(), view=PainelAjuda(),
                       allowed_mentions=discord.AllowedMentions.none())
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @publicar_ajuda.error
    async def erro_publicar(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('❌ Apenas membros com **Gerenciar Servidor** podem publicar o painel.', delete_after=12)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(AjudaPublica(bot))
