"""Painéis nativos V2, snapshots PostgreSQL e navegação persistente de relatórios."""
import json
import logging
import math
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import discord

LOG = logging.getLogger('sants.relatorios.ui')
SCHEMA = '''CREATE TABLE IF NOT EXISTS sants_relatorio_paineis (
 id text PRIMARY KEY, guild_id bigint NOT NULL, canal_id bigint NOT NULL,
 criado_em timestamptz NOT NULL DEFAULT now(), dados jsonb NOT NULL
)'''
MARKER = 'DADOS_STAFF:'
PAGE_SIZE = 6


def staff_data(report):
    for line in report.splitlines():
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    return {'members': [], 'alerts': ['Este registro não possui os dados individuais da nova versão. Gere uma nova prévia.'], 'coverage': {}}


def chunks(text, limit=2400):
    result = []
    page = ''
    for line in (text or 'Nenhum registro nesta seção.').splitlines():
        while len(line) > limit:
            if page:
                result.append(page)
                page = ''
            result.append(line[:limit])
            line = line[limit:]
        if len(page) + len(line) + 1 > limit:
            result.append(page)
            page = ''
        page += line + '\n'
    if page or not result:
        result.append(page.strip() or 'Nenhum registro nesta seção.')
    return result


def safe_name(value):
    return discord.utils.escape_markdown(str(value).replace('@', '@\u200b'))[:70]


def member_line(member):
    last = member.get('last')
    recent = f'<t:{int(datetime.fromisoformat(last).timestamp())}:R>' if last else 'sem registro no período'
    def metric(key, source):
        count = member[key]
        status = member.get('coverage', {}).get(source, 'completa')
        return ('—' if not count else str(count) + '+') if status != 'completa' else str(count)
    return (f"> `👤` <@{int(member['id'])}>\n"
            f"> Painel **{metric('panel', 'painel')}** · Auditoria **{metric('audit', 'auditoria')}** · Mensagens **{metric('messages', 'mensagens')}**\n"
            f"> Última atividade observada: {recent}")


def technical_sections(report):
    result = {'updates': [], 'deploys': [], 'alerts': [], 'next': [], 'full': []}
    section = 'updates'
    for line in report.splitlines():
        if line.startswith(MARKER):
            continue
        result['full'].append(line)
        if line.startswith('## GitHub'):
            section = 'updates'
        elif line.startswith('GitHub Actions') or line.startswith('## Railway'):
            section = 'deploys'
        elif line.startswith('## Painel web') or line.startswith('## Registros dos canais'):
            section = 'alerts'
        elif line.startswith('## Pendências'):
            section = 'next'
        result[section].append(line)
        if section != 'alerts' and any(word in line.lower() for word in ('indisponív', 'não configurad', 'com falha', 'linhas suspeitas', 'parcial')):
            result['alerts'].append(line)
    return {key: '\n'.join(value) for key, value in result.items()}


async def save_snapshot(bot, channel, report, summary, start, end, prefix):
    pool = getattr(bot, 'pool', None)
    if pool is None:
        raise ValueError('PostgreSQL indisponível; o painel interativo precisa do banco para guardar suas consultas.')
    await pool.execute(SCHEMA)
    data = {'kind': 'admin' if prefix == 'RELATORIO_ADMIN' else 'tech',
            'report': report, 'summary': summary, 'start': start.isoformat(), 'end': end.isoformat(),
            'prefix': prefix, 'guild_id': channel.guild.id, 'channel_id': channel.id}
    if data['kind'] == 'admin':
        data['staff'] = staff_data(report)
    sid = uuid.uuid4().hex
    await pool.execute('INSERT INTO sants_relatorio_paineis(id,guild_id,canal_id,dados) VALUES($1,$2,$3,$4::jsonb)',
                       sid, channel.guild.id, channel.id, json.dumps(data, ensure_ascii=False))
    return sid, data


async def load_snapshot(bot, sid):
    pool = getattr(bot, 'pool', None)
    if pool is None:
        raise ValueError('Banco temporariamente indisponível. Tente novamente mais tarde.')
    row = await pool.fetchrow('SELECT dados FROM sants_relatorio_paineis WHERE id=$1', sid)
    if not row:
        raise ValueError('Relatório não encontrado. Gere uma nova prévia.')
    data = row['dados']
    return json.loads(data) if isinstance(data, str) else dict(data)


def authorized(interaction, data):
    if not interaction.guild or interaction.guild.id != data['guild_id'] or interaction.channel_id != data['channel_id']:
        return False
    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    perms = interaction.channel.permissions_for(user)
    if not perms.view_channel:
        return False
    if user.guild_permissions.administrator or user.guild_permissions.manage_guild:
        return True
    configured = {int(os.getenv('RELATORIO_ADMIN_STAFF_CARGO_ID', '1560385636819796059')),
                  int(os.getenv('RELATORIO_CARGO_ID', '1560385636819796059')),
                  int(os.getenv('RELATORIO_ADMIN_CARGO_ID', '1560385636819796059'))}
    configured.update(int(v.strip()) for v in os.getenv('RELATORIO_LEITURA_CARGOS', '').split(',') if v.strip().isdigit())
    return any(role.id in configured for role in user.roles)


