from __future__ import annotations

import asyncio
import inspect
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import discord
from discord.ext import commands

try:
    from utils.cassino_db import (
        adicionar_moedas as _ext_adicionar,
        obter_saldo as _ext_saldo,
        remover_moedas as _ext_remover,
    )

    TEM_ECONOMIA_EXTERNA = True
except Exception:  # noqa: BLE001
    TEM_ECONOMIA_EXTERNA = False

log = logging.getLogger("leilao")

NOME_SERVIDOR = "Família Sant's"
NOME_LEILAO = "Leilão Cartoon • Família Sant's"

MOEDA_NOME = "Moedas"
MOEDA_EMOJI = "🪙"

# Mesma identidade dos tickets e das notificações
COR_AZUL = 0x211A1A  # Preto de tinta, inspirado no visual vintage de Cuphead
COR_AZUL_CLARO = 0xD94A38  # Vermelho cartunesco

# Link direto do banner (https://...). "" = sem banner.
BANNER_LEILAO = ""  # Opcional: link direto para um banner vintage inspirado em Cuphead

# Canal onde os leilões são publicados. 0 = o canal em que o painel foi enviado.
CANAL_LEILAO_ID = 0

# Canal (só da staff) que recebe o registro de leilões criados/encerrados. 0 = desligado.
CANAL_LOGS_ID = 1559312469959119039

# Quem pode ENVIAR o painel (!painelleilao) e gerenciar leilões
# (Administrador também pode). ADICIONE aqui os IDs dos cargos que quiser.
CARGOS_PAINEL = [
    1559771638025691178, #Leilão Organizador
    
]
CARGOS_CRIAR_LEILAO: list[int] = []

DURACAO_PADRAO = "10m"            # sugestão no formulário
DURACAO_MIN_SEG = 60              # 1 minuto
DURACAO_MAX_SEG = 7 * 24 * 3600   # 7 dias
INCREMENTO_PADRAO = 1             # aumento mínimo entre lances
VALOR_MAXIMO = 10**12

ANTI_SNIPER_SEGUNDOS = 30         # lance nos últimos X segundos...
EXTENSAO_ANTI_SNIPER = 60         # ...prorroga em X segundos
MAXIMO_EXTENSOES = 5
LEMBRETE_SEGUNDOS = 300           # quem clicou em "Lembrar" é avisado por DM
MAX_LEILOES_ATIVOS = 10

# True = ignora o utils.cassino_db e usa sempre a carteira própria do cog.
FORCAR_ECONOMIA_PROPRIA = False

# ── Texto do painel (EDITE AQUI e rode !painelleilao de novo) ──────────────────
PAINEL_DESCRICAO = """\\
# 🎪 **Grande Leilão Cartoon**
🎩 Entre no espetáculo da Família Sant's! Dê seus lances e tente levar o prêmio para casa.

**Como participar**
> `🪙` Aposte suas moedas no item desejado.
> `🎭` Se alguém cobrir seu lance, suas moedas voltam automaticamente.
> `⏱️` Lances no último instante podem estender o espetáculo.

**No balcão de ofertas**
> `🎟️` **Leilões Ativos** — Veja os itens em disputa.
> `💰` **Meu Saldo** — Confira sua carteira.
> `📜` **Como Funciona** — Consulte as regras.
> `🎩` **Criar Leilão** — Acesso exclusivo à equipe autorizada.

**Atenção, parceiro!**
> `⚠️` Todo lance é cobrado na hora. Pense bem antes de apostar!
"""

COMO_FUNCIONA = f"""\\
# 🎭 **Regras do Espetáculo**

**Apostas**
> `🪙` Ao apostar, o valor sai do seu saldo imediatamente.
> `↩️` Se outro membro cobrir seu lance, suas moedas são devolvidas automaticamente.
> `📬` Você recebe uma mensagem privada quando seu lance for superado.

**O relógio está correndo!**
> `⏱️` Lances nos últimos **{ANTI_SNIPER_SEGUNDOS}s** prorrogam o prazo em **{EXTENSAO_ANTI_SNIPER}s** (até {MAXIMO_EXTENSOES} vezes).
> `🔔` Use **Lembrar** para receber um aviso quando o encerramento estiver próximo.

**Quem leva o prêmio?**
> `🏆` Quando o tempo acabar, vence o maior lance.
> `⚡` Alguns itens têm **arremate imediato**: atingiu o valor, o leilão termina.
> `🎁` Cargos anunciados como prêmio são entregues automaticamente, quando configurados.

🎩 Boa sorte — e que comece o espetáculo!
"""

# ════════════════════════════════════════════════════════════════
#                            BANCO DE DADOS
# ════════════════════════════════════════════════════════════════

SQL_TABELAS = """
CREATE TABLE IF NOT EXISTS leiloes (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    autor_id BIGINT NOT NULL,
    item TEXT NOT NULL,
    descricao TEXT NOT NULL,
    imagem TEXT,
    lance_minimo BIGINT NOT NULL,
    incremento BIGINT NOT NULL DEFAULT 1,
    arremate BIGINT,
    cargo_premio_id BIGINT,
    lance_atual BIGINT NOT NULL DEFAULT 0,
    vencedor_id BIGINT,
    fim_ts BIGINT NOT NULL,
    extensoes INTEGER NOT NULL DEFAULT 0,
    lembrou BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'ativo',
    criado_ts BIGINT NOT NULL,
    encerrado_ts BIGINT
);
CREATE INDEX IF NOT EXISTS idx_leiloes_status ON leiloes (guild_id, status);

CREATE TABLE IF NOT EXISTS leilao_lances (
    id BIGSERIAL PRIMARY KEY,
    leilao_id BIGINT NOT NULL REFERENCES leiloes(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    nome TEXT NOT NULL,
    valor BIGINT NOT NULL,
    ts BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leilao_lances ON leilao_lances (leilao_id, id);

CREATE TABLE IF NOT EXISTS leilao_lembretes (
    leilao_id BIGINT NOT NULL REFERENCES leiloes(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    PRIMARY KEY (leilao_id, user_id)
);

CREATE TABLE IF NOT EXISTS leilao_carteiras (
    user_id BIGINT PRIMARY KEY,
    saldo BIGINT NOT NULL DEFAULT 0 CHECK (saldo >= 0)
);
"""


# ════════════════════════════════════════════════════════════════
#                              ECONOMIA
# ════════════════════════════════════════════════════════════════


async def _chamar(fn, *args):
    resultado = fn(*args)
    if inspect.isawaitable(resultado):
        resultado = await resultado
    return resultado


class EconomiaPropria:
    """Carteira no PostgreSQL. Débitos e créditos são atômicos."""

    nome = "carteira própria (PostgreSQL)"
    externa = False

    def __init__(self, pool):
        self.pool = pool

    async def saldo(self, uid: int, conn=None) -> int:
        valor = await (conn or self.pool).fetchval(
            "SELECT saldo FROM leilao_carteiras WHERE user_id=$1", uid
        )
        return int(valor or 0)

    async def debitar(self, uid: int, valor: int, conn=None) -> bool:
        linha = await (conn or self.pool).fetchrow(
            "UPDATE leilao_carteiras SET saldo = saldo - $2 "
            "WHERE user_id=$1 AND saldo >= $2 RETURNING saldo",
            uid, valor,
        )
        return linha is not None

    async def creditar(self, uid: int, valor: int, conn=None) -> None:
        await (conn or self.pool).execute(
            "INSERT INTO leilao_carteiras (user_id, saldo) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE "
            "SET saldo = leilao_carteiras.saldo + EXCLUDED.saldo",
            uid, valor,
        )


