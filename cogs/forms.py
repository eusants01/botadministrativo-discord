from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
import asyncpg
import discord
from discord.ext import commands, tasks

log = logging.getLogger("formularios")

# ╔══════════════════════════════════════════════════════════════╗
# ║                        CONFIGURAÇÃO                          ║
# ╚══════════════════════════════════════════════════════════════╝
#
# Como funciona:
#   1. A staff envia o painel com  !painelformulario <chave>
#   2. A pessoa clica em "Iniciar Formulário" e ganha um canal privado.
#   3. O bot apresenta o formulário (regras, prazo...) e faz as perguntas UMA POR VEZ.
#   4. No fim, a pessoa revisa, envia, e a staff aprova ou recusa.
#
# Requer o PostgreSQL do projeto (bot.pool). Tudo fica salvo: se o bot reiniciar no
# meio de um formulário, a pessoa continua de onde parou.

NOME_SERVIDOR = "Família Sant's"
FUSO = ZoneInfo("America/Sao_Paulo")

COR_AZUL = 0x1A3C8C
COR_AZUL_CLARO = 0x4A90E2

# Quem gerencia os formulários (Administrador também pode)
CARGOS_STAFF = [
    1553832098404499516,
    1553832097905377422,
]

# Categoria onde os canais privados são criados. 0 = a categoria do canal do painel.
CATEGORIA_FORMS_ID = 0

# Canal da staff que recebe as respostas quando o formulário não define o próprio.
# 0 = nenhum (o formulário PRECISA ter "canal_respostas_id").
CANAL_RESPOSTAS_PADRAO_ID = 0

INATIVIDADE_MIN = 30        # minutos sem responder → o formulário é cancelado
APAGAR_CANAL_APOS_SEG = 20  # tempo até apagar o canal depois de enviar/cancelar
DIGITANDO_SEG = 0.8         # "digitando..." antes de cada pergunta (efeito de conversa)

# ── Formulários ──────────────────────────────────────────────────────────────
# A chave (ex.: "staff") só pode ter letras minúsculas, números e "_".
#
# Placeholders que podem ser usados nos textos "painel", "boas_vindas" e "conclusao":
#   {usuario} {encerra} {abre} {vagas} {status} {total_perguntas} {tempo_estimado}
#   {inatividade} {protocolo}
#
# Tipos de pergunta:
#   "texto"     resposta curta           ("min_chars", "max_chars", "validar": "url"|"convite")
#   "paragrafo" resposta longa           ("min_chars", "max_chars")
#   "numero"    só números               ("min", "max")
#   "escolha"   uma opção                ("opcoes": ["A", ("B", "🔥"), ...] até 25)
#   "multi"     várias opções           ("opcoes", "max": quantas no máximo)
#   "sim_nao"   Sim ou Não
#   "anexo"     prints/arquivos          ("max_arquivos", "aceita_link": True)
# Em qualquer pergunta:  "obrigatoria": False  (permite pular)
#                        "dica": "texto de ajuda"
#                        "se": ("id_de_outra_pergunta", "Sim")   (só pergunta se a resposta bater)
FORMULARIOS = {
    "staff": {
        "nome": "Recrutamento de Staff",
        "emoji": "🛡️",
        "cor": COR_AZUL,
        "banner": "",
        # Disponibilidade (horário de Brasília). None = sem data.
        "abre_em": None,                  # ex.: "2026-11-01 00:00"
        "encerra_em": "2026-12-31 23:59",
        "max_respostas": 50,              # 0 = ilimitado
        # Regras de quem pode responder
        "uma_por_usuario": True,
        "cooldown_recusa_dias": 7,        # depois de recusado, só pode tentar de novo após X dias
        "cargos_exigidos": [],            # só quem tem ALGUM destes cargos ([] = todos)
        "cargos_bloqueados": [],          # quem tem algum destes cargos não pode responder
        "dias_no_servidor_min": 0,
        # Para onde vão as respostas e quem avalia
        "canal_respostas_id": 1560397237534597332,          # <<< PREENCHA com o canal da staff
        "cargos_avaliadores": [],         # cargos que também podem aprovar/recusar e são marcados
        "cargo_ao_aprovar": None,         # cargo entregue automaticamente ao aprovar
        "painel": """\
# 🛡️ **Recrutamento de Staff**
Quer fazer parte da equipe da **Família Sant's**? Preencha o formulário e aguarde a análise.

**Informações**
> `📅` **Encerra:** {encerra}
> `🎟️` **Vagas:** {vagas}
> `❓` **Perguntas:** {total_perguntas} (cerca de {tempo_estimado})
> `🔔` **Status:** {status}

**Requisitos**
> `✅` Ser ativo e respeitar as regras do servidor.
> `✅` Ter disponibilidade para ajudar a equipe.

**Regras**
> `📌` Responda com sinceridade e capricho.
> `⚠️` Só é possível enviar o formulário **uma vez**.
""",
        "boas_vindas": """\
# 🛡️ **Formulário — Recrutamento de Staff**
Olá, {usuario}! Vou te fazer algumas perguntas, **uma de cada vez**.
Responda enviando uma mensagem aqui no canal.

**Antes de começar**
> `⏳` Sem responder por **{inatividade} min**, o formulário é cancelado.
> `↩️` Você pode **voltar**, **pular** (quando for opcional) e **revisar tudo** antes de enviar.
> `📅` O formulário encerra: {encerra}

**Regras**
> `📌` Responda com sinceridade. Respostas copiadas ou falsas eliminam o candidato.
> `⚠️` Só é possível enviar **uma vez**.

Clique em **Aceito e quero começar** quando estiver pronto.
""",
        "conclusao": """\
# ✅ **Formulário enviado!**
Obrigado, {usuario}! O seu protocolo é **{protocolo}**.

> `🔎` A equipe vai analisar as suas respostas.
> `📬` Você será avisado por **DM** quando houver uma decisão (mantenha as DMs abertas).
> `🗑️` Este canal será apagado em instantes.
""",
        "perguntas": [
            {
                "id": "Teste de honestidade?",
                "texto": "Voce acha que o Kael é gay?",
                "tipo": "texto",
                "max_chars": 60,
            },
            {
                "id": "idade",
                "texto": "Qual é a sua idade?",
                "tipo": "numero",
                "min": 13,
                "max": 99,
                "dica": "Apenas números.",
            },
            {
                "id": "tempo",
                "texto": "Há quanto tempo você está na Família?",
                "tipo": "escolha",
                "opcoes": ["Menos de 1 mês", "1 a 3 meses", "3 a 6 meses", "Mais de 6 meses"],
            },
            {
                "id": "ja_foi_staff",
                "texto": "Você já foi staff em outro servidor?",
                "tipo": "sim_nao",
            },
            {
                "id": "experiencia",
                "texto": "Conte sobre a sua experiência como staff.",
                "tipo": "paragrafo",
                "min_chars": 30,
                "se": ("ja_foi_staff", "Sim"),
            },
            {
                "id": "areas",
                "texto": "Em quais áreas você gostaria de ajudar?",
                "tipo": "multi",
                "max": 2,
                "opcoes": [("Moderação", "🛡️"), ("Eventos", "🎉"), ("Divulgação", "📣"), ("Suporte", "💬")],
                "dica": "Escolha até 2 opções.",
            },
            {
                "id": "motivo",
                "texto": "Por que você quer entrar para a staff?",
                "tipo": "paragrafo",
                "min_chars": 60,
                "dica": "Seja detalhado: o que você pode agregar à equipe?",
            },
            {
                "id": "disponibilidade",
                "texto": "Quais dias e horários você tem disponíveis?",
                "tipo": "texto",
                "max_chars": 200,
            },
            {
                "id": "prints",
                "texto": "Quer enviar prints que mostrem a sua atividade? (opcional)",
                "tipo": "anexo",
                "obrigatoria": False,
                "max_arquivos": 3,
                "dica": "Envie as imagens como anexo nesta conversa.",
            },
        ],
    },
}

# ════════════════════════════════════════════════════════════════
#                            BANCO DE DADOS
# ════════════════════════════════════════════════════════════════

