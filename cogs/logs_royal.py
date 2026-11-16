# -*- coding: utf-8 -*-
"""Auditoria e painel !logs — Família Royal.

Requer: discord.py >= 2.6; PostgreSQL via bot.pool (asyncpg).
O main.py atual já carrega cogs/*.py automaticamente.

Comandos (apenas prefixo):
  !configurarlogs #registros #relatorios   (administrador)
  !logs                                   (no canal de painéis)
  !logs @membro                           (histórico envolvendo o membro)

Canais: #registros recebe ocorrências; #relatorios recebe alertas críticos.
Por segurança, !logs só funciona no canal de painéis ID 1571744772652269588.
Interações também são validadas nesse canal.

Variáveis opcionais:
  ROYAL_LOGS_STAFF_ROLE_IDS=111,222       (cargos autorizados a consultar)
  ROYAL_LOGS_RETENTION_DAYS=90            (0 desativa expiração)
  ROYAL_LOGS_STORE_CONTENT=0              (1 guarda trechos de mensagens)
  ROYAL_LOGS_CORRELATE_DELETIONS=0        (1 pesquisa autoria provável; mais chamadas à API)

Notas:
- Não captura histórico anterior à instalação.
- Não identifica com certeza o executor de TODA exclusão de mensagem.
- Para eventos auditáveis, exige permissão Ver Registro de Auditoria.
- Não substitui o sistema de logs preexistente; desative outro coletor
  duplicado se houver para evitar mensagens repetidas.
- Os botões do painel expiram após 10 minutos. Use !logs para abrir outro.
- O conteúdo original de mensagens fica desativado por padrão.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord.ext import commands, tasks

LOG = logging.getLogger('royal.logs')
COLOR_GOLD = discord.Colour.from_rgb(204, 162, 79)
COLOR_RED = discord.Colour.from_rgb(218, 65, 78)
COLOR_BLUE = discord.Colour.from_rgb(85, 150, 227)
PANEL_CHANNEL_ID = 1571744772652269588
PAGE_SIZE = 5
AUDIT_WINDOW_SECONDS = 20
# Pequena espera + tentativas limitadas para auditorias que chegam após o evento.
AUDIT_WAIT_SECONDS = 0.75
AUDIT_RETRIES = 3
MISSING = object()
ACTION_NAMES = {
    'ban': 'Banimento aplicado',
    'unban': 'Banimento removido',
    'kick': 'Expulsão de membro',
    'timeout_apply': 'Timeout aplicado',
    'timeout_change': 'Timeout alterado',
    'timeout_remove': 'Timeout removido',
    'timeout_expire': 'Timeout expirado',
    'message_delete': 'Mensagem excluída',
    'message_edit': 'Mensagem editada',
    'message_bulk_delete': 'Exclusão em massa',
    'member_join': 'Entrada de membro',
    'member_leave': 'Saída de membro',
    'role_added': 'Cargo atribuído',
    'role_removed': 'Cargo removido',
    'role_create': 'Cargo criado',
    'role_delete': 'Cargo excluído',
    'role_update': 'Cargo atualizado',
    'role_permissions': 'Permissões de cargo alteradas',
    'channel_create': 'Canal criado',
    'channel_delete': 'Canal excluído',
    'channel_update': 'Canal atualizado',
    'nickname_update': 'Apelido atualizado',
}

def action_name(action: str) -> str:
    return ACTION_NAMES.get(action, action.replace('_', ' ').capitalize())

def same_audit_value(observed: Any, expected: Any) -> bool:
    """Valida mudanças do audit log; compara datas com pequena tolerância."""
    if observed is MISSING or expected is MISSING:
        return False
    if isinstance(observed, datetime) and isinstance(expected, datetime):
        return abs((observed - expected).total_seconds()) <= 2.0
    if hasattr(observed, 'value') and hasattr(expected, 'value'):
        return observed.value == expected.value
    return observed == expected

CATEGORIES = {
    'todos': '📚 Todos',
    'mensagens': '📨 Mensagens',
    'moderacao': '🛡️ Moderação',
    'cargos': '🎭 Cargos',
    'membros': '👥 Membros',
    'administracao': '⚙️ Administração',
}
CRITICAL_ACTIONS = {
    'ban', 'kick', 'channel_delete', 'role_delete',
    'role_permissions', 'timeout_apply', 'timeout_change', 'timeout_remove',
}


def event_target(action: str, target_id: int | None,
                 channel_id: int | None, details: dict[str, Any]) -> str:
    """Diferencia pessoas, cargos e canais: não exibe canal como menção de usuário."""
    if target_id:
        return format_user(target_id)
    if action.startswith('role_') or action == 'role_permissions':
        role_id = details.get('role_id')
        role_name = details.get('cargo')
        if role_id and action != 'role_delete':
            return f'<@&{int(role_id)}> (`{int(role_id)}`)'
        if role_name:
            return safe(role_name, 100)
    if action.startswith('channel_'):
        name = details.get('canal')
        if channel_id:
            return f'<#{channel_id}>'
        if name:
            return f'#{safe(name, 80)}'
    if action in ('message_edit', 'message_delete', 'message_bulk_delete') and channel_id:
        return f'<#{channel_id}>'
    return 'Não disponível'


def audit_status(actor_id: int | None, details: dict[str, Any]) -> str:
    if actor_id is None:
        return 'Executor não confirmado'
    if details.get('audit_entry_id'):
        return 'Identificado no registro de auditoria'
    if details.get('fonte') == 'auditoria do Discord':
        return 'Correlacionado com auditoria do Discord'
    return 'Registrado pelo sistema'


def build_notification(*, item_id: int, category: str, action: str, summary: str,
                       actor_id: int | None, target_id: int | None,
                       channel_id: int | None, details: dict[str, Any],
                       created_at: datetime, alert: bool) -> discord.ui.LayoutView:
    """Duas apresentações independentes, com mesma informação e hierarquia visual."""
    view = discord.ui.LayoutView(timeout=None)
    box = discord.ui.Container(accent_colour=COLOR_RED if alert else COLOR_BLUE)
    titulo = '🚨 ALERTA ADMINISTRATIVO' if alert else '📋 REGISTRO DE AUDITORIA'
    categoria = CATEGORIES.get(category, category)
    occurrence = action_name(action)
    target = event_target(action, target_id, channel_id, details)
    stamp = int(created_at.timestamp())
    box.add_item(discord.ui.TextDisplay(
        f'## {titulo}\n-# FAMÍLIA ROYAL  •  OCORRÊNCIA `#{item_id:05d}`'
    ))
    box.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    if alert:
        # Campos na ordem solicitada, distribuídos para melhor leitura no celular.
        box.add_item(discord.ui.TextDisplay(
            f'**🏛️ Categoria:** {categoria}\n'
            f'**🚓 Ocorrência:** {safe(occurrence, 100)}'
        ))
        box.add_item(discord.ui.TextDisplay(
            f'**📄 Descrição:**\n> {safe(summary, 620)}'
        ))
        box.add_item(discord.ui.TextDisplay(
            f'**⚙️ Executor:** {format_user(actor_id) if actor_id else "Não confirmado"}\n'
            f'**🎯 Alvo:** {target}'
        ))
    else:
        box.add_item(discord.ui.TextDisplay(
            f'**📁 Categoria:** {categoria}\n'
            f'**🧾 Evento:** {safe(occurrence, 100)}'
        ))
        box.add_item(discord.ui.TextDisplay(
            f'**📝 Descrição:**\n> {safe(summary, 620)}'
        ))
        box.add_item(discord.ui.TextDisplay(
            f'**👤 Responsável:** {format_user(actor_id) if actor_id else "Não confirmado"}\n'
            f'**🎯 Alvo:** {target}'
        ))
    box.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    if channel_id:
        box.add_item(discord.ui.TextDisplay(f'**📍 Canal relacionado:** {format_channel(channel_id)}'))
    box.add_item(discord.ui.TextDisplay(
        f'🕒 <t:{stamp}:f>  •  {safe(audit_status(actor_id, details), 110)}\n'
        f'-# 🔎 Histórico e detalhes em <#{PANEL_CHANNEL_ID}> com `!logs`.'
    ))
    view.add_item(box)
    return view


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))


def safe(value: Any, limit: int = 350) -> str:
    value = str(value if value is not None else 'Não informado')
    value = discord.utils.escape_markdown(value.replace('@', '@\u200b'))
    return value[:limit] + ('…' if len(value) > limit else '')


def format_user(user_id: int | None) -> str:
    return f'<@{user_id}> (`{user_id}`)' if user_id else 'Não identificado'


def format_channel(channel_id: int | None) -> str:
    return f'<#{channel_id}>' if channel_id else 'Não informado'


def allowed(member: discord.Member) -> bool:
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    role_ids = set()
    for part in os.getenv('ROYAL_LOGS_STAFF_ROLE_IDS', '').split(','):
        if part.strip().isdigit():
            role_ids.add(int(part.strip()))
    return bool(role_ids.intersection(role.id for role in member.roles))


def matched_name(guild: discord.Guild, keyword: str) -> discord.TextChannel | None:
    channels = guild.text_channels
    exact = [ch for ch in channels if normalize(ch.name) == keyword]
    if exact:
        return exact[0]
    suffix = [ch for ch in channels if normalize(ch.name).endswith(keyword)]
    return suffix[0] if len(suffix) == 1 else None


def _intenv(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


async def respond_error(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class FilterMemberModal(discord.ui.Modal):
    def __init__(self, parent: 'LogsHistoryView'):
        super().__init__(title='Filtrar histórico por membro', timeout=180)
        self.parent_view = parent
        self.member_id_field = discord.ui.TextInput(
            label='ID ou menção do membro (vazio = todos)',
            placeholder='123456789012345678',
            required=False,
            default=str(parent.member_id) if parent.member_id else '',
            max_length=30,
        )
        self.add_item(self.member_id_field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        parent = self.parent_view
        if not await parent.validate(interaction):
            return
        raw = str(self.member_id_field).strip()
        found = re.fullmatch(r'(?:<@!?)?(\d{15,22})>?', raw) if raw else None
        if raw and not found:
            await interaction.response.send_message('❌ Informe um ID ou menção válida.', ephemeral=True)
            return
        member_id = int(found.group(1)) if found else None
        await parent.navigate(interaction, member_id=member_id, page=0)


class CategorySelect(discord.ui.Select):
    def __init__(self, parent: 'LogsHistoryView'):
        self.parent_view = parent
        super().__init__(
            placeholder='Filtrar categoria de logs',
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=label, value=key, default=key == parent.category)
                     for key, label in CATEGORIES.items()],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if await self.parent_view.validate(interaction):
            await self.parent_view.navigate(interaction, category=self.values[0], page=0)


class PeriodSelect(discord.ui.Select):
    def __init__(self, parent: 'LogsHistoryView'):
        self.parent_view = parent
        super().__init__(
            placeholder='Período da pesquisa',
            options=[discord.SelectOption(label=f'Últimos {d} dias' if d > 1 else 'Últimas 24 horas',
                                          value=str(d), default=d == parent.days)
                     for d in (1, 7, 30)],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if await self.parent_view.validate(interaction):
            await self.parent_view.navigate(interaction, days=int(self.values[0]), page=0)


class EventSelect(discord.ui.Select):
    def __init__(self, parent: 'LogsHistoryView', records: list[Any]):
        self.parent_view = parent
        options = []
        for record in records:
            title = action_name(str(record['action']))
            options.append(discord.SelectOption(
                label=f'#{record["id"]} • {title}'[:100],
                description=str(record['summary'])[:95],
                value=str(record['id']),
            ))
        super().__init__(placeholder='Abrir detalhes de uma ocorrência', options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.parent_view.validate(interaction):
            return
        await interaction.response.defer()
        try:
            details_view = await LogsDetailView.create(self.parent_view, int(self.values[0]))
            if details_view is None:
                await interaction.followup.send('Registro não localizado.', ephemeral=True)
                return
            message = self.parent_view.panel_message or interaction.message
            if message is None:
                raise RuntimeError('Mensagem do painel não disponível')
            await message.edit(view=details_view, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            LOG.exception('Falha ao abrir detalhes de logs')
            await interaction.followup.send('❌ Falha ao consultar o registro.', ephemeral=True)


class LogsHistoryView(discord.ui.LayoutView):
    def __init__(
        self, cog: 'LogsRoyal', *, guild_id: int, category: str, days: int,
        member_id: int | None, page: int, window_end: datetime,
        records: list[Any], total: int, invoker_id: int,
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.category = category
        self.days = days
        self.member_id = member_id
        self.page = page
        self.window_end = window_end
        self.invoker_id = invoker_id
        self.total = total
        self.panel_message: discord.Message | None = None
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        container = discord.ui.Container(accent_colour=COLOR_GOLD)
        container.add_item(discord.ui.TextDisplay('## 👑 CENTRAL DE AUDITORIA — FAMÍLIA ROYAL'))
        container.add_item(discord.ui.TextDisplay(
            f'**Categoria:** {CATEGORIES[category]}  •  **Período:** {days} dia(s)\n'
            f'**Membro:** {format_user(member_id) if member_id else "Todos"}\n'
            f'**Registros encontrados:** **{total}**  •  **Página:** **{page + 1}/{pages}**'
        ))
        container.add_item(discord.ui.Separator())
        if records:
            for row in records:
                when = int(row['created_at'].timestamp())
                title = action_name(str(row['action'])).upper()
                container.add_item(discord.ui.TextDisplay(
                    f'**`#{row["id"]}` • {safe(title, 80)}** — <t:{when}:f>\n'
                    f'{safe(row["summary"], 310)}\n'
                    f'-# {CATEGORIES.get(row["category"], row["category"])} • '
                    f'Responsável: {format_user(row["actor_id"])}'
                ))
        else:
            container.add_item(discord.ui.TextDisplay('Nenhuma ocorrência encontrada para este filtro.'))

        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.ActionRow(CategorySelect(self)))
        container.add_item(discord.ui.ActionRow(PeriodSelect(self)))
        if records:
            container.add_item(discord.ui.ActionRow(EventSelect(self, records)))

        prev = discord.ui.Button(label='Anterior', emoji='◀️', disabled=page <= 0)
        nxt = discord.ui.Button(label='Próxima', emoji='▶️', disabled=page + 1 >= pages)
        filter_member = discord.ui.Button(label='Filtrar membro', emoji='👤')
        refresh = discord.ui.Button(label='Atualizar', emoji='🔄')

        async def go_prev(interaction: discord.Interaction):
            if await self.validate(interaction):
                await self.navigate(interaction, page=self.page - 1)

        async def go_next(interaction: discord.Interaction):
            if await self.validate(interaction):
                await self.navigate(interaction, page=self.page + 1)

        async def go_member(interaction: discord.Interaction):
            if await self.validate(interaction):
                await interaction.response.send_modal(FilterMemberModal(self))

        async def go_refresh(interaction: discord.Interaction):
            if await self.validate(interaction):
                await self.navigate(interaction, page=0, window_end=datetime.now(timezone.utc))

        prev.callback = go_prev
        nxt.callback = go_next
        filter_member.callback = go_member
        refresh.callback = go_refresh
        container.add_item(discord.ui.ActionRow(prev, nxt, filter_member, refresh))
        container.add_item(discord.ui.TextDisplay(
            '-# 🔒 Painel administrativo exclusivo deste canal • Histórico PostgreSQL.'
        ))
        self.add_item(container)

    @classmethod
    async def create(
        cls, cog: 'LogsRoyal', *, guild_id: int, invoker_id: int,
        category: str = 'todos', days: int = 7, member_id: int | None = None,
        page: int = 0, window_end: datetime | None = None,
    ) -> 'LogsHistoryView':
        window_end = window_end or datetime.now(timezone.utc)
        total, records = await cog.fetch_history(guild_id, category, days, member_id, page, window_end)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        corrected_page = min(max(0, page), pages - 1)
        if corrected_page != page:
            page = corrected_page
            total, records = await cog.fetch_history(guild_id, category, days, member_id, page, window_end)
        return cls(cog, guild_id=guild_id, category=category, days=days,
                   member_id=member_id, page=page, window_end=window_end,
                   records=records, total=total, invoker_id=invoker_id)

    async def validate(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if (not interaction.guild or interaction.guild.id != self.guild_id
                or interaction.channel_id != PANEL_CHANNEL_ID
                or not isinstance(member, discord.Member) or not allowed(member)):
            await respond_error(interaction, '🔒 Você não tem acesso a esta consulta.')
            return False
        if member.id != self.invoker_id:
            await respond_error(interaction, '🔒 Abra seu próprio painel com `!logs`.')
            return False
        return True

    async def navigate(self, interaction: discord.Interaction, **changes: Any) -> None:
        args = dict(
            guild_id=self.guild_id, invoker_id=self.invoker_id,
            category=self.category, days=self.days,
            member_id=self.member_id, page=self.page, window_end=self.window_end,
        )
        args.update(changes)
        modal = interaction.type == discord.InteractionType.modal_submit
        if modal:
            # Modal tem resposta própria: editar a resposta original NÃO edita
            # necessariamente a mensagem do painel.
            await interaction.response.defer(ephemeral=True, thinking=True)
        else:
            await interaction.response.defer()
        try:
            new_view = await type(self).create(self.cog, **args)
            message = self.panel_message or interaction.message
            if message is None:
                raise RuntimeError('Mensagem do painel não disponível')
            await message.edit(view=new_view, allowed_mentions=discord.AllowedMentions.none())
            new_view.panel_message = message
            if modal:
                await interaction.edit_original_response(content='✅ Filtro aplicado no painel de auditoria.')
        except Exception:
            LOG.exception('Falha na navegação do painel de auditoria')
            if modal:
                await interaction.edit_original_response(content='❌ Não foi possível atualizar o painel.')
            else:
                await interaction.followup.send('❌ Não foi possível atualizar o painel.', ephemeral=True)


class LogsDetailView(discord.ui.LayoutView):
    def __init__(self, source: LogsHistoryView, item: Any):
        super().__init__(timeout=600)
        self.source = source
        details = item['details']
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except (TypeError, ValueError):
                details = {'dados': str(details)}
        extra = json.dumps(details, ensure_ascii=False, indent=2, default=str)
        extra = extra.replace('```', "'''", 10)
        extra = extra[:2300] + ('\n… (dados truncados)' if len(extra) > 2300 else '')
        stamp = int(item['created_at'].timestamp())
        target = event_target(item['action'], item['target_id'], item['channel_id'], details)

        box = discord.ui.Container(accent_colour=COLOR_GOLD)
        box.add_item(discord.ui.TextDisplay(f'## 📑 DETALHES DO REGISTRO #{item["id"]}'))
        box.add_item(discord.ui.TextDisplay(
            f'**Categoria:** {CATEGORIES.get(item["category"], item["category"])}\n'
            f'**Ação:** {safe(action_name(item["action"]))}\n'
            f'**Responsável:** {format_user(item["actor_id"])}\n'
            f'**Membro/objeto afetado:** {target}\n'
            f'**Canal:** {format_channel(item["channel_id"])}\n'
            f'**Horário:** <t:{stamp}:F>\n'
            f'**Resumo:** {safe(item["summary"], 500)}'
        ))
        box.add_item(discord.ui.Separator())
        box.add_item(discord.ui.TextDisplay(f'**Metadados da ocorrência**\n```json\n{extra}\n```'))
        back = discord.ui.Button(label='Voltar ao histórico', emoji='◀️')

        async def go_back(interaction: discord.Interaction):
            if await self.source.validate(interaction):
                await self.source.navigate(interaction)
        back.callback = go_back
        box.add_item(discord.ui.ActionRow(back))
        self.add_item(box)

    @classmethod
    async def create(cls, source: LogsHistoryView, event_id: int) -> 'LogsDetailView | None':
        item = await source.cog.get_event(source.guild_id, event_id)
        if item is None:
            return None
        # Revalida filtros para que o detalhe não contorne a janela da consulta.
        if not (source.window_end - timedelta(days=source.days) <= item['created_at'] <= source.window_end):
            return None
        if source.category != 'todos' and item['category'] != source.category:
            return None
        if source.member_id and source.member_id not in (item['actor_id'], item['target_id']):
            return None
        return cls(source, item)


class LogsRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ready = False
        self.channels_cache: dict[int, tuple[int | None, int | None]] = {}
        self.retention = _intenv('ROYAL_LOGS_RETENTION_DAYS', 90)
        self.store_content = os.getenv('ROYAL_LOGS_STORE_CONTENT', '0') == '1'
        self._audit_lookup_locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        pool = getattr(self.bot, 'pool', None)
        if pool is None:
            LOG.error('PostgreSQL indisponível: logs não inicializados (bot.pool não existe)')
            return
        try:
            async with pool.acquire() as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS royal_audit_settings (
                        guild_id BIGINT PRIMARY KEY,
                        registros_channel_id BIGINT,
                        relatorios_channel_id BIGINT
                    )
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS royal_audit_events (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        category TEXT NOT NULL,
                        action TEXT NOT NULL,
                        actor_id BIGINT,
                        target_id BIGINT,
                        channel_id BIGINT,
                        summary TEXT NOT NULL,
                        details JSONB NOT NULL DEFAULT '{}'::jsonb,
                        dedupe_key TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                ''')
                await db.execute('''
                    CREATE UNIQUE INDEX IF NOT EXISTS royal_audit_guild_dedupe
                    ON royal_audit_events (guild_id, dedupe_key)
                    WHERE dedupe_key IS NOT NULL
                ''')
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS royal_audit_history_idx
                    ON royal_audit_events (guild_id, created_at DESC, id DESC)
                ''')
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS royal_audit_category_idx
                    ON royal_audit_events (guild_id, category, created_at DESC)
                ''')
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS royal_audit_actor_idx
                    ON royal_audit_events (guild_id, actor_id, created_at DESC)
                ''')
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS royal_audit_target_idx
                    ON royal_audit_events (guild_id, target_id, created_at DESC)
                ''')
            self.ready = True
            if self.retention > 0:
                self.prune_events.start()
            LOG.info('Sistema Royal Logs V2 inicializado')
        except Exception:
            LOG.exception('Falha criando tabelas de auditoria')

    def cog_unload(self) -> None:
        if self.prune_events.is_running():
            self.prune_events.cancel()

    @tasks.loop(hours=24)
    async def prune_events(self):
        if self.ready and self.retention > 0:
            try:
                await self.bot.pool.execute(
                    'DELETE FROM royal_audit_events WHERE created_at < $1',
                    datetime.now(timezone.utc) - timedelta(days=self.retention),
                )
            except Exception:
                LOG.exception('Falha na expiração de logs')

    @prune_events.before_loop
    async def before_prune(self):
        await self.bot.wait_until_ready()

    async def get_channels(self, guild: discord.Guild) -> tuple[discord.TextChannel | None, discord.TextChannel | None]:
        ids = self.channels_cache.get(guild.id)
        if ids is None:
            ids = (None, None)
            if self.ready:
                try:
                    record = await self.bot.pool.fetchrow(
                        'SELECT registros_channel_id, relatorios_channel_id FROM royal_audit_settings WHERE guild_id=$1',
                        guild.id,
                    )
                    if record:
                        ids = (record['registros_channel_id'], record['relatorios_channel_id'])
                except Exception:
                    LOG.exception('Erro consultando configuração de canais')
            self.channels_cache[guild.id] = ids
        registros = guild.get_channel(ids[0]) if ids[0] else matched_name(guild, 'registros')
        relatorios = guild.get_channel(ids[1]) if ids[1] else matched_name(guild, 'relatorios')
        return (registros if isinstance(registros, discord.TextChannel) else None,
                relatorios if isinstance(relatorios, discord.TextChannel) else None)

    @staticmethod
    def can_send(guild: discord.Guild, channel: discord.TextChannel) -> bool:
        me = guild.me
        if me is None:
            return False
        perms = channel.permissions_for(me)
        return perms.view_channel and perms.send_messages

    async def fetch_history(self, guild_id: int, category: str, days: int,
                            member_id: int | None, page: int, window_end: datetime):
        if not self.ready:
            raise RuntimeError('PostgreSQL indisponível')
        if category not in CATEGORIES or days not in (1, 7, 30):
            raise ValueError('Filtro inválido')
        args: list[Any] = [guild_id, window_end - timedelta(days=days), window_end]
        clauses = ['guild_id=$1', 'created_at >= $2', 'created_at <= $3']
        if category != 'todos':
            args.append(category)
            clauses.append(f'category=${len(args)}')
        if member_id:
            args.append(member_id)
            clauses.append(f'(actor_id=${len(args)} OR target_id=${len(args)})')
        where = ' AND '.join(clauses)
        page = max(0, page)
        async with self.bot.pool.acquire() as db:
            total = await db.fetchval(f'SELECT COUNT(*) FROM royal_audit_events WHERE {where}', *args)
            offset_pos = len(args) + 1
            rows = await db.fetch(
                f'SELECT id, category, action, actor_id, summary, created_at '
                f'FROM royal_audit_events WHERE {where} '
                f'ORDER BY created_at DESC, id DESC LIMIT {PAGE_SIZE} OFFSET ${offset_pos}',
                *args, page * PAGE_SIZE,
            )
        return int(total), rows

    async def get_event(self, guild_id: int, event_id: int):
        if not self.ready:
            return None
        return await self.bot.pool.fetchrow(
            'SELECT * FROM royal_audit_events WHERE guild_id=$1 AND id=$2', guild_id, event_id,
        )

    async def event(self, guild: discord.Guild, *, category: str, action: str,
                    summary: str, actor_id: int | None = None,
                    target_id: int | None = None, channel_id: int | None = None,
                    details: dict[str, Any] | None = None, dedupe_key: str | None = None,
                    critical: bool = False) -> None:
        if not self.ready or category not in CATEGORIES or category == 'todos':
            return
        reg, rel = await self.get_channels(guild)
        if category == 'mensagens' and channel_id and channel_id in (
            PANEL_CHANNEL_ID, getattr(reg, 'id', None), getattr(rel, 'id', None)
        ):
            return  # Impede loops de mensagens no painel e nos canais de auditoria.

        try:
            inserted = await self.bot.pool.fetchrow('''
                INSERT INTO royal_audit_events
                    (guild_id, category, action, actor_id, target_id,
                     channel_id, summary, details, dedupe_key)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
                ON CONFLICT (guild_id, dedupe_key) WHERE dedupe_key IS NOT NULL
                DO NOTHING RETURNING id, created_at
            ''', guild.id, category, action, actor_id, target_id, channel_id,
                summary[:1200], json.dumps(details or {}, ensure_ascii=False, default=str), dedupe_key)
        except Exception:
            LOG.exception('Erro persistindo log %s', action)
            return
        if not inserted:
            return
        item_id = inserted['id']
        created_at = inserted['created_at']
        is_critical = critical or action in CRITICAL_ACTIONS
        sent_channel_ids: set[int] = set()
        for destination in (reg, rel if is_critical else None):
            if not destination or destination.id in sent_channel_ids:
                continue
            sent_channel_ids.add(destination.id)
            if not self.can_send(guild, destination):
                LOG.warning('Sem permissão de envio no canal %s', destination.id)
                continue
            try:
                view = build_notification(
                    item_id=item_id, category=category, action=action,
                    summary=summary, actor_id=actor_id, target_id=target_id,
                    channel_id=channel_id, details=details or {},
                    created_at=created_at, alert=(destination == rel),
                )
                await destination.send(view=view, allowed_mentions=discord.AllowedMentions.none())
            except (discord.HTTPException, discord.Forbidden):
                LOG.exception('Não foi possível publicar evento %s no canal %s', item_id, destination.id)

    async def audit(self, guild: discord.Guild, action: discord.AuditLogAction,
                    *, target_id: int | None = None,
                    channel_id: int | None = None) -> tuple[int | None, str | None, int | None]:
        """Busca executor pela ação + alvo, retornando o ID oficial da auditoria."""
        entry = await self._find_audit(guild, action, target_id=target_id,
                                       channel_id=channel_id)
        return ((getattr(entry.user, 'id', None), entry.reason, entry.id)
                if entry else (None, None, None))

    async def _find_audit(
        self, guild: discord.Guild, action: discord.AuditLogAction, *,
        target_id: int | None = None, channel_id: int | None = None,
        extra_id: int | None = None,
        change_field: str | None = None, expected_after: Any = MISSING,
        expected_before: Any = MISSING,
        role_added: set[int] | None = None,
        role_removed: set[int] | None = None,
    ) -> discord.AuditLogEntry | None:
        """Somente associa executor quando a entrada de auditoria é compatível.

        Consulta algumas vezes porque o audit log do Discord chega em atraso.
        Ações de message_delete ainda NÃO comprovam qual mensagem foi deletada.
        """
        me = guild.me
        if me is None or not me.guild_permissions.view_audit_log:
            return None
        lock = self._audit_lookup_locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            for attempt in range(AUDIT_RETRIES):
                await asyncio.sleep(AUDIT_WAIT_SECONDS if attempt == 0 else 1.0)
                now = datetime.now(timezone.utc)
                try:
                    async for entry in guild.audit_logs(limit=30, action=action):
                        age = (now - entry.created_at).total_seconds()
                        if not -3.0 <= age <= AUDIT_WINDOW_SECONDS:
                            continue
                        if target_id is not None and getattr(entry.target, 'id', None) != target_id:
                            continue
                        if channel_id is not None:
                            extra_channel = getattr(getattr(entry, 'extra', None), 'channel', None)
                            if getattr(extra_channel, 'id', None) != channel_id:
                                continue
                        if extra_id is not None and getattr(entry.extra, 'id', None) != extra_id:
                            continue
                        if change_field:
                            got_after = getattr(entry.after, change_field, MISSING)
                            if not same_audit_value(got_after, expected_after):
                                continue
                            if expected_before is not MISSING:
                                got_before = getattr(entry.before, change_field, MISSING)
                                if got_before is not MISSING and not same_audit_value(got_before, expected_before):
                                    continue
                        if role_added is not None or role_removed is not None:
                            actual_add = {r.id for r in getattr(entry.after, 'roles', ()) or ()}
                            actual_remove = {r.id for r in getattr(entry.before, 'roles', ()) or ()}
                            if not (role_added or set()).issubset(actual_add):
                                continue
                            if not (role_removed or set()).issubset(actual_remove):
                                continue
                        return entry
                except (discord.Forbidden, discord.HTTPException):
                    LOG.warning('Não foi possível ler auditoria do servidor %s', guild.id)
                    return None
        return None

    async def audit_change(
        self, guild: discord.Guild, action: discord.AuditLogAction,
        *, target_id: int, field: str, after: Any, before: Any = MISSING,
    ) -> tuple[int | None, str | None, int | None]:
        """Executores identificados apenas quando há evidência do campo alterado."""
        entry = await self._find_audit(
            guild, action, target_id=target_id, change_field=field,
            expected_after=after, expected_before=before,
        )
        if not entry:
            return None, None, None
        return getattr(entry.user, 'id', None), entry.reason, entry.id

    async def audit_roles(
        self, guild: discord.Guild, member_id: int, *,
        added: set[int], removed: set[int],
    ) -> tuple[int | None, str | None, int | None]:
        """Confere quais cargos foram adicionados/removidos no registro oficial."""
        entry = await self._find_audit(
            guild, discord.AuditLogAction.member_role_update,
            target_id=member_id, role_added=added, role_removed=removed,
        )
        if entry is None:
            return None, None, None
        return getattr(entry.user, 'id', None), entry.reason, entry.id

    @commands.command(name='configurarlogs')
    @commands.guild_only()
    async def configure_channels(self, ctx: commands.Context,
                                 registros: discord.TextChannel,
                                 relatorios: discord.TextChannel):
        """!configurarlogs #registros #relatorios"""
        if not ctx.author.guild_permissions.administrator:
            await ctx.send('🔒 Somente administradores podem alterar os canais.')
            return
        if registros.id == relatorios.id:
            await ctx.send('❌ Escolha canais diferentes para registros e relatórios.')
            return
        if PANEL_CHANNEL_ID in (registros.id, relatorios.id):
            await ctx.send('❌ O canal do painel deve ser separado dos canais de notificação.')
            return
        if not self.ready:
            await ctx.send('❌ PostgreSQL indisponível. Verifique DATABASE_URL.')
            return
        await self.bot.pool.execute('''
            INSERT INTO royal_audit_settings
              (guild_id, registros_channel_id, relatorios_channel_id)
            VALUES ($1,$2,$3)
            ON CONFLICT (guild_id) DO UPDATE SET
              registros_channel_id = EXCLUDED.registros_channel_id,
              relatorios_channel_id = EXCLUDED.relatorios_channel_id
        ''', ctx.guild.id, registros.id, relatorios.id)
        self.channels_cache[ctx.guild.id] = (registros.id, relatorios.id)
        warning = ''
        if registros.permissions_for(ctx.guild.default_role).view_channel or relatorios.permissions_for(ctx.guild.default_role).view_channel:
            warning = '\n⚠️ Pelo menos um canal está visível para @everyone. Restrinja o acesso manualmente.'
        await ctx.send(f'✅ Auditoria configurada: registros {registros.mention} e relatórios {relatorios.mention}.{warning}',
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name='logs')
    @commands.guild_only()
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def logs(self, ctx: commands.Context, member: str | None = None):
        """!logs ou !logs @membro (padrão: todos os eventos dos últimos 7 dias)."""
        if not isinstance(ctx.author, discord.Member) or not allowed(ctx.author):
            await ctx.send('🔒 Apenas administradores autorizados podem consultar os logs.', delete_after=15)
            return
        if ctx.channel.id != PANEL_CHANNEL_ID:
            await ctx.send(f'🔒 O comando `!logs` funciona exclusivamente em <#{PANEL_CHANNEL_ID}>.',
                           delete_after=20, allowed_mentions=discord.AllowedMentions.none())
            return
        if ctx.channel.permissions_for(ctx.guild.default_role).view_channel:
            await ctx.send('🔒 O canal do painel está visível para @everyone. Restrinja seu acesso antes de consultar o histórico.',
                           allowed_mentions=discord.AllowedMentions.none())
            return
        if not self.ready:
            await ctx.send('❌ Histórico indisponível: PostgreSQL não conectado.')
            return
        member_id = None
        if member:
            found = re.fullmatch(r'(?:<@!?)?(\d{15,22})>?', member.strip())
            if not found:
                await ctx.send('❌ Utilize `!logs`, `!logs @membro` ou `!logs ID`.')
                return
            member_id = int(found.group(1))
        try:
            view = await LogsHistoryView.create(
                self, guild_id=ctx.guild.id, invoker_id=ctx.author.id,
                member_id=member_id, category='todos', days=7,
            )
            view.panel_message = await ctx.send(
                view=view, allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            LOG.exception('Falha abrindo painel !logs')
            await ctx.send('❌ Não foi possível consultar o histórico no PostgreSQL.')

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if not payload.guild_id or payload.channel_id == PANEL_CHANNEL_ID:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        cached = payload.cached_message
        owner_id = cached.author.id if cached else None
        details: dict[str, Any] = {'message_id': payload.message_id, 'autor_em_cache': bool(cached)}
        if cached and self.store_content and cached.content:
            details['conteudo'] = cached.content[:1000]
        # A auditoria de exclusão NÃO traz o ID da mensagem: nunca atribuir
        # definitivamente autoria com base apenas em uma ocorrência próxima.
        possible_id = None
        if owner_id and os.getenv('ROYAL_LOGS_CORRELATE_DELETIONS', '0') == '1':
            possible_id, _, possible_audit_id = await self.audit(
                guild, discord.AuditLogAction.message_delete,
                target_id=owner_id, channel_id=payload.channel_id,
            )
            if possible_id:
                details['possivel_executor_id'] = possible_id
                details['confianca'] = 'Possível correspondência; auditoria não vincula ID da mensagem'
        await self.event(
            guild, category='mensagens', action='message_delete',
            summary=f'Mensagem {payload.message_id} excluída; autor: {owner_id or "não disponível"}. '
                    'Executor não confirmado.',
            target_id=owner_id, channel_id=payload.channel_id,
            details=details, dedupe_key=f'message_delete:{payload.message_id}',
        )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if not guild:
            return
        ids = sorted(payload.message_ids)
        digest = hashlib.sha256(','.join(map(str, ids)).encode()).hexdigest()[:24]
        actor, reason, audit_id = await self.audit(guild, discord.AuditLogAction.message_bulk_delete,
                                         target_id=payload.channel_id)
        await self.event(
            guild, category='mensagens', action='message_bulk_delete',
            summary=f'{len(ids)} mensagens removidas em massa do canal {payload.channel_id}.',
            actor_id=actor, channel_id=payload.channel_id,
            details={'quantidade': len(ids), 'ids_amostra': ids[:30], 'motivo': reason,
                     'audit_entry_id': audit_id},
            dedupe_key=f'message_bulk:{payload.channel_id}:{digest}',
            critical=len(ids) >= 20,
        )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if not payload.guild_id or payload.channel_id == PANEL_CHANNEL_ID or 'content' not in payload.data:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        old = payload.cached_message
        new_text = payload.data.get('content', '')
        if old and old.content == new_text:
            return
        author_id = old.author.id if old else None
        if not author_id and isinstance(payload.data.get('author'), dict):
            raw = payload.data['author'].get('id')
            author_id = int(raw) if str(raw).isdigit() else None
        details: dict[str, Any] = {'message_id': payload.message_id, 'texto_anterior_em_cache': bool(old)}
        if self.store_content:
            details['antes'] = old.content[:1000] if old else None
            details['depois'] = str(new_text)[:1000]
        await self.event(guild, category='mensagens', action='message_edit',
                         summary=f'Mensagem {payload.message_id} editada.',
                         actor_id=author_id, target_id=author_id, channel_id=payload.channel_id,
                         details=details)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.event(member.guild, category='membros', action='member_join',
                         summary=f'{member} entrou no servidor.', target_id=member.id,
                         details={'conta_criada': member.created_at.isoformat()},
                         dedupe_key=f'member_join:{member.id}:{int(member.joined_at.timestamp()) if member.joined_at else int(datetime.now(timezone.utc).timestamp())}')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        kick_entry = await self._find_audit(
            member.guild, discord.AuditLogAction.kick, target_id=member.id
        )
        if kick_entry:
            await self.event(
                member.guild, category='moderacao', action='kick',
                summary=f'{member} foi expulso do servidor.',
                actor_id=getattr(kick_entry.user, 'id', None), target_id=member.id,
                details={'motivo': kick_entry.reason, 'fonte': 'auditoria do Discord',
                         'audit_entry_id': kick_entry.id},
                dedupe_key=f'kick:{kick_entry.id}', critical=True,
            )
            return
        # Banimento também dispara remoção: o listener on_member_ban publica o ban.
        ban_entry = await self._find_audit(
            member.guild, discord.AuditLogAction.ban, target_id=member.id
        )
        if ban_entry:
            return
        await self.event(
            member.guild, category='membros', action='member_leave',
            summary=f'{member} saiu ou foi removido do servidor (motivo não confirmado).',
            target_id=member.id,
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        actor, reason, audit_id = await self.audit(guild, discord.AuditLogAction.ban, target_id=user.id)
        await self.event(guild, category='moderacao', action='ban',
                         summary=f'{user} foi banido.', actor_id=actor, target_id=user.id,
                         details={'motivo': reason, 'audit_entry_id': audit_id},
                         dedupe_key=f'ban:{audit_id}' if audit_id else None, critical=True)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        actor, reason, audit_id = await self.audit(guild, discord.AuditLogAction.unban, target_id=user.id)
        await self.event(guild, category='moderacao', action='unban',
                         summary=f'{user} foi desbanido.', actor_id=actor, target_id=user.id,
                         details={'motivo': reason, 'audit_entry_id': audit_id},
                         dedupe_key=f'unban:{audit_id}' if audit_id else None)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild = after.guild
        old_role_ids = {r.id for r in before.roles}
        new_role_ids = {r.id for r in after.roles}
        add_ids = new_role_ids - old_role_ids
        remove_ids = old_role_ids - new_role_ids
        if add_ids or remove_ids:
            actor, reason, audit_id = await self.audit_roles(
                guild, after.id, added=add_ids, removed=remove_ids
            )
            for role_id in sorted(add_ids):
                await self.event(
                    guild, category='cargos', action='role_added',
                    summary=f'Cargo {role_id} atribuído a {after}.',
                    actor_id=actor, target_id=after.id,
                    details={'role_id': role_id, 'motivo': reason,
                             'operacao': 'adicionar', 'audit_entry_id': audit_id},
                    dedupe_key=f'role_add:{audit_id}:{role_id}' if audit_id else None,
                )
            for role_id in sorted(remove_ids):
                await self.event(
                    guild, category='cargos', action='role_removed',
                    summary=f'Cargo {role_id} removido de {after}.',
                    actor_id=actor, target_id=after.id,
                    details={'role_id': role_id, 'motivo': reason,
                             'operacao': 'remover', 'audit_entry_id': audit_id},
                    dedupe_key=f'role_remove:{audit_id}:{role_id}' if audit_id else None,
                )
        if before.nick != after.nick:
            actor, reason, audit_id = await self.audit_change(
                guild, discord.AuditLogAction.member_update,
                target_id=after.id, field='nick', after=after.nick,
                before=before.nick,
            )
            await self.event(
                guild, category='membros', action='nickname_update',
                summary=f'Apelido de {after} alterado.',
                actor_id=actor, target_id=after.id,
                details={'antes': before.nick, 'depois': after.nick,
                         'motivo': reason, 'audit_entry_id': audit_id},
                dedupe_key=f'nick:{audit_id}' if audit_id else None,
            )
        if before.timed_out_until != after.timed_out_until:
            now = datetime.now(timezone.utc)
            old_until = before.timed_out_until
            new_until = after.timed_out_until
            old_active = old_until is not None and old_until > now
            new_active = new_until is not None and new_until > now
            if new_active:
                action = 'timeout_change' if old_active else 'timeout_apply'
            elif old_active:
                action = 'timeout_remove'
            else:
                # O prazo já venceu: não presumir que um moderador removeu.
                action = 'timeout_expire'
            actor = reason = audit_id = None
            if action != 'timeout_expire':
                actor, reason, audit_id = await self.audit_change(
                    guild, discord.AuditLogAction.member_update,
                    target_id=after.id, field='timed_out_until',
                    after=new_until, before=old_until,
                )
            changes = {
                'timeout_apply': 'aplicado',
                'timeout_change': 'alterado',
                'timeout_remove': 'removido',
                'timeout_expire': 'expirado automaticamente',
            }
            summary = f'Timeout de {after} {changes[action]}.'
            if new_active:
                summary += f' Término previsto: {new_until.astimezone(timezone.utc):%d/%m/%Y %H:%M} UTC.'
            details = {
                'antes': old_until,
                'depois': new_until,
                'motivo': reason,
                'audit_entry_id': audit_id,
                'fonte': 'auditoria do Discord' if audit_id else 'evento Discord sem executor confirmado',
                'executor_confirmado': bool(audit_id and actor),
            }
            # Valor antes/depois + membro diferencia eventos seguidos sem autoria confirmada.
            fingerprint = hashlib.sha256(
                f'{after.id}:{old_until!s}:{new_until!s}:{action}'.encode()
            ).hexdigest()[:24]
            await self.event(
                guild, category='moderacao', action=action,
                summary=summary, actor_id=actor, target_id=after.id,
                details=details,
                dedupe_key=(f'timeout:{audit_id}' if audit_id
                        else f'timeout_change:{fingerprint}:{int(now.timestamp()) // 2}'),
                critical=action in ('timeout_apply', 'timeout_change', 'timeout_remove'),
            )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        actor, reason, audit_id = await self.audit(channel.guild, discord.AuditLogAction.channel_create,
                                         target_id=channel.id)
        await self.event(channel.guild, category='administracao', action='channel_create',
                         summary=f'Canal {channel.name} criado.', actor_id=actor,
                         channel_id=channel.id,
                         details={'canal': channel.name, 'id': channel.id, 'motivo': reason,
                                  'audit_entry_id': audit_id},
                         dedupe_key=f'channel_create:{audit_id}' if audit_id else None)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        actor, reason, audit_id = await self.audit(channel.guild, discord.AuditLogAction.channel_delete,
                                         target_id=channel.id)
        await self.event(channel.guild, category='administracao', action='channel_delete',
                         summary=f'Canal {channel.name} excluído.', actor_id=actor,
                         details={'canal': channel.name, 'id': channel.id, 'motivo': reason,
                                  'audit_entry_id': audit_id},
                         dedupe_key=f'channel_delete:{audit_id}' if audit_id else None,
                         critical=True)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel,
                                      after: discord.abc.GuildChannel):
        changes: dict[str, Any] = {}
        for attr in ('name', 'position', 'category_id', 'slowmode_delay', 'topic', 'nsfw'):
            old, new = getattr(before, attr, None), getattr(after, attr, None)
            if old != new:
                changes[attr] = {'antes': old, 'depois': new}
        if before.overwrites != after.overwrites:
            changes['permissoes'] = 'Permissões de canal alteradas'
        if not changes:
            return
        actor = reason = audit_id = None
        # Atualizações de sobrescrita são ações distintas de channel_update.
        if 'permissoes' in changes:
            b = {target.id: overwrite for target, overwrite in before.overwrites.items()}
            a = {target.id: overwrite for target, overwrite in after.overwrites.items()}
            altered = [rid for rid in b.keys() | a.keys() if b.get(rid) != a.get(rid)]
            if len(altered) == 1:
                rid = altered[0]
                audit_action = (discord.AuditLogAction.overwrite_create if rid not in b
                                else discord.AuditLogAction.overwrite_delete if rid not in a
                                else discord.AuditLogAction.overwrite_update)
                entry = await self._find_audit(
                    after.guild, audit_action, target_id=after.id, extra_id=rid,
                )
                # Correlaciona canal e cargo/membro correto, não só a hora do evento.
                if entry:
                    # Também confere o estado das permissões (quando disponível).
                    # Não atribuímos o executor usando somente um ID próximo no tempo.
                    overwrite = a.get(rid) if audit_action != discord.AuditLogAction.overwrite_delete else b.get(rid)
                    expected_allow, expected_deny = overwrite.pair()
                    source = entry.before if audit_action == discord.AuditLogAction.overwrite_delete else entry.after
                    got_allow = getattr(source, 'allow', MISSING)
                    got_deny = getattr(source, 'deny', MISSING)
                    if (got_allow is MISSING or got_deny is MISSING
                            or not same_audit_value(got_allow, expected_allow)
                            or not same_audit_value(got_deny, expected_deny)):
                        entry = None
                if entry:
                    actor = getattr(entry.user, 'id', None)
                    reason, audit_id = entry.reason, entry.id
                changes['alvo_permissao_id'] = rid
        else:
            for key in ('name', 'topic', 'slowmode_delay', 'nsfw', 'position'):
                if key in changes:
                    actor, reason, audit_id = await self.audit_change(
                        after.guild, discord.AuditLogAction.channel_update,
                        target_id=after.id, field=key,
                        after=getattr(after, key), before=getattr(before, key),
                    )
                    break
        await self.event(
            after.guild, category='administracao', action='channel_update',
            summary=f'Canal {after.name} alterado: {", ".join(k for k in changes if k != "alvo_permissao_id")}.',
            actor_id=actor, channel_id=after.id,
            details={'mudancas': changes, 'motivo': reason,
                     'audit_entry_id': audit_id, 'canal': after.name},
            dedupe_key=f'channel_update:{audit_id}' if audit_id else None,
            critical='permissoes' in changes,
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        actor, reason, audit_id = await self.audit(role.guild, discord.AuditLogAction.role_create,
                                         target_id=role.id)
        await self.event(role.guild, category='cargos', action='role_create',
                         summary=f'Cargo {role.name} criado.', actor_id=actor,
                         details={'role_id': role.id, 'cargo': role.name, 'motivo': reason,
                                  'audit_entry_id': audit_id},
                         dedupe_key=f'role_create:{audit_id}' if audit_id else None)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        actor, reason, audit_id = await self.audit(role.guild, discord.AuditLogAction.role_delete,
                                         target_id=role.id)
        await self.event(role.guild, category='cargos', action='role_delete',
                         summary=f'Cargo {role.name} excluído.', actor_id=actor,
                         details={'role_id': role.id, 'cargo': role.name, 'motivo': reason,
                                  'audit_entry_id': audit_id},
                         dedupe_key=f'role_delete:{audit_id}' if audit_id else None,
                         critical=True)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes: dict[str, Any] = {}
        for attr in ('name', 'hoist', 'mentionable', 'position'):
            old, new = getattr(before, attr), getattr(after, attr)
            if old != new:
                changes[attr] = {'antes': old, 'depois': new}
        if before.permissions.value != after.permissions.value:
            changes['permissoes'] = {'antes': before.permissions.value,
                                     'depois': after.permissions.value}
        if before.colour != after.colour:
            changes['cor'] = {'antes': str(before.colour), 'depois': str(after.colour)}
        if not changes:
            return
        actor = reason = audit_id = None
        key_map = {
            'permissoes': ('permissions', before.permissions, after.permissions),
            'name': ('name', before.name, after.name),
            'hoist': ('hoist', before.hoist, after.hoist),
            'mentionable': ('mentionable', before.mentionable, after.mentionable),
            'position': ('position', before.position, after.position),
            'cor': ('colour', before.colour, after.colour),
        }
        for change_key in key_map:
            if change_key in changes:
                field, old, new = key_map[change_key]
                actor, reason, audit_id = await self.audit_change(
                    after.guild, discord.AuditLogAction.role_update,
                    target_id=after.id, field=field, before=old, after=new,
                )
                break
        await self.event(
            after.guild, category='cargos',
            action='role_permissions' if 'permissoes' in changes else 'role_update',
            summary=f'Cargo {after.name} alterado: {", ".join(changes)}.',
            actor_id=actor,
            details={'role_id': after.id, 'cargo': after.name,
                     'mudancas': changes, 'motivo': reason, 'audit_entry_id': audit_id},
            dedupe_key=f'role_update:{audit_id}' if audit_id else None,
            critical='permissoes' in changes,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsRoyal(bot))
