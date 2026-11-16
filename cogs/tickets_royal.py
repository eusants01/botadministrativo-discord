
from __future__ import annotations

import asyncio
import copy
import html
import io
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


import discord
from discord.ext import commands, tasks

LOG = logging.getLogger("royal.tickets")

NOME_SERVIDOR = "Família Royal"
FUSO = ZoneInfo("America/Sao_Paulo")

COR_AZUL = 0xB8904F  # ouro envelhecido • identidade Royal       
COR_AZUL_CLARO = 0xE7C990  # marfim dourado  
COR_NATAL_VERDE = 0x185540
COR_NATAL_VERMELHO = 0xA83238
COR_NATAL_OURO = 0xD2AD61

CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,
]

CARGOS_NOTIFICAR = [1560385636819796059]


def ids_ambiente(chave: str) -> list[int]:
    resultado = []
    for texto in os.getenv(chave, "").replace(";", ",").split(","):
        texto = texto.strip()
        if texto.isdigit():
            resultado.append(int(texto))
    return resultado


# Denúncias contra a própria equipe só podem ser geridas pela Corregedoria
# informada aqui (ou pelo proprietário do servidor, por segurança).
CARGOS_CORREGEDORIA = ids_ambiente("ROYAL_TICKETS_CORREGEDORIA_ROLE_IDS")
TEMA_PADRAO = os.getenv("ROYAL_TICKETS_TEMA", "natal").strip().lower()
BANNER_NATAL = os.getenv("ROYAL_NATAL_BANNER_URL", "").strip()
BANNERS_NATAL = {
    k: os.getenv(f"ROYAL_NATAL_BANNER_{k.upper()}_URL", "").strip()
    for k in ("DENUNCIA", "CARGO_EB", "PARCERIA", "OUTROS")
}
MAX_TRANSCRICAO_BYTES = 15 * 1024 * 1024
ALERTAS_ESCALONADOS_MINUTOS = (5, 20, 60)


CATEGORIA_TICKETS_ID = 1555449984453972009

CANAL_LOGS_ID = 1555446279033589770

CANAL_AVALIACOES_ID = 1555453132387913728

MAX_TICKETS_POR_USUARIO = 1
TEMPO_PARA_APAGAR = 3
COOLDOWN_CHAMAR_EQUIPE = 60
ALERTA_SEM_ATENDENTE_MINUTOS = 5

INATIVIDADE_AVISO_HORAS = 0
INATIVIDADE_FECHAR_APOS_AVISO_HORAS = 0
FECHAR_APOS_DECISAO_MIN = 0
BANNER_PRINCIPAL = os.getenv("ROYAL_SUPPORT_BANNER_URL", "").strip() or None
BANNER_TICKET_PADRAO = os.getenv("ROYAL_TICKET_BANNER_URL", "").strip() or BANNER_PRINCIPAL
BANNER_AVALIACAO = os.getenv("ROYAL_AVALIACAO_BANNER_URL", "").strip() or BANNER_TICKET_PADRAO


PAINEL_DESCRICAO_CLASSICO = """\
# <a:coroa:1564000189167960177> CENTRAL ATENDIMENTO ROYAL
Bem-vindo(a) à central oficial de atendimento da **Família Royal**. Selecione a categoria correspondente à sua solicitação para receber o devido atendimento.

**<:ImagemdoChatGPT25deoutde202615_4:1563986647144730826> CATEGORIAS DE ATENDIMENTO**
> `📜` **Denúncias** — Relatar condutas irregulares ou infrações.
> `🛡️` **Cargo do E.B** — Solicitar cargos de divisões ou organizações.
> `🤝` **Parcerias** — Apresentar propostas de colaboração.
> `✉️` **Outros Assuntos** — Encaminhar dúvidas e solicitações gerais.

**<:ImagemdoChatGPT25deoutde202615_4:1563986753830912070> HORÁRIO DE ATENDIMENTO**
> `⏳` **Segunda a Sexta:** 09h às 22h.
> `⏳` **Sábados e domingos:** 11h às 18h.

**<:ImagemdoChatGPT25deoutde202615_4:1563986790753378424> ORIENTAÇÕES IMPORTANTES**
> `⚖️` Todas as solicitações serão analisadas conforme as normas da Família Royal.
> `📎` Apresente informações claras e as comprovações necessárias.
> `⚠️` O uso indevido do sistema poderá resultar em medidas administrativas.
"""

PAINEL_DESCRICAO = """\
# <:wreath:1570688836776755200> CENTRAL DE ATENDIMENTO ROYAL 
Bem-vindo(a) à central oficial de atendimento da **Família Royal**. Selecione a categoria correspondente à sua solicitação.

**<:ImagemdoChatGPT25deoutde202615_4:1563986647144730826> CATEGORIAS DE ATENDIMENTO**
> `📜` **Denúncias** — Relatar condutas irregulares ou infrações com segurança.
> `🛡️` **Cargo do E.B** — Solicitar cargos de divisões ou organizações.
> `🤝` **Parcerias** — Apresentar propostas de colaboração.
> `✉️` **Outros Assuntos** — Encaminhar dúvidas e solicitações gerais.

**<:ImagemdoChatGPT25deoutde202615_4:1563986753830912070> HORÁRIO DE ATENDIMENTO**
> `⏳` **Segunda** a **Sexta**: 10h às 22h.
> `⏳` **Sábado** e **Domingo**: 11h às 18h.
> `🎅` Nosso clima é **natalino**, mas os horários permanecem os mesmos.

**<:ImagemdoChatGPT25deoutde202615_4:1563986790753378424> ORIENTAÇÕES IMPORTANTES**
> `⚖️` Toda solicitação será analisada conforme as normas da Família Royal.
> `📷` Descreva seu caso com clareza e anexe as comprovações necessárias.
> `🚓` Denúncias contra a equipe terão tratamento reservado.
> `⚠️` O uso indevido do sistema poderá resultar em medidas administrativas.
"""


PRIORIDADES = {
    "baixa": ("🟢", "Baixa"),
    "normal": ("🟡", "Normal"),
    "alta": ("🟠", "Alta"),
    "urgente": ("🔴", "Urgente"),
}

RESPOSTAS_PRONTAS = {
    "recebido": (
        "Recebido",
        "👋",
        "Olá, {usuario}! Recebemos o seu ticket e já estamos analisando. "
        "Em breve retornamos por aqui.",
    ),
    "mais_info": (
        "Pedir mais informações",
        "❓",
        "{usuario}, precisamos de mais detalhes para continuar. "
        "Pode enviar mais informações ou provas por aqui?",
    ),
    "em_analise": (
        "Em análise",
        "🔎",
        "{usuario}, o seu pedido está **em análise** pela equipe. "
        "Avisaremos assim que houver uma decisão.",
    ),
    "aguardando": (
        "Aguardando você",
        "⏳",
        "{usuario}, estamos aguardando a sua resposta para dar andamento. "
        "Sem retorno, o ticket poderá ser encerrado.",
    ),
    "comprovacao": (
        "Pedir comprovação",
        "📎",
        "{usuario}, envie aqui os prints ou links que comprovem os requisitos "
        "do que você solicitou.",
    ),
    "resolvido": (
        "Resolvido",
        "✅",
        "{usuario}, acreditamos que tudo foi resolvido. Se estiver tudo certo, "
        "pode fechar o ticket no botão **Fechar**. ⚜️",
    ),
}