SQL_TABELAS = """
CREATE TABLE IF NOT EXISTS form_estado (
    form_key TEXT PRIMARY KEY,
    aberto BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS form_sessoes (
    id BIGSERIAL PRIMARY KEY,
    form_key TEXT NOT NULL,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    channel_id BIGINT,
    etapa INTEGER NOT NULL DEFAULT -1,
    respostas JSONB NOT NULL DEFAULT '{}'::jsonb,
    corrigindo BOOLEAN NOT NULL DEFAULT FALSE,
    msg_id BIGINT,
    status TEXT NOT NULL DEFAULT 'andamento',
    iniciado_ts BIGINT NOT NULL,
    atividade_ts BIGINT NOT NULL,
    avisou BOOLEAN NOT NULL DEFAULT FALSE,
    fim_ts BIGINT,
    apagado BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_form_sessao_ativa
    ON form_sessoes (form_key, user_id) WHERE status = 'andamento';
CREATE INDEX IF NOT EXISTS idx_form_sessoes_canal ON form_sessoes (channel_id);

CREATE TABLE IF NOT EXISTS form_envios (
    id BIGSERIAL PRIMARY KEY,
    sessao_id BIGINT,
    form_key TEXT NOT NULL,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    respostas JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente',
    decidido_por BIGINT,
    motivo TEXT,
    enviado_ts BIGINT NOT NULL,
    decidido_ts BIGINT,
    msg_id BIGINT,
    canal_resp_id BIGINT
);
CREATE INDEX IF NOT EXISTS idx_form_envios_user ON form_envios (form_key, user_id);

CREATE TABLE IF NOT EXISTS form_paineis (
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    form_key TEXT NOT NULL,
    PRIMARY KEY (guild_id, message_id)
);
"""


# ════════════════════════════════════════════════════════════════
#                       LÓGICA PURA (testável)
# ════════════════════════════════════════════════════════════════


class _Seguro(dict):
    def __missing__(self, chave):
        return "{" + chave + "}"


def formatar(texto: str, **dados) -> str:
    try:
        return texto.format_map(_Seguro(**dados))
    except (IndexError, ValueError, KeyError):
        return texto


def slug(texto: str, limite: int = 20) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:limite].strip("-")


def parsear_data(texto: str | None) -> int | None:
    """'2026-12-31 23:59' (horário de Brasília) → timestamp."""
    if not texto:
        return None
    return int(datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=FUSO).timestamp())


def tipo_efetivo(q: dict) -> str:
    return "escolha" if q["tipo"] == "sim_nao" else q["tipo"]


def opcoes_da(q: dict) -> list[tuple[str, str | None]]:
    brutas = q.get("opcoes") or (["Sim", "Não"] if q["tipo"] == "sim_nao" else [])
    saida = []
    for o in brutas:
        if isinstance(o, str):
            saida.append((o, None))
        else:
            saida.append((o[0], o[1] if len(o) > 1 else None))
    return saida


def obrigatoria(q: dict) -> bool:
    return q.get("obrigatoria", True)


def deve_perguntar(q: dict, respostas: dict) -> bool:
    se = q.get("se")
    if not se:
        return True
    chave, valor = se
    atual = respostas.get(chave)
    return valor in atual if isinstance(atual, list) else atual == valor


def proxima_etapa(form: dict, respostas: dict, etapa: int, sentido: int = 1) -> int:
    """Próxima pergunta aplicável. Retorna len(perguntas) para a revisão final."""
    perguntas = form["perguntas"]
    n = len(perguntas)
    i = etapa + sentido
    while 0 <= i < n and not deve_perguntar(perguntas[i], respostas):
        i += sentido
    if i < 0:
        i = 0
        while i < n and not deve_perguntar(perguntas[i], respostas):
            i += 1
    return min(i, n)


def respostas_validas(form: dict, respostas: dict) -> dict:
    """Mantém só as respostas das perguntas que se aplicam (nas condicionais)."""
    saida: dict = {}
    for q in form["perguntas"]:
        if deve_perguntar(q, saida):
            saida[q["id"]] = respostas.get(q["id"])
    return saida


def faltando_obrigatorias(form: dict, respostas: dict) -> list[str]:
    validas = respostas_validas(form, respostas)
    return [
        q["texto"]
        for q in form["perguntas"]
        if q["id"] in validas and obrigatoria(q) and validas[q["id"]] in (None, "", [])
    ]


REGEX_CONVITE = r"(?:discord\.gg|discord(?:app)?\.com/invite)/[\w-]+"


def validar_texto(q: dict, texto: str | None) -> tuple[bool, str]:
    t = (texto or "").strip()
    if not t:
        return False, "Envie a sua resposta em texto."
    tipo = q["tipo"]
    if tipo == "numero":
        limpo = re.sub(r"[.\s]", "", t)
        if not re.fullmatch(r"-?\d+", limpo):
            return False, "Responda apenas com um número (ex.: 17)."
        v = int(limpo)
        if "min" in q and v < q["min"]:
            return False, f"O valor mínimo é {q['min']}."
        if "max" in q and v > q["max"]:
            return False, f"O valor máximo é {q['max']}."
        return True, str(v)
    minimo = q.get("min_chars", 0)
    maximo = q.get("max_chars", 1500 if tipo == "paragrafo" else 300)
    if len(t) < minimo:
        return False, f"Escreva um pouco mais: mínimo de {minimo} caracteres (você enviou {len(t)})."
    if len(t) > maximo:
        return False, f"Resposta muito longa: máximo de {maximo} caracteres (você enviou {len(t)})."
    if q.get("validar") == "url" and not re.fullmatch(r"https?://\S+", t, re.IGNORECASE):
        return False, "Envie um link válido, começando com http:// ou https://."
    if q.get("validar") == "convite" and not re.search(REGEX_CONVITE, t, re.IGNORECASE):
        return False, "Envie um convite do Discord (ex.: https://discord.gg/abc123)."
    return True, t


def validar_anexos(q: dict, anexos: list[dict]) -> tuple[bool, object]:
    if not anexos:
        return False, "Envie o arquivo como anexo da mensagem" + (
            " (ou um link)." if q.get("aceita_link") else "."
        )
    limite = q.get("max_arquivos", 3)
    if len(anexos) > limite:
        return False, f"Envie no máximo {limite} arquivo(s) por vez."
    return True, anexos


def texto_resposta(q: dict, valor) -> str:
    if valor in (None, "", []):
        return "—"
    if q["tipo"] == "anexo":
        return "\n".join(f"[{a.get('nome', 'arquivo')}]({a['url']})" for a in valor)
    if isinstance(valor, list):
        return ", ".join(valor)
    return str(valor)


def barra(atual: int, total: int, tamanho: int = 10) -> str:
    cheios = round(tamanho * atual / total) if total else 0
    return "▰" * cheios + "▱" * (tamanho - cheios)


def status_do_form(form: dict, aberto_manual: bool, enviados: int, agora: int | None = None) -> tuple[str, str]:
    """Retorna (código, texto) da disponibilidade."""
    agora = agora or int(time.time())
    abre, encerra = parsear_data(form.get("abre_em")), parsear_data(form.get("encerra_em"))
    if not aberto_manual:
        return "pausado", "⏸️ Pausado pela equipe"
    if abre and agora < abre:
        return "em_breve", "⏳ Abre em breve"
    if encerra and agora >= encerra:
        return "encerrado", "🔒 Encerrado"
    if form.get("max_respostas") and enviados >= form["max_respostas"]:
        return "esgotado", "🔒 Vagas esgotadas"
    return "aberto", "🟢 Aberto"


def validar_config(forms: dict) -> list[str]:
    erros = []
    for chave, f in forms.items():
        if not re.fullmatch(r"[a-z0-9_]+", chave):
            erros.append(f"[{chave}] a chave só pode ter letras minúsculas, números e _")
        ids = [q["id"] for q in f["perguntas"]]
        if len(ids) != len(set(ids)):
            erros.append(f"[{chave}] há ids de perguntas repetidos")
        if not f["perguntas"]:
            erros.append(f"[{chave}] não tem perguntas")
        for campo in ("abre_em", "encerra_em"):
            try:
                parsear_data(f.get(campo))
            except ValueError:
                erros.append(f"[{chave}] '{campo}' deve ser 'AAAA-MM-DD HH:MM'")
        for q in f["perguntas"]:
            t = tipo_efetivo(q)
            if t not in ("texto", "paragrafo", "numero", "escolha", "multi", "anexo"):
                erros.append(f"[{chave}/{q['id']}] tipo desconhecido: {q['tipo']}")
            if t in ("escolha", "multi") and not (1 <= len(opcoes_da(q)) <= 25):
                erros.append(f"[{chave}/{q['id']}] precisa de 1 a 25 opções")
            if len(q["texto"]) > 250:
                erros.append(f"[{chave}/{q['id']}] texto da pergunta muito longo (máx. 250)")
            if q.get("se") and q["se"][0] not in ids[: ids.index(q["id"])]:
                erros.append(f"[{chave}/{q['id']}] 'se' precisa apontar para uma pergunta anterior")
        if not (f.get("canal_respostas_id") or CANAL_RESPOSTAS_PADRAO_ID):
            erros.append(f"[{chave}] defina 'canal_respostas_id' (canal da staff que recebe as respostas)")
    return erros


def eh_staff(membro) -> bool:
    if not isinstance(membro, discord.Member):
        return False
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in CARGOS_STAFF for r in membro.roles)