class ReportButton(discord.ui.DynamicItem[discord.ui.Button], template=r'sants:report:(?P<sid>[a-f0-9]{32}):(?P<section>[a-z]+)'):
    def __init__(self, sid, section, label='Consultar', emoji=None):
        self.sid = sid
        self.section = section
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary,
                                           custom_id=f'sants:report:{sid}:{section}'))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match['sid'], match['section'], item.label or 'Consultar')

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            data = await load_snapshot(interaction.client, self.sid)
            if not authorized(interaction, data):
                await interaction.followup.send('Você não tem acesso a este relatório.', ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                return
            view = DetailView(data, self.section, interaction.user.id)
            await interaction.followup.send(view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except Exception as exc:
            LOG.warning('Falha na consulta do relatório: %s', type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else 'Não foi possível abrir o relatório. Tente novamente.'
            await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


def register(bot):
    if not getattr(bot, '_sants_report_ui_registered', False):
        bot.add_dynamic_items(ReportButton)
        bot._sants_report_ui_registered = True


def public_panel(data, sid):
    view = discord.ui.LayoutView(timeout=None)
    body = []
    files = []
    banner_url = os.getenv(data['prefix'] + '_BANNER_URL', '').strip()
    banner = Path(__file__).resolve().parent.parent / 'assets' / 'relatorios-cuphead.png'
    if banner_url.startswith('https://'):
        body.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner_url)))
    elif banner.is_file():
        files.append(discord.File(banner, filename='banner-relatorios.png'))
        body.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media='attachment://banner-relatorios.png')))
    body.append(discord.ui.TextDisplay(data['summary']))
    body.append(discord.ui.Separator())
    if data['kind'] == 'admin':
        members = data.get('staff', {}).get('members', [])
        roster = '\n\n'.join(member_line(member) for member in members[:12]) or 'Nenhum membro confirmado.'
        body.append(discord.ui.TextDisplay('### 👥 Membros da staff\n' + roster))
        if len(members) > 12:
            body.append(discord.ui.TextDisplay(f'-# Mostrando 12 de {len(members)}. Use Equipe completa para ver todos.'))
        body.append(discord.ui.TextDisplay('-# —: fonte indisponível/não coletada ou parcial sem registros. +: contagem parcial. Sem registro não comprova inatividade.'))
        choices = [('team', 'Equipe completa', '👥'), ('actions', 'Ações por membro', '🛡️'), ('quiet', 'Sem registros', '🔎'), ('alerts', 'Cobertura e atenção', '⚠️')]
    else:
        choices = [('updates', 'Atualizações', '🛠️'), ('deploys', 'Deploys', '🚀'), ('alerts', 'Erros e atenção', '⚠️'), ('next', 'Prioridades', '🎯'), ('full', 'Relatório completo', '📋')]
    row = discord.ui.ActionRow()
    for section, label, emoji in choices:
        row.add_item(ReportButton(sid, section, label, emoji))
    body.append(row)
    view.add_item(discord.ui.Container(*body, accent_colour=0xB98B57 if data['kind'] == 'admin' else 0x5B87C4))
    return view, files