CATEGORIAS = {
    "denuncia": {
        "nome": "Denúncias",
        "emoji": "📜",
        "descricao": "Reportar jogadores ou comportamentos",
        "cor": COR_AZUL,
        "banner": "https://media.discordapp.net/attachments/961677475191078992/1564152726575915018/02_denuncias.png?ex=6ae03a3e&is=6adee8be&hm=f7a2cb4d6c674ec7f711cadd207b4fdfc8c09209ac3fbc8a27286b8614b63847&=&format=webp&quality=lossless",
        "mensagem": """Olá, {usuario}.
Sua denúncia será tratada com **sigilo e seriedade**.

**O que enviar**
> `👤` Nome, ID ou @ de quem você está denunciando.
> `📅` Quando e onde aconteceu.
> `📎` Provas: prints, vídeos ou links.

**Aviso**
> `⚠️` Denúncias falsas ou sem provas podem gerar punição.
""",
        "escolha": {
            "label": "Tipo da denúncia",
            "placeholder": "Qual o tipo da denúncia?",
            "opcoes": [
                ("Membro / jogador", "Comportamento de outro membro", "👤"),
                ("Membro da staff", "Conduta de alguém da equipe", "🛡️"),
                ("Golpe ou fraude", "Tentativa de enganar ou roubar", "🚨"),
                ("Outro", "Algo que não se encaixa acima", "📌"),
            ],
        },
        "perguntas": [
            {
                "label": "Quem você está denunciando?",
                "placeholder": "Nome, ID ou @ do denunciado",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "O que aconteceu?",
                "placeholder": "Conte o que ocorreu e onde...",
                "longo": True,
                "obrigatorio": True,
            },
            {
                "label": "Quando aconteceu?",
                "placeholder": "Ex: hoje às 20h / 10/10",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Provas (links)",
                "placeholder": "Links de prints/vídeos (ou envie aqui no ticket)",
                "longo": False,
                "obrigatorio": False,
            },
        ],
        "decisao": False,
        "cargo_ao_aprovar": None,
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
    "cargo_eb": {
        "nome": "Solicitar Cargo no E.B",
        "emoji": "🛡️",
        "descricao": "Peça cargo em uma divisão do E.B",
        "cor": COR_AZUL,
        "banner": "https://media.discordapp.net/attachments/961677475191078992/1564152724314914856/04_cargo_do_eb.png?ex=6ae03a3e&is=6adee8be&hm=3a96636091a2419c091f36e6bb99e3bbd12c6662e7524ab05c408757470d044d&=&format=webp&quality=lossless",
        "mensagem": """Olá, {usuario}.
Recebemos o seu pedido de cargo no **E.B**.

**Como funciona**
> `🔎` A equipe confere o seu pedido e os requisitos do cargo.
> `⚖️` Você recebe a decisão (**aprovado** ou **recusado**) aqui mesmo.
> `⏳` Aguarde — a equipe já foi avisada.

**Aviso**
> `⚠️` Informe o seu nome/ID corretamente para a equipe te localizar no E.B.
""",
       
        "escolha": {
            "label": "Divisão",
            "placeholder": "Em qual divisão/organização você quer o cargo?",
            "opcoes": [
                ("CGEx", "Solicitar cargo no CGEx", "🛡️"),
                ("AFEx", "Solicitar cargo no AFEx", "🎖️"),
                ("Outra divisão", "Informe qual no formulário", "📌"),
            ],
        },
        "perguntas": [
            {
                "label": "Qual cargo você deseja?",
                "placeholder": "Nome do cargo/patente (e divisão, se for outra)",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Seu nome/ID no E.B",
                "placeholder": "Como a equipe vai te localizar",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Cargo atual (se tiver)",
                "placeholder": "Ex: Soldado / nenhum",
                "longo": False,
                "obrigatorio": False,
            },
            {
                "label": "Por que merece o cargo?",
                "placeholder": "Atividade, tempo e requisitos que você cumpre...",
                "longo": True,
                "obrigatorio": True,
            },
            {
                "label": "Comprovação (links)",
                "placeholder": "Links de prints/vídeos (ou envie aqui no ticket)",
                "longo": False,
                "obrigatorio": False,
            },
        ],
        "decisao": True,
        "cargo_ao_aprovar": None,
        "cargos_permitidos": [],
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
    "parceria": {
        "nome": "Solicitar Parcerias",
        "emoji": "🤝",
        "descricao": "Propostas de parceria entre servidores",
        "cor": COR_AZUL,
        "banner": "https://media.discordapp.net/attachments/961677475191078992/1564152724889538561/05_parcerias.png?ex=6ae03a3e&is=6adee8be&hm=d87012f76b163587e5ee6b2b192652f8c9e7d014a3f2227b786e84da848d337d&=&format=webp&quality=lossless",
        "mensagem": """Olá, {usuario}.
Agradecemos seu interesse em estabelecer uma parceria com a **Família Royal**.

**Como funciona**
> `📋` Um responsável analisa a sua proposta.
> `⚖️` Você recebe a decisão (**aprovada** ou **recusada**) aqui mesmo.
> `⏳` Aguarde — a equipe já foi avisada.
""",
        "escolha": {
            "label": "Tipo de parceria",
            "placeholder": "Que tipo de parceria você propõe?",
            "opcoes": [
                ("Divulgação mútua", "Um divulga o outro", "📣"),
                ("Evento em conjunto", "Eventos entre os servidores", "🎉"),
                ("Outro tipo", "Explique na proposta", "💡"),
            ],
        },
        "perguntas": [
            {
                "label": "Nome do servidor/grupo",
                "placeholder": "Ex: Comunidade X",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Link de convite",
                "placeholder": "https://discord.gg/...",
                "longo": False,
                "obrigatorio": True,
                "validar": "convite",
            },
            {
                "label": "Quantidade de membros",
                "placeholder": "Ex: 500",
                "longo": False,
                "obrigatorio": True,
                "validar": "numero",
            },
            {
                "label": "Qual é a sua proposta?",
                "placeholder": "Como seria a parceria?",
                "longo": True,
                "obrigatorio": True,
            },
        ],
        "decisao": True,
        "cargo_ao_aprovar": None,
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
    "outros": {
        "nome": "Outros Assuntos",
        "emoji": "✉️",
        "descricao": "Qualquer outra dúvida ou pedido",
        "cor": COR_AZUL,
        "banner": "https://media.discordapp.net/attachments/961677475191078992/1564152725422219265/06_outros_assuntos.png?ex=6ae03a3e&is=6adee8be&hm=874cdc3e3f8ea514b41d30b7cdbea4d1939ec72becdb48752bfa5d24339a68e8&=&format=webp&quality=lossless",
        "mensagem": """Olá, {usuario}.
Seu atendimento foi registrado na **Família Royal**.

**Como funciona**
> `📝` Explique a sua dúvida ou pedido com detalhes.
> `📎` Se puder, envie prints ou vídeos que ajudem.
> `⏳` Aguarde um momento — a equipe já foi avisada.
""",
        "perguntas": [
            {
                "label": "Qual é o assunto?",
                "placeholder": "Resuma em poucas palavras",
                "longo": False,
                "obrigatorio": True,
            },
            {
                "label": "Descreva o que você precisa",
                "placeholder": "Explique com o máximo de detalhes possível...",
                "longo": True,
                "obrigatorio": True,
            },
        ],
        "decisao": False,
        "cargo_ao_aprovar": None,
        "cargos_ping": [],
        "categoria_discord_id": None,
    },
}

BANNERS_CATEGORIAS = {
    "denuncia": os.getenv("ROYAL_BANNER_DENUNCIA_URL", "").strip() or BANNER_TICKET_PADRAO,
    "cargo_eb": os.getenv("ROYAL_BANNER_CARGO_EB_URL", "").strip() or BANNER_TICKET_PADRAO,
    "parceria": os.getenv("ROYAL_BANNER_PARCERIA_URL", "").strip() or BANNER_TICKET_PADRAO,
    "outros": os.getenv("ROYAL_BANNER_OUTROS_URL", "").strip() or BANNER_TICKET_PADRAO,
}

for _chave, _banner in BANNERS_CATEGORIAS.items():
    if _chave in CATEGORIAS and _banner:
        CATEGORIAS[_chave]["banner"] = _banner

PASTA_DADOS = "dados_tickets"
os.makedirs(PASTA_DADOS, exist_ok=True)
F_CONTADOR = os.path.join(PASTA_DADOS, "contador.json")
F_ESTADOS = os.path.join(PASTA_DADOS, "tickets_abertos.json")
F_HISTORICO = os.path.join(PASTA_DADOS, "historico.json")
F_AVALIACOES = os.path.join(PASTA_DADOS, "avaliacoes.json")
F_BLOQUEIOS = os.path.join(PASTA_DADOS, "bloqueados.json")
F_TEMA = os.path.join(PASTA_DADOS, "tema.json")
F_PAINEIS = os.path.join(PASTA_DADOS, "paineis.json")

for _antigo, _novo in (
    ("tickets_contador.json", F_CONTADOR),
    ("tickets_avaliacoes.json", F_AVALIACOES),
):
    if os.path.exists(_antigo) and not os.path.exists(_novo):
        os.replace(_antigo, _novo)

CANAIS_FECHANDO: set[int] = set()
CRIANDO: set[int] = set()
COOLDOWN_CHAMAR: dict[int, float] = {}

SQL_KV = """
CREATE TABLE IF NOT EXISTS tickets_kv (
    chave TEXT PRIMARY KEY,
    valor JSONB NOT NULL,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
SQL_KV_UPSERT = """
INSERT INTO tickets_kv (chave, valor) VALUES ($1, $2::jsonb)
ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()
"""

_CACHE: dict[str, object] = {}
_POOL = None
_PENDENTES: set[str] = set()
_TAREFAS: set[asyncio.Task] = set()
_VERSOES: dict[str, int] = {}
_CONFIRMADAS: dict[str, int] = {}
_TRAVAS_DB: dict[str, asyncio.Lock] = {}

SQL_ARQUIVOS = """
CREATE TABLE IF NOT EXISTS royal_tickets_transcripts (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    ticket_no BIGINT NOT NULL,
    owner_id BIGINT NOT NULL,
    fechado_por BIGINT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    protocolo TEXT NOT NULL,
    arquivo_html BYTEA NOT NULL,
    confidencial BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_royal_transcripts_owner
ON royal_tickets_transcripts (guild_id, owner_id, criado_em DESC);
"""
SQL_REVIEWS = """
CREATE TABLE IF NOT EXISTS royal_tickets_reviews (
    guild_id BIGINT NOT NULL,
    ticket_no BIGINT NOT NULL,
    owner_id BIGINT NOT NULL,
    staff_id BIGINT,
    categoria TEXT NOT NULL,
    nota SMALLINT NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario TEXT NOT NULL DEFAULT '',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (guild_id, ticket_no)
);
"""
SQL_NATAL = """
CREATE TABLE IF NOT EXISTS royal_tickets_cartas_natal (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    remetente_id BIGINT NOT NULL,
    destinatario_id BIGINT NOT NULL,
    mensagem TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    aprovado_por BIGINT,
    entrega_em TIMESTAMPTZ,
    entregue_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_royal_cartas_entrega
ON royal_tickets_cartas_natal (status, entrega_em);
"""


def tema_atual() -> str:
    atual = _ler_json(F_TEMA, {"tema": TEMA_PADRAO}).get("tema", TEMA_PADRAO)
    return atual if atual in ("natal", "classico") else "natal"


def cor_tema() -> int:
    return COR_NATAL_VERDE if tema_atual() == "natal" else COR_AZUL


def descricao_tema() -> str:
    return PAINEL_DESCRICAO if tema_atual() == "natal" else PAINEL_DESCRICAO_CLASSICO


def banner_tema(chave: str | None = None) -> str | None:
    if tema_atual() == "natal":
        env_key = chave.upper() if chave else None
        url = BANNERS_NATAL.get(env_key, "") if env_key else BANNER_NATAL
        if banner_valido(url):
            return url
    if chave:
        return CATEGORIAS.get(chave, {}).get("banner") or BANNER_TICKET_PADRAO
    return BANNER_PRINCIPAL


def ticket_confidencial(t: dict) -> bool:
    if t.get("confidencial"):
        return True
    return t.get("cat") == "denuncia" and any(
        label == "Tipo da denúncia" and valor == "Membro da staff"
        for label, valor in t.get("respostas", [])
    )


def autorizado_no_ticket(membro, t: dict) -> bool:
    if not isinstance(membro, discord.Member):
        return False
    if ticket_confidencial(t):
        if membro.id == membro.guild.owner_id:
            return True
        return any(r.id in CARGOS_CORREGEDORIA for r in membro.roles)
    return eh_staff(membro)


def ticket_status(t: dict) -> str:
    valor = t.get("status") or ("em_analise" if t.get("claim") else "aguardando")
    return valor if valor in STATUS_TICKET else "aguardando"


STATUS_TICKET = {
    "aguardando": ("⏳", "Aguardando equipe"),
    "em_analise": ("🔎", "Em análise"),
    "aguardando_usuario": ("✉️", "Aguardando solicitante"),
    "concluido": ("✅", "Concluído"),
    "suspenso": ("🔒", "Solicitante ausente"),
}


def _ler_json(caminho: str, padrao):
    chave = os.path.basename(caminho)
    if chave in _CACHE:
        return copy.deepcopy(_CACHE[chave])
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return padrao


async def _persistir_versao(chave: str):
    if _POOL is None:
        return False
    trava = _TRAVAS_DB.setdefault(chave, asyncio.Lock())
    async with trava:
        atual = _VERSOES.get(chave, 0)
        if atual <= _CONFIRMADAS.get(chave, -1):
            return True
        dados = json.dumps(_CACHE.get(chave), ensure_ascii=False)
        await _POOL.execute(SQL_KV_UPSERT, chave, dados)
        _CONFIRMADAS[chave] = atual
        return True


async def _persistir(chave: str):
    try:
        await asyncio.sleep(0.2)
        for _ in range(50):
            if await _persistir_versao(chave):
                if _CONFIRMADAS.get(chave, -1) >= _VERSOES.get(chave, 0):
                    break
            else:
                break
    except Exception:
        LOG.exception("Erro ao salvar '%s' no PostgreSQL", chave)
    finally:
        _PENDENTES.discard(chave)


def _agendar_persistencia(chave: str):
    if _POOL is None or chave in _PENDENTES:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _PENDENTES.add(chave)
    tarefa = loop.create_task(_persistir(chave))
    _TAREFAS.add(tarefa)
    tarefa.add_done_callback(_TAREFAS.discard)


def _salvar_json(caminho: str, dados):
    chave = os.path.basename(caminho)
    _CACHE[chave] = copy.deepcopy(dados)
    _VERSOES[chave] = _VERSOES.get(chave, 0) + 1
    try:
        tmp = caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, caminho)
    except OSError:
        LOG.warning("Impossível gravar cache local '%s'", chave)
    _agendar_persistencia(chave)


async def confirmar_gravacao(*caminhos: str) -> bool:
    """Confirma em PostgreSQL antes de responder uma ação crítica."""
    if _POOL is None:
        return False
    try:
        for caminho in caminhos:
            chave = os.path.basename(caminho)
            for _ in range(5):
                if not await _persistir_versao(chave):
                    return False
                if _CONFIRMADAS.get(chave, -1) >= _VERSOES.get(chave, 0):
                    break
            else:
                return False
        return True
    except Exception:
        LOG.exception("Falha ao confirmar persistência de %s", caminhos)
        return False


async def carregar_armazenamento(bot: commands.Bot) -> bool:
    """Carrega os dados do PostgreSQL (e migra os arquivos locais, se houver)."""
    global _POOL
    pool = getattr(bot, "pool", None)
    if pool is None:
        print(
            "[tickets] AVISO: bot.pool não existe — os dados ficam só em arquivos "
            "locais e podem ser perdidos em um novo deploy."
        )
        return False
    try:
        await pool.execute(SQL_KV)
        await pool.execute(SQL_ARQUIVOS)
        await pool.execute("ALTER TABLE royal_tickets_transcripts ADD COLUMN IF NOT EXISTS confidencial BOOLEAN NOT NULL DEFAULT FALSE")
        await pool.execute(SQL_REVIEWS)
        await pool.execute(SQL_NATAL)
        for r in await pool.fetch("SELECT chave, valor FROM tickets_kv"):
            valor = r["valor"]
            _CACHE[r["chave"]] = json.loads(valor) if isinstance(valor, str) else valor
        for caminho in (F_CONTADOR, F_ESTADOS, F_HISTORICO, F_AVALIACOES, F_BLOQUEIOS, F_TEMA, F_PAINEIS):
            chave = os.path.basename(caminho)
            if chave not in _CACHE and os.path.exists(caminho):
                dados = _ler_json(caminho, None)
                if dados is not None:
                    _CACHE[chave] = dados
                    await pool.execute(SQL_KV_UPSERT, chave, json.dumps(dados, ensure_ascii=False))
                    print(f"[tickets] '{chave}' migrado para o PostgreSQL.")
        # Conciliar avaliações já confirmadas na tabela dedicada com o cache
        # legado. Isto protege o ranking se houve uma falha no JSONB após o INSERT.
        chave_av = os.path.basename(F_AVALIACOES)
        atuais = list(_CACHE.get(chave_av) or [])
        existentes = {(a.get("guild_id"), a.get("ticket")) for a in atuais}
        novos = await pool.fetch("""
            SELECT guild_id, ticket_no, owner_id, staff_id, categoria,
                   nota, comentario, EXTRACT(EPOCH FROM criado_em)::BIGINT AS ts
            FROM royal_tickets_reviews
        """)
        alterou = False
        for a in novos:
            ident = (a["guild_id"], a["ticket_no"])
            if ident in existentes:
                continue
            atuais.append({
                "guild_id": a["guild_id"], "ticket": a["ticket_no"],
                "usuario": a["owner_id"], "staff": a["staff_id"] or 0,
                "categoria": a["categoria"], "nota": a["nota"],
                "comentario": a["comentario"], "ts": a["ts"],
                "data": datetime.fromtimestamp(a["ts"], FUSO).strftime("%d/%m/%Y %H:%M:%S"),
            })
            existentes.add(ident)
            alterou = True
        if alterou:
            _CACHE[chave_av] = atuais
            await pool.execute(SQL_KV_UPSERT, chave_av,
                               json.dumps(atuais, ensure_ascii=False))
        _POOL = pool
        for chave in _CACHE:
            _CONFIRMADAS[chave] = _VERSOES.get(chave, 0)
        print("[tickets] Armazenamento no PostgreSQL ativo.")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[tickets] ERRO ao preparar o PostgreSQL: {type(e).__name__}: {e}")
        return False


async def proximo_numero() -> int:
    """Contador atômico no banco: evita protocolos duplicados entre reinícios."""
    if _POOL is None:
        raise RuntimeError("PostgreSQL indisponível para gerar protocolo")
    registro = await _POOL.fetchrow("""
        INSERT INTO tickets_kv (chave, valor)
        VALUES ($1, '{"contador": 1}'::jsonb)
        ON CONFLICT (chave) DO UPDATE
        SET valor = jsonb_build_object('contador',
                      COALESCE((tickets_kv.valor->>'contador')::BIGINT, 0) + 1),
            atualizado_em = now()
        RETURNING (valor->>'contador')::BIGINT AS numero
    """, os.path.basename(F_CONTADOR))
    numero = int(registro["numero"])
    _CACHE[os.path.basename(F_CONTADOR)] = {"contador": numero}
    return numero


def estados() -> dict:
    return _ler_json(F_ESTADOS, {})


def salvar_estado(canal_id: int, **campos) -> dict:
    dados = estados()
    est = dados.setdefault(str(canal_id), {})
    est.update(campos)
    _salvar_json(F_ESTADOS, dados)
    return est


def remover_estado(canal_id):
    dados = estados()
    if str(canal_id) in dados:
        dados.pop(str(canal_id))
        _salvar_json(F_ESTADOS, dados)


def salvar_avaliacao(registro: dict):
    dados = _ler_json(F_AVALIACOES, [])
    dados.append(registro)
    _salvar_json(F_AVALIACOES, dados)


def registrar_historico(registro: dict):
    dados = _ler_json(F_HISTORICO, [])
    dados.append(registro)
    _salvar_json(F_HISTORICO, dados)


def ler_topico(canal) -> dict:
    """O tópico guarda (só na criação): owner=ID;cat=chave;num=N"""
    info = {}
    if getattr(canal, "topic", None):
        for parte in canal.topic.split(";"):
            if "=" in parte:
                k, v = parte.split("=", 1)
                info[k.strip()] = v.strip()
    return info


def ler_ticket(canal, cache: dict | None = None) -> dict:
    """Dados do ticket (estado salvo + tópico). Retorna {} se não for ticket."""
    info = ler_topico(canal)
    if not info.get("owner") and str(canal.id) not in (cache or estados()):
        return {}
    t = {
        "owner": int(info["owner"]) if info.get("owner") else None,
        "cat": info.get("cat", ""),
        "num": int(info.get("num", 0) or 0),
        "prio": "normal",
        "claim": int(info["claim"]) if info.get("claim") else None,
        "claim_ts": None,
        "locked": False,
        "decisao": None,
        "respostas": [],
        "notas": [],
        "card_id": None,
    }
    t.update((cache if cache is not None else estados()).get(str(canal.id), {}))
    return t if t.get("owner") else {}


def listar_tickets(guild: discord.Guild) -> list[tuple[discord.TextChannel, dict]]:
    cache = estados()
    out = []
    for c in guild.text_channels:
        t = ler_ticket(c, cache)
        if t:
            out.append((c, t))
    return out

def eh_staff(membro) -> bool:
    """Staff = quem tem a permissão Administrador (em qualquer cargo, ou o dono
    do servidor) OU algum dos cargos de CARGOS_STAFF."""
    if not isinstance(membro, discord.Member):
        return False
    if membro.guild_permissions.administrator:
        return True
    ids = {r.id for r in membro.roles}
    return any(c in ids for c in CARGOS_STAFF)


def apenas_staff():
    async def predicate(ctx: commands.Context):
        if eh_staff(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def agora() -> str:
    return datetime.now(FUSO).strftime("%d/%m/%Y %H:%M:%S")


def banner_valido(url) -> bool:
    if not url or "link_do_banner" in str(url):
        return False
    p = urlparse(str(url))
    if p.scheme not in ("https", "http") or not p.netloc:
        return False
    expiracao = parse_qs(p.query).get("ex", [None])[0]
    if expiracao:
        try:
            if int(expiracao, 16) < int(time.time()) + 60:
                return False
        except ValueError:
            return False
    return True


def estrelas(nota: int) -> str:
    return "⭐" * nota + "☆" * (5 - nota)


def slug(texto: str, limite: int = 20) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:limite].strip("-")


def nome_canal(chave: str, respostas: list, numero: int) -> str:
    """Ex.: cargo-eb-cgex-0007 (a escolha do menu entra no nome do canal)."""
    partes = [chave.replace("_", "-")]
    esc = CATEGORIAS.get(chave, {}).get("escolha")
    if esc and respostas and respostas[0][0] == esc["label"]:
        extra = slug(respostas[0][1])
        if extra:
            partes.append(extra)
    partes.append(f"{numero:04d}")
    return "-".join(partes)[:90]


def protocolo_de(criado_em: datetime, numero: int) -> str:
    """Protocolo único do atendimento. Ex.: ROYAL-2610-0042"""
    d = criado_em.astimezone(FUSO)
    return f"ROYAL-{d.year % 100:02d}{d.month:02d}-{numero:04d}"


def formatar_duracao(seg: float) -> str:
    seg = int(seg)
    d, seg = divmod(seg, 86400)
    h, seg = divmod(seg, 3600)
    m, _ = divmod(seg, 60)
    partes = []
    if d:
        partes.append(f"{d}d")
    if h:
        partes.append(f"{h}h")
    if m:
        partes.append(f"{m}min")
    return " ".join(partes) or "<1min"


def cargos_para_notificar(chave: str) -> list[int]:
    ids = list(CARGOS_NOTIFICAR) + list(CATEGORIAS.get(chave, {}).get("cargos_ping", []))
    return list(dict.fromkeys(ids))


def resolver_categoria(guild, cat: dict, fallback):
    for cid in (cat.get("categoria_discord_id"), CATEGORIA_TICKETS_ID):
        if cid:
            c = guild.get_channel(cid)
            if isinstance(c, discord.CategoryChannel):
                return c
    return fallback


async def buscar_membro(bot, guild: discord.Guild, user_id: int):
    m = guild.get_member(user_id)
    if m:
        return m
    try:
        return await guild.fetch_member(user_id)
    except discord.HTTPException:
        pass
    try:
        return await bot.fetch_user(user_id)
    except discord.HTTPException:
        return None


async def registrar(guild: discord.Guild, titulo: str, descricao: str, cor=None,
                    *, confidencial: bool = False):
    """Registra ações gerais, sem publicar conteúdo sensível em canal comum."""
    if not confidencial:
        confidencial = any(
            ticket_confidencial(t) and (c.mention in descricao or str(c.id) in descricao)
            for c, t in listar_tickets(guild)
        )
    if confidencial:
        descricao = "🔒 Ação em denúncia confidencial; detalhes disponíveis apenas no próprio ticket."
    canal = guild.get_channel(CANAL_LOGS_ID) if CANAL_LOGS_ID else None
    if not canal:
        return
    try:
        await canal.send(
            embed=discord.Embed(
                title=titulo,
                description=descricao,
                color=cor if cor is not None else cor_tema(),
                timestamp=datetime.now(FUSO),
            )
        )
    except discord.HTTPException:
        pass


async def aviso_no_ticket(canal: discord.TextChannel, texto: str, cor=COR_AZUL):
    try:
        await canal.send(embed=discord.Embed(description=texto, color=cor))
    except discord.HTTPException:
        pass


def checar_pode_abrir(guild: discord.Guild, user: discord.abc.User) -> str | None:
    bloqueios = _ler_json(F_BLOQUEIOS, {})
    if str(user.id) in bloqueios:
        motivo = bloqueios[str(user.id)].get("motivo", "Não informado")
        return f"🚫 Você está bloqueado de abrir tickets.\n**Motivo:** {motivo}"
    abertos = [c for c, t in listar_tickets(guild) if t.get("owner") == user.id]
    if len(abertos) >= MAX_TICKETS_POR_USUARIO:
        return f"❌ Você já possui um ticket aberto: {abertos[0].mention}"
    return None


def validar_resposta(tipo: str, valor: str) -> str | None:
    """Retorna uma mensagem de erro (ou None se estiver tudo certo)."""
    if tipo == "convite":
        if not re.search(
            r"(?:discord\.gg|discord(?:app)?\.com/invite)/[\w-]+", valor, re.IGNORECASE
        ):
            return "o link precisa ser um convite do Discord (ex.: https://discord.gg/abc123)"
    elif tipo == "numero":
        if not re.fullmatch(r"\d[\d.,\s]*", valor):
            return "informe apenas números (ex.: 500)"
    return None


def minutos_uteis(desde: datetime, ate: datetime | None = None) -> int:
    """Relógio de atendimento baseado nos horários publicados no painel."""
    ate = (ate or datetime.now(timezone.utc)).astimezone(FUSO)
    desde = desde.astimezone(FUSO)
    if ate <= desde:
        return 0
    total = 0
    dia = desde.date()
    while dia <= ate.date():
        fim_dia = 18 if dia.weekday() >= 5 else 22
        inicio_dia = 11 if dia.weekday() >= 5 else 9
        abertura = datetime.combine(dia, datetime.min.time(), FUSO).replace(hour=inicio_dia)
        fechamento = datetime.combine(dia, datetime.min.time(), FUSO).replace(hour=fim_dia)
        inicio = max(abertura, desde)
        fim = min(fechamento, ate)
        if fim > inicio:
            total += int((fim - inicio).total_seconds() // 60)
        dia += timedelta(days=1)
    return total


def fila_ordenada(guild: discord.Guild):
    tickets = listar_tickets(guild)
    nivel = {"urgente": 0, "alta": 1, "normal": 2, "baixa": 3}
    return sorted(tickets, key=lambda x: (
        x[1].get("claim") is not None,
        nivel.get(x[1].get("prio", "normal"), 2),
        x[0].created_at,
    ))


def resumo_7_dias(guild: discord.Guild, dias: int = 7) -> discord.Embed:
    limite = time.time() - dias * 86400
    historico = [h for h in _ler_json(F_HISTORICO, [])
                 if h.get("fechado_ts", 0) >= limite
                 and h.get("guild_id", guild.id) == guild.id]
    abertos = listar_tickets(guild)
    esperas = [h["espera_seg"] for h in historico if h.get("espera_seg") is not None]
    duracoes = [h.get("duracao_seg", 0) for h in historico]
    avaliacoes = [a for a in _ler_json(F_AVALIACOES, [])
                  if a.get("guild_id", guild.id) == guild.id
                  and a.get("ts", 0) >= limite]
    espera = formatar_duracao(sum(esperas) / len(esperas)) if esperas else "—"
    duracao = formatar_duracao(sum(duracoes) / len(duracoes)) if duracoes else "—"
    avaliacao = f"{sum(a['nota'] for a in avaliacoes)/len(avaliacoes):.2f}/5" if avaliacoes else "—"
    e = discord.Embed(title=f"📑 Relatório Royal — últimos {dias} dias", color=cor_tema())
    e.description = "\n".join((
        f"> `📬` **Abertos agora:** {len(abertos)}",
        f"> `⏳` **Sem responsável:** {sum(not t.get('claim') for _, t in abertos)}",
        f"> `✅` **Finalizados:** {len(historico)}",
        f"> `⌛` **Espera média:** {espera}",
        f"> `🕒` **Duração média:** {duracao}",
        f"> `⭐` **Avaliação média:** {avaliacao}",
    ))
    return e


def media_espera() -> float | None:
    """Tempo médio (seg) até um atendente assumir, pelos últimos tickets fechados."""
    hist = _ler_json(F_HISTORICO, [])
    vals = [h["espera_seg"] for h in hist[-30:] if h.get("espera_seg") is not None]
    return sum(vals) / len(vals) if vals else None


def posicao_na_fila(guild: discord.Guild, canal: discord.TextChannel) -> int:
    pos = 1
    for c, t in listar_tickets(guild):
        if c.id != canal.id and not t.get("claim") and c.created_at < canal.created_at:
            pos += 1
    return pos


def montar_card(guild: discord.Guild, canal, t: dict) -> discord.Embed:
    cat = CATEGORIAS.get(t["cat"], {})
    p_emoji, p_nome = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])
    proto = protocolo_de(canal.created_at, t["num"])

    cabecalho = (
        f"**{cat.get('emoji', '🎫')} {cat.get('nome', 'Ticket')} • `{proto}`**"
    )
    mensagem = cat.get("mensagem", "").replace("{usuario}", f"<@{t['owner']}>").strip()
    partes = [f"{cabecalho}\n{mensagem}"]

    # Seção: solicitação do usuário (respostas do formulário)
    respostas = t.get("respostas", [])
    if respostas:
        blocos = []
        for label, valor in respostas:
            linhas = [f"> `📝` **{label}**"]
            linhas += [f"> {l}" if l.strip() else ">" for l in valor.splitlines()]
            blocos.append("\n".join(linhas))
        partes.append("**Sua solicitação**\n" + "\n>\n".join(blocos))

    # Seção: atendimento (só mostra o que é relevante)
    linhas = [
        f"> `🙋` Atendente: <@{t['claim']}>"
        if t.get("claim")
        else "> `⏳` Aguardando um atendente"
    ]
    if t.get("prio", "normal") != "normal":
        linhas.append(f"> `{p_emoji}` Prioridade **{p_nome}**")
    if t.get("locked"):
        linhas.append("> `🔒` Ticket trancado pela equipe")
    partes.append("**Atendimento**\n" + "\n".join(linhas))

    # Seção: decisão (cargos e parcerias)
    dec = t.get("decisao")
    if dec:
        aprovado = dec.get("status") == "aprovado"
        linhas = [
            f"> `{'✅' if aprovado else '❌'}` **{'Aprovado' if aprovado else 'Recusado'}** "
            f"por <@{dec.get('por')}> • <t:{dec.get('ts', 0)}:R>"
        ]
        if dec.get("motivo"):
            linhas.append(f"> `💬` {dec['motivo']}")
        partes.append("**Decisão**\n" + "\n".join(linhas))

    embed = discord.Embed(
        description="\n\n".join(partes)[:4096],
        color=cat.get("cor", COR_AZUL),
        timestamp=canal.created_at,
    )
    if banner_valido(cat.get("banner")):
        embed.set_image(url=cat["banner"])
    embed.set_footer(text=f"{NOME_SERVIDOR} • {proto}")
    return embed


def criar_card_v2(canal: discord.TextChannel, t: dict) -> discord.ui.LayoutView:
    """Cartão persistente do atendimento, com identidade visual Royal."""
    cat = CATEGORIAS.get(t.get("cat", ""), {})
    controles = TicketControls(
        assumido=bool(t.get("claim")),
        decisao=bool(cat.get("decisao")),
        decidido=bool(t.get("decisao")),
    )
    proto = protocolo_de(canal.created_at, int(t.get("num", 0)))
    nome = cat.get("nome", "Atendimento")
    banner_ticket = banner_tema(t.get("cat"))

    blocos = []
    if banner_valido(banner_ticket):
        blocos.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner_ticket)))
        blocos.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

    linhas = [
        f"## {'🎄' if tema_atual() == 'natal' else '⚜️'} {nome.upper()}",
        f"> `📋` Protocolo: **{proto}**",
        f"> `👤` Solicitante: <@{t['owner']}>",
        f"> `🛡️` Responsável: " + (f"<@{t['claim']}>" if t.get("claim") else "Aguardando a equipe"),
        f"> `📌` Etapa: **{STATUS_TICKET[ticket_status(t)][0]} {STATUS_TICKET[ticket_status(t)][1]}**",
    ]
    if t.get("prio", "normal") != "normal":
        linhas.append(f"> `⚑` Prioridade: **{PRIORIDADES.get(t['prio'], PRIORIDADES['normal'])[1]}**")
    if t.get("locked"):
        linhas.append("> `🔒` Atendimento restrito pela equipe")
    blocos.append(discord.ui.TextDisplay("\n".join(linhas)))
    blocos.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

    if cat.get("mensagem"):
        texto = cat["mensagem"].replace("{usuario}", f"<@{t['owner']}>").strip()
        blocos.extend(discord.ui.TextDisplay(p) for p in dividir_texto_card(texto))

    respostas = t.get("respostas", [])
    if respostas:
        blocos.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        blocos.append(discord.ui.TextDisplay("**📜 INFORMAÇÕES DA SOLICITAÇÃO**"))
        texto = "\n".join(
            f"> **{str(label)}**\n> {str(valor).replace(chr(10), chr(10) + '> ')}"
            for label, valor in respostas
        )
        if len(texto) > 2300:
            texto = texto[:2300].rstrip() + "\n> -# Solicitação resumida no cartão; dados completos disponíveis no histórico."
        blocos.extend(discord.ui.TextDisplay(p) for p in dividir_texto_card(texto))

    decisao = t.get("decisao")
    if decisao:
        blocos.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        situacao = "APROVADA" if decisao.get("status") == "aprovado" else "RECUSADA"
        justificativa = str(decisao.get("motivo") or "Sem justificativa adicional.")
        blocos.append(discord.ui.TextDisplay(
            f"**⚖️ DELIBERAÇÃO — {situacao}**\n"
            f"> Responsável: <@{decisao.get('por', 0)}>\n"
            f"> {justificativa[:450]}"
        ))

    blocos.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    botoes = list(controles.children)
    for inicio in range(0, len(botoes), 5):
        linha = discord.ui.ActionRow()
        for botao in botoes[inicio:inicio + 5]:
            botao._view = None
            linha.add_item(botao)
        blocos.append(linha)

    blocos.append(discord.ui.TextDisplay(
        "-# <a:animated_Settings:1556187476177981440> Família Royal"
    ))
    layout = TicketCardV2(controles)
    layout.add_item(discord.ui.Container(*blocos, accent_colour=discord.Colour(cor_tema())))
    return layout


def dividir_texto_card(texto: str, limite: int = 3500) -> list[str]:
    partes = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip()
    if texto:
        partes.append(texto)
    return partes


class TicketCardV2(discord.ui.LayoutView):
    """Ações preservadas no próprio LayoutView persistente."""

    def __init__(self, controles: "TicketControls"):
        super().__init__(timeout=None)
        self.controles = controles

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.controles.interaction_check(interaction)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        LOG.error("Erro no botão V2 de ticket", exc_info=(type(error), error, error.__traceback__))
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Falha ao executar ação. Avise a equipe.", ephemeral=True)


async def atualizar_card(canal: discord.TextChannel) -> bool:
    """Atualiza V2 sem recriar cartão ou perder os botões."""
    t = ler_ticket(canal)
    if not t:
        return False
    view = criar_card_v2(canal, t)
    card_id = t.get("card_id")
    if card_id:
        try:
            msg = await canal.fetch_message(int(card_id))
            if msg.flags.value & (1 << 15):
                await msg.edit(view=view, allowed_mentions=discord.AllowedMentions.none())
                return True
            LOG.warning("Cartão antigo %s não é V2; publicando substituto", card_id)
        except discord.NotFound:
            LOG.warning("Cartão %s removido; criando outro", card_id)
        except discord.HTTPException:
            LOG.exception("Falha ao editar cartão V2 no canal %s", canal.id)
            return False
    try:
        novo = await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        salvar_estado(canal.id, card_id=novo.id)
        return True
    except discord.HTTPException:
        LOG.exception("Falha ao publicar cartão V2 no canal %s", canal.id)
        return False


async def gerar_transcript_html(canal: discord.TextChannel, t: dict) -> tuple[str, int]:
    linhas = []
    total = 0
    async for msg in canal.history(limit=None, oldest_first=True):
        total += 1
        hora = msg.created_at.astimezone(FUSO).strftime("%d/%m/%Y %H:%M:%S")
        conteudo = html.escape(msg.clean_content).replace("\n", "<br>")
        extras = ""
        for a in msg.attachments:
            extras += (
                f'<div class="anexo">📎 <a href="{html.escape(a.url)}" '
                f'target="_blank">{html.escape(a.filename)}</a></div>'
            )
        for e in msg.embeds:
            if e.title or e.description or e.fields:
                corpo = f"<b>{html.escape(e.title or '')}</b><br>"
                corpo += html.escape(e.description or "").replace("\n", "<br>")
                for f in e.fields:
                    corpo += (
                        f"<br><b>{html.escape(f.name)}</b>: "
                        f"{html.escape(f.value).replace(chr(10), '<br>')}"
                    )
                extras += f'<div class="embed">{corpo}</div>'
        linhas.append(
            f'<div class="msg"><img src="{msg.author.display_avatar.url}">'
            f'<div><span class="autor">{html.escape(str(msg.author))}</span> '
            f'<span class="hora">{hora}</span><br>{conteudo}{extras}</div></div>'
        )

    cat = CATEGORIAS.get(t.get("cat", ""), {}).get("nome", "—")
    proto = protocolo_de(canal.created_at, int(t.get("num", 0) or 0))
    pagina = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Logs — {html.escape(canal.name)}</title>
<style>
body{{background:#191712;color:#f1eadf;font-family:Segoe UI,Arial,sans-serif;margin:0;padding:20px}}
h1{{color:#fff;margin-bottom:0}} .sub{{color:#bca782;margin-bottom:20px}}
.msg{{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #403729}}
.msg img{{width:40px;height:40px;border-radius:50%}}
.autor{{color:#fff;font-weight:600}} .hora{{color:#bca782;font-size:12px}}
.anexo{{margin-top:4px;font-size:13px}} a{{color:#e7c990}}
.embed{{border-left:4px solid #b8904f;background:#282319;padding:6px 10px;margin-top:4px;border-radius:4px}}
</style></head><body>
<h1>📑 {html.escape(NOME_SERVIDOR)} — Logs do Ticket</h1>
<div class="sub">Protocolo: {html.escape(proto)} · Canal: #{html.escape(canal.name)} ·
Categoria: {html.escape(cat)} · Mensagens: {total} · Gerado em {agora()}</div>
{''.join(linhas)}
</body></html>"""
    return pagina, total


async def fechar_ticket(
    bot: commands.Bot,
    canal: discord.TextChannel,
    quem_fechou: discord.Member,
    motivo: str,
):
    if canal.id in CANAIS_FECHANDO:
        return
    CANAIS_FECHANDO.add(canal.id)
    apagado = False

    try:
        guild = canal.guild
        t = ler_ticket(canal)
        dono_id = t.get("owner")
        dono = await buscar_membro(bot, guild, dono_id) if dono_id else None
        cat_key = t.get("cat", "")
        cat = CATEGORIAS.get(cat_key, {})
        numero = int(t.get("num", 0) or 0)
        proto = protocolo_de(canal.created_at, numero)
        staff_id = int(t.get("claim") or 0)
        p_emoji, p_nome = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])
        duracao = (datetime.now(timezone.utc) - canal.created_at).total_seconds()
        espera = None
        if t.get("claim_ts"):
            espera = max(0, int(t["claim_ts"] - canal.created_at.timestamp()))
        dec = t.get("decisao") or {}

        await aviso_no_ticket(
            canal,
            f"🔒 Encerramento solicitado por {quem_fechou.mention}.\n"
            "Confirmando o arquivamento dos registros antes de encerrar o canal.",
            COR_AZUL_CLARO,
        )

        pagina, total_msgs = await gerar_transcript_html(canal, t)
        dados = pagina.encode("utf-8")
        nome_arquivo = f"logs_{canal.name}.html"
        confidencial = ticket_confidencial(t)
        if len(dados) > MAX_TRANSCRICAO_BYTES:
            LOG.error("Transcrição muito grande (%s bytes), ticket %s preservado", len(dados), canal.id)
            await aviso_no_ticket(canal, "⚠️ O histórico excedeu o limite seguro de arquivamento. O canal foi preservado. Solicite suporte administrativo.")
            return False

        salvo_no_banco = False
        if _POOL is not None:
            try:
                await _POOL.execute("""
                    INSERT INTO royal_tickets_transcripts
                    (guild_id, channel_id, ticket_no, owner_id, fechado_por,
                     protocolo, arquivo_html, confidencial)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT (guild_id, channel_id) DO UPDATE
                    SET arquivo_html=EXCLUDED.arquivo_html,
                        fechado_por=EXCLUDED.fechado_por,
                        confidencial=EXCLUDED.confidencial
                """, guild.id, canal.id, numero, dono_id, quem_fechou.id,
                     proto, dados, confidencial)
                salvo_no_banco = True
            except Exception:
                LOG.exception("Falha ao arquivar transcrição %s no PostgreSQL", canal.id)

        def base_embed() -> discord.Embed:
            e = discord.Embed(
                title=f"📑 Ticket #{numero:04d} Fechado",
                color=cat.get("cor", COR_AZUL),
                timestamp=datetime.now(FUSO),
            )
            e.add_field(name="Protocolo", value=f"`{proto}`", inline=True)
            e.add_field(name="Ticket", value=f"`{canal.name}`", inline=True)
            e.add_field(name="Categoria", value=cat.get("nome", "—"), inline=True)
            e.add_field(
                name="Aberto por",
                value=dono.mention if dono else f"<@{dono_id}>",
                inline=True,
            )
            e.add_field(name="Fechado por", value=quem_fechou.mention, inline=True)
            e.add_field(
                name="Atendente",
                value=f"<@{staff_id}>" if staff_id else "Ninguém",
                inline=True,
            )
            e.add_field(name="Duração", value=formatar_duracao(duracao), inline=True)
            if dec:
                ok = dec.get("status") == "aprovado"
                e.add_field(
                    name="Decisão",
                    value=("✅ Aprovado" if ok else "❌ Recusado"),
                    inline=True,
                )
            e.add_field(name="Motivo", value=motivo or "Não informado", inline=False)
            e.set_footer(text=NOME_SERVIDOR)
            return e

        # Log completo para a staff: UMA mensagem (embed + arquivo)
        embed_staff = base_embed()
        embed_staff.insert_field_at(
            5, name="Prioridade", value=f"{p_emoji} {p_nome}", inline=True
        )
        embed_staff.add_field(name="Mensagens", value=str(total_msgs), inline=True)
        if dec.get("motivo"):
            embed_staff.add_field(
                name="Motivo da decisão", value=dec["motivo"][:1024], inline=False
            )
        notas = t.get("notas", [])
        if notas:
            texto_notas = "\n".join(f"• **{n['autor']}**: {n['texto']}" for n in notas)
            embed_staff.add_field(
                name="📝 Notas internas", value=texto_notas[:1024], inline=False
            )
        canal_logs = guild.get_channel(CANAL_LOGS_ID) if CANAL_LOGS_ID else None
        # Denúncias internas jamais enviam suas transcrições para logs comuns.
        logs_enviados = False
        privado = (canal_logs and not canal_logs.permissions_for(guild.default_role).view_channel)
        if canal_logs and privado and not confidencial:
            try:
                await canal_logs.send(
                    embed=embed_staff,
                    file=discord.File(io.BytesIO(dados), filename=nome_arquivo),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                logs_enviados = True
            except discord.HTTPException:
                LOG.exception("Falha ao publicar transcrição no canal staff")

        if not salvo_no_banco and not logs_enviados:
            await aviso_no_ticket(canal,
                "⚠️ Falha no arquivamento seguro. O ticket NÃO será apagado. "
                "Verifique PostgreSQL e permissões do canal de logs.")
            return False

        registrar_historico(
            {
                "num": numero,
                "guild_id": guild.id,
                "protocolo": proto,
                "cat": cat_key,
                "owner": dono_id,
                "claim": staff_id,
                "prio": t.get("prio", "normal"),
                "duracao_seg": int(duracao),
                "espera_seg": espera,
                "decisao": dec.get("status") if dec else None,
                "mensagens": total_msgs,
                "fechado_por": quem_fechou.id,
                "motivo": motivo,
                "fechado_ts": int(time.time()),
            }
        )

        if not await confirmar_gravacao(F_HISTORICO):
            await aviso_no_ticket(canal,
                "⚠️ Histórico de encerramento ainda não persistido. O canal permanecerá aberto.")
            return False

        # DM para quem abriu: UMA mensagem (resumo + logs + avaliação)
        dm_ok = False
        if dono:
            try:
                staff_membro = guild.get_member(staff_id) if staff_id else None
                atendente = (
                    f" com **{staff_membro.display_name}**"
                    if staff_membro
                    else " com a nossa equipe"
                )
                embed_av = discord.Embed(
                    title="⭐ Avalie o seu atendimento",
                    description=(
                        f"Olá, **{dono.display_name}**!\n\n"
                        f"Seu ticket **{proto}** "
                        f"({cat.get('nome', 'Ticket')}) foi finalizado.\n"
                        f"Como foi o seu atendimento{atendente}?\n\n"
                        "Clique em uma das notas abaixo. ⚜️"
                    ),
                    color=COR_AZUL_CLARO,
                )
                embed_av.set_footer(text=f"{NOME_SERVIDOR} • Sua opinião importa!")
                view = discord.ui.View(timeout=None)
                for n in range(1, 6):
                    view.add_item(
                        BotaoNota(n, guild.id, numero, staff_id, cat_key or "x")
                    )
                await dono.send(
                    content=f"📑 Aqui estão os logs do seu ticket em "
                    f"**{NOME_SERVIDOR}**:",
                    embeds=[base_embed(), embed_av],
                    file=discord.File(io.BytesIO(dados), filename=nome_arquivo),
                    view=view,
                )
                dm_ok = True
            except (discord.Forbidden, discord.HTTPException):
                pass


        await asyncio.sleep(TEMPO_PARA_APAGAR)
        try:
            await canal.delete(reason=f"Ticket fechado por {quem_fechou}")
            apagado = True
        except discord.HTTPException:
            pass
    finally:
        CANAIS_FECHANDO.discard(canal.id)
        if apagado:
            remover_estado(canal.id)
            await confirmar_gravacao(F_ESTADOS)
    return apagado


class ComentarioModal(discord.ui.Modal):
    comentario = discord.ui.TextInput(
        label="Quer deixar um comentário? (opcional)",
        placeholder="Conte como foi sua experiência...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, nota, guild_id, numero, staff_id, cat_key):
        super().__init__(title=f"Sua nota: {nota} de 5", timeout=300)
        self.nota = nota
        self.guild_id = guild_id
        self.numero = numero
        self.staff_id = staff_id
        self.cat_key = cat_key

    async def on_submit(self, interaction: discord.Interaction):
        comentario = str(self.comentario).strip()
        cat = CATEGORIAS.get(self.cat_key, {})

        historico = _ler_json(F_HISTORICO, [])
        ticket = next((h for h in reversed(historico)
                       if int(h.get("num", 0)) == self.numero
                       and h.get("guild_id", self.guild_id) == self.guild_id), None)
        if ticket is None or ticket.get("owner") != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Somente quem abriu este ticket pode avaliá-lo após o encerramento.", ephemeral=True
            )
        if any(a.get("ticket") == self.numero and a.get("guild_id", self.guild_id) == self.guild_id
               for a in _ler_json(F_AVALIACOES, [])):
            return await interaction.response.send_message(
                "ℹ️ Este atendimento já recebeu uma avaliação.", ephemeral=True
            )
        if _POOL is None:
            return await interaction.response.send_message(
                "⚠️ As avaliações estão indisponíveis no momento.", ephemeral=True
            )
        try:
            linha = await _POOL.fetchrow("""
                INSERT INTO royal_tickets_reviews
                (guild_id, ticket_no, owner_id, staff_id, categoria, nota, comentario)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (guild_id, ticket_no) DO NOTHING
                RETURNING ticket_no
            """, self.guild_id, self.numero, interaction.user.id,
                 self.staff_id or None, self.cat_key, self.nota, comentario)
        except Exception:
            LOG.exception("Falha no registro da avaliação")
            return await interaction.response.send_message(
                "❌ Falha ao registrar avaliação. Tente novamente.", ephemeral=True
            )
        if linha is None:
            return await interaction.response.send_message(
                "ℹ️ Este atendimento já foi avaliado.", ephemeral=True
            )
        salvar_avaliacao({
            "nota": self.nota, "staff": self.staff_id,
            "categoria": self.cat_key, "ticket": self.numero,
            "guild_id": self.guild_id, "usuario": interaction.user.id,
            "comentario": comentario, "data": agora(), "ts": int(time.time()),
        })
        await confirmar_gravacao(F_AVALIACOES)

        guild = interaction.client.get_guild(self.guild_id)
        canal = (
            guild.get_channel(CANAL_AVALIACOES_ID or CANAL_LOGS_ID) if guild else None
        )
        if canal and not canal.permissions_for(guild.default_role).view_channel:
            embed = discord.Embed(
                title="<a:coroa:1564000189167960177> Nova Avaliação de Atendimento",
                description=(
                    "Registro automático de avaliação do atendimento realizado pela "
                    f"**{NOME_SERVIDOR}**."
                ),
                color=COR_AZUL_CLARO,
                timestamp=datetime.now(FUSO),
            )
            embed.add_field(name="Nota", value=estrelas(self.nota), inline=True)
            embed.add_field(
                name="Ticket",
                value=f"#{self.numero:04d} • {cat.get('nome', '—')}",
                inline=True,
            )
            embed.add_field(
                name="Atendente",
                value=f"<@{self.staff_id}>" if self.staff_id else "Ninguém assumiu",
                inline=True,
            )
            embed.add_field(
                name="Avaliado por", value=interaction.user.mention, inline=True
            )
            embed.add_field(
                name="Comentário", value=comentario or "*Sem comentário*", inline=False
            )
            if banner_valido(BANNER_AVALIACAO):
                embed.set_image(url=BANNER_AVALIACAO)
            embed.set_footer(text=f"{NOME_SERVIDOR} • Central de Atendimento")
            try:
                await canal.send(embed=embed)
            except discord.HTTPException:
                pass


        agradecimento = discord.Embed(
            title="⚜️ Obrigado pela sua avaliação!",
            description=f"Sua nota: {estrelas(self.nota)}\n\n"
            f"Ela nos ajuda a melhorar o atendimento da **{NOME_SERVIDOR}**.",
            color=COR_AZUL,
        )
        await interaction.response.edit_message(embed=agradecimento, view=None)


class BotaoNota(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"sants_nota:(?P<nota>[1-5]):(?P<guild>\d+):(?P<num>\d+):(?P<staff>\d+):(?P<cat>\w+)",
):
    """Botão de nota 1-5. Os dados ficam no custom_id, então continua
    funcionando mesmo depois de o bot reiniciar."""

    def __init__(self, nota, guild_id, numero, staff_id, cat_key):
        estilo = (
            discord.ButtonStyle.danger
            if nota <= 2
            else discord.ButtonStyle.secondary
            if nota == 3
            else discord.ButtonStyle.success
        )
        super().__init__(
            discord.ui.Button(
                label=str(nota),
                emoji="⭐",
                style=estilo,
                custom_id=f"sants_nota:{nota}:{guild_id}:{numero}:{staff_id}:{cat_key}",
            )
        )
        self.nota = nota
        self.guild_id = guild_id
        self.numero = numero
        self.staff_id = staff_id
        self.cat_key = cat_key

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(
            int(match["nota"]),
            int(match["guild"]),
            int(match["num"]),
            int(match["staff"]),
            match["cat"],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ComentarioModal(
                self.nota, self.guild_id, self.numero, self.staff_id, self.cat_key
            )
        )


# ════════════════════════════════════════════════════════════════
#                         CRIAÇÃO DO TICKET
# ════════════════════════════════════════════════════════════════


async def criar_ticket(
    interaction: discord.Interaction, chave: str, respostas: list[list[str]]
):
    """Evita dois tickets do mesmo usuário ao mesmo tempo (clique duplo)."""
    if interaction.user.id in CRIANDO:
        return await interaction.followup.send(
            "⏳ O seu ticket já está sendo criado, aguarde um instante.", ephemeral=True
        )
    CRIANDO.add(interaction.user.id)
    try:
        await _criar_ticket(interaction, chave, respostas)
    finally:
        CRIANDO.discard(interaction.user.id)


async def _criar_ticket(
    interaction: discord.Interaction, chave: str, respostas: list[list[str]]
):
    """Chamar DEPOIS de interaction.response.defer(ephemeral=True)."""
    guild = interaction.guild
    user = interaction.user
    cat = CATEGORIAS[chave]

    erro = checar_pode_abrir(guild, user)
    if erro:
        return await interaction.followup.send(erro, ephemeral=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_permissions=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
        ),
    }
    dados_contexto = {"cat": chave, "respostas": respostas}
    confidencial = ticket_confidencial(dados_contexto)
    cargos_visiveis = CARGOS_CORREGEDORIA if confidencial else CARGOS_STAFF
    for cargo_id in dict.fromkeys(cargos_visiveis):
        cargo = guild.get_role(cargo_id)
        if cargo:
            overwrites[cargo] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
                manage_messages=True,
            )

    categoria_discord = resolver_categoria(guild, cat, interaction.channel.category)
    try:
        numero = await proximo_numero()
    except Exception:
        LOG.exception("PostgreSQL indisponível na abertura do ticket")
        return await interaction.followup.send(
            "❌ A central está temporariamente indisponível. A equipe já pode verificar o Railway.",
            ephemeral=True,
        )
    try:
        canal = await guild.create_text_channel(
            name=nome_canal(chave, respostas, numero),
            category=categoria_discord,
            overwrites=overwrites,
            topic=f"owner={user.id};cat={chave};num={numero}",
            reason=f"Ticket de {user} ({cat['nome']})",
        )
    except discord.HTTPException as e:
        return await interaction.followup.send(
            f"❌ Não consegui criar o ticket ({e.text}). "
            "Avise a staff — a categoria pode estar cheia (limite de 50 canais).",
            ephemeral=True,
        )

    salvar_estado(
        canal.id,
        owner=user.id,
        cat=chave,
        num=numero,
        prio="normal",
        claim=None,
        claim_ts=None,
        locked=False,
        status="aguardando",
        confidencial=confidencial,
        decisao=None,
        respostas=respostas,
        notas=[],
        card_id=None,
    )

    if not await confirmar_gravacao(F_ESTADOS):
        LOG.error("Ticket %s criado, mas persistência inicial falhou", canal.id)
        await canal.send("⚠️ Registro inicial pendente de confirmação. Acione a administração.")

    # Confirmação com protocolo, posição na fila e espera média
    proto = protocolo_de(canal.created_at, numero)
    espera = media_espera()
    confirmacao = discord.Embed(
        title="✅ Ticket criado",
        description=f"Seu atendimento já está aberto em {canal.mention}.",
        color=COR_AZUL,
    )
    confirmacao.add_field(name="🔖 Protocolo", value=f"`{proto}`", inline=True)
    confirmacao.add_field(
        name="📍 Fila", value=f"Nº **{posicao_na_fila(guild, canal)}**", inline=True
    )
    confirmacao.add_field(
        name="⏱️ Espera média",
        value=formatar_duracao(espera) if espera is not None else "—",
        inline=True,
    )
    confirmacao.set_footer(text=NOME_SERVIDOR)
    await interaction.followup.send(embed=confirmacao, ephemeral=True)

    if confidencial:
        pings = (" ".join(f"<@&{r}>" for r in CARGOS_CORREGEDORIA)
                 or f"<@{guild.owner_id}>")
        allowed = discord.AllowedMentions(users=True, roles=bool(CARGOS_CORREGEDORIA))
    else:
        pings = " ".join(f"<@&{r}>" for r in cargos_para_notificar(chave))
        allowed = discord.AllowedMentions(users=True, roles=True)
    await canal.send(content=f"{user.mention} {pings}".strip(), allowed_mentions=allowed)
    if not await atualizar_card(canal):
        LOG.error("Ticket criado mas cartão V2 não publicado: canal %s", canal.id)
    # (Sem log de abertura no canal de logs: só uma mensagem, ao fechar.)


class PerguntasModal(discord.ui.Modal):
    def __init__(self, chave: str, escolha: tuple[str, str] | None = None,
                 anteriores: dict[str, str] | None = None):
        cat = CATEGORIAS[chave]
        super().__init__(title=f"{cat['emoji']} {cat['nome']}"[:45], timeout=600)
        self.chave = chave
        self.escolha = escolha
        self.campos: list[tuple[dict, discord.ui.TextInput]] = []
        for p in cat["perguntas"][:5]:
            longo = p.get("longo", False)
            campo = discord.ui.TextInput(
                label=p["label"][:45],
                placeholder=p.get("placeholder", "")[:100] or None,
                style=discord.TextStyle.paragraph if longo else discord.TextStyle.short,
                required=p.get("obrigatorio", True),
                max_length=800 if longo else 200,
                default=(anteriores or {}).get(p["label"], "") or None,
            )
            self.add_item(campo)
            self.campos.append((p, campo))

    async def on_submit(self, interaction: discord.Interaction):
        respostas: list[list[str]] = []
        for pergunta, campo in self.campos:
            valor = str(campo).strip()
            if not valor:
                continue
            if pergunta.get("validar"):
                erro = validar_resposta(pergunta["validar"], valor)
                if erro:
                    return await interaction.response.send_message(
                        f"⚠️ **{pergunta['label']}:** {erro}.\n"
                        "Use o botão abaixo para corrigir, sem perder as outras respostas.",
                        view=CorrigirFormularioView(
                            self.chave, self.escolha,
                            {p["label"]: str(c) for p, c in self.campos}
                        ),
                        ephemeral=True,
                    )
            respostas.append([pergunta["label"], valor])
        if self.escolha:
            respostas.insert(0, [self.escolha[0], self.escolha[1]])

        await interaction.response.defer(ephemeral=True)
        await criar_ticket(interaction, self.chave, respostas)


class CorrigirFormularioView(discord.ui.View):
    def __init__(self, chave, escolha, anteriores):
        super().__init__(timeout=600)
        self.chave = chave
        self.escolha = escolha
        self.anteriores = anteriores

    @discord.ui.button(label="Corrigir formulário", emoji="✏️",
                       style=discord.ButtonStyle.primary)
    async def corrigir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            PerguntasModal(self.chave, self.escolha, self.anteriores)
        )


class EscolhaSelect(discord.ui.Select):
    """Pergunta rápida (menu) antes do formulário."""

    def __init__(self, chave: str):
        esc = CATEGORIAS[chave]["escolha"]
        super().__init__(
            placeholder=esc.get("placeholder", "Escolha uma opção...")[:150],
            options=[
                discord.SelectOption(
                    label=nome[:100], value=str(i), description=(desc or "")[:100] or None, emoji=emoji
                )
                for i, (nome, desc, emoji) in enumerate(esc["opcoes"])
            ],
        )
        self.chave = chave

    async def callback(self, interaction: discord.Interaction):
        esc = CATEGORIAS[self.chave]["escolha"]
        nome = esc["opcoes"][int(self.values[0])][0]
        await interaction.response.send_modal(
            PerguntasModal(self.chave, escolha=(esc["label"], nome))
        )


class EscolhaView(discord.ui.View):
    def __init__(self, chave: str):
        super().__init__(timeout=180)
        self.add_item(EscolhaSelect(chave))


def embed_meus_tickets(guild: discord.Guild, user: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title="📂 Meus Tickets",
        description=f"Histórico de atendimentos de {user.mention}.",
        color=COR_AZUL,
    )
    abertos = [(c, t) for c, t in listar_tickets(guild) if t.get("owner") == user.id]
    if abertos:
        linhas = []
        for canal, t in abertos:
            cat = CATEGORIAS.get(t.get("cat", ""), {})
            atendente = f"<@{t['claim']}>" if t.get("claim") else "aguardando atendente"
            linhas.append(
                f"{cat.get('emoji', '🎫')} {canal.mention} • "
                f"`{protocolo_de(canal.created_at, t['num'])}` • {atendente}"
            )
        embed.add_field(name="🟢 Em andamento", value="\n".join(linhas), inline=False)

    historico = [h for h in _ler_json(F_HISTORICO, []) if h.get("owner") == user.id]
    if historico:
        linhas = []
        for h in reversed(historico[-5:]):
            cat = CATEGORIAS.get(h.get("cat", ""), {})
            dec = {"aprovado": " • ✅ aprovado", "recusado": " • ❌ recusado"}.get(
                h.get("decisao"), ""
            )
            proto = h.get("protocolo") or f"#{h.get('num', 0):04d}"
            linhas.append(
                f"{cat.get('emoji', '🎫')} `{proto}` • {cat.get('nome', '—')} • "
                f"<t:{h.get('fechado_ts', 0)}:d>{dec}"
            )
        embed.add_field(name="📁 Encerrados (últimos 5)", value="\n".join(linhas), inline=False)

    if not abertos and not historico:
        embed.description = "Você ainda não abriu nenhum ticket."
    embed.set_footer(text=NOME_SERVIDOR)
    return embed


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=c["nome"],
                value=chave,
                description=c["descricao"],
                emoji=c["emoji"],
            )
            for chave, c in CATEGORIAS.items()
        ]
        super().__init__(
            placeholder="Selecione o assunto do atendimento...",
            options=options,
            custom_id="sants_ticket_select",
        )

    async def _resetar(self, interaction: discord.Interaction):
        # Selects voltam ao placeholder automaticamente após a interação.
        # Editar a mensagem pública aqui quebrava painéis Componentes V2.
        return

    async def callback(self, interaction: discord.Interaction):
        chave = self.values[0]
        cat = CATEGORIAS[chave]

        erro = checar_pode_abrir(interaction.guild, interaction.user)
        if erro:
            await interaction.response.send_message(erro, ephemeral=True)
            return await self._resetar(interaction)

        permitidos = cat.get("cargos_permitidos") or []
        if permitidos and not (
            eh_staff(interaction.user)
            or any(r.id in permitidos for r in getattr(interaction.user, "roles", []))
        ):
            await interaction.response.send_message(
                "🔒 Esta categoria é restrita a membros com cargo autorizado.",
                ephemeral=True,
            )
            return await self._resetar(interaction)

        # Etapa 1 (opcional): pergunta rápida em menu
        if cat.get("escolha"):
            embed = discord.Embed(
                description=(
                    f"**{cat['emoji']} {cat['nome']}**\n"
                    f"> `📌` {cat['escolha']['label']}: escolha abaixo para continuar."
                ),
                color=COR_AZUL,
            )
            await interaction.response.send_message(
                embed=embed, view=EscolhaView(chave), ephemeral=True
            )
            return await self._resetar(interaction)

        # Etapa 2: formulário
        if cat.get("perguntas"):
            await interaction.response.send_modal(PerguntasModal(chave))
            return await self._resetar(interaction)

        await interaction.response.defer(ephemeral=True)
        await self._resetar(interaction)
        await criar_ticket(interaction, chave, [])


