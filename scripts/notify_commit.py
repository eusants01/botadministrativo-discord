"""GitHub Actions -> Discord Components V2 commit notification (stdlib only)."""
"""GitHub Actions -> Discord Components V2 commit notification (stdlib only)."""
import json
import os
import urllib.error
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode


def send(url, data):
    if not url:
        print('Webhook não configurado; notificação ignorada.')
        return
    # Discord incoming webhooks require with_components=true to accept Components V2.
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["with_components"] = "true"
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    request = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Sants-Commit-Monitor/1.1'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print('Notificação enviada:', response.status)
    except urllib.error.HTTPError as exc:
        # Discord usually returns a JSON description of the invalid component.
        body = exc.read().decode('utf-8', errors='replace')
        print(f'Falha ao enviar notificação: HTTP {exc.code} - {body[:3000]}')
        raise SystemExit(1) from None


def main():
    env = os.environ
    repo = env.get('REPOSITORY', '').strip()
    sha = env.get('SHA', '').strip()
    passed = env.get('CHECK_RESULT', '') == 'success'
    lines = (env.get('COMMIT_MESSAGE') or '').strip().splitlines()
    message = (lines[0] if lines else 'Atualização manual do sistema')[:350]
    actor = (env.get('ACTOR') or 'Não informado')[:100]
    branch = (env.get('BRANCH') or 'Não informada')[:100]

    def safe(value):
        return value.replace('@', '@\u200b').replace('`', 'ˋ')

    repo = env.get('REPOSITORY', '').strip()
    sha = env.get('SHA', '').strip()
    passed = env.get('CHECK_RESULT', '') == 'success'
    lines = (env.get('COMMIT_MESSAGE') or '').strip().splitlines()
    message = (lines[0] if lines else 'Atualização manual do sistema')[:350]
    actor = (env.get('ACTOR') or 'Não informado')[:100]
    branch = (env.get('BRANCH') or 'Não informada')[:100]

    def safe(value):
        return value.replace('@', '@\u200b').replace('`', 'ˋ')

    blocks = [
        {'type': 10, 'content': '## ' + ('✅ Commit verificado' if passed else '🚨 Verificação de commit reprovada')},
        {'type': 10, 'content': '**Família Sant’s • Registro de Desenvolvimento**'},
        {'type': 14, 'divider': True, 'spacing': 1},
        {'type': 10, 'content': '**Descrição:** ' + safe(message) + '\n**Autor:** `' + safe(actor) + '`\n**Branch:** `' + safe(branch) + '`\n**Commit:** `' + safe(sha[:10]) + '`\n**Repositório:** `' + safe(repo[:150]) + '`'},
        {'type': 10, 'content': '**Validação:** ' + ('Sintaxe Python aprovada' if passed else 'Erro na verificação de sintaxe Python') + '\n-# O envio ao GitHub não confirma a conclusão do deploy no Railway.'},
    ]
    if repo and sha:
        base = (env.get('SERVER_URL') or 'https://github.com').rstrip('/')
        url = f'{base}/{quote(repo, safe="/")}/commit/{quote(sha, safe="")}'
        blocks.append({'type': 1, 'components': [{'type': 2, 'style': 5, 'label': 'Visualizar commit', 'url': url}]})
    blocks.append({'type': 10, 'content': '-# Registro automático • ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')})

    data = {
        'flags': 32768,
        'allowed_mentions': {'parse': []},
        'components': [{'type': 17, 'accent_color': 5763719 if passed else 15548997, 'components': blocks}],
    }
        {'type': 10, 'content': '**Descrição:** ' + safe(message) + '\n**Autor:** `' + safe(actor) + '`\n**Branch:** `' + safe(branch) + '`\n**Commit:** `' + safe(sha[:10]) + '`\n**Repositório:** `' + safe(repo[:150]) + '`'},
        {'type': 10, 'content': '**Validação:** ' + ('Sintaxe Python aprovada' if passed else 'Erro na verificação de sintaxe Python') + '\n-# O envio ao GitHub não confirma a conclusão do deploy no Railway.'},
    ]
    if repo and sha:
        base = (env.get('SERVER_URL') or 'https://github.com').rstrip('/')
        url = f'{base}/{quote(repo, safe="/")}/commit/{quote(sha, safe="")}'
        blocks.append({'type': 1, 'components': [{'type': 2, 'style': 5, 'label': 'Visualizar commit', 'url': url}]})
    blocks.append({'type': 10, 'content': '-# Registro automático • ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')})

    data = {
        'flags': 32768,
        'allowed_mentions': {'parse': []},
        'components': [{'type': 17, 'accent_color': 5763719 if passed else 15548997, 'components': blocks}],
    }
    send(env.get('COMMIT_WEBHOOK'), data)
    if not passed:
        send(env.get('ERROR_WEBHOOK'), data)


if __name__ == '__main__':
    main()
