from __future__ import annotations
import asyncio
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils import cassino_db as db
from utils import cassino_partidas as partidas
from utils import cassino_extras as extras

LOG = logging.getLogger(__name__)
COR = 0xA52A35
MOEDA = 'SC'
MIN_APOSTA = 10
MAX_APOSTA = 1000
BANNER = os.getenv('CASSINO_BANNER_URL', '').strip()


def fmt(n):
    return f'{n:,}'.replace(',', '.') + ' SC'


def painel_embed():
    e = discord.Embed(title='<:thedevilgrin:1559778113519493151> CASSINO DO DIABO', description=(
        '**BEM-VINDO À MESA DO DESTINO**\n'
        '> `🎲` Escolha um jogo no menu abaixo.\n'
        '> `🪙` Aposte Sant’s Coins, a moeda compartilhada com os leilões.\n'
        '> `📜` Apenas grandes vitórias podem ser anunciadas.\n\n'
        '**JOGOS DISPONÍVEIS**\n'
        '> `🪙` Cara ou Coroa\n'
        '> `🎲` Dados\n'
        '> `🎡` Roleta\n'
        '> `👑` Mesa do King Dice\n'
        '> `📜` Contratos do Diabo — recompensas diárias gratuitas\n'
        '> `🃏` Cartas do Destino — uma escolha gratuita por dia\n\n'
        '**LIMITES**\n'
        f'> `💰` {fmt(MIN_APOSTA)} a {fmt(MAX_APOSTA)} por rodada.\n'
        '> `⏳` Uma partida por vez, com intervalo de 5 segundos.\n'
        '> `📜` Use os botões para consultar suas estatísticas.\n\n'
        '*Apostas usam apenas moedas virtuais do servidor.*'
    ), color=COR)
    if BANNER.startswith(('https://', 'http://')):
        e.set_image(url=BANNER)
    e.set_footer(text="Família Sant's • Cassino do Diabo • Esperamos que você perca")
    return e


def resultado_embed(jogo, escolha, sorteio, aposta, premio, saldo, numero):
    venceu = premio > 0
    e = discord.Embed(
        title='🏆 O DIABO PAGOU!' if venceu else '🎭 A CASA VENCEU',
        description=(f'**{jogo}** · Rodada `{numero[:8]}`\n'
                     f'> Sua escolha: **{escolha}**\n'
                     f'> Resultado: **{sorteio}**\n\n'
                     f'**Aposta:** {fmt(aposta)}\n'
                     f'**Prêmio bruto:** {fmt(premio)}\n'
                     f'**Resultado líquido:** {"+" if premio-aposta >= 0 else ""}{fmt(premio-aposta)}\n'
                     f'**Saldo:** {fmt(saldo)}'),
        color=0x26996C if venceu else COR
    )
    e.set_footer(text='Família Sant\'s • Partida registrada • Esperamos que você perca')
    return e


