
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord.ext import commands

LOG = logging.getLogger(__name__)
COR = 0x8B0000
MAX_PASSAGEIROS = 10
MIN_PASSAGEIROS = 2
BANNER = os.getenv('EXPRESSO_BANNER_URL', '').strip()

SQL = """
CREATE TABLE IF NOT EXISTS expresso_viagens (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    status TEXT NOT NULL DEFAULT 'embarque',
    passageiros BIGINT[] NOT NULL DEFAULT '{}',
    iniciado_por BIGINT,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def eh_staff(membro: discord.Member) -> bool:
    return membro.guild_permissions.manage_guild or membro.guild_permissions.administrator


class AcaoExpresso(discord.ui.Button):
    def __init__(self, cog: 'Expresso', acao: str, *, label: str, style: discord.ButtonStyle, emoji: str):
        super().__init__(label=label, style=style, emoji=emoji, custom_id=f'sants:expresso:{acao}')
        self.cog = cog
        self.acao = acao

    async def callback(self, interaction: discord.Interaction):
        await self.cog.executar(interaction, self.acao)


class PainelExpresso(discord.ui.LayoutView):
    def __init__(self, cog: 'Expresso', estado: dict | None = None):
        super().__init__(timeout=None)
        estado = estado or {}
        status = estado.get('status', 'embarque')
        passageiros = list(estado.get('passageiros') or [])
        titulo = '🚂 EXPRESSO FANTASMA'
        descricao = (
            '**Uma passagem para os trilhos do submundo.**\n'
            'O Diabo observa cada passageiro que ousa embarcar.\n\n'
            f'**Situação:** {"🚉 Embarque aberto" if status == "embarque" else "🔥 Viagem iniciada"}\n'
            f'**Passageiros:** {len(passageiros)}/{MAX_PASSAGEIROS}\n'
            f'**Tripulação:** {", ".join(f"<@{u}>" for u in passageiros) if passageiros else "Nenhum passageiro ainda"}\n\n'
            '*Primeira fase: embarque e partida; os vagões serão adicionados em uma próxima atualização.*'
        )
        blocos = []
        if BANNER.startswith(('https://', 'http://')):
            blocos.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=BANNER)))
        blocos.extend([
            discord.ui.TextDisplay(f'# {titulo}'),
            discord.ui.TextDisplay(descricao),
            discord.ui.Separator(),
        ])
        linha = discord.ui.ActionRow()
        for acao, nome, estilo, emoji in (
            ('embarcar', 'Embarcar', discord.ButtonStyle.success, '🎟️'),
            ('sair', 'Desembarcar', discord.ButtonStyle.secondary, '🚪'),
            ('passageiros', 'Passageiros', discord.ButtonStyle.primary, '👥'),
            ('iniciar', 'Iniciar viagem', discord.ButtonStyle.danger, '🚂'),
        ):
            botao = AcaoExpresso(cog, acao, label=nome, style=estilo, emoji=emoji)
            if status != 'embarque' and acao in ('embarcar', 'sair', 'iniciar'):
                botao.disabled = True
            linha.add_item(botao)
        blocos.append(linha)
        self.add_item(discord.ui.Container(*blocos, accent_colour=discord.Colour(COR)))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        LOG.error('Erro no painel do Expresso', exc_info=(type(error), error, error.__traceback__))
        if not interaction.response.is_done():
            await interaction.response.send_message('❌ Não foi possível processar a ação.', ephemeral=True)


class Expresso(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self):
        if not getattr(self.bot, 'pool', None):
            raise RuntimeError('Expresso requer PostgreSQL (bot.pool).')
        await self.bot.pool.execute(SQL)
        # Registro dos custom_ids, inclusive após reiniciar o Railway.
        self.bot.add_view(PainelExpresso(self))

    def lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def obter(self, guild_id: int):
        r = await self.bot.pool.fetchrow('SELECT * FROM expresso_viagens WHERE guild_id=$1', guild_id)
        return dict(r) if r else None

    async def atualizar_painel(self, estado: dict):
        canal = self.bot.get_channel(estado['channel_id'])
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(estado['channel_id'])
            except discord.HTTPException:
                LOG.warning('Canal do Expresso inacessível: %s', estado['channel_id'])
                return
        try:
            msg = await canal.fetch_message(estado['message_id'])
            await msg.edit(view=PainelExpresso(self, estado), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            LOG.exception('Falha ao atualizar painel do Expresso %s', estado['message_id'])

    @commands.command(name='expresso', aliases=['painelexpresso'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def painel(self, ctx: commands.Context):
        """Publica ou substitui o painel; não reseta uma viagem em andamento."""
        gid = ctx.guild.id
        async with self.lock(gid):
            anterior = await self.obter(gid)
            if anterior and anterior['status'] == 'viagem':
                return await ctx.reply('🚂 Uma viagem já foi iniciada. Use `!resetarexpresso` para preparar uma nova.', mention_author=False)
            passageiros = list(anterior['passageiros']) if anterior else []
            estado = {'status': 'embarque', 'passageiros': passageiros}
            msg = await ctx.send(view=PainelExpresso(self, estado), allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute('''
                INSERT INTO expresso_viagens (guild_id, channel_id, message_id, status, passageiros)
                VALUES ($1,$2,$3,'embarque',$4::bigint[])
                ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2, message_id=$3,
                status='embarque', passageiros=$4::bigint[], atualizado_em=NOW()
            ''', gid, ctx.channel.id, msg.id, passageiros)
            if anterior and anterior['message_id']:
                # Desativa o painel anterior para evitar dois pontos de embarque.
                antigo_canal = self.bot.get_channel(anterior['channel_id'])
                if antigo_canal:
                    try:
                        antigo = await antigo_canal.fetch_message(anterior['message_id'])
                        await antigo.edit(view=PainelExpresso(self, {'status':'viagem', 'passageiros':passageiros}))
                    except discord.HTTPException:
                        LOG.warning('Não foi possível desativar painel anterior do Expresso')

    @commands.command(name='resetarexpresso')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def resetar(self, ctx: commands.Context):
        gid = ctx.guild.id
        async with self.lock(gid):
            estado = await self.obter(gid)
            if not estado:
                return await ctx.reply('❌ Publique o painel com `!expresso` primeiro.', mention_author=False)
            await self.bot.pool.execute("UPDATE expresso_viagens SET status='embarque', passageiros='{}', iniciado_por=NULL, atualizado_em=NOW() WHERE guild_id=$1", gid)
            estado.update(status='embarque', passageiros=[])
            await self.atualizar_painel(estado)
        await ctx.reply('🚉 Embarque reiniciado. Os passageiros anteriores foram removidos.', mention_author=False)

    async def executar(self, interaction: discord.Interaction, acao: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('❌ Disponível somente no servidor.', ephemeral=True)
        gid = interaction.guild.id
        async with self.lock(gid):
            estado = await self.obter(gid)
            if not estado or estado['message_id'] != interaction.message.id:
                return await interaction.response.send_message('⚠️ Este painel foi substituído. Use o painel mais recente.', ephemeral=True)
            passageiros = list(estado['passageiros'])
            uid = interaction.user.id
            if acao == 'passageiros':
                nomes = '\n'.join(f'{i}. <@{pid}>' for i, pid in enumerate(passageiros, 1)) or 'Ninguém embarcou ainda.'
                return await interaction.response.send_message(f'👥 **Passageiros ({len(passageiros)}/{MAX_PASSAGEIROS})**\n{nomes}', ephemeral=True)
            if estado['status'] != 'embarque':
                return await interaction.response.send_message('🚂 A viagem já começou. Aguarde a próxima estação.', ephemeral=True)
            if acao == 'embarcar':
                if uid in passageiros:
                    return await interaction.response.send_message('🎟️ Você já está a bordo.', ephemeral=True)
                if len(passageiros) >= MAX_PASSAGEIROS:
                    return await interaction.response.send_message('❌ O Expresso está lotado.', ephemeral=True)
                passageiros.append(uid)
                resposta = '🎟️ Passagem confirmada! Você embarcou no Expresso Fantasma.'
            elif acao == 'sair':
                if uid not in passageiros:
                    return await interaction.response.send_message('❌ Você não está a bordo.', ephemeral=True)
                passageiros.remove(uid)
                resposta = '🚪 Você desembarcou antes da partida.'
            elif acao == 'iniciar':
                if not eh_staff(interaction.user):
                    return await interaction.response.send_message('🔒 Somente a administração pode iniciar a viagem.', ephemeral=True)
                if len(passageiros) < MIN_PASSAGEIROS:
                    return await interaction.response.send_message(f'❌ São necessários pelo menos {MIN_PASSAGEIROS} passageiros.', ephemeral=True)
                estado['status'] = 'viagem'
                resposta = '🔥 O Expresso Fantasma partiu! A fase dos vagões será implementada em breve.'
            else:
                return await interaction.response.send_message('❌ Ação desconhecida.', ephemeral=True)
            await self.bot.pool.execute('''
                UPDATE expresso_viagens SET passageiros=$2::bigint[], status=$3, iniciado_por=$4,
                atualizado_em=NOW() WHERE guild_id=$1
            ''', gid, passageiros, estado['status'], uid if acao == 'iniciar' else estado.get('iniciado_por'))
            estado['passageiros'] = passageiros
            await interaction.response.send_message(resposta, ephemeral=True)
            await self.atualizar_painel(estado)


async def setup(bot: commands.Bot):
    await bot.add_cog(Expresso(bot))