class BotaoMeusTickets(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Meus Tickets",
            emoji="📂",
            style=discord.ButtonStyle.secondary,
            custom_id="sants_meus_tickets",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=embed_meus_tickets(interaction.guild, interaction.user),
            ephemeral=True,
        )


class TicketView(discord.ui.LayoutView):
    """Painel público persistente em Componentes V2 nativos."""

    def __init__(self):
        super().__init__(timeout=None)
        elementos = [discord.ui.TextDisplay(descricao_tema())]
        banner = banner_tema()
        if banner_valido(banner):
            elementos.insert(0, discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner)))
        elementos.append(discord.ui.Separator())
        elementos.append(discord.ui.ActionRow(TicketSelect()))
        elementos.append(discord.ui.TextDisplay(
            '-# <a:animated_Settings:1556187476177981440> Família Royal • '
            + ('🎄 Edição de Natal' if tema_atual() == 'natal' else 'Central oficial')
        ))
        self.add_item(discord.ui.Container(*elementos, accent_colour=discord.Colour(cor_tema())))


# ════════════════════════════════════════════════════════════════
#                  CONTROLES DENTRO DO TICKET (público)
# ════════════════════════════════════════════════════════════════


class MotivoFechamentoModal(discord.ui.Modal, title="Fechar Ticket"):
    motivo = discord.ui.TextInput(
        label="Motivo do fechamento",
        placeholder="Ex: Problema resolvido",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok = await fechar_ticket(
            interaction.client, interaction.channel, interaction.user, str(self.motivo)
        )
        await interaction.followup.send(
            "✅ Ticket encerrado e arquivado." if ok else
            "⚠️ O canal foi preservado porque não foi possível confirmar o encerramento.",
            ephemeral=True,
        )


class DecisaoModal(discord.ui.Modal):
    """Aprovar/Recusar uma solicitação (cargos e parcerias)."""

    def __init__(self, aprovar: bool):
        super().__init__(
            title="Aprovar solicitação" if aprovar else "Recusar solicitação",
            timeout=300,
        )
        self.aprovar = aprovar
        self.motivo = discord.ui.TextInput(
            label="Observação (opcional)" if aprovar else "Motivo da recusa",
            placeholder="Será enviado ao solicitante.",
            style=discord.TextStyle.paragraph,
            required=not aprovar,
            max_length=400,
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        canal = interaction.channel
        guild = interaction.guild
        t = ler_ticket(canal)
        if not t:
            return await interaction.response.send_message(
                "❌ Ticket não encontrado.", ephemeral=True
            )
        if t.get("decisao"):
            return await interaction.response.send_message(
                f"⚠️ Já decidido por <@{t['decisao'].get('por')}>.", ephemeral=True
            )
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message("❌ Sem permissão neste caso.", ephemeral=True)

        cat = CATEGORIAS.get(t.get("cat", ""), {})
        motivo = str(self.motivo).strip()
        status = "aprovado" if self.aprovar else "recusado"
        salvar_estado(
            canal.id,
            decisao={
                "status": status,
                "por": interaction.user.id,
                "motivo": motivo,
                "ts": int(time.time()),
            },
        )
        await interaction.response.send_message("✅ Decisão registrada!", ephemeral=True)
        await atualizar_card(canal)

        # Cargo automático ao aprovar (se configurado)
        extra = ""
        cargo_id = cat.get("cargo_ao_aprovar")
        if self.aprovar and cargo_id:
            cargo = guild.get_role(cargo_id)
            dono_m = guild.get_member(t["owner"])
            if cargo and dono_m:
                try:
                    await dono_m.add_roles(cargo, reason="Solicitação aprovada no ticket")
                    extra = f"\n> `🎖️` Cargo {cargo.mention} entregue automaticamente."
                except discord.HTTPException:
                    extra = "\n> `⚠️` Não consegui entregar o cargo automaticamente."

        titulo = "✅ Solicitação aprovada" if self.aprovar else "❌ Solicitação recusada"
        corpo = (
            f"{interaction.user.mention} **{status}** a solicitação de <@{t['owner']}>."
            + (f"\n> `💬` {motivo}" if motivo else "")
            + extra
        )
        try:
            await canal.send(
                content=f"<@{t['owner']}>",
                embed=discord.Embed(title=titulo, description=corpo, color=COR_AZUL),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            pass

        # DM para o solicitante (melhor esforço)
        dono = await buscar_membro(interaction.client, guild, t["owner"])
        if dono:
            try:
                await dono.send(
                    embed=discord.Embed(
                        title=f"{titulo} — {NOME_SERVIDOR}",
                        description=(
                            f"Sua solicitação **{cat.get('nome', 'Ticket')}** foi "
                            f"**{status}**."
                            + (f"\n\n**Observação da equipe:** {motivo}" if motivo else "")
                            + f"\n\n➡️ Ticket: {canal.mention}"
                        ),
                        color=COR_AZUL,
                        timestamp=datetime.now(FUSO),
                    )
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        if FECHAR_APOS_DECISAO_MIN:
            fechar_em = int(time.time()) + FECHAR_APOS_DECISAO_MIN * 60
            salvar_estado(canal.id, fechar_em=fechar_em)
            await aviso_no_ticket(
                canal,
                f"⏳ Este ticket será fechado automaticamente <t:{fechar_em}:R>. "
                "Se precisar de algo, responda aqui antes disso.",
            )

        await registrar(
            guild,
            titulo,
            f"{interaction.user.mention} → <@{t['owner']}> em {canal.mention}"
            + (f"\n**Observação:** {motivo}" if motivo else ""),
        )


class RespostasSelect(discord.ui.Select):
    def __init__(self, canal: discord.TextChannel):
        super().__init__(
            placeholder="💬 Escolha a resposta pronta...",
            options=[
                discord.SelectOption(label=nome, value=chave, emoji=emoji)
                for chave, (nome, emoji, _) in RESPOSTAS_PRONTAS.items()
            ],
        )
        self.canal = canal

    async def callback(self, interaction: discord.Interaction):
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message(
                "❌ Apenas a equipe autorizada.", ephemeral=True
            )
        nome, emoji, texto = RESPOSTAS_PRONTAS[self.values[0]]
        texto = texto.replace("{usuario}", f"<@{t.get('owner')}>")
        await interaction.response.send_message(
            f"✅ Resposta **{nome}** enviada.", ephemeral=True
        )
        try:
            embed = discord.Embed(description=f"{emoji} {texto}", color=COR_AZUL)
            embed.set_footer(text=f"Atendimento • {interaction.user.display_name}")
            await self.canal.send(
                content=f"<@{t.get('owner')}>",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            pass


class RespostasView(discord.ui.View):
    def __init__(self, canal: discord.TextChannel):
        super().__init__(timeout=120)
        self.add_item(RespostasSelect(canal))


class EtapaSelect(discord.ui.Select):
    def __init__(self, canal: discord.TextChannel):
        super().__init__(
            placeholder="Atualizar etapa do atendimento",
            options=[discord.SelectOption(label=nome, value=chave, emoji=emoji)
                     for chave, (emoji, nome) in STATUS_TICKET.items()
                     if chave != "suspenso"],
        )
        self.canal = canal

    async def callback(self, interaction: discord.Interaction):
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message("❌ Sem autorização.", ephemeral=True)
        etapa = self.values[0]
        salvar_estado(self.canal.id, status=etapa)
        if not await confirmar_gravacao(F_ESTADOS):
            return await interaction.response.send_message("⚠️ Falha ao persistir a etapa.", ephemeral=True)
        await atualizar_card(self.canal)
        emoji, nome = STATUS_TICKET[etapa]
        await interaction.response.send_message(f"✅ Etapa alterada para {emoji} **{nome}**.", ephemeral=True)
        await registrar(interaction.guild, "📌 Etapa atualizada",
                        f"{interaction.user.mention} alterou a etapa para {nome} em {self.canal.mention}")


class EtapaView(discord.ui.View):
    def __init__(self, canal: discord.TextChannel):
        super().__init__(timeout=180)
        self.add_item(EtapaSelect(canal))


class TicketControls(discord.ui.View):
    def __init__(self, assumido: bool = False, decisao: bool = False, decidido: bool = False):
        super().__init__(timeout=None)
        self.assumir.disabled = assumido
        if assumido:
            self.assumir.label = "Assumido"
        if not decisao:
            self.remove_item(self.aprovar)
            self.remove_item(self.recusar)
        elif decidido:
            self.aprovar.disabled = True
            self.recusar.disabled = True

    @discord.ui.button(
        label="Assumir",
        style=discord.ButtonStyle.green,
        custom_id="sants_assumir_ticket",
        emoji="🙋",
        row=0,
    )
    async def assumir(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel)):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode assumir tickets.", ephemeral=True
            )
        t = ler_ticket(interaction.channel)
        if not t:
            return await interaction.response.send_message("Ticket não encontrado no registro.", ephemeral=True)
        if t.get("claim"):
            return await interaction.response.send_message(
                f"⚠️ Este ticket já foi assumido por <@{t['claim']}>.\n"
                "Use o **Painel Staff** para transferir.",
                ephemeral=True,
            )
        await interaction.response.defer()
        salvar_estado(
            interaction.channel.id,
            claim=interaction.user.id,
            claim_ts=t.get("claim_ts") or time.time(),
            status="em_analise",
            alerta_nivel=len(ALERTAS_ESCALONADOS_MINUTOS),
        )
        await confirmar_gravacao(F_ESTADOS)
        await atualizar_card(interaction.channel)
        await aviso_no_ticket(
            interaction.channel,
            f"🙋 {interaction.user.mention} assumiu este ticket e vai te atender!",
            COR_AZUL_CLARO,
        )
        await registrar(
            interaction.guild,
            "🙋 Ticket Assumido",
            f"{interaction.user.mention} assumiu {interaction.channel.mention}",
            confidencial=ticket_confidencial(t),
        )

    @discord.ui.button(
        label="Fechar",
        style=discord.ButtonStyle.red,
        custom_id="sants_fechar_ticket",
        emoji="🔒",
        row=0,
    )
    async def fechar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        t = ler_ticket(interaction.channel)
        if not t:
            return await interaction.response.send_message("Ticket não encontrado no registro.", ephemeral=True)
        eh_dono = t.get("owner") == interaction.user.id
        if not (eh_dono or autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel))):
            return await interaction.response.send_message(
                "❌ Você não pode fechar este ticket.", ephemeral=True
            )
        await interaction.response.send_modal(MotivoFechamentoModal())

    @discord.ui.button(
        label="Chamar Equipe",
        style=discord.ButtonStyle.secondary,
        custom_id="sants_chamar_equipe",
        emoji="🔔",
        row=0,
    )
    async def chamar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        t = ler_ticket(interaction.channel)
        if autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel)):
            return await interaction.response.send_message(
                "ℹ️ Você já faz parte da equipe.", ephemeral=True
            )
        if t.get("owner") != interaction.user.id:
            return await interaction.response.send_message(
                "❌ Apenas quem abriu o ticket pode chamar a equipe.", ephemeral=True
            )
        restante = COOLDOWN_CHAMAR_EQUIPE - (
            time.time() - COOLDOWN_CHAMAR.get(interaction.channel.id, 0)
        )
        if restante > 0:
            return await interaction.response.send_message(
                f"⏳ Aguarde **{formatar_duracao(restante)}** para chamar de novo.",
                ephemeral=True,
            )
        COOLDOWN_CHAMAR[interaction.channel.id] = time.time()

        if t.get("claim"):
            mencao = f"<@{t['claim']}>"
        elif ticket_confidencial(t):
            mencao = " ".join(f"<@&{r}>" for r in CARGOS_CORREGEDORIA) or f"<@{interaction.guild.owner_id}>"
        else:
            ids = cargos_para_notificar(t.get("cat", "")) or list(CARGOS_STAFF)
            mencao = " ".join(f"<@&{r}>" for r in ids)
        await interaction.channel.send(
            content=mencao or None,
            embed=discord.Embed(
                description=f"🔔 {interaction.user.mention} está chamando a equipe!",
                color=COR_AZUL_CLARO,
            ),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
        await interaction.response.send_message("✅ Equipe chamada!", ephemeral=True)

    @discord.ui.button(
        label="Painel Staff",
        style=discord.ButtonStyle.blurple,
        custom_id="sants_painel_staff_ticket",
        emoji="🛠️",
        row=0,
    )
    async def painel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel)):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode abrir o painel staff.", ephemeral=True
            )
        t = ler_ticket(interaction.channel)
        await interaction.response.send_message(
            embed=embed_info_painel(interaction.channel, t),
            view=PainelTicketView(interaction.channel),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Respostas",
        style=discord.ButtonStyle.secondary,
        custom_id="sants_respostas_prontas",
        emoji="💬",
        row=0,
    )
    async def respostas(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel)):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode usar as respostas prontas.", ephemeral=True
            )
        await interaction.response.send_message(
            "💬 Escolha uma resposta pronta para enviar neste ticket:",
            view=RespostasView(interaction.channel),
            ephemeral=True,
        )

    @discord.ui.button(label="Etapa", emoji="📌", style=discord.ButtonStyle.secondary,
                       custom_id="sants_ticket_etapa", row=1)
    async def etapa(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = ler_ticket(interaction.channel)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message("❌ Apenas responsáveis autorizados.", ephemeral=True)
        await interaction.response.send_message("📌 Selecione a etapa do atendimento:",
                                                view=EtapaView(interaction.channel), ephemeral=True)

    @discord.ui.button(
        label="Aprovar",
        style=discord.ButtonStyle.green,
        custom_id="sants_aprovar_ticket",
        emoji="✅",
        row=1,
    )
    async def aprovar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel)):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode decidir.", ephemeral=True
            )
        if ler_ticket(interaction.channel).get("decisao"):
            return await interaction.response.send_message(
                "⚠️ Esta solicitação já foi decidida.", ephemeral=True
            )
        await interaction.response.send_modal(DecisaoModal(aprovar=True))

    @discord.ui.button(
        label="Recusar",
        style=discord.ButtonStyle.red,
        custom_id="sants_recusar_ticket",
        emoji="❌",
        row=1,
    )
    async def recusar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not autorizado_no_ticket(interaction.user, ler_ticket(interaction.channel)):
            return await interaction.response.send_message(
                "❌ Apenas a equipe pode decidir.", ephemeral=True
            )
        if ler_ticket(interaction.channel).get("decisao"):
            return await interaction.response.send_message(
                "⚠️ Esta solicitação já foi decidida.", ephemeral=True
            )
        await interaction.response.send_modal(DecisaoModal(aprovar=False))


