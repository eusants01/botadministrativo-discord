"""Runtime incident reporting to a Discord webhook using native Components V2."""
import asyncio
import logging
import os
import re
import sys
import traceback
from datetime import datetime, timezone

import aiohttp

LOG = logging.getLogger('sants.monitor')
WEBHOOK = 'LOGS_ERROS_WEBHOOK_URL'


def redact(value):
    value = str(value)
    for key in ('DISCORD_TOKEN', 'DATABASE_URL', 'LOGS_ERROS_WEBHOOK_URL', 'LOGS_COMMIT_WEBHOOK_URL'):
        secret = os.getenv(key, '')
        if secret and len(secret) > 5:
            value = value.replace(secret, '[REDACTED]')
    value = re.sub(r'(?i)(postgres(?:ql)?://)[^\s]+', '[DATABASE_URL]', value)
    value = re.sub(r'https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[^\s]+', '[WEBHOOK]', value)
    return value[:1700]


def payload(title, description, error=None):
    fields = [
        {'type': 10, 'content': '## 🚨 ' + title},
        {'type': 14, 'divider': True, 'spacing': 1},
        {'type': 10, 'content': description[:1800]},
    ]
    if error:
        fields += [{'type': 14, 'divider': True, 'spacing': 1},
                   {'type': 10, 'content': '**Diagnóstico técnico**\n```text\n' + redact(error).replace('```', "---") + '\n```'}]
    fields.append({'type': 10, 'content': '-# Família Sant’s • Monitoramento | ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')})
    return {'flags': 32768, 'allowed_mentions': {'parse': []}, 'components': [{'type': 17, 'accent_color': 15158332, 'components': fields}]}


class IncidentMonitor(logging.Handler):
    def __init__(self, loop):
        super().__init__(level=logging.ERROR)
        self.loop = loop
        self.pending = set()
        self.last = {}

    def emit(self, record):
        if record.name.startswith('sants.monitor'):
            return
        try:
            msg = self.format(record)
            signature = (record.name, record.getMessage()[:160])
            now = self.loop.time()
            if now - self.last.get(signature, -999999) < 180:
                return
            self.last[signature] = now
            def schedule():
                task = self.loop.create_task(send_incident(record.name, msg))
                self.pending.add(task)
                task.add_done_callback(self.pending.discard)
            self.loop.call_soon_threadsafe(schedule)
        except Exception:
            self.handleError(record)


async def send_incident(source, detail):
    url = os.getenv(WEBHOOK, '')
    if not url:
        return
    data = payload('Falha registrada', '**Origem:** `' + redact(source)[:100] + '`\n**Situação:** ocorrência capturada automaticamente.', detail)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=data) as response:
                if response.status >= 400:
                    LOG.warning('Falha ao entregar alerta HTTP %s', response.status)
    except Exception as exc:
        LOG.warning('Falha de conexão ao entregar alerta: %s', type(exc).__name__)


def install_monitor(loop):
    handler = IncidentMonitor(loop)
    handler.setFormatter(logging.Formatter('%(levelname)s %(name)s: %(message)s\n%(exc_text)s'))
    logging.getLogger().addHandler(handler)
    def exception_handler(loop, context):
        exc = context.get('exception')
        detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc else str(context.get('message'))
        logging.getLogger('sants.asyncio').error('Exceção não tratada: %s', redact(detail))
    loop.set_exception_handler(exception_handler)
    return handler