class ApostaModal(discord.ui.Modal, title='🎲 Mesa do Diabo'):
    valor = discord.ui.TextInput(label='Valor da aposta (SC)', placeholder='100', min_length=1, max_length=8)
    escolha = discord.ui.TextInput(label='Escolha', placeholder='cara / coroa', max_length=20)

    def __init__(self, cog, jogo):
        super().__init__(timeout=180)
        self.cog = cog
        self.jogo = jogo
        self.escolha.label = {'cara': 'Cara ou coroa', 'dados': 'Número de 1 a 6', 'roleta': 'vermelho / preto / verde'}[jogo]
        self.escolha.placeholder = {'cara': 'cara', 'dados': '4', 'roleta': 'vermelho'}[jogo]

    async def on_submit(self, interaction):
        try:
            aposta = int(self.valor.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ Digite uma aposta numérica inteira.', ephemeral=True)
        escolha = self.escolha.value.strip().lower()
        await self.cog.jogar(interaction, self.jogo, aposta, escolha)


class KingDiceModal(discord.ui.Modal, title='👑 Mesa do King Dice'):
    valor = discord.ui.TextInput(label='Aposta em SC', placeholder='100', min_length=1, max_length=8)
    etapas = discord.ui.TextInput(label='Quantidade de desafios (1, 2 ou 3)', placeholder='2', min_length=1, max_length=1)

    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    async def on_submit(self, interaction):
        try:
            aposta = int(self.valor.value.strip())
            etapas = int(self.etapas.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ Informe números inteiros válidos.', ephemeral=True)
        if etapas not in (1, 2, 3):
            return await interaction.response.send_message('❌ Escolha 1, 2 ou 3 desafios.', ephemeral=True)
        await self.cog.jogar(interaction, 'kingdice', aposta, str(etapas))


class CassinoView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.select(placeholder='🎲 Escolha sua mesa', custom_id='sants:cassino2:mesa', options=[
        discord.SelectOption(label='Cara ou Coroa', value='cara', emoji='🪙', description='50% de chance • prêmio 2×'),
        discord.SelectOption(label='Dados', value='dados', emoji='🎲', description='Acerte o número • prêmio 5×'),
        discord.SelectOption(label='Roleta', value='roleta', emoji='🎡', description='Vermelho, preto ou verde'),
        discord.SelectOption(label='Mesa do King Dice', value='kingdice', emoji='👑', description='Escolha 1, 2 ou 3 desafios'),
        discord.SelectOption(label='Contratos do Diabo', value='contratos', emoji='📜', description='Missões gratuitas diárias'),
        discord.SelectOption(label='Cartas do Destino', value='cartas', emoji='🃏', description='Uma carta grátis por dia'),
    ])
    async def mesa(self, interaction, select):
        jogo = select.values[0]
        if jogo == 'contratos':
            return await self.cog.mostrar_contratos(interaction)
        if jogo == 'cartas':
            return await self.cog.mostrar_cartas(interaction)
        await interaction.response.send_modal(KingDiceModal(self.cog) if jogo == 'kingdice' else ApostaModal(self.cog, jogo))

    @discord.ui.button(label='Carteira', emoji='🪙', style=discord.ButtonStyle.secondary, custom_id='sants:cassino2:saldo', row=1)
    async def carteira(self, interaction, button):
        saldo = await db.obter_saldo(interaction.user.id)
        await interaction.response.send_message(f'🪙 Sua carteira: **{fmt(saldo)}**', ephemeral=True)

    @discord.ui.button(label='Meu perfil', emoji='📊', style=discord.ButtonStyle.secondary, custom_id='sants:cassino2:perfil', row=1)
    async def perfil(self, interaction, button):
        s = await partidas.estatisticas_cassino(interaction.user.id)
        await interaction.response.send_message(
            f'📊 **Seu histórico no cassino**\n> Partidas: **{s["partidas"]}**\n'
            f'> Vitórias: **{s["vitorias"]}**\n> Derrotas: **{s["derrotas"]}**\n'
            f'> Resultado líquido: **{fmt(s["lucro"])}**', ephemeral=True)

    @discord.ui.button(label='Ranking semanal', emoji='🏆', style=discord.ButtonStyle.secondary, custom_id='sants:cassino2:ranking', row=1)
    async def ranking(self, interaction, button):
        rows = await partidas.ranking_cassino(10)
        texto = '\n'.join(f'`{i}.` <@{r["user_id"]}> — {fmt(r["lucro"])}' for i, r in enumerate(rows, 1)) or 'Nenhuma partida nesta semana.'
        await interaction.response.send_message('🏆 **Ranking semanal por lucro líquido**\n' + texto, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())



class ContratoView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label='Concluir visita (+40 SC)', emoji='📜', style=discord.ButtonStyle.success)
    async def coletar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.coletar_visita(interaction)


class CartasView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog
        for numero in (1, 2, 3):
            botao = discord.ui.Button(label=f'Carta {numero}', emoji='🂠', style=discord.ButtonStyle.primary)
            async def callback(interaction, n=numero):
                await self.cog.revelar_carta(interaction, n)
            botao.callback = callback
            self.add_item(botao)


class Cassino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locks = {}
        self.ultimo = {}

    async def cog_load(self):
        pool = getattr(self.bot, 'pool', None)
        if pool is None:
            raise RuntimeError('PostgreSQL indisponível: bot.pool não configurado')
        db.configurar_pool(pool)
        await db.inicializar_tabelas(pool)
        await partidas.inicializar_cassino(pool)
        await extras.inicializar_extras(pool)
        self.bot.add_view(CassinoView(self))
        LOG.info('Cassino 2.0: painel persistente registrado')

    async def mostrar_contratos(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dados = await extras.estado_contratos(interaction.user.id)
            embed = discord.Embed(
                title='📜 CONTRATOS DO DIABO',
                description=(
                    '**╭・MISSÕES DO DIA (UTC)**\n'
                    f'> `🚪` Visitar o salão — **40 SC** {"✅" if dados["visita"] else "⏳"}\n'
                    f'> `🃏` Revelar uma Carta do Destino — **60 SC** {"✅" if dados["carta"] else "⏳"}\n\n'
                    '> `ℹ️` A recompensa de visita é obtida pelo botão abaixo.\n'
                    '> `🔒` A missão da carta é creditada automaticamente ao revelar uma carta.\n'
                    '> `🕛` Reinício diário às 00:00 UTC.'
                ), color=COR)
            await interaction.followup.send(embed=embed, view=ContratoView(self), ephemeral=True)
        except Exception:
            LOG.exception('Falha ao consultar contratos')
            await interaction.followup.send('❌ Não foi possível consultar os contratos agora.', ephemeral=True)

    async def mostrar_cartas(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dados = await extras.estado_contratos(interaction.user.id)
            if dados['carta']:
                return await interaction.followup.send('🃏 Sua carta de hoje já foi revelada. Volte após 00:00 UTC.', ephemeral=True)
            embed = discord.Embed(title='🃏 CARTAS DO DESTINO', description=(
                '**Três cartas. Um destino.**\n'
                '> `🂠` Escolha uma das cartas abaixo.\n'
                '> `🎁` Recompensas possíveis: 0, 25, 50 ou 100 SC.\n'
                '> `📜` A primeira carta do dia também conclui o contrato de **60 SC**.\n\n'
                '**Probabilidades por tentativa**\n'
                '> `40%` — 0 SC\n> `35%` — 25 SC\n'
                '> `20%` — 50 SC\n> `5%` — 100 SC\n\n'
                '*As três cartas possuem as mesmas probabilidades. Uma tentativa por dia (UTC).*'
            ), color=COR)
            await interaction.followup.send(embed=embed, view=CartasView(self), ephemeral=True)
        except Exception:
            LOG.exception('Falha ao abrir cartas')
            await interaction.followup.send('❌ Não foi possível abrir as cartas agora.', ephemeral=True)

    async def coletar_visita(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            ganho, saldo = await extras.coletar_visita(interaction.user.id)
            msg = f'📜 Contrato concluído! **+40 SC**. Saldo: **{fmt(saldo)}**.' if ganho else '⌛ Você já concluiu o contrato de visita hoje.'
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            LOG.exception('Falha ao coletar visita')
            await interaction.followup.send('❌ Não foi possível concluir o contrato. Tente mais tarde.', ephemeral=True)

    async def revelar_carta(self, interaction, carta):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            resultado = await extras.revelar_carta(interaction.user.id, carta)
            if not resultado['novo']:
                return await interaction.followup.send('🃏 Você já revelou uma carta hoje. Volte amanhã (UTC).', ephemeral=True)
            await interaction.followup.send(
                f'🃏 **Carta {carta} revelada!**\n'
                f'> Prêmio da carta: **{fmt(resultado["premio"])}**\n'
                f'> Contrato concluído: **+60 SC**\n'
                f'> Saldo atual: **{fmt(resultado["saldo"])}**', ephemeral=True)
        except Exception:
            LOG.exception('Falha ao revelar carta')
            await interaction.followup.send('❌ Não foi possível confirmar sua carta. Consulte seu extrato antes de tentar novamente.', ephemeral=True)

    async def jogar(self, interaction, jogo, aposta, escolha):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild is None:
            return await interaction.followup.send('❌ Jogue dentro do servidor.', ephemeral=True)
        if not MIN_APOSTA <= aposta <= MAX_APOSTA:
            return await interaction.followup.send(f'❌ Aposte entre {fmt(MIN_APOSTA)} e {fmt(MAX_APOSTA)}.', ephemeral=True)
        escolhas = {'cara': ('cara', 'coroa'), 'dados': tuple(str(i) for i in range(1, 7)), 'roleta': ('vermelho', 'preto', 'verde'), 'kingdice': ('1', '2', '3')}
        if escolha not in escolhas[jogo]:
            return await interaction.followup.send(f'❌ Escolha válida: {", ".join(escolhas[jogo])}.', ephemeral=True)
        uid = interaction.user.id
        lock = self.locks.setdefault(uid, asyncio.Lock())
        if lock.locked():
            return await interaction.followup.send('⏳ Sua partida anterior ainda está sendo processada.', ephemeral=True)
        async with lock:
            import time
            if time.monotonic() - self.ultimo.get(uid, 0) < 5:
                return await interaction.followup.send('⏳ Aguarde 5 segundos entre partidas.', ephemeral=True)
            self.ultimo[uid] = time.monotonic()
            if jogo == 'cara':
                sorteio = ('cara', 'coroa')[secrets.randbelow(2)]
                mult = 2
                titulo = 'Cara ou Coroa'
            elif jogo == 'dados':
                sorteio = str(secrets.randbelow(6) + 1)
                mult = 5
                titulo = 'Dados'
            elif jogo == 'kingdice':
                # Cada desafio tem 50% de chance; pagamento bruto 1.5x, 3x ou 6x.
                # A quantidade de desafios é escolhida ANTES da aposta; não há
                # cobrança parcial nem sessão pendente entre interações.
                etapas = int(escolha)
                sucessos = 0
                for _ in range(etapas):
                    if secrets.randbelow(2) != 0:
                        break
                    sucessos += 1
                sorteio = f'{sucessos}/{etapas} desafios vencidos'
                mult = {1: 1.5, 2: 3, 3: 6}[etapas]
                titulo = 'Mesa do King Dice'
            else:
                numero = secrets.randbelow(37)
                sorteio = 'verde' if numero == 0 else ('vermelho' if numero <= 18 else 'preto')
                mult = 14 if escolha == 'verde' else 2
                titulo = 'Roleta'
            if jogo == 'kingdice':
                premio = int(aposta * mult) if sucessos == etapas else 0
            else:
                premio = aposta * mult if escolha == sorteio else 0
            numero = str(uuid.uuid4())
            try:
                saldo = await partidas.finalizar_partida_cassino(uid, interaction.guild.id, numero, jogo, escolha, sorteio, aposta, premio)
            except partidas.SaldoInsuficiente:
                return await interaction.followup.send('❌ Saldo insuficiente para essa aposta.', ephemeral=True)
            except Exception:
                LOG.exception('Falha ao registrar partida %s', numero)
                return await interaction.followup.send('❌ Não foi possível confirmar a partida. Confira seu extrato antes de tentar novamente.', ephemeral=True)
            exibicao = f'{escolha} desafio(s)' if jogo == 'kingdice' else escolha
            await interaction.followup.send(embed=resultado_embed(titulo, exibicao, sorteio, aposta, premio, saldo, numero), ephemeral=True)

    @commands.command(name='painelcassino')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def painel_cassino(self, ctx):
        await ctx.send(embed=painel_embed(), view=CassinoView(self), allowed_mentions=discord.AllowedMentions.none())
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name='cara', aliases=['coroa'])
    @commands.guild_only()
    async def cara(self, ctx, aposta: int, escolha: str = 'cara'):
        await ctx.reply('🎰 Utilize o **painel do cassino** para jogar com segurança e receber seu resultado privado.', mention_author=False)

    @commands.command(name='dados')
    @commands.guild_only()
    async def dados(self, ctx, aposta: int, palpite: int):
        await ctx.reply('🎰 Utilize o **painel do cassino** para jogar com segurança e receber seu resultado privado.', mention_author=False)

    @commands.command(name='roleta')
    @commands.guild_only()
    async def roleta(self, ctx, aposta: int, escolha: str = 'vermelho'):
        await ctx.reply('🎰 Utilize o **painel do cassino** para jogar com segurança e receber seu resultado privado.', mention_author=False)


async def setup(bot):
    await bot.add_cog(Cassino(bot))
