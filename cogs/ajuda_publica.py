
import logging
import os

import discord
from discord.ext import commands

LOG = logging.getLogger(__name__)
COR = 0x2375C8
MARCA = "Família Sant's  •  Central de Ajuda"
BANNER_URL = os.getenv("AJUDA_BANNER_URL", "https://i.imgur.com/epIDAS3.png").strip()

SECOES = {
    "inicio": (
        "<a:animated_Settings:1556187476177981440> CENTRAL DE AJUDA",
        "**BEM-VINDO À CENTRAL DA FAMÍLIA SANT'S**\n"
        "> `📚` Consulte os comandos disponíveis para membros.\n"
        "> `🧭` Selecione uma categoria no menu abaixo.\n"
        "> `🔒` As opções da administração não são exibidas.\n\n"
        "**COMO FUNCIONA?**\n"
        "> `01` Escolha um sistema no seletor.\n"
        "> `02` Leia as instruções e exemplos.\n"
        "> `03` Use o comando no canal permitido.\n\n"
        "*As respostas do menu são privadas para quem consulta.*",
    ),
    "economia": (
        "🪙  ECONOMIA • SANT'S COINS",
        "**SUA CARTEIRA**\n"
        "> `🪙` `!saldo` — consultar suas moedas.\n"
        "> `👤` `!saldo @membro` — consultar outro saldo, quando permitido.\n"
        "> `🎁` `!diario` — coletar a recompensa diária.\n"
        "> `📜` `!extrato` — conferir movimentações.\n\n"
        "**TRANSFERÊNCIAS**\n"
        "> `💸` `!transferir @membro 100` — enviar 100 moedas.\n\n"
        "**ATALHOS**\n"
        "> `🔁` `!carteira`, `!coins`, `!daily`, `!coletar`, `!pagar`, `!pix`, `!historico`, `!transacoes`.\n\n"
        "*As moedas também podem ser usadas nos jogos e leilões.*",
    ),
    "cassino": (
        "🎲  CASSINO • JOGOS",
        "**ESCOLHA SEU JOGO**\n"
        "> `🪙` `!cara 100 cara` — apostar 100 em cara.\n"
        "> `🪙` `!cara 100 coroa` — apostar 100 em coroa.\n"
        "> `🎲` `!dados 100 4` — apostar 100 no número 4.\n"
        "> `🎡` `!roleta 100 vermelho` — apostar 100 no vermelho.\n\n"
        "**ANTES DE JOGAR**\n"
        "> `💰` Confira suas moedas com `!saldo`.\n"
        "> `⚠️` Apostar pode aumentar ou diminuir seu saldo.\n"
        "> `📝` Informe o valor da aposta depois do comando.",
    ),
    "leiloes": (
        "🔨  LEILÕES • PARTICIPAÇÃO",
        "**CONSULTAR**\n"
        "> `📦` `!leiloes` — visualizar os leilões ativos.\n"
        "> `🪙` `!leilaosaldo` — consultar saldo disponível.\n\n"
        "**COMO PARTICIPAR**\n"
        "> `01` Abra o anúncio de um leilão ativo.\n"
        "> `02` Use os botões e formulários do anúncio.\n"
        "> `03` Confira seu lance antes de confirmar.\n\n"
        "`⚠️` Você precisa ter saldo suficiente para ofertar.",
    ),
    "tickets": (
        "🎟️  TICKETS • ATENDIMENTO",
        "**PRECISA DE AJUDA?**\n"
        "> `🎫` Encontre o painel de tickets do servidor.\n"
        "> `📂` Selecione a categoria adequada ao seu pedido.\n"
        "> `✍️` Explique a situação com informações úteis.\n"
        "> `⌛` Aguarde o atendimento da equipe.\n\n"
        "`🔒` As ferramentas de gerenciamento são reservadas aos responsáveis.",
    ),
    "sorteios": (
        "🎁  SORTEIOS • PARTICIPAÇÃO",
        "**COMO PARTICIPAR**\n"
        "> `🎁` Localize um anúncio de sorteio ativo.\n"
        "> `🖱️` Utilize o botão de participação, se disponível.\n"
        "> `📋` Leia os requisitos e as regras do sorteio.\n"
        "> `🏆` Acompanhe o resultado no canal correspondente.\n\n"
        "`ℹ️` Cada sorteio pode ter condições próprias.",
    ),
    "notificacoes": (
        "🔔  NOTIFICAÇÕES • AVISOS",
        "**ESCOLHA O QUE RECEBER**\n"
        "> `🔔` Encontre o painel de notificações do servidor.\n"
        "> `🏷️` Selecione os cargos de avisos disponíveis.\n"
        "> `🔄` Volte ao painel quando quiser alterar sua escolha.\n\n"
        "`ℹ️` Os avisos dependem das opções configuradas pela equipe.",
    ),
}

OPCOES = [
    ("inicio", "Página inicial", "📘"),
    ("economia", "Economia", "🪙"),
    ("cassino", "Cassino", "🎲"),
    ("leiloes", "Leilões", "🔨"),
    ("tickets", "Tickets", "🎟️"),
    ("sorteios", "Sorteios", "🎁"),
    ("notificacoes", "Notificações", "🔔"),
]


def criar_embed(pagina: str) -> discord.Embed:
    titulo, descricao = SECOES.get(pagina, SECOES["inicio"])
    embed = discord.Embed(title=titulo, description=descricao, color=COR)
    if pagina == "inicio":
        embed.add_field(
            name="╭・CATEGORIAS DISPONÍVEIS",
            value=("> `🪙` Economia  •  `🎲` Cassino\n"
                   "> `🔨` Leilões  •  `🎟️` Tickets\n"
                   "> `🎁` Sorteios  •  `🔔` Notificações"),
            inline=False,
        )
        if BANNER_URL.startswith(("https://", "http://")):
            embed.set_image(url=BANNER_URL)
    embed.set_footer(text=MARCA)
    return embed


class MenuAjuda(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="📚 Escolha a categoria que deseja consultar",
            min_values=1,
            max_values=1,
            custom_id="sants:ajuda_publica:categoria",
            options=[discord.SelectOption(label=nome, value=chave, emoji=emoji)
                     for chave, nome, emoji in OPCOES],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=criar_embed(self.values[0]), ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class PainelAjuda(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuAjuda())


class AjudaPublica(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PainelAjuda())
        LOG.info("Painel público de ajuda registrado como view persistente")

    @commands.command(name="ajuda", aliases=["comandos", "helpme"])
    @commands.guild_only()
    async def ajuda(self, ctx: commands.Context):
        """Mostra a ajuda; o painel fixo deve ser publicado com !publicarajuda."""
        await ctx.send(embed=criar_embed("inicio"), view=PainelAjuda(),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="publicarajuda")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def publicar_ajuda(self, ctx: commands.Context):
        """Publica o painel permanente no canal atual."""
        await ctx.send(embed=criar_embed("inicio"), view=PainelAjuda(),
                       allowed_mentions=discord.AllowedMentions.none())
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @publicar_ajuda.error
    async def erro_publicar(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Apenas quem possui **Gerenciar Servidor** pode publicar este painel.",
                           delete_after=12)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AjudaPublica(bot))
