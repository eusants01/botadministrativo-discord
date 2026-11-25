"""Expresso Fantasma v2.0 — painel público único + salas privadas (discord.py 2.6+).

Instalação: substitua cogs/expresso.py. Reutiliza as tabelas/partidas anteriores.
Interfaces Components V2 não são enviadas junto com conteúdo textual comum:
os avisos são TextDisplay dentro de LayoutView.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import string
from typing import Any

import discord
from discord.ext import commands
from utils import cassino_db

LOG = logging.getLogger(__name__)
COR = 0x8B0000
MAX_VIDA = 700
MIN_JOGADORES = 2
MAX_JOGADORES = 10
PREMIO = 500
PAGINA = 20
BANNER = os.getenv('EXPRESSO_BANNER_URL', '').strip()

VAGOES = (
    {'nome': '🚉 Estação dos Mortos',
     'historia': 'O trem atravessa a neblina. Uma figura sem rosto exige sua passagem.',
     'opcoes': (('Mostrar passagem', '🎟️', (0, 12)), ('Esconder-se', '🌫️', (8, 22)), ('Enfrentar o vulto', '⚔️', (12, 30)))},
    {'nome': '👻 Vagão das Almas',
     'historia': 'Sussurros ecoam pelos bancos vazios. Uma alma oferece um pacto.',
     'opcoes': (('Recusar o pacto', '🛡️', (5, 18)), ('Aceitar o pacto', '📜', (0, 32)), ('Fugir do vagão', '🏃', (10, 25)))},
    {'nome': '⛓️ Vagão dos Condenados',
     'historia': 'Correntes bloqueiam a saída. O condutor exige uma decisão.',
     'opcoes': (('Quebrar correntes', '🔨', (10, 28)), ('Procurar uma chave', '🗝️', (2, 20)), ('Pedir clemência', '🙏', (8, 24)))},
    {'nome': '🚂 Locomotiva Fantasma',
     'historia': 'O maquinista espectral bloqueia a passagem e convoca seus servos.',
     'opcoes': (('Atacar o maquinista', '⚔️', (12, 28)), ('Proteger os passageiros', '🛡️', (5, 18)), ('Destruir a caldeira', '💥', (8, 24)))},
    {'nome': '😈 Estação do Diabo',
     'historia': 'O Diabo surge na plataforma final. Esta é a última decisão.',
     'opcoes': (('Enfrentar o Diabo', '⚔️', (15, 34)), ('Resistir à tentação', '🛡️', (8, 25)), ('Quebrar o contrato', '📜', (10, 29)))},
)

# Campos e chaves preservados para não perder salas que já existem no PostgreSQL.
SQL = """
CREATE TABLE IF NOT EXISTS expresso_salas (
  guild_id BIGINT NOT NULL, codigo VARCHAR(12) NOT NULL,
  host_id BIGINT NOT NULL, channel_id BIGINT NOT NULL, message_id BIGINT,
  status TEXT NOT NULL DEFAULT 'embarque', hp_max INTEGER NOT NULL,
  limite INTEGER NOT NULL, passageiros BIGINT[] NOT NULL DEFAULT '{}',
  vagao INTEGER NOT NULL DEFAULT 0,
  vidas JSONB NOT NULL DEFAULT '{}'::jsonb,
  escolhas JSONB NOT NULL DEFAULT '{}'::jsonb,
  relatos JSONB NOT NULL DEFAULT '[]'::jsonb,
  premio_entregue BOOLEAN NOT NULL DEFAULT FALSE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(guild_id, codigo)
);
ALTER TABLE expresso_salas ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE expresso_salas ADD COLUMN IF NOT EXISTS premio_entregue BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS expresso_lobby (
  guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL, PRIMARY KEY(guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS expresso_salas_premios (
  guild_id BIGINT NOT NULL, codigo VARCHAR(12) NOT NULL,
  user_id BIGINT NOT NULL, valor INTEGER NOT NULL,
  PRIMARY KEY(guild_id, codigo, user_id)
);
CREATE INDEX IF NOT EXISTS idx_expresso_ativas ON expresso_salas(guild_id, status, criado_em DESC);
"""


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return default
    if not isinstance(value, type(default)):
        return default
    return value


def normalizar(registro: Any) -> dict[str, Any] | None:
    if registro is None:
        return None
    sala = dict(registro)
    sala['passageiros'] = [int(v) for v in (sala.get('passageiros') or [])]
    sala['vidas'] = json_value(sala.get('vidas'), {})
    sala['escolhas'] = json_value(sala.get('escolhas'), {})
    sala['relatos'] = json_value(sala.get('relatos'), [])
    sala['vagao'] = max(0, int(sala.get('vagao', 0)))
    return sala


def vivos(sala: dict[str, Any]) -> list[int]:
    vidas = sala['vidas']
    return [uid for uid in sala['passageiros'] if int(vidas.get(str(uid), sala['hp_max'])) > 0]


def resumo_tripulacao(sala: dict[str, Any]) -> str:
    tripulacao = sala['passageiros']
    if not tripulacao:
        return '> Aguardando passageiros.'
    linhas = []
    for indice, uid in enumerate(tripulacao, 1):
        host = ' 👑' if uid == sala['host_id'] else ''
        if sala['status'] == 'embarque':
            hp = f'{sala["hp_max"]} HP previstos'
            icon = '🎟️'
        else:
            atual = max(0, int(sala['vidas'].get(str(uid), sala['hp_max'])))
            hp = f'{atual}/{sala["hp_max"]} HP'
            icon = '❤️' if atual > 0 else '💀'
        linhas.append(f'> `{indice:02}` {icon} <@{uid}>{host} — **{hp}**')
    return '\n'.join(linhas)


def resumo_sala(sala: dict[str, Any]) -> str:
    estado = {'embarque': '🎟️ Embarque', 'viagem': '🚂 Em viagem', 'encerrada': '🏁 Encerrada'}.get(sala['status'], 'Indefinido')
    linhas = [
        f'> `🔑` **Código:** `{sala["codigo"]}`',
        f'> `👑` **Anfitrião:** <@{sala["host_id"]}>',
        f'> `📍` **Situação:** {estado}',
        f'> `👥` **Passageiros:** {len(sala["passageiros"])}/{sala["limite"]}',
        f'> `❤️` **Vida inicial:** {sala["hp_max"]} HP',
    ]
    if sala['status'] == 'embarque':
        linhas.append(f'> `🚦` Início com {MIN_JOGADORES}+ passageiros, pelo anfitrião.')
    elif sala['status'] == 'viagem':
        etapa = VAGOES[min(sala['vagao'], len(VAGOES)-1)]
        ativos = vivos(sala)
        escolhidos = sum(str(uid) in sala['escolhas'] for uid in ativos)
        linhas += [
            '', f'### VAGÃO {min(sala["vagao"]+1, 5)}/5 — {etapa["nome"]}',
            f'> {etapa["historia"]}',
            f'> `🎯` **Decisões:** {escolhidos}/{len(ativos)} sobreviventes',
            *[f'> `{i+1}` {op[1]} {op[0]}' for i, op in enumerate(etapa['opcoes'])],
        ]
    elif sala['status'] == 'encerrada':
        linhas.append('> O expresso concluiu ou interrompeu sua viagem.')
    linhas += ['', '### 👥 TRIPULAÇÃO', resumo_tripulacao(sala)]
    if sala['relatos']:
        linhas += ['', '### 📜 ÚLTIMOS ACONTECIMENTOS']
        # no máximo 2 eventos para preservar limite de 4000 caracteres do TextDisplay
        linhas += [f'> {texto}' for texto in sala['relatos'][-2:]]
    return '\n'.join(linhas)[:3900]


def linha_botoes(*botoes: discord.ui.Item) -> discord.ui.ActionRow:
    linha = discord.ui.ActionRow()
    for botao in botoes:
        linha.add_item(botao)
    return linha


class Botao(discord.ui.Button):
    def __init__(self, cog: 'Expresso', acao: str, nome: str, estilo: discord.ButtonStyle,
                 emoji: str, codigo: str | None = None):
        # ID persistente somente para os botões públicos do Lobby.
        custom_id = f'sants:expresso:{acao}' if codigo is None else f'sants:expresso:{codigo}:{acao}'
        super().__init__(label=nome, emoji=emoji, style=estilo, custom_id=custom_id)
        self.cog, self.acao, self.codigo = cog, acao, codigo

    async def callback(self, interaction: discord.Interaction):
        try:
            if self.codigo is None:
                await self.cog.acao_central(interaction, self.acao)
            else:
                await self.cog.acao_sala(interaction, self.codigo, self.acao)
        except Exception:
            await self.cog.erro(interaction, f'botão {self.acao}', self.codigo)


class Central(discord.ui.LayoutView):
    def __init__(self, cog: 'Expresso'):
        super().__init__(timeout=None)
        conteudo: list = []
        if BANNER.startswith(('http://', 'https://')):
            conteudo.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=BANNER)))
        conteudo += [
            discord.ui.TextDisplay('# 🚂 EXPRESSO FANTASMA'),
            discord.ui.TextDisplay('> `👻` Uma viagem pelos cinco vagões amaldiçoados.\n'
                                   '> `🎟️` Crie ou participe de uma sala usando o código.\n'
                                   f'> `❤️` Configure de 1 a {MAX_VIDA} HP.\n'
                                   f'> `👥` Até {MAX_JOGADORES} passageiros.\n'
                                   f'> `🪙` Sobreviventes recebem {PREMIO} Sant\'s Coins.'),
            discord.ui.Separator(),
            linha_botoes(
                Botao(cog, 'criar', 'Criar sala', discord.ButtonStyle.success, '➕'),
                Botao(cog, 'salas', 'Ver salas', discord.ButtonStyle.primary, '🚂'),
                Botao(cog, 'entrar', 'Entrar com código', discord.ButtonStyle.secondary, '🎟️'),
                Botao(cog, 'minha', 'Minha sala', discord.ButtonStyle.secondary, '👥'),
            ),
        ]
        self.add_item(discord.ui.Container(*conteudo, accent_colour=discord.Colour(COR)))


class Sala(discord.ui.LayoutView):
    def __init__(self, cog: 'Expresso', sala: dict, aviso: str = ''):
        super().__init__(timeout=1800)
        conteudo: list = []
        if BANNER.startswith(('http://', 'https://')):
            conteudo.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=BANNER)))
        if aviso:
            conteudo.append(discord.ui.TextDisplay(f'**{aviso[:350]}**'))
            conteudo.append(discord.ui.Separator())
        conteudo += [
            discord.ui.TextDisplay(f'# 🚂 SALA {sala["codigo"]}'),
            discord.ui.TextDisplay(resumo_sala(sala)),
            discord.ui.Separator(),
        ]
        codigo = sala['codigo']
        if sala['status'] == 'embarque':
            conteudo.append(linha_botoes(
                Botao(cog, 'entrar', 'Embarcar', discord.ButtonStyle.success, '🎟️', codigo),
                Botao(cog, 'sair', 'Desembarcar', discord.ButtonStyle.secondary, '🚪', codigo),
                Botao(cog, 'iniciar', 'Iniciar', discord.ButtonStyle.danger, '🚂', codigo),
                Botao(cog, 'config', 'Configurar', discord.ButtonStyle.primary, '⚙️', codigo),
            ))
        elif sala['status'] == 'viagem':
            conteudo.append(linha_botoes(*[
                Botao(cog, f'escolha{i}', f'Escolha {i+1}', discord.ButtonStyle.primary, op[1], codigo)
                for i, op in enumerate(VAGOES[min(sala['vagao'], 4)]['opcoes'])
            ]))
            conteudo.append(linha_botoes(
                Botao(cog, 'avancar', 'Próximo vagão / Finalizar', discord.ButtonStyle.success, '🚂', codigo),
            ))
        if sala['status'] != 'encerrada':
            conteudo.append(linha_botoes(
                Botao(cog, 'encerrar', 'Encerrar sala', discord.ButtonStyle.secondary, '🔒', codigo),
                Botao(cog, 'atualizar', 'Atualizar painel', discord.ButtonStyle.secondary, '🔄', codigo),
                Botao(cog, 'salas', 'Outras salas', discord.ButtonStyle.secondary, '↩️', codigo),
            ))
        else:
            conteudo.append(linha_botoes(Botao(cog, 'salas', 'Ver outras salas', discord.ButtonStyle.secondary, '↩️', codigo)))
        self.add_item(discord.ui.Container(*conteudo, accent_colour=discord.Colour(COR)))


class EscolherSala(discord.ui.Select):
    def __init__(self, cog: 'Expresso', salas: list[dict]):
        self.cog = cog
        options = [discord.SelectOption(
            label=s['codigo'], value=s['codigo'], emoji='🚂',
            description=f'{"Embarque" if s["status"] == "embarque" else "Em viagem"} • {len(s["passageiros"])}/{s["limite"]} jogadores • {s["hp_max"]} HP',
        ) for s in salas]
        super().__init__(placeholder='Escolha a sala para abrir os controles', options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            sala = await self.cog.buscar(interaction.guild_id, self.values[0])
            if not sala or sala['status'] == 'encerrada':
                return await self.cog.listar(interaction, editar=True, aviso='⚠️ Sala indisponível. Lista atualizada.')
            await interaction.response.edit_message(view=Sala(self.cog, sala))
        except Exception:
            await self.cog.erro(interaction, 'abrir sala')


class Navegador(discord.ui.LayoutView):
    def __init__(self, cog: 'Expresso', salas: list[dict], pagina: int, aviso: str = ''):
        super().__init__(timeout=1800)
        self.cog, self.pagina = cog, pagina
        comeco = pagina * PAGINA
        parte = salas[comeco:comeco + PAGINA]
        texto = '\n'.join(
            f'> `🚂` **{s["codigo"]}** · {len(s["passageiros"])}/{s["limite"]} jogadores · '
            f'{"Embarque" if s["status"] == "embarque" else "Em viagem"}' for s in parte
        ) or '> Nenhuma sala ativa no momento.'
        campos = []
        if aviso:
            campos.append(discord.ui.TextDisplay(aviso[:350]))
        campos.extend([discord.ui.TextDisplay('# 🚂 SALAS DISPONÍVEIS'), discord.ui.TextDisplay(texto)])
        if parte:
            campos += [discord.ui.Separator(), linha_botoes(EscolherSala(cog, parte))]
        botoes = []
        if pagina > 0:
            botoes.append(BotaoNavegar(cog, pagina-1, '⬅️ Anterior'))
        if comeco + PAGINA < len(salas):
            botoes.append(BotaoNavegar(cog, pagina+1, 'Próxima ➡️'))
        botoes.append(BotaoNavegar(cog, pagina, '🔄 Atualizar'))
        campos.append(linha_botoes(*botoes))
        self.add_item(discord.ui.Container(*campos, accent_colour=discord.Colour(COR)))


class BotaoNavegar(discord.ui.Button):
    def __init__(self, cog: 'Expresso', pagina: int, nome: str):
        super().__init__(label=nome, style=discord.ButtonStyle.secondary)
        self.cog, self.pagina = cog, pagina

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.cog.listar(interaction, pagina=self.pagina, editar=True)
        except Exception:
            await self.cog.erro(interaction, 'navegação de salas')


class CriarModal(discord.ui.Modal, title='Criar sala — Expresso Fantasma'):
    vida = discord.ui.TextInput(label='Vida máxima: 1 a 700', default='300', max_length=3)
    limite = discord.ui.TextInput(label='Passageiros: 2 a 10', default='5', max_length=2)

    def __init__(self, cog: 'Expresso'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            vida, limite = int(self.vida.value), int(self.limite.value)
            await self.cog.criar(interaction, vida, limite)
        except ValueError:
            await interaction.response.send_message('❌ Preencha ambos os campos com números inteiros.', ephemeral=True)
        except Exception:
            await self.cog.erro(interaction, 'criação da sala')


class EntrarModal(discord.ui.Modal, title='Entrar com código'):
    codigo = discord.ui.TextInput(label='Código da sala', placeholder='EXP-A1B2C3', max_length=12)

    def __init__(self, cog: 'Expresso'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.cog.entrar_codigo(interaction, self.codigo.value.strip().upper())
        except Exception:
            await self.cog.erro(interaction, 'embarque por código')


class ConfigModal(discord.ui.Modal, title='Configurar a sala'):
    vida = discord.ui.TextInput(label='Vida máxima: 1 a 700', placeholder='Ex.: 300', max_length=3)
    limite = discord.ui.TextInput(label='Passageiros: 2 a 10', placeholder='Ex.: 5', max_length=2)

    def __init__(self, cog: 'Expresso', codigo: str, vida: int, limite: int):
        super().__init__()
        self.cog, self.codigo = cog, codigo
        self.vida.default = str(vida)
        self.limite.default = str(limite)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.cog.configurar(interaction, self.codigo, int(self.vida.value), int(self.limite.value))
        except ValueError:
            await interaction.response.send_message('❌ Use apenas números inteiros.', ephemeral=True)
        except Exception:
            await self.cog.erro(interaction, 'configuração da sala', self.codigo)


class Expresso(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        pool = getattr(self.bot, 'pool', None)
        if pool is None:
            raise RuntimeError('Expresso requer bot.pool (PostgreSQL conectado).')
        await pool.execute(SQL)
        await cassino_db.inicializar_tabelas(pool)
        self.bot.add_view(Central(self))
        # Limpa mensagens antigas de sala sem alterar progresso ou participantes.
        antigas = await pool.fetch('SELECT guild_id,codigo,channel_id,message_id FROM expresso_salas WHERE message_id IS NOT NULL')
        for r in antigas:
            try:
                canal = self.bot.get_channel(r['channel_id']) or await self.bot.fetch_channel(r['channel_id'])
                mensagem = await canal.fetch_message(r['message_id'])
                await mensagem.delete()
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException):
                LOG.warning('Não foi possível remover o antigo painel público da sala %s.', r['codigo'])
                continue
            except Exception:
                LOG.exception('Erro na limpeza do painel antigo da sala %s.', r['codigo'])
                continue
            await pool.execute('UPDATE expresso_salas SET message_id=NULL WHERE guild_id=$1 AND codigo=$2',r['guild_id'],r['codigo'])

    async def erro(self, interaction: discord.Interaction, onde: str, codigo: str | None = None):
        LOG.exception('Expresso | erro em %s | sala=%s | usuário=%s', onde, codigo, interaction.user.id)
        texto = '❌ Falha ao executar a ação. Confira os logs do Railway (Expresso) e reabra **Minha sala**.'
        try:
            if interaction.response.is_done():
                await interaction.followup.send(texto, ephemeral=True)
            else:
                await interaction.response.send_message(texto, ephemeral=True)
        except discord.HTTPException:
            LOG.exception('Falha ao apresentar aviso de erro do Expresso')

    async def buscar(self, gid: int, codigo: str) -> dict | None:
        row = await self.bot.pool.fetchrow('SELECT * FROM expresso_salas WHERE guild_id=$1 AND codigo=$2', gid, codigo)
        return normalizar(row)

    async def exibir(self, interaction: discord.Interaction, view: discord.ui.LayoutView,
                    *, editar: bool = False):
        """Nunca mistura texto normal com LayoutView (Components V2)."""
        if editar:
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message(view=view, ephemeral=True)

    async def listar(self, interaction: discord.Interaction, pagina: int = 0,
                     editar: bool = False, aviso: str = ''):
        rows = await self.bot.pool.fetch("""SELECT * FROM expresso_salas WHERE guild_id=$1
            AND status IN ('embarque','viagem') ORDER BY criado_em DESC LIMIT 500""", interaction.guild_id)
        salas = [normalizar(r) for r in rows]
        pagina = max(0, min(pagina, max(0, (len(salas)-1)//PAGINA)))
        await self.exibir(interaction, Navegador(self, salas, pagina, aviso), editar=editar)

    @commands.command(name='expresso', aliases=['painelexpresso'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def painel(self, ctx):
        antigo = await self.bot.pool.fetchval('SELECT message_id FROM expresso_lobby WHERE guild_id=$1 AND channel_id=$2', ctx.guild.id, ctx.channel.id)
        if antigo:
            try:
                msg = await ctx.channel.fetch_message(antigo)
                await msg.edit(view=Central(self))
                resposta = await ctx.reply('✅ Painel principal atualizado.', mention_author=False)
                try: await resposta.delete(delay=6)
                except discord.HTTPException: pass
                return
            except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                pass
        msg = await ctx.send(view=Central(self))
        await self.bot.pool.execute("""INSERT INTO expresso_lobby(guild_id,channel_id,message_id)
            VALUES($1,$2,$3) ON CONFLICT(guild_id,channel_id)
            DO UPDATE SET message_id=EXCLUDED.message_id""", ctx.guild.id, ctx.channel.id, msg.id)

    async def acao_central(self, interaction: discord.Interaction, acao: str):
        if acao == 'criar':
            return await interaction.response.send_modal(CriarModal(self))
        if acao == 'entrar':
            return await interaction.response.send_modal(EntrarModal(self))
        if acao == 'salas':
            return await self.listar(interaction)
        if acao == 'minha':
            row = await self.bot.pool.fetchrow("""SELECT * FROM expresso_salas WHERE guild_id=$1
                AND status IN ('embarque','viagem') AND $2=ANY(passageiros)
                ORDER BY criado_em DESC LIMIT 1""", interaction.guild_id, interaction.user.id)
            if not row:
                return await interaction.response.send_message('🎟️ Você não participa de uma sala ativa. Clique em **Ver salas** para embarcar.', ephemeral=True)
            return await self.exibir(interaction, Sala(self, normalizar(row)))
        await interaction.response.send_message('❌ Botão desconhecido.', ephemeral=True)

    @staticmethod
    def validar(vida: int, limite: int) -> str | None:
        if not (1 <= vida <= MAX_VIDA):
            return f'❌ A vida precisa estar entre 1 e {MAX_VIDA} HP.'
        if not (MIN_JOGADORES <= limite <= MAX_JOGADORES):
            return f'❌ O limite precisa estar entre {MIN_JOGADORES} e {MAX_JOGADORES} passageiros.'
        return None

    async def criar(self, interaction: discord.Interaction, vida: int, limite: int):
        erro = self.validar(vida, limite)
        if erro:
            return await interaction.response.send_message(erro, ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        gid, uid = interaction.guild_id, interaction.user.id
        # SELECT/INSERT protegidos por advisory lock por usuário (também entre instâncias do bot).
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('SELECT pg_advisory_xact_lock($1::bigint)', uid)
                antiga = await conn.fetchrow("""SELECT * FROM expresso_salas
                    WHERE guild_id=$1 AND host_id=$2 AND status IN ('embarque','viagem')
                    ORDER BY criado_em DESC LIMIT 1""", gid, uid)
                if antiga:
                    sala = normalizar(antiga)
                    aviso = '⚠️ Você já possui uma sala ativa.'
                else:
                    for _ in range(10):
                        codigo = 'EXP-' + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
                        codigo_usado = await conn.fetchval('SELECT 1 FROM expresso_salas WHERE guild_id=$1 AND codigo=$2',gid,codigo)
                        if not codigo_usado:
                            break
                    else:
                        raise RuntimeError('Não foi possível gerar um código de sala.')
                    await conn.execute("""INSERT INTO expresso_salas
                        (guild_id,codigo,host_id,channel_id,hp_max,limite,passageiros)
                        VALUES($1,$2,$3,$4,$5,$6,$7::bigint[])""",
                        gid, codigo, uid, interaction.channel_id, vida, limite, [uid])
                    sala = await self._buscar_conn(conn, gid, codigo)
                    aviso = '✅ Sala criada! Compartilhe o código e aguarde os passageiros.'
        await interaction.followup.send(view=Sala(self, sala, aviso), ephemeral=True)

    async def _buscar_conn(self, conn, gid: int, codigo: str, *, bloquear: bool = False):
        sql = 'SELECT * FROM expresso_salas WHERE guild_id=$1 AND codigo=$2'
        if bloquear:
            sql += ' FOR UPDATE'
        return normalizar(await conn.fetchrow(sql, gid, codigo))

    async def _salvar_conn(self, conn, sala: dict):
        await conn.execute("""UPDATE expresso_salas SET status=$3,passageiros=$4::bigint[],vagao=$5,
            vidas=$6::jsonb,escolhas=$7::jsonb,relatos=$8::jsonb,hp_max=$9,limite=$10,
            premio_entregue=$11,atualizado_em=NOW() WHERE guild_id=$1 AND codigo=$2""",
            sala['guild_id'], sala['codigo'], sala['status'], sala['passageiros'], sala['vagao'],
            json.dumps(sala['vidas']), json.dumps(sala['escolhas']), json.dumps(sala['relatos']),
            sala['hp_max'], sala['limite'], bool(sala.get('premio_entregue')))

    async def entrar_codigo(self, interaction: discord.Interaction, codigo: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        sala, aviso = await self._alterar(interaction.guild_id, codigo, interaction.user.id, 'entrar',
                                        admin=False)
        if not sala:
            return await interaction.followup.send(aviso, ephemeral=True)
        await interaction.followup.send(view=Sala(self, sala, aviso), ephemeral=True)

    async def configurar(self, interaction: discord.Interaction, codigo: str, vida: int, limite: int):
        erro = self.validar(vida, limite)
        if erro:
            return await interaction.response.send_message(erro, ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        sala, aviso = await self._alterar(interaction.guild_id, codigo, interaction.user.id, 'configurar',
                                        admin=False, vida=vida, limite=limite)
        if not sala:
            return await interaction.followup.send(aviso, ephemeral=True)
        await interaction.followup.send(view=Sala(self, sala, aviso), ephemeral=True)

    async def _premiar_conn(self, conn, sala: dict) -> int:
        """Recebimento atômico e idempotente na MESMA transação que encerra o jogo."""
        if sala['status'] != 'encerrada' or sala['vagao'] < len(VAGOES)-1 or sala.get('premio_entregue'):
            return 0
        total = 0
        for uid in vivos(sala):
            inserido = await conn.fetchval("""INSERT INTO expresso_salas_premios(guild_id,codigo,user_id,valor)
                VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING user_id""",
                sala['guild_id'], sala['codigo'], uid, PREMIO)
            if inserido is None:
                continue
            await cassino_db.garantir_carteira(uid, conn)
            await conn.execute('UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW() WHERE user_id=$1',uid,PREMIO)
            await conn.execute("""INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
                VALUES($1,'expresso',$2,$3)""", uid, PREMIO, f'Expresso Fantasma • sala {sala["codigo"]}')
            total += 1
        sala['premio_entregue'] = True
        return total

    async def _alterar(self, gid: int, codigo: str, uid: int, acao: str,
                      *, admin: bool = False, vida: int | None = None, limite: int | None = None):
        """Única máquina de estados, protegida por transação + SELECT FOR UPDATE."""
        if not codigo.startswith('EXP-') or len(codigo) != 10:
            return None, '❌ Código inválido. Exemplo: EXP-A1B2C3.'
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                sala = await self._buscar_conn(conn, gid, codigo, bloquear=True)
                if not sala:
                    return None, '❌ Sala não encontrada. Consulte **Ver salas**.'
                status = sala['status']
                aviso = ''
                alterou = False
                if acao == 'entrar':
                    if status != 'embarque':
                        aviso = '🚂 O embarque desta sala já foi encerrado.'
                    elif uid in sala['passageiros']:
                        aviso = '🎟️ Você já está a bordo.'
                    elif len(sala['passageiros']) >= sala['limite']:
                        aviso = '❌ A sala está lotada.'
                    else:
                        sala['passageiros'].append(uid)
                        alterou = True
                        aviso = '✅ Embarque confirmado!'
                elif acao == 'sair':
                    if status != 'embarque':
                        aviso = '🚂 Não é possível desembarcar depois da partida.'
                    elif uid == sala['host_id']:
                        aviso = '👑 O anfitrião deve encerrar a sala para sair.'
                    elif uid not in sala['passageiros']:
                        aviso = '⚠️ Você não faz parte desta tripulação.'
                    else:
                        sala['passageiros'].remove(uid)
                        alterou = True
                        aviso = '🚪 Desembarque realizado.'
                elif acao == 'configurar':
                    if status != 'embarque' or uid != sala['host_id']:
                        aviso = '🔒 Somente o anfitrião pode configurar antes da partida.'
                    elif limite < len(sala['passageiros']):
                        aviso = '❌ O limite não pode ser menor do que a tripulação atual.'
                    else:
                        sala['hp_max'], sala['limite'] = vida, limite
                        alterou = True
                        aviso = '⚙️ Configurações salvas.'
                elif acao == 'iniciar':
                    if status != 'embarque':
                        aviso = '🚂 Esta sala já foi iniciada ou encerrada.'
                    elif uid != sala['host_id']:
                        aviso = '🔒 Somente o anfitrião pode iniciar.'
                    elif len(sala['passageiros']) < MIN_JOGADORES:
                        aviso = f'⚠️ São necessários pelo menos {MIN_JOGADORES} passageiros.'
                    else:
                        sala.update(status='viagem', vagao=0, escolhas={}, relatos=['🚂 O Expresso Fantasma partiu!'],
                                    vidas={str(p): sala['hp_max'] for p in sala['passageiros']})
                        alterou = True
                        aviso = f'🚂 Viagem iniciada! **1/5 — {VAGOES[0]["nome"]}**'
                elif acao.startswith('escolha') and acao[-1:] in {'0', '1', '2'}:
                    if status != 'viagem':
                        aviso = '⚠️ Não há uma fase em andamento.'
                    elif uid not in sala['passageiros']:
                        aviso = '🔒 Você não pertence a esta tripulação.'
                    elif uid not in vivos(sala):
                        aviso = '💀 Você foi eliminado e não pode escolher.'
                    elif str(uid) in sala['escolhas']:
                        aviso = '⏳ Você já decidiu neste vagão.'
                    else:
                        indice = int(acao[-1])
                        opcao = VAGOES[min(sala['vagao'], 4)]['opcoes'][indice]
                        dano = secrets.randbelow(opcao[2][1]-opcao[2][0]+1) + opcao[2][0]
                        hp_atual = max(0, int(sala['vidas'].get(str(uid), sala['hp_max'])) - dano)
                        sala['vidas'][str(uid)] = hp_atual
                        sala['escolhas'][str(uid)] = indice
                        sala['relatos'] = (sala['relatos'] + [f'<@{uid}> escolheu {opcao[0]} (−{dano} HP).'])[-8:]
                        alterou = True
                        aviso = f'{opcao[1]} **{opcao[0]}**: −{dano} HP. Restam **{hp_atual} HP**.'
                elif acao == 'avancar':
                    if status != 'viagem':
                        aviso = '⚠️ A viagem não está em andamento.'
                    elif uid != sala['host_id']:
                        aviso = '🔒 Somente o anfitrião avança os vagões.'
                    elif any(str(p) not in sala['escolhas'] for p in vivos(sala)):
                        aviso = '⏳ Aguarde todas as decisões dos sobreviventes.'
                    elif not vivos(sala):
                        sala['status'] = 'encerrada'
                        sala['premio_entregue'] = True  # sem vencedores; bloqueia resgate indevido
                        sala['relatos'] = (sala['relatos'] + ['💀 A tripulação inteira foi eliminada.'])[-8:]
                        alterou = True
                        aviso = '💀 Todos foram eliminados. Viagem encerrada sem prêmio.'
                    elif sala['vagao'] >= len(VAGOES)-1:
                        sala['status'] = 'encerrada'
                        total = await self._premiar_conn(conn, sala)
                        sala['relatos'] = (sala['relatos'] + [f'🏆 Fim da viagem! {total} sobrevivente(s) premiado(s).'])[-8:]
                        alterou = True
                        aviso = f'🏆 Viagem concluída! **{total} sobrevivente(s)** receberam {PREMIO} Sant\'s Coins.'
                    else:
                        sala['vagao'] += 1
                        sala['escolhas'] = {}
                        sala['relatos'] = [f'🚂 Próxima parada: {VAGOES[sala["vagao"]]["nome"]}.']
                        alterou = True
                        aviso = f'🚂 **Vagão {sala["vagao"]+1}/5:** {VAGOES[sala["vagao"]]["nome"]}'
                elif acao == 'encerrar':
                    if status == 'encerrada':
                        aviso = '🏁 Esta sala já foi encerrada.'
                    elif uid != sala['host_id'] and not admin:
                        aviso = '🔒 Somente o anfitrião ou a administração pode encerrar.'
                    else:
                        sala['status'] = 'encerrada'
                        sala['premio_entregue'] = True  # cancelamento não paga prêmios
                        sala['relatos'] = (sala['relatos'] + ['🔒 Sala encerrada pelo responsável.'])[-8:]
                        alterou = True
                        aviso = '🔒 Sala encerrada. Nenhum prêmio foi atribuído por cancelamento.'
                else:
                    aviso = '🔄 Esse botão não corresponde ao estado atual. Painel atualizado.'
                if alterou:
                    await self._salvar_conn(conn, sala)
                return sala, aviso

    async def acao_sala(self, interaction: discord.Interaction, codigo: str, acao: str):
        if acao == 'salas':
            return await self.listar(interaction, editar=True)
        if acao == 'config':
            sala = await self.buscar(interaction.guild_id, codigo)
            if not sala or sala['status'] != 'embarque' or interaction.user.id != sala['host_id']:
                if sala:
                    return await self.exibir(interaction, Sala(self, sala, '🔒 Somente o anfitrião pode configurar antes da viagem.'), editar=True)
                return await interaction.response.send_message('❌ Sala não encontrada.', ephemeral=True)
            return await interaction.response.send_modal(ConfigModal(self, codigo, sala['hp_max'], sala['limite']))
        if acao == 'atualizar':
            sala = await self.buscar(interaction.guild_id, codigo)
            if not sala:
                return await interaction.response.send_message('❌ Sala não encontrada.', ephemeral=True)
            return await self.exibir(interaction, Sala(self, sala, '🔄 Sala sincronizada com o PostgreSQL.'), editar=True)
        admin = bool(getattr(getattr(interaction.user, 'guild_permissions', None), 'manage_guild', False))
        # Defer tipo UPDATE: atualiza a mesma mensagem efêmera (sem gerar mensagens repetidas).
        await interaction.response.defer()
        sala, aviso = await self._alterar(interaction.guild_id, codigo, interaction.user.id, acao, admin=admin)
        if sala is None:
            return await interaction.followup.send(aviso, ephemeral=True)
        # Usar edit_original_response após deferred_message_update, sem texto externo.
        await interaction.edit_original_response(view=Sala(self, sala, aviso))

    @commands.command(name='premioexpresso')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def recuperar_premio(self, ctx, codigo: str):
        codigo = codigo.upper()
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                sala = await self._buscar_conn(conn, ctx.guild.id, codigo, bloquear=True)
                if not sala or sala['status'] != 'encerrada':
                    return await ctx.reply('❌ Sala encerrada não encontrada.', mention_author=False)
                total = await self._premiar_conn(conn, sala)
                await self._salvar_conn(conn, sala)
        await ctx.reply(f'🪙 {total} recompensa(s) recuperada(s).', mention_author=False)

    @commands.command(name='configexpresso')
    @commands.guild_only()
    async def config_comando(self, ctx, codigo: str, vida: int, limite: int):
        erro = self.validar(vida, limite)
        if erro:
            return await ctx.reply(erro, mention_author=False)
        sala, aviso = await self._alterar(ctx.guild.id, codigo.upper(), ctx.author.id,
                                         'configurar', vida=vida, limite=limite)
        await ctx.reply(aviso, mention_author=False)


async def setup(bot):
    await bot.add_cog(Expresso(bot))
