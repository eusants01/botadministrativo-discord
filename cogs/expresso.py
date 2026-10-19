"""Expresso Fantasma — versão completa: cinco etapas, chefes e recompensas.

Discord.py 2.6+ / Components V2. Uma viagem ativa por servidor.
Recompensas de Sant's Coins com registro único por partida.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

import discord
from discord.ext import commands

LOG = logging.getLogger(__name__)
COR = 0x8B0000
MAX_PASSAGEIROS = 10
MIN_PASSAGEIROS = 2
VIDA_INICIAL = 100
PREMIO_VITORIA = 500
PREMIO_DERROTA = 0
BANNER = os.getenv('EXPRESSO_BANNER_URL', '').strip()

# Etapas da viagem, incluindo os dois confrontos finais.
VAGOES = (
    {
        'nome': '🚉 Estação dos Mortos',
        'historia': 'O trem atravessa a neblina. Uma figura sem rosto pede sua passagem.',
        'opcoes': (
            ('Mostrar passagem', '🎟️', (0, 12)),
            ('Esconder-se', '🌫️', (8, 22)),
            ('Enfrentar o vulto', '⚔️', (12, 30)),
        ),
    },
    {
        'nome': '👻 Vagão das Almas',
        'historia': 'Sussurros ecoam pelos bancos vazios. Uma alma oferece um pacto.',
        'opcoes': (
            ('Recusar o pacto', '🛡️', (5, 18)),
            ('Aceitar o pacto', '📜', (0, 32)),
            ('Fugir do vagão', '🏃', (10, 25)),
        ),
    },
    {
        'nome': '⛓️ Vagão dos Condenados',
        'historia': 'Correntes bloqueiam a saída. O condutor exige uma decisão.',
        'opcoes': (
            ('Quebrar correntes', '🔨', (10, 28)),
            ('Procurar uma chave', '🗝️', (2, 20)),
            ('Pedir clemência', '🙏', (8, 24)),
        ),
    },
    {
        'nome': '🚂 Locomotiva Fantasma',
        'historia': 'O maquinista espectral bloqueia a passagem e convoca seus servos.',
        'opcoes': (
            ('Atacar o maquinista', '⚔️', (12, 28)),
            ('Proteger os passageiros', '🛡️', (5, 18)),
            ('Destruir a caldeira', '💥', (8, 24)),
        ),
    },
    {
        'nome': '😈 Estação do Diabo',
        'historia': 'O Diabo aparece na plataforma final. Esta é a última decisão da viagem.',
        'opcoes': (
            ('Enfrentar o Diabo', '⚔️', (15, 34)),
            ('Resistir à tentação', '🛡️', (8, 25)),
            ('Quebrar o contrato', '📜', (10, 29)),
        ),
    },
)

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
ALTER TABLE expresso_viagens ADD COLUMN IF NOT EXISTS vagao INTEGER NOT NULL DEFAULT 0;
ALTER TABLE expresso_viagens ADD COLUMN IF NOT EXISTS vidas JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE expresso_viagens ADD COLUMN IF NOT EXISTS escolhas JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE expresso_viagens ADD COLUMN IF NOT EXISTS relatos JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE expresso_viagens ADD COLUMN IF NOT EXISTS partida INTEGER NOT NULL DEFAULT 1;
CREATE TABLE IF NOT EXISTS expresso_premios (
    guild_id BIGINT NOT NULL,
    partida INTEGER NOT NULL,
    user_id BIGINT NOT NULL,
    valor INTEGER NOT NULL,
    PRIMARY KEY (guild_id, partida, user_id)
);
"""


def eh_staff(membro: discord.Member) -> bool:
    return membro.guild_permissions.manage_guild or membro.guild_permissions.administrator


def hp_de(estado: dict, uid: int) -> int:
    return max(0, int((estado.get('vidas') or {}).get(str(uid), VIDA_INICIAL)))


def vivos(estado: dict) -> list[int]:
    return [uid for uid in estado.get('passageiros', []) if hp_de(estado, uid) > 0]


