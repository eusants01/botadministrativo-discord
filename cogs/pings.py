
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger('royal.notificacoes')
COR = discord.Colour.from_rgb(188, 148, 86)
BANNER = Path(__file__).resolve().parent.parent / 'assets' / 'notificacoes_royal.png'
STAFF_IDS = {1553832098404499516, 1553832097905377422}
COOLDOWN = 3.0

NOTIFICACOES = {
    'sorteios': {'nome': 'Sorteios', 'emoji': '🎁', 'id': 1555798698410377246, 'desc': 'Premiações e sorteios da Família.'},
    'eventos': {'nome': 'Eventos', 'emoji': '🎉', 'id': 1555798699643375717, 'desc': 'Eventos e atividades da comunidade.'},
    'anuncios': {'nome': 'Anúncios', 'emoji': '📢', 'id': 1555798703586152458, 'desc': 'Comunicados oficiais e novidades.'},
    'avisos': {'nome': 'Avisos', 'emoji': '📜', 'id': 1555798705775448084, 'desc': 'Orientações e lembretes importantes.'},
    'videos': {'nome': 'Vídeos', 'emoji': '🎥', 'id': 1557612576798544002, 'desc': 'Novos vídeos e conteúdos publicados.'},
    'artes': {'nome': 'Artes', 'emoji': '🎨', 'id': 1559238946305613904, 'desc': 'Criações e trabalhos artísticos.'},
}

CREATE_TABLE = '''
CREATE TABLE IF NOT EXISTS pings_paineis (
  guild_id BIGINT NOT NULL,
  channel_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL,
  PRIMARY KEY (guild_id, message_id)
)'''


def staff(m: discord.Member) -> bool:
    return m.guild_permissions.manage_guild or m.guild_permissions.administrator or any(
        r.id in STAFF_IDS for r in m.roles
    )


def ids_ativos(member: discord.Member) -> set[str]:
    member_ids = {r.id for r in member.roles}
    return {k for k, value in NOTIFICACOES.items() if value['id'] in member_ids}


def cargos_gerenciaveis(guild: discord.Guild) -> tuple[dict[str, discord.Role], list[str]]:
    me = guild.me
    if me is None:
        return {}, ['Não foi possível identificar o cargo do bot.']
    if not me.guild_permissions.manage_roles:
        return {}, ['O bot precisa da permissão Gerenciar Cargos.']
    available, errors = {}, []
    for key, info in NOTIFICACOES.items():
        role = guild.get_role(info['id'])
        if role is None:
            errors.append(f"{info['nome']}: cargo {info['id']} não encontrado.")
        elif role.managed or role >= me.top_role:
            errors.append(f"{info['nome']}: cargo não gerenciável pela hierarquia do bot.")
        else:
            available[key] = role
    return available, errors


def card(title: str, body: str, *, tone: discord.Colour = COR) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    cont = discord.ui.Container(accent_colour=tone)
    cont.add_item(discord.ui.TextDisplay(f'## {title}\n{body}'))
    view.add_item(cont)
    return view


