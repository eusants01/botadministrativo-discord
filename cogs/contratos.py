from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils import cassino_db as db
from utils import cassino_extras as extras

LOG = logging.getLogger('sants.contratos20')
COR = 0x3B8EEA

# Rotação por dia UTC. As recompensas são fixas, sem sorteio/apostas.
SELOS = [
    ('🗡️', 'Selo da Coragem', 'Aceite um desafio diante do Diabo.'),
    ('🛡️', 'Selo da Lealdade', 'Proteja seus companheiros de jornada.'),
    ('🔥', 'Selo da Determinação', 'Mostre que não desiste facilmente.'),
    ('🎭', 'Selo da Astúcia', 'Enfrente a sorte com inteligência.'),
    ('⭐', 'Selo da Honra', 'Honre sua palavra e seus aliados.'),
    ('💎', 'Selo da Perseverança', 'Continue mesmo diante dos obstáculos.'),
    ('⚔️', 'Selo do Desafio', 'Prepare-se para o próximo episódio.'),
]
PREMIO_SELO = 20
PREMIO_FINAL = 30

SQL = """
CREATE TABLE IF NOT EXISTS sants_contratos20_diario (
    user_id BIGINT NOT NULL,
    dia DATE NOT NULL,
    selo_resgatado BOOLEAN NOT NULL DEFAULT FALSE,
    final_resgatado BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, dia)
);
"""


def selo_do_dia():
    return SELOS[datetime.now(timezone.utc).date().toordinal() % len(SELOS)]