# ════════════════════════════════════════════════════════════════
#                  PAINEL STAFF DO TICKET (somente staff)
# ════════════════════════════════════════════════════════════════


def embed_info_painel(canal, t: dict) -> discord.Embed:
    cat = CATEGORIAS.get(t.get("cat", ""), {})
    p_emoji, p_nome = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])
    proto = protocolo_de(canal.created_at, int(t.get("num", 0) or 0))
    e = discord.Embed(
        title=f"🛠️ Painel Staff — {proto}",
        description=(
            f"**Categoria:** {cat.get('nome', '—')}\n"
            f"**Aberto por:** <@{t.get('owner')}>\n"
            f"**Atendente:** "
            f"{('<@' + str(t['claim']) + '>') if t.get('claim') else 'Ninguém'}\n"
            f"**Prioridade:** {p_emoji} {p_nome}\n"
            f"**Status:** {'🔒 Trancado' if t.get('locked') else '🟢 Aberto'}\n"
            f"**Notas internas:** {len(t.get('notas', []))}"
        ),
        color=COR_AZUL,
    )
    e.set_footer(text="Use as opções abaixo para gerenciar este ticket.")
    return e


class RenomearModal(discord.ui.Modal, title="Renomear Ticket"):
    nome = discord.ui.TextInput(label="Novo nome do canal", max_length=90)

    def __init__(self, canal):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        if not autorizado_no_ticket(interaction.user, ler_ticket(self.canal)):
            return await interaction.response.send_message("❌ Sem autorização.", ephemeral=True)
        antigo = self.canal.name
        try:
            await asyncio.wait_for(self.canal.edit(name=str(self.nome)), timeout=8)
        except asyncio.TimeoutError:
            return await interaction.response.send_message(
                "⏳ O Discord limita a 2 renomeações a cada 10 minutos. "
                "Tente novamente mais tarde.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "❌ Não consegui renomear.", ephemeral=True
            )
        await interaction.response.send_message("✅ Ticket renomeado.", ephemeral=True)
        await aviso_no_ticket(
            self.canal, f"✏️ {interaction.user.mention} renomeou o ticket."
        )
        await registrar(
            interaction.guild,
            "✏️ Ticket Renomeado",
            f"{interaction.user.mention}: `{antigo}` → {self.canal.mention}",
        )