class EconomiaExterna:
    """Usa as funções do utils.cassino_db (economia do cassino)."""

    nome = "economia do cassino (utils.cassino_db)"
    externa = True

    async def saldo(self, uid: int, conn=None) -> int:
        return int(await _chamar(_ext_saldo, uid) or 0)

    async def debitar(self, uid: int, valor: int, conn=None) -> bool:
        if await self.saldo(uid) < valor:
            return False
        await _chamar(_ext_remover, uid, valor)
        return True

    async def creditar(self, uid: int, valor: int, conn=None) -> None:
        await _chamar(_ext_adicionar, uid, valor)


class _SaldoInsuficiente(Exception):
    pass


# ════════════════════════════════════════════════════════════════
#                              AUXILIARES
# ════════════════════════════════════════════════════════════════


def formatar_moedas(valor: int) -> str:
    return f"{MOEDA_EMOJI} `{valor:,}`".replace(",", ".")


def formatar_duracao_seg(seg: int) -> str:
    d, resto = divmod(int(seg), 86400)
    h, resto = divmod(resto, 3600)
    m, _ = divmod(resto, 60)
    partes = []
    if d:
        partes.append(f"{d}d")
    if h:
        partes.append(f"{h}h")
    if m or not partes:
        partes.append(f"{m}min")
    return " ".join(partes)


def parsear_valor(raw: str | None) -> int | None:
    """Aceita 5000, 5.000, 5k, 1,5k, 2m."""
    if not raw:
        return None
    t = raw.strip().lower().replace(" ", "")
    mult = 1
    if t.endswith("k"):
        mult, t = 1_000, t[:-1]
    elif t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    try:
        if mult > 1:
            v = int(round(float(t.replace(",", ".")) * mult))
        else:
            v = int(t.replace(".", "").replace(",", ""))
    except ValueError:
        return None
    return v if 0 < v <= VALOR_MAXIMO else None


def parsear_duracao(raw: str | None) -> int | None:
    """Aceita 10m, 45, 2h, 1h30m, 1d. Número sozinho = minutos."""
    if not raw:
        return None
    t = raw.strip().lower().replace(" ", "")
    t = re.sub(r"min(utos?)?", "m", t)
    t = re.sub(r"(horas?|hrs?)", "h", t)
    t = re.sub(r"dias?", "d", t)
    if not re.fullmatch(r"(\d+[dhm]?)+", t):
        return None
    unidade = {"d": 86400, "h": 3600, "m": 60, "": 60}
    total = sum(int(n) * unidade[u] for n, u in re.findall(r"(\d+)([dhm]?)", t))
    if total < DURACAO_MIN_SEG or total > DURACAO_MAX_SEG:
        return None
    return total


def eh_gestor(membro) -> bool:
    """Administrador ou algum cargo de CARGOS_PAINEL."""
    if not isinstance(membro, discord.Member):
        return False
    if membro.guild_permissions.administrator:
        return True
    return any(r.id in CARGOS_PAINEL for r in membro.roles)


def pode_criar_leilao(membro) -> bool:
    if eh_gestor(membro):
        return True
    return isinstance(membro, discord.Member) and any(
        r.id in CARGOS_CRIAR_LEILAO for r in membro.roles
    )


def apenas_gestor():
    async def predicate(ctx: commands.Context):
        if ctx.guild is not None and eh_gestor(ctx.author):
            return True
        raise commands.CheckFailure("sem_permissao")

    return commands.check(predicate)


def embed_base(
    titulo: str | None,
    descricao: str | None = None,
    cor: int = COR_AZUL,
    banner: bool = False,
) -> discord.Embed:
    e = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor,
        timestamp=datetime.now(timezone.utc),
    )
    e.set_footer(text=f"{NOME_SERVIDOR} • {NOME_LEILAO}")
    if banner and BANNER_LEILAO.lower().startswith("http"):
        e.set_image(url=BANNER_LEILAO)
    return e


# ════════════════════════════════════════════════════════════════
#                              MODELOS
# ════════════════════════════════════════════════════════════════


@dataclass
class LeilaoEstado:
    id: int
    guild_id: int
    channel_id: int
    autor_id: int
    item: str
    descricao: str
    lance_minimo: int
    fim_ts: int
    message_id: int | None = None
    imagem: str | None = None
    incremento: int = 1
    arremate: int | None = None
    cargo_premio_id: int | None = None
    lance_atual: int = 0
    vencedor_id: int | None = None
    extensoes: int = 0
    lembrou: bool = False
    status: str = "ativo"
    total_lances: int = 0
    historico: list = field(default_factory=list)  # (nome, valor, ts)
    cancelado_por: int | None = None
    motivo_cancelamento: str = ""
    premio_nota: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def valor_exibido(self) -> int:
        return self.lance_atual if self.lance_atual > 0 else self.lance_minimo

    @property
    def minimo_proximo(self) -> int:
        if self.lance_atual == 0:
            return self.lance_minimo
        return self.lance_atual + self.incremento

    def restante(self) -> int:
        return max(0, self.fim_ts - int(time.time()))

    def vivo(self) -> bool:
        return self.status == "ativo" and self.restante() > 0

    @property
    def link(self) -> str:
        return f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"


@dataclass
class Rascunho:
    autor_id: int
    item: str
    descricao: str
    lance_minimo: int
    duracao_seg: int
    incremento: int
    arremate: int | None = None
    cargo_premio_id: int | None = None
    imagem: str | None = None


# ════════════════════════════════════════════════════════════════
#                              EMBEDS
# ════════════════════════════════════════════════════════════════


def embed_leilao(l: LeilaoEstado) -> discord.Embed:
    lider = f"<@{l.vencedor_id}>" if l.vencedor_id else "*ninguém ainda*"
    inicial = " *(inicial)*" if l.lance_atual == 0 else ""

    situacao = [
        f"> `💰` **Lance atual:** {formatar_moedas(l.valor_exibido)}{inicial}",
        f"> `👑` **Líder:** {lider}",
        f"> `🔼` **Próximo mínimo:** {formatar_moedas(l.minimo_proximo)}",
        f"> `⏳` **Encerra:** <t:{l.fim_ts}:R> • <t:{l.fim_ts}:T>",
    ]
    if l.arremate:
        situacao.append(f"> `⚡` **Arremate imediato:** {formatar_moedas(l.arremate)}")
    if l.cargo_premio_id:
        situacao.append(f"> `🎁` **Prêmio:** <@&{l.cargo_premio_id}> (entregue automaticamente)")
    if l.extensoes:
        situacao.append(f"> `🔁` **Prorrogado:** {l.extensoes}× (anti-sniper)")

    ultimos = list(reversed(l.historico[-5:]))
    if ultimos:
        linhas_lances = "\n".join(
            f"> `#{l.total_lances - i:02d}` **{nome}** — {formatar_moedas(valor)} • <t:{ts}:R>"
            for i, (nome, valor, ts) in enumerate(ultimos)
        )
    else:
        linhas_lances = "> *Nenhum lance ainda. Seja o primeiro!*"

    descricao = (
        f"# 🎪 **{l.item}**\n"
        f"{l.descricao}\n\n"
        "**Situação**\n" + "\n".join(situacao) + "\n\n"
        f"**Últimos lances** ({l.total_lances} no total)\n{linhas_lances}\n\n"
        "**Regras**\n"
        "> `💳` Lance cobrado na hora.\n"
        "> `↩️` Superado? Suas moedas voltam automaticamente.\n"
        f"> `⚡` Lances nos últimos {ANTI_SNIPER_SEGUNDOS}s prorrogam o tempo."
    )
    e = embed_base(None, descricao[:4096], banner=True)
    e.set_footer(text=f"{NOME_SERVIDOR} • {NOME_LEILAO} • #{l.id}")
    if l.imagem:
        e.set_thumbnail(url=l.imagem)
    return e


