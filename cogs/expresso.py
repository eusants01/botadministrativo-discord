"""Expresso Fantasma: salas independentes, decisões V2 e PostgreSQL.
Substitui somente cogs/expresso.py; requer discord.py 2.6+.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import random
import secrets
import string
import discord
from discord.ext import commands
from utils import cassino_db

LOG = logging.getLogger(__name__)
COR = 0x8B0000
MIN_JOGADORES = 2
MAX_JOGADORES = 10
MAX_VIDA = 700
PREMIO = 500
BANNER = os.getenv('EXPRESSO_BANNER_URL', '').strip()

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
CREATE TABLE IF NOT EXISTS expresso_salas (
  guild_id BIGINT NOT NULL,
  codigo VARCHAR(12) NOT NULL,
  host_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  message_id BIGINT,
  status TEXT NOT NULL DEFAULT 'embarque',
  hp_max INTEGER NOT NULL,
  limite INTEGER NOT NULL,
  passageiros BIGINT[] NOT NULL DEFAULT '{}',
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
CREATE TABLE IF NOT EXISTS expresso_lobby (
  guild_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL,
  PRIMARY KEY(guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS expresso_salas_premios (
  guild_id BIGINT NOT NULL,
  codigo VARCHAR(12) NOT NULL,
  user_id BIGINT NOT NULL,
  valor INTEGER NOT NULL,
  PRIMARY KEY(guild_id, codigo, user_id)
);
"""

def as_json(value, default):
    if value is None: return default
    if isinstance(value, str):
        try: return json.loads(value)
        except (ValueError, TypeError): return default
    return value

def vivos(sala):
    vidas = as_json(sala.get('vidas'), {})
    return [uid for uid in sala['passageiros'] if int(vidas.get(str(uid), sala['hp_max'])) > 0]

def descricao(sala):
    jogadores = sala['passageiros']
    status = sala['status']
    linhas = [
      '> `🔍` Sobreviva aos cinco vagões do Expresso Fantasma.',
      '> `🎟️` Crie uma sala e compartilhe seu código com outros passageiros.',
      f'> `❤️` Vida configurável de **1 a {MAX_VIDA} HP**.',
      f'> `🪙` Sobreviventes recebem **{PREMIO} Sant\'s Coins**.',
      '', f'> `🔑` **Código:** `{sala["codigo"]}`',
      f'> `👑` **Anfitrião:** <@{sala["host_id"]}>',
      f'> `📍` **Situação:** {"Embarque" if status == "embarque" else "Em viagem" if status == "viagem" else "Encerrada"}',
      f'> `👥` **Passageiros:** {len(jogadores)}/{sala["limite"]}',
      f'> `❤️` **Vida máxima:** {sala["hp_max"]} HP',
    ]
    if status == 'viagem':
        etapa = VAGOES[min(sala['vagao'], len(VAGOES)-1)]
        escolhas = as_json(sala['escolhas'], {})
        ativos = vivos(sala)
        linhas += ['', f'### {etapa["nome"]}', f'> `📖` {etapa["historia"]}',
                  f'> `🔍` **Decisões:** {sum(str(u) in escolhas for u in ativos)}/{len(ativos)}',
                  '**Escolha seu destino:**']
        linhas += [f'> `{i+1}` {op[0]}' for i,op in enumerate(etapa['opcoes'])]
    if status != 'embarque':
        vidas = as_json(sala['vidas'], {})
        linhas += ['', '**Estado dos passageiros:**']
        linhas += [f'> `{"💀" if int(vidas.get(str(u), 0)) <= 0 else "❤️"}` <@{u}> — **{vidas.get(str(u), 0)}/{sala["hp_max"]} HP**' for u in jogadores]
    else:
        linhas += ['', '**Tripulação:** ' + (', '.join(f'<@{u}>' for u in jogadores) or 'Aguardando passageiros')]
    if status == 'encerrada':
        linhas += ['', '> `🏁` Viagem encerrada. O anfitrião pode criar uma nova sala.']
    relatos = as_json(sala['relatos'], [])
    if relatos: linhas += ['', '**Últimos acontecimentos:**', *[f'> `📜` {r}' for r in relatos[-3:]]]
    return '\n'.join(linhas)[:3900]

