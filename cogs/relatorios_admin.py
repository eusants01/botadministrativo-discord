"""Atividade administrativa por membro atual da staff; fontes de leitura."""
import asyncio
import json
import logging
import os
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from utils.relatorios_ui import save_snapshot, public_panel, register, staff_data
from cogs.relatorios import Relatorios, TZ, UTC, clean, window

LOG = logging.getLogger('sants.relatorios_admin')
LABELS = {
    'ban': 'banimento', 'unban': 'remoção de banimento', 'kick': 'expulsão',
    'member_update': 'alteração de membro', 'member_role_update': 'alteração de cargos',
    'message_delete': 'exclusão de mensagens', 'message_bulk_delete': 'exclusão em lote',
    'channel_create': 'criação de canal', 'channel_update': 'alteração de canal',
    'channel_delete': 'exclusão de canal', 'role_create': 'criação de cargo',
    'role_update': 'alteração de cargo', 'role_delete': 'exclusão de cargo',
    'timeout': 'silenciamento', 'cargo_add': 'cargo adicionado', 'cargo_remove': 'cargo removido',
    'aviso': 'aviso', 'post': 'publicação', 'historia': 'registro de história',
}


def admin_message(report, start, end, *, ping=False, preview=False, role_id=None):
    rows = report.splitlines()
    summary = next((r[7:] for r in rows if r.startswith('RESUMO:')), 'Coleta incompleta.')
    alerts = [r[7:] for r in rows if r.startswith('ALERTA:')]
    data = staff_data(report)
    members = data.get('members', [])
    coverage = data.get('coverage', {})
    if members:
        def total(key, source):
            value = sum(m[key] for m in members)
            status = coverage.get(source, 'completa')
            return str(value) if status == 'completa' else (f'{value}+ (parcial)' if value else 'não confirmado')
        observed = sum(bool(m['panel'] or m['audit'] or m['messages']) for m in members)
        summary = (f"{len(members)} no cargo • {observed} com registros • {len(members)-observed} sem registros na cobertura\n"
                   f"Painel: {total('panel', 'painel')} • Auditoria: {total('audit', 'auditoria')} • Mensagens: {total('messages', 'mensagens')}")
    attention = clean(' • '.join(alerts) or 'Consulte a ficha de cada membro pelos botões abaixo.')[:240]
    return ((f'<@&{role_id}>\n' if ping and role_id else '')
        + ('## PRÉVIA ADMINISTRATIVA\n' if preview else '## RELATÓRIO ADMINISTRATIVO\n')
        + f'-# {start.astimezone(TZ):%d/%m %H:%M} → {end.astimezone(TZ):%d/%m %H:%M} • Brasília\n\n'
        + '> `🛡️` **Visão geral**\n> ' + clean(summary)[:240] + '\n\n'
        + '> `⚠️` **Atenção**\n> ' + attention + '\n\n'
        + '-# Consulte todos os membros e suas ações nos botões. Mensagens não medem desempenho.')


def activity_channels(guild, destination_id):
    setting = os.getenv('RELATORIO_ADMIN_ATIVIDADE_CANAIS', '*').strip()
    excluded = {destination_id,
        int(os.getenv('RELATORIO_CANAL_ID', '1561964628207210516')),
        int(os.getenv('RELATORIO_ADMIN_CANAL_ID', '1561964860676247633'))}
    if setting.lower() in ('*', 'todos', 'all'):
        selected = []
        unavailable = 0
        for channel in guild.text_channels:
            if channel.id in excluded:
                continue
            perms = channel.permissions_for(guild.me)
            if perms.view_channel and perms.read_message_history:
                selected.append(str(channel.id))
            else:
                unavailable += 1
        return selected, unavailable
    return list(dict.fromkeys(x.strip() for x in setting.split(',')
        if x.strip() and (not x.strip().isdigit() or int(x.strip()) not in excluded))), 0


class RelatoriosAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engine = Relatorios(bot, prefix='RELATORIO_ADMIN', default_channel='1561964860676247633',
                                 builder=self.build, formatter=admin_message)

    async def cog_load(self):
        register(self.bot)
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    async def build(self, start, end, channel):
        guild = channel.guild
        role_id = int(os.getenv('RELATORIO_ADMIN_STAFF_CARGO_ID', '1560385636819796059'))
        role = guild.get_role(role_id)
        if not role or role.is_default():
            raise ValueError('Cargo de staff não encontrado. Confira RELATORIO_ADMIN_STAFF_CARGO_ID.')
        if not guild.chunked:
            await asyncio.wait_for(guild.chunk(cache=True), timeout=60)
        staff = {m.id: m for m in role.members if not m.bot}
        lines = ['RELATÓRIO ADMINISTRATIVO — FAMÍLIA SANT’S',
                 f'Período: {start.astimezone(TZ):%d/%m/%Y %H:%M} até {end.astimezone(TZ):%d/%m/%Y %H:%M} (Brasília)',
                 'Escopo: membros que possuem o cargo de staff no momento da coleta. Não reconstrói cargos antigos.',
                 'Fontes separadas: não somar registros do painel e auditoria como ações únicas, pois podem se referir à mesma ação.']
        panel = Counter()
        audits = Counter()
        messages = Counter()
        last = {}
        details = {uid: [] for uid in staff}
        recent_messages = defaultdict(lambda: deque(maxlen=5))
        alerts = []
        coverage = {'painel': 'completa', 'auditoria': 'completa', 'mensagens': 'completa'}
        action_types = {uid: Counter() for uid in staff}
        def remember(uid, ts, detail):
            if uid not in staff:
                return
            if uid not in last or ts > last[uid]:
                last[uid] = ts
            if detail.startswith('Mensagem |'):
                recent_messages[uid].append(detail)
            else:
                details[uid].append(detail)
        if not staff:
            alerts.append('Nenhum membro humano encontrado no cargo selecionado.')
        pool = getattr(self.bot, 'pool', None)
        if pool and staff:
            try:
                records = await pool.fetch('''SELECT ts, ator_id, acao, alvo_id FROM audit
                    WHERE ts >= $1 AND ts < $2 AND ator_id = ANY($3::bigint[])
                    ORDER BY ts LIMIT 5001''', start, end, list(staff))
                if len(records) > 5000:
                    coverage['painel'] = 'parcial'
                    alerts.append('Painel: limite de 5.000 registros; cobertura parcial.')
                for row in records[:5000]:
                    uid = row['ator_id']
                    panel[uid] += 1
                    label = LABELS.get(row['acao'], row['acao'])
                    action_types[uid]['Painel: ' + label] += 1
                    remember(uid, row['ts'], f"Painel | {row['ts'].astimezone(TZ):%d/%m %H:%M} | {label} | alvo {row['alvo_id'] or 'não informado'}")
            except Exception:
                LOG.warning('Leitura de auditoria do painel indisponível.', exc_info=True)
                coverage['painel'] = 'parcial' if sum(panel.values()) else 'indisponível'
                alerts.append('Auditoria do painel ' + coverage['painel'] + '; não interpretar contagens como totais confirmados.')
        elif not pool:
            coverage['painel'] = 'indisponível'
            alerts.append('Banco indisponível: auditoria do painel não consultada.')
        if guild.me.guild_permissions.view_audit_log:
            try:
                count = 0
                async for entry in guild.audit_logs(limit=5001, after=start, before=end, oldest_first=True):
                    count += 1
                    if count > 5000:
                        coverage['auditoria'] = 'parcial'
                        alerts.append('Discord: limite de 5.000 entradas; cobertura parcial.')
                        break
                    uid = entry.user_id
                    # Ações executadas pelo bot não são atribuídas por adivinhação a um moderador.
                    if uid not in staff:
                        continue
                    audits[uid] += 1
                    name = getattr(entry.action, 'name', str(entry.action))
                    label = LABELS.get(name, name.replace('_', ' '))
                    action_types[uid]['Discord: ' + label] += 1
                    target = getattr(entry.target, 'id', None)
                    remember(uid, entry.created_at, f'Discord | {entry.created_at.astimezone(TZ):%d/%m %H:%M} | {label} | alvo {target or "não informado"}')
            except Exception:
                LOG.warning('Leitura do registro de auditoria Discord indisponível.', exc_info=True)
                coverage['auditoria'] = 'parcial' if sum(audits.values()) else 'indisponível'
                alerts.append('Auditoria do Discord ' + coverage['auditoria'] + '; os valores exibidos são somente os registros coletados.')
        else:
            coverage['auditoria'] = 'indisponível'
            alerts.append('Falta a permissão Ver registro de auditoria no Discord.')
        selected, unavailable = activity_channels(guild, channel.id)
        if unavailable:
            coverage['mensagens'] = 'parcial'
            alerts.append(f'{unavailable} canais de texto sem acesso/histórico; atividade parcial.')
        if not selected:
            coverage['mensagens'] = 'não coletada'
            alerts.append('Nenhum canal de atividade disponível ou selecionado; mensagens não contabilizadas.')
        lines.append(f'Canais de texto selecionados para atividade: {len(selected)}. Canais dos relatórios excluídos.')
        for raw in selected:
            try:
                source = guild.get_channel(int(raw))
                if not isinstance(source, discord.TextChannel) or source.id == channel.id:
                    raise ValueError('Canal inválido ou igual ao destino.')
                count = 0
                async for msg in source.history(limit=5001, after=start, before=end, oldest_first=True):
                    count += 1
                    if count > 5000:
                        coverage['mensagens'] = 'parcial'
                        alerts.append(f'#{source.name}: limite de 5.000 mensagens; cobertura parcial.')
                        break
                    uid = msg.author.id
                    if uid in staff and not msg.author.bot:
                        messages[uid] += 1
                        # Só horário e canal, sem copiar o conteúdo das conversas.
                        remember(uid, msg.created_at, f'Mensagem | {msg.created_at.astimezone(TZ):%d/%m %H:%M} | #{source.name} | {msg.jump_url}')
            except Exception:
                coverage['mensagens'] = 'parcial'
                alerts.append(f'Canal de atividade {raw} não pôde ser consultado.')
        for uid in staff:
            details[uid].extend(recent_messages[uid])
        observed = sum(1 for uid in staff if panel[uid] or audits[uid] or messages[uid])
        lines.append(f'RESUMO:{len(staff)} membros • {observed} com registros • {sum(panel.values())} registros no painel • {sum(audits.values())} entradas Discord • {sum(messages.values())} mensagens.')
        for member in sorted(staff.values(), key=lambda m: m.display_name.casefold()):
            uid = member.id
            name = clean(member.display_name)
            lines.append(f'STAFF:{name} — painel: {panel[uid]} | Discord: {audits[uid]} | mensagens: {messages[uid]}')
        lines.extend('ALERTA:' + a for a in alerts)
        lines.append('\n## Ações e atividade por membro')
        for uid, member in staff.items():
            lines.append(f'\n{clean(member.display_name)} (ID {uid})')
            lines.append('Última atividade observada no período: ' + (last[uid].astimezone(TZ).strftime('%d/%m/%Y %H:%M') if uid in last else 'nenhum registro nas fontes consultadas.'))
            lines.extend(details[uid] or ['Nenhum registro encontrado na cobertura disponível; isso não comprova inatividade.'])
        lines.extend(['\n## Limites de interpretação',
            'Auditoria Discord conta entradas, não vítimas afetadas nem volume exato de ações.',
            'Ações de outros bots não são atribuídas ao staff sem um registro com autoria humana.',
            'Conversas excluídas, canais apagados, threads, mensagens privadas, voz e canais sem acesso/não selecionados não entram na coleta.',
            'Nenhum conteúdo de conversa é incluído. Contagens abrangem o período coletado; links mostram até as cinco mensagens mais recentes de cada membro. Atividade de mensagens e moderação são métricas distintas.',
            'Ausência de registros não comprova inatividade. Fontes podem ser parciais ou indisponíveis.'])
        payload = {'members': [], 'alerts': alerts, 'coverage': coverage}
        for member in sorted(staff.values(), key=lambda m: m.display_name.casefold()):
            uid = member.id
            payload['members'].append({'id': uid, 'name': clean(member.display_name),
                'panel': panel[uid], 'audit': audits[uid], 'messages': messages[uid],
                'last': last[uid].isoformat() if uid in last else None,
                'action_types': dict(action_types[uid]), 'details': details[uid], 'coverage': coverage})
        lines.append('DADOS_STAFF:' + json.dumps(payload, ensure_ascii=False))
        return clean('\n'.join(lines))

    @tasks.loop(minutes=1)
    async def tick(self):
        if os.getenv('RELATORIO_ADMIN_ATIVO', '').lower() not in ('1', 'true', 'sim'):
            return
        try:
            now = datetime.now(TZ)
            start, end = window(now, os.getenv('RELATORIO_ADMIN_HORARIO', '09:00'))
            if now < end:
                return
            async with self.engine.lock:
                channel = await self.engine.destination()
                if channel.id == int(os.getenv('RELATORIO_CANAL_ID', '1561964628207210516')):
                    raise ValueError('Escolha um canal diferente do relatório técnico.')
                await self.engine.publish(channel, start, end)
        except Exception:
            LOG.exception('Relatório administrativo não concluído.')

    @tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()

    @commands.command(name='relatorio_admin_teste')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def admin_test(self, ctx):
        try:
            channel = await self.engine.destination()
            if channel.id == int(os.getenv('RELATORIO_CANAL_ID', '1561964628207210516')):
                raise ValueError('Configure um canal administrativo diferente do canal técnico.')
            if ctx.channel.id != channel.id:
                await ctx.send('Execute no canal configurado em RELATORIO_ADMIN_CANAL_ID.', allowed_mentions=discord.AllowedMentions.none())
                return
            if self.engine.lock.locked():
                await ctx.send('> `⏳` Já existe um relatório administrativo em preparação.', allowed_mentions=discord.AllowedMentions.none())
                return
            async with self.engine.lock:
                await ctx.send('> `🛡️` Preparando o relatório administrativo...', allowed_mentions=discord.AllowedMentions.none())
                end = datetime.now(UTC)
                start = end - timedelta(days=1)
                report = await self.build(start, end, channel)
                summary = admin_message(report, start, end, preview=True)
                sid, data = await save_snapshot(self.bot, channel, report, summary, start, end, 'RELATORIO_ADMIN')
                view, files = public_panel(data, sid)
                await channel.send(view=view, files=files, allowed_mentions=discord.AllowedMentions.none())
        except ValueError as exc:
            await ctx.send('> `⚠️` ' + clean(str(exc)), allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            LOG.exception('Falha na prévia administrativa.')
            await ctx.send('> `⚠️` Falha ao preparar a prévia. Confira permissões e logs.', allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(RelatoriosAdmin(bot))
