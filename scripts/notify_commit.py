"""GitHub Actions -> Discord Components V2 commit notification (stdlib only)."""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

# ╔══════════════════════════════════════════════════════════════╗
# ║                        CONFIGURAÇÃO                          ║
# ╚══════════════════════════════════════════════════════════════╝

NOME = 'Família Sant’s'

# Cores da faixa lateral da mensagem
COR_SUCESSO = 0x4A90E2   # azul do servidor
COR_FALHA = 0xED4245     # vermelho

# Link direto de um banner para o topo da mensagem (https://...). '' = sem banner.
# Também pode ser definido pela variável de ambiente BANNER_URL.
BANNER_URL = ''

# O mesmo conjunto de arquivos que o workflow verifica
CAMINHOS_VERIFICADOS = ['main.py', 'painel.py', 'portal_ext.py', 'cogs', 'utils']

# Áreas do projeto: (trecho do caminho, emoji, nome). A primeira que casar vence.
AREAS = [
    ('cogs/tickets.py', '🎫', 'Tickets'),
    ('cogs/cassino.py', '🎰', 'Cassino'),
    ('cogs/leiloes.py', '🔨', 'Leilões'),
    ('cogs/pings.py', '🔔', 'Notificações'),
    ('cogs/forms.py', '📝', 'Formulários'),
    ('cogs/convites.py', '🔗', 'Convites'),
    ('cogs/sorteios.py', '🎁', 'Sorteios'),
    ('cogs/economia.py', '💰', 'Economia'),
    ('cogs/contratos.py', '📜', 'Contratos'),
    ('cogs/ajuda_publica.py', '❓', 'Ajuda pública'),
    ('main.py', '🤖', 'Núcleo do bot'),
    ('painel.py', '🌐', 'Portal web'),
    ('portal_ext.py', '🌐', 'Portal web'),
    ('.html', '🌐', 'Portal web'),
    ('assets/', '🌐', 'Portal web'),
    ('utils/', '🧰', 'Utilitários'),
    ('.github/', '⚙️', 'Automação'),
    ('scripts/', '⚙️', 'Automação'),
    ('requirements', '📦', 'Dependências'),
]

# Tipo do commit, pela mensagem: (regex, emoji, título da mensagem, rótulo)
TIPOS = [
    (r'^(feat|feature)(\(.+\))?!?:', '✨', 'Nova funcionalidade', 'Novidade'),
    (r'^(fix|bugfix)(\(.+\))?!?:', '🐛', 'Correção aplicada', 'Correção'),
    (r'^(docs?)(\(.+\))?!?:', '📝', 'Documentação atualizada', 'Documentação'),
    (r'\b(corrig\w*|correç\w*|fix(es|ed)?|bug|conserta\w*|erro)\b', '🐛', 'Correção aplicada', 'Correção'),
    (r'\b(implement\w*|adicion\w*|novo|nova|add(ed)?|cria\w*|lanç\w*)\b', '✨', 'Nova funcionalidade', 'Novidade'),
    (r'\b(melhor\w*|refe\w*|reform\w*|reestrutur\w*|otimiz\w*|ajust\w*|atualiz\w*|update[sd]?|refactor\w*)\b', '🔧', 'Melhoria enviada', 'Melhoria'),
    (r'\b(test\w*)\b', '🧪', 'Teste enviado', 'Teste'),
    (r'\b(docs?|readme|document\w*)\b', '📝', 'Documentação atualizada', 'Documentação'),
]

LIMITE_TEXTO_TOTAL = 3800   # o Discord aceita 4000 caracteres de texto por mensagem


# ════════════════════════════════════════════════════════════════
#                              ENVIO
# ════════════════════════════════════════════════════════════════


def send(url, data):
    """Envia ao webhook. Retorna True se deu certo."""
    if not url:
        print('Webhook não configurado; notificação ignorada.')
        return True
    # Webhooks exigem with_components=true para aceitar Components V2.
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['with_components'] = 'true'
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    request = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Sants-Commit-Monitor/1.2'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print('Notificação enviada:', response.status)
        return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        print(f'Falha ao enviar notificação: HTTP {exc.code} - {body[:3000]}')
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f'Falha ao enviar notificação: {exc}')
    return False


# ════════════════════════════════════════════════════════════════
#                              DADOS
# ════════════════════════════════════════════════════════════════


def safe(value):
    """Evita menções e quebra de formatação com texto vindo do commit."""
    return str(value).replace('@', '@\u200b').replace('`', 'ˋ')


def cortar(texto, limite):
    texto = (texto or '').strip()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + '…'


def ler_json(env, nome):
    try:
        return json.loads(env.get(nome) or 'null')
    except (ValueError, TypeError):
        return None


def detectar_tipo(mensagem):
    baixa = mensagem.lower()
    for padrao, emoji, titulo, rotulo in TIPOS:
        if re.search(padrao, baixa):
            return emoji, titulo, rotulo
    return '📦', 'Atualização enviada', 'Atualização'