class Acao(discord.ui.Button):
    def __init__(self, cog, acao, nome, estilo, emoji, codigo=None):
        # IDs fixos no lobby; IDs por sala para evitar colisão entre painéis
        custom = f'sants:expresso:{acao}' if codigo is None else f'sants:expresso:{codigo}:{acao}'
        super().__init__(label=nome, emoji=emoji, style=estilo, custom_id=custom)
        self.cog, self.acao, self.codigo = cog, acao, codigo

    async def callback(self, interaction):
        if self.codigo is None:
            await self.cog.lobby_acao(interaction, self.acao)
        else:
            await self.cog.sala_acao(interaction, self.codigo, self.acao)

class Lobby(discord.ui.LayoutView):
    def __init__(self, cog):
        super().__init__(timeout=None)
        blocos = []
        if BANNER.startswith(('http://','https://')):
            blocos.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=BANNER)))
        blocos.extend([discord.ui.TextDisplay('# 🚂 EXPRESSO FANTASMA'),
          discord.ui.TextDisplay('> `🔍` **Uma viagem pelos trilhos amaldiçoados.**\n> `🎟️` Crie sua sala ou entre usando um código.\n> `❤️` Configure de 1 a 700 HP por passageiro.\n> `👥` Até 10 jogadores por sala.\n> `🏆` Sobreviva aos cinco vagões para ganhar Sant\'s Coins.'), discord.ui.Separator()])
        linha = discord.ui.ActionRow()
        for a,n,e,emoji in [('criar','Criar sala',discord.ButtonStyle.success,'➕'),('entrar','Entrar com código',discord.ButtonStyle.primary,'🎟️'),('salas','Ver salas',discord.ButtonStyle.secondary,'🚂'),('minha','Minha sala',discord.ButtonStyle.secondary,'👥')]:
            linha.add_item(Acao(cog,a,n,e,emoji))
        blocos.append(linha)
        self.add_item(discord.ui.Container(*blocos,accent_colour=discord.Colour(COR)))

class SalaView(discord.ui.LayoutView):
    def __init__(self, cog, sala):
        super().__init__(timeout=900)
        blocos = []
        if BANNER.startswith(('http://','https://')):
            blocos.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=BANNER)))
        blocos += [discord.ui.TextDisplay(f'# 🚂 SALA {sala["codigo"]}'),discord.ui.TextDisplay(descricao(sala)),discord.ui.Separator()]
        linha = discord.ui.ActionRow()
        if sala['status'] == 'embarque':
            itens = [('entrar','Embarcar',discord.ButtonStyle.success,'🎟️'),('sair','Desembarcar',discord.ButtonStyle.secondary,'🚪'),('iniciar','Iniciar',discord.ButtonStyle.danger,'🚂'),('config','Configurar',discord.ButtonStyle.primary,'⚙️')]
        elif sala['status'] == 'viagem':
            itens = [('escolha0','Escolha 1',discord.ButtonStyle.primary,'🎟️'),('escolha1','Escolha 2',discord.ButtonStyle.primary,'🛡️'),('escolha2','Escolha 3',discord.ButtonStyle.primary,'⚔️'),('avancar','Próximo vagão',discord.ButtonStyle.danger,'🚂')]
        else: itens=[]
        for a,n,e,emoji in itens:
            linha.add_item(Acao(cog,a,n,e,emoji,sala['codigo']))
        if itens: blocos.append(linha)
        if sala['status'] != 'encerrada':
            linha2=discord.ui.ActionRow()
            linha2.add_item(Acao(cog,'tripulacao','Tripulação',discord.ButtonStyle.secondary,'👥',sala['codigo']))
            linha2.add_item(Acao(cog,'encerrar','Encerrar sala',discord.ButtonStyle.secondary,'🔒',sala['codigo']))
            blocos.append(linha2)
        voltar = discord.ui.ActionRow()
        voltar.add_item(VoltarSalas(cog))
        blocos.append(voltar)
        self.add_item(discord.ui.Container(*blocos,accent_colour=discord.Colour(COR)))


class VoltarSalas(discord.ui.Button):
    def __init__(self,cog):
        super().__init__(label='Ver outras salas',emoji='↩️',style=discord.ButtonStyle.secondary)
        self.cog=cog
    async def callback(self,interaction):
        await self.cog.mostrar_salas(interaction,editar=True)