class AvisoDMModal(discord.ui.Modal, title="Avisar usuário por DM"):
    mensagem = discord.ui.TextInput(
        label="Mensagem para o usuário",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Precisamos de mais informações no seu ticket.",
        max_length=800,
    )

    def __init__(self, canal):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message("❌ Sem autorização.", ephemeral=True)
        dono = await buscar_membro(interaction.client, interaction.guild, t["owner"])
        if not dono:
            return await interaction.response.send_message(
                "❌ Não encontrei o usuário.", ephemeral=True
            )
        embed = discord.Embed(
            title=f"📨 Aviso da equipe — {NOME_SERVIDOR}",
            description=f"{self.mensagem}\n\n➡️ Acesse seu ticket: {self.canal.mention}",
            color=COR_AZUL,
            timestamp=datetime.now(FUSO),
        )
        embed.set_footer(text=f"Enviado por {interaction.user.display_name}")
        try:
            await dono.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.response.send_message(
                "❌ O usuário está com a DM fechada.", ephemeral=True
            )
        await interaction.response.send_message("✅ DM enviada!", ephemeral=True)
        await aviso_no_ticket(
            self.canal, f"📨 {interaction.user.mention} avisou o usuário por DM."
        )


class NotaInternaModal(discord.ui.Modal, title="Nota interna (só staff)"):
    texto = discord.ui.TextInput(
        label="Anotação",
        style=discord.TextStyle.paragraph,
        placeholder="Visível apenas nos logs da staff.",
        max_length=400,
    )

    def __init__(self, canal):
        super().__init__()
        self.canal = canal

    async def on_submit(self, interaction: discord.Interaction):
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message("❌ Sem autorização.", ephemeral=True)
        notas = list(t.get("notas", []))
        notas.append(
            {
                "autor": interaction.user.display_name,
                "texto": str(self.texto),
                "data": agora(),
            }
        )
        salvar_estado(self.canal.id, notas=notas)
        await interaction.response.send_message(
            "📝 Nota salva! Ela aparece só no log da staff ao fechar o ticket.",
            ephemeral=True,
        )