def eh_avaliador(membro, form: dict) -> bool:
    if eh_staff(membro):
        return True
    return isinstance(membro, discord.Member) and any(
        r.id in (form.get("cargos_avaliadores") or []) for r in membro.roles
    )


def apenas_staff():
    async def predicate(ctx: commands.Context):
        if ctx.guild is not None and eh_staff(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def protocolo_de(envio_id: int, ts: int) -> str:
    d = datetime.fromtimestamp(ts, FUSO)
    return f"FORM-{d.year % 100:02d}{d.month:02d}-{envio_id:04d}"


def embed_base(descricao: str, cor: int = COR_AZUL, banner: str = "", titulo: str | None = None) -> discord.Embed:
    e = discord.Embed(title=titulo, description=descricao[:4096], color=cor, timestamp=datetime.now(timezone.utc))
    e.set_footer(text=f"{NOME_SERVIDOR} • Formulários")
    if banner and banner.lower().startswith("http"):
        e.set_image(url=banner)
    return e


def aviso(texto: str) -> discord.Embed:
    return embed_base(texto, COR_AZUL_CLARO)


# ════════════════════════════════════════════════════════════════
#                  BOTÕES / MENUS (persistentes, dinâmicos)
# ════════════════════════════════════════════════════════════════

# ação: (rótulo, emoji, estilo)
BOTOES = {
    "ini": ("Aceito e quero começar", "✅", discord.ButtonStyle.success),
    "can": ("Cancelar", "✖️", discord.ButtonStyle.danger),
    "cc": ("Sim, cancelar o formulário", "🗑️", discord.ButtonStyle.danger),
    "vol": ("Voltar", "↩️", discord.ButtonStyle.secondary),
    "pul": ("Pular", "⏭️", discord.ButtonStyle.secondary),
    "opc": ("Opção", None, discord.ButtonStyle.primary),
    "env": ("Enviar formulário", "📨", discord.ButtonStyle.success),
    "cor": ("Corrigir uma resposta", "✏️", discord.ButtonStyle.secondary),
    "ap": ("Aprovar", "✅", discord.ButtonStyle.success),
    "rc": ("Recusar", "❌", discord.ButtonStyle.danger),
}


class BotaoForm(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"form:(?P<acao>[a-z]+):(?P<id>\d+)(?::(?P<a>\d+))?(?::(?P<b>\d+))?",
):
    """Os dados ficam no custom_id: continua funcionando depois de reiniciar."""

    def __init__(self, acao, id_, a=None, b=None, rotulo=None, emoji=None, row=None):
        padrao = BOTOES[acao]
        cid = f"form:{acao}:{id_}" + (f":{a}" if a is not None else "") + (f":{b}" if b is not None else "")
        super().__init__(
            discord.ui.Button(
                label=rotulo or padrao[0],
                emoji=emoji if emoji is not None else padrao[1],
                style=padrao[2],
                custom_id=cid,
                row=row,
            )
        )
        self.acao, self.id_, self.a, self.b = acao, int(id_), a, b

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        if match["acao"] not in BOTOES:
            raise ValueError("ação desconhecida")
        a = int(match["a"]) if match["a"] is not None else None
        b = int(match["b"]) if match["b"] is not None else None
        return cls(match["acao"], int(match["id"]), a, b)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Formularios")
        if cog is None:
            return await interaction.response.send_message("❌ Sistema indisponível.", ephemeral=True)
        await cog.tratar_botao(interaction, self.acao, self.id_, self.a, self.b)


class SelectForm(
    discord.ui.DynamicItem[discord.ui.Select],
    template=r"formsel:(?P<tipo>[a-z]+):(?P<sid>\d+):(?P<etapa>\d+)",
):
    def __init__(self, tipo, sid, etapa, opcoes=None, placeholder="Escolha...", maximo=1):
        opcoes = opcoes or [discord.SelectOption(label="…", value="0")]
        super().__init__(
            discord.ui.Select(
                custom_id=f"formsel:{tipo}:{sid}:{etapa}",
                placeholder=placeholder[:150],
                options=opcoes,
                min_values=1,
                max_values=max(1, min(maximo, len(opcoes))),
            )
        )
        self.tipo, self.sid, self.etapa = tipo, int(sid), int(etapa)

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["tipo"], int(match["sid"]), int(match["etapa"]))

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Formularios")
        if cog is None:
            return await interaction.response.send_message("❌ Sistema indisponível.", ephemeral=True)
        valores = (interaction.data or {}).get("values", [])
        await cog.tratar_select(interaction, self.tipo, self.sid, self.etapa, valores)


class BotaoPainelForm(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"formpainel:(?P<acao>[a-z]+):(?P<chave>[a-z0-9_]+)",
):
    def __init__(self, acao: str, chave: str, desabilitado: bool = False, rotulo: str | None = None):
        if acao == "ini":
            rotulo = rotulo or "Iniciar Formulário"
            emoji, estilo = "📝", discord.ButtonStyle.primary
        else:
            rotulo = rotulo or "Meu Status"
            emoji, estilo = "📂", discord.ButtonStyle.secondary
        super().__init__(
            discord.ui.Button(
                label=rotulo,
                emoji=emoji,
                style=estilo,
                custom_id=f"formpainel:{acao}:{chave}",
                disabled=desabilitado,
            )
        )
        self.acao, self.chave = acao, chave

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["acao"], match["chave"])

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Formularios")
        if cog is None:
            return await interaction.response.send_message("❌ Sistema indisponível.", ephemeral=True)
        if self.acao == "ini":
            await cog.iniciar(interaction, self.chave)
        else:
            await cog.meu_status(interaction, self.chave)


def view_painel(chave: str, aberto: bool) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(BotaoPainelForm("ini", chave, desabilitado=not aberto, rotulo=None if aberto else "Indisponível"))
    v.add_item(BotaoPainelForm("st", chave))
    return v


class DecisaoModal(discord.ui.Modal):
    def __init__(self, cog: "Formularios", envio_id: int, aprovar: bool):
        super().__init__(title="Aprovar candidato" if aprovar else "Recusar candidato", timeout=300)
        self.cog, self.envio_id, self.aprovar = cog, envio_id, aprovar
        self.motivo = discord.ui.TextInput(
            label="Observação (opcional)" if aprovar else "Motivo da recusa",
            placeholder="Será enviado ao candidato.",
            style=discord.TextStyle.paragraph,
            required=not aprovar,
            max_length=400,
        )
        self.add_item(self.motivo)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.decidir(interaction, self.envio_id, self.aprovar, str(self.motivo).strip())


# ════════════════════════════════════════════════════════════════
#                                COG
# ════════════════════════════════════════════════════════════════


