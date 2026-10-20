"""Relatório diário somente leitura. Carregado automaticamente pelo main.py."""
import asyncio
import hashlib
import io
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord.ext import commands, tasks

LOG = logging.getLogger('sants.relatorios')
TZ = ZoneInfo('America/Sao_Paulo')
UTC = timezone.utc
SCHEMA = """
CREATE TABLE IF NOT EXISTS sants_relatorio_envios (
 canal_id bigint NOT NULL, dia date NOT NULL, estado text NOT NULL,
 conteudo text NOT NULL, mensagem_id bigint, PRIMARY KEY(canal_id, dia)
);
"""


def clean(value):
    value = str(value or '')
    for key, secret in os.environ.items():
        if any(word in key.upper() for word in ('TOKEN', 'SECRET', 'PASSWORD', 'WEBHOOK', 'DATABASE_URL')) and len(secret) > 5:
            value = value.replace(secret, '[OCULTO]')
    value = re.sub(r'https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S+', '[WEBHOOK]', value)
    value = re.sub(r'(?:postgres(?:ql)?|https?)://[^\s/@]+:[^\s/@]+@\S+', '[CREDENCIAL]', value)
    value = re.sub(r'(?i)(authorization|password|token|secret)\s*[:=]\s*\S+', r'\1=[OCULTO]', value)
    return value.replace('@', '@\u200b').replace('```', "'''")


STATUS_LABELS = {
    'success': 'bem-sucedidos', 'SUCCESS': 'bem-sucedidos',
    'failure': 'com falha', 'FAILED': 'com falha', 'CRASHED': 'interrompidos por falha',
    'timed_out': 'tempo esgotado', 'cancelled': 'cancelados',
    'in_progress': 'em execução', 'BUILDING': 'em construção',
    'DEPLOYING': 'em publicação', 'queued': 'na fila', 'QUEUED': 'na fila',
    'waiting': 'aguardando', 'WAITING': 'aguardando aprovação',
    'REMOVED': 'removidos', 'SKIPPED': 'ignorados', 'skipped': 'ignorados',
    'SLEEPING': 'em repouso', 'action_required': 'exigem ação',
}


def format_counts(counts):
    return ' • '.join(f"{count} {STATUS_LABELS.get(state, state)}" for state, count in counts.items()) or 'nenhum deploy criado no período.'


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)


def window(now, clock):
    hour, minute = map(int, clock.split(':'))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError('RELATORIO_HORARIO deve ser HH:MM.')
    end = now.astimezone(TZ).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return end - timedelta(days=1), end


def component_text(items):
    result = []
    for item in items:
        text = getattr(item, 'content', None)
        if isinstance(text, str):
            result.append(text)
        result.extend(component_text(getattr(item, 'children', None) or getattr(item, 'components', []) or []))
    return result