class SeletorSalas(discord.ui.Select):
    def __init__(self,cog,rows):
        self.cog=cog
        options=[]
        for sala in rows:
            titulo='Embarque' if sala['status']=='embarque' else 'Em viagem'
            options.append(discord.SelectOption(label=sala['codigo'],value=sala['codigo'],
                description=f"{titulo} • {len(sala['passageiros'])}/{sala['limite']} passageiros • {sala['hp_max']} HP",emoji='🚂'))
        super().__init__(placeholder='Escolha uma sala para visualizar',options=options)
    async def callback(self,interaction):
        sala=await self.cog.obter(interaction.guild_id,self.values[0])
        if not sala or sala['status']=='encerrada':
            return await self.cog.mostrar_salas(interaction,editar=True)
        await interaction.response.edit_message(view=SalaView(self.cog,sala),allowed_mentions=discord.AllowedMentions.none())

class NavegadorSalas(discord.ui.LayoutView):
    def __init__(self,cog,rows,page=0):
        super().__init__(timeout=900)
        self.cog,self.page=cog,page
        n=len(rows)
        inicio=page*20
        selecao=rows[inicio:inicio+20]
        linhas=[f'> `🚂` **{r["codigo"]}** • {len(r["passageiros"])}/{r["limite"]} • {"Embarque" if r["status"]=="embarque" else "Em viagem"}' for r in selecao]
        corpo='\n'.join(linhas) or 'Nenhuma sala ativa no momento.'
        self.add_item(discord.ui.Container(discord.ui.TextDisplay('# 🚂 SALAS DO EXPRESSO'),
            discord.ui.TextDisplay(corpo),accent_colour=discord.Colour(COR)))
        if selecao:
            self.add_item(discord.ui.ActionRow(SeletorSalas(cog,selecao)))
        linha=discord.ui.ActionRow()
        if page>0:
            anterior=discord.ui.Button(label='Anterior',style=discord.ButtonStyle.secondary,emoji='⬅️')
            anterior.callback=self.anterior
            linha.add_item(anterior)
        if inicio+20<n:
            proximo=discord.ui.Button(label='Próxima',style=discord.ButtonStyle.secondary,emoji='➡️')
            proximo.callback=self.proximo
            linha.add_item(proximo)
        atualizar=discord.ui.Button(label='Atualizar',style=discord.ButtonStyle.primary,emoji='🔄')
        atualizar.callback=self.atualizar
        linha.add_item(atualizar)
        self.add_item(linha)
    async def anterior(self,interaction):
        await self.cog.mostrar_salas(interaction,page=self.page-1,editar=True)
    async def proximo(self,interaction):
        await self.cog.mostrar_salas(interaction,page=self.page+1,editar=True)
    async def atualizar(self,interaction):
        await self.cog.mostrar_salas(interaction,page=self.page,editar=True)

class CriarModal(discord.ui.Modal, title='Criar sala — Expresso Fantasma'):
    vida=discord.ui.TextInput(label='Vida máxima (1 a 700)',placeholder='Ex.: 300',default='300',max_length=3)
    limite=discord.ui.TextInput(label='Limite de passageiros (2 a 10)',placeholder='Ex.: 5',default='5',max_length=2)
    def __init__(self,cog): super().__init__(); self.cog=cog
    async def on_submit(self,interaction):
        try:
            vida, limite = int(self.vida.value),int(self.limite.value)
        except ValueError:
            return await interaction.response.send_message('❌ Informe números inteiros.',ephemeral=True)
        if not 1 <= vida <= MAX_VIDA or not MIN_JOGADORES <= limite <= MAX_JOGADORES:
            return await interaction.response.send_message('❌ Vida de 1 a 700; passageiros de 2 a 10. Zero HP eliminaria todos antes de jogar.',ephemeral=True)
        await self.cog.criar(interaction,vida,limite)

class EntrarModal(discord.ui.Modal,title='Entrar em uma sala'):
    codigo=discord.ui.TextInput(label='Código da sala',placeholder='Ex.: EXP-A1B2C3',max_length=12)
    def __init__(self,cog): super().__init__(); self.cog=cog
    async def on_submit(self,interaction):
        await self.cog.entrar_codigo(interaction,str(self.codigo.value).strip().upper())