class PreferenceEngine:
    """Operações comuns aos painéis V2 e às mensagens antigas, sem editar mensagem pública."""

    def __init__(self, cog: 'NotificacoesRoyal'):
        self.cog = cog

    async def change(self, interaction: discord.Interaction, selected: set[str], mode: str = 'toggle'):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('❌ Utilize no servidor da Família Royal.', ephemeral=True)
        member = interaction.user
        now = time.monotonic()
        async with self.cog.lock_for(member.id):
            if now - self.cog.last_used.get(member.id, -100) < COOLDOWN:
                return await interaction.response.send_message('⏳ Aguarde alguns segundos para alterar novamente.', ephemeral=True)
            self.cog.last_used[member.id] = now
            manage, problems = cargos_gerenciaveis(interaction.guild)
            if not manage:
                return await interaction.response.send_message('❌ Não consigo gerenciar os cargos. Avise a Diretoria.', ephemeral=True)
            active = ids_ativos(member)
            if mode == 'all':
                add, remove = set(manage) - active, set()
            elif mode == 'none':
                add, remove = set(), set(manage) & active
            else:
                selected &= set(NOTIFICACOES)
                add, remove = (selected - active) & set(manage), (selected & active) & set(manage)
            unavailable = selected - set(manage) if mode == 'toggle' else set(NOTIFICACOES) - set(manage)
            if add or remove:
                # Somente os seis cargos do painel: os demais cargos do membro permanecem intocados.
                try:
                    if add:
                        await member.add_roles(*(manage[k] for k in add), reason='Central Royal — ativar notificações')
                    if remove:
                        await member.remove_roles(*(manage[k] for k in remove), reason='Central Royal — desativar notificações')
                except discord.HTTPException:
                    LOG.exception('Falha ao alterar notificações do usuário %s', member.id)
                    return await interaction.response.send_message(
                        '❌ O Discord não permitiu concluir a alteração. Confira a hierarquia dos cargos.', ephemeral=True)
            after = ids_ativos(member) | add
            after -= remove
            details = []
            if add:
                details.append('> `✅` Ativadas: ' + ', '.join(NOTIFICACOES[k]['nome'] for k in NOTIFICACOES if k in add))
            if remove:
                details.append('> `🔕` Desativadas: ' + ', '.join(NOTIFICACOES[k]['nome'] for k in NOTIFICACOES if k in remove))
            if unavailable:
                details.append('> `⚠️` Indisponíveis: ' + ', '.join(NOTIFICACOES[k]['nome'] for k in NOTIFICACOES if k in unavailable))
            if not details:
                details = ['Suas preferências já estavam configuradas dessa forma.']
            details.append(f'\n-# {len(after)}/{len(NOTIFICACOES)} notificações ativas.')
            await interaction.response.send_message(view=card('👑 PREFERÊNCIAS ATUALIZADAS', '\n'.join(details)), ephemeral=True)
            # Não deixa um seletor marcado publicamente nem edita os painéis.

    async def mine(self, interaction: discord.Interaction):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message('❌ Este recurso funciona apenas no servidor.', ephemeral=True)
        active = ids_ativos(interaction.user)
        lines = [f"> `{'✅' if k in active else '▫️'}` **{i['nome']}** — {'Ativa' if k in active else 'Desativada'}"
                 for k, i in NOTIFICACOES.items()]
        await interaction.response.send_message(
            view=card('📋 MINHAS NOTIFICAÇÕES', '\n'.join(lines) + f'\n\n-# {len(active)} de {len(NOTIFICACOES)} categorias ativas.'),
            ephemeral=True)


class PingSelect(discord.ui.Select):
    def __init__(self, cog: 'NotificacoesRoyal', *, legacy: bool = False):
        opts = [discord.SelectOption(label=i['nome'], value=k, description=i['desc'], emoji=i['emoji'])
                for k, i in NOTIFICACOES.items()]
        if legacy:
            opts.extend([
                discord.SelectOption(label='Ativar todas', value='__todas', emoji='✅'),
                discord.SelectOption(label='Desativar todas', value='__nenhuma', emoji='🚫'),
            ])
        super().__init__(placeholder='Escolha as notificações que deseja alterar', min_values=1,
                         max_values=len(opts) if legacy else len(NOTIFICACOES), options=opts,
                         custom_id='pings:select' if legacy else 'royal:pings:select:v2')
        self.cog = cog
        self.legacy = legacy

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        mode = 'none' if '__nenhuma' in selected else 'all' if '__todas' in selected else 'toggle'
        await PreferenceEngine(self.cog).change(interaction, selected, mode)


class OptionButton(discord.ui.Button):
    def __init__(self, cog: 'NotificacoesRoyal', mode: str, *, legacy: bool = False):
        items = {
            'mine': ('Minhas notificações', '📋', 'pings:minhas' if legacy else 'royal:pings:mine:v2'),
            'all': ('Ativar todas', '✅', 'royal:pings:all:v2'),
            'none': ('Desativar todas', '🔕', 'royal:pings:none:v2'),
        }
        label, emoji, custom_id = items[mode]
        super().__init__(label=label, emoji=emoji, custom_id=custom_id, style=discord.ButtonStyle.secondary)
        self.cog, self.mode = cog, mode

    async def callback(self, interaction: discord.Interaction):
        engine = PreferenceEngine(self.cog)
        if self.mode == 'mine':
            return await engine.mine(interaction)
        await engine.change(interaction, set(), self.mode)


class RoyalPingPanel(discord.ui.LayoutView):
    def __init__(self, cog: 'NotificacoesRoyal', banner_uri: str | None = None):
        super().__init__(timeout=None)
        c = discord.ui.Container(accent_colour=COR)
        if banner_uri:
            c.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner_uri)))
        c.add_item(discord.ui.TextDisplay(
            '## <a:animated_Notifications:1557622860569120821> CENTRAL DE NOTIFICAÇÕES\n'
            'Escolha quais novidades da **Família Royal** deseja acompanhar.'))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        c.add_item(discord.ui.TextDisplay(
            '> `🎁` **Sorteios** — Premiações e oportunidades.\n'
            '> `🎉` **Eventos** — Atividades da comunidade.\n'
            '> `📢` **Anúncios** — Novidades oficiais.\n'
            '> `📜` **Avisos** — Informações importantes.\n'
            '> `🎥` **Vídeos** — Conteúdos publicados.\n'
            '> `🎨` **Artes** — Criações da Família.'))
        c.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        c.add_item(discord.ui.ActionRow(PingSelect(cog)))
        c.add_item(discord.ui.ActionRow(OptionButton(cog, 'mine'), OptionButton(cog, 'all'), OptionButton(cog, 'none')))
        c.add_item(discord.ui.TextDisplay('-# ⚜️ Selecione uma categoria para ativar ou desativar. Suas escolhas são individuais.'))
        self.add_item(c)


class LegacyPingPanel(discord.ui.View):
    """Mantém interativos os embeds de notificações enviados pelo cog antigo."""
    def __init__(self, cog: 'NotificacoesRoyal'):
        super().__init__(timeout=None)
        self.add_item(PingSelect(cog, legacy=True))
        self.add_item(OptionButton(cog, 'mine', legacy=True))


class _MemberLock:
    def __init__(self, lock: asyncio.Lock):
        self.lock = lock
    async def __aenter__(self):
        await self.lock.acquire()
    async def __aexit__(self, exc_type, exc, tb):
        self.lock.release()