def embed_final(l: LeilaoEstado) -> discord.Embed:
    if l.status == "cancelado":
        linhas = [f"> `👤` Cancelado por <@{l.cancelado_por}>"]
        if l.motivo_cancelamento:
            linhas.append(f"> `💬` {l.motivo_cancelamento}")
        if l.vencedor_id and l.lance_atual:
            linhas.append(f"> `↩️` Lance de <@{l.vencedor_id}> devolvido: {formatar_moedas(l.lance_atual)}")
        descricao = f"# 🎭 **Espetáculo cancelado**\n**{l.item}**\n\n" + "\n".join(linhas)
        cor = COR_AZUL
    elif l.vencedor_id:
        linhas = [
            f"> `👑` **Vencedor:** <@{l.vencedor_id}>",
            f"> `💰` **Lance final:** {formatar_moedas(l.lance_atual)}",
            f"> `🔢` **Total de lances:** {l.total_lances}",
        ]
        if l.premio_nota:
            linhas.append(f"> `🎁` {l.premio_nota}")
        descricao = (
            f"# 🏆 **Espetáculo encerrado!**\n**{l.item}**\n\n"
            "**Resultado**\n" + "\n".join(linhas)
        )
        cor = COR_AZUL_CLARO
    else:
        descricao = (
            f"# 📭 **Cortinas fechadas — sem apostas**\n**{l.item}**\n\n"
            "> `📭` Ninguém deu lance neste item."
        )
        cor = COR_AZUL
    e = embed_base(None, descricao, cor=cor, banner=True)
    e.set_footer(text=f"{NOME_SERVIDOR} • {NOME_LEILAO} • #{l.id}")
    if l.imagem:
        e.set_thumbnail(url=l.imagem)
    return e


def embed_rascunho(r: Rascunho) -> discord.Embed:
    linhas = [
        f"> `📦` **Item:** {r.item}",
        f"> `💰` **Lance inicial:** {formatar_moedas(r.lance_minimo)}",
        f"> `🔼` **Incremento mínimo:** {formatar_moedas(r.incremento)}",
        f"> `⏳` **Duração:** {formatar_duracao_seg(r.duracao_seg)}",
        f"> `⚡` **Arremate imediato:** {formatar_moedas(r.arremate) if r.arremate else '—'}",
        f"> `🎁` **Cargo de prêmio:** {f'<@&{r.cargo_premio_id}>' if r.cargo_premio_id else '—'}",
        f"> `🖼️` **Imagem:** {'sim' if r.imagem else 'não'}",
    ]
    descricao = (
        "# 🎩 **Conferir o espetáculo**\nRevise os detalhes antes de colocar o prêmio em cena.\n\n"
        + "\n".join(linhas)
        + f"\n\n**Descrição**\n> {r.descricao}"
    )
    return embed_base(None, descricao[:4096])


# ════════════════════════════════════════════════════════════════
#                  BOTÕES DO LEILÃO (persistentes, dinâmicos)
# ════════════════════════════════════════════════════════════════

# ação: (rótulo, emoji, estilo, linha)
ACOES = {
    "lance": ("Fazer Aposta", "🪙", discord.ButtonStyle.primary, 0),
    "min": ("Aposta Mínima", "🎟️", discord.ButtonStyle.secondary, 0),
    "p10": ("+10%", "📈", discord.ButtonStyle.secondary, 0),
    "p25": ("+25%", "🚀", discord.ButtonStyle.secondary, 0),
    "arremate": ("Arrematar", "⚡", discord.ButtonStyle.success, 0),
    "hist": ("Livro de Apostas", "📜", discord.ButtonStyle.secondary, 1),
    "saldo": ("Minha Carteira", "💰", discord.ButtonStyle.secondary, 1),
    "lembrar": ("Lembrar", "🔔", discord.ButtonStyle.secondary, 1),
    "cancelar": ("Cancelar", "🛑", discord.ButtonStyle.danger, 1),
}