class Formularios(commands.Cog, name="Formularios"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pronto = False
        self.canais: dict[int, int] = {}          # canal privado → id da sessão
        self.locks: dict[int, asyncio.Lock] = {}
        self.manual: dict[str, bool] = {}         # abrir/fechar manual
        self.ultimo_status: dict[str, str] = {}
        self.aux: set[asyncio.Task] = set()
        self.painel_pendente: set[str] = set()

    @property
    def pool(self):
        return getattr(self.bot, "pool", None)

    def _lock(self, sid: int) -> asyncio.Lock:
        return self.locks.setdefault(sid, asyncio.Lock())

    def _tarefa(self, coro):
        t = asyncio.create_task(coro)
        self.aux.add(t)
        t.add_done_callback(self.aux.discard)
        return t

    # ── Ciclo de vida ───────────────────────────────────────────
    async def cog_load(self):
        self.bot.add_dynamic_items(BotaoForm, SelectForm, BotaoPainelForm)
        self._tarefa(self._iniciar())
        self.manutencao.start()

    async def cog_unload(self):
        self.manutencao.cancel()
        for t in list(self.aux):
            t.cancel()

    async def _iniciar(self):
        await self.bot.wait_until_ready()
        if self.pool is None:
            print("[formularios] ERRO: bot.pool não existe. Configure o PostgreSQL no main.py.")
            return
        try:
            await self.pool.execute(SQL_TABELAS)
            for r in await self.pool.fetch("SELECT form_key, aberto FROM form_estado"):
                self.manual[r["form_key"]] = r["aberto"]
            for r in await self.pool.fetch(
                "SELECT id, channel_id FROM form_sessoes WHERE status='andamento' AND channel_id IS NOT NULL"
            ):
                self.canais[r["channel_id"]] = r["id"]
            for erro in validar_config(FORMULARIOS):
                print(f"[formularios] CONFIG: {erro}")
            self.pronto = True
            for chave in FORMULARIOS:
                await self._atualizar_paineis(chave)
            print(f"[formularios] Pronto: {len(FORMULARIOS)} formulário(s), {len(self.canais)} sessão(ões) em andamento.")
        except Exception as e:  # noqa: BLE001
            print(f"[formularios] ERRO ao iniciar: {type(e).__name__}: {e}")

    # ── Estado / disponibilidade ────────────────────────────────
    async def _enviados(self, chave: str) -> int:
        return int(await self.pool.fetchval("SELECT COUNT(*) FROM form_envios WHERE form_key=$1", chave) or 0)

    async def estado_form(self, chave: str) -> dict:
        form = FORMULARIOS[chave]
        enviados = await self._enviados(chave)
        codigo, texto = status_do_form(form, self.manual.get(chave, True), enviados)
        maximo = form.get("max_respostas") or 0
        return {
            "codigo": codigo,
            "texto": texto,
            "enviados": enviados,
            "restantes": max(0, maximo - enviados) if maximo else None,
            "encerra_ts": parsear_data(form.get("encerra_em")),
            "abre_ts": parsear_data(form.get("abre_em")),
        }

    def _placeholders(self, form: dict, estado: dict, **extra) -> dict:
        n = len(form["perguntas"])
        maximo = form.get("max_respostas") or 0
        dados = {
            "encerra": (
                f"<t:{estado['encerra_ts']}:F> (<t:{estado['encerra_ts']}:R>)"
                if estado["encerra_ts"] else "Sem prazo definido"
            ),
            "abre": f"<t:{estado['abre_ts']}:F>" if estado["abre_ts"] else "Já aberto",
            "vagas": f"{estado['restantes']} de {maximo}" if maximo else "Ilimitadas",
            "status": estado["texto"],
            "total_perguntas": str(n),
            "tempo_estimado": f"{max(1, round(n * 0.7))} min",
            "inatividade": str(INATIVIDADE_MIN),
        }
        dados.update(extra)
        return dados

    async def embed_painel(self, chave: str) -> discord.Embed:
        form = FORMULARIOS[chave]
        estado = await self.estado_form(chave)
        texto = formatar(form["painel"].strip(), **self._placeholders(form, estado))
        return embed_base(texto, form.get("cor", COR_AZUL), form.get("banner", ""))

    async def _atualizar_paineis(self, chave: str):
        if chave not in FORMULARIOS:
            return
        estado = await self.estado_form(chave)
        embed = await self.embed_painel(chave)
        view = view_painel(chave, estado["codigo"] == "aberto")
        self.ultimo_status[chave] = estado["codigo"]
        for r in await self.pool.fetch("SELECT guild_id, channel_id, message_id FROM form_paineis WHERE form_key=$1", chave):
            canal = self.bot.get_channel(r["channel_id"])
            if canal is None:
                continue
            try:
                await canal.get_partial_message(r["message_id"]).edit(embed=embed, view=view)
            except discord.NotFound:
                await self.pool.execute(
                    "DELETE FROM form_paineis WHERE guild_id=$1 AND message_id=$2", r["guild_id"], r["message_id"]
                )
            except discord.HTTPException:
                pass

    def _agendar_painel(self, chave: str):
        if chave in self.painel_pendente:
            return
        self.painel_pendente.add(chave)

        async def tarefa():
            try:
                await asyncio.sleep(2)
            finally:
                self.painel_pendente.discard(chave)
            await self._atualizar_paineis(chave)

        self._tarefa(tarefa())

    # ── Sessões ─────────────────────────────────────────────────
    async def _sessao(self, sid: int):
        return await self.pool.fetchrow("SELECT * FROM form_sessoes WHERE id=$1", sid)

    @staticmethod
    def _respostas(s) -> dict:
        r = s["respostas"]
        return json.loads(r) if isinstance(r, str) else dict(r or {})

    async def _encerrar_sessao(self, sid: int, status: str):
        await self.pool.execute(
            "UPDATE form_sessoes SET status=$2, fim_ts=$3 WHERE id=$1", sid, status, int(time.time())
        )
        for cid, x in list(self.canais.items()):
            if x == sid:
                self.canais.pop(cid, None)

    async def _apagar_canal(self, canal_id: int | None, atraso: float, sid: int | None = None):
        await asyncio.sleep(atraso)
        canal = self.bot.get_channel(canal_id) if canal_id else None
        if canal is not None:
            try:
                await canal.delete(reason="Formulário finalizado")
            except discord.HTTPException:
                pass
        if sid is not None:
            await self.pool.execute("UPDATE form_sessoes SET apagado=TRUE WHERE id=$1", sid)

    # ── Início (botão do painel) ────────────────────────────────
    async def _verificar(self, guild: discord.Guild, membro: discord.Member, chave: str) -> str | None:
        form = FORMULARIOS[chave]
        estado = await self.estado_form(chave)
        if estado["codigo"] != "aberto":
            extra = ""
            if estado["codigo"] == "em_breve" and estado["abre_ts"]:
                extra = f" Abre <t:{estado['abre_ts']}:R>."
            return f"🔒 Este formulário não está disponível: {estado['texto']}.{extra}"

        ids = {r.id for r in membro.roles}
        exigidos = form.get("cargos_exigidos") or []
        if exigidos and not (ids & set(exigidos)):
            return "🔒 Este formulário é restrito a membros com um cargo específico."
        if ids & set(form.get("cargos_bloqueados") or []):
            return "🚫 Você não pode responder este formulário."
        dias = form.get("dias_no_servidor_min") or 0
        if dias and membro.joined_at and (datetime.now(timezone.utc) - membro.joined_at).days < dias:
            return f"⏳ Você precisa estar há pelo menos **{dias} dia(s)** no servidor para responder."

        ativa = await self.pool.fetchrow(
            "SELECT id, channel_id FROM form_sessoes WHERE form_key=$1 AND user_id=$2 AND status='andamento'",
            chave, membro.id,
        )
        if ativa:
            canal = guild.get_channel(ativa["channel_id"]) if ativa["channel_id"] else None
            if canal:
                return f"📌 Você já tem este formulário em andamento: {canal.mention}"
            await self._encerrar_sessao(ativa["id"], "cancelado")

        if form.get("uma_por_usuario", True):
            ultimo = await self.pool.fetchrow(
                "SELECT status, decidido_ts FROM form_envios WHERE form_key=$1 AND user_id=$2 ORDER BY id DESC LIMIT 1",
                chave, membro.id,
            )
            if ultimo:
                if ultimo["status"] in ("pendente", "aprovado"):
                    return f"📌 Você já enviou este formulário (situação: **{ultimo['status']}**)."
                dias_cd = form.get("cooldown_recusa_dias") or 0
                if dias_cd and ultimo["decidido_ts"]:
                    libera = ultimo["decidido_ts"] + dias_cd * 86400
                    if time.time() < libera:
                        return f"⏳ Você poderá tentar de novo <t:{libera}:R>."
        return None

    async def iniciar(self, interaction: discord.Interaction, chave: str):
        if not self.pronto or chave not in FORMULARIOS:
            return await interaction.response.send_message("❌ Formulário indisponível no momento.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        guild, membro = interaction.guild, interaction.user
        form = FORMULARIOS[chave]

        erro = await self._verificar(guild, membro, chave)
        if erro:
            return await interaction.followup.send(erro, ephemeral=True)

        agora = int(time.time())
        try:
            sid = await self.pool.fetchval(
                "INSERT INTO form_sessoes (form_key, guild_id, user_id, iniciado_ts, atividade_ts) "
                "VALUES ($1,$2,$3,$4,$4) RETURNING id",
                chave, guild.id, membro.id, agora,
            )
        except asyncpg.UniqueViolationError:
            return await interaction.followup.send("📌 Você já tem este formulário em andamento.", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membro: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True,
                embed_links=True, read_message_history=True, add_reactions=False,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True,
                manage_messages=True, embed_links=True, attach_files=True, add_reactions=True,
            ),
        }
        for rid in dict.fromkeys(list(CARGOS_STAFF) + list(form.get("cargos_avaliadores") or [])):
            cargo = guild.get_role(rid)
            if cargo:
                overwrites[cargo] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                )
        categoria = guild.get_channel(CATEGORIA_FORMS_ID) if CATEGORIA_FORMS_ID else None
        if not isinstance(categoria, discord.CategoryChannel):
            categoria = getattr(interaction.channel, "category", None)

        try:
            canal = await guild.create_text_channel(
                name=f"form-{slug(membro.display_name, 14) or membro.id}-{sid:04d}",
                category=categoria,
                overwrites=overwrites,
                topic=f"form={chave};user={membro.id};sessao={sid}",
                reason=f"Formulário {form['nome']} de {membro}",
            )
        except discord.HTTPException as e:
            await self._encerrar_sessao(sid, "cancelado")
            return await interaction.followup.send(
                f"❌ Não consegui criar o seu canal ({e.text}). Avise a staff.", ephemeral=True
            )

        await self.pool.execute("UPDATE form_sessoes SET channel_id=$2 WHERE id=$1", sid, canal.id)
        self.canais[canal.id] = sid

        estado = await self.estado_form(chave)
        texto = formatar(form["boas_vindas"].strip(), usuario=membro.mention, **self._placeholders(form, estado))
        view = discord.ui.View(timeout=None)
        view.add_item(BotaoForm("ini", sid))
        view.add_item(BotaoForm("can", sid))
        msg = await canal.send(
            content=membro.mention,
            embed=embed_base(texto, form.get("cor", COR_AZUL), form.get("banner", "")),
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )
        await self.pool.execute("UPDATE form_sessoes SET msg_id=$2 WHERE id=$1", sid, msg.id)
        await interaction.followup.send(f"✅ Seu formulário está pronto em {canal.mention}.", ephemeral=True)

    async def meu_status(self, interaction: discord.Interaction, chave: str):
        if not self.pronto or chave not in FORMULARIOS:
            return await interaction.response.send_message("❌ Indisponível no momento.", ephemeral=True)
        linhas = await self.pool.fetch(
            "SELECT id, status, enviado_ts, decidido_ts, motivo FROM form_envios "
            "WHERE form_key=$1 AND user_id=$2 ORDER BY id DESC LIMIT 5",
            chave, interaction.user.id,
        )
        if not linhas:
            texto = "Você ainda não enviou este formulário."
        else:
            icone = {"pendente": "⏳ em análise", "aprovado": "✅ aprovado", "recusado": "❌ recusado"}
            partes = []
            for r in linhas:
                linha = f"`{protocolo_de(r['id'], r['enviado_ts'])}` • {icone.get(r['status'], r['status'])} • <t:{r['enviado_ts']}:d>"
                if r["motivo"]:
                    linha += f"\n> `💬` {r['motivo']}"
                partes.append(linha)
            texto = "\n".join(partes)
        await interaction.response.send_message(
            embed=embed_base(f"# 📂 **Meu status**\n{FORMULARIOS[chave]['nome']}\n\n{texto}"), ephemeral=True
        )

    # ── Conversa: perguntas ─────────────────────────────────────
    def _embed_pergunta(self, form: dict, s, idx: int) -> discord.Embed:
        q = form["perguntas"][idx]
        respostas = self._respostas(s)
        aplicaveis = [i for i, x in enumerate(form["perguntas"]) if deve_perguntar(x, respostas)]
        posicao = aplicaveis.index(idx) + 1 if idx in aplicaveis else idx + 1
        total = len(aplicaveis)
        tipo = tipo_efetivo(q)
        como = {
            "texto": "Responda enviando uma mensagem aqui no canal.",
            "paragrafo": "Responda enviando uma mensagem aqui no canal.",
            "numero": "Responda enviando um número aqui no canal.",
            "anexo": "Envie o arquivo como anexo da mensagem" + (" (ou um link)." if q.get("aceita_link") else "."),
            "escolha": "Escolha uma opção abaixo.",
            "multi": f"Escolha até {q.get('max', len(opcoes_da(q)))} opção(ões) no menu abaixo.",
        }[tipo]
        linhas = [
            f"# ❓ Pergunta {posicao}/{total}",
            f"**{q['texto']}**",
            "",
            f"> `✍️` {como}",
            f"> `{'📌' if obrigatoria(q) else '➖'}` {'Obrigatória' if obrigatoria(q) else 'Opcional — você pode pular'}",
        ]
        if q.get("dica"):
            linhas.append(f"> `💡` {q['dica']}")
        atual = respostas.get(q["id"])
        if atual not in (None, "", []):
            linhas.append(f"> `📝` Resposta atual: {texto_resposta(q, atual)[:200]}")
        linhas += ["", f"`{barra(posicao - 1, total)}` {round(100 * (posicao - 1) / total)}%"]
        return embed_base("\n".join(linhas), form.get("cor", COR_AZUL))

    def _view_pergunta(self, form: dict, s, idx: int) -> discord.ui.View:
        q = form["perguntas"][idx]
        sid = s["id"]
        tipo = tipo_efetivo(q)
        view = discord.ui.View(timeout=None)
        opcoes = opcoes_da(q)
        if tipo == "escolha" and len(opcoes) <= 5:
            for i, (nome, emoji) in enumerate(opcoes):
                view.add_item(BotaoForm("opc", sid, idx, i, rotulo=nome[:80], emoji=emoji, row=0))
        elif tipo in ("escolha", "multi"):
            maximo = 1 if tipo == "escolha" else min(q.get("max", len(opcoes)), len(opcoes))
            view.add_item(
                SelectForm(
                    "resp", sid, idx,
                    opcoes=[discord.SelectOption(label=n[:100], value=str(i), emoji=e) for i, (n, e) in enumerate(opcoes)],
                    placeholder="Escolha..." if maximo == 1 else f"Escolha até {maximo}...",
                    maximo=maximo,
                )
            )
        primeira = proxima_etapa(form, self._respostas(s), idx, -1) == idx
        if not primeira:
            view.add_item(BotaoForm("vol", sid, idx, row=1))
        if not obrigatoria(q):
            view.add_item(BotaoForm("pul", sid, idx, row=1))
        view.add_item(BotaoForm("can", sid, row=1))
        return view

    async def _limpar_botoes(self, canal, msg_id):
        if not msg_id:
            return
        try:
            await canal.get_partial_message(msg_id).edit(view=None)
        except discord.HTTPException:
            pass

    async def _apresentar(self, canal, sid: int, digitando: bool = True):
        s = await self._sessao(sid)
        form = FORMULARIOS[s["form_key"]]
        n = len(form["perguntas"])
        await self._limpar_botoes(canal, s["msg_id"])
        if digitando and DIGITANDO_SEG:
            try:
                async with canal.typing():
                    await asyncio.sleep(DIGITANDO_SEG)
            except discord.HTTPException:
                pass
        if s["etapa"] >= n:
            embed, view = self._embed_revisao(form, s), self._view_revisao(sid)
        else:
            embed, view = self._embed_pergunta(form, s, s["etapa"]), self._view_pergunta(form, s, s["etapa"])
        msg = await canal.send(embed=embed, view=view)
        await self.pool.execute("UPDATE form_sessoes SET msg_id=$2, atividade_ts=$3, avisou=FALSE WHERE id=$1", sid, msg.id, int(time.time()))

    async def _guardar(self, s, q: dict, valor):
        respostas = self._respostas(s)
        respostas[q["id"]] = valor
        await self.pool.execute(
            "UPDATE form_sessoes SET respostas=$2::jsonb, atividade_ts=$3, avisou=FALSE WHERE id=$1",
            s["id"], json.dumps(respostas, ensure_ascii=False), int(time.time()),
        )

    async def _avancar(self, canal, sid: int, sentido: int = 1):
        s = await self._sessao(sid)
        form = FORMULARIOS[s["form_key"]]
        n = len(form["perguntas"])
        if s["corrigindo"] and sentido > 0:
            nova = n
        else:
            nova = proxima_etapa(form, self._respostas(s), s["etapa"], sentido)
        await self.pool.execute("UPDATE form_sessoes SET etapa=$2, corrigindo=FALSE WHERE id=$1", sid, nova)
        await self._apresentar(canal, sid)

    # ── Conversa: revisão ───────────────────────────────────────
    def _embed_revisao(self, form: dict, s) -> discord.Embed:
        validas = respostas_validas(form, self._respostas(s))
        n = len(validas) or 1
        corte = max(80, min(400, 4800 // n - 60))
        e = embed_base(
            "# 🔎 **Revise as suas respostas**\nConfira tudo antes de enviar. "
            "Depois do envio **não será possível editar**.",
            form.get("cor", COR_AZUL),
        )
        for q in form["perguntas"]:
            if q["id"] in validas:
                texto = texto_resposta(q, validas[q["id"]])
                e.add_field(name=q["texto"][:250], value=(texto[:corte] + ("…" if len(texto) > corte else "")) or "—", inline=False)
        return e

    def _view_revisao(self, sid: int) -> discord.ui.View:
        v = discord.ui.View(timeout=None)
        v.add_item(BotaoForm("env", sid, row=0))
        v.add_item(BotaoForm("cor", sid, row=0))
        v.add_item(BotaoForm("can", sid, row=0))
        return v

    # ── Mensagens do candidato ──────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not self.pronto:
            return
        sid = self.canais.get(message.channel.id)
        if sid is None:
            return
        async with self._lock(sid):
            s = await self._sessao(sid)
            if s is None or s["status"] != "andamento" or message.author.id != s["user_id"]:
                return
            form = FORMULARIOS.get(s["form_key"])
            if form is None:
                return
            etapa, n = s["etapa"], len(form["perguntas"])
            if etapa < 0 or etapa >= n:
                return
            q = form["perguntas"][etapa]
            tipo = tipo_efetivo(q)
            await self.pool.execute("UPDATE form_sessoes SET atividade_ts=$2, avisou=FALSE WHERE id=$1", sid, int(time.time()))

            if tipo in ("escolha", "multi"):
                return await message.channel.send(embed=aviso("👆 Use os botões/menu da pergunta acima para responder."), delete_after=8)

            if tipo == "anexo":
                anexos = [{"url": a.url, "nome": a.filename} for a in message.attachments]
                if not anexos and q.get("aceita_link"):
                    achado = re.search(r"https?://\S+", message.content or "")
                    if achado:
                        anexos = [{"url": achado.group(), "nome": "link"}]
                ok, valor = validar_anexos(q, anexos)
            else:
                ok, valor = validar_texto(q, message.content)

            if not ok:
                return await message.channel.send(embed=aviso(f"⚠️ {valor}"), delete_after=12)

            await self._guardar(s, q, valor)
            try:
                await message.add_reaction("✅")
            except discord.HTTPException:
                pass
            await self._avancar(message.channel, sid)

    # ── Botões ──────────────────────────────────────────────────
    async def tratar_botao(self, interaction: discord.Interaction, acao: str, id_: int, a, b):
        if not self.pronto:
            return await interaction.response.send_message("❌ Sistema indisponível no momento.", ephemeral=True)
        if acao in ("ap", "rc"):
            return await self._botao_decisao(interaction, acao, id_)

        async with self._lock(id_):
            s = await self._sessao(id_)
            if s is None or s["status"] != "andamento":
                return await interaction.response.send_message("❌ Este formulário já foi encerrado.", ephemeral=True)
            if interaction.user.id != s["user_id"]:
                return await interaction.response.send_message("❌ Este formulário não é seu.", ephemeral=True)
            form = FORMULARIOS.get(s["form_key"])
            if form is None:
                return await interaction.response.send_message("❌ Formulário não existe mais.", ephemeral=True)
            n = len(form["perguntas"])
            canal = interaction.channel

            if acao == "ini":
                if s["etapa"] != -1:
                    return await interaction.response.send_message("⚠️ Você já começou.", ephemeral=True)
                await interaction.response.defer()
                primeira = proxima_etapa(form, {}, -1, 1)
                await self.pool.execute("UPDATE form_sessoes SET etapa=$2 WHERE id=$1", id_, primeira)
                return await self._apresentar(canal, id_)

            if acao == "can":
                v = discord.ui.View(timeout=120)
                v.add_item(BotaoForm("cc", id_))
                return await interaction.response.send_message(
                    embed=aviso("⚠️ Tem certeza? **Você perderá as respostas** e o canal será apagado."),
                    view=v, ephemeral=True,
                )

            if acao == "cc":
                await interaction.response.defer()
                await self._encerrar_sessao(id_, "cancelado")
                await self._limpar_botoes(canal, s["msg_id"])
                await canal.send(embed=aviso("🗑️ Formulário cancelado. Este canal será apagado em instantes."))
                self._tarefa(self._apagar_canal(s["channel_id"], 5, id_))
                return

            if acao in ("vol", "pul", "opc") and a != s["etapa"]:
                return await interaction.response.send_message("⌛ Essa pergunta já foi respondida.", ephemeral=True)

            if acao == "vol":
                await interaction.response.defer()
                nova = proxima_etapa(form, self._respostas(s), s["etapa"], -1)
                await self.pool.execute("UPDATE form_sessoes SET etapa=$2, corrigindo=FALSE WHERE id=$1", id_, nova)
                return await self._apresentar(canal, id_, digitando=False)

            if acao == "pul":
                q = form["perguntas"][s["etapa"]]
                if obrigatoria(q):
                    return await interaction.response.send_message("❌ Esta pergunta é obrigatória.", ephemeral=True)
                await interaction.response.defer()
                await self._guardar(s, q, None)
                return await self._avancar(canal, id_)

            if acao == "opc":
                q = form["perguntas"][s["etapa"]]
                opcoes = opcoes_da(q)
                if b is None or b >= len(opcoes):
                    return await interaction.response.send_message("❌ Opção inválida.", ephemeral=True)
                await interaction.response.defer()
                await self._guardar(s, q, opcoes[b][0])
                return await self._avancar(canal, id_)

            if acao == "cor":
                if s["etapa"] < n:
                    return await interaction.response.send_message("⌛ Isso só está disponível na revisão.", ephemeral=True)
                validas = respostas_validas(form, self._respostas(s))
                opcoes = [
                    discord.SelectOption(label=q["texto"][:100], value=str(i))
                    for i, q in enumerate(form["perguntas"]) if q["id"] in validas
                ][:25]
                v = discord.ui.View(timeout=180)
                v.add_item(SelectForm("cor", id_, 0, opcoes=opcoes, placeholder="Qual resposta corrigir?"))
                return await interaction.response.send_message(view=v, ephemeral=True, content="✏️ Escolha a pergunta que deseja responder de novo:")

            if acao == "env":
                if s["etapa"] < n:
                    return await interaction.response.send_message("⌛ Termine as perguntas antes de enviar.", ephemeral=True)
                await interaction.response.defer()
                return await self._enviar(canal, s, form, interaction.user)

    async def tratar_select(self, interaction: discord.Interaction, tipo: str, sid: int, etapa: int, valores: list[str]):
        if not self.pronto:
            return await interaction.response.send_message("❌ Sistema indisponível no momento.", ephemeral=True)
        async with self._lock(sid):
            s = await self._sessao(sid)
            if s is None or s["status"] != "andamento":
                return await interaction.response.send_message("❌ Este formulário já foi encerrado.", ephemeral=True)
            if interaction.user.id != s["user_id"]:
                return await interaction.response.send_message("❌ Este formulário não é seu.", ephemeral=True)
            form = FORMULARIOS.get(s["form_key"])
            canal = interaction.channel
            try:
                indices = [int(v) for v in valores]
            except ValueError:
                return await interaction.response.send_message("❌ Opção inválida.", ephemeral=True)

            if tipo == "cor":
                if not indices or indices[0] >= len(form["perguntas"]):
                    return await interaction.response.send_message("❌ Opção inválida.", ephemeral=True)
                await interaction.response.edit_message(content="✏️ Ok! Veja a pergunta no canal.", view=None)
                await self.pool.execute("UPDATE form_sessoes SET etapa=$2, corrigindo=TRUE WHERE id=$1", sid, indices[0])
                return await self._apresentar(canal, sid)

            if tipo == "resp":
                if etapa != s["etapa"]:
                    return await interaction.response.send_message("⌛ Essa pergunta já foi respondida.", ephemeral=True)
                q = form["perguntas"][etapa]
                opcoes = opcoes_da(q)
                if not indices or any(i >= len(opcoes) for i in indices):
                    return await interaction.response.send_message("❌ Opção inválida.", ephemeral=True)
                await interaction.response.defer()
                nomes = [opcoes[i][0] for i in indices]
                await self._guardar(s, q, nomes if tipo_efetivo(q) == "multi" else nomes[0])
                return await self._avancar(canal, sid)

    # ── Envio ───────────────────────────────────────────────────
    async def _baixar_anexos(self, respostas: dict, form: dict) -> list[discord.File]:
        urls = []
        for q in form["perguntas"]:
            if q["tipo"] == "anexo" and respostas.get(q["id"]):
                urls += [a for a in respostas[q["id"]] if a.get("nome") != "link"]
        arquivos = []
        if not urls:
            return arquivos
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as sessao:
                for a in urls[:8]:
                    try:
                        async with sessao.get(a["url"]) as r:
                            if r.status == 200 and (r.content_length or 0) <= 8_000_000:
                                arquivos.append(discord.File(io.BytesIO(await r.read()), filename=a["nome"][:80]))
                    except Exception:  # noqa: BLE001
                        continue
        except Exception:  # noqa: BLE001
            pass
        return arquivos

    def _embed_envio(self, form: dict, envio, membro_txt: str, modo: str = "staff") -> tuple[discord.Embed, str | None]:
        """Retorna (embed, texto_completo_se_houve_corte)."""
        respostas = envio["respostas"]
        respostas = json.loads(respostas) if isinstance(respostas, str) else dict(respostas)
        proto = protocolo_de(envio["id"], envio["enviado_ts"])
        n = len(respostas) or 1
        corte = max(120, min(900, 4800 // n - 60))
        icone = {"pendente": "⏳ Pendente de análise", "aprovado": "✅ Aprovado", "recusado": "❌ Recusado"}[envio["status"]]
        cab = [f"# 📥 Nova resposta • {proto}" if modo == "staff" else f"# 📬 Cópia das suas respostas • {proto}", f"**{form['nome']}**", ""]
        if modo == "staff":
            cab.append(f"> `👤` **Candidato:** {membro_txt}")
        cab.append(f"> `📅` **Enviado:** <t:{envio['enviado_ts']}:F>")
        cab.append(f"> `🔔` **Situação:** {icone}")
        if envio["status"] != "pendente" and envio["decidido_por"]:
            cab.append(f"> `⚖️` **Decidido por:** <@{envio['decidido_por']}> • <t:{envio['decidido_ts']}:R>")
        if envio["motivo"]:
            cab.append(f"> `💬` **Observação:** {envio['motivo']}")
        e = embed_base("\n".join(cab), form.get("cor", COR_AZUL))
        completo, cortou = [], False
        for q in form["perguntas"]:
            if q["id"] in respostas:
                texto = texto_resposta(q, respostas[q["id"]])
                completo.append(f"{q['texto']}\n{texto}\n")
                if len(texto) > corte:
                    cortou = True
                e.add_field(name=q["texto"][:250], value=(texto[:corte] + ("…" if len(texto) > corte else "")), inline=False)
        return e, ("\n".join(completo) if cortou else None)

    async def _enviar(self, canal, s, form: dict, membro: discord.Member):
        sid, chave = s["id"], s["form_key"]
        respostas = respostas_validas(form, self._respostas(s))
        falta = faltando_obrigatorias(form, respostas)
        if falta:
            return await canal.send(embed=aviso("⚠️ Ainda faltam respostas obrigatórias:\n> " + "\n> ".join(falta[:5])))

        agora = int(time.time())
        maximo = form.get("max_respostas") or 0
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"form:{chave}")
                total = int(await conn.fetchval("SELECT COUNT(*) FROM form_envios WHERE form_key=$1", chave) or 0)
                if maximo and total >= maximo:
                    envio_id = None
                else:
                    envio_id = await conn.fetchval(
                        "INSERT INTO form_envios (sessao_id, form_key, guild_id, user_id, respostas, enviado_ts) "
                        "VALUES ($1,$2,$3,$4,$5::jsonb,$6) RETURNING id",
                        sid, chave, s["guild_id"], s["user_id"], json.dumps(respostas, ensure_ascii=False), agora,
                    )
                    await conn.execute("UPDATE form_sessoes SET status='enviado', fim_ts=$2 WHERE id=$1", sid, agora)
        if envio_id is None:
            return await canal.send(embed=aviso("🔒 As vagas deste formulário esgotaram enquanto você respondia. Desculpe!"))

        for cid, x in list(self.canais.items()):
            if x == sid:
                self.canais.pop(cid, None)
        await self._limpar_botoes(canal, s["msg_id"])
        proto = protocolo_de(envio_id, agora)

        envio = await self.pool.fetchrow("SELECT * FROM form_envios WHERE id=$1", envio_id)
        guild = canal.guild

        # 1) Staff recebe
        canal_resp = guild.get_channel(form.get("canal_respostas_id") or CANAL_RESPOSTAS_PADRAO_ID)
        if canal_resp is not None:
            embed, completo = self._embed_envio(form, envio, f"{membro.mention} (`{membro.id}`)")
            embed.add_field(
                name="🕒 Perfil",
                value=(f"Conta criada <t:{int(membro.created_at.timestamp())}:R>"
                       + (f" • No servidor desde <t:{int(membro.joined_at.timestamp())}:R>" if membro.joined_at else "")),
                inline=False,
            )
            arquivos = await self._baixar_anexos(respostas, form)
            if completo:
                arquivos.append(discord.File(io.BytesIO(completo.encode("utf-8")), filename=f"respostas_{proto}.txt"))
            view = discord.ui.View(timeout=None)
            view.add_item(BotaoForm("ap", envio_id))
            view.add_item(BotaoForm("rc", envio_id))
            ping = " ".join(f"<@&{r}>" for r in (form.get("cargos_avaliadores") or []))
            try:
                msg = await canal_resp.send(
                    content=ping or None, embed=embed, view=view, files=arquivos[:10],
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
                await self.pool.execute("UPDATE form_envios SET msg_id=$2, canal_resp_id=$3 WHERE id=$1", envio_id, msg.id, canal_resp.id)
            except discord.HTTPException as e:
                log.error("Falha ao enviar resposta à staff: %s", e)

        # 2) Candidato recebe cópia por DM
        try:
            embed_dm, _ = self._embed_envio(form, envio, membro.mention, modo="dm")
            await membro.send(embed=embed_dm)
        except (discord.Forbidden, discord.HTTPException):
            pass

        # 3) Conclusão no canal
        estado = await self.estado_form(chave)
        texto = formatar(form["conclusao"].strip(), usuario=membro.mention, protocolo=proto, **self._placeholders(form, estado))
        await canal.send(embed=embed_base(texto, form.get("cor", COR_AZUL)))
        self._tarefa(self._apagar_canal(canal.id, APAGAR_CANAL_APOS_SEG, sid))
        self._agendar_painel(chave)

    # ── Decisão da staff ────────────────────────────────────────
    async def _botao_decisao(self, interaction: discord.Interaction, acao: str, envio_id: int):
        envio = await self.pool.fetchrow("SELECT * FROM form_envios WHERE id=$1", envio_id)
        if envio is None:
            return await interaction.response.send_message("❌ Resposta não encontrada.", ephemeral=True)
        form = FORMULARIOS.get(envio["form_key"])
        if form is None or not eh_avaliador(interaction.user, form):
            return await interaction.response.send_message("❌ Apenas quem avalia este formulário pode decidir.", ephemeral=True)
        if envio["status"] != "pendente":
            return await interaction.response.send_message("⚠️ Esta resposta já foi decidida.", ephemeral=True)
        await interaction.response.send_modal(DecisaoModal(self, envio_id, acao == "ap"))

    async def decidir(self, interaction: discord.Interaction, envio_id: int, aprovar: bool, motivo: str):
        status = "aprovado" if aprovar else "recusado"
        agora = int(time.time())
        envio = await self.pool.fetchrow(
            "UPDATE form_envios SET status=$2, decidido_por=$3, decidido_ts=$4, motivo=$5 "
            "WHERE id=$1 AND status='pendente' RETURNING *",
            envio_id, status, interaction.user.id, agora, motivo or None,
        )
        if envio is None:
            return await interaction.response.send_message("⚠️ Esta resposta já foi decidida.", ephemeral=True)
        await interaction.response.send_message(f"✅ Candidato **{status}**.", ephemeral=True)

        form = FORMULARIOS[envio["form_key"]]
        guild = interaction.guild
        membro = guild.get_member(envio["user_id"])

        extra = ""
        if aprovar and form.get("cargo_ao_aprovar") and membro:
            cargo = guild.get_role(form["cargo_ao_aprovar"])
            if cargo:
                try:
                    await membro.add_roles(cargo, reason=f"Aprovado no formulário {form['nome']}")
                    extra = f"\n> `🎖️` Cargo {cargo.mention} entregue automaticamente."
                except discord.HTTPException:
                    extra = "\n> `⚠️` Não consegui entregar o cargo automaticamente."

        # atualiza a mensagem da staff
        if envio["msg_id"] and envio["canal_resp_id"]:
            canal = self.bot.get_channel(envio["canal_resp_id"])
            if canal is not None:
                try:
                    embed, _ = self._embed_envio(form, envio, f"<@{envio['user_id']}> (`{envio['user_id']}`)")
                    await canal.get_partial_message(envio["msg_id"]).edit(embed=embed, view=None)
                except discord.HTTPException:
                    pass

        # avisa o candidato
        titulo = "✅ Aprovado!" if aprovar else "❌ Não aprovado"
        corpo = (
            f"# {titulo}\nSobre o formulário **{form['nome']}** (`{protocolo_de(envio_id, envio['enviado_ts'])}`):\n\n"
            f"> `⚖️` Resultado: **{status}**"
            + (f"\n> `💬` {motivo}" if motivo else "")
            + extra
        )
        try:
            user = membro or await self.bot.fetch_user(envio["user_id"])
            await user.send(embed=embed_base(corpo, form.get("cor", COR_AZUL)))
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── Manutenção (1 min) ──────────────────────────────────────
    @tasks.loop(minutes=1)
    async def manutencao(self):
        if not self.pronto:
            return
        agora = int(time.time())
        limite = INATIVIDADE_MIN * 60

        for s in await self.pool.fetch("SELECT * FROM form_sessoes WHERE status='andamento'"):
            canal = self.bot.get_channel(s["channel_id"]) if s["channel_id"] else None
            if s["channel_id"] and canal is None:
                await self._encerrar_sessao(s["id"], "cancelado")
                continue
            parado = agora - s["atividade_ts"]
            if canal is None:
                continue
            if parado >= limite:
                await self._encerrar_sessao(s["id"], "expirado")
                await self._limpar_botoes(canal, s["msg_id"])
                try:
                    await canal.send(embed=aviso("⌛ Formulário cancelado por inatividade. Você pode começar de novo pelo painel."))
                except discord.HTTPException:
                    pass
                self._tarefa(self._apagar_canal(s["channel_id"], 15, s["id"]))
            elif parado >= limite // 2 and not s["avisou"]:
                await self.pool.execute("UPDATE form_sessoes SET avisou=TRUE WHERE id=$1", s["id"])
                try:
                    await canal.send(
                        content=f"<@{s['user_id']}>",
                        embed=aviso(f"⏳ Você ainda está aí? O formulário será cancelado <t:{s['atividade_ts'] + limite}:R> se não houver resposta."),
                        allowed_mentions=discord.AllowedMentions(users=True),
                    )
                except discord.HTTPException:
                    pass

        # canais que ficaram para trás (bot reiniciou antes de apagar)
        for s in await self.pool.fetch(
            "SELECT id, channel_id FROM form_sessoes WHERE status<>'andamento' AND apagado=FALSE "
            "AND channel_id IS NOT NULL AND fim_ts < $1", agora - 60,
        ):
            self._tarefa(self._apagar_canal(s["channel_id"], 0, s["id"]))

        # abriu/fechou por data ou vagas → atualiza os painéis
        for chave in FORMULARIOS:
            estado = await self.estado_form(chave)
            if self.ultimo_status.get(chave) != estado["codigo"]:
                await self._atualizar_paineis(chave)

    @manutencao.before_loop
    async def _antes_manutencao(self):
        await self.bot.wait_until_ready()

    @manutencao.error
    async def _erro_manutencao(self, error):
        log.error("Erro na manutenção dos formulários: %s", error)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        sid = self.canais.pop(channel.id, None)
        if sid is not None and self.pool is not None:
            await self._encerrar_sessao(sid, "cancelado")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if self.pool is None or not self.pronto:
            return
        for s in await self.pool.fetch(
            "SELECT id, channel_id FROM form_sessoes WHERE user_id=$1 AND status='andamento'", member.id
        ):
            await self._encerrar_sessao(s["id"], "cancelado")
            self._tarefa(self._apagar_canal(s["channel_id"], 1, s["id"]))

    # ── Erros de comando ────────────────────────────────────────
    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=6)
        elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send(f"⚠️ Uso incorreto. Veja `{ctx.clean_prefix}formajuda`.", delete_after=8)
        else:
            raise error

    def _chave_valida(self, chave: str) -> bool:
        return chave in FORMULARIOS

    # ── Comandos (staff) ────────────────────────────────────────
    @commands.command(name="painelformulario")
    @apenas_staff()
    async def painelformulario(self, ctx: commands.Context, chave: str):
        """Envia o painel de um formulário neste canal."""
        if not self.pronto:
            return await ctx.send("❌ Sistema ainda iniciando (ou sem PostgreSQL).", delete_after=8)
        if not self._chave_valida(chave):
            return await ctx.send(f"❌ Formulário `{chave}` não existe. Disponíveis: {', '.join(f'`{k}`' for k in FORMULARIOS)}", delete_after=10)
        erros = [e for e in validar_config({chave: FORMULARIOS[chave]})]
        if erros:
            return await ctx.send("⚠️ Corrija a configuração antes:\n" + "\n".join(f"• {e}" for e in erros), delete_after=20)
        estado = await self.estado_form(chave)
        msg = await ctx.send(embed=await self.embed_painel(chave), view=view_painel(chave, estado["codigo"] == "aberto"))
        await self.pool.execute(
            "INSERT INTO form_paineis (guild_id, channel_id, message_id, form_key) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            ctx.guild.id, ctx.channel.id, msg.id, chave,
        )
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    async def _alternar(self, ctx, chave: str, aberto: bool):
        if not self._chave_valida(chave):
            return await ctx.send("❌ Formulário não encontrado.", delete_after=8)
        self.manual[chave] = aberto
        await self.pool.execute(
            "INSERT INTO form_estado (form_key, aberto) VALUES ($1,$2) ON CONFLICT (form_key) DO UPDATE SET aberto=EXCLUDED.aberto",
            chave, aberto,
        )
        await self._atualizar_paineis(chave)
        await ctx.send(f"{'🟢 Formulário aberto' if aberto else '⏸️ Formulário pausado'}: **{FORMULARIOS[chave]['nome']}**.", delete_after=10)

    @commands.command(name="formabrir")
    @apenas_staff()
    async def formabrir(self, ctx: commands.Context, chave: str):
        """Reabre um formulário pausado."""
        await self._alternar(ctx, chave, True)

    @commands.command(name="formpausar")
    @apenas_staff()
    async def formpausar(self, ctx: commands.Context, chave: str):
        """Pausa um formulário (ninguém novo consegue iniciar)."""
        await self._alternar(ctx, chave, False)

    @commands.command(name="formstatus")
    @apenas_staff()
    async def formstatus(self, ctx: commands.Context, chave: str = None):
        """Resumo dos formulários."""
        chaves = [chave] if chave else list(FORMULARIOS)
        embed = embed_base("# 📊 **Status dos formulários**")
        for k in chaves:
            if k not in FORMULARIOS:
                return await ctx.send("❌ Formulário não encontrado.", delete_after=8)
            estado = await self.estado_form(k)
            cont = {
                r["status"]: r["n"]
                for r in await self.pool.fetch("SELECT status, COUNT(*) AS n FROM form_envios WHERE form_key=$1 GROUP BY status", k)
            }
            andamento = await self.pool.fetchval("SELECT COUNT(*) FROM form_sessoes WHERE form_key=$1 AND status='andamento'", k)
            embed.add_field(
                name=f"{FORMULARIOS[k]['emoji']} {FORMULARIOS[k]['nome']} (`{k}`)",
                value=(
                    f"{estado['texto']}\n"
                    f"> `📥` Enviados: **{estado['enviados']}**"
                    + (f" / {FORMULARIOS[k]['max_respostas']}" if FORMULARIOS[k].get("max_respostas") else "")
                    + f"\n> `⏳` Pendentes: **{cont.get('pendente', 0)}** • `✅` Aprovados: **{cont.get('aprovado', 0)}** • `❌` Recusados: **{cont.get('recusado', 0)}**\n"
                    f"> `✍️` Em andamento agora: **{andamento}**\n"
                    + (f"> `📅` Encerra: <t:{estado['encerra_ts']}:R>" if estado["encerra_ts"] else "> `📅` Sem prazo")
                ),
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="formexportar")
    @apenas_staff()
    async def formexportar(self, ctx: commands.Context, chave: str):
        """Exporta todas as respostas de um formulário em CSV."""
        if not self._chave_valida(chave):
            return await ctx.send("❌ Formulário não encontrado.", delete_after=8)
        form = FORMULARIOS[chave]
        linhas = await self.pool.fetch("SELECT * FROM form_envios WHERE form_key=$1 ORDER BY id", chave)
        if not linhas:
            return await ctx.send("📭 Ainda não há respostas.", delete_after=8)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["protocolo", "usuario_id", "status", "enviado_em", "decidido_por", "motivo"] + [q["id"] for q in form["perguntas"]])
        for r in linhas:
            resp = json.loads(r["respostas"]) if isinstance(r["respostas"], str) else dict(r["respostas"])
            w.writerow(
                [protocolo_de(r["id"], r["enviado_ts"]), r["user_id"], r["status"],
                 datetime.fromtimestamp(r["enviado_ts"], FUSO).strftime("%d/%m/%Y %H:%M"),
                 r["decidido_por"] or "", r["motivo"] or ""]
                + [texto_resposta(q, resp.get(q["id"])).replace("\n", " | ") if q["id"] in resp else "" for q in form["perguntas"]]
            )
        dados = ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM: o Excel abre com acentos certos
        await ctx.send(f"📤 {len(linhas)} resposta(s):", file=discord.File(io.BytesIO(dados), filename=f"{chave}_respostas.csv"))

    @commands.command(name="formajuda")
    @apenas_staff()
    async def formajuda(self, ctx: commands.Context):
        """Lista os comandos de formulários."""
        p = ctx.clean_prefix
        await ctx.send(embed=embed_base(
            "# 📖 **Comandos de formulários**\n"
            f"`{p}painelformulario <chave>` — envia o painel neste canal\n"
            f"`{p}formstatus [chave]` — resumo de envios e situação\n"
            f"`{p}formpausar <chave>` / `{p}formabrir <chave>` — pausa ou reabre\n"
            f"`{p}formexportar <chave>` — baixa as respostas em CSV\n\n"
            f"**Formulários disponíveis:** {', '.join(f'`{k}`' for k in FORMULARIOS)}"
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(Formularios(bot))