class NotificacoesRoyal(commands.Cog, name='Pings'):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_used: dict[int, float] = {}
        self.locks: dict[int, asyncio.Lock] = {}

    def lock_for(self, member_id: int) -> _MemberLock:
        return _MemberLock(self.locks.setdefault(member_id, asyncio.Lock()))

    @property
    def pool(self):
        return getattr(self.bot, 'pool', None)

    async def cog_load(self):
        self.bot.add_view(RoyalPingPanel(self))
        self.bot.add_view(LegacyPingPanel(self))
        if self.pool:
            await self.pool.execute(CREATE_TABLE)
        LOG.info('Central de Notificações Royal inicializada.')

    async def _record(self, guild_id: int, channel_id: int, message_id: int):
        if self.pool:
            await self.pool.execute(CREATE_TABLE)
            await self.pool.execute('''INSERT INTO pings_paineis(guild_id,channel_id,message_id)
                                       VALUES($1,$2,$3) ON CONFLICT DO NOTHING''', guild_id, channel_id, message_id)

    @staticmethod
    def _image_reference(message: discord.Message) -> str | None:
        # A URL do anexo continua válida ao editar componentes, sem reenviar arquivo.
        for attachment in message.attachments:
            if attachment.filename == BANNER.name:
                return attachment.url
        return None

    async def _publish(self, channel: discord.TextChannel):
        if BANNER.is_file():
            with BANNER.open('rb') as image:
                return await channel.send(view=RoyalPingPanel(self, f'attachment://{BANNER.name}'),
                                          file=discord.File(image, filename=BANNER.name),
                                          allowed_mentions=discord.AllowedMentions.none())
        return await channel.send(view=RoyalPingPanel(self), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='painelpings', aliases=['painel_notificacoes'])
    @commands.guild_only()
    async def painelpings(self, ctx: commands.Context, canal: discord.TextChannel | None = None):
        if not staff(ctx.author):
            return await ctx.reply('⛔ Comando exclusivo da equipe Royal.', mention_author=False)
        dest = canal or ctx.channel
        perms = dest.permissions_for(ctx.guild.me)
        if not perms.view_channel or not perms.send_messages or (BANNER.is_file() and not perms.attach_files):
            return await ctx.reply('❌ Verifique as permissões de enviar mensagens e anexar arquivos.', mention_author=False)
        msg = await self._publish(dest)
        await self._record(ctx.guild.id, dest.id, msg.id)
        await ctx.reply(f'✅ Central Royal publicada em {dest.mention}: {msg.jump_url}', mention_author=False)

    @commands.command(name='atualizarpings')
    @commands.guild_only()
    async def atualizarpings(self, ctx: commands.Context):
        if not staff(ctx.author):
            return await ctx.reply('⛔ Comando exclusivo da equipe Royal.', mention_author=False)
        if not self.pool:
            return await ctx.reply('❌ PostgreSQL indisponível.', mention_author=False)
        rows = await self.pool.fetch('SELECT channel_id,message_id FROM pings_paineis WHERE guild_id=$1', ctx.guild.id)
        updated, old, lost = 0, 0, 0
        for row in rows:
            channel = ctx.guild.get_channel(row['channel_id'])
            try:
                if channel is None:
                    channel = await ctx.guild.fetch_channel(row['channel_id'])
                msg = await channel.fetch_message(row['message_id'])
                # Mensagens antigas com embeds são mantidas, mas o comando pode criar a versão nova.
                if bool(getattr(msg.flags, 'is_components_v2', False)):
                    await msg.edit(view=RoyalPingPanel(self, self._image_reference(msg)), attachments=msg.attachments)
                    updated += 1
                else:
                    old += 1
            except discord.NotFound:
                await self.pool.execute('DELETE FROM pings_paineis WHERE guild_id=$1 AND message_id=$2', ctx.guild.id, row['message_id'])
                lost += 1
            except (discord.HTTPException, AttributeError):
                LOG.exception('Não foi possível atualizar painel %s', row['message_id'])
        await ctx.reply(f'✅ Atualizados: **{updated}**. Legados ainda ativos: **{old}**. Removidos: **{lost}**.\n'
                        'Use `!painelpings` para publicar o layout novo caso tenha painéis antigos.', mention_author=False)

    @commands.command(name='statuspings')
    @commands.guild_only()
    async def statuspings(self, ctx: commands.Context):
        if not staff(ctx.author):
            return await ctx.reply('⛔ Comando exclusivo da equipe Royal.', mention_author=False)
        usable, problems = cargos_gerenciaveis(ctx.guild)
        lines = [f"> `{n['emoji']}` **{n['nome']}** — {len(ctx.guild.get_role(n['id']).members)} integrantes"
                 if ctx.guild.get_role(n['id']) else f"> `⚠️` {n['nome']} — cargo ausente"
                 for n in NOTIFICACOES.values()]
        body = '\n'.join(lines) + (f'\n\n**Atenção**\n' + '\n'.join(problems) if problems else '\n\n✅ Cargos configurados corretamente.')
        body += f'\n-# {len(usable)}/{len(NOTIFICACOES)} cargos gerenciáveis.'
        await ctx.reply(view=card('📊 STATUS DAS NOTIFICAÇÕES', body), mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(NotificacoesRoyal(bot))