class ConfigModal(discord.ui.Modal,title='Configurar sua sala'):
    vida=discord.ui.TextInput(label='Vida máxima (1 a 700)',placeholder='Ex.: 500',max_length=3)
    limite=discord.ui.TextInput(label='Limite de passageiros (2 a 10)',placeholder='Ex.: 8',max_length=2)
    def __init__(self,cog,codigo): super().__init__(); self.cog,self.codigo=cog,codigo
    async def on_submit(self,interaction):
        try: vida,limite=int(self.vida.value),int(self.limite.value)
        except ValueError: return await interaction.response.send_message('❌ Use apenas números.',ephemeral=True)
        await self.cog.configurar(interaction,self.codigo,vida,limite)

class Expresso(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.locks={}

    def lock(self,gid,codigo):
        return self.locks.setdefault((gid,codigo),asyncio.Lock())

    async def cog_load(self):
        if getattr(self.bot,'pool',None) is None: raise RuntimeError('Expresso requer PostgreSQL (bot.pool).')
        await self.bot.pool.execute(SQL)
        self.bot.add_view(Lobby(self))
        # Despublica os antigos painéis por sala. As salas e seu progresso permanecem no banco.
        rows=await self.bot.pool.fetch("SELECT guild_id,codigo,channel_id,message_id FROM expresso_salas WHERE message_id IS NOT NULL")
        for row in rows:
            try:
                canal=self.bot.get_channel(row['channel_id']) or await self.bot.fetch_channel(row['channel_id'])
                await (await canal.fetch_message(row['message_id'])).delete()
            except discord.NotFound:
                pass
            except (discord.Forbidden,discord.HTTPException):
                LOG.warning('Não foi possível apagar o antigo painel público %s',row['codigo'])
            await self.bot.pool.execute('UPDATE expresso_salas SET message_id=NULL WHERE guild_id=$1 AND codigo=$2',row['guild_id'],row['codigo'])

    async def obter(self,gid,codigo):
        row=await self.bot.pool.fetchrow('SELECT * FROM expresso_salas WHERE guild_id=$1 AND codigo=$2',gid,codigo)
        return dict(row) if row else None

    async def salvar(self,sala):
        await self.bot.pool.execute("""UPDATE expresso_salas SET status=$3, passageiros=$4::bigint[], vagao=$5,
          vidas=$6::jsonb, escolhas=$7::jsonb, relatos=$8::jsonb, hp_max=$9, limite=$10,
          atualizado_em=NOW() WHERE guild_id=$1 AND codigo=$2""",
          sala['guild_id'],sala['codigo'],sala['status'],sala['passageiros'],sala['vagao'],
          json.dumps(as_json(sala['vidas'],{})),json.dumps(as_json(sala['escolhas'],{})),
          json.dumps(as_json(sala['relatos'],[])),sala['hp_max'],sala['limite'])

    async def atualizar(self,sala):
        # O estado vive no PostgreSQL; as interfaces privadas são reconstruídas a cada clique.
        return

    async def mostrar_salas(self,interaction,page=0,editar=False):
        rows=[dict(r) for r in await self.bot.pool.fetch("""SELECT * FROM expresso_salas
            WHERE guild_id=$1 AND status IN ('embarque','viagem') ORDER BY criado_em DESC LIMIT 200""",interaction.guild_id)]
        page=max(0,min(page,max(0,(len(rows)-1)//20)))
        view=NavegadorSalas(self,rows,page)
        if editar:
            await interaction.response.edit_message(view=view,allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message(view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='expresso',aliases=['painelexpresso'])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def painel(self,ctx):
        # Reutiliza o painel existente no canal, em vez de postar duplicatas.
        antigo=await self.bot.pool.fetchval('SELECT message_id FROM expresso_lobby WHERE guild_id=$1 AND channel_id=$2',ctx.guild.id,ctx.channel.id)
        if antigo:
            try:
                msg=await ctx.channel.fetch_message(antigo)
                await msg.edit(view=Lobby(self),allowed_mentions=discord.AllowedMentions.none())
                return await ctx.reply('✅ Painel principal atualizado.',delete_after=8,mention_author=False)
            except (discord.NotFound,discord.Forbidden,discord.HTTPException):
                pass
        msg=await ctx.send(view=Lobby(self),allowed_mentions=discord.AllowedMentions.none())
        await self.bot.pool.execute("""INSERT INTO expresso_lobby(guild_id,channel_id,message_id)
            VALUES($1,$2,$3) ON CONFLICT(guild_id,channel_id) DO UPDATE SET message_id=EXCLUDED.message_id""",ctx.guild.id,ctx.channel.id,msg.id)

    async def lobby_acao(self,interaction,acao):
        if acao=='criar': return await interaction.response.send_modal(CriarModal(self))
        if acao=='entrar': return await interaction.response.send_modal(EntrarModal(self))
        if acao=='salas': return await self.mostrar_salas(interaction)
        if acao=='minha':
            sala=await self.bot.pool.fetchrow("""SELECT * FROM expresso_salas WHERE guild_id=$1
              AND status IN ('embarque','viagem') AND $2=ANY(passageiros) ORDER BY criado_em DESC LIMIT 1""",
              interaction.guild_id,interaction.user.id)
            if not sala:
                return await interaction.response.send_message('🎟️ Você não está em uma sala ativa. Use **Ver salas** para embarcar.',ephemeral=True)
            return await interaction.response.send_message(view=SalaView(self,dict(sala)),ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none())
        await interaction.response.send_message('❌ Ação desconhecida.',ephemeral=True)

    async def criar(self,interaction,vida,limite):
        await interaction.response.defer(ephemeral=True,thinking=True)
        gid,uid=interaction.guild_id,interaction.user.id
        existente=await self.bot.pool.fetchval("SELECT codigo FROM expresso_salas WHERE guild_id=$1 AND host_id=$2 AND status IN ('embarque','viagem') ORDER BY criado_em DESC LIMIT 1",gid,uid)
        if existente:
            sala=await self.obter(gid,existente)
            return await interaction.followup.send('⚠️ Você já possui uma sala ativa.',view=SalaView(self,sala),ephemeral=True)
        for _ in range(8):
            codigo='EXP-'+''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(6))
            exists=await self.obter(gid,codigo)
            if not exists: break
        else: return await interaction.followup.send('❌ Não foi possível gerar um código.',ephemeral=True)
        sala={'guild_id':gid,'codigo':codigo,'host_id':uid,'channel_id':interaction.channel_id,'message_id':None,
          'status':'embarque','hp_max':vida,'limite':limite,'passageiros':[uid],'vagao':0,'vidas':{},'escolhas':{},'relatos':[]}
        await self.bot.pool.execute("""INSERT INTO expresso_salas(guild_id,codigo,host_id,channel_id,hp_max,limite,passageiros)
            VALUES($1,$2,$3,$4,$5,$6,$7::bigint[])""",gid,codigo,uid,interaction.channel_id,vida,limite,[uid])
        await interaction.followup.send(view=SalaView(self,sala),ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none())

    async def entrar_codigo(self,interaction,codigo):
        await interaction.response.defer(ephemeral=True,thinking=True)
        async with self.lock(interaction.guild_id,codigo):
            sala=await self.obter(interaction.guild_id,codigo)
            if not sala or sala['status']!='embarque': return await interaction.followup.send('❌ Sala não encontrada ou embarque encerrado.',ephemeral=True)
            if interaction.user.id in sala['passageiros']: return await interaction.followup.send('🎟️ Você já está nessa sala.',view=SalaView(self,sala),ephemeral=True)
            if len(sala['passageiros'])>=sala['limite']: return await interaction.followup.send('❌ Sala lotada.',ephemeral=True)
            sala['passageiros'].append(interaction.user.id)
            await self.salvar(sala)
            await self.atualizar(sala)
        await interaction.followup.send(f'🎟️ Embarque confirmado na sala **`{codigo}`**!',view=SalaView(self,sala),ephemeral=True)

    async def configurar(self,interaction,codigo,vida,limite):
        if not 1<=vida<=MAX_VIDA or not MIN_JOGADORES<=limite<=MAX_JOGADORES:
            return await interaction.response.send_message('❌ Vida entre 1 e 700; limite entre 2 e 10.',ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with self.lock(interaction.guild_id,codigo):
            sala=await self.obter(interaction.guild_id,codigo)
            if not sala or sala['status']!='embarque' or sala['host_id']!=interaction.user.id:
                return await interaction.followup.send('❌ Somente o anfitrião pode configurar antes da partida.',ephemeral=True)
            if limite<len(sala['passageiros']):
                return await interaction.followup.send('❌ O limite não pode ser menor que o número de passageiros atuais.',ephemeral=True)
            sala.update(hp_max=vida,limite=limite)
            await self.salvar(sala)
            await self.atualizar(sala)
        await interaction.followup.send('⚙️ Configurações atualizadas.',ephemeral=True)

    async def premiar(self,sala):
        if sala['status']!='encerrada' or sala['vagao'] < len(VAGOES)-1: return 0
        total=0
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                for uid in vivos(sala):
                    ok=await conn.fetchval("""INSERT INTO expresso_salas_premios(guild_id,codigo,user_id,valor)
                      VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING user_id""",sala['guild_id'],sala['codigo'],uid,PREMIO)
                    if ok is None: continue
                    await cassino_db.garantir_carteira(uid,conn)
                    await conn.execute('UPDATE sants_carteiras SET saldo=saldo+$2, atualizado_em=NOW() WHERE user_id=$1',uid,PREMIO)
                    await conn.execute("""INSERT INTO sants_transacoes(user_id,tipo,quantia,descricao)
                      VALUES($1,'expresso',$2,$3)""",uid,PREMIO,f'Expresso Fantasma • sala {sala["codigo"]}')
                    total+=1
        return total

    @commands.command(name='premioexpresso')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def recuperar_premio(self,ctx,codigo:str):
        sala=await self.obter(ctx.guild.id,codigo.upper())
        if not sala or sala['status']!='encerrada': return await ctx.reply('❌ Sala encerrada não encontrada.',mention_author=False)
        total=await self.premiar(sala)
        await ctx.reply(f'🪙 {total} recompensa(s) recuperada(s).',mention_author=False)

    async def sala_acao(self,interaction,codigo,acao):
        # Modais exigem uma resposta inicial, antes de qualquer defer.
        if acao == 'config':
            sala = await self.obter(interaction.guild_id, codigo)
            if not sala or sala['status'] != 'embarque' or sala['host_id'] != interaction.user.id:
                return await interaction.response.send_message('🔒 Apenas o anfitrião configura a sala antes da viagem.', ephemeral=True)
            return await interaction.response.send_modal(ConfigModal(self, codigo))
        await interaction.response.defer(ephemeral=True)
        gid,uid=interaction.guild_id,interaction.user.id
        async with self.lock(gid,codigo):
            sala=await self.obter(gid,codigo)
            if not sala:
                return await interaction.followup.send('⚠️ Painel desatualizado ou sala inexistente.',ephemeral=True)
            if acao=='tripulacao':
                vidas=as_json(sala['vidas'],{})
                nomes='\n'.join(f'{i}. <@{p}> — {vidas.get(str(p),sala["hp_max"])} HP' for i,p in enumerate(sala['passageiros'],1)) or 'Nenhum passageiro.'
                return await interaction.followup.send('👥 **Tripulação**\n'+nomes,ephemeral=True)
            if acao=='encerrar':
                if uid!=sala['host_id'] and not interaction.user.guild_permissions.manage_guild:
                    return await interaction.followup.send('🔒 Somente anfitrião ou administração.',ephemeral=True)
                sala['status']='encerrada'; resposta='🔒 Sala encerrada.'
            elif sala['status']=='embarque':
                if acao=='entrar':
                    if uid in sala['passageiros']: return await interaction.followup.send('🎟️ Você já embarcou.',ephemeral=True)
                    if len(sala['passageiros'])>=sala['limite']: return await interaction.followup.send('❌ Sala lotada.',ephemeral=True)
                    sala['passageiros'].append(uid); resposta='🎟️ Você embarcou!'
                elif acao=='sair':
                    if uid==sala['host_id']: return await interaction.followup.send('👑 O anfitrião deve encerrar a sala para sair.',ephemeral=True)
                    if uid not in sala['passageiros']: return await interaction.followup.send('❌ Você não embarcou.',ephemeral=True)
                    sala['passageiros'].remove(uid); resposta='🚪 Você desembarcou.'
                elif acao=='iniciar':
                    if uid!=sala['host_id']: return await interaction.followup.send('🔒 Somente o anfitrião inicia a viagem.',ephemeral=True)
                    if len(sala['passageiros'])<MIN_JOGADORES: return await interaction.followup.send('❌ São necessários pelo menos dois passageiros.',ephemeral=True)
                    sala.update(status='viagem',vagao=0,vidas={str(u):sala['hp_max'] for u in sala['passageiros']},escolhas={},relatos=[])
                    resposta='🚂 A locomotiva partiu!'
                else: return await interaction.followup.send('❌ Ação inválida.',ephemeral=True)
            elif sala['status']=='viagem':
                if acao.startswith('escolha'):
                    if uid not in vivos(sala): return await interaction.followup.send('💀 Apenas passageiros vivos podem escolher.',ephemeral=True)
                    escolhas=as_json(sala['escolhas'],{})
                    if str(uid) in escolhas: return await interaction.followup.send('⏳ Você já escolheu neste vagão.',ephemeral=True)
                    try: opcao=VAGOES[sala['vagao']]['opcoes'][int(acao[-1])]
                    except (ValueError,IndexError): return await interaction.followup.send('❌ Escolha inválida.',ephemeral=True)
                    dano=random.SystemRandom().randint(*opcao[2]); vidas=as_json(sala['vidas'],{})
                    vidas[str(uid)]=max(0,int(vidas[str(uid)])-dano)
                    escolhas[str(uid)]=int(acao[-1]); sala['vidas']=vidas;sala['escolhas']=escolhas
                    sala['relatos']=(as_json(sala['relatos'],[])+[f'<@{uid}> escolheu {opcao[0]} e perdeu {dano} HP.'])[-8:]
                    resposta=f'{opcao[1]} **{opcao[0]}** — dano de {dano} HP. Restam {vidas[str(uid)]} HP.'
                elif acao=='avancar':
                    if uid!=sala['host_id']: return await interaction.followup.send('🔒 Somente o anfitrião avança.',ephemeral=True)
                    ativos=vivos(sala); escolhas=as_json(sala['escolhas'],{})
                    if ativos and any(str(p) not in escolhas for p in ativos):
                        return await interaction.followup.send('⏳ Aguarde as escolhas dos passageiros vivos.',ephemeral=True)
                    if not ativos or sala['vagao']>=len(VAGOES)-1:
                        sala['status']='encerrada';resposta='🏁 A viagem terminou!'
                    else:
                        sala['vagao']+=1;sala['escolhas']={};sala['relatos']=[]
                        resposta=f'🚂 Próxima parada: {VAGOES[sala["vagao"]]["nome"]}.'
                else: return await interaction.followup.send('❌ Ação indisponível.',ephemeral=True)
            else: return await interaction.followup.send('🏁 Esta sala já foi encerrada.',ephemeral=True)
            await self.salvar(sala)
            await self.atualizar(sala)
        await interaction.followup.send(resposta,view=SalaView(self,sala),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        if sala['status']=='encerrada' and acao=='avancar':
            try: await self.premiar(sala)
            except Exception: LOG.exception('Falha ao premiar sala %s',codigo)

    @commands.command(name='configexpresso')
    @commands.guild_only()
    async def config_comando(self,ctx,codigo:str,vida:int,limite:int):
        if not 1<=vida<=MAX_VIDA or not MIN_JOGADORES<=limite<=MAX_JOGADORES:
            return await ctx.reply('❌ Vida de 1 a 700; passageiros de 2 a 10.',mention_author=False)
        codigo=codigo.upper()
        async with self.lock(ctx.guild.id,codigo):
            sala=await self.obter(ctx.guild.id,codigo)
            if not sala or sala['status']!='embarque' or sala['host_id']!=ctx.author.id:
                return await ctx.reply('❌ Sala inexistente, iniciada ou você não é anfitrião.',mention_author=False)
            if limite<len(sala['passageiros']): return await ctx.reply('❌ Limite menor que a tripulação atual.',mention_author=False)
            sala.update(hp_max=vida,limite=limite)
            await self.salvar(sala);await self.atualizar(sala)
        await ctx.reply('⚙️ Configurações atualizadas.',mention_author=False)

async def setup(bot):
    await bot.add_cog(Expresso(bot))