class BotaoLeilao(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"leilao:(?P<acao>[a-z0-9]+):(?P<id>\d+)",
):
    """O ID do leilão fica no custom_id: vários leilões ao mesmo tempo funcionam
    e os botões continuam vivos depois de o bot reiniciar."""

    def __init__(self, acao: str, leilao_id: int):
        rotulo, emoji, estilo, linha = ACOES[acao]
        super().__init__(
            discord.ui.Button(
                label=rotulo,
                emoji=emoji,
                style=estilo,
                row=linha,
                custom_id=f"leilao:{acao}:{leilao_id}",
            )
        )
        self.acao = acao
        self.leilao_id = leilao_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        acao = match["acao"]
        if acao not in ACOES:
            raise ValueError(f"ação desconhecida: {acao}")
        return cls(acao, int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("Leilao")
        if cog is None:
            return await interaction.response.send_message(
                "❌ Sistema de leilões indisponível.", ephemeral=True
            )
        await cog.tratar_botao(interaction, self.acao, self.leilao_id)


def montar_view(l: LeilaoEstado) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for acao in ("lance", "min", "p10", "p25"):
        view.add_item(BotaoLeilao(acao, l.id))
    if l.arremate:
        view.add_item(BotaoLeilao("arremate", l.id))
    for acao in ("hist", "saldo", "lembrar", "cancelar"):
        view.add_item(BotaoLeilao(acao, l.id))
    return view


# ════════════════════════════════════════════════════════════════
#                              MODAIS
# ════════════════════════════════════════════════════════════════


class CriarLeilaoModal(discord.ui.Modal, title="🎩 Novo Leilão Cartoon"):
    item = discord.ui.TextInput(
        label="Prêmio em disputa",
        placeholder="Ex: Cargo VIP, Nitro, Gamepass…",
        max_length=80,
    )
    descricao = discord.ui.TextInput(
        label="Descrição do item",
        placeholder="Explique o que será entregue ao vencedor.",
        style=discord.TextStyle.paragraph,
        max_length=700,
    )
    lance_inicial = discord.ui.TextInput(
        label="Lance inicial",
        placeholder="Ex: 1000 ou 1k",
        max_length=14,
    )
    duracao = discord.ui.TextInput(
        label="Duração",
        placeholder="Ex: 10m, 2h, 1h30m, 1d",
        default=DURACAO_PADRAO,
        max_length=12,
    )
    incremento = discord.ui.TextInput(
        label="Aumento mínimo entre lances (opcional)",
        placeholder=f"Padrão: {INCREMENTO_PADRAO}",
        required=False,
        max_length=14,
    )

    def __init__(self, cog: "Leilao"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        valor = parsear_valor(self.lance_inicial.value)
        if valor is None:
            return await interaction.response.send_message(
                "❌ Lance inicial inválido. Use números maiores que zero (ex.: 1000 ou 1k).",
                ephemeral=True,
            )
        duracao = parsear_duracao(self.duracao.value)
        if duracao is None:
            return await interaction.response.send_message(
                "❌ Duração inválida. Use algo como `10m`, `2h`, `1h30m` ou `1d` "
                f"(de {formatar_duracao_seg(DURACAO_MIN_SEG)} a {formatar_duracao_seg(DURACAO_MAX_SEG)}).",
                ephemeral=True,
            )
        incremento = INCREMENTO_PADRAO
        if self.incremento.value.strip():
            incremento = parsear_valor(self.incremento.value)
            if incremento is None:
                return await interaction.response.send_message(
                    "❌ Aumento mínimo inválido. Use um número maior que zero.",
                    ephemeral=True,
                )

        rascunho = Rascunho(
            autor_id=interaction.user.id,
            item=self.item.value.strip(),
            descricao=self.descricao.value.strip(),
            lance_minimo=valor,
            duracao_seg=duracao,
            incremento=incremento,
        )
        self.cog.rascunhos[interaction.user.id] = rascunho
        await interaction.response.send_message(
            embed=embed_rascunho(rascunho),
            view=RascunhoView(self.cog, interaction.user.id),
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("Erro em CriarLeilaoModal", exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "⚠️ Ocorreu um erro inesperado ao criar o leilão.", ephemeral=True
            )


class ExtrasModal(discord.ui.Modal, title="⚙️ Opções extras"):
    def __init__(self, cog: "Leilao", rascunho: Rascunho):
        super().__init__()
        self.cog = cog
        self.rascunho = rascunho
        self.arremate = discord.ui.TextInput(
            label="Arremate imediato (opcional)",
            placeholder="Valor que encerra o leilão na hora",
            required=False,
            max_length=14,
            default=str(rascunho.arremate) if rascunho.arremate else None,
        )
        self.cargo = discord.ui.TextInput(
            label="Cargo de prêmio (opcional)",
            placeholder="ID ou menção do cargo entregue ao vencedor",
            required=False,
            max_length=40,
            default=str(rascunho.cargo_premio_id) if rascunho.cargo_premio_id else None,
        )
        self.imagem = discord.ui.TextInput(
            label="Imagem do item (opcional)",
            placeholder="Link direto (https://...)",
            required=False,
            max_length=300,
            default=rascunho.imagem,
        )
        for campo in (self.arremate, self.cargo, self.imagem):
            self.add_item(campo)

    async def on_submit(self, interaction: discord.Interaction):
        r = self.rascunho

        arremate = None
        if self.arremate.value.strip():
            arremate = parsear_valor(self.arremate.value)
            if arremate is None or arremate <= r.lance_minimo:
                return await interaction.response.send_message(
                    "❌ O arremate imediato precisa ser um número maior que o lance inicial.",
                    ephemeral=True,
                )

        cargo_id = None
        if self.cargo.value.strip():
            achado = re.search(r"\d{15,20}", self.cargo.value)
            cargo = interaction.guild.get_role(int(achado.group())) if achado else None
            if cargo is None:
                return await interaction.response.send_message(
                    "❌ Cargo não encontrado. Informe o ID ou mencione o cargo.",
                    ephemeral=True,
                )
            if cargo >= interaction.guild.me.top_role:
                return await interaction.response.send_message(
                    f"❌ O cargo {cargo.mention} está acima do cargo do bot — "
                    "o bot não conseguiria entregá-lo.",
                    ephemeral=True,
                )
            cargo_id = cargo.id

        imagem = self.imagem.value.strip() or None
        if imagem and not imagem.lower().startswith("http"):
            return await interaction.response.send_message(
                "❌ A imagem precisa ser um link que comece com https://",
                ephemeral=True,
            )

        r.arremate = arremate
        r.cargo_premio_id = cargo_id
        r.imagem = imagem
        await interaction.response.edit_message(
            embed=embed_rascunho(r), view=RascunhoView(self.cog, r.autor_id)
        )


class LanceModal(discord.ui.Modal, title="🪙 Fazer Aposta"):
    def __init__(self, cog: "Leilao", l: LeilaoEstado):
        super().__init__()
        self.cog = cog
        self.leilao_id = l.id
        self.valor = discord.ui.TextInput(
            label="Valor da aposta",
            placeholder=f"Mínimo: {l.minimo_proximo:,}".replace(",", ".")[:100],
            max_length=14,
        )
        self.add_item(self.valor)

    async def on_submit(self, interaction: discord.Interaction):
        valor = parsear_valor(self.valor.value)
        if valor is None:
            return await interaction.response.send_message(
                "❌ Valor inválido. Use números (ex.: 5000 ou 5k).", ephemeral=True
            )
        await self.cog.processar_lance(interaction, self.leilao_id, valor)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        log.exception("Erro em LanceModal", exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "⚠️ Erro ao processar seu lance.", ephemeral=True
            )


class CancelarModal(discord.ui.Modal, title="🎭 Retirar do Espetáculo"):
    motivo = discord.ui.TextInput(
        label="Motivo (opcional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=300,
    )

    def __init__(self, cog: "Leilao", leilao_id: int):
        super().__init__()
        self.cog = cog
        self.leilao_id = leilao_id

    async def on_submit(self, interaction: discord.Interaction):
        l = self.cog.ativos.get(self.leilao_id)
        if l is None or l.status != "ativo":
            return await interaction.response.send_message(
                "❌ Este leilão já foi encerrado.", ephemeral=True
            )
        if not (eh_gestor(interaction.user) or interaction.user.id == l.autor_id):
            return await interaction.response.send_message(
                "❌ Apenas a gestão ou quem criou o leilão pode cancelar.", ephemeral=True
            )
        await interaction.response.send_message("🛑 Cancelando o leilão...", ephemeral=True)
        l.cancelado_por = interaction.user.id
        l.motivo_cancelamento = str(self.motivo).strip()
        await self.cog.finalizar(self.leilao_id, cancelado=True)


# ════════════════════════════════════════════════════════════════
#                       RASCUNHO (PRÉVIA ANTES DE PUBLICAR)
# ════════════════════════════════════════════════════════════════


class RascunhoView(discord.ui.View):
    def __init__(self, cog: "Leilao", autor_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.autor_id = autor_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.autor_id:
            return True
        await interaction.response.send_message("❌ Este rascunho não é seu.", ephemeral=True)
        return False

    @discord.ui.button(label="Publicar", emoji="🚀", style=discord.ButtonStyle.success, row=0)
    async def publicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.cog.rascunhos.get(self.autor_id)
        if r is None:
            return await interaction.response.send_message(
                "⌛ Este rascunho expirou. Crie o leilão de novo.", ephemeral=True
            )
        await interaction.response.defer()
        resultado = await self.cog.publicar(interaction, r)
        if isinstance(resultado, str):
            return await interaction.followup.send(resultado, ephemeral=True)
        self.cog.rascunhos.pop(self.autor_id, None)
        await interaction.edit_original_response(
            content=f"✅ Leilão publicado: {resultado.link}", embed=None, view=None
        )

    @discord.ui.button(label="Opções extras", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
    async def extras(self, interaction: discord.Interaction, button: discord.ui.Button):
        r = self.cog.rascunhos.get(self.autor_id)
        if r is None:
            return await interaction.response.send_message(
                "⌛ Este rascunho expirou. Crie o leilão de novo.", ephemeral=True
            )
        await interaction.response.send_modal(ExtrasModal(self.cog, r))

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.danger, row=0)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.rascunhos.pop(self.autor_id, None)
        await interaction.response.edit_message(
            content="✖️ Rascunho descartado.", embed=None, view=None
        )


# ════════════════════════════════════════════════════════════════
#                       PAINEL (persistente)
# ════════════════════════════════════════════════════════════════


class PainelLeilaoView(discord.ui.View):
    def __init__(self, cog: "Leilao"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Leilões Ativos", emoji="🎟️", style=discord.ButtonStyle.primary, custom_id="leilao_painel:ativos", row=0)
    async def btn_ativos(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=self.cog.embed_ativos(interaction.guild_id), ephemeral=True
        )

    @discord.ui.button(label="Meu Saldo", emoji="💼", style=discord.ButtonStyle.secondary, custom_id="leilao_painel:saldo", row=0)
    async def btn_saldo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.pronto:
            return await interaction.response.send_message(
                "❌ Sistema de leilões indisponível no momento.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        saldo = await self.cog.economia.saldo(interaction.user.id)
        await interaction.followup.send(
            embed=embed_base(
                "💰 Sua carteira",
                f"{interaction.user.mention}, você tem {formatar_moedas(saldo)} {MOEDA_NOME.lower()}.",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Regras do Jogo", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="leilao_painel:info", row=0)
    async def btn_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed_base(None, COMO_FUNCIONA, banner=True), ephemeral=True
        )

    @discord.ui.button(label="Abrir Leilão", emoji="🎩", style=discord.ButtonStyle.success, custom_id="leilao_painel:criar", row=0)
    async def btn_criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not pode_criar_leilao(interaction.user):
            return await interaction.response.send_message(
                "❌ Apenas a equipe autorizada pode criar leilões.", ephemeral=True
            )
        if not self.cog.pronto:
            return await interaction.response.send_message(
                "❌ Sistema de leilões indisponível no momento.", ephemeral=True
            )
        await interaction.response.send_modal(CriarLeilaoModal(self.cog))


# ════════════════════════════════════════════════════════════════
#                                COG
# ════════════════════════════════════════════════════════════════


class Leilao(commands.Cog, name="Leilao"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ativos: dict[int, LeilaoEstado] = {}
        self.tarefas: dict[int, asyncio.Task] = {}
        self.rascunhos: dict[int, Rascunho] = {}
        self.edicoes: set[int] = set()
        self.aux: set[asyncio.Task] = set()
        self.economia = None
        self.pronto = False

    @property
    def pool(self):
        return getattr(self.bot, "pool", None)

    # ── Ciclo de vida do cog ────────────────────────────────────
    async def cog_load(self):
        self.bot.add_dynamic_items(BotaoLeilao)
        self.bot.add_view(PainelLeilaoView(self))
        self._tarefa_aux(self._iniciar())

    async def cog_unload(self):
        for t in list(self.tarefas.values()) + list(self.aux):
            t.cancel()

    def _tarefa_aux(self, coro):
        t = asyncio.create_task(coro)
        self.aux.add(t)
        t.add_done_callback(self.aux.discard)
        return t

    async def _iniciar(self):
        await self.bot.wait_until_ready()
        if self.pool is None:
            print("[leilao] ERRO: bot.pool não existe. Configure o PostgreSQL no main.py.")
            return
        try:
            await self.pool.execute(SQL_TABELAS)
            if TEM_ECONOMIA_EXTERNA and not FORCAR_ECONOMIA_PROPRIA:
                self.economia = EconomiaExterna()
            else:
                self.economia = EconomiaPropria(self.pool)
            print(f"[leilao] Economia: {self.economia.nome}")
            await self._restaurar()
            self.pronto = True
        except Exception as e:  # noqa: BLE001
            print(f"[leilao] ERRO ao iniciar: {type(e).__name__}: {e}")

    async def _restaurar(self):
        """Retoma os leilões que estavam ativos antes de o bot reiniciar."""
        linhas = await self.pool.fetch("SELECT * FROM leiloes WHERE status='ativo' ORDER BY id")
        for r in linhas:
            if r["id"] in self.ativos:
                continue
            lances = await self.pool.fetch(
                "SELECT nome, valor, ts FROM leilao_lances WHERE leilao_id=$1 "
                "ORDER BY id DESC LIMIT 50",
                r["id"],
            )
            total = await self.pool.fetchval(
                "SELECT COUNT(*) FROM leilao_lances WHERE leilao_id=$1", r["id"]
            )
            l = self._de_linha(r)
            l.historico = [(x["nome"], x["valor"], x["ts"]) for x in reversed(lances)]
            l.total_lances = int(total or 0)
            self.ativos[l.id] = l
            self._agendar(l)
        if linhas:
            print(f"[leilao] {len(linhas)} leilão(ões) retomado(s).")

    @staticmethod
    def _de_linha(r) -> "LeilaoEstado":
        return LeilaoEstado(
            id=r["id"],
            guild_id=r["guild_id"],
            channel_id=r["channel_id"],
            message_id=r["message_id"],
            autor_id=r["autor_id"],
            item=r["item"],
            descricao=r["descricao"],
            imagem=r["imagem"],
            lance_minimo=r["lance_minimo"],
            incremento=r["incremento"],
            arremate=r["arremate"],
            cargo_premio_id=r["cargo_premio_id"],
            lance_atual=r["lance_atual"],
            vencedor_id=r["vencedor_id"],
            fim_ts=r["fim_ts"],
            extensoes=r["extensoes"],
            lembrou=r["lembrou"],
            status=r["status"],
        )

    # ── Agendamento / encerramento ──────────────────────────────
    def _agendar(self, l: "LeilaoEstado"):
        self.tarefas[l.id] = asyncio.create_task(self._aguardar_fim(l.id))

    async def _aguardar_fim(self, lid: int):
        while True:
            try:
                l = self.ativos.get(lid)
                if l is None or l.status != "ativo":
                    return
                restante = l.fim_ts - time.time()
                if restante <= 0:
                    await self.finalizar(lid)
                    return
                if not l.lembrou and restante <= LEMBRETE_SEGUNDOS:
                    l.lembrou = True
                    await self.pool.execute("UPDATE leiloes SET lembrou=TRUE WHERE id=$1", lid)
                    await self._enviar_lembretes(l)
                    continue
                await asyncio.sleep(min(restante, 15))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - nunca deixar o leilão sem encerrar
                log.exception("Erro no ciclo do leilão %s", lid)
                await asyncio.sleep(10)

    async def finalizar(self, lid: int, cancelado: bool = False):
        l = self.ativos.get(lid)
        if l is None:
            return
        async with l.lock:
            if l.status != "ativo":
                return
            novo = "cancelado" if cancelado else "finalizado"
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if cancelado and l.vencedor_id and l.lance_atual:
                        await self.economia.creditar(l.vencedor_id, l.lance_atual, conn)
                    await conn.execute(
                        "UPDATE leiloes SET status=$2, encerrado_ts=$3 WHERE id=$1",
                        lid, novo, int(time.time()),
                    )
            l.status = novo

        self.ativos.pop(lid, None)
        tarefa = self.tarefas.pop(lid, None)
        if tarefa is not None and tarefa is not asyncio.current_task():
            tarefa.cancel()

        # Prêmio automático (cargo)
        if novo == "finalizado" and l.vencedor_id and l.cargo_premio_id:
            l.premio_nota = await self._entregar_cargo(l)
        elif novo == "finalizado" and l.vencedor_id:
            l.premio_nota = "Entre em contato com a administração para resgatar o prêmio."

        await self._editar_mensagem(l, embed=embed_final(l), view=None)
        await self.pool.execute("DELETE FROM leilao_lembretes WHERE leilao_id=$1", lid)

        if novo == "finalizado" and l.vencedor_id:
            await self._dm(
                l.vencedor_id,
                embed_base(
                    "🏆 Você levou o prêmio!",
                    f"**{l.item}**\n\n> `💰` Lance final: {formatar_moedas(l.lance_atual)}\n"
                    f"> `🎁` {l.premio_nota}\n\n[Ver leilão]({l.link})",
                ),
            )

        titulo = "🛑 Leilão cancelado" if novo == "cancelado" else "🏁 Leilão encerrado"
        resumo = f"**{l.item}** (#{l.id})\n"
        if l.vencedor_id and novo == "finalizado":
            resumo += f"Vencedor: <@{l.vencedor_id}> • {formatar_moedas(l.lance_atual)}\n"
        elif novo == "finalizado":
            resumo += "Sem lances.\n"
        else:
            resumo += f"Cancelado por <@{l.cancelado_por}>\n"
        await self._log(l.guild_id, titulo, resumo + l.link)

    async def _entregar_cargo(self, l: "LeilaoEstado") -> str:
        guild = self.bot.get_guild(l.guild_id)
        cargo = guild.get_role(l.cargo_premio_id) if guild else None
        membro = guild.get_member(l.vencedor_id) if guild else None
        if guild and membro is None:
            try:
                membro = await guild.fetch_member(l.vencedor_id)
            except discord.HTTPException:
                membro = None
        if cargo is None or membro is None:
            return "Não consegui entregar o cargo automaticamente — fale com a administração."
        try:
            await membro.add_roles(cargo, reason=f"Prêmio do leilão #{l.id}")
            return f"Cargo {cargo.mention} entregue automaticamente."
        except discord.HTTPException:
            return "Não consegui entregar o cargo automaticamente — fale com a administração."

    # ── Mensagens / DMs / logs ──────────────────────────────────
    async def _canal(self, canal_id: int):
        canal = self.bot.get_channel(canal_id)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(canal_id)
            except discord.HTTPException:
                return None
        return canal

    async def _editar_mensagem(self, l: "LeilaoEstado", **kwargs):
        if not l.message_id:
            return
        canal = await self._canal(l.channel_id)
        if canal is None:
            return
        try:
            await canal.get_partial_message(l.message_id).edit(**kwargs)
        except discord.HTTPException as exc:
            log.warning("Falha ao editar a mensagem do leilão %s: %s", l.id, exc)

    def _agendar_atualizacao(self, l: "LeilaoEstado"):
        """Agrupa várias edições seguidas em uma só (evita rate limit)."""
        if l.id in self.edicoes:
            return
        self.edicoes.add(l.id)
        self._tarefa_aux(self._atualizar_mensagem(l.id))

    async def _atualizar_mensagem(self, lid: int):
        try:
            await asyncio.sleep(1.0)
            self.edicoes.discard(lid)
            l = self.ativos.get(lid)
            if l is not None and l.status == "ativo":
                await self._editar_mensagem(l, embed=embed_leilao(l))
        finally:
            self.edicoes.discard(lid)

    async def _dm(self, user_id: int, embed: discord.Embed):
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _enviar_lembretes(self, l: "LeilaoEstado"):
        linhas = await self.pool.fetch(
            "SELECT user_id FROM leilao_lembretes WHERE leilao_id=$1", l.id
        )
        for r in linhas:
            await self._dm(
                r["user_id"],
                embed_base(
                    "⏳ Última chamada para apostar!",
                    f"**{l.item}** termina <t:{l.fim_ts}:R>.\n"
                    f"> `💰` Lance atual: {formatar_moedas(l.valor_exibido)}\n\n"
                    f"[Ir para o leilão]({l.link})",
                ),
            )
            await asyncio.sleep(0.3)

    async def _avisar_superado(self, l: "LeilaoEstado", user_id: int, novo_valor: int):
        await self._dm(
            user_id,
            embed_base(
                "↩️ Seu lance foi superado",
                f"Alguém deu **{formatar_moedas(novo_valor)}** em **{l.item}**.\n"
                f"As suas moedas já voltaram para o seu saldo.\n\n[Dar outro lance]({l.link})",
            ),
        )

    async def _log(self, guild_id: int, titulo: str, descricao: str):
        if not CANAL_LOGS_ID:
            return
        canal = await self._canal(CANAL_LOGS_ID)
        if canal is None:
            return
        try:
            await canal.send(embed=embed_base(titulo, descricao))
        except discord.HTTPException:
            pass

    # ── Publicação ──────────────────────────────────────────────
    async def publicar(self, interaction: discord.Interaction, r: Rascunho):
        """Cria o leilão no banco e publica a mensagem. Retorna Leilao ou texto de erro."""
        guild = interaction.guild
        ativos_guild = [x for x in self.ativos.values() if x.guild_id == guild.id]
        if len(ativos_guild) >= MAX_LEILOES_ATIVOS:
            return f"❌ Já existem {MAX_LEILOES_ATIVOS} leilões ativos. Aguarde algum terminar."

        canal = guild.get_channel(CANAL_LEILAO_ID) if CANAL_LEILAO_ID else interaction.channel
        if canal is None:
            return "❌ Canal de leilão não encontrado. Verifique o `CANAL_LEILAO_ID`."
        perms = canal.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            return f"❌ Não tenho permissão para enviar embeds em {canal.mention}."

        if r.cargo_premio_id:
            cargo = guild.get_role(r.cargo_premio_id)
            if cargo is None or cargo >= guild.me.top_role:
                return "❌ O cargo de prêmio não existe mais ou está acima do cargo do bot."

        agora = int(time.time())
        lid = await self.pool.fetchval(
            """
            INSERT INTO leiloes (guild_id, channel_id, autor_id, item, descricao, imagem,
                                 lance_minimo, incremento, arremate, cargo_premio_id,
                                 fim_ts, criado_ts)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING id
            """,
            guild.id, canal.id, r.autor_id, r.item, r.descricao, r.imagem,
            r.lance_minimo, r.incremento, r.arremate, r.cargo_premio_id,
            agora + r.duracao_seg, agora,
        )
        l = LeilaoEstado(
            id=lid,
            guild_id=guild.id,
            channel_id=canal.id,
            autor_id=r.autor_id,
            item=r.item,
            descricao=r.descricao,
            imagem=r.imagem,
            lance_minimo=r.lance_minimo,
            incremento=r.incremento,
            arremate=r.arremate,
            cargo_premio_id=r.cargo_premio_id,
            fim_ts=agora + r.duracao_seg,
        )
        try:
            msg = await canal.send(embed=embed_leilao(l), view=montar_view(l))
        except discord.HTTPException as e:
            await self.pool.execute("DELETE FROM leiloes WHERE id=$1", lid)
            return f"❌ Não consegui publicar o leilão ({e.text})."

        l.message_id = msg.id
        await self.pool.execute("UPDATE leiloes SET message_id=$2 WHERE id=$1", lid, msg.id)
        self.ativos[lid] = l
        self._agendar(l)
        await self._log(
            guild.id,
            "🔨 Leilão criado",
            f"**{l.item}** (#{l.id}) por <@{l.autor_id}>\n"
            f"Lance inicial: {formatar_moedas(l.lance_minimo)} • "
            f"Duração: {formatar_duracao_seg(r.duracao_seg)}\n{l.link}",
        )
        return l

    # ── Lances ──────────────────────────────────────────────────
    async def processar_lance(self, interaction: discord.Interaction, lid: int, valor: int):
        if not self.pronto:
            return await interaction.response.send_message(
                "❌ Sistema de leilões indisponível no momento.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        l = self.ativos.get(lid)
        if l is None or l.status != "ativo":
            return await interaction.followup.send("❌ Este leilão já foi encerrado.", ephemeral=True)

        user = interaction.user
        arrematou = False
        superado_id = None

        async with l.lock:
            if l.status != "ativo" or not l.vivo():
                return await interaction.followup.send("❌ O tempo deste leilão expirou.", ephemeral=True)
            if user.id == l.autor_id:
                return await interaction.followup.send(
                    "❌ Você não pode dar lances no leilão que criou.", ephemeral=True
                )
            if l.vencedor_id == user.id:
                return await interaction.followup.send(
                    "⚠️ Você já possui o maior lance! Aguarde ser superado.", ephemeral=True
                )
            minimo = l.minimo_proximo
            if valor < minimo:
                return await interaction.followup.send(
                    f"❌ Lance mínimo: {formatar_moedas(minimo)}\nVocê tentou: {formatar_moedas(valor)}",
                    ephemeral=True,
                )
            if l.arremate and valor >= l.arremate:
                valor = l.arremate
                arrematou = True

            anterior_id, anterior_valor = l.vencedor_id, l.lance_atual
            agora = int(time.time())
            prorrogou = (
                not arrematou
                and l.restante() <= ANTI_SNIPER_SEGUNDOS
                and l.extensoes < MAXIMO_EXTENSOES
            )
            novo_fim = l.fim_ts + EXTENSAO_ANTI_SNIPER if prorrogou else l.fim_ts
            novas_ext = l.extensoes + (1 if prorrogou else 0)

            debitado = creditado = False
            try:
                async with self.pool.acquire() as conn:
                    async with conn.transaction():
                        if not await self.economia.debitar(user.id, valor, conn):
                            raise _SaldoInsuficiente()
                        debitado = True
                        if anterior_id and anterior_valor:
                            await self.economia.creditar(anterior_id, anterior_valor, conn)
                            creditado = True
                        await conn.execute(
                            "UPDATE leiloes SET lance_atual=$2, vencedor_id=$3, fim_ts=$4, "
                            "extensoes=$5 WHERE id=$1 AND status='ativo'",
                            lid, valor, user.id, novo_fim, novas_ext,
                        )
                        await conn.execute(
                            "INSERT INTO leilao_lances (leilao_id, user_id, nome, valor, ts) "
                            "VALUES ($1,$2,$3,$4,$5)",
                            lid, user.id, user.display_name, valor, agora,
                        )
            except _SaldoInsuficiente:
                saldo = await self.economia.saldo(user.id)
                return await interaction.followup.send(
                    f"❌ Saldo insuficiente.\nSeu saldo: {formatar_moedas(saldo)}\n"
                    f"Lance desejado: {formatar_moedas(valor)}",
                    ephemeral=True,
                )
            except Exception:  # noqa: BLE001
                log.exception("Erro ao processar lance no leilão %s", lid)
                if self.economia.externa:
                    # A transação do banco foi revertida, mas a economia externa não.
                    try:
                        if debitado:
                            await self.economia.creditar(user.id, valor)
                        if creditado:
                            await self.economia.debitar(anterior_id, anterior_valor)
                    except Exception:  # noqa: BLE001
                        log.exception("Falha ao compensar o lance do leilão %s", lid)
                return await interaction.followup.send(
                    "⚠️ Não consegui registrar o lance. Nenhuma moeda foi cobrada — tente de novo.",
                    ephemeral=True,
                )

            l.lance_atual = valor
            l.vencedor_id = user.id
            l.fim_ts = novo_fim
            l.extensoes = novas_ext
            l.total_lances += 1
            l.historico.append((user.display_name, valor, agora))
            l.historico = l.historico[-50:]
            superado_id = anterior_id

        extra = ""
        if arrematou:
            extra = "\n⚡ **Arremate imediato!** O leilão será encerrado agora."
        elif prorrogou:
            extra = f"\n⚡ *Tempo estendido em {EXTENSAO_ANTI_SNIPER}s (anti-sniper).*"
        await interaction.followup.send(
            f"✅ Lance registrado: {formatar_moedas(valor)}{extra}", ephemeral=True
        )

        if superado_id and superado_id != user.id:
            self._tarefa_aux(self._avisar_superado(l, superado_id, valor))

        if arrematou:
            await self.finalizar(lid)
        else:
            self._agendar_atualizacao(l)

    # ── Botões do leilão ────────────────────────────────────────
    async def tratar_botao(self, interaction: discord.Interaction, acao: str, lid: int):
        if not self.pronto:
            return await interaction.response.send_message(
                "❌ Sistema de leilões indisponível no momento.", ephemeral=True
            )
        l = self.ativos.get(lid)
        if l is None or l.status != "ativo":
            return await interaction.response.send_message(
                "❌ Este leilão já foi encerrado.", ephemeral=True
            )

        if acao == "lance":
            return await interaction.response.send_modal(LanceModal(self, l))
        if acao == "min":
            return await self.processar_lance(interaction, lid, l.minimo_proximo)
        if acao in ("p10", "p25"):
            pct = 10 if acao == "p10" else 25
            valor = max(l.minimo_proximo, math.ceil(l.valor_exibido * (1 + pct / 100)))
            return await self.processar_lance(interaction, lid, valor)
        if acao == "arremate":
            if not l.arremate:
                return await interaction.response.send_message(
                    "❌ Este leilão não tem arremate imediato.", ephemeral=True
                )
            return await self.processar_lance(interaction, lid, l.arremate)

        if acao == "hist":
            if not l.historico:
                return await interaction.response.send_message(
                    "📜 Nenhum lance registrado ainda.", ephemeral=True
                )
            linhas = [
                f"`#{l.total_lances - i:02d}` **{nome}** — {formatar_moedas(valor)} • <t:{ts}:R>"
                for i, (nome, valor, ts) in enumerate(reversed(l.historico[-20:]))
            ]
            return await interaction.response.send_message(
                embed=embed_base(f"📜 Histórico — {l.item}", "\n".join(linhas)),
                ephemeral=True,
            )

        if acao == "saldo":
            await interaction.response.defer(ephemeral=True)
            saldo = await self.economia.saldo(interaction.user.id)
            minimo = l.minimo_proximo
            pode = saldo >= minimo
            return await interaction.followup.send(
                f"💼 **Seu saldo:** {formatar_moedas(saldo)}\n"
                f"🎯 **Próximo mínimo:** {formatar_moedas(minimo)}\n"
                f"{'✅ Você pode' if pode else '❌ Você não pode'} dar o próximo lance.",
                ephemeral=True,
            )

        if acao == "lembrar":
            existe = await self.pool.fetchval(
                "SELECT 1 FROM leilao_lembretes WHERE leilao_id=$1 AND user_id=$2",
                lid, interaction.user.id,
            )
            if existe:
                await self.pool.execute(
                    "DELETE FROM leilao_lembretes WHERE leilao_id=$1 AND user_id=$2",
                    lid, interaction.user.id,
                )
                return await interaction.response.send_message(
                    "🔕 Lembrete desativado para este leilão.", ephemeral=True
                )
            await self.pool.execute(
                "INSERT INTO leilao_lembretes (leilao_id, user_id) VALUES ($1,$2) "
                "ON CONFLICT DO NOTHING",
                lid, interaction.user.id,
            )
            return await interaction.response.send_message(
                f"🔔 Combinado! Aviso por DM quando faltarem {LEMBRETE_SEGUNDOS // 60} minutos.\n"
                "*Mantenha as DMs abertas. Se alguém superar o seu lance, você também é avisado.*",
                ephemeral=True,
            )

        if acao == "cancelar":
            if not (eh_gestor(interaction.user) or interaction.user.id == l.autor_id):
                return await interaction.response.send_message(
                    "❌ Apenas a gestão ou quem criou o leilão pode cancelar.", ephemeral=True
                )
            return await interaction.response.send_modal(CancelarModal(self, lid))

    # ── Embeds de listagem ──────────────────────────────────────
    def embed_ativos(self, guild_id: int) -> discord.Embed:
        lista = sorted(
            (x for x in self.ativos.values() if x.guild_id == guild_id),
            key=lambda x: x.fim_ts,
        )
        if not lista:
            return embed_base("📋 Leilões ativos", "> `📭` Nenhum leilão ativo no momento.")
        linhas = [
            f"`#{x.id}` **{x.item}** — {formatar_moedas(x.valor_exibido)} • "
            f"encerra <t:{x.fim_ts}:R> • [ir ao leilão]({x.link})"
            for x in lista
        ]
        return embed_base("📋 Leilões ativos", "\n".join(linhas))

    # ── Erros de comando ────────────────────────────────────────
    async def cog_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=6)
        elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send("⚠️ Uso incorreto do comando.", delete_after=7)
        else:
            raise error

    # ── Comandos ────────────────────────────────────────────────
    @commands.command(name="painelleilao", aliases=["painel_leilao"])
    @apenas_gestor()
    async def painelleilao(self, ctx: commands.Context):
        """Envia o painel de leilões neste canal."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        embed = embed_base(None, PAINEL_DESCRICAO.strip(), banner=True)
        await ctx.send(embed=embed, view=PainelLeilaoView(self))

    @commands.command(name="leiloes")
    async def leiloes(self, ctx: commands.Context):
        """Lista os leilões ativos."""
        await ctx.send(embed=self.embed_ativos(ctx.guild.id))

    @commands.command(name="leilaostatus")
    @apenas_gestor()
    async def leilaostatus(self, ctx: commands.Context):
        """Diagnóstico do sistema de leilões."""
        embed = embed_base("🩺 Status dos leilões")
        embed.add_field(
            name="🗄️ PostgreSQL",
            value="✅ Conectado" if self.pool is not None else "❌ bot.pool não existe",
            inline=True,
        )
        embed.add_field(
            name="💳 Economia",
            value=self.economia.nome if self.economia else "—",
            inline=True,
        )
        embed.add_field(
            name="🔨 Leilões ativos",
            value=f"**{len([x for x in self.ativos.values() if x.guild_id == ctx.guild.id])}**"
            f" / {MAX_LEILOES_ATIVOS}",
            inline=True,
        )
        canal = ctx.guild.get_channel(CANAL_LEILAO_ID) if CANAL_LEILAO_ID else None
        embed.add_field(
            name="📢 Canal dos leilões",
            value=canal.mention if canal else "Onde o painel foi enviado",
            inline=True,
        )
        embed.add_field(
            name="🧾 Canal de logs",
            value=f"<#{CANAL_LOGS_ID}>" if CANAL_LOGS_ID else "desligado",
            inline=True,
        )
        cargos = []
        for rid in CARGOS_PAINEL:
            cargo = ctx.guild.get_role(rid)
            cargos.append(f"✅ {cargo.mention}" if cargo else f"❌ `{rid}` não encontrado")
        embed.add_field(
            name="🛡️ Cargos do painel",
            value="\n".join(cargos) or "—",
            inline=False,
        )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="leilaosaldo")
    async def leilaosaldo(self, ctx: commands.Context, membro: discord.Member = None):
        """Mostra o saldo de moedas (a equipe pode ver o de outras pessoas)."""
        if not self.pronto:
            return await ctx.send("❌ Sistema de leilões indisponível.", delete_after=6)
        alvo = membro or ctx.author
        if alvo.id != ctx.author.id and not eh_gestor(ctx.author):
            return await ctx.send("❌ Só a equipe vê o saldo de outras pessoas.", delete_after=6)
        saldo = await self.economia.saldo(alvo.id)
        await ctx.send(
            embed=embed_base("💼 Saldo", f"{alvo.mention} tem {formatar_moedas(saldo)}."),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="leilaodar")
    @apenas_gestor()
    async def leilaodar(self, ctx: commands.Context, membro: discord.Member, valor: str):
        """Dá moedas na carteira própria do leilão. Ex.: !leilaodar @membro 5k"""
        if not self.pronto or self.economia.externa:
            return await ctx.send(
                "❌ Disponível só com a carteira própria. Use os comandos da economia do cassino.",
                delete_after=8,
            )
        quantia = parsear_valor(valor)
        if quantia is None:
            return await ctx.send("⚠️ Valor inválido.", delete_after=6)
        await self.economia.creditar(membro.id, quantia)
        await ctx.send(f"✅ {membro.mention} recebeu {formatar_moedas(quantia)}.")
        await self._log(ctx.guild.id, "➕ Moedas entregues", f"{ctx.author.mention} → {membro.mention}: {formatar_moedas(quantia)}")

    @commands.command(name="leilaotirar")
    @apenas_gestor()
    async def leilaotirar(self, ctx: commands.Context, membro: discord.Member, valor: str):
        """Remove moedas da carteira própria do leilão. Ex.: !leilaotirar @membro 5k"""
        if not self.pronto or self.economia.externa:
            return await ctx.send(
                "❌ Disponível só com a carteira própria. Use os comandos da economia do cassino.",
                delete_after=8,
            )
        quantia = parsear_valor(valor)
        if quantia is None:
            return await ctx.send("⚠️ Valor inválido.", delete_after=6)
        if not await self.economia.debitar(membro.id, quantia):
            return await ctx.send("❌ Saldo insuficiente para remover essa quantia.", delete_after=8)
        await ctx.send(f"✅ Removido {formatar_moedas(quantia)} de {membro.mention}.")
        await self._log(ctx.guild.id, "➖ Moedas removidas", f"{ctx.author.mention} → {membro.mention}: {formatar_moedas(quantia)}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Leilao(bot))