def para_epoch(iso):
    try:
        return int(datetime.fromisoformat(iso).timestamp())
    except (ValueError, TypeError):
        return None


def area_de(caminho):
    baixo = caminho.lower()
    for trecho, emoji, nome in AREAS:
        if trecho in baixo:
            return emoji, nome
    return '📄', 'Outros'


def verificar_sintaxe():
    """Compila todos os .py verificados. Retorna (total, [(arquivo, linha, erro, trecho)])."""
    arquivos = []
    for caminho in CAMINHOS_VERIFICADOS:
        if os.path.isfile(caminho) and caminho.endswith('.py'):
            arquivos.append(caminho)
        elif os.path.isdir(caminho):
            for raiz, pastas, nomes in os.walk(caminho):
                pastas[:] = sorted(p for p in pastas if p != '__pycache__')
                arquivos += [os.path.join(raiz, n) for n in sorted(nomes) if n.endswith('.py')]
    erros = []
    for arquivo in arquivos:
        nome = arquivo.replace(os.sep, '/')
        try:
            with open(arquivo, 'rb') as f:
                compile(f.read(), arquivo, 'exec')
        except SyntaxError as exc:
            erros.append((nome, exc.lineno, exc.msg, (exc.text or '').strip()))
        except (ValueError, OSError) as exc:
            erros.append((nome, None, str(exc), ''))
    return len(arquivos), erros


# ════════════════════════════════════════════════════════════════
#                             MENSAGEM
# ════════════════════════════════════════════════════════════════


def texto(conteudo):
    return {'type': 10, 'content': conteudo}


def separador(grande=True):
    return {'type': 14, 'divider': True, 'spacing': 2 if grande else 1}


def botao(rotulo, emoji, url):
    return {'type': 2, 'style': 5, 'label': rotulo, 'emoji': {'name': emoji}, 'url': url}


def contar_texto(blocos):
    total = 0
    for b in blocos:
        if b['type'] == 10:
            total += len(b['content'])
        elif b['type'] == 9:
            total += sum(len(c['content']) for c in b['components'])
    return total


def caber_no_limite(blocos):
    """Encurta os maiores textos até caber no limite do Discord."""
    while contar_texto(blocos) > LIMITE_TEXTO_TOTAL:
        todos = []
        for b in blocos:
            if b['type'] == 10:
                todos.append(b)
            elif b['type'] == 9:
                todos += b['components']
        maior = max(todos, key=lambda x: len(x['content']))
        if len(maior['content']) <= 120:
            break
        maior['content'] = maior['content'][: int(len(maior['content']) * 0.8)].rstrip() + '…'


