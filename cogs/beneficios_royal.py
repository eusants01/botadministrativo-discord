from __future__ import annotations

import logging

import os

from datetime import datetime, timezone

from pathlib import Path

import discord

from discord.ext import commands

LOG = logging.getLogger('royal.beneficios')

COR = discord.Colour.from_rgb(188, 148, 86)

OFC_ROLE_ID = 1554367619463913582

STAFF_ROLE_IDS = {1553832098404499516, 1553832097905377422}

BANNER = Path(__file__).resolve().parent.parent / 'assets' / 'beneficios_royal.png'

BANNER_CONSELHO = Path(__file__).resolve().parent.parent / 'assets' / 'conselho_royal.png'
BANNER_INDICACOES = Path(__file__).resolve().parent.parent / 'assets' / 'indicacoes_royal.png'
PROPOSTAS_CHANNEL_ID = 1564875343330811925
BENEFICIOS_CHANNEL_ID = 1564005234655625327
FUNDADORES_ROLE_ID = 1553944794957615175

CONSELHO_CHANNEL_ID = int(os.getenv('ROYAL_BENEFICIOS_CONSELHO_CHANNEL_ID', '0') or 0)

GIVEAWAY_CHANNEL_ID = 1553829712621740103

ADMIN_CHANNEL_ID = int(os.getenv('ROYAL_BENEFICIOS_ADMIN_CHANNEL_ID', '0') or 0)

COROA = '👑'

def staff(member: discord.Member) -> bool:

    return (member.guild_permissions.manage_guild or member.guild_permissions.administrator

            or any(r.id in STAFF_ROLE_IDS for r in member.roles))

def oficial(member: discord.Member) -> bool:

    return staff(member) or any(r.id == OFC_ROLE_ID for r in member.roles)

async def check_ofc(interaction: discord.Interaction) -> bool:

    member = interaction.user

    if not isinstance(member, discord.Member) or not oficial(member):

        await interaction.response.send_message('🔒 Este benefício é exclusivo dos membros oficiais da Família Royal.', ephemeral=True)

        return False

    return True

def bloco(titulo: str, corpo: str, *, banner: bool = False, buttons=None) -> discord.ui.LayoutView:

    view = discord.ui.LayoutView(timeout=None)

    cont = discord.ui.Container(accent_colour=COR)

    if banner and BANNER.is_file():

        cont.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=f'attachment://{BANNER.name}')))

    cont.add_item(discord.ui.TextDisplay(f'## {titulo}\n{corpo}'))

    if buttons:

        cont.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        for start in range(0, len(buttons), 5):

            cont.add_item(discord.ui.ActionRow(*buttons[start:start + 5]))

    view.add_item(cont)

    return view

async def ephemeral(interaction: discord.Interaction, titulo: str, corpo: str, buttons=None):

    await interaction.response.send_message(view=bloco(titulo, corpo, buttons=buttons), ephemeral=True,

                                            allowed_mentions=discord.AllowedMentions.none())

class IndicacaoModal(discord.ui.Modal, title='Indicação Familiar Royal'):

    candidato = discord.ui.TextInput(label='ID ou @ do candidato no Discord', max_length=70,

                                      placeholder='Ex.: 123456789012345678')

    roblox = discord.ui.TextInput(label='Usuário Roblox (opcional)', required=False, max_length=80)

    justificativa = discord.ui.TextInput(label='Por que deseja indicá-lo?', style=discord.TextStyle.paragraph,

                                         max_length=900, min_length=15)

    def __init__(self, cog: 'BeneficiosRoyal'):

        super().__init__()

        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):

        if not await check_ofc(interaction):

            return

        candidato = str(self.candidato).strip()

        digits = ''.join(ch for ch in candidato if ch.isdigit())

        if len(digits) < 15 or len(digits) > 20:

            return await interaction.response.send_message('❌ Informe o ID numérico ou a menção do candidato.', ephemeral=True)

        uid = int(digits)

        if uid == interaction.user.id:

            return await interaction.response.send_message('❌ Você não pode indicar a si mesmo.', ephemeral=True)

        pool = self.cog.pool()

        async with pool.acquire() as conn:

            row = await conn.fetchrow('''INSERT INTO royal_benefit_referrals

                (guild_id, author_id, candidate_id, roblox, justification)

                VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING RETURNING id''',

                interaction.guild_id, interaction.user.id, uid,

                str(self.roblox).strip(), str(self.justificativa).strip())

        if not row:

            return await interaction.response.send_message('⏳ Já existe uma indicação pendente sua para este candidato.', ephemeral=True)

        await interaction.response.send_message(f'✅ Indicação registrada sob protocolo **ROY-{row["id"]:05d}**. A Diretoria fará a análise.', ephemeral=True)

        enviados = await self.cog.enviar_indicacao_staff(interaction.guild, row['id'])
        if enviados == 0:
            LOG.warning('Indicação #%s não foi entregue em nenhuma DM de fundador.', row['id'])