def report_message(report, start, end, *, ping=False, preview=False):
    """Resumo legível no chat; evidências completas permanecem no anexo."""
    groups = {'updates': [], 'deploys': [], 'errors': [], 'web': [], 'next': []}
    context = ''
    for line in report.splitlines():
        if line.startswith('## GitHub —') or line.startswith('## Railway —'):
            context = line.removeprefix('## ')
        elif line.startswith('## '):
            context = ''
        if line.startswith('Áreas alteradas') or re.match(r'^\d+ commits', line):
            groups['updates'].append((context + ': ' if context else '') + line)
        elif line.startswith(('GitHub Actions', 'Deploys criados', 'Último deploy')):
            groups['deploys'].append((context + ': ' if context else '') + line)
        elif line.startswith('Teste HTTP'):
            groups['web'].append(line)
        elif line.startswith('- P'):
            groups['next'].append(line[2:])
        elif any(word in line.lower() for word in ('indisponível', 'indisponíveis', 'não configurad', 'não foram verificados', 'linhas suspeitas', 'cobertura parcial', 'coleta parcial')):
            groups['errors'].append((context + ': ' if context else '') + line)
    def excerpt(key, fallback, limit=470):
        text = ' • '.join(groups[key]) or fallback
        text = clean(text).replace('\n', ' ')
        return text if len(text) <= limit else text[:limit-1] + '…'
    prefix = '@everyone\n' if ping else ''
    title = 'PRÉVIA DO RELATÓRIO' if preview else 'RELATÓRIO DIÁRIO'
    return (
        prefix + f"## 📊 {title} | FAMÍLIA SANT’S\n"
        + f"> `🗓️` **Período:** {start.astimezone(TZ):%d/%m %H:%M} até {end.astimezone(TZ):%d/%m %H:%M} • Brasília\n\n"
        + "Alta Gestão, este é o acompanhamento do nosso bot e do painel web, com os registros disponíveis e as próximas prioridades.\n\n"
        + "> `🛠️` **FUNCIONALIDADES E ATUALIZAÇÕES**\n> "
        + excerpt('updates', 'Alterações não confirmadas nas fontes consultadas. Confira a cobertura no anexo.') + '\n\n'
        + "> `🚀` **DEPLOYS E VERIFICAÇÕES**\n> "
        + excerpt('deploys', 'Não há resultados confirmados para exibir. Consulte as fontes e limitações no anexo.') + '\n\n'
        + "> `⚠️` **ERROS E PONTOS DE ATENÇÃO**\n> "
        + excerpt('errors', 'Nenhum alerta destacado na coleta. Isso não garante ausência de falhas.') + '\n\n'
        + "> `🌐` **PAINEL WEB**\n> "
        + excerpt('web', 'Sem resultado confirmado do teste HTTP nesta coleta.', 250) + '\n\n'
        + "> `🎯` **PRIORIDADES E SUGESTÕES**\n> "
        + excerpt('next', 'Revisar o relatório completo e validar as funcionalidades alteradas.', 500) + '\n\n'
        + "> `📎` **RELATÓRIO COMPLETO**\n> O arquivo anexado reúne commits, status, registros e links para investigação. Aprovação no GitHub Actions não comprova sucesso no Railway.\n\n"
        + '-# Família Sant’s • Acompanhamento técnico • Sugestões para avaliação da gestão.'
    )