def texto_estado(estado: dict) -> str:
    status = estado.get('status', 'embarque')
    passageiros = list(estado.get('passageiros') or [])
    linhas = [
        '> `🚂` **Bem-vindo ao Expresso Fantasma.**',
        '> `🔍` Atravesse cinco etapas, enfrente o maquinista e sobreviva ao Diabo.',
        '> `🎟️` Embarque para participar; cada passageiro começa com **100 HP**.',
        '> `💀` Chegar a **0 HP** elimina o passageiro da viagem.',
        '> `🪙` Sobreviventes recebem **500 Sant\'s Coins** ao final.',
        '',
    ]
    if status == 'embarque':
        linhas += [
            '### 🚉 Plataforma de embarque',
            f'> `📍` **Situação:** aguardando partida',
            f'> `👥` **Passageiros:** {len(passageiros)}/{MAX_PASSAGEIROS} (mínimo {MIN_PASSAGEIROS})',
            '> `🔒` Somente a administração inicia a viagem.',
            '',
            '**Tripulação:** ' + (', '.join(f'<@{uid}>' for uid in passageiros) if passageiros else 'Nenhum passageiro ainda'),
        ]
    else:
        sobreviventes = vivos(estado)
        linhas += [
            f'### {"🏁 Fim da viagem" if status == "encerrada" else VAGOES[min(max(0, int(estado.get("vagao") or 0)), len(VAGOES)-1)]["nome"]}',
            f'> `📍` **Situação:** {"encerrada" if status == "encerrada" else "viagem em andamento"}',
            f'> `🚃` **Etapa:** {min(int(estado.get("vagao") or 0) + 1, len(VAGOES))}/{len(VAGOES)}',
            f'> `👥` **Sobreviventes:** {len(sobreviventes)}/{len(passageiros)}',
        ]
        if status == 'viagem':
            etapa = VAGOES[min(max(0, int(estado.get('vagao') or 0)), len(VAGOES)-1)]
            escolhas = estado.get('escolhas') or {}
            linhas += [
                '', f'> `📖` {etapa["historia"]}',
                f'> `🔍` **Decisões:** {sum(str(uid) in escolhas for uid in sobreviventes)}/{len(sobreviventes)}',
                '', '**Escolha seu destino:**',
                *[f'> `{i+1}️⃣` {nome}' for i, (nome, _, _) in enumerate(etapa['opcoes'])],
            ]
            if sobreviventes and all(str(uid) in escolhas for uid in sobreviventes):
                linhas.append('> `✅` Todos os sobreviventes decidiram; a administração pode avançar.')
        else:
            linhas += ['', '> `🏆` **Vitória!** Os sobreviventes chegaram à estação final.' if sobreviventes and int(estado.get('vagao') or 0) >= len(VAGOES)-1 else '> `💀` A viagem terminou sem alcançar a estação final.']
        linhas += ['', '**Estado dos passageiros**']
        for uid in passageiros:
            hp = hp_de(estado, uid)
            linhas.append(f'> `{"💀" if hp == 0 else "❤️"}` <@{uid}> — **{hp}/{VIDA_INICIAL} HP**')
    relatos = estado.get('relatos') or []
    if relatos:
        linhas += ['', '**Últimos acontecimentos**', *[f'> `📜` {r}' for r in relatos[-3:]]]
    return '\n'.join(linhas)[:3900]


class BotaoExpresso(discord.ui.Button):
    def __init__(self, cog: 'Expresso', acao: str, label: str, style: discord.ButtonStyle, emoji: str, disabled: bool = False):
        super().__init__(label=label, style=style, emoji=emoji, disabled=disabled, custom_id=f'sants:expresso:{acao}')
        self.cog = cog
        self.acao = acao

    async def callback(self, interaction: discord.Interaction):
        await self.cog.executar(interaction, self.acao)