class PropostaModal(discord.ui.Modal, title='Proposta ao Conselho Royal'):

    titulo = discord.ui.TextInput(label='Título da proposta', min_length=5, max_length=100)

    detalhes = discord.ui.TextInput(label='Descreva sua proposta', style=discord.TextStyle.paragraph,

                                    min_length=20, max_length=1400)

    def __init__(self, cog: 'BeneficiosRoyal'):

        super().__init__()

        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):

        if not await check_ofc(interaction):

            return

        row = await self.cog.pool().fetchrow('''INSERT INTO royal_benefit_proposals

            (guild_id, author_id, title, body) VALUES ($1,$2,$3,$4) RETURNING id''',

            interaction.guild_id, interaction.user.id, str(self.titulo), str(self.detalhes))

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:

            mensagem = await self.cog.publicar_proposta(interaction.guild, row['id'])

        except (discord.HTTPException, OSError, RuntimeError):

            LOG.exception('Não foi possível publicar a proposta #%s', row['id'])

            await interaction.followup.send(

                f'⚠️ Proposta *#{row["id"]}** registrada, mas ainda não publicada. '

                'A Diretoria poderá usar `!votacaoroyal ID #canal`.', ephemeral=True)

        else:

            await interaction.followup.send(

                f'✅ Proposta *#{row["id"]}** publicada para votação dos membros OFC: {mensagem.jump_url}',

                ephemeral=True)

        await self.cog.enviar_proposta_staff(interaction.guild, row['id'])

class ReferralDecision(discord.ui.View):

    def __init__(self, cog: 'BeneficiosRoyal', ref_id: int):

        super().__init__(timeout=None)

        self.cog = cog

        self.ref_id = ref_id

        for accepted, label, style in [(True, 'Aprovar', discord.ButtonStyle.success),

                                       (False, 'Recusar', discord.ButtonStyle.danger)]:

            b = discord.ui.Button(label=label, style=style,

                                  custom_id=f'royal:beneficio:indicacao:{ref_id}:{int(accepted)}')

            async def cb(interaction, approve=accepted):

                await self.cog.decidir_indicacao(interaction, self.ref_id, approve)

            b.callback = cb

            self.add_item(b)

class VoteView(discord.ui.LayoutView):

    """Cartão público de votação, com custom_ids históricos preservados."""

    def __init__(self, cog: 'BeneficiosRoyal', proposal_id: int, row=None,

                 yes_count: int = 0, no_count: int = 0, with_banner: bool = False,

                 closed: bool = False):

        super().__init__(timeout=None)

        self.cog = cog

        self.proposal_id = proposal_id

        cont = discord.ui.Container(accent_colour=COR)

        if with_banner and (BANNER_CONSELHO if BANNER_CONSELHO.is_file() else BANNER).is_file():

            banner_file = BANNER_CONSELHO if BANNER_CONSELHO.is_file() else BANNER

            cont.add_item(discord.ui.MediaGallery(

                discord.MediaGalleryItem(media=f'attachment://{banner_file.name}')))

        if row is not None:

            titulo = discord.utils.escape_markdown(str(row['title']))[:100]

            descricao = discord.utils.escape_mentions(str(row['body']))[:1400]

            cont.add_item(discord.ui.TextDisplay(

                f'## <a:coroa:1564000189167960177> CONSELHO ROYAL · PROPOSTA #{proposal_id}\n'

                f'**{titulo}**\n{descricao}\n\n'

                f'> `👤` Proponente: <@{row["author_id"]}>\n'

                f'> `📊` A favor: **{yes_count}** · Contra: **{no_count}**\n'

                f'> `📜` Situação: **{"Encerrada" if closed else "Votação aberta"}**'))

        else:

            cont.add_item(discord.ui.TextDisplay(

                f'## <a:coroa:1564000189167960177> CONSELHO ROYAL · PROPOSTA #{proposal_id}'))

        if not closed:

            linha = discord.ui.ActionRow()

            for favor, nome, emoji in ((True, 'A favor', '✅'), (False, 'Contra', '❎')):

                botao = discord.ui.Button(label=nome, emoji=emoji,

                    style=discord.ButtonStyle.secondary,

                    custom_id=f'royal:beneficio:voto:{proposal_id}:{int(favor)}')

                async def callback(interaction: discord.Interaction, escolha=favor):

                    await self.cog.votar(interaction, self.proposal_id, escolha)

                botao.callback = callback

                linha.add_item(botao)

            cont.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

            cont.add_item(linha)

        cont.add_item(discord.ui.TextDisplay(

            '-# Família Royal • Cada membro OFC possui um voto, alterável enquanto aberto. '

            'O resultado é consultivo.'))

        self.add_item(cont)

class EventView(discord.ui.View):

    def __init__(self, cog: 'BeneficiosRoyal', event_id: int):

        super().__init__(timeout=None)

        self.cog = cog

        self.event_id = event_id

        for attending, label, emoji in [(True, 'Confirmar presença', '✅'), (False, 'Cancelar inscrição', '🚪')]:

            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary,

                                  custom_id=f'royal:beneficio:evento:{event_id}:{int(attending)}')

            async def cb(interaction, choice=attending):

                await self.cog.evento_presenca(interaction, self.event_id, choice)

            b.callback = cb

            self.add_item(b)

class BenefitButton(discord.ui.Button):

    def __init__(self, cog: 'BeneficiosRoyal', action: str, label: str, emoji: str):

        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary,

                         custom_id=f'royal:beneficios:{action}:v1')

        self.cog = cog

        self.action = action

    async def callback(self, interaction: discord.Interaction):

        if not await check_ofc(interaction):

            return

        cog = self.cog

        guild = interaction.guild

        if self.action == 'indicacao':

            return await interaction.response.send_modal(IndicacaoModal(cog))

        if self.action == 'conselho':

            return await interaction.response.send_modal(PropostaModal(cog))

        if self.action == 'sorteios':

            channel = guild.get_channel(GIVEAWAY_CHANNEL_ID)

            await ephemeral(interaction, '🎁 SORTEIOS OFICIAIS',

                f'Consulte as premiações em {channel.mention if channel else "nos canais de sorteios"}.\n'

                f'Os sorteios OFC exigem o cargo <@&{OFC_ROLE_ID}> como requisito.\n'

                'A participação é realizada no painel próprio de cada sorteio.')

        elif self.action == 'perfil':

            await cog.perfil(interaction)

        elif self.action == 'eventos':

            await cog.eventos(interaction)

        elif self.action == 'resumo':

            await cog.resumo(interaction)

class BenefitPanel(discord.ui.LayoutView):

    def __init__(self, cog: 'BeneficiosRoyal', with_banner: bool = False):

        super().__init__(timeout=None)

        p = discord.ui.Container(accent_colour=COR)

        if with_banner and BANNER.is_file():

            p.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(media=f'attachment://{BANNER.name}')))

        p.add_item(discord.ui.TextDisplay(

            '## <a:coroa:1564000189167960177> PRIVILÉGIOS DA FAMÍLIA\n'

            'Central reservada aos membros oficiais da **Família Royal**.\n'

            'Consulte benefícios e participe das iniciativas exclusivas de nossa comunidade.'))

        p.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        p.add_item(discord.ui.TextDisplay(

            '> `🎁` **Sorteios** — Premiações reservadas aos OFC.\n'

            '> `📜` **Indicações** — Recomende candidatos à Família.\n'

            '> `👤` **Perfil Royal** — Sua trajetória e insígnias.\n'

            '> `🎭` **Eventos** — Atividades e inscrições privativas.\n'

            '> `⚖️` **Conselho** — Propostas e votações consultivas.'))

        p.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        buttons = [

            BenefitButton(cog, 'sorteios', 'Sorteios', '<a:Presenteghost:1553872045492797550>'),

            BenefitButton(cog, 'indicacao', 'Indicar membro', '<:ImagemdoChatGPT25deoutde202615_4:1563986647144730826>'),

            BenefitButton(cog, 'perfil', 'Meu perfil', '<a:animated_Settings:1556187476177981440>'),

            BenefitButton(cog, 'eventos', 'Eventos', '<:versustrophy:1564669597440016485>'),

            BenefitButton(cog, 'conselho', 'Conselho', '<:pj:1564669592540942416>'),

            BenefitButton(cog, 'resumo', 'Meus benefícios', '<a:coroa:1564000189167960177>'),

        ]

        p.add_item(discord.ui.ActionRow(*buttons[:3]))

        p.add_item(discord.ui.ActionRow(*buttons[3:]))

        p.add_item(discord.ui.TextDisplay('-# Família Royal • Honra à coroa. Lealdade à família.'))

        self.add_item(p)

class BeneficiosRoyal(commands.Cog):

    def __init__(self, bot: commands.Bot):

        self.bot = bot

    def pool(self):

        pool = getattr(self.bot, 'pool', None)

        if pool is None:

            raise RuntimeError('PostgreSQL indisponível: confira bot.pool e DATABASE_URL.')

        return pool

    async def cog_load(self):

        pool = self.pool()

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_referrals (

            id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, author_id BIGINT NOT NULL,

            candidate_id BIGINT NOT NULL, roblox TEXT NOT NULL DEFAULT '',

            justification TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',

            reviewer_id BIGINT, reviewed_at TIMESTAMPTZ, staff_message_id BIGINT,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

        await pool.execute('''CREATE UNIQUE INDEX IF NOT EXISTS royal_benefit_referral_pending

            ON royal_benefit_referrals (guild_id, author_id, candidate_id) WHERE status='pending' ''')

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_proposals (

            id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, author_id BIGINT NOT NULL,

            title TEXT NOT NULL, body TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'submitted', staff_message_id BIGINT,

            voting_message_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_settings (

            guild_id BIGINT PRIMARY KEY,

            benefits_channel_id BIGINT NOT NULL)''')

        await pool.execute('''ALTER TABLE royal_benefit_proposals

            ADD COLUMN IF NOT EXISTS voting_channel_id BIGINT''')

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_votes (

            proposal_id BIGINT NOT NULL REFERENCES royal_benefit_proposals(id),

            user_id BIGINT NOT NULL, support BOOLEAN NOT NULL,

            PRIMARY KEY(proposal_id,user_id))''')

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_events (

            id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, title TEXT NOT NULL,

            details TEXT NOT NULL, starts_at TIMESTAMPTZ NOT NULL,

            status TEXT NOT NULL DEFAULT 'open', message_id BIGINT,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_attendance (

            event_id BIGINT NOT NULL REFERENCES royal_benefit_events(id),

            user_id BIGINT NOT NULL, PRIMARY KEY(event_id,user_id))''')

        self.bot.add_view(BenefitPanel(self, False))

        await pool.execute('''CREATE TABLE IF NOT EXISTS royal_benefit_referral_dms (
            referral_id BIGINT NOT NULL REFERENCES royal_benefit_referrals(id),
            founder_id BIGINT NOT NULL, message_id BIGINT NOT NULL,
            PRIMARY KEY(referral_id,founder_id))''')
        pending_ids = await pool.fetch("SELECT id FROM royal_benefit_referrals WHERE status='pending'")
        for row in pending_ids:
            self.bot.add_view(ReferralDecision(self, row['id']))

        for row in await pool.fetch("SELECT id, voting_message_id FROM royal_benefit_proposals WHERE status='voting' AND voting_message_id IS NOT NULL"):

            self.bot.add_view(VoteView(self, row['id']), message_id=row['voting_message_id'])

        for row in await pool.fetch("SELECT id, message_id FROM royal_benefit_events WHERE status='open' AND message_id IS NOT NULL"):

            self.bot.add_view(EventView(self, row['id']), message_id=row['message_id'])

        LOG.info('Benefícios Royal carregados.')

    async def admin_channel(self, guild: discord.Guild):

        if not ADMIN_CHANNEL_ID:

            return None

        channel = guild.get_channel(ADMIN_CHANNEL_ID)

        if channel is None:

            try:

                channel = await guild.fetch_channel(ADMIN_CHANNEL_ID)

            except discord.HTTPException:

                return None

        return channel if isinstance(channel, discord.TextChannel) else None

    async def enviar_indicacao_staff(self, guild: discord.Guild, ref_id: int) -> int:
        """Encaminha a indicação por DM a todos os fundadores com acesso ao servidor."""
        row = await self.pool().fetchrow('SELECT * FROM royal_benefit_referrals WHERE id=$1', ref_id)
        if row is None:
            return 0
        role = guild.get_role(FUNDADORES_ROLE_ID)
        if role is None:
            LOG.error('Cargo dos fundadores %s não existe no servidor %s', FUNDADORES_ROLE_ID, guild.id)
            return 0
        # A lista de membros requer Members Intent habilitado no portal e no bot.
        founders = [m for m in role.members if not m.bot]
        if not founders:
            LOG.error('Nenhum fundador encontrado no cache; confira Members Intent e o cargo de fundadores')
            return 0
        sent = 0
        for founder in founders:
            try:
                panel = discord.ui.Container(accent_colour=COR)
                if BANNER_INDICACOES.is_file():
                    panel.add_item(discord.ui.MediaGallery(
                        discord.MediaGalleryItem(media=f'attachment://{BANNER_INDICACOES.name}')))
                panel.add_item(discord.ui.TextDisplay(
                    f'## 👑 INDICAÇÃO ROYAL · ROY-{ref_id:05d}\n'
                    f'> `👤` Indicado por: <@{row["author_id"]}>\n'
                    f'> `🎯` Candidato: <@{row["candidate_id"]}>\n'
                    f'> `🎮` Roblox: {discord.utils.escape_markdown(row["roblox"] or "Não informado")}\n\n'
                    f'**📜 JUSTIFICATIVA**\n{discord.utils.escape_mentions(str(row["justification"]))[:900]}\n\n'
                    '-# Decisão exclusiva dos fundadores · A indicação não concede cargo automaticamente.'))
                buttons = ReferralDecision(self, ref_id)
                panel.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
                botoes = list(buttons.children)
                for botao in botoes:
                    botao._view = None
                panel.add_item(discord.ui.ActionRow(*botoes))
                view = discord.ui.LayoutView(timeout=None)
                view.add_item(panel)
                if BANNER_INDICACOES.is_file():
                    with BANNER_INDICACOES.open('rb') as image:
                        msg = await founder.send(view=view,
                            file=discord.File(image, filename=BANNER_INDICACOES.name),
                            allowed_mentions=discord.AllowedMentions.none())
                else:
                    msg = await founder.send(view=view, allowed_mentions=discord.AllowedMentions.none())
                await self.pool().execute("""INSERT INTO royal_benefit_referral_dms
                    (referral_id,founder_id,message_id) VALUES($1,$2,$3)
                    ON CONFLICT(referral_id,founder_id) DO UPDATE SET message_id=$3""",
                    ref_id, founder.id, msg.id)
                sent += 1
            except (discord.HTTPException, OSError):
                LOG.exception('Não foi possível enviar indicação #%s por DM ao fundador %s', ref_id, founder.id)
        if sent:
            self.bot.add_view(ReferralDecision(self, ref_id))
        return sent

    async def decidir_indicacao(self, interaction: discord.Interaction, ref_id: int, approved: bool):
        # As interações ocorrem na DM: interaction.user não é discord.Member.
        row = await self.pool().fetchrow('SELECT * FROM royal_benefit_referrals WHERE id=$1', ref_id)
        if row is None:
            return await interaction.response.send_message('Indicação não encontrada.', ephemeral=True)
        guild = self.bot.get_guild(int(row['guild_id']))
        if guild is None:
            return await interaction.response.send_message('Servidor indisponível.', ephemeral=True)
        try:
            founder = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
        except discord.HTTPException:
            return await interaction.response.send_message('Não foi possível confirmar seu cargo de fundador.', ephemeral=True)
        if not any(role.id == FUNDADORES_ROLE_ID for role in founder.roles):
            return await interaction.response.send_message('⛔ Apenas fundadores podem decidir indicações.', ephemeral=True)
        state = 'approved' if approved else 'rejected'
        updated = await self.pool().fetchrow("""UPDATE royal_benefit_referrals
            SET status=$2, reviewer_id=$3, reviewed_at=NOW()
            WHERE id=$1 AND status='pending' RETURNING author_id""",
            ref_id, state, interaction.user.id)
        if updated is None:
            return await interaction.response.send_message('Esta indicação já foi decidida.', ephemeral=True)
        await interaction.response.send_message(
            f'✅ Indicação ROY-{ref_id:05d} **{"aprovada" if approved else "recusada"}**. ' 
            'O ingresso não é concedido automaticamente.', ephemeral=True)
        try:
            requester = await self.bot.fetch_user(updated['author_id'])
            await requester.send(f'👑 Sua indicação ROY-{ref_id:05d} foi **{"aprovada" if approved else "recusada"}** pelos fundadores.')
        except discord.HTTPException:
            LOG.warning('Não foi possível avisar o autor da indicação #%s', ref_id)
        for dm in await self.pool().fetch('SELECT founder_id,message_id FROM royal_benefit_referral_dms WHERE referral_id=$1', ref_id):
            try:
                target = await self.bot.fetch_user(dm['founder_id'])
                channel = await target.create_dm()
                message = await channel.fetch_message(dm['message_id'])
                finished = discord.ui.LayoutView(timeout=None)
                finished.add_item(discord.ui.Container(
                    discord.ui.TextDisplay(f'## ⚜️ INDICAÇÃO ROYAL · ROY-{ref_id:05d}\n'
                        f'**Decisão: {"Aprovada" if approved else "Recusada"}**\n'
                        f'-# Decidida por <@{interaction.user.id}>.'), accent_colour=COR))
                await message.edit(view=finished)
            except discord.HTTPException:
                LOG.warning('Não foi possível atualizar DM da indicação #%s para %s',ref_id,dm['founder_id'])

    async def enviar_proposta_staff(self, guild: discord.Guild, proposal_id: int):

        channel = await self.admin_channel(guild)

        if channel is None:

            LOG.warning('Proposta #%s registrada sem canal administrativo.', proposal_id)

            return

        row = await self.pool().fetchrow('SELECT * FROM royal_benefit_proposals WHERE id=$1', proposal_id)

        embed = discord.Embed(title=f'⚖️ Proposta Royal #{proposal_id} — {row["title"]}',

                              description=f'Autor: <@{row["author_id"]}>\n\n{row["body"]}', color=COR)

        try:

            msg = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

            await self.pool().execute('UPDATE royal_benefit_proposals SET staff_message_id=$1 WHERE id=$2', msg.id, proposal_id)

        except discord.HTTPException:

            LOG.exception('Erro ao encaminhar proposta #%s', proposal_id)

    async def canal_conselho(self, guild: discord.Guild):

        canal_id = PROPOSTAS_CHANNEL_ID

        if not canal_id:

            canal_id = await self.pool().fetchval(

                'SELECT benefits_channel_id FROM royal_benefit_settings WHERE guild_id=$1', guild.id)

        if not canal_id:

            raise RuntimeError('Publique primeiro o painel com !painelbeneficios #canal ou configure ROYAL_BENEFICIOS_CONSELHO_CHANNEL_ID.')

        channel = guild.get_channel(int(canal_id))

        if channel is None:

            channel = await guild.fetch_channel(int(canal_id))

        if not isinstance(channel, discord.TextChannel):

            raise RuntimeError('O canal do Conselho não é um canal de texto.')

        if channel.permissions_for(guild.default_role).view_channel:

            raise RuntimeError('Canal do Conselho não é privado: bloqueie @everyone antes de publicar.')

        return channel

    async def contagem_votos(self, proposal_id: int):

        row = await self.pool().fetchrow('''SELECT

            COUNT(*) FILTER(WHERE support) AS favor,

            COUNT(*) FILTER(WHERE NOT support) AS contra

            FROM royal_benefit_votes WHERE proposal_id=$1''', proposal_id)

        return int(row['favor'] or 0), int(row['contra'] or 0)

    async def publicar_proposta(self, guild: discord.Guild, proposal_id: int,

                               channel: discord.TextChannel | None = None):

        row = await self.pool().fetchrow('''SELECT * FROM royal_benefit_proposals

            WHERE id=$1 AND guild_id=$2 AND status='submitted' ''', proposal_id, guild.id)

        if row is None:

            raise RuntimeError('Proposta já publicada ou inexistente.')

        channel = channel or await self.canal_conselho(guild)

        if channel.guild.id != guild.id or channel.permissions_for(guild.default_role).view_channel:

            raise RuntimeError('A votação deve ocorrer em um canal privado da Família Royal.')

        banner = BANNER_CONSELHO if BANNER_CONSELHO.is_file() else BANNER

        view = VoteView(self, proposal_id, row, with_banner=banner.is_file())

        if banner.is_file():

            with banner.open('rb') as arquivo:

                mensagem = await channel.send(

                    view=view, file=discord.File(arquivo, filename=banner.name),

                    allowed_mentions=discord.AllowedMentions.none())

        else:

            mensagem = await channel.send(view=view, allowed_mentions=discord.AllowedMentions.none())

        atualizado = await self.pool().fetchrow('''UPDATE royal_benefit_proposals

            SET status='voting', voting_message_id=$2, voting_channel_id=$3

            WHERE id=$1 AND status='submitted' RETURNING id''',

            proposal_id, mensagem.id, channel.id)

        if not atualizado:

            await mensagem.delete()

            raise RuntimeError('A proposta foi publicada simultaneamente em outro local.')

        self.bot.add_view(VoteView(self, proposal_id), message_id=mensagem.id)

        return mensagem

    async def atualizar_votacao(self, guild: discord.Guild, proposal_id: int):

        row = await self.pool().fetchrow('''SELECT * FROM royal_benefit_proposals

            WHERE id=$1 AND guild_id=$2''', proposal_id, guild.id)

        if not row or not row['voting_channel_id'] or not row['voting_message_id']:

            return

        channel = guild.get_channel(row['voting_channel_id'])

        if channel is None:

            channel = await guild.fetch_channel(row['voting_channel_id'])

        mensagem = await channel.fetch_message(row['voting_message_id'])

        favor, contra = await self.contagem_votos(proposal_id)

        banner = any(a.filename in {BANNER.name, BANNER_CONSELHO.name} for a in mensagem.attachments)

        await mensagem.edit(view=VoteView(self, proposal_id, row, favor, contra,

            with_banner=banner, closed=row['status'] != 'voting'))

    async def votar(self, interaction: discord.Interaction, proposal_id: int, yes: bool):

        if not await check_ofc(interaction):

            return

        async with self.pool().acquire() as conn:

            active = await conn.fetchval("SELECT 1 FROM royal_benefit_proposals WHERE id=$1 AND guild_id=$2 AND status='voting'",

                                         proposal_id, interaction.guild_id)

            if not active:

                return await interaction.response.send_message('Votação encerrada ou indisponível.', ephemeral=True)

            await conn.execute('''INSERT INTO royal_benefit_votes(proposal_id,user_id,support)

                VALUES($1,$2,$3) ON CONFLICT(proposal_id,user_id) DO UPDATE SET support=$3''',

                proposal_id, interaction.user.id, yes)

        await interaction.response.send_message(

            '✅ Seu voto foi registrado. Você pode alterá-lo enquanto a votação estiver aberta.',

            ephemeral=True)

        try:

            await self.atualizar_votacao(interaction.guild, proposal_id)

        except discord.HTTPException:

            LOG.warning('Falha ao atualizar contadores da proposta #%s', proposal_id)

    async def evento_presenca(self, interaction: discord.Interaction, event_id: int, attend: bool):

        if not await check_ofc(interaction):

            return

        async with self.pool().acquire() as conn:

            active = await conn.fetchval("SELECT 1 FROM royal_benefit_events WHERE id=$1 AND guild_id=$2 AND status='open' AND starts_at > NOW()",

                                         event_id, interaction.guild_id)

            if not active:

                return await interaction.response.send_message('As inscrições deste evento estão encerradas.', ephemeral=True)

            if attend:

                await conn.execute('INSERT INTO royal_benefit_attendance(event_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING', event_id, interaction.user.id)

            else:

                await conn.execute('DELETE FROM royal_benefit_attendance WHERE event_id=$1 AND user_id=$2', event_id, interaction.user.id)

        await interaction.response.send_message('✅ Presença confirmada.' if attend else '✅ Inscrição cancelada.', ephemeral=True)

    async def perfil(self, interaction: discord.Interaction):

        member = interaction.user

        roles = [r.mention for r in member.roles if r.name.lower().startswith('insígnia') or r.name.lower().startswith('insignia')]

        indic = await self.pool().fetchrow('''SELECT COUNT(*) AS total,

            COUNT(*) FILTER (WHERE status='pending') AS pending,

            COUNT(*) FILTER (WHERE status='approved') AS approved

            FROM royal_benefit_referrals WHERE guild_id=$1 AND author_id=$2''', interaction.guild_id, member.id)

        inscricoes = await self.pool().fetchval('''SELECT COUNT(*) FROM royal_benefit_attendance a

            JOIN royal_benefit_events e ON e.id=a.event_id WHERE e.guild_id=$1 AND a.user_id=$2''', interaction.guild_id, member.id)

        joined = f'<t:{int(member.joined_at.timestamp())}:D>' if member.joined_at else 'Não registrada'

        await ephemeral(interaction, '👤 IDENTIDADE ROYAL',

            f'> `👑` Integrante: {member.mention}\n> `📅` No servidor desde: {joined}\n'

            f'> `🏅` Insígnias: {", ".join(roles[:8]) or "Nenhuma registrada"}\n'

            f'> `📜` Indicações: **{indic["total"]}** (pendentes: {indic["pending"]}; aprovadas: {indic["approved"]})\n'

            f'> `🎭` Inscrições em eventos: **{inscricoes}**\n\n'

            '-# O tempo de associação oficial pode diferir da entrada no servidor.')

    async def eventos(self, interaction: discord.Interaction):

        rows = await self.pool().fetch('''SELECT id,title,starts_at FROM royal_benefit_events

            WHERE guild_id=$1 AND status='open' AND starts_at > NOW() ORDER BY starts_at LIMIT 8''', interaction.guild_id)

        texto = '\n'.join(f'> `🎭` #{r["id"]} — {r["title"]}** • <t:{int(r["starts_at"].timestamp())}:F>' for r in rows)

        await ephemeral(interaction, '🎭 EVENTOS OFICIAIS', texto or 'Não há eventos OFC com inscrições abertas. Consulte novamente em breve.')

    async def resumo(self, interaction: discord.Interaction):

        p = await self.pool().fetchval("SELECT COUNT(*) FROM royal_benefit_referrals WHERE guild_id=$1 AND author_id=$2 AND status='pending'", interaction.guild_id, interaction.user.id)

        e = await self.pool().fetchval('''SELECT COUNT(*) FROM royal_benefit_attendance a JOIN royal_benefit_events e

            ON a.event_id=e.id WHERE e.guild_id=$1 AND a.user_id=$2 AND e.starts_at>NOW() AND e.status='open' ''',

            interaction.guild_id, interaction.user.id)

        await ephemeral(interaction, '👑 MEUS BENEFÍCIOS',

            f'> `✅` Cargo OFC: **ativo**\n> `📜` Indicações aguardando decisão: **{p}**\n'

            f'> `🎭` Próximos eventos inscritos: **{e}**\n> `⚖️` Conselho consultivo: **disponível**\n'

            '> `🎁` Sorteios OFC: **conforme publicações vigentes**')

    @commands.command(name='painelbeneficios')

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def painel_beneficios(self, ctx: commands.Context, canal: discord.TextChannel | None = None):

        destino = canal or ctx.guild.get_channel(BENEFICIOS_CHANNEL_ID) or ctx.channel

        me = ctx.guild.me

        perms = destino.permissions_for(me)

        if not (perms.view_channel and perms.send_messages):

            return await ctx.reply('❌ Sem permissão para enviar mensagens ao canal escolhido.', mention_author=False)

        if BANNER.is_file() and not perms.attach_files:

            return await ctx.reply('❌ Necessito da permissão Anexar arquivos para enviar o banner.', mention_author=False)

        try:

            if BANNER.is_file():

                with BANNER.open('rb') as f:

                    msg = await destino.send(view=BenefitPanel(self, True),

                        file=discord.File(f, filename=BANNER.name), allowed_mentions=discord.AllowedMentions.none())

            else:

                msg = await destino.send(view=BenefitPanel(self), allowed_mentions=discord.AllowedMentions.none())

            await ctx.reply(f'✅ Painel publicado em {destino.mention}: {msg.jump_url}', mention_author=False)

        except discord.HTTPException:

            LOG.exception('Erro ao publicar benefícios')

            await ctx.reply('❌ Não foi possível publicar o painel. Consulte os logs.', mention_author=False)

    @commands.command(name='criareventoofc')

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def criar_evento(self, ctx: commands.Context, data_utc: str, canal: discord.TextChannel, *, titulo: str):

        """!criareventoofc 2026-11-01T20:00Z #eventos Noite Roblox | descrição opcional"""

        try:

            when = datetime.fromisoformat(data_utc.replace('Z', '+00:00'))

            if when.tzinfo is None or when <= datetime.now(timezone.utc):

                raise ValueError

        except ValueError:

            return await ctx.reply('❌ Informe uma data UTC futura: `2026-11-01T20:00Z`.', mention_author=False)

        partes = titulo.split('|', 1)

        nome = partes[0].strip()[:100]

        descricao = partes[1].strip()[:700] if len(partes) > 1 else 'Evento exclusivo aos membros oficiais.'

        if not nome:

            return await ctx.reply('❌ Informe o nome do evento.', mention_author=False)

        row = await self.pool().fetchrow('''INSERT INTO royal_benefit_events (guild_id,title,details,starts_at)

            VALUES ($1,$2,$3,$4) RETURNING id''', ctx.guild.id, nome, descricao, when)

        event_id = row['id']

        try:

            msg = await canal.send(embed=discord.Embed(title=f'🎭 EVENTO OFC — {nome}',

                description=f'{descricao}\n\n> `🕒` Data: <t:{int(when.timestamp())}:F>\n> `👑` Exclusivo para membros oficiais.', color=COR),

                view=EventView(self, event_id), allowed_mentions=discord.AllowedMentions.none())

            await self.pool().execute('UPDATE royal_benefit_events SET message_id=$1 WHERE id=$2', msg.id, event_id)

            self.bot.add_view(EventView(self, event_id), message_id=msg.id)

        except discord.HTTPException:

            await self.pool().execute("UPDATE royal_benefit_events SET status='closed' WHERE id=$1", event_id)

            return await ctx.reply('❌ Falha ao publicar evento. Confirme as permissões.', mention_author=False)

        await ctx.reply(f'✅ Evento OFC #{event_id} publicado.', mention_author=False)

    @commands.command(name='votacaoroyal')

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def abrir_votacao(self, ctx: commands.Context, proposta_id: int, canal: discord.TextChannel):

        try:

            mensagem = await self.publicar_proposta(ctx.guild, proposta_id, canal)

        except (discord.HTTPException, OSError, RuntimeError) as exc:

            return await ctx.reply(f'❌ Não foi possível publicar a proposta: {exc}', mention_author=False)

        await ctx.reply(f'✅ Votação #{proposta_id} aberta: {mensagem.jump_url}', mention_author=False)

    @commands.command(name='encerrarvotacaoroyal')

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def encerrar_votacao(self, ctx: commands.Context, proposta_id: int):

        row = await self.pool().fetchrow("UPDATE royal_benefit_proposals SET status='closed' WHERE id=$1 AND guild_id=$2 AND status='voting' RETURNING *", proposta_id, ctx.guild.id)

        if row is None:

            return await ctx.reply('❌ Votação não encontrada ou encerrada.', mention_author=False)

        results = await self.pool().fetchrow('''SELECT COUNT(*) FILTER(WHERE support) AS yes,

            COUNT(*) FILTER(WHERE NOT support) AS no FROM royal_benefit_votes WHERE proposal_id=$1''', proposta_id)

        try:

            await self.atualizar_votacao(ctx.guild, proposta_id)

        except discord.HTTPException:

            LOG.warning('Não foi possível atualizar painel da votação #%s', proposta_id)

        await ctx.reply(f'⚖️ Votação #{proposta_id} encerrada: **{results["yes"]} favoráveis** e **{results["no"]} contrários**. Resultado consultivo.', mention_author=False)

    @commands.command(name='beneficiosajuda')

    @commands.guild_only()

    @commands.has_guild_permissions(manage_guild=True)

    async def ajuda(self, ctx: commands.Context):

        await ctx.reply('**👑 Benefícios Royal — Administração**\n'

            '`!painelbeneficios #canal` — publica o painel.\n'

            '`!criareventoofc 2026-11-01T20:00Z #canal Nome | detalhes` — abre inscrições.\n'

            '`!votacaoroyal 12 #canal` — publica manualmente uma proposta pendente.\n'

            '`!encerrarvotacaoroyal 12` — encerra e apresenta resultado.\n'

            'Novas propostas são publicadas automaticamente no canal do painel de benefícios.\n'

            f'Canal para análise de indicações/propostas: `ROYAL_BENEFICIOS_ADMIN_CHANNEL_ID` (atual: {ADMIN_CHANNEL_ID or "não configurado"}).',

            mention_author=False)

async def setup(bot: commands.Bot):

    await bot.add_cog(BeneficiosRoyal(bot))
