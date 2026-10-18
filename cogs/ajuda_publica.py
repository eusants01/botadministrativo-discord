import logging
import os

import discord
from discord.ext import commands

LOG = logging.getLogger(__name__)
COR = 0x2375C8
BANNER_URL = os.getenv('AJUDA_BANNER_URL', 'https://cdn.discordapp.com/attachments/961677475191078992/1559807635270934588/Samurai_mask_glowing_blue_flames_20261014025530.gif?ex=6ad06b90&is=6acf1a10&hm=b1b189ae19d523c4eed1b09251e04071578ee6486a2de1d68cbcacc0ef0aff9d&').strip()
RODAPE = "Família Sant's • Central de Ajuda"

SECOES = {
    'economia': ('🪙 Economia • Sant’s Coins', [
        ('Sua carteira', '`!saldo` — Consultar saldo\n`!extrato` — Ver movimentações'),
        ('Recompensas e transferências', '`!diario` — Resgatar moedas diárias\n`!transferir @membro 100` — Transferir SC'),
        ('Integração', 'A mesma carteira de Sant’s Coins é utilizada nos leilões e no Cassino do Diabo.'),
    ]),
    'cassino': ('🎰 Cassino do Diabo • Episódio Cuphead', [
        ('Como acessar', 'Utilize o painel do **Cassino do Diabo** e selecione uma modalidade no menu.\n`!painelcassino` — Publicar painel (**Gerenciar Servidor**).'),
        ('Jogos disponíveis', '🪙 **Cara ou Coroa** — Escolha um lado.\n🎲 **Dados** — Escolha um número de 1 a 6.\n🎡 **Roleta** — Vermelho, preto ou verde.\n👑 **King Dice** — Escolha 1, 2 ou 3 desafios.'),
        ('Atividades diárias gratuitas', '📜 **Contratos do Diabo** — Missões diárias com recompensas.\n🃏 **Cartas do Destino** — Revele uma carta por dia.'),
        ('Consultas', 'Os botões do painel permitem consultar **Carteira**, **Meu perfil** e **Ranking semanal**.'),
        ('Regras', 'Apostas entre **10 e 1.000 SC** por rodada, com intervalo de 5 segundos. Jogos com apostas podem gerar perdas. As Sant’s Coins são exclusivamente virtuais.\nOs comandos antigos `!cara`, `!dados` e `!roleta` apenas orientam a usar o painel.'),
    ]),
    'leiloes': ('🔨 Leilões', [
        ('Como participar', 'Abra o painel de leilões, consulte os lotes ativos e utilize os botões para ofertar lances com Sant’s Coins.'),
        ('Comandos', '`!leiloes` — Consultar leilões ativos\n`!leilaosaldo` — Consultar carteira\n`!leilaostatus` — Ver situação dos leilões'),
        ('Painel', '`!painelleilao` — Abrir painel de leilões (conforme permissões do servidor).'),
        ('Importante', 'Cada lote possui condições, valores e prazos próprios. Confira-os antes de participar.'),
    ]),
    'tickets': ('🎟️ Atendimento e Tickets', [
        ('Solicitações', 'No painel de tickets, escolha a categoria apropriada, como suporte, denúncia, parcerias ou solicitação de cargos, e descreva seu pedido.'),
        ('Comandos úteis', '`!ticketajuda` — Informações do sistema\n`!painelticket` — Publicar painel (equipe autorizada).'),
    ]),
    'sorteios': ('🎁 Sorteios', [
        ('Participação', 'Acesse um sorteio ativo, confira o prêmio, o prazo e as regras, e use o botão **Participar**.'),
        ('Comandos úteis', '`!sorteioajuda` — Informações sobre sorteios\n`!painelsorteio` — Painel de sorteios (equipe autorizada).'),
    ]),
    'notificacoes': ('🔔 Notificações', [
        ('Preferências', 'No painel de notificações, escolha os cargos de aviso que deseja receber.'),
        ('Comandos úteis', '`!painelpings` — Painel de notificações (equipe autorizada)\n`!statuspings` — Consultar status.'),
    ]),
    'convites': ('📨 Convites', [
        ('Consultas', '`!convites` — Seus convites\n`!topconvites` — Ranking\n`!quemconvidou` — Consultar quem convidou\n`!convidados` — Ver convidados'),
        ('Ajuda', '`!conviteajuda` — Mais informações sobre o sistema de convites.'),
    ]),
}

OPCOES = [
    discord.SelectOption(label='Economia', value='economia', emoji='🪙', description='Saldo, diário e transferências'),
    discord.SelectOption(label='Cassino do Diabo', value='cassino', emoji='🎰', description='King Dice, contratos e cartas'),
    discord.SelectOption(label='Leilões', value='leiloes', emoji='🔨', description='Lances, itens e carteira'),
    discord.SelectOption(label='Tickets', value='tickets', emoji='🎟️', description='Atendimento e suporte'),
    discord.SelectOption(label='Sorteios', value='sorteios', emoji='🎁', description='Sorteios e premiações'),
    discord.SelectOption(label='Notificações', value='notificacoes', emoji='🔔', description='Cargos de avisos'),
    discord.SelectOption(label='Convites', value='convites', emoji='📨', description='Estatísticas e ranking'),
]
def criar_painel_v2(pagina: str = 'inicio', com_menu: bool = True) -> discord.ui.LayoutView:
    """Painel nativo Components V2, sem embed legado."""
    view = discord.ui.LayoutView(timeout=None if com_menu else 180)
    if pagina == 'inicio':
        texto = (
            "# 📖 Central de Ajuda\n"
            "Bem-vindo à central da **Família Sant's**.\n\n"
            "Selecione uma categoria para conhecer os sistemas disponíveis.\n"
            "- 🪙 Economia e Sant's Coins\n"
            "- 🎰 Cassino do Diabo\n"
            "- 🔨 Leilões\n"
            "- 🎟️ Tickets\n"
            "- 🎁 Sorteios\n"
            "- 🔔 Notificações\n"
            "- 📨 Convites"
        )
    else:
        titulo, campos = SECOES.get(pagina, SECOES['economia'])
        texto = '# ' + titulo + '\n\n' + '\n\n'.join(
            f'**{nome}**\n{valor}' for nome, valor in campos
        )
    partes = [discord.ui.TextDisplay(texto)]
    if pagina == 'inicio' and BANNER_URL.startswith(('https://', 'http://')):
        partes.insert(0, discord.ui.MediaGallery(discord.ui.MediaGalleryItem(media=BANNER_URL)))
    partes.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    partes.append(discord.ui.TextDisplay('-# ' + RODAPE))
    if com_menu:
        partes.append(discord.ui.ActionRow(MenuAjuda()))
    view.add_item(discord.ui.Container(*partes, accent_colour=discord.Colour(COR)))
    return view


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
            view=criar_painel_v2(self.values[0], com_menu=False),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )



class AjudaPublica(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(criar_painel_v2())
        LOG.info('Painel público de ajuda registrado como view persistente')

    @commands.command(name='ajuda', aliases=['comandos', 'helpme'])
    @commands.guild_only()
    async def ajuda(self, ctx):
        await ctx.send(view=criar_painel_v2(),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='publicarajuda')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def publicar_ajuda(self, ctx):
        await ctx.send(view=criar_painel_v2(),
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