class Relatorios(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        self.ready_db = False

    async def cog_load(self):
        self.tick.start()

    def cog_unload(self):
        self.tick.cancel()

    async def database(self):
        pool = getattr(self.bot, 'pool', None)
        if pool is None:
            raise RuntimeError('PostgreSQL indisponível; envio suspenso para preservar o controle diário.')
        if not self.ready_db:
            await pool.execute(SCHEMA)
            self.ready_db = True
        return pool

    async def destination(self):
        cid = int(os.getenv('RELATORIO_CANAL_ID', '1553834996488339547'))
        gid = int(os.getenv('GUILD_ID', '0'))
        channel = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != gid:
            raise ValueError('RELATORIO_CANAL_ID deve ser um canal de texto do GUILD_ID.')
        perms = channel.permissions_for(channel.guild.me)
        if not all((perms.view_channel, perms.send_messages, perms.attach_files, perms.read_message_history)):
            raise ValueError('Faltam permissões: Ver canal, Enviar mensagens, Anexar arquivos ou Ler histórico.')
        return channel

    async def request(self, session, url, **kwargs):
        async with session.request(kwargs.pop('method', 'GET'), url, **kwargs) as response:
            if response.status >= 400:
                raise RuntimeError(f'HTTP {response.status}; confira acesso, limites e credenciais.')
            data = await response.json()
            if isinstance(data, dict) and data.get('errors'):
                raise RuntimeError('A API GraphQL recusou a consulta; confira token e IDs.')
            return data

    async def github_list(self, session, repo, path, params, key=None):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'Sants-Daily-Report'}
        token = os.getenv('RELATORIO_GITHUB_TOKEN', '')
        if token:
            headers['Authorization'] = 'Bearer ' + token
        rows = []
        for page in range(1, 11):
            data = await self.request(session, f'https://api.github.com/repos/{repo}/{path}',
                                      headers=headers, params={**params, 'per_page': 100, 'page': page})
            batch = data[key] if key else data
            if not isinstance(batch, list):
                raise RuntimeError('Formato inesperado do GitHub.')
            rows.extend(batch)
            if len(batch) < 100:
                return rows, False
        return rows, True

    async def github(self, session, start, end, lines, priorities):
        repos = [r.strip() for r in os.getenv('RELATORIO_GITHUB_REPOS', '').split(',') if r.strip()]
        if not repos:
            lines.append('GitHub não configurado: alterações e workflows não verificados.')
            priorities.append('Configurar as fontes do GitHub para acompanhar bot e painel.')
        for repo in repos:
            if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
                lines.append('Repositório inválido; use dono/repositorio.')
                continue
            lines.append('\n## GitHub — ' + repo)
            branch = os.getenv('RELATORIO_GITHUB_BRANCH', 'main')
            try:
                commits, partial = await self.github_list(session, repo, 'commits', {
                    'since': start.isoformat(), 'until': end.isoformat(), 'sha': branch})
                lines.append(f'{len(commits)} commits na branch {branch}.' + (' Coleta limitada a 1.000; resultado parcial.' if partial else ''))
                for item in commits:
                    msg = (item['commit'].get('message') or 'Sem descrição').splitlines()[0]
                    lines.append(f"- {item['sha'][:7]}: {msg}\n  {item['html_url']}")
                areas = Counter()
                for item in commits[:30]:
                    try:
                        detail = await self.request(session, f"https://api.github.com/repos/{repo}/commits/{item['sha']}",
                            headers={'Accept': 'application/vnd.github+json', **({'Authorization': 'Bearer ' + os.getenv('RELATORIO_GITHUB_TOKEN')} if os.getenv('RELATORIO_GITHUB_TOKEN') else {})})
                        files = detail.get('files', [])
                        for file in files:
                            name = file['filename']
                            area = 'Painel web' if name.endswith('.html') or name.startswith('assets/') or name in ('painel.py', 'portal_ext.py') else ('Bot / ' + name[5:-3] if name.startswith('cogs/') and name.endswith('.py') else 'Infraestrutura e utilitários')
                            areas[area] += 1
                        if len(files) >= 300:
                            lines.append('Lista de arquivos deste commit pode estar parcial (300 arquivos).')
                    except Exception:
                        lines.append('Não foi possível classificar os arquivos do commit ' + item['sha'][:7])
                lines.append('Áreas alteradas (ocorrências de arquivos nos primeiros 30 commits): ' + (str(dict(areas)) if areas else 'nenhuma identificada.'))
                if len(commits) > 30:
                    lines.append('Classificação de áreas limitada aos primeiros 30 commits.')
                lines.append('As descrições acima vêm dos commits; não confirmam funcionamento nem publicação.')
            except Exception as exc:
                lines.append('Commits indisponíveis: ' + str(exc))
                priorities.append('Restabelecer a leitura dos commits no GitHub.')
            try:
                runs, partial = await self.github_list(session, repo, 'actions/runs', {
                    'created': start.isoformat() + '..' + end.isoformat(), 'branch': branch}, 'workflow_runs')
                counts = Counter(r.get('conclusion') or r['status'] for r in runs)
                lines.append('GitHub Actions (CI, não comprova deploy Railway): ' + (format_counts(counts) if counts else 'sem execuções no período.'))
                if partial:
                    lines.append('Actions: coleta parcial, limite de 1.000 execuções.')
                for run in runs:
                    state = run.get('conclusion') or run['status']
                    lines.append(f"- {run['name']}: {state} | {run['head_sha'][:7]} | {run['html_url']}")
                if any(r.get('conclusion') in ('failure', 'timed_out', 'action_required') for r in runs):
                    priorities.append('P1 — Investigar workflows com falha e validar novamente antes de publicar.')
            except Exception as exc:
                lines.append('Actions indisponíveis: ' + str(exc))
                priorities.append('Verificar acesso de leitura ao GitHub Actions.')

    async def railway(self, session, start, end, lines, priorities):
        # project_id:service_id:environment_id; aceita vários serviços separados por vírgula.
        services = [s.strip() for s in os.getenv('RELATORIO_RAILWAY_SERVICOS', '').split(',') if s.strip()]
        token = os.getenv('RELATORIO_RAILWAY_TOKEN', '')
        if not services or not token:
            lines.append('\n## Railway\nFonte não configurada. Deploys bem-sucedidos e falhas não foram verificados.')
            priorities.append('Configurar a API Railway para confirmar os resultados dos deploys.')
            return
        headers = {'Authorization': 'Bearer ' + token}
        query = '''query($input: DeploymentListInput!, $after: String) {
          deployments(input: $input, first: 100, after: $after) {
            edges { node { id status createdAt } }
            pageInfo { hasNextPage endCursor }
          }
        }'''
        for spec in services:
            lines.append('\n## Railway — serviço ' + spec)
            try:
                project, service, environment = spec.split(':')
                cursor = None
                deployments = []
                for page in range(10):
                    data = await self.request(session, 'https://backboard.railway.com/graphql/v2', method='POST',
                        headers=headers, json={'query': query, 'variables': {'input': {
                            'projectId': project, 'serviceId': service, 'environmentId': environment}, 'after': cursor}})
                    result = data['data']['deployments']
                    batch = [e['node'] for e in result['edges']]
                    deployments.extend(batch)
                    info = result['pageInfo']
                    # Não presumir ordenação: limite explícito se necessário.
                    if not info['hasNextPage']:
                        break
                    cursor = info['endCursor']
                else:
                    lines.append('Histórico limitado a 1.000 deploys; contagem pode ser parcial.')
                deployments.sort(key=lambda d: stamp(d['createdAt']), reverse=True)
                recent = [d for d in deployments if start <= stamp(d['createdAt']) < end]
                lines.append('Deploys criados no período, com status atual: ' + format_counts(Counter(d['status'] for d in recent)))
                lines.append('Status atual consultado agora; não é uma linha do tempo de transições.')
                if deployments:
                    latest = deployments[0]
                    lines.append(f"Último deploy criado: {latest['id']} | {latest['status']} | {latest['createdAt']}")
                    if latest['status'] in ('FAILED', 'CRASHED'):
                        priorities.append('P1 — Verificar o último deploy Railway com falha e confirmar qual versão está atendendo.')
                for dep in recent:
                    lines.append(f"- {dep['id']} | {dep['status']} | {dep['createdAt']}")
                # Inclui o último deploy antigo: ele pode continuar ativo e produzir erros hoje.
                logs_deps = {d['id']: d for d in recent}
                if deployments:
                    logs_deps[deployments[0]['id']] = deployments[0]
                for dep in logs_deps.values():
                    for kind in ('buildLogs', 'deploymentLogs'):
                        try:
                            log_query = f'''query($id: String!) {{ {kind}(deploymentId: $id, limit: 500) {{ timestamp message severity }} }}'''
                            data = await self.request(session, 'https://backboard.railway.com/graphql/v2', method='POST',
                                headers=headers, json={'query': log_query, 'variables': {'id': dep['id']}})
                            logs = data['data'][kind] or []
                            errors = [x for x in logs if start <= stamp(x['timestamp']) < end and (
                                (x.get('severity') or '').upper() in ('ERROR', 'FATAL', 'CRITICAL') or
                                re.search(r'\b(error|exception|traceback|failed|fatal)\b', x.get('message', ''), re.I))]
                            if errors:
                                lines.append(f"  {kind} {dep['id']}: {len(errors)} linhas suspeitas na amostra (não equivale a incidentes).")
                                for entry in errors:
                                    lines.append(f"  - {entry['timestamp']}: {entry['message'][:1500]}")
                                priorities.append('P1 — Revisar os trechos de log sinalizados; palavras-chave podem gerar falsos positivos.')
                            if len(logs) >= 500:
                                lines.append(f'  {kind}: limite de 500 linhas atingido; cobertura parcial.')
                        except Exception as exc:
                            lines.append(f'  {kind} indisponível: {exc}')
            except Exception as exc:
                lines.append('Railway indisponível: ' + str(exc))
                priorities.append('Restabelecer a leitura da API Railway; não interpretar ausência de dados como sucesso.')

    async def discord_logs(self, start, end, channel, lines, priorities):
        ids = [s.strip() for s in os.getenv('RELATORIO_LOG_CANAIS', '').split(',') if s.strip()]
        lines.append('\n## Registros dos canais selecionados')
        if not ids:
            lines.append('Nenhum canal de logs selecionado.')
        for raw in ids:
            try:
                source = self.bot.get_channel(int(raw)) or await self.bot.fetch_channel(int(raw))
                if not isinstance(source, discord.TextChannel) or source.guild.id != channel.guild.id or source.id == channel.id:
                    raise ValueError('Escolha outro canal de texto deste servidor, diferente do destino.')
                count = 0
                async for message in source.history(limit=1001, after=start, before=end, oldest_first=True):
                    count += 1
                    if count > 1000:
                        lines.append('Limite de 1.000 registros atingido neste canal; cobertura parcial.')
                        break
                    if not (message.webhook_id or message.author.bot):
                        continue
                    parts = [message.content]
                    for embed in message.embeds:
                        parts.extend([embed.title or '', embed.description or ''])
                        parts.extend(f.name + ': ' + f.value for f in embed.fields)
                    parts.extend(component_text(message.components))
                    text = '\n'.join(p for p in parts if p)
                    lines.append(f'- #{source.name} | {message.created_at.isoformat()} | {message.jump_url}\n{text[:3500]}')
                if not count:
                    lines.append(f'#{source.name}: sem registros no período. Isso não comprova ausência de erros.')
            except Exception as exc:
                lines.append(f'Canal {raw} indisponível: {exc}')
                priorities.append('Verificar acesso e histórico dos canais de logs selecionados.')

    async def build(self, start, end, channel):
        lines = ["RELATÓRIO DIÁRIO — FAMÍLIA SANT'S",
                 f"Período: {start.astimezone(TZ):%d/%m/%Y %H:%M} até {end.astimezone(TZ):%d/%m/%Y %H:%M} (Brasília)",
                 f"Coleta: {datetime.now(TZ):%d/%m/%Y %H:%M}",
                 'Fontes somente leitura. Recomendações baseadas em regras; sem IA externa nem correções automáticas.']
        priorities = []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            await self.github(session, start, end, lines, priorities)
            await self.railway(session, start, end, lines, priorities)
            url = os.getenv('PUBLIC_URL', '').rstrip('/')
            lines.append('\n## Painel web')
            if url.startswith('https://'):
                try:
                    async with session.get(url + '/', allow_redirects=False) as response:
                        lines.append(f'Teste HTTP atual da página inicial: {response.status}. Não valida login, dados, versão publicada ou disponibilidade nas últimas 24h.')
                        if response.status != 200:
                            priorities.append('P1 — Verificar resposta HTTP do painel web.')
                except Exception as exc:
                    lines.append('Página inicial indisponível para consulta: ' + type(exc).__name__)
                    priorities.append('P1 — Verificar conectividade e disponibilidade do painel.')
            else:
                lines.append('PUBLIC_URL HTTPS não configurada; verificação não realizada.')
        await self.discord_logs(start, end, channel, lines, priorities)
        lines.append('\n## Pendências e próximas melhorias')
        lines.extend('- ' + p for p in dict.fromkeys(priorities))
        lines.extend(['- P2 — Validar manualmente tickets, expresso, leilões e login do painel após mudanças nessas áreas.',
                      '- P2 — Comparar commit publicado com o esperado quando houver suspeita de painel desatualizado.',
                      '- Pendências funcionais não são inferidas como resolvidas por um deploy bem-sucedido.',
                      '- Ausência de alertas nas fontes consultadas não comprova ausência de falhas.'])
        return clean('\n'.join(lines))

    async def preview(self, channel, end=None):
        end = end or datetime.now(UTC)
        return await self.build(end - timedelta(days=1), end, channel)

    async def publish(self, channel, start, end):
        pool = await self.database()
        # Lock de sessão: impede dois processos de publicar o mesmo canal simultaneamente.
        async with pool.acquire() as con:
            locked = await con.fetchval('SELECT pg_try_advisory_lock($1)', channel.id)
            if not locked:
                return
            try:
                day = end.astimezone(TZ).date()
                row = await con.fetchrow('SELECT * FROM sants_relatorio_envios WHERE canal_id=$1 AND dia=$2', channel.id, day)
                if row and row['estado'] in ('enviado', 'incerto'):
                    return
                report = row['conteudo'] if row else await self.build(start, end, channel)
                if not row:
                    await con.execute("INSERT INTO sants_relatorio_envios VALUES($1,$2,'preparado',$3,NULL)", channel.id, day, report)
                # Marcar antes da chamada externa: falhas ambíguas não causam novo @everyone.
                await con.execute("UPDATE sants_relatorio_envios SET estado='incerto' WHERE canal_id=$1 AND dia=$2", channel.id, day)
                can_ping = channel.permissions_for(channel.guild.me).mention_everyone
                note = '' if can_ping else '\nO bot não tem permissão para marcar @everyone.'
                digest = hashlib.sha256(report.encode()).hexdigest()[:10]
                view = discord.ui.LayoutView()
                view.add_item(discord.ui.TextDisplay(
                    report_message(report, start, end, ping=can_ping)
                    + note + f'\n-# Registro {day}/{digest}'))
                view.add_item(discord.ui.File(f'attachment://relatorio-sants-{day}.txt'))
                try:
                    message = await channel.send(view=view,
                        file=discord.File(io.BytesIO(report.encode('utf-8')), filename=f'relatorio-sants-{day}.txt'),
                        allowed_mentions=discord.AllowedMentions(everyone=can_ping, users=False, roles=False, replied_user=False))
                except (discord.Forbidden, discord.NotFound):
                    # Rejeição conhecida: nenhuma mensagem criada, permite nova tentativa após corrigir permissões.
                    await con.execute("UPDATE sants_relatorio_envios SET estado='preparado' WHERE canal_id=$1 AND dia=$2", channel.id, day)
                    raise
                await con.execute("UPDATE sants_relatorio_envios SET estado='enviado', mensagem_id=$3 WHERE canal_id=$1 AND dia=$2", channel.id, day, message.id)
            finally:
                await con.execute('SELECT pg_advisory_unlock($1)', channel.id)

    @tasks.loop(minutes=1)
    async def tick(self):
        if os.getenv('RELATORIO_ATIVO', '').lower() not in ('1', 'true', 'sim'):
            return
        try:
            now = datetime.now(TZ)
            start, end = window(now, os.getenv('RELATORIO_HORARIO', '09:00'))
            if now < end:
                return
            async with self.lock:
                channel = await self.destination()
                await self.publish(channel, start, end)
        except Exception:
            LOG.exception('Relatório diário não concluído; confira configuração e fontes.')

    @tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()

    @commands.command(name='relatorio_teste')
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def relatorio_teste(self, ctx):
        """Prévia no canal configurado, sem @everyone e sem consumir o relatório diário."""
        try:
            channel = await self.destination()
            if ctx.channel.id != channel.id:
                await ctx.send('Execute este comando no canal configurado em RELATORIO_CANAL_ID.', allowed_mentions=discord.AllowedMentions.none())
                return
            if self.lock.locked():
                await ctx.send('> `⏳` **Já existe um relatório em preparação.** Você pode testar novamente assim que ele terminar.', allowed_mentions=discord.AllowedMentions.none())
                return
            async with self.lock:
                end = datetime.now(UTC)
                await ctx.send('> `📊` **Preparando o relatório...** Consultando as fontes configuradas.', allowed_mentions=discord.AllowedMentions.none())
                report = await self.preview(channel, end=end)
                view = discord.ui.LayoutView()
                view.add_item(discord.ui.TextDisplay(report_message(report, end - timedelta(days=1), end, preview=True)))
                view.add_item(discord.ui.File('attachment://previa-relatorio-sants.txt'))
                await channel.send(view=view,
                    file=discord.File(io.BytesIO(report.encode()), filename='previa-relatorio-sants.txt'),
                    allowed_mentions=discord.AllowedMentions.none())
        except (ValueError, discord.Forbidden, discord.NotFound) as exc:
            await ctx.send('> `⚠️` **Não foi possível preparar o relatório.**\n> ' + clean(str(exc))[:1000], allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            LOG.exception('Falha ao gerar prévia do relatório.')
            await ctx.send('Não foi possível gerar a prévia. Confira os logs e a configuração.', allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Relatorios(bot))
