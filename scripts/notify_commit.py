"""GitHub Actions -> Discord native V2 commit notification; stdlib only."""
import json
import os
import urllib.request
from datetime import datetime, timezone


def send(url, data):
    if not url:
        print('Webhook não configurado; notificação ignorada.')
        return
    req = urllib.request.Request(url, json.dumps(data).encode(), {'Content-Type': 'application/json', 'User-Agent': 'Sants-Commit-Monitor/1.0'})
    with urllib.request.urlopen(req, timeout=12) as resp:
        print('Notificação enviada:', resp.status)


def main():
    env = os.environ
    repo = env.get('REPOSITORY', '')
    sha = env.get('SHA', '')
    link = env.get('SERVER_URL', 'https://github.com') + '/' + repo + '/commit/' + sha
    passed = env.get('CHECK_RESULT') == 'success'
    message = (
    (os.environ.get("COMMIT_MESSAGE") or "").strip().splitlines()
    or ["Atualização manual do sistema"]
)[0][:350]
    blocks = [
        {'type': 10, 'content': '## ' + ('✅ Commit verificado' if passed else '🚨 Verificação de commit reprovada')},
        {'type': 10, 'content': '**Família Sant’s • Registro de Desenvolvimento**'},
        {'type': 14, 'divider': True, 'spacing': 1},
        {'type': 10, 'content': '**Descrição:** ' + message.replace('@', '@\u200b') + '\n**Autor:** `' + env.get('ACTOR','')[:100] + '`\n**Branch:** `' + env.get('BRANCH','')[:100] + '`\n**Commit:** `' + sha[:10] + '`\n**Repositório:** `' + repo[:150] + '`'},
        {'type': 10, 'content': '**Validação:** ' + ('Sintaxe Python aprovada' if passed else 'Erro na verificação de sintaxe Python') + '\n-# Envio ao GitHub não comprova que o deploy no Railway terminou.'},
        {'type': 1, 'components': [{'type': 2, 'style': 5, 'label': 'Visualizar commit', 'url': link}]},
        {'type': 10, 'content': '-# Registro automático • ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')},
    ]
    data = {'flags': 32768, 'allowed_mentions': {'parse': []}, 'components': [{'type': 17, 'accent_color': 5763719 if passed else 15548997, 'components': blocks}]}
    send(env.get('COMMIT_WEBHOOK'), data)
    if not passed:
        send(env.get('ERROR_WEBHOOK'), data)


if __name__ == '__main__':
    main()