class PainelExpresso(discord.ui.LayoutView):
    def __init__(self, cog: 'Expresso', estado: dict | None = None):
        super().__init__(timeout=None)
        estado = estado or {'status': 'embarque', 'passageiros': []}
        status = estado.get('status', 'embarque')
        blocos: list[Any] = []
        if BANNER.startswith(('https://', 'http://')):
            blocos.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=BANNER)))
        blocos += [discord.ui.TextDisplay('# 🚂 EXPRESSO FANTASMA'), discord.ui.TextDisplay('**FAMÍLIA SANT’S • UMA VIAGEM PELOS TRILHOS DO SUBMUNDO**'), discord.ui.Separator(), discord.ui.TextDisplay(texto_estado(estado)), discord.ui.Separator()]
        linha = discord.ui.ActionRow()
        if status == 'embarque':
            acoes = (
                ('embarcar', 'Embarcar', discord.ButtonStyle.success, '🎟️', False),
                ('sair', 'Desembarcar', discord.ButtonStyle.secondary, '🚪', False),
                ('passageiros', 'Passageiros', discord.ButtonStyle.primary, '👥', False),
                ('iniciar', 'Iniciar viagem', discord.ButtonStyle.danger, '🚂', False),
            )
        elif status == 'viagem':
            acoes = (
                ('escolha_0', 'Escolha 1', discord.ButtonStyle.primary, '🎟️', False),
                ('escolha_1', 'Escolha 2', discord.ButtonStyle.primary, '🛡️', False),
                ('escolha_2', 'Escolha 3', discord.ButtonStyle.primary, '⚔️', False),
                ('passageiros', 'Tripulação', discord.ButtonStyle.secondary, '👥', False),
                ('avancar', 'Próximo vagão', discord.ButtonStyle.danger, '🚂', False),
            )
            etapa = VAGOES[min(max(0, int(estado.get('vagao') or 0)), len(VAGOES) - 1)]
            # As opções já aparecem na descrição, com a formatação do painel.
        else:
            acoes = (('passageiros', 'Resultado', discord.ButtonStyle.secondary, '🏁', False),)
        for acao, nome, estilo, emoji, disabled in acoes:
            linha.add_item(BotaoExpresso(cog, acao, nome, estilo, emoji, disabled))
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
        self.bot.add_view(PainelExpresso(self))
        # Todos os custom_ids possíveis devem estar registrados após reiniciar.
        self.bot.add_view(PainelExpresso(self, {'status': 'viagem', 'passageiros': [], 'vagao': 0}))
        self.bot.add_view(PainelExpresso(self, {'status': 'encerrada', 'passageiros': []}))

    def lock(self, gid: int) -> asyncio.Lock:
        return self._locks.setdefault(gid, asyncio.Lock())

    async def obter(self, gid: int) -> dict | None:
        r = await self.bot.pool.fetchrow('SELECT * FROM expresso_viagens WHERE guild_id=$1', gid)
        return dict(r) if r else None

    async def salvar(self, gid: int, estado: dict):
        import json
        await self.bot.pool.execute('''
            UPDATE expresso_viagens SET status=$2, passageiros=$3::bigint[], iniciado_por=$4,
                vagao=$5, vidas=$6::jsonb, escolhas=$7::jsonb, relatos=$8::jsonb,
                atualizado_em=NOW() WHERE guild_id=$1
        ''', gid, estado['status'], estado['passageiros'], estado.get('iniciado_por'),
            int(estado.get('vagao') or 0), json.dumps(estado.get('vidas') or {}),
            json.dumps(estado.get('escolhas') or {}), json.dumps(estado.get('relatos') or []))

    async def atualizar_painel(self, estado: dict):
        canal = self.bot.get_channel(estado['channel_id'])
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(estado['channel_id'])
            except discord.HTTPException:
                LOG.exception('Canal do Expresso inacessível: %s', estado['channel_id'])
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
        gid = ctx.guild.id
        async with self.lock(gid):
            anterior = await self.obter(gid)
            if anterior and anterior['status'] == 'viagem':
                return await ctx.reply('🚂 Há uma viagem em andamento. Use `!resetarexpresso` somente se quiser cancelá-la.', mention_author=False)
            passageiros = list(anterior['passageiros']) if anterior and anterior['status'] == 'embarque' else []
            estado = {'status': 'embarque', 'passageiros': passageiros}
            msg = await ctx.send(view=PainelExpresso(self, estado), allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute('''
                INSERT INTO expresso_viagens (guild_id, channel_id, message_id, status, passageiros, iniciado_por, vagao, vidas, escolhas, relatos)
                VALUES ($1,$2,$3,'embarque',$4::bigint[],NULL,0,'{}'::jsonb,'{}'::jsonb,'[]'::jsonb)
                ON CONFLICT (guild_id) DO UPDATE SET channel_id=$2, message_id=$3,
                status='embarque', passageiros=$4::bigint[], iniciado_por=NULL, vagao=0,
                vidas='{}'::jsonb, escolhas='{}'::jsonb, relatos='[]'::jsonb, partida=expresso_viagens.partida+1, atualizado_em=NOW()
            ''', gid, ctx.channel.id, msg.id, passageiros)
            if anterior and anterior['message_id']:
                antigo_canal = self.bot.get_channel(anterior['channel_id'])
                if antigo_canal:
                    try:
                        antigo = await antigo_canal.fetch_message(anterior['message_id'])
                        await antigo.edit(view=PainelExpresso(self, {'status': 'encerrada', 'passageiros': passageiros}))
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
            estado.update(status='embarque', passageiros=[], iniciado_por=None, vagao=0, vidas={}, escolhas={}, relatos=[])
            await self.bot.pool.execute('UPDATE expresso_viagens SET partida=partida+1 WHERE guild_id=$1', gid)
            await self.salvar(gid, estado)
            await self.atualizar_painel(estado)
        await ctx.reply('🚉 Embarque reiniciado; vidas e decisões anteriores foram apagadas.', mention_author=False)

    async def premiar(self, gid: int, estado: dict) -> int:
        """Premia sobreviventes uma única vez por partida, em transação atômica."""
        if estado.get('status') != 'encerrada' or int(estado.get('vagao') or 0) < len(VAGOES)-1:
            return 0
        from utils import cassino_db
        # A tabela compartilhada da economia já é criada pelo cog de Economia.
        total = 0
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                for uid in vivos(estado):
                    inserted = await conn.fetchval("""
                        INSERT INTO expresso_premios(guild_id,partida,user_id,valor)
                        VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING user_id
                    """, gid, int(estado.get('partida') or 1), uid, PREMIO_VITORIA)
                    if inserted is None:
                        continue
                    await cassino_db.garantir_carteira(uid, conn)
                    await conn.execute("""
                        UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW()
                        WHERE user_id=$1
                    """, uid, PREMIO_VITORIA)
                    await conn.execute("""
                        INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
                        VALUES($1,'expresso',$2,$3)
                    """, uid, PREMIO_VITORIA, f'Expresso Fantasma • servidor {gid} • partida {estado.get("partida", 1)}')
                    total += 1
        return total

    @commands.command(name='premioexpresso')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def recuperar_premio(self, ctx: commands.Context):
        estado = await self.obter(ctx.guild.id)
        if not estado or estado['status'] != 'encerrada':
            return await ctx.reply('❌ Nenhuma viagem encerrada para conferir.', mention_author=False)
        total = await self.premiar(ctx.guild.id, estado)
        await ctx.reply(f'🪙 Conferência concluída. {total} recompensa(s) pendente(s) creditada(s).', mention_author=False)

    async def executar(self, interaction: discord.Interaction, acao: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('❌ Disponível somente no servidor.', ephemeral=True)
        gid = interaction.guild.id
        async with self.lock(gid):
            estado = await self.obter(gid)
            if not estado or estado['message_id'] != interaction.message.id:
                return await interaction.response.send_message('⚠️ Painel antigo. Utilize o painel mais recente.', ephemeral=True)
            passageiros = list(estado['passageiros'])
            uid = interaction.user.id
            if acao == 'passageiros':
                nomes = '\n'.join(f'{i}. <@{pid}> — {hp_de(estado, pid)} HP' for i, pid in enumerate(passageiros, 1)) or 'Ninguém embarcou.'
                return await interaction.response.send_message(f'👥 **Tripulação ({len(passageiros)}/{MAX_PASSAGEIROS})**\n{nomes}', ephemeral=True)
            if estado['status'] == 'embarque':
                if acao == 'embarcar':
                    if uid in passageiros:
                        return await interaction.response.send_message('🎟️ Você já está a bordo.', ephemeral=True)
                    if len(passageiros) >= MAX_PASSAGEIROS:
                        return await interaction.response.send_message('❌ O Expresso está lotado.', ephemeral=True)
                    passageiros.append(uid)
                    resposta = '🎟️ Passagem confirmada! Você embarcou.'
                elif acao == 'sair':
                    if uid not in passageiros:
                        return await interaction.response.send_message('❌ Você não está a bordo.', ephemeral=True)
                    passageiros.remove(uid)
                    resposta = '🚪 Você desembarcou.'
                elif acao == 'iniciar':
                    if not eh_staff(interaction.user):
                        return await interaction.response.send_message('🔒 Apenas a administração pode iniciar.', ephemeral=True)
                    if len(passageiros) < MIN_PASSAGEIROS:
                        return await interaction.response.send_message(f'❌ São necessários {MIN_PASSAGEIROS} passageiros.', ephemeral=True)
                    estado.update(status='viagem', vagao=0, vidas={str(pid): VIDA_INICIAL for pid in passageiros}, escolhas={}, relatos=[], iniciado_por=uid)
                    resposta = '🔥 A locomotiva partiu! O primeiro vagão está aberto para decisões.'
                else:
                    return await interaction.response.send_message('❌ Ação indisponível durante o embarque.', ephemeral=True)
                estado['passageiros'] = passageiros
            elif estado['status'] == 'viagem':
                if acao.startswith('escolha_'):
                    if uid not in passageiros or hp_de(estado, uid) == 0:
                        return await interaction.response.send_message('💀 Apenas passageiros vivos podem decidir.', ephemeral=True)
                    escolhas = dict(estado.get('escolhas') or {})
                    if str(uid) in escolhas:
                        return await interaction.response.send_message('⏳ Você já decidiu neste vagão.', ephemeral=True)
                    try:
                        indice = int(acao.split('_', 1)[1])
                        opcao = VAGOES[int(estado['vagao'])]['opcoes'][indice]
                    except (ValueError, IndexError, KeyError):
                        return await interaction.response.send_message('❌ Escolha inválida.', ephemeral=True)
                    dano = random.SystemRandom().randint(*opcao[2])
                    vidas = dict(estado.get('vidas') or {})
                    vidas[str(uid)] = max(0, hp_de(estado, uid) - dano)
                    escolhas[str(uid)] = indice
                    estado['vidas'] = vidas
                    estado['escolhas'] = escolhas
                    estado['relatos'] = (list(estado.get('relatos') or []) + [f'<@{uid}> escolheu {opcao[0]} e perdeu {dano} HP.'])[-8:]
                    resposta = f'{opcao[1]} **{opcao[0]}** — você perdeu **{dano} HP**. Restam **{vidas[str(uid)]} HP**.'
                elif acao == 'avancar':
                    if not eh_staff(interaction.user):
                        return await interaction.response.send_message('🔒 Apenas a administração pode avançar.', ephemeral=True)
                    ativos = vivos(estado)
                    escolhas = estado.get('escolhas') or {}
                    if ativos and any(str(pid) not in escolhas for pid in ativos):
                        return await interaction.response.send_message('⏳ Aguarde todos os passageiros vivos escolherem.', ephemeral=True)
                    if not ativos or int(estado['vagao']) >= len(VAGOES) - 1:
                        estado['status'] = 'encerrada'
                        resposta = '🏁 A viagem terminou! Veja os sobreviventes no painel.'
                    else:
                        estado['vagao'] = int(estado['vagao']) + 1
                        estado['escolhas'] = {}
                        estado['relatos'] = []
                        resposta = f'🚂 Próxima parada: **{VAGOES[estado["vagao"]]["nome"]}**.'
                else:
                    return await interaction.response.send_message('❌ Ação indisponível durante a viagem.', ephemeral=True)
            else:
                return await interaction.response.send_message('🏁 Esta viagem terminou. Aguarde a próxima.', ephemeral=True)
            await self.salvar(gid, estado)
            await interaction.response.send_message(resposta, ephemeral=True)
            if estado['status'] == 'encerrada':
                try:
                    premiados = await self.premiar(gid, estado)
                    if premiados:
                        LOG.info('Expresso %s: %s sobreviventes premiados', gid, premiados)
                except Exception:
                    LOG.exception('Falha ao premiar Expresso %s; use !premioexpresso para tentar novamente', gid)
            await self.atualizar_painel(estado)


async def setup(bot: commands.Bot):
    await bot.add_cog(Expresso(bot))
