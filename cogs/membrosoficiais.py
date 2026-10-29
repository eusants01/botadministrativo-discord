from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger('royal.membros')
COR = discord.Colour.from_rgb(188, 148, 86)
OFC_ROLE_ID = 1554367619463913582
FUNDADORES = {
    925863471902503033: ('Sant\'s', 'Criador da Família'),
    697068974323793921: ('Bruna', 'Fundadora'),
    1541150632554135724: ('Kael', 'Cofundador'),
}
ASSETS = Path(__file__).resolve().parent.parent / 'assets'
BANNER = ASSETS / 'membros_royal.png'
MAX_LINHAS = 25


def integrante(member: discord.Member) -> bool:
    return any(role.id == OFC_ROLE_ID for role in member.roles)


def seguro(texto: str) -> str:
    return discord.utils.escape_mentions(discord.utils.escape_markdown(texto))


class ConsultaSelect(discord.ui.Select):
    def __init__(self, cog: 'MembrosRoyal', membros: list[discord.Member], pagina: int = 0):
        self.cog = cog
        self.membros = membros
        self.pagina = pagina
        atual = membros[pagina * 25:(pagina + 1) * 25]
        opcoes = [discord.SelectOption(
            label=m.display_name[:100], value=str(m.id),
            description=f'@{m.name}'[:100], emoji='👑' if m.id in FUNDADORES else '🪽'
        ) for m in atual]
        super().__init__(placeholder=f'Escolha um integrante — página {pagina + 1}',
                         options=opcoes, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await self.cog.ficha(interaction, int(self.values[0]))


class ConsultaView(discord.ui.View):
    def __init__(self, cog: 'MembrosRoyal', membros: list[discord.Member], pagina: int = 0):
        super().__init__(timeout=180)
        self.cog = cog
        self.membros = membros
        self.pagina = pagina
        self.add_item(ConsultaSelect(cog, membros, pagina))
        total = (len(membros) + 24) // 25
        if pagina > 0:
            botao = discord.ui.Button(label='Anterior', emoji='⬅️', style=discord.ButtonStyle.secondary)
            async def voltar(interaction: discord.Interaction):
                await interaction.response.edit_message(view=ConsultaView(cog, membros, pagina - 1))
            botao.callback = voltar
            self.add_item(botao)
        if pagina + 1 < total:
            botao = discord.ui.Button(label='Próxima', emoji='➡️', style=discord.ButtonStyle.secondary)
            async def avancar(interaction: discord.Interaction):
                await interaction.response.edit_message(view=ConsultaView(cog, membros, pagina + 1))
            botao.callback = avancar
            self.add_item(botao)


class VerificarModal(discord.ui.Modal, title='Verificar integrante Royal'):
    usuario = discord.ui.TextInput(label='ID ou menção do usuário',
                                    placeholder='123456789012345678', min_length=15, max_length=80)

    def __init__(self, cog: 'MembrosRoyal'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        valor = str(self.usuario).strip()
        if valor.startswith('<@') and valor.endswith('>'):
            valor = valor[2:-1].lstrip('!')
        if not valor.isdecimal() or not 15 <= len(valor) <= 20:
            await interaction.response.send_message('❌ Informe uma menção ou ID válido.', ephemeral=True)
            return
        await self.cog.ficha(interaction, int(valor))


class BotaoConsultar(discord.ui.Button):
    def __init__(self, cog: 'MembrosRoyal'):
        super().__init__(label='Consultar integrantes', emoji='👥',
                         custom_id='royal:membros:consultar:v1', style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message('Disponível somente no servidor.', ephemeral=True)
        membros = self.cog.membros_oficiais(interaction.guild)
        if not membros:
            return await interaction.response.send_message('Não há membros oficiais cadastrados no momento.', ephemeral=True)
        await interaction.response.send_message('<a:coroa:1564000189167960177> **Consulta ao Quadro Oficial**',
                                                view=ConsultaView(self.cog, membros), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())


class BotaoVerificar(discord.ui.Button):
    def __init__(self, cog: 'MembrosRoyal'):
        super().__init__(label='Verificar membro', emoji='🛡️',
                         custom_id='royal:membros:verificar:v1', style=discord.ButtonStyle.secondary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(VerificarModal(self.cog))


class QuadroRoyal(discord.ui.LayoutView):
    def __init__(self, cog: 'MembrosRoyal', guild: discord.Guild | None = None,
                 imagem: str | None = None):
        super().__init__(timeout=None)
        caixa = discord.ui.Container(accent_colour=COR)
        if imagem:
            caixa.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=imagem)))
        caixa.add_item(discord.ui.TextDisplay(
            '## <a:coroa:1564000189167960177> QUADRO OFICIAL · FAMÍLIA ROYAL\n'
            'Relação pública dos integrantes reconhecidos oficialmente pela Família Royal.'))
        caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        if guild is not None:
            membros = cog.membros_oficiais(guild)
            fundadores = [m for m in membros if m.id in FUNDADORES]
            outros = [m for m in membros if m.id not in FUNDADORES]
            if fundadores:
                caixa.add_item(discord.ui.TextDisplay('**⚜️ FUNDAÇÃO**\n' + '\n'.join(
                    f'> `👑` {m.mention} — *{FUNDADORES[m.id][1]}*' for m in fundadores)))
                caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            linhas = [f'> `🪽` {m.mention}' for m in outros[:MAX_LINHAS]]
            restante = len(outros) - len(linhas)
            texto = '**🛡️ INTEGRANTES OFICIAIS**\n' + ('\n'.join(linhas) if linhas else '> Nenhum outro integrante no momento.')
            if restante > 0:
                texto += f'\n-# E mais {restante} integrantes. Utilize o botão para consultar a relação completa.'
            caixa.add_item(discord.ui.TextDisplay(texto))
            caixa.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            caixa.add_item(discord.ui.TextDisplay(
                f'> `👥` **{len(membros)}** integrantes reconhecidos\n'
                '> `📜` Fundação: **28/01/2026**\n'
                '-# A identificação oficial depende do cargo da Família no servidor.'))
        else:
            caixa.add_item(discord.ui.TextDisplay('Consulte ou verifique um membro utilizando os botões abaixo.'))
        caixa.add_item(discord.ui.ActionRow(BotaoConsultar(cog), BotaoVerificar(cog)))
        self.add_item(caixa)


class MembrosRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}

    def pool(self):
        pool = getattr(self.bot, 'pool', None)
        if pool is None:
            raise RuntimeError('PostgreSQL indisponível: bot.pool não inicializado.')
        return pool

    async def cog_load(self):
        await self.pool().execute('''CREATE TABLE IF NOT EXISTS royal_roster_panels (
            guild_id BIGINT PRIMARY KEY, channel_id BIGINT NOT NULL, message_id BIGINT NOT NULL)''')
        await self.pool().execute('''CREATE TABLE IF NOT EXISTS royal_roster_join_dates (
            guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, joined_at DATE NOT NULL,
            PRIMARY KEY(guild_id,user_id))''')
        self.bot.add_view(QuadroRoyal(self))
        LOG.info('Quadro Oficial Royal carregado.')

    def membros_oficiais(self, guild: discord.Guild) -> list[discord.Member]:
        role = guild.get_role(OFC_ROLE_ID)
        if role is None:
            return []
        return sorted((m for m in role.members if not m.bot),
                      key=lambda m: (m.id not in FUNDADORES, m.display_name.casefold(), m.id))

    async def ficha(self, interaction: discord.Interaction, user_id: int):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message('Consulta disponível no servidor.', ephemeral=True)
        membro = guild.get_member(user_id)
        if membro is None:
            try:
                membro = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                membro = None
        if membro is None or not integrante(membro):
            return await interaction.response.send_message(
                '❌ Este usuário não consta atualmente no quadro oficial da Família Royal.', ephemeral=True)
        data = await self.pool().fetchval('''SELECT joined_at FROM royal_roster_join_dates
            WHERE guild_id=$1 AND user_id=$2''', guild.id, membro.id)
        ingresso = data.strftime('%d/%m/%Y') if data else 'Ainda não cadastrada'
        instituicao = FUNDADORES.get(membro.id)
        cargo = instituicao[1] if instituicao else 'Integrante Oficial'
        insignias = [r.mention for r in membro.roles if r.name.casefold().startswith(('insígnia', 'insignia'))]
        texto = (f'## 👑 REGISTRO DE INTEGRANTE\n'
                 f'> `👤` **Membro:** {membro.mention}\n'
                 f'> `⚜️` **Posição:** {cargo}\n'
                 f'> `📅` **Ingresso oficial:** {ingresso}\n'
                 f'> `🏅` **Insígnias:** {", ".join(insignias[:8]) or "Nenhuma"}\n'
                 '> `🛡️` **Situação:** Membro oficial confirmado')
        v = discord.ui.LayoutView()
        v.add_item(discord.ui.Container(discord.ui.TextDisplay(texto), accent_colour=COR))
        await interaction.response.send_message(view=v, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    async def atualizar(self, guild: discord.Guild):
        lock = self._locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            registro = await self.pool().fetchrow('''SELECT channel_id,message_id FROM royal_roster_panels
                WHERE guild_id=$1''', guild.id)
            if not registro:
                return
            canal = guild.get_channel(registro['channel_id'])
            if canal is None:
                try:
                    canal = await guild.fetch_channel(registro['channel_id'])
                except discord.HTTPException:
                    LOG.exception('Canal do quadro Royal inacessível')
                    return
            try:
                msg = await canal.fetch_message(registro['message_id'])
                imagem = next((a.url for a in msg.attachments if a.content_type and
                               a.content_type.startswith('image/')), None)
                await msg.edit(view=QuadroRoyal(self, guild, imagem))
            except discord.HTTPException:
                LOG.exception('Falha ao atualizar o quadro oficial Royal')

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if integrante(before) != integrante(after):
            await self.atualizar(after.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if integrante(member):
            await self.atualizar(member.guild)

    @commands.command(name='painelmembros')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def painel_membros(self, ctx: commands.Context, canal: discord.TextChannel | None = None):
        destino = canal or ctx.channel
        me = ctx.guild.me or await ctx.guild.fetch_member(self.bot.user.id)
        permissoes = destino.permissions_for(me)
        if not (permissoes.view_channel and permissoes.send_messages):
            return await ctx.reply('❌ Faltam permissões de visualização ou envio de mensagens.', mention_author=False)
        if BANNER.is_file() and not permissoes.attach_files:
            return await ctx.reply('❌ Preciso da permissão Anexar arquivos.', mention_author=False)
        if not ctx.guild.get_role(OFC_ROLE_ID):
            return await ctx.reply('❌ Cargo OFC não encontrado neste servidor.', mention_author=False)
        try:
            if BANNER.is_file():
                with BANNER.open('rb') as f:
                    msg = await destino.send(view=QuadroRoyal(self, ctx.guild, f'attachment://{BANNER.name}'),
                                              file=discord.File(f, filename=BANNER.name),
                                              allowed_mentions=discord.AllowedMentions.none())
            else:
                msg = await destino.send(view=QuadroRoyal(self, ctx.guild),
                                         allowed_mentions=discord.AllowedMentions.none())
            anterior = await self.pool().fetchrow('''SELECT channel_id,message_id FROM royal_roster_panels
                WHERE guild_id=$1''', ctx.guild.id)
            await self.pool().execute('''INSERT INTO royal_roster_panels(guild_id,channel_id,message_id)
                VALUES($1,$2,$3) ON CONFLICT(guild_id) DO UPDATE
                SET channel_id=$2,message_id=$3''', ctx.guild.id, destino.id, msg.id)
            if anterior:
                try:
                    canal_anterior = ctx.guild.get_channel(anterior['channel_id']) or await ctx.guild.fetch_channel(anterior['channel_id'])
                    antiga = await canal_anterior.fetch_message(anterior['message_id'])
                    await antiga.delete()
                except discord.HTTPException:
                    LOG.warning('Não foi possível remover o painel antigo da Família Royal.')
            await ctx.reply(f'✅ Quadro público publicado em {destino.mention}: {msg.jump_url}', mention_author=False)
        except (discord.HTTPException, OSError):
            LOG.exception('Não foi possível publicar quadro Royal')
            await ctx.reply('❌ Não foi possível publicar o quadro. Confira os logs.', mention_author=False)

    @commands.command(name='atualizarmembros')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def atualizar_membros(self, ctx: commands.Context):
        await self.atualizar(ctx.guild)
        await ctx.reply('✅ Solicitação de atualização do quadro concluída.', mention_author=False)

    @commands.command(name='ingressomembro')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def ingresso_membro(self, ctx: commands.Context, membro: discord.Member, data: str):
        """!ingressomembro @usuario DD/MM/AAAA"""
        if not integrante(membro):
            return await ctx.reply('❌ O usuário não possui o cargo OFC.', mention_author=False)
        try:
            dia = datetime.strptime(data, '%d/%m/%Y').date()
            if dia > datetime.now(timezone.utc).date():
                raise ValueError
        except ValueError:
            return await ctx.reply('❌ Use uma data válida no formato DD/MM/AAAA.', mention_author=False)
        await self.pool().execute('''INSERT INTO royal_roster_join_dates(guild_id,user_id,joined_at)
            VALUES($1,$2,$3) ON CONFLICT(guild_id,user_id) DO UPDATE SET joined_at=$3''',
            ctx.guild.id, membro.id, dia)
        await self.atualizar(ctx.guild)
        await ctx.reply(f'✅ Ingresso oficial de {membro.mention} definido como {data}.', mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(MembrosRoyal(bot))