class DetailView(discord.ui.LayoutView):
    def __init__(self, data, section, owner_id, *, page=0, member_id=None, detail_page=0):
        super().__init__(timeout=900)
        self.data = data
        self.section = section
        self.owner_id = owner_id
        self.page = max(0, page)
        self.member_id = member_id
        self.detail_page = max(0, detail_page)
        self.render()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or not authorized(interaction, self.data):
            await interaction.response.send_message('Você não tem acesso a esta consulta.', ephemeral=True)
            return False
        return True

    async def on_error(self, interaction, error, item):
        LOG.warning('Falha na navegação do relatório: %s', type(error).__name__)
        if not interaction.response.is_done():
            await interaction.response.send_message('Falha ao navegar. Abra novamente pelo painel.', ephemeral=True)

    def button(self, label, **changes):
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
        async def callback(interaction):
            values = dict(page=self.page, member_id=self.member_id, detail_page=self.detail_page)
            values.update(changes)
            view = DetailView(self.data, self.section, self.owner_id, **values)
            await interaction.response.edit_message(view=view, allowed_mentions=discord.AllowedMentions.none())
        button.callback = callback
        return button

    def render(self):
        body = []
        if self.data['kind'] != 'admin':
            pages = chunks(technical_sections(self.data['report']).get(self.section, 'Seção não encontrada.'))
            self.page = min(self.page, len(pages)-1)
            body.append(discord.ui.TextDisplay(f'## 📋 Consulta técnica\n{pages[self.page]}\n-# Página {self.page+1}/{len(pages)} • Dados do relatório salvo.'))
            row = discord.ui.ActionRow()
            if self.page:
                row.add_item(self.button('Anterior', page=self.page-1))
            if self.page+1 < len(pages):
                row.add_item(self.button('Próxima', page=self.page+1))
            if row.children:
                body.append(row)
        else:
            staff = self.data.get('staff', {})
            members = staff.get('members', [])
            if self.section == 'quiet':
                members = [m for m in members if not (m['panel'] or m['audit'] or m['messages'])]
            if self.section == 'alerts':
                warnings = staff.get('alerts', [])
                coverage = '\n'.join(f"> **{k}:** {v}" for k, v in staff.get('coverage', {}).items())
                text = '\n'.join('> `⚠️` ' + warning for warning in warnings) or 'Nenhuma limitação adicional registrada.'
                text += '\n\n' + coverage + '\n\nSem registro não significa inatividade. Mensagens não medem desempenho. Ações do painel e da auditoria podem se sobrepor.'
                pages = chunks(text)
                self.page = min(self.page, len(pages)-1)
                body.append(discord.ui.TextDisplay('## ⚠️ Fontes e cobertura\n' + pages[self.page] + f'\n-# Página {self.page+1}/{len(pages)}'))
                row = discord.ui.ActionRow()
                if self.page:
                    row.add_item(self.button('Anterior',page=self.page-1))
                if self.page+1 < len(pages):
                    row.add_item(self.button('Próxima',page=self.page+1))
                if row.children:
                    body.append(row)
            else:
                page_count = max(1, math.ceil(len(members)/PAGE_SIZE))
                self.page = min(self.page, page_count-1)
                batch = members[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
                heading = '## 🔎 Sem registros na cobertura disponível\n' if self.section == 'quiet' else '## 👥 Equipe completa\n'
                body.append(discord.ui.TextDisplay(heading + ('\n\n'.join(member_line(m) for m in batch) or 'Nenhum membro confirmado.')
                    + f'\n-# Página {self.page+1}/{page_count} • {len(members)} membros nesta consulta. Ausência de registro não prova inatividade.'))
                if batch:
                    select = discord.ui.Select(placeholder='Consultar ações e dados de um membro', options=[discord.SelectOption(
                        label=str(m['name'])[:100], value=str(m['id']), description=f"Painel {m['panel']} | Auditoria {m['audit']} | Mensagens {m['messages']}"[:100]) for m in batch])
                    async def choose(interaction):
                        view = DetailView(self.data, self.section, self.owner_id, page=self.page, member_id=int(select.values[0]))
                        await interaction.response.edit_message(view=view, allowed_mentions=discord.AllowedMentions.none())
                    select.callback = choose
                    body.append(discord.ui.ActionRow(select))
                nav = discord.ui.ActionRow()
                if self.page:
                    nav.add_item(self.button('Membros anteriores', page=self.page-1, member_id=None, detail_page=0))
                if self.page+1 < page_count:
                    nav.add_item(self.button('Mais membros', page=self.page+1, member_id=None, detail_page=0))
                if nav.children:
                    body.append(nav)
                chosen = next((m for m in members if m['id'] == self.member_id), None)
                if chosen:
                    text = f"### 🛡️ {safe_name(chosen['name'])} · <@{chosen['id']}>\n"
                    kinds = chosen.get('action_types', {})
                    text += ('**Tipos de ação registrados:** ' + ' · '.join(f'{safe_name(k)}: {v}' for k, v in kinds.items())[:400] + '\n\n') if kinds else '**Ações:** nenhuma identificada na cobertura disponível.\n\n'
                    text += '\n'.join(chosen.get('details', []) or ['Nenhum registro nas fontes consultadas. Isso não comprova inatividade.'])
                    pages = chunks(text, limit=1700)
                    self.detail_page = min(self.detail_page,len(pages)-1)
                    body.append(discord.ui.Separator())
                    body.append(discord.ui.TextDisplay(pages[self.detail_page] + f'\n-# Registros {self.detail_page+1}/{len(pages)} • Cobertura no botão Atenção do painel.'))
                    nav = discord.ui.ActionRow()
                    if self.detail_page:
                        nav.add_item(self.button('Registros anteriores',detail_page=self.detail_page-1))
                    if self.detail_page+1 < len(pages):
                        nav.add_item(self.button('Mais registros',detail_page=self.detail_page+1))
                    if nav.children:
                        body.append(nav)
        self.add_item(discord.ui.Container(*body, accent_colour=0xB98B57))