class Contratos20View(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label='Visitar o Salão', emoji='🚪', style=discord.ButtonStyle.primary,
                       custom_id='sants:contratos20:visita')
    async def visita(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.executar(interaction, 'visita')

    @discord.ui.button(label='Aceitar Selo', emoji='📜', style=discord.ButtonStyle.primary,
                       custom_id='sants:contratos20:selo')
    async def selo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.executar(interaction, 'selo')

    @discord.ui.button(label='Recompensa Final', emoji='🎁', style=discord.ButtonStyle.success,
                       custom_id='sants:contratos20:final')
    async def final(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.executar(interaction, 'final')

    @discord.ui.button(label='Meu Progresso', emoji='📊', style=discord.ButtonStyle.secondary,
                       custom_id='sants:contratos20:status')
    async def status(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.executar(interaction, 'status')


class ContratosDiabo20(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def pool(self):
        return getattr(self.bot, 'pool', None)

    async def cog_load(self):
        if self.pool is None:
            raise RuntimeError('Contratos 2.0: bot.pool não foi configurado')
        # Idempotente: não apaga, renomeia ou altera dados existentes.
        db.configurar_pool(self.pool)
        await db.inicializar_tabelas(self.pool)
        await extras.inicializar_extras(self.pool)
        await self.pool.execute(SQL)
        self.bot.add_view(Contratos20View(self))
        LOG.info('Contratos do Diabo 2.0 carregados')

    async def _estado(self, conn, uid):
        await conn.execute('''
            INSERT INTO sants_contratos20_diario(user_id, dia)
            VALUES($1, (NOW() AT TIME ZONE 'UTC')::date)
            ON CONFLICT DO NOTHING
        ''', uid)
        novo = await conn.fetchrow('''
            SELECT selo_resgatado, final_resgatado
            FROM sants_contratos20_diario
            WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
            FOR UPDATE
        ''', uid)
        antigo = await conn.fetchrow('''
            SELECT visita, carta FROM sants_cassino_extras_diario
            WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
        ''', uid)
        return {
            'visita': bool(antigo['visita']) if antigo else False,
            'carta': bool(antigo['carta']) if antigo else False,
            'selo': bool(novo['selo_resgatado']),
            'final': bool(novo['final_resgatado']),
        }

    async def _creditar(self, conn, uid, quantia, descricao):
        await db.garantir_carteira(uid, conn)
        await conn.execute('''
            UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW()
            WHERE user_id=$1
        ''', uid, quantia)
        await conn.execute('''
            INSERT INTO sants_transacoes(user_id, tipo, quantia, descricao)
            VALUES($1, 'credito', $2, $3)
        ''', uid, quantia, descricao)

    async def _recompensa(self, uid, acao):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                estado = await self._estado(conn, uid)
                if acao == 'selo':
                    if estado['selo']:
                        return '⌛ Você já aceitou o Selo do Diabo hoje.'
                    await conn.execute('''
                        UPDATE sants_contratos20_diario SET selo_resgatado=TRUE
                        WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
                    ''', uid)
                    await self._creditar(conn, uid, PREMIO_SELO, 'Contratos 2.0 • selo diário')
                    return f'📜 Selo aceito! **+{PREMIO_SELO} SC** creditadas.'
                if acao == 'final':
                    if estado['final']:
                        return '⌛ Você já recebeu a recompensa final de hoje.'
                    if not (estado['visita'] and estado['carta'] and estado['selo']):
                        return '🔒 Para liberar a recompensa final, conclua a visita, revele uma Carta do Destino e aceite o selo diário.'
                    await conn.execute('''
                        UPDATE sants_contratos20_diario SET final_resgatado=TRUE
                        WHERE user_id=$1 AND dia=(NOW() AT TIME ZONE 'UTC')::date
                    ''', uid)
                    await self._creditar(conn, uid, PREMIO_FINAL, 'Contratos 2.0 • recompensa final')
                    return f'🎁 Contrato completo! **+{PREMIO_FINAL} SC** creditadas.'
                return '❌ Ação inválida.'

    async def _embed(self, uid):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                estado = await self._estado(conn, uid)
        emoji, nome, descricao = selo_do_dia()
        marca = lambda x: '✅' if x else '⬜'
        embed = discord.Embed(
            title='😈 CONTRATOS DO DIABO 2.0',
            description=(
                '*Uma nova página do seu contrato foi revelada...*\n\n'
                f'**{emoji} {nome}**\n> {descricao}\n\n'
                '**Missões diárias**\n'
                f'{marca(estado["visita"])} 🚪 Visitar o Salão — **40 SC** (Cassino 2.2)\n'
                f'{marca(estado["carta"])} 🃏 Revelar uma Carta do Destino — **60 SC** + prêmio da carta (Cassino 2.2)\n'
                f'{marca(estado["selo"])} 📜 Aceitar o selo diário — **{PREMIO_SELO} SC**\n'
                f'{marca(estado["final"])} 🎁 Concluir as três etapas — **{PREMIO_FINAL} SC**\n\n'
                '**Como participar**\n'
                '> Use os botões para visitar o salão e aceitar o selo.\n'
                '> Revele sua carta no painel do cassino.\n'
                '> Depois, resgate a recompensa final aqui.\n\n'
                '*Reinício às 00:00 UTC. Os prêmios são gratuitos e não exigem apostas.*'
            ),
            color=COR,
        )
        embed.set_footer(text="Família Sant's • Episódio Cuphead")
        return embed

    async def executar(self, interaction, acao):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            uid = interaction.user.id
            if acao == 'visita':
                ganho, saldo = await extras.coletar_visita(uid)
                mensagem = f'🚪 Visita concluída! **+40 SC**. Saldo: **{saldo} SC**.' if ganho else '⌛ Visita já concluída hoje.'
            elif acao in ('selo', 'final'):
                mensagem = await self._recompensa(uid, acao)
            elif acao == 'status':
                return await interaction.followup.send(embed=await self._embed(uid), ephemeral=True)
            else:
                mensagem = '❌ Ação desconhecida.'
            await interaction.followup.send(mensagem, ephemeral=True)
        except Exception:
            LOG.exception('Erro em contrato 2.0: %s', acao)
            await interaction.followup.send('❌ Falha ao processar o contrato. Confira seu saldo antes de tentar novamente.', ephemeral=True)

    @commands.command(name='painelcontratos', aliases=['contratos2'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def painel_contratos(self, ctx):
        """Publica o painel permanente de Contratos do Diabo 2.0."""
        await ctx.send(embed=await self._embed(ctx.author.id), view=Contratos20View(self),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='meuscontratos')
    @commands.guild_only()
    async def meus_contratos(self, ctx):
        await ctx.reply(embed=await self._embed(ctx.author.id), mention_author=False)


async def setup(bot):
    await bot.add_cog(ContratosDiabo20(bot))