def montar(env):
    repo = env.get('REPOSITORY', '').strip()
    sha = env.get('SHA', '').strip()
    passou = env.get('CHECK_RESULT', '') == 'success'
    autor_actor = (env.get('ACTOR') or 'Não informado')[:100]
    branch = (env.get('BRANCH') or 'Não informada')[:100]
    base = (env.get('SERVER_URL') or 'https://github.com').rstrip('/')

    # ── Commits do envio ────────────────────────────────────────
    head = ler_json(env, 'HEAD_COMMIT_JSON') or {}
    commits = ler_json(env, 'COMMITS_JSON') or []
    if not isinstance(commits, list):
        commits = []
    mensagem_completa = (head.get('message') or env.get('COMMIT_MESSAGE') or '').strip()
    linhas = mensagem_completa.splitlines()
    manual = not linhas
    titulo = linhas[0].strip() if linhas else 'Execução manual do monitor'
    corpo = '\n'.join(l.rstrip() for l in linhas[1:]).strip()
    emoji, titulo_tipo, rotulo_tipo = ('🛠️', 'Verificação manual', 'Manual') if manual else detectar_tipo(titulo)
    quando = para_epoch(head.get('timestamp'))

    # ── Arquivos alterados ──────────────────────────────────────
    adicionados, modificados, removidos = set(), set(), set()
    for c in commits or ([head] if head else []):
        adicionados |= set(c.get('added') or [])
        modificados |= set(c.get('modified') or [])
        removidos |= set(c.get('removed') or [])
    modificados -= adicionados
    todos = adicionados | modificados | removidos
    areas = {}
    for caminho in sorted(todos):
        a = area_de(caminho)
        areas.setdefault(a, []).append(caminho.rsplit('/', 1)[-1])

    # ── Validação ───────────────────────────────────────────────
    total_arquivos, erros = verificar_sintaxe()

    # ── Blocos ──────────────────────────────────────────────────
    cabecalho = ('## ' + emoji + ' ' + titulo_tipo) if passou else ('## 🚨 Falha na verificação • ' + rotulo_tipo)
    cab_texto = [texto(cabecalho), texto('-# ' + NOME + ' • Registro de Desenvolvimento')]
    avatar = f'https://github.com/{quote(autor_actor, safe="")}.png?size=128'
    blocos = []

    banner = (env.get('BANNER_URL') or BANNER_URL).strip()
    if banner.lower().startswith(('https://', 'http://')):
        blocos.append({'type': 12, 'items': [{'media': {'url': banner}}]})
    blocos.append({'type': 9, 'components': cab_texto, 'accessory': {'type': 11, 'media': {'url': avatar}}})
    blocos.append(separador())

    descricao = '### ' + safe(cortar(titulo, 200))
    if corpo:
        descricao += '\n' + '\n'.join('> ' + safe(l) if l.strip() else '>' for l in cortar(corpo, 500).splitlines())
    blocos.append(texto(descricao))

    detalhes = [
        '**Detalhes**',
        '> `👤` **Autor:** ' + safe(autor_actor),
        '> `🌿` **Branch:** ' + safe(branch),
        '> `🔖` **Commit:** `' + safe(sha[:7]) + '`',
    ]
    if quando:
        detalhes.append(f'> `🕒` **Quando:** <t:{quando}:F> • <t:{quando}:R>')
    resumo = 'Execução manual' if manual and not commits else (
        f'{len(commits) or 1} commit' + ('s' if len(commits) > 1 else ''))
    if todos:
        resumo += f' • `+{len(adicionados)}` novos • `~{len(modificados)}` alterados • `−{len(removidos)}` removidos'
    detalhes.append('> `📦` **Envio:** ' + resumo)
    blocos.append(texto('\n'.join(detalhes)))

    if areas:
        itens = []
        for (emo, nome), arquivos in list(areas.items())[:6]:
            mostrados = ', '.join(f'`{safe(a)}`' for a in arquivos[:2])
            extra = f' +{len(arquivos) - 2}' if len(arquivos) > 2 else ''
            itens.append(f'> {emo} **{nome}** — {mostrados}{extra}')
        if len(areas) > 6:
            itens.append(f'> … e mais {len(areas) - 6} área(s)')
        blocos.append(texto('**Áreas afetadas**\n' + '\n'.join(itens)))

    if len(commits) > 1:
        itens = []
        for c in commits[:5]:
            msg = safe(cortar((c.get('message') or '').splitlines()[0] if c.get('message') else '', 70))
            autor = safe((c.get('author') or {}).get('username') or (c.get('author') or {}).get('name') or '')
            itens.append(f'> `{safe((c.get("id") or "")[:7])}` {msg}' + (f' — *{autor}*' if autor else ''))
        if len(commits) > 5:
            itens.append(f'> … e mais {len(commits) - 5} commit(s)')
        blocos.append(texto('**Commits neste envio**\n' + '\n'.join(itens)))

    blocos.append(separador())
    if passou:
        validacao = (
            '**Validação**\n'
            f'> `✅` Sintaxe Python aprovada — **{total_arquivos}** arquivos verificados'
        )
    else:
        validacao = '**Validação**\n> `❌` Erro na verificação de sintaxe Python'
        if erros:
            detalhe = []
            for arquivo, linha, erro, trecho in erros[:3]:
                local = f'{arquivo}:{linha}' if linha else arquivo
                detalhe.append(f'{local}  →  {erro}' + (f'\n    {cortar(trecho, 90)}' if trecho else ''))
            if len(erros) > 3:
                detalhe.append(f'… e mais {len(erros) - 3} erro(s)')
            validacao += '\n```\n' + cortar(safe('\n'.join(detalhe)), 700).replace('ˋ', "'") + '\n```'
    validacao += '\n-# O envio ao GitHub não confirma a conclusão do deploy no Railway.'
    blocos.append(texto(validacao))

    botoes = []
    if repo and sha:
        repo_url = f'{base}/{quote(repo, safe="/")}'
        botoes.append(botao('Ver commit', '🔍', f'{repo_url}/commit/{quote(sha, safe="")}'))
        compare = (env.get('COMPARE_URL') or '').strip()
        if len(commits) > 1 and compare.startswith('http'):
            botoes.append(botao('Ver comparação', '🔀', compare))
        if env.get('RUN_ID'):
            botoes.append(botao('Ver execução', '⚙️', f'{repo_url}/actions/runs/{quote(env["RUN_ID"], safe="")}'))
    if botoes:
        blocos.append({'type': 1, 'components': botoes})

    agora = int(datetime.now(timezone.utc).timestamp())
    blocos.append(texto(f'-# Registro automático • <t:{agora}:f>'))

    caber_no_limite(blocos)
    return {
        'flags': 32768,
        'allowed_mentions': {'parse': []},
        'components': [{'type': 17, 'accent_color': COR_SUCESSO if passou else COR_FALHA, 'components': blocos}],
    }, passou


def main():
    env = os.environ
    data, passou = montar(env)
    ok = send(env.get('COMMIT_WEBHOOK'), data)
    if not passou:
        ok = send(env.get('ERROR_WEBHOOK'), data) and ok
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
    