class PainelTicketView(discord.ui.View):
    def __init__(self, canal: discord.TextChannel):
        super().__init__(timeout=600)
        self.canal = canal
        t = ler_ticket(canal)
        self.btn_trancar.label = "Destrancar" if t.get("locked") else "Trancar"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if autorizado_no_ticket(interaction.user, ler_ticket(self.canal)):
            return True
        await interaction.response.send_message("❌ Apenas a equipe autorizada.", ephemeral=True)
        return False

    # ── Linha 0: prioridade ──
    @discord.ui.select(
        placeholder="🚦 Definir prioridade",
        row=0,
        options=[
            discord.SelectOption(label=n, value=k, emoji=e)
            for k, (e, n) in PRIORIDADES.items()
        ],
    )
    async def sel_prioridade(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        valor = select.values[0]
        emoji, nome = PRIORIDADES[valor]
        salvar_estado(self.canal.id, prio=valor)
        await atualizar_card(self.canal)
        await interaction.response.send_message(
            f"✅ Prioridade: {emoji} **{nome}**", ephemeral=True
        )
        await aviso_no_ticket(
            self.canal,
            f"🚦 {interaction.user.mention} definiu a prioridade como "
            f"{emoji} **{nome}**.",
        )
        await registrar(
            interaction.guild,
            "🚦 Prioridade Alterada",
            f"{interaction.user.mention} → {emoji} {nome} em {self.canal.mention}",
        )

    # ── Linha 1: adicionar membro ──
    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="➕ Adicionar membro ao ticket",
        min_values=1,
        max_values=5,
        row=1,
    )
    async def sel_adicionar(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        if ticket_confidencial(ler_ticket(self.canal)):
            return await interaction.response.send_message(
                "🔒 Uma denúncia contra a equipe não permite inclusão manual de participantes.", ephemeral=True
            )
        adicionados = []
        for u in select.values:
            m = u if isinstance(u, discord.Member) else interaction.guild.get_member(u.id)
            if not m or m.bot:
                continue
            await self.canal.set_permissions(
                m,
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            )
            adicionados.append(m.mention)
        if not adicionados:
            return await interaction.response.send_message(
                "❌ Nenhum membro válido selecionado.", ephemeral=True
            )
        await interaction.response.send_message("✅ Adicionado(s)!", ephemeral=True)
        await aviso_no_ticket(
            self.canal,
            f"➕ {interaction.user.mention} adicionou {', '.join(adicionados)} "
            "ao ticket.",
            COR_AZUL_CLARO,
        )
        await registrar(
            interaction.guild,
            "➕ Membro Adicionado",
            f"{interaction.user.mention} adicionou {', '.join(adicionados)} "
            f"em {self.canal.mention}",
        )

    # ── Linha 2: remover membro ──
    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="➖ Remover membro do ticket",
        min_values=1,
        max_values=5,
        row=2,
    )
    async def sel_remover(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        t = ler_ticket(self.canal)
        removidos = []
        for u in select.values:
            if u.id == t.get("owner"):
                continue
            m = u if isinstance(u, discord.Member) else interaction.guild.get_member(u.id)
            if not m:
                continue
            await self.canal.set_permissions(m, overwrite=None)
            removidos.append(m.mention)
        if not removidos:
            return await interaction.response.send_message(
                "❌ Nenhum membro removível (quem abriu o ticket não pode ser "
                "removido).",
                ephemeral=True,
            )
        await interaction.response.send_message("✅ Removido(s)!", ephemeral=True)
        await aviso_no_ticket(
            self.canal,
            f"➖ {interaction.user.mention} removeu {', '.join(removidos)} do ticket.",
            COR_AZUL_CLARO,
        )
        await registrar(
            interaction.guild,
            "➖ Membro Removido",
            f"{interaction.user.mention} removeu {', '.join(removidos)} "
            f"de {self.canal.mention}",
        )

    # ── Linha 3: transferir atendimento ──
    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="🔁 Transferir atendimento para...",
        min_values=1,
        max_values=1,
        row=3,
    )
    async def sel_transferir(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ):
        alvo = select.values[0]
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(alvo, t):
            return await interaction.response.send_message(
                "❌ Só é possível transferir para um responsável autorizado neste ticket.", ephemeral=True
            )
        salvar_estado(
            self.canal.id, claim=alvo.id, claim_ts=t.get("claim_ts") or time.time()
        )
        await atualizar_card(self.canal)
        await interaction.response.send_message("✅ Transferido!", ephemeral=True)
        await aviso_no_ticket(
            self.canal,
            f"🔁 {interaction.user.mention} transferiu o atendimento para "
            f"{alvo.mention}.",
            COR_AZUL_CLARO,
        )
        await registrar(
            interaction.guild,
            "🔁 Atendimento Transferido",
            f"{interaction.user.mention} → {alvo.mention} em {self.canal.mention}",
        )

    # ── Linha 4: botões ──
    @discord.ui.button(label="Renomear", emoji="✏️", style=discord.ButtonStyle.secondary, row=4)
    async def btn_renomear(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(RenomearModal(self.canal))

    @discord.ui.button(label="Trancar", emoji="🔐", style=discord.ButtonStyle.secondary, row=4)
    async def btn_trancar(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.response.send_message("❌ Sem autorização.", ephemeral=True)
        dono = await buscar_membro(interaction.client, interaction.guild, t["owner"])
        if not isinstance(dono, discord.Member):
            return await interaction.response.send_message(
                "❌ O usuário não está mais no servidor.", ephemeral=True
            )
        trancar = not t.get("locked")
        ow = self.canal.overwrites_for(dono)
        ow.send_messages = not trancar
        await self.canal.set_permissions(dono, overwrite=ow)
        salvar_estado(self.canal.id, locked=trancar)
        await atualizar_card(self.canal)
        button.label = "Destrancar" if trancar else "Trancar"
        await interaction.response.edit_message(view=self)
        await aviso_no_ticket(
            self.canal,
            f"🔒 {interaction.user.mention} **trancou** o ticket. "
            "Você não pode enviar mensagens por enquanto."
            if trancar
            else f"🔓 {interaction.user.mention} **destrancou** o ticket.",
            COR_AZUL_CLARO,
        )
        await registrar(
            interaction.guild,
            "🔐 Ticket " + ("Trancado" if trancar else "Destrancado"),
            f"{interaction.user.mention} em {self.canal.mention}",
        )

    @discord.ui.button(label="Avisar DM", emoji="📨", style=discord.ButtonStyle.secondary, row=4)
    async def btn_dm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(AvisoDMModal(self.canal))

    @discord.ui.button(label="Nota", emoji="📝", style=discord.ButtonStyle.secondary, row=4)
    async def btn_nota(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(NotaInternaModal(self.canal))

    @discord.ui.button(label="Transcript", emoji="📄", style=discord.ButtonStyle.secondary, row=4)
    async def btn_transcript(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)
        t = ler_ticket(self.canal)
        if not autorizado_no_ticket(interaction.user, t):
            return await interaction.followup.send("❌ Sem autorização.", ephemeral=True)
        pagina, total = await gerar_transcript_html(self.canal, t)
        await interaction.followup.send(
            content=f"📄 Transcript parcial ({total} mensagens):",
            file=discord.File(
                io.BytesIO(pagina.encode("utf-8")),
                filename=f"parcial_{self.canal.name}.html",
            ),
            ephemeral=True,
        )


# ════════════════════════════════════════════════════════════════
#                 EMBEDS DE ESTATÍSTICA / CONFIG / RANKING
# ════════════════════════════════════════════════════════════════


def embed_avaliacoes() -> discord.Embed | None:
    dados = _ler_json(F_AVALIACOES, [])
    if not dados:
        return None
    media = sum(d["nota"] for d in dados) / len(dados)
    por_staff: dict[int, list[int]] = {}
    por_cat: dict[str, list[int]] = {}
    for d in dados:
        por_staff.setdefault(d["staff"], []).append(d["nota"])
        por_cat.setdefault(d["categoria"], []).append(d["nota"])

    ranking = sorted(
        por_staff.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True
    )[:10]
    txt_staff = "\n".join(
        f"**{i}.** "
        + (f"<@{sid}>" if sid else "Sem atendente")
        + f" — {sum(n) / len(n):.2f} ⭐ ({len(n)})"
        for i, (sid, n) in enumerate(ranking, 1)
    )
    txt_cat = "\n".join(
        f"{CATEGORIAS.get(k, {}).get('emoji', '📁')} "
        f"{CATEGORIAS.get(k, {}).get('nome', k)} — "
        f"{sum(n) / len(n):.2f} ⭐ ({len(n)})"
        for k, n in por_cat.items()
    )
    embed = discord.Embed(
        title=f"🏆 Avaliações — {NOME_SERVIDOR}",
        description=f"**Média geral:** {media:.2f} / 5 ⭐\n"
        f"**Total de avaliações:** {len(dados)}",
        color=COR_AZUL,
    )
    embed.add_field(name="Ranking de atendentes", value=txt_staff, inline=False)
    embed.add_field(name="Por categoria", value=txt_cat or "—", inline=False)
    return embed


def embed_estatisticas(guild: discord.Guild) -> discord.Embed:
    abertos = listar_tickets(guild)
    historico = _ler_json(F_HISTORICO, [])
    avaliacoes = _ler_json(F_AVALIACOES, [])
    contador = _ler_json(F_CONTADOR, {"contador": 0}).get("contador", 0)

    inicio_dia = datetime.now(FUSO).replace(hour=0, minute=0, second=0, microsecond=0)
    fechados_hoje = sum(1 for h in historico if h.get("fechado_ts", 0) >= inicio_dia.timestamp())
    sem_atendente = sum(1 for _, t in abertos if not t.get("claim"))
    urgentes = sum(1 for _, t in abertos if t.get("prio") == "urgente")
    tempo_medio = (
        sum(h.get("duracao_seg", 0) for h in historico) / len(historico)
        if historico
        else 0
    )
    media_av = (
        sum(a["nota"] for a in avaliacoes) / len(avaliacoes) if avaliacoes else 0
    )
    aprovados = sum(1 for h in historico if h.get("decisao") == "aprovado")
    recusados = sum(1 for h in historico if h.get("decisao") == "recusado")
    espera = media_espera()

    por_cat = {k: 0 for k in CATEGORIAS}
    for _, t in abertos:
        if t.get("cat") in por_cat:
            por_cat[t["cat"]] += 1
    txt_cat = "\n".join(
        f"{c['emoji']} {c['nome']}: **{por_cat[k]}** aberto(s)"
        for k, c in CATEGORIAS.items()
    )

    embed = discord.Embed(title=f"📊 Estatísticas — {NOME_SERVIDOR}", color=COR_AZUL)
    embed.add_field(name="🎫 Criados (total)", value=str(contador), inline=True)
    embed.add_field(name="🟢 Abertos agora", value=str(len(abertos)), inline=True)
    embed.add_field(name="✅ Fechados (total)", value=str(len(historico)), inline=True)
    embed.add_field(name="📅 Fechados hoje", value=str(fechados_hoje), inline=True)
    embed.add_field(name="⏳ Sem atendente", value=str(sem_atendente), inline=True)
    embed.add_field(name="🔴 Urgentes", value=str(urgentes), inline=True)
    embed.add_field(
        name="⏱️ Tempo médio de ticket",
        value=formatar_duracao(tempo_medio) if historico else "—",
        inline=True,
    )
    embed.add_field(
        name="⌛ Espera até atender",
        value=formatar_duracao(espera) if espera is not None else "—",
        inline=True,
    )
    embed.add_field(
        name="⭐ Nota média",
        value=f"{media_av:.2f} ({len(avaliacoes)})" if avaliacoes else "—",
        inline=True,
    )
    embed.add_field(
        name="⚖️ Decisões", value=f"✅ {aprovados} • ❌ {recusados}", inline=True
    )
    embed.add_field(name="📂 Por categoria", value=txt_cat, inline=False)
    return embed


def embed_lista_tickets(guild: discord.Guild, membro=None) -> discord.Embed:
    abertos = [(c, t) for c, t in fila_ordenada(guild)
               if not ticket_confidencial(t) or autorizado_no_ticket(membro, t)]
    embed = discord.Embed(title="📋 Tickets Abertos", color=COR_AZUL)
    if not abertos:
        embed.description = "✨ Nenhum ticket aberto no momento."
        return embed
    linhas = []
    for canal, t in abertos[:20]:
        cat = CATEGORIAS.get(t.get("cat", ""), {})
        p_emoji = PRIORIDADES.get(t.get("prio", "normal"), PRIORIDADES["normal"])[0]
        atendente = f"🙋 <@{t['claim']}>" if t.get("claim") else "⏳ sem atendente"
        etapa = STATUS_TICKET[ticket_status(t)][1]
        linhas.append(
            f"{p_emoji} {canal.mention} • {cat.get('emoji', '')} {cat.get('nome', '')} "
            f"• <@{t['owner']}> • {atendente} • {etapa} • <t:{int(canal.created_at.timestamp())}:R>"
        )
    embed.description = "\n".join(linhas)
    if len(abertos) > 20:
        embed.set_footer(text=f"+{len(abertos) - 20} ticket(s) não exibido(s)")
    return embed


def embed_config(guild: discord.Guild, bot: commands.Bot) -> discord.Embed:
    embed = discord.Embed(title="⚙️ Verificação da Configuração", color=COR_AZUL)

    # Armazenamento
    embed.add_field(
        name="🗄️ Armazenamento",
        value=(
            "✅ PostgreSQL (dados protegidos contra redeploy)"
            if _POOL is not None
            else "⚠️ Arquivos locais — podem ser perdidos em um novo deploy"
        ),
        inline=False,
    )

    # Categoria dos tickets
    if not CATEGORIA_TICKETS_ID:
        cat_txt = "⚠️ Não definida — usa a categoria do canal do painel"
    else:
        c = guild.get_channel(CATEGORIA_TICKETS_ID)
        cat_txt = (
            f"✅ **{c.name}**"
            if isinstance(c, discord.CategoryChannel)
            else f"❌ ID `{CATEGORIA_TICKETS_ID}` não é uma categoria deste servidor"
        )
    embed.add_field(name="📁 Categoria dos tickets", value=cat_txt, inline=False)

    # Canais
    def canal_txt(cid, opcional=False):
        if not cid:
            return "⚠️ Não definido" if opcional else "❌ Não definido"
        c = guild.get_channel(cid)
        return f"✅ {c.mention}" if c else f"❌ ID `{cid}` não encontrado"

    embed.add_field(name="📑 Canal de logs", value=canal_txt(CANAL_LOGS_ID), inline=True)
    embed.add_field(
        name="⭐ Canal de avaliações",
        value=canal_txt(CANAL_AVALIACOES_ID, True)
        if CANAL_AVALIACOES_ID
        else "ℹ️ Usa o canal de logs",
        inline=True,
    )

    # Cargos
    def cargos_txt(ids):
        if not ids:
            return "—"
        out = []
        for rid in ids:
            r = guild.get_role(rid)
            out.append(f"✅ {r.mention}" if r else f"❌ `{rid}` não encontrado")
        return "\n".join(out)

    embed.add_field(name="🛡️ Cargos staff", value=cargos_txt(CARGOS_STAFF), inline=False)
    embed.add_field(name="🔒 Cargos da Corregedoria",
                    value=cargos_txt(CARGOS_CORREGEDORIA) if CARGOS_CORREGEDORIA
                          else "⚠️ Não configurados; denúncias contra staff ficam restritas ao dono do servidor.",
                    inline=False)
    if CARGOS_NOTIFICAR:
        embed.add_field(
            name="🔔 Cargos notificados", value=cargos_txt(CARGOS_NOTIFICAR), inline=False
        )

    # Categorias
    linhas = []
    for k, c in CATEGORIAS.items():
        banner = "✅" if banner_valido(c.get("banner")) else "—"
        extra = ""
        if c.get("categoria_discord_id"):
            ok = isinstance(guild.get_channel(c["categoria_discord_id"]), discord.CategoryChannel)
            extra = " • categoria própria " + ("✅" if ok else "❌")
        if c.get("decisao"):
            extra += " • decisão ⚖️"
        linhas.append(
            f"{c['emoji']} **{c['nome']}** — banner {banner} • "
            f"{len(c.get('perguntas', []))} pergunta(s){extra}"
        )
    embed.add_field(name="📂 Categorias", value="\n".join(linhas), inline=False)
    embed.add_field(
        name="🖼️ Banner principal",
        value="✅" if banner_valido(BANNER_PRINCIPAL) else "⚠️ link de exemplo",
        inline=True,
    )

    # Permissões do bot
    exigidas = {
        "manage_channels": "Gerenciar Canais",
        "manage_roles": "Gerenciar Permissões/Cargos",
        "manage_messages": "Gerenciar Mensagens",
        "view_channel": "Ver Canais",
        "send_messages": "Enviar Mensagens",
        "embed_links": "Inserir Links",
        "attach_files": "Anexar Arquivos",
        "read_message_history": "Ler Histórico",
    }
    perms = guild.me.guild_permissions
    faltando = [nome for attr, nome in exigidas.items() if not getattr(perms, attr)]
    embed.add_field(
        name="🤖 Permissões do bot",
        value="✅ Tudo certo" if not faltando else "❌ Faltando: " + ", ".join(faltando),
        inline=True,
    )
    embed.add_field(
        name="👥 Intent Members",
        value="✅ Ativada" if bot.intents.members else "⚠️ Desativada (recomendado ativar)",
        inline=True,
    )
    return embed


# ════════════════════════════════════════════════════════════════
#                     PAINEL DA EQUIPE (global, persistente)
# ════════════════════════════════════════════════════════════════


class PainelStaffView(discord.ui.LayoutView):
    """Central da equipe 100% Components V2 (sem embeds no mesmo envio)."""

    def __init__(self):
        super().__init__(timeout=None)
        itens = [
            discord.ui.TextDisplay(
                "## 🛡️ CENTRAL ADMINISTRATIVA ROYAL\n"
                "> `📋` Gestão de solicitações por prioridade.\n"
                "> `⏱️` Fila com tempo de espera e etapas.\n"
                "> `📊` Relatórios, satisfação e verificação da configuração."
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
        ]
        botoes = [
            ("Fila de tickets", "📋", "royal_staff_fila_v3", self.lista),
            ("Estatísticas", "📊", "royal_staff_stats_v3", self.stats),
            ("Relatório 7 dias", "📑", "royal_staff_relatorio_v3", self.relatorio),
            ("Avaliações", "⭐", "royal_staff_avaliacoes_v3", self.ranking),
            ("Configuração", "⚙️", "royal_staff_config_v3", self.config),
        ]
        row = discord.ui.ActionRow()
        for label, emoji, custom_id, acao in botoes:
            botao = discord.ui.Button(
                label=label, emoji=emoji, custom_id=custom_id,
                style=discord.ButtonStyle.secondary,
            )
            botao.callback = acao
            row.add_item(botao)
        itens.append(row)
        itens.append(discord.ui.TextDisplay(
            "-# <a:animated_Settings:1556187476177981440> Família Royal • "
            + ("🎄 Edição Natalina" if tema_atual() == "natal" else "Central oficial")
        ))
        self.add_item(discord.ui.Container(*itens, accent_colour=discord.Colour(cor_tema())))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if eh_staff(interaction.user):
            return True
        await interaction.response.send_message("❌ Apenas a equipe autorizada.", ephemeral=True)
        return False

    async def lista(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=embed_lista_tickets(interaction.guild, interaction.user), ephemeral=True)

    async def stats(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=embed_estatisticas(interaction.guild), ephemeral=True)

    async def relatorio(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=resumo_7_dias(interaction.guild), ephemeral=True)

    async def ranking(self, interaction: discord.Interaction):
        embed = embed_avaliacoes()
        await interaction.response.send_message(
            embed=embed, ephemeral=True) if embed else await interaction.response.send_message(
            "📭 Ainda não há avaliações.", ephemeral=True)

    async def config(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=embed_config(interaction.guild, interaction.client), ephemeral=True)


# ════════════════════════════════════════════════════════════════
#              CORREIO NATALINO — OPCIONAL / MODERADO
# ════════════════════════════════════════════════════════════════

TRAVAS_CARTAS: dict[tuple[int, int], asyncio.Lock] = {}


def entrega_natal() -> datetime:
    """Data de entrega local (BRT) configurável por variável de ambiente."""
    texto = os.getenv("ROYAL_NATAL_DATA_ENTREGA", "").strip()
    try:
        if texto:
            return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=FUSO)
    except ValueError:
        LOG.warning("ROYAL_NATAL_DATA_ENTREGA inválida; usando 24/12 18h")
    hoje = datetime.now(FUSO)
    ano = hoje.year if hoje.month < 12 or (hoje.month == 12 and hoje.day <= 24) else hoje.year + 1
    return datetime(ano, 12, 24, 18, 0, tzinfo=FUSO)


async def entregar_cartas_aprovadas(bot: commands.Bot):
    if _POOL is None:
        return
    try:
        await _POOL.execute("""
            UPDATE royal_tickets_cartas_natal SET status='aprovada'
            WHERE status='enviando' AND entrega_em < now() - interval '10 minutes'
        """)
        rows = await _POOL.fetch("""
            SELECT id, guild_id, remetente_id, destinatario_id, mensagem
            FROM royal_tickets_cartas_natal
            WHERE status='aprovada' AND entrega_em <= now()
            ORDER BY id LIMIT 15
        """)
        for r in rows:
            claimed = await _POOL.fetchrow("""
                UPDATE royal_tickets_cartas_natal SET status='enviando'
                WHERE id=$1 AND status='aprovada'
                RETURNING id
            """, r["id"])
            if not claimed:
                continue
            try:
                alvo = await bot.fetch_user(r["destinatario_id"])
                await alvo.send(
                    "🎄 **CORREIO NATALINO ROYAL** 🎁\n\n"
                    "Você recebeu uma mensagem especial de um integrante da Família Royal!\n\n"
                    f"> {str(r['mensagem']).replace(chr(10), chr(10) + '> ')}\n\n"
                    "-# <a:coroa:1564000189167960177> Família Royal • Boas festas!",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                await _POOL.execute("""
                    UPDATE royal_tickets_cartas_natal
                    SET status='entregue', entregue_em=now() WHERE id=$1
                """, r["id"])
            except discord.HTTPException:
                await _POOL.execute("""
                    UPDATE royal_tickets_cartas_natal SET status='falha' WHERE id=$1
                """, r["id"])
            except Exception:
                LOG.exception("Falha no envio da carta %s", r["id"])
                await _POOL.execute("""
                    UPDATE royal_tickets_cartas_natal SET status='falha' WHERE id=$1
                """, r["id"])
    except Exception:
        LOG.exception("Falha no processamento do Correio Natalino")


class CartaNatalModal(discord.ui.Modal):
    mensagem = discord.ui.TextInput(
        label="Sua mensagem de Natal", style=discord.TextStyle.paragraph,
        placeholder="Escreva um recado de carinho ou agradecimento...",
        min_length=10, max_length=500,
    )

    def __init__(self, destinatario: int, guild_id: int):
        super().__init__(title="🎄 Correio Natalino Royal", timeout=300)
        self.destinatario = destinatario
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            return await interaction.response.send_message("❌ Servidor inválido.", ephemeral=True)
        if interaction.user.id == self.destinatario:
            return await interaction.response.send_message("⚠️ Escolha outro membro para receber a carta.", ephemeral=True)
        if _POOL is None:
            return await interaction.response.send_message("⚠️ Correio indisponível no momento.", ephemeral=True)
        chave = (self.guild_id, interaction.user.id)
        trava = TRAVAS_CARTAS.setdefault(chave, asyncio.Lock())
        async with trava:
            try:
                count = await _POOL.fetchval("""
                    SELECT count(*) FROM royal_tickets_cartas_natal
                    WHERE guild_id=$1 AND remetente_id=$2
                      AND criado_em >= now() - interval '24 hours'
                """, self.guild_id, interaction.user.id)
                if count >= 3:
                    return await interaction.response.send_message(
                        "⏳ Você atingiu o limite de 3 cartas nas últimas 24 horas.", ephemeral=True
                    )
                await _POOL.execute("""
                    INSERT INTO royal_tickets_cartas_natal
                    (guild_id, remetente_id, destinatario_id, mensagem)
                    VALUES ($1,$2,$3,$4)
                """, self.guild_id, interaction.user.id, self.destinatario,
                     str(self.mensagem).strip())
            except Exception:
                LOG.exception("Falha ao registrar carta")
                return await interaction.response.send_message("❌ Não consegui registrar a carta.", ephemeral=True)
        await interaction.response.send_message(
            "✅ Mensagem recebida! Ela será revisada pela equipe antes da entrega de Natal.",
            ephemeral=True,
        )


class DestinatarioNatal(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="🎁 Escolha quem receberá a mensagem",
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        alvo = self.values[0]
        if alvo.bot:
            return await interaction.response.send_message("❌ Escolha um membro, não um bot.", ephemeral=True)
        await interaction.response.send_modal(CartaNatalModal(alvo.id, interaction.guild.id))


class EscolherDestinatarioNatal(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(DestinatarioNatal())


class CorreioNatalView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        botao = discord.ui.Button(
            label="Escrever uma carta", emoji="💌",
            custom_id="royal_correio_natal_enviar_v1",
            style=discord.ButtonStyle.success,
        )
        botao.callback = self.comecar
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 🎄 CORREIO NATALINO ROYAL\n"
                "Envie uma mensagem positiva a alguém da Família! 🎁\n"
                "> `💌` Escolha o destinatário e escreva seu recado.\n"
                "> `🛡️` As cartas passam pela aprovação da equipe.\n"
                "> `📅` Entrega programada para **24 de dezembro**, ou na data definida pela staff."
            ),
            discord.ui.Separator(),
            discord.ui.ActionRow(botao),
            discord.ui.TextDisplay("-# <a:coroa:1564000189167960177> Família Royal • União e respeito"),
            accent_colour=discord.Colour(COR_NATAL_VERDE),
        ))

    async def comecar(self, interaction: discord.Interaction):
        if _POOL is None:
            return await interaction.response.send_message(
                "⚠️ O Correio Natalino está indisponível no momento.", ephemeral=True)
        await interaction.response.send_message(
            "🎁 Quem deve receber sua carta?", view=EscolherDestinatarioNatal(), ephemeral=True)


class ModerarCartaView(discord.ui.LayoutView):
    def __init__(self, carta: dict):
        super().__init__(timeout=600)
        self.carta = carta
        botoes = []
        for texto, emoji, nome, estilo in (
            ("Aprovar", "✅", "aprovada", discord.ButtonStyle.success),
            ("Rejeitar", "❌", "rejeitada", discord.ButtonStyle.danger),
        ):
            b = discord.ui.Button(label=texto, emoji=emoji, style=estilo)
            b.callback = self.acao_aprovar if nome == "aprovada" else self.acao_rejeitar
            botoes.append(b)
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                f"## 💌 CARTA NATALINA #{carta['id']}\n"
                f"> `👤` Remetente: <@{carta['remetente_id']}>\n"
                f"> `🎯` Destinatário: <@{carta['destinatario_id']}>\n"
                f"> `📝` Mensagem:\n> {str(carta['mensagem']).replace(chr(10), chr(10) + '> ')}"
            ),
            discord.ui.Separator(),
            discord.ui.ActionRow(*botoes),
            accent_colour=discord.Colour(COR_NATAL_OURO),
        ))

    async def revisar(self, interaction: discord.Interaction, status: str):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message("❌ Apenas a equipe.", ephemeral=True)
        if _POOL is None:
            return await interaction.response.send_message("❌ PostgreSQL indisponível.", ephemeral=True)
        data = entrega_natal()
        try:
            salvo = await _POOL.fetchrow("""
                UPDATE royal_tickets_cartas_natal
                SET status=$2, aprovado_por=$3, entrega_em=$4
                WHERE id=$1 AND status='pendente' AND guild_id=$5
                RETURNING id
            """, self.carta["id"], status, interaction.user.id,
                 data if status == "aprovada" else None, interaction.guild.id)
        except Exception:
            LOG.exception("Erro ao moderar carta %s", self.carta["id"])
            return await interaction.response.send_message("❌ Erro na moderação.", ephemeral=True)
        if not salvo:
            return await interaction.response.send_message("ℹ️ Carta já analisada.", ephemeral=True)
        await interaction.response.edit_message(view=discord.ui.LayoutView().add_item(
            discord.ui.Container(discord.ui.TextDisplay(
                f"## 💌 CARTA #{self.carta['id']}\n**Decisão:** {status} "
                f"por {interaction.user.mention}."
            ), accent_colour=discord.Colour(COR_NATAL_VERDE))))
        if status == "aprovada" and data <= datetime.now(FUSO):
            await entregar_cartas_aprovadas(interaction.client)

    async def acao_aprovar(self, interaction: discord.Interaction):
        await self.revisar(interaction, "aprovada")

    async def acao_rejeitar(self, interaction: discord.Interaction):
        await self.revisar(interaction, "rejeitada")


# ════════════════════════════════════════════════════════════════
#                                  COG
# ════════════════════════════════════════════════════════════════


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await carregar_armazenamento(self.bot)
        self.bot.add_view(TicketView())
        self.bot.add_view(PainelStaffView())
        self.bot.add_view(CorreioNatalView())
        self.bot.add_dynamic_items(BotaoNota)
        self.monitorar.start()

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for canal, estado in listar_tickets(guild):
                if estado.get("card_id"):
                    try:
                        self.bot.add_view(criar_card_v2(canal, estado), message_id=int(estado["card_id"]))
                    except Exception:
                        LOG.exception("Falha ao restaurar botões do ticket %s", canal.id)

    async def cog_unload(self):
        self.monitorar.cancel()

    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "❌ Você não tem permissão para usar este comando.", delete_after=5
            )
        elif isinstance(
            error, (commands.MissingRequiredArgument, commands.BadArgument)
        ):
            await ctx.send(
                f"⚠️ Uso incorreto. Veja `{ctx.clean_prefix}ticketajuda`.",
                delete_after=7,
            )
        else:
            raise error

    # ── Monitoramento: alerta sem atendente + inatividade ───────
    @tasks.loop(minutes=1)
    async def monitorar(self):
        await entregar_cartas_aprovadas(self.bot)
        agora_utc = datetime.now(timezone.utc)
        for cid in list(estados().keys()):
            try:
                canal = self.bot.get_channel(int(cid))
                if canal is None:
                    try:
                        canal = await self.bot.fetch_channel(int(cid))
                    except discord.NotFound:
                        remover_estado(cid)
                        await confirmar_gravacao(F_ESTADOS)
                        continue
                    except discord.HTTPException:
                        LOG.warning("Não foi possível consultar o canal %s; mantendo estado", cid)
                        continue
                if not isinstance(canal, discord.TextChannel):
                    continue
                if canal.id in CANAIS_FECHANDO:
                    continue
                t = ler_ticket(canal)
                if not t:
                    continue
                guild = canal.guild

                # 0) Fechamento automático após a decisão
                if (t.get("fechar_em") and time.time() >= t["fechar_em"]
                        and not ticket_confidencial(t) and not t.get("solicitante_saiu_ts")):
                    salvar_estado(canal.id, fechar_em=None)
                    asyncio.create_task(
                        fechar_ticket(
                            self.bot, canal, guild.me, "Fechado automaticamente após a decisão."
                        )
                    )
                    continue

                # 1) Escalonamento respeitando o horário publicado no painel.
                if not t.get("claim") and ticket_status(t) not in ("concluido", "suspenso"):
                    uteis = minutos_uteis(canal.created_at, agora_utc)
                    nivel_antigo = int(t.get("alerta_nivel", 1 if t.get("alertado") else 0))
                    nivel = min(len(ALERTAS_ESCALONADOS_MINUTOS),
                                sum(uteis >= m for m in ALERTAS_ESCALONADOS_MINUTOS))
                    if nivel > nivel_antigo:
                        confidencial = ticket_confidencial(t)
                        if confidencial:
                            destinatarios = (" ".join(f"<@&{r}>" for r in CARGOS_CORREGEDORIA)
                                             or f"<@{guild.owner_id}>")
                        else:
                            destinatarios = " ".join(f"<@&{r}>" for r in cargos_para_notificar(t.get("cat", "")))
                        await canal.send(
                            content=destinatarios or None,
                            embed=discord.Embed(
                                description=(f"⏰ **Acompanhamento:** ticket sem responsável "
                                             f"há **{uteis} minutos úteis**. "
                                             "Solicitamos atenção da equipe responsável."),
                                color=COR_NATAL_OURO,
                            ),
                            allowed_mentions=discord.AllowedMentions(users=confidencial,
                                                                      roles=True),
                        )
                        salvar_estado(canal.id, alerta_nivel=nivel, alertado=True)
                # Tickets em análise/aguardando usuário não causam spam de alerta.

                # 2) Inatividade
                if INATIVIDADE_AVISO_HORAS:
                    ultima = (
                        discord.utils.snowflake_time(canal.last_message_id)
                        if canal.last_message_id
                        else canal.created_at
                    )
                    parado = (agora_utc - ultima).total_seconds()
                    aviso_id = t.get("aviso_msg_id")
                    if aviso_id:
                        if canal.last_message_id != aviso_id:
                            salvar_estado(canal.id, aviso_msg_id=None)
                        elif (
                            INATIVIDADE_FECHAR_APOS_AVISO_HORAS
                            and parado >= INATIVIDADE_FECHAR_APOS_AVISO_HORAS * 3600
                        ):
                            if not ticket_confidencial(t) and not t.get("solicitante_saiu_ts"):
                                asyncio.create_task(
                                    fechar_ticket(
                                        self.bot, canal, guild.me,
                                        "Fechado automaticamente por inatividade.",
                                    )
                                )
                    elif parado >= INATIVIDADE_AVISO_HORAS * 3600:
                        extra = (
                            f" Se ninguém responder em "
                            f"**{INATIVIDADE_FECHAR_APOS_AVISO_HORAS}h**, ele será "
                            "fechado automaticamente."
                            if INATIVIDADE_FECHAR_APOS_AVISO_HORAS
                            else ""
                        )
                        msg = await canal.send(
                            content=f"<@{t['owner']}>",
                            embed=discord.Embed(
                                description="💤 Este ticket está **parado** há "
                                f"{INATIVIDADE_AVISO_HORAS}h." + extra,
                                color=COR_AZUL,
                            ),
                        )
                        salvar_estado(canal.id, aviso_msg_id=msg.id)
            except Exception as e:  # noqa: BLE001 - o monitor nunca deve parar
                print(f"[tickets] erro no monitoramento: {e}")

    @monitorar.before_loop
    async def antes_monitorar(self):
        await self.bot.wait_until_ready()

    # ── Painéis ─────────────────────────────────────────────────
    @commands.command(name="painelticket")
    @apenas_staff()
    async def painelticket(self, ctx: commands.Context):
        """Cria o painel público de tickets no canal atual."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        msg = await ctx.send(view=TicketView(), allowed_mentions=discord.AllowedMentions.none())
        paineis = _ler_json(F_PAINEIS, {})
        paineis[str(ctx.guild.id)] = {"canal": ctx.channel.id, "mensagem": msg.id}
        _salvar_json(F_PAINEIS, paineis)
        await confirmar_gravacao(F_PAINEIS)

    @commands.command(name="painelstaff")
    @apenas_staff()
    async def painelstaff(self, ctx: commands.Context):
        """Cria a central administrativa V2 somente em canal privado."""
        if ctx.channel.permissions_for(ctx.guild.default_role).view_channel:
            return await ctx.send("🔒 Use o comando em um canal privado da administração.")
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(view=PainelStaffView(), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="tematicket")
    @apenas_staff()
    async def tematicket(self, ctx: commands.Context, tema: str = "natal"):
        """!tematicket natal|classico: troca visual e atualiza painéis conhecidos."""
        tema = tema.strip().lower()
        if tema not in ("natal", "classico"):
            return await ctx.send("⚠️ Use `!tematicket natal` ou `!tematicket classico`.")
        _salvar_json(F_TEMA, {"tema": tema})
        if not await confirmar_gravacao(F_TEMA):
            return await ctx.send("❌ Falha ao salvar o tema no PostgreSQL.")
        resultado = []
        painel = _ler_json(F_PAINEIS, {}).get(str(ctx.guild.id), {})
        if painel:
            try:
                canal = ctx.guild.get_channel(int(painel["canal"]))
                if canal:
                    mensagem = await canal.fetch_message(int(painel["mensagem"]))
                    await mensagem.edit(view=TicketView(),
                                        allowed_mentions=discord.AllowedMentions.none())
                    resultado.append("Painel principal atualizado")
            except (discord.HTTPException, KeyError, ValueError):
                LOG.warning("Painel principal antigo não encontrado para atualização")
        atualizados = 0
        for canal, _ in listar_tickets(ctx.guild):
            if await atualizar_card(canal):
                atualizados += 1
            await asyncio.sleep(0.15)
        await ctx.send(f"✅ Tema **{tema}** aplicado. "
                       f"{atualizados} ticket(s) atualizados. "
                       + ("• ".join(resultado) if resultado else
                          "Use `!painelticket` para publicar o novo painel natalino, caso o antigo não esteja registrado."))

    @commands.command(name="correionatal")
    @apenas_staff()
    async def correionatal(self, ctx: commands.Context):
        """Publica o painel opcional do Correio Natalino."""
        await ctx.send(view=CorreioNatalView(), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="cartasnatal")
    @apenas_staff()
    async def cartasnatal(self, ctx: commands.Context):
        """Modera cartas apenas em canal privado de staff."""
        if ctx.channel.permissions_for(ctx.guild.default_role).view_channel:
            return await ctx.send("🔒 Execute este comando em um canal privado.")
        if _POOL is None:
            return await ctx.send("❌ PostgreSQL indisponível.")
        r = await _POOL.fetchrow("""
            SELECT id, remetente_id, destinatario_id, mensagem
            FROM royal_tickets_cartas_natal
            WHERE guild_id=$1 AND status='pendente'
            ORDER BY criado_em ASC LIMIT 1
        """, ctx.guild.id)
        if not r:
            return await ctx.send("📭 Nenhuma carta aguardando revisão.")
        await ctx.send(view=ModerarCartaView(dict(r)),
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="reentregarcarta")
    @apenas_staff()
    async def reentregarcarta(self, ctx: commands.Context, carta_id: int):
        if ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.administrator:
            return await ctx.send("🔒 Somente administradores podem tentar reenviar cartas.")
        if _POOL is None:
            return await ctx.send("❌ PostgreSQL indisponível.")
        r = await _POOL.fetchrow("""
            UPDATE royal_tickets_cartas_natal
            SET status='aprovada', entrega_em=now()
            WHERE id=$1 AND guild_id=$2 AND status='falha'
            RETURNING id
        """, carta_id, ctx.guild.id)
        if not r:
            return await ctx.send("⚠️ Carta não encontrada ou não está em falha.")
        await entregar_cartas_aprovadas(self.bot)
        await ctx.send("✅ Reenvio solicitado; consulte o estado no banco.")

    @commands.command(name="filaticket")
    @apenas_staff()
    async def filaticket(self, ctx: commands.Context):
        if ctx.channel.permissions_for(ctx.guild.default_role).view_channel:
            return await ctx.send("🔒 Consulte a fila em um canal privado.")
        await ctx.send(embed=embed_lista_tickets(ctx.guild, ctx.author))

    @commands.command(name="relatorioticket")
    @apenas_staff()
    async def relatorioticket(self, ctx: commands.Context, dias: int = 7):
        if ctx.channel.permissions_for(ctx.guild.default_role).view_channel:
            return await ctx.send("🔒 Consulte relatórios em um canal privado.")
        dias = min(90, max(1, dias))
        await ctx.send(embed=resumo_7_dias(ctx.guild, dias))

    @commands.command(name="arquivoticket")
    @apenas_staff()
    async def arquivoticket(self, ctx: commands.Context, numero: int):
        """Recupera um transcript arquivado; entrega por DM para não vazar dados."""
        if _POOL is None:
            return await ctx.send("❌ PostgreSQL indisponível.")
        registro = await _POOL.fetchrow("""
            SELECT protocolo, arquivo_html, confidencial FROM royal_tickets_transcripts
            WHERE guild_id=$1 AND ticket_no=$2 ORDER BY criado_em DESC LIMIT 1
        """, ctx.guild.id, numero)
        if not registro:
            return await ctx.send("📭 Não há transcrição arquivada com esse número.")
        if registro["confidencial"] and not (
            ctx.author.id == ctx.guild.owner_id
            or any(r.id in CARGOS_CORREGEDORIA for r in ctx.author.roles)
        ):
            return await ctx.send("🔒 Este histórico é reservado à Corregedoria.")
        try:
            await ctx.author.send(
                content=f"📄 Histórico arquivado • `{registro['protocolo']}`",
                file=discord.File(io.BytesIO(bytes(registro["arquivo_html"])),
                                  filename=f"{registro['protocolo']}.html"),
            )
            await ctx.send("✅ Transcrição enviada por mensagem privada.", delete_after=10)
        except discord.HTTPException:
            await ctx.send("⚠️ Não consegui entregar o arquivo por DM.")

    @commands.command(name="configticket")
    @apenas_staff()
    async def configticket(self, ctx: commands.Context):
        """Verifica se IDs, cargos e permissões estão corretos."""
        await ctx.send(embed=embed_config(ctx.guild, self.bot))

    @commands.command(name="ticketajuda")
    @apenas_staff()
    async def ticketajuda(self, ctx: commands.Context):
        """Lista os comandos do sistema de tickets."""
        p = ctx.clean_prefix
        embed = discord.Embed(
            title="📖 Comandos de Tickets",
            description=(
                f"`{p}painelticket` — cria o painel público\n"
                f"`{p}painelstaff` — cria a central V2 da equipe\n"
                f"`{p}filaticket` — fila por prioridade\n"
                f"`{p}relatorioticket [dias]` — relatório de 7 a 90 dias\n"
                f"`{p}tematicket natal|classico` — muda o tema\n"
                f"`{p}arquivoticket número` — transcrição arquivada por DM\n"
                f"`{p}correionatal` — publica o Correio Natalino\n"
                f"`{p}cartasnatal` — revisar as cartas num canal privado\n"
                f"`{p}recuperarticket` — restaura os botões do ticket\n"
                f"`{p}configticket` — verifica a configuração\n"
                f"`{p}avaliacoes` — ranking de avaliações\n"
                f"`{p}bloquear @membro [motivo]` — impede de abrir tickets\n"
                f"`{p}desbloquear @membro` — libera de novo\n\n"
                "**Dentro de um ticket:**\n"
                f"`{p}fechar [motivo]` • `{p}adicionar @membro` • "
                f"`{p}remover @membro` • `{p}renomear nome`\n"
                "Botões: **Respostas** (mensagens prontas) e **Aprovar/Recusar** "
                "nas categorias com decisão."
            ),
            color=COR_AZUL,
        )
        await ctx.send(embed=embed)

    # ── Comandos dentro do ticket ───────────────────────────────
    def _eh_ticket(self, ctx: commands.Context) -> bool:
        t = ler_ticket(ctx.channel)
        return bool(t) and autorizado_no_ticket(ctx.author, t)

    @commands.command(name="recuperarticket")
    @apenas_staff()
    async def recuperarticket(self, ctx: commands.Context):
        """Restaura os botões do ticket quando o painel sumir."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=8)
        t = ler_ticket(ctx.channel)
        # Atualiza o painel existente, ou publica um novo se tiver sido apagado.
        if await atualizar_card(ctx.channel):
            await ctx.send("✅ Painel de gerenciamento restaurado. Os botões estão disponíveis novamente.")
        else:
            salvar_estado(ctx.channel.id, card_id=t.get("card_id"))
            await ctx.send("❌ Não foi possível restaurar. Consulte os logs do Railway.")

    @commands.command(name="fechar")
    @apenas_staff()
    async def fechar(self, ctx: commands.Context, *, motivo: str = "Não informado"):
        """Fecha o ticket atual por comando."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        await fechar_ticket(self.bot, ctx.channel, ctx.author, motivo)

    @commands.command(name="adicionar")
    @apenas_staff()
    async def adicionar(self, ctx: commands.Context, membro: discord.Member):
        """Adiciona um membro ao ticket atual."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Você não tem acesso a este ticket.", delete_after=5)
        if ticket_confidencial(ler_ticket(ctx.channel)):
            return await ctx.send("🔒 Não é permitido incluir participantes em denúncia interna.")
        await ctx.channel.set_permissions(
            membro,
            view_channel=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
        )
        await ctx.send(f"✅ {membro.mention} foi adicionado ao ticket.")

    @commands.command(name="remover")
    @apenas_staff()
    async def remover(self, ctx: commands.Context, membro: discord.Member):
        """Remove um membro do ticket atual."""
        t = ler_ticket(ctx.channel)
        if not t:
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        if not autorizado_no_ticket(ctx.author, t):
            return await ctx.send("❌ Sem autorização neste atendimento.", delete_after=5)
        if t.get("owner") == membro.id:
            return await ctx.send(
                "❌ Não dá para remover quem abriu o ticket.", delete_after=5
            )
        await ctx.channel.set_permissions(membro, overwrite=None)
        await ctx.send(f"✅ {membro.mention} foi removido do ticket.")

    @commands.command(name="renomear")
    @apenas_staff()
    async def renomear(self, ctx: commands.Context, *, nome: str):
        """Renomeia o ticket atual."""
        if not self._eh_ticket(ctx):
            return await ctx.send("❌ Use dentro de um ticket.", delete_after=5)
        try:
            await asyncio.wait_for(ctx.channel.edit(name=nome[:90]), timeout=8)
        except asyncio.TimeoutError:
            return await ctx.send(
                "⏳ Limite do Discord: 2 renomeações a cada 10 minutos.",
                delete_after=8,
            )
        await ctx.send(f"✅ Ticket renomeado para **{nome[:90]}**.")

    # ── Avaliações / bloqueios ──────────────────────────────────
    @commands.command(name="avaliacoes")
    @apenas_staff()
    async def avaliacoes(self, ctx: commands.Context):
        """Mostra a média geral e o ranking de atendentes."""
        embed = embed_avaliacoes()
        if not embed:
            return await ctx.send("📭 Ainda não há avaliações.", delete_after=10)
        await ctx.send(embed=embed)

    @commands.command(name="bloquear")
    @apenas_staff()
    async def bloquear(
        self, ctx: commands.Context, membro: discord.Member, *, motivo: str = "Não informado"
    ):
        """Impede um membro de abrir tickets."""
        dados = _ler_json(F_BLOQUEIOS, {})
        dados[str(membro.id)] = {"motivo": motivo, "por": ctx.author.id, "data": agora()}
        _salvar_json(F_BLOQUEIOS, dados)
        await ctx.send(f"🚫 {membro.mention} não pode mais abrir tickets.\n**Motivo:** {motivo}")
        await registrar(
            ctx.guild,
            "🚫 Usuário Bloqueado de Tickets",
            f"{ctx.author.mention} bloqueou {membro.mention}\n**Motivo:** {motivo}",
        )

    @commands.command(name="desbloquear")
    @apenas_staff()
    async def desbloquear(self, ctx: commands.Context, membro: discord.Member):
        """Libera um membro bloqueado."""
        dados = _ler_json(F_BLOQUEIOS, {})
        if str(membro.id) not in dados:
            return await ctx.send("ℹ️ Esse membro não está bloqueado.", delete_after=6)
        dados.pop(str(membro.id))
        _salvar_json(F_BLOQUEIOS, dados)
        await ctx.send(f"✅ {membro.mention} pode abrir tickets novamente.")
        await registrar(
            ctx.guild,
            "✅ Usuário Desbloqueado",
            f"{ctx.author.mention} desbloqueou {membro.mention}",
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Reabre o fluxo de quem saiu e retornou, sem apagar o histórico."""
        for canal, t in listar_tickets(member.guild):
            if t.get("owner") != member.id or not t.get("solicitante_saiu_ts"):
                continue
            try:
                ow = canal.overwrites_for(member)
                ow.view_channel = True
                ow.read_message_history = True
                ow.send_messages = not t.get("locked", False)
                await canal.set_permissions(member, overwrite=ow,
                                            reason="Solicitante voltou ao servidor")
            except discord.HTTPException:
                LOG.exception("Falha ao restaurar acesso ao ticket %s", canal.id)
                continue
            salvar_estado(canal.id, solicitante_saiu_ts=None,
                         status="em_analise" if t.get("claim") else "aguardando")
            await confirmar_gravacao(F_ESTADOS)
            await atualizar_card(canal)
            await aviso_no_ticket(canal,
                f"🎄 {member.mention} retornou ao servidor. Seu atendimento foi retomado.")

    # ── Saída de membro: nunca destrói prova ou atendimento pendente ──
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        for canal, t in listar_tickets(member.guild):
            if t.get("owner") != member.id:
                continue
            salvar_estado(canal.id, status="suspenso", solicitante_saiu_ts=int(time.time()))
            await confirmar_gravacao(F_ESTADOS)
            await aviso_no_ticket(
                canal,
                "🔒 O solicitante saiu do servidor. O histórico foi preservado "
                "para análise e encerramento manual pela equipe responsável.",
                COR_NATAL_OURO,
            )
            if not ticket_confidencial(t):
                await registrar(member.guild, "📂 Atendimento preservado",
                                f"Solicitante <@{member.id}> saiu; ticket {canal.id} permanece aberto.")



async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))