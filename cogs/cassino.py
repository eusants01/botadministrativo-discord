from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg
import discord
from discord.ext import commands

from utils import cassino_db as db
from utils import cassino_extras as extras
from utils import cassino_partidas as partidas

LOG = logging.getLogger(__name__)
FUSO = ZoneInfo("America/Sao_Paulo")
RNG = random.SystemRandom()

# ╔══════════════════════════════════════════════════════════════╗
# ║                        CONFIGURAÇÃO                          ║
# ╚══════════════════════════════════════════════════════════════╝

NOME_SERVIDOR = "Família Sant's"
MOEDA = "SC"
BANNER = os.getenv("CASSINO_BANNER_URL", "").strip()   # link direto da imagem do cassino

# Paleta "desenho animado dos anos 30": ouro, vermelho-diabo e sépia
COR_OURO = 0xD4A23A
COR_DIABO = 0xA52A35
COR_SEPIA = 0x4A3320
COR_JACKPOT = 0xFFC107

MIN_APOSTA = 10
INTERVALO_SEG = 4              # tempo mínimo entre partidas de uma mesma pessoa
PAUSA_ANIMACAO = 0.9           # segundos entre os "quadros" das animações

# Canal público que recebe o aviso de grandes vitórias (0 = desligado)
CANAL_ANUNCIOS_ID = 0
LIMITE_ANUNCIO = 5_000         # prêmio mínimo (SC) para anunciar
LIMITE_ANUNCIO_MULT = 25       # ...ou multiplicador mínimo

# Pote do Diabo (jackpot progressivo)
POTE_INICIAL = 5_000
POTE_PERCENTUAL = 0.03         # % de TODA aposta que vai para o pote
JACKPOT_BASE_MULT = 100        # a trinca de 😈 paga isso × aposta + o pote inteiro

# Eventos de bônus: somam % ao prêmio quando a pessoa ganha. [] = nenhum.
# dias: 0=segunda ... 6=domingo (horário de Brasília)
EVENTOS_BONUS = [
    {"nome": "Hora Feliz do Diabo", "dias": [4, 5, 6], "inicio": 20, "fim": 23, "bonus": 0.10},
]

# Níveis: (apostado total necessário, título, aposta máxima)
NIVEIS = [
    (0, "Visitante da Mesa", 1_000),
    (2_000, "Cuphead Apostador", 2_000),
    (10_000, "Fã do King Dice", 4_000),
    (40_000, "Cliente VIP", 7_500),
    (120_000, "Sócio do Diabo", 12_500),
    (400_000, "Lenda do Cassino", 20_000),
    (1_000_000, "Dono da Casa", 30_000),
]

# ── Tabelas de prêmio ────────────────────────────────────────────────────────
CARA_MULT = 1.95
DADOS_MULT_NUMERO = 5.85
DADOS_MULT_METADE = 1.95

# Slot: (símbolo, peso por rolo, prêmio da trinca em ×). 😈 é o jackpot.
SIMBOLOS = [
    ("🪙", 30, 8), ("🥤", 24, 14), ("🎲", 20, 22), ("🃏", 15, 35),
    ("🍀", 10, 70), ("👑", 8, 150), ("😈", 9, 0),
]
SLOT_PAR_MOEDA = 1.0     # duas 🪙 em qualquer posição
SLOT_PAR_OUTRO = 0.6     # dois símbolos iguais quaisquer

# Roleta europeia (0-36). Pagamento = 36 / casas cobertas × 0,973 ≈ tabela abaixo.
VERMELHOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

# Corrida: (nome, emoji, chance de vencer). Pagamento ≈ 0,95 / chance.
CORREDORES = [
    ("Cuphead", "🥤", 0.36),
    ("Mugman", "☕", 0.27),
    ("Ms. Chalice", "🏆", 0.19),
    ("Phear Lap", "👻", 0.12),
    ("O Diabo", "😈", 0.06),
]

# King Dice: cada andar tem esta chance; vencer TODOS os andares escolhidos paga o prêmio.
KD_CHANCE = 0.55
KD_BOSSES = ["Pip & Dot", "Mr. Wheezy", "Hopus Pocus", "Phear Lap", "Tipsy Troop", "Chips Bettigan", "King Dice"]


def kd_mult(andares: int) -> float:
    return round(0.95 / (KD_CHANCE ** andares), 1)


def corrida_mult(i: int) -> float:
    return int(0.95 / CORREDORES[i][2] * 10) / 10


# ── Conquistas ───────────────────────────────────────────────────────────────
CONQUISTAS = {
    "contrato": ("📜", "Contrato Assinado", "Faça a sua primeira aposta."),
    "veterano": ("🎖️", "Veterano da Mesa", "Jogue 100 partidas."),
    "x10": ("🔥", "Sorte do Diabo", "Ganhe um prêmio de 10× ou mais."),
    "x50": ("💥", "Pancada Lendária", "Ganhe um prêmio de 50× ou mais."),
    "milhar": ("💰", "Cofre Aberto", "Ganhe 10.000 SC ou mais em uma partida."),
    "jackpot": ("😈", "Pacto com o Diabo", "Leve o Pote do Diabo."),
    "seq5": ("⚡", "Em Chamas", "Vença 5 partidas seguidas."),
    "andar7": ("👑", "Derrotou o Rei", "Vença os 7 andares do King Dice."),
    "numero": ("🎯", "Mira Certeira", "Acerte um número exato na roleta."),
    "alto": ("💎", "High Roller", "Aposte 5.000 SC ou mais de uma vez."),
}

# ════════════════════════════════════════════════════════════════
#                              BANCO (extras)
# ════════════════════════════════════════════════════════════════
# Dinheiro: SEMPRE pelo partidas.finalizar_partida_cassino (débito + prêmio atômicos).
# Estas tabelas guardam só progressão e o pote: não mexem no saldo.

SQL_CASSINO = """
CREATE TABLE IF NOT EXISTS cassino_perfil (
    user_id BIGINT PRIMARY KEY,
    apostado BIGINT NOT NULL DEFAULT 0,
    partidas INTEGER NOT NULL DEFAULT 0,
    vitorias INTEGER NOT NULL DEFAULT 0,
    maior_premio BIGINT NOT NULL DEFAULT 0,
    melhor_mult DOUBLE PRECISION NOT NULL DEFAULT 0,
    sequencia INTEGER NOT NULL DEFAULT 0,
    melhor_sequencia INTEGER NOT NULL DEFAULT 0,
    jackpots INTEGER NOT NULL DEFAULT 0,
    conquistas JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_cassino_perfil_premio ON cassino_perfil (maior_premio DESC);

CREATE TABLE IF NOT EXISTS cassino_pote (
    id INTEGER PRIMARY KEY,
    valor BIGINT NOT NULL,
    ultimo_vencedor BIGINT,
    ultimo_valor BIGINT,
    ultimo_ts BIGINT
);
"""

JOGOS_LEGADO = {"cara", "dados", "roleta", "kingdice"}


# ════════════════════════════════════════════════════════════════
#                      LÓGICA DOS JOGOS (testável)
# ════════════════════════════════════════════════════════════════


@dataclass
class Resultado:
    mult: float                 # multiplicador bruto sobre a aposta (0 = perdeu)
    sorteio: str                # texto curto do que saiu
    escolha: str                # texto curto do que a pessoa escolheu
    cena: dict = field(default_factory=dict)
    jackpot: bool = False
    extra: int = 0              # bônus fixo somado ao prêmio (pote)


def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", ".") + f" {MOEDA}"


def fmt_mult(m: float) -> str:
    return (f"{m:.2f}".rstrip("0").rstrip(".") if m % 1 else f"{int(m)}").replace(".", ",") + "×"


def nivel_de(apostado: int) -> int:
    nivel = 0
    for i, (minimo, _, _) in enumerate(NIVEIS):
        if apostado >= minimo:
            nivel = i
    return nivel


def limite_de(apostado: int) -> int:
    return NIVEIS[nivel_de(apostado)][2]


def barra(atual: float, total: float, tam: int = 10) -> str:
    cheios = max(0, min(tam, round(tam * atual / total))) if total else tam
    return "▰" * cheios + "▱" * (tam - cheios)


def cor_roleta(n: int) -> str:
    return "🟢" if n == 0 else ("🔴" if n in VERMELHOS else "⚫")


def evento_ativo(agora: datetime | None = None) -> dict | None:
    agora = agora or datetime.now(FUSO)
    for e in EVENTOS_BONUS:
        if agora.weekday() in e["dias"] and e["inicio"] <= agora.hour < e["fim"]:
            return e
    return None


def escolha_valida(jogo: str, escolha: str) -> bool:
    if jogo == "cara":
        return escolha in ("cara", "coroa")
    if jogo == "dados":
        return escolha in ("1", "2", "3", "4", "5", "6", "alto", "baixo", "par", "impar")
    if jogo == "roleta":
        if escolha in ("vermelho", "preto", "par", "impar", "d1", "d2", "d3", "verde"):
            return True
        return escolha.startswith("n") and escolha[1:].isdigit() and 0 <= int(escolha[1:]) <= 36
    if jogo == "kingdice":
        return escolha in {str(k) for k in range(1, 8)}
    if jogo == "corrida":
        return escolha in {str(i) for i in range(len(CORREDORES))}
    if jogo == "slots":
        return escolha == "girar"
    return False


def nome_escolha(jogo: str, escolha: str) -> str:
    if jogo == "roleta":
        if escolha.startswith("n"):
            return f"Número {escolha[1:]}"
        return {"vermelho": "Vermelho", "preto": "Preto", "par": "Par", "impar": "Ímpar",
                "d1": "1ª dúzia", "d2": "2ª dúzia", "d3": "3ª dúzia", "verde": "Verde (0)"}[escolha]
    if jogo == "dados":
        return {"alto": "Alto (4-6)", "baixo": "Baixo (1-3)", "par": "Par", "impar": "Ímpar"}.get(escolha, f"Número {escolha}")
    if jogo == "corrida":
        return CORREDORES[int(escolha)][0]
    if jogo == "kingdice":
        n = int(escolha)
        return f"{n} andar" + ("" if n == 1 else "es")
    if jogo == "slots":
        return "Girar"
    return escolha.capitalize()


def resolver_cara(escolha: str) -> Resultado:
    lado = RNG.choice(("cara", "coroa"))
    return Resultado(CARA_MULT if lado == escolha else 0, lado, escolha, {"lado": lado})


def resolver_dados(escolha: str) -> Resultado:
    d = RNG.randint(1, 6)
    if escolha.isdigit():
        ganhou, mult = d == int(escolha), DADOS_MULT_NUMERO
    else:
        ganhou = {"alto": d >= 4, "baixo": d <= 3, "par": d % 2 == 0, "impar": d % 2 == 1}[escolha]
        mult = DADOS_MULT_METADE
    return Resultado(mult if ganhou else 0, str(d), escolha, {"dado": d})


def resolver_roleta(escolha: str) -> Resultado:
    n = RNG.randint(0, 36)
    if escolha in ("vermelho", "preto"):
        ganhou, mult = n != 0 and (n in VERMELHOS) == (escolha == "vermelho"), 2
    elif escolha in ("par", "impar"):
        ganhou, mult = n != 0 and (n % 2 == 0) == (escolha == "par"), 2
    elif escolha in ("d1", "d2", "d3"):
        k = int(escolha[1])
        ganhou, mult = 12 * (k - 1) < n <= 12 * k, 3
    elif escolha == "verde":
        ganhou, mult = n == 0, 36
    else:
        ganhou, mult = n == int(escolha[1:]), 36
    return Resultado(mult if ganhou else 0, f"{n} {cor_roleta(n)}", escolha, {"n": n})


def resolver_kingdice(escolha: str) -> Resultado:
    andares = int(escolha)
    passou = []
    for _ in range(andares):
        ok = RNG.random() < KD_CHANCE
        passou.append(ok)
        if not ok:
            break
    venceu = len(passou) == andares and all(passou)
    return Resultado(
        kd_mult(andares) if venceu else 0,
        f"{sum(passou)}/{andares} andares",
        escolha,
        {"passou": passou, "andares": andares},
    )


def resolver_corrida(escolha: str) -> Resultado:
    chances = [c[2] for c in CORREDORES]
    vencedor = RNG.choices(range(len(CORREDORES)), weights=chances, k=1)[0]
    mult = corrida_mult(int(escolha)) if vencedor == int(escolha) else 0
    return Resultado(mult, CORREDORES[vencedor][0], escolha, {"vencedor": vencedor})


def resolver_slots(pote: int = 0) -> Resultado:
    rolos = RNG.choices([s[0] for s in SIMBOLOS], weights=[s[1] for s in SIMBOLOS], k=3)
    sorteio = " ".join(rolos)
    tabela = {s[0]: s[2] for s in SIMBOLOS}
    if rolos[0] == rolos[1] == rolos[2]:
        if rolos[0] == "😈":
            return Resultado(JACKPOT_BASE_MULT, sorteio, "girar", {"rolos": rolos}, jackpot=True, extra=pote)
        return Resultado(tabela[rolos[0]], sorteio, "girar", {"rolos": rolos})
    for s in set(rolos):
        if rolos.count(s) == 2:
            mult = SLOT_PAR_MOEDA if s == "🪙" else SLOT_PAR_OUTRO
            return Resultado(mult, sorteio, "girar", {"rolos": rolos})
    return Resultado(0, sorteio, "girar", {"rolos": rolos})


def resolver(jogo: str, escolha: str, pote: int = 0) -> Resultado:
    if jogo == "cara":
        return resolver_cara(escolha)
    if jogo == "dados":
        return resolver_dados(escolha)
    if jogo == "roleta":
        return resolver_roleta(escolha)
    if jogo == "kingdice":
        return resolver_kingdice(escolha)
    if jogo == "corrida":
        return resolver_corrida(escolha)
    return resolver_slots(pote)


def conquistas_novas(perfil: dict, ctx: dict) -> list[str]:
    ja = set(perfil["conquistas"])
    ganhou: list[str] = []

    def add(chave: str, cond: bool):
        if cond and chave not in ja:
            ganhou.append(chave)

    add("contrato", True)
    add("veterano", perfil["partidas"] >= 100)
    add("x10", ctx["mult"] >= 10)
    add("x50", ctx["mult"] >= 50)
    add("milhar", ctx["premio"] >= 10_000)
    add("jackpot", ctx["jackpot"])
    add("seq5", perfil["sequencia"] >= 5)
    add("andar7", ctx["jogo"] == "kingdice" and ctx["escolha"] == "7" and ctx["premio"] > 0)
    add("numero", ctx["jogo"] == "roleta" and ctx["escolha"].startswith("n") and ctx["premio"] > 0)
    add("alto", ctx["aposta"] >= 5_000)
    return ganhou


FRASES_PERDA = [
    "A casa nunca perde, Cuphead.",
    "Sua alma ficou mais leve... e a carteira também.",
    "O contrato ainda está de pé. Tente de novo!",
    "Quase! Mas “quase” não paga a conta.",
    "O Diabo sorri. Você, nem tanto.",
]
FRASES_PARCIAL = [
    "Salvou uma parte. O Diabo deixou passar... desta vez.",
    "Prêmio de consolação! A casa é generosa. Às vezes.",
]
FRASES_GANHO = [
    "Hmpf... sorte de principiante.",
    "O Diabo paga as suas dívidas. Desta vez.",
    "Contrato cumprido! As moedas são suas.",
    "Isso foi sorte ou habilidade? Descubra jogando de novo.",
]
FRASES_GRANDE = [
    "IMPOSSÍVEL! Quem deixou esse jogador entrar?!",
    "A casa estremece! Que pancada!",
    "O Diabo está furioso... e o seu bolso, feliz!",
]


# ════════════════════════════════════════════════════════════════
#                               EMBEDS
# ════════════════════════════════════════════════════════════════


def base(descricao: str, cor: int = COR_DIABO, banner: bool = False, titulo: str | None = None) -> discord.Embed:
    e = discord.Embed(title=titulo, description=descricao[:4096], color=cor)
    if banner and BANNER.startswith(("https://", "http://")):
        e.set_image(url=BANNER)
    e.set_footer(text=f"{NOME_SERVIDOR} • Cassino do Diabo • Jogue com moderação (a casa não)")
    return e


def painel_embed() -> discord.Embed:
    texto = (
        "# <:thedevilgrin:1559778113519493151> **CASSINO DO DIABO**\n"
        "*Entre, assine o contrato e tente a sorte. A casa sempre sorri.*\n\n"
        "**As Mesas**\n"
        "> `🪙` **Cara ou Coroa** — Dobre (quase) a aposta.\n"
        "> `🎲` **Dados do Rei** — Número exato paga até **5,85×**.\n"
        "> `🎡` **Roleta** — Números pagam até **36×**.\n"
        "> `🎰` **Caça-Níquel** — Trincas até **150×** e o **Pote do Diabo**.\n"
        "> `🏇` **Corrida de Phear Lap** — Zebras pagam até "
        f"**{fmt_mult(corrida_mult(len(CORREDORES) - 1))}**.\n"
        f"> `👑` **Casa de Dados (King Dice)** — 7 andares, até **{fmt_mult(kd_mult(7))}**.\n\n"
        "**Grátis todo dia**\n"
        "> `📜` **Contratos do Diabo** — Missões diárias com recompensa.\n"
        "> `🃏` **Cartas do Destino** — Uma carta grátis por dia.\n\n"
        "**Progressão**\n"
        "> `⭐` Quanto mais você joga, mais sobe de **nível** e maior fica a sua **aposta máxima**.\n"
        "> `🏅` Desbloqueie **conquistas** e entre no **Hall da Fama**.\n"
        "> `🔥` Eventos de **bônus** aumentam os prêmios em horários especiais.\n\n"
        "**Regras**\n"
        f"> `💰` Apostas a partir de **{fmt(MIN_APOSTA)}** (o limite máximo depende do seu nível).\n"
        "> `⏳` Uma partida por vez, com um pequeno intervalo.\n"
        "> `🎭` Apostas usam apenas moedas virtuais do servidor."
    )
    return base(texto, COR_DIABO, banner=True)


def embed_tabela() -> discord.Embed:
    slot = "\n".join(f"> `{s[0]}{s[0]}{s[0]}` — **{fmt_mult(s[2])}**" for s in SIMBOLOS if s[0] != "😈")
    roleta = (
        "> **Vermelho / Preto / Par / Ímpar** — 2×\n"
        "> **Dúzias** (1-12, 13-24, 25-36) — 3×\n"
        "> **Número exato / Verde (0)** — 36×"
    )
    corrida = "\n".join(
        f"> {c[1]} **{c[0]}** — {fmt_mult(corrida_mult(i))} ({round(c[2] * 100)}% de chance)"
        for i, c in enumerate(CORREDORES)
    )
    kd = "\n".join(
        f"> **{k}** andar{'es' if k > 1 else ''} — {fmt_mult(kd_mult(k))} ({KD_CHANCE ** k * 100:.1f}% de chance)"
        for k in range(1, 8)
    )
    texto = (
        "# 📜 **Tabela de Prêmios**\n\n"
        f"**🪙 Cara ou Coroa**\n> Acertou o lado — **{fmt_mult(CARA_MULT)}**\n\n"
        f"**🎲 Dados do Rei**\n> Número exato — **{fmt_mult(DADOS_MULT_NUMERO)}**\n"
        f"> Alto, Baixo, Par ou Ímpar — **{fmt_mult(DADOS_MULT_METADE)}**\n\n"
        f"**🎡 Roleta**\n{roleta}\n\n"
        f"**🎰 Caça-Níquel**\n{slot}\n"
        f"> `😈😈😈` — **JACKPOT:** {JACKPOT_BASE_MULT}× **+ o Pote do Diabo**\n"
        f"> Duas 🪙 — {fmt_mult(SLOT_PAR_MOEDA)} • Dois iguais — {fmt_mult(SLOT_PAR_OUTRO)}\n\n"
        f"**🏇 Corrida de Phear Lap**\n{corrida}\n\n"
        f"**👑 Casa de Dados (King Dice)**\n{kd}"
    )
    return base(texto, COR_SEPIA)


def embed_cena(titulo: str, linhas: list[str], cor: int = COR_SEPIA) -> discord.Embed:
    return base(f"# {titulo}\n" + "\n".join(linhas), cor)


def embed_resultado(
    jogo_nome: str, escolha: str, sorteio: str, aposta: int, premio: int, saldo: int,
    numero: str, mult: float, bonus: dict | None, jackpot: bool,
    perfil: dict, nivel_antes: int, novas: list[str], pote: int,
) -> discord.Embed:
    liquido = premio - aposta
    if jackpot:
        titulo, cor, frase = "😈 JACKPOT DO DIABO!!!", COR_JACKPOT, RNG.choice(FRASES_GRANDE)
    elif premio >= aposta * 10 and premio > 0:
        titulo, cor, frase = "🏆 O DIABO PAGOU!", COR_OURO, RNG.choice(FRASES_GRANDE)
    elif premio > aposta:
        titulo, cor, frase = "🏆 O DIABO PAGOU!", COR_OURO, RNG.choice(FRASES_GANHO)
    elif premio > 0:
        titulo, cor, frase = "🎭 QUASE!", COR_SEPIA, RNG.choice(FRASES_PARCIAL)
    else:
        titulo, cor, frase = "🎭 A CASA VENCEU", COR_DIABO, RNG.choice(FRASES_PERDA)

    linhas = [
        f"*“{frase}”*",
        "",
        f"**{jogo_nome}** • Rodada `{numero[:8]}`",
        f"> `🎯` Sua escolha: **{escolha}**",
        f"> `🎲` Resultado: **{sorteio}**",
        "",
        f"> `💰` Aposta: **{fmt(aposta)}**",
        f"> `🏆` Prêmio: **{fmt(premio)}**" + (f" ({fmt_mult(mult)})" if mult else ""),
        f"> `{'📈' if liquido >= 0 else '📉'}` Líquido: **{'+' if liquido >= 0 else '-'}{fmt(abs(liquido))}**",
        f"> `👛` Saldo: **{fmt(saldo)}**",
    ]
    if bonus and premio > 0:
        linhas.append(f"> `🔥` **{bonus['nome']}**: +{round(bonus['bonus'] * 100)}% no prêmio!")
    if perfil["sequencia"] >= 2:
        linhas.append(f"> `⚡` Sequência de **{perfil['sequencia']}** vitórias!")

    nivel = nivel_de(perfil["apostado"])
    if nivel > nivel_antes:
        linhas += ["", f"⭐ **NOVO NÍVEL!** Você agora é **{NIVEIS[nivel][1]}** — aposta máxima de **{fmt(NIVEIS[nivel][2])}**."]
    for chave in novas:
        emoji, nome, desc = CONQUISTAS[chave]
        linhas.append(f"🏅 **Conquista desbloqueada:** {emoji} {nome}")
    if not jackpot:
        linhas += ["", f"`🎰` Pote do Diabo: **{fmt(pote)}**"]
    return base("\n".join(linhas), cor)


# ════════════════════════════════════════════════════════════════
#                           MENUS E BOTÕES
# ════════════════════════════════════════════════════════════════


def opcoes_do_jogo(jogo: str) -> list[tuple[str, str, str, str]]:
    """(rótulo, valor, emoji, descrição)"""
    if jogo == "cara":
        return [("Cara", "cara", "🪙", f"Prêmio {fmt_mult(CARA_MULT)}"), ("Coroa", "coroa", "👑", f"Prêmio {fmt_mult(CARA_MULT)}")]
    if jogo == "dados":
        ops = [(f"Número {i}", str(i), "🎯", f"Prêmio {fmt_mult(DADOS_MULT_NUMERO)}") for i in range(1, 7)]
        ops += [
            ("Alto (4-6)", "alto", "⬆️", f"Prêmio {fmt_mult(DADOS_MULT_METADE)}"),
            ("Baixo (1-3)", "baixo", "⬇️", f"Prêmio {fmt_mult(DADOS_MULT_METADE)}"),
            ("Par", "par", "2️⃣", f"Prêmio {fmt_mult(DADOS_MULT_METADE)}"),
            ("Ímpar", "impar", "1️⃣", f"Prêmio {fmt_mult(DADOS_MULT_METADE)}"),
        ]
        return ops
    if jogo == "roleta":
        return [
            ("Vermelho", "vermelho", "🔴", "Prêmio 2×"), ("Preto", "preto", "⚫", "Prêmio 2×"),
            ("Par", "par", "2️⃣", "Prêmio 2×"), ("Ímpar", "impar", "1️⃣", "Prêmio 2×"),
            ("1ª Dúzia (1-12)", "d1", "🟦", "Prêmio 3×"), ("2ª Dúzia (13-24)", "d2", "🟨", "Prêmio 3×"),
            ("3ª Dúzia (25-36)", "d3", "🟥", "Prêmio 3×"),
            ("Verde (0)", "verde", "🟢", "Prêmio 36×"), ("Número exato", "numero", "🎯", "Prêmio 36×"),
        ]
    if jogo == "corrida":
        return [
            (c[0], str(i), c[1], f"Prêmio {fmt_mult(corrida_mult(i))} • {round(c[2] * 100)}% de chance")
            for i, c in enumerate(CORREDORES)
        ]
    if jogo == "kingdice":
        return [
            (f"{k} andar{'es' if k > 1 else ''}", str(k), "👑" if k == 7 else "🎲",
             f"Prêmio {fmt_mult(kd_mult(k))} • {KD_CHANCE ** k * 100:.1f}% de chance")
            for k in range(1, 8)
        ]
    return []


NOMES_JOGOS = {
    "cara": "Cara ou Coroa", "dados": "Dados do Rei", "roleta": "Roleta",
    "slots": "Caça-Níquel do Diabo", "corrida": "Corrida de Phear Lap", "kingdice": "Casa de Dados (King Dice)",
}


class ApostaModal(discord.ui.Modal):
    def __init__(self, cog: "Cassino", jogo: str, escolha: str, limite: int):
        super().__init__(title=f"🎲 {NOMES_JOGOS[jogo]}"[:45], timeout=180)
        self.cog, self.jogo, self.escolha = cog, jogo, escolha
        self.valor = discord.ui.TextInput(
            label=f"Aposta em {MOEDA} (até {limite:,})".replace(",", "."),
            placeholder="Ex.: 100 • 1k • max",
            min_length=1,
            max_length=10,
        )
        self.add_item(self.valor)
        self.numero = None
        if escolha == "numero":
            self.numero = discord.ui.TextInput(label="Número (0 a 36)", placeholder="Ex.: 17", min_length=1, max_length=2)
            self.add_item(self.numero)

    async def on_submit(self, interaction: discord.Interaction):
        escolha = self.escolha
        if self.numero is not None:
            texto = self.numero.value.strip()
            if not (texto.isdigit() and 0 <= int(texto) <= 36):
                return await interaction.response.send_message("❌ Escolha um número entre 0 e 36.", ephemeral=True)
            escolha = f"n{int(texto)}"
        await self.cog.jogar(interaction, self.jogo, self.valor.value, escolha)


class EscolhaSelect(discord.ui.Select):
    def __init__(self, cog: "Cassino", jogo: str, limite: int):
        ops = opcoes_do_jogo(jogo)
        super().__init__(
            placeholder="Faça a sua escolha...",
            options=[discord.SelectOption(label=r, value=v, emoji=e, description=d[:100]) for r, v, e, d in ops],
        )
        self.cog, self.jogo, self.limite = cog, jogo, limite

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApostaModal(self.cog, self.jogo, self.values[0], self.limite))


class EscolhaView(discord.ui.View):
    def __init__(self, cog: "Cassino", jogo: str, limite: int):
        super().__init__(timeout=120)
        self.add_item(EscolhaSelect(cog, jogo, limite))


class ResultadoView(discord.ui.View):
    def __init__(self, cog: "Cassino", uid: int, jogo: str, escolha: str, aposta: int, limite: int):
        super().__init__(timeout=300)
        self.cog, self.uid, self.jogo, self.escolha, self.aposta = cog, uid, jogo, escolha, aposta
        self.dobrar.disabled = aposta * 2 > limite

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.uid:
            return True
        await interaction.response.send_message("❌ Esta mesa não é sua.", ephemeral=True)
        return False

    @discord.ui.button(label="Jogar de novo", emoji="🔁", style=discord.ButtonStyle.primary)
    async def repetir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.jogar(interaction, self.jogo, str(self.aposta), self.escolha, editar=True)

    @discord.ui.button(label="Dobrar aposta", emoji="⬆️", style=discord.ButtonStyle.danger)
    async def dobrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.jogar(interaction, self.jogo, str(self.aposta * 2), self.escolha, editar=True)


class CassinoView(discord.ui.View):
    def __init__(self, cog: "Cassino"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.select(
        placeholder="🎲 Escolha a sua mesa",
        custom_id="sants:cassino2:mesa",
        options=[
            discord.SelectOption(label="Cara ou Coroa", value="cara", emoji="🪙", description="50% de chance • prêmio 1,95×"),
            discord.SelectOption(label="Dados do Rei", value="dados", emoji="🎲", description="Número exato paga 5,85×"),
            discord.SelectOption(label="Roleta", value="roleta", emoji="🎡", description="Números pagam até 36×"),
            discord.SelectOption(label="Caça-Níquel do Diabo", value="slots", emoji="🎰", description="Trincas até 150× e o Pote do Diabo"),
            discord.SelectOption(label="Corrida de Phear Lap", value="corrida", emoji="🏇", description="Aposte no seu corredor • até 15,8×"),
            discord.SelectOption(label="Casa de Dados (King Dice)", value="kingdice", emoji="👑", description="Enfrente até 7 andares • até 62,5×"),
            discord.SelectOption(label="Contratos do Diabo", value="contratos", emoji="📜", description="Missões gratuitas diárias"),
            discord.SelectOption(label="Cartas do Destino", value="cartas", emoji="🃏", description="Uma carta grátis por dia"),
        ],
    )
    async def mesa(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.cog.abrir_mesa(interaction, select.values[0])

    @discord.ui.button(label="Carteira", emoji="🪙", style=discord.ButtonStyle.secondary, custom_id="sants:cassino2:saldo", row=1)
    async def carteira(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.mostrar_carteira(interaction)

    @discord.ui.button(label="Meu perfil", emoji="📊", style=discord.ButtonStyle.secondary, custom_id="sants:cassino2:perfil", row=1)
    async def perfil(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.mostrar_perfil(interaction)

    @discord.ui.button(label="Rankings", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="sants:cassino2:ranking", row=1)
    async def ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.mostrar_rankings(interaction)

    @discord.ui.button(label="Pote do Diabo", emoji="😈", style=discord.ButtonStyle.danger, custom_id="sants:cassino2:pote", row=2)
    async def pote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.mostrar_pote(interaction)

    @discord.ui.button(label="Tabela de prêmios", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="sants:cassino2:tabela", row=2)
    async def tabela(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=embed_tabela(), ephemeral=True)

    @discord.ui.button(label="Conquistas", emoji="🏅", style=discord.ButtonStyle.secondary, custom_id="sants:cassino2:conquistas", row=2)
    async def conquistas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.mostrar_conquistas(interaction)


class ContratoView(discord.ui.View):
    def __init__(self, cog: "Cassino"):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label="Concluir visita (+40 SC)", emoji="📜", style=discord.ButtonStyle.success)
    async def coletar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.coletar_visita(interaction)


class CartasView(discord.ui.View):
    def __init__(self, cog: "Cassino"):
        super().__init__(timeout=180)
        self.cog = cog
        for numero in (1, 2, 3):
            botao = discord.ui.Button(label=f"Carta {numero}", emoji="🂠", style=discord.ButtonStyle.primary)

            async def callback(interaction, n=numero):
                await self.cog.revelar_carta(interaction, n)

            botao.callback = callback
            self.add_item(botao)


# ════════════════════════════════════════════════════════════════
#                                COG
# ════════════════════════════════════════════════════════════════


class Cassino(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locks: dict[int, asyncio.Lock] = {}
        self.ultimo: dict[int, float] = {}
        self.lock_pote = asyncio.Lock()
        self.fallback_avisado = False

    @property
    def pool(self):
        return getattr(self.bot, "pool", None)

    async def cog_load(self):
        pool = self.pool
        if pool is None:
            raise RuntimeError("PostgreSQL indisponível: bot.pool não configurado")
        db.configurar_pool(pool)
        await db.inicializar_tabelas(pool)
        await partidas.inicializar_cassino(pool)
        await extras.inicializar_extras(pool)
        await pool.execute(SQL_CASSINO)
        await pool.execute(
            "INSERT INTO cassino_pote (id, valor) VALUES (1, $1) ON CONFLICT (id) DO NOTHING", POTE_INICIAL
        )
        self.bot.add_view(CassinoView(self))
        LOG.info("Cassino 3.0: painel persistente registrado")

    # ── Perfil / pote ───────────────────────────────────────────
    @staticmethod
    def _perfil_de(row) -> dict:
        if row is None:
            return {"apostado": 0, "partidas": 0, "vitorias": 0, "maior_premio": 0, "melhor_mult": 0.0,
                    "sequencia": 0, "melhor_sequencia": 0, "jackpots": 0, "conquistas": []}
        d = dict(row)
        c = d.get("conquistas")
        d["conquistas"] = json.loads(c) if isinstance(c, str) else list(c or [])
        return d

    async def perfil(self, uid: int) -> dict:
        row = await self.pool.fetchrow("SELECT * FROM cassino_perfil WHERE user_id=$1", uid)
        return self._perfil_de(row)

    async def pote_atual(self) -> int:
        return int(await self.pool.fetchval("SELECT valor FROM cassino_pote WHERE id=1") or POTE_INICIAL)

    async def _registrar_perfil(self, uid: int, ctx: dict) -> tuple[dict, list[str]]:
        """Atualiza progressão; retorna (perfil novo, conquistas novas)."""
        premio, aposta = ctx["premio"], ctx["aposta"]
        venceu = premio > aposta
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("INSERT INTO cassino_perfil (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", uid)
                p = self._perfil_de(await conn.fetchrow("SELECT * FROM cassino_perfil WHERE user_id=$1 FOR UPDATE", uid))
                p["apostado"] += aposta
                p["partidas"] += 1
                p["vitorias"] += 1 if venceu else 0
                p["maior_premio"] = max(p["maior_premio"], premio)
                p["melhor_mult"] = max(p["melhor_mult"], ctx["mult"])
                p["sequencia"] = p["sequencia"] + 1 if venceu else 0
                p["melhor_sequencia"] = max(p["melhor_sequencia"], p["sequencia"])
                p["jackpots"] += 1 if ctx["jackpot"] else 0
                novas = conquistas_novas(p, ctx)
                p["conquistas"] = p["conquistas"] + novas
                await conn.execute(
                    "UPDATE cassino_perfil SET apostado=$2, partidas=$3, vitorias=$4, maior_premio=$5, melhor_mult=$6, "
                    "sequencia=$7, melhor_sequencia=$8, jackpots=$9, conquistas=$10::jsonb WHERE user_id=$1",
                    uid, p["apostado"], p["partidas"], p["vitorias"], p["maior_premio"], p["melhor_mult"],
                    p["sequencia"], p["melhor_sequencia"], p["jackpots"], json.dumps(p["conquistas"]),
                )
        return p, novas

    async def _finalizar(self, uid, guild_id, numero, jogo, escolha, sorteio, aposta, premio) -> int:
        escolha, sorteio = escolha[:60], sorteio[:60]
        try:
            return await partidas.finalizar_partida_cassino(uid, guild_id, numero, jogo, escolha, sorteio, aposta, premio)
        except asyncpg.exceptions.CheckViolationError:
            if jogo in JOGOS_LEGADO:
                raise
            # O banco antigo só aceitava os 4 jogos originais: registra como "kingdice".
            if not self.fallback_avisado:
                LOG.warning("Banco recusou o jogo %r; registrando como 'kingdice'. Ajuste o CHECK de 'jogo' em cassino_partidas.", jogo)
                self.fallback_avisado = True
            return await partidas.finalizar_partida_cassino(uid, guild_id, numero, "kingdice", escolha, sorteio, aposta, premio)

    # ── Painel: ações ───────────────────────────────────────────
    async def abrir_mesa(self, interaction: discord.Interaction, jogo: str):
        if jogo == "contratos":
            return await self.mostrar_contratos(interaction)
        if jogo == "cartas":
            return await self.mostrar_cartas(interaction)
        if jogo not in NOMES_JOGOS:
            return await interaction.response.send_message("❌ Mesa indisponível.", ephemeral=True)
        perfil = await self.perfil(interaction.user.id)
        limite = limite_de(perfil["apostado"])
        if jogo == "slots":
            return await interaction.response.send_modal(ApostaModal(self, "slots", "girar", limite))
        descricao = {
            "cara": "Cara ou coroa? Escolha o seu lado.",
            "dados": "Aposte em um número (5,85×) ou em alto, baixo, par ou ímpar (1,95×).",
            "roleta": "Cor, par/ímpar, dúzia ou número exato. Escolha a sua aposta.",
            "corrida": "Cada corredor tem as suas chances e o seu prêmio. Escolha o seu favorito!",
            "kingdice": f"Quanto mais andares, maior o prêmio — cada andar tem **{round(KD_CHANCE * 100)}%** de chance.",
        }[jogo]
        embed = base(f"# {NOMES_JOGOS[jogo]}\n{descricao}\n\n> `⭐` Sua aposta máxima: **{fmt(limite)}**", COR_SEPIA)
        await interaction.response.send_message(embed=embed, view=EscolhaView(self, jogo, limite), ephemeral=True)

    async def mostrar_carteira(self, interaction: discord.Interaction):
        saldo = await db.obter_saldo(interaction.user.id)
        await interaction.response.send_message(f"🪙 Sua carteira: **{fmt(saldo)}**", ephemeral=True)

    async def mostrar_pote(self, interaction: discord.Interaction):
        pote = await self.pote_atual()
        row = await self.pool.fetchrow("SELECT ultimo_vencedor, ultimo_valor, ultimo_ts FROM cassino_pote WHERE id=1")
        linhas = [
            "# 😈 **Pote do Diabo**",
            f"> `💰` Acumulado agora: **{fmt(pote)}**",
            f"> `🎰` Como ganhar: **😈😈😈** no Caça-Níquel — leva **{JACKPOT_BASE_MULT}× a aposta + o pote inteiro**.",
            f"> `📈` {round(POTE_PERCENTUAL * 100)}% de **todas** as apostas do cassino entram no pote.",
        ]
        if row and row["ultimo_vencedor"]:
            linhas.append(f"> `👑` Último vencedor: <@{row['ultimo_vencedor']}> — **{fmt(row['ultimo_valor'])}** (<t:{row['ultimo_ts']}:R>)")
        await interaction.response.send_message(embed=base("\n".join(linhas), COR_JACKPOT), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    async def mostrar_perfil(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        p = await self.perfil(uid)
        s = await partidas.estatisticas_cassino(uid)
        n = nivel_de(p["apostado"])
        proximo = NIVEIS[n + 1] if n + 1 < len(NIVEIS) else None
        if proximo:
            ant = NIVEIS[n][0]
            prog = f"`{barra(p['apostado'] - ant, proximo[0] - ant)}` {fmt(p['apostado'])} / {fmt(proximo[0])}"
            prox = f"\n> `🎯` Próximo nível: **{proximo[1]}** (aposta máxima {fmt(proximo[2])})"
        else:
            prog, prox = "`▰▰▰▰▰▰▰▰▰▰` **Nível máximo!**", ""
        linhas = [
            f"# 📊 **Perfil de {interaction.user.display_name}**",
            f"> `⭐` Nível **{n + 1}** — **{NIVEIS[n][1]}**",
            f"> {prog}{prox}",
            "",
            "**Histórico**",
            f"> `🎲` Partidas: **{s['partidas']}** • `✅` Vitórias: **{s['vitorias']}** • `❌` Derrotas: **{s['derrotas']}**",
            f"> `📈` Resultado líquido: **{fmt(s['lucro'])}**",
            f"> `🏆` Maior prêmio: **{fmt(p['maior_premio'])}** • `🔥` Melhor multiplicador: **{fmt_mult(p['melhor_mult']) if p['melhor_mult'] else '—'}**",
            f"> `⚡` Melhor sequência: **{p['melhor_sequencia']}** • `😈` Jackpots: **{p['jackpots']}**",
            f"> `🏅` Conquistas: **{len(p['conquistas'])}/{len(CONQUISTAS)}**",
        ]
        embed = base("\n".join(linhas), COR_OURO)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def mostrar_conquistas(self, interaction: discord.Interaction):
        p = await self.perfil(interaction.user.id)
        linhas = ["# 🏅 **Conquistas**"]
        for chave, (emoji, nome, desc) in CONQUISTAS.items():
            ok = chave in p["conquistas"]
            linhas.append(f"> {'✅' if ok else '🔒'} {emoji} **{nome}** — {desc}")
        linhas.append(f"\n**{len(p['conquistas'])}/{len(CONQUISTAS)}** desbloqueadas.")
        await interaction.response.send_message(embed=base("\n".join(linhas), COR_OURO), ephemeral=True)

    async def mostrar_rankings(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        semanal = await partidas.ranking_cassino(10)
        hall = await self.pool.fetch(
            "SELECT user_id, maior_premio FROM cassino_perfil WHERE maior_premio > 0 ORDER BY maior_premio DESC LIMIT 5"
        )
        nivel = await self.pool.fetch(
            "SELECT user_id, apostado FROM cassino_perfil WHERE apostado > 0 ORDER BY apostado DESC LIMIT 5"
        )
        medalha = {1: "🥇", 2: "🥈", 3: "🥉"}
        def lista(linhas, f):
            return "\n".join(f"> {medalha.get(i, f'`{i}.`')} <@{r['user_id']}> — {f(r)}" for i, r in enumerate(linhas, 1)) or "> *Ninguém ainda.*"
        texto = (
            "# 🏆 **Rankings do Cassino**\n\n"
            f"**📈 Semanal — lucro líquido**\n{lista(semanal, lambda r: fmt(r['lucro']))}\n\n"
            f"**💎 Hall da Fama — maiores prêmios**\n{lista(hall, lambda r: fmt(r['maior_premio']))}\n\n"
            f"**⭐ Mais viciados — total apostado**\n{lista(nivel, lambda r: fmt(r['apostado']))}"
        )
        await interaction.followup.send(embed=base(texto, COR_OURO), ephemeral=True,
                                        allowed_mentions=discord.AllowedMentions.none())

    # ── Contratos e cartas (economia gerida pelo módulo extras) ──
    async def mostrar_contratos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dados = await extras.estado_contratos(interaction.user.id)
            embed = base(
                "# 📜 **Contratos do Diabo**\n"
                "**Missões do dia (UTC)**\n"
                f"> `🚪` Visitar o salão — **40 SC** {'✅' if dados['visita'] else '⏳'}\n"
                f"> `🃏` Revelar uma Carta do Destino — **60 SC** {'✅' if dados['carta'] else '⏳'}\n\n"
                "> `ℹ️` A recompensa de visita é obtida pelo botão abaixo.\n"
                "> `🔒` A missão da carta é creditada automaticamente ao revelar uma carta.\n"
                "> `🕛` Reinício diário às 00:00 UTC.",
                COR_SEPIA,
            )
            await interaction.followup.send(embed=embed, view=ContratoView(self), ephemeral=True)
        except Exception:
            LOG.exception("Falha ao consultar contratos")
            await interaction.followup.send("❌ Não foi possível consultar os contratos agora.", ephemeral=True)

    async def mostrar_cartas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dados = await extras.estado_contratos(interaction.user.id)
            if dados["carta"]:
                return await interaction.followup.send("🃏 Sua carta de hoje já foi revelada. Volte após 00:00 UTC.", ephemeral=True)
            embed = base(
                "# 🃏 **Cartas do Destino**\n"
                "**Três cartas. Um destino.**\n"
                "> `🂠` Escolha uma das cartas abaixo.\n"
                "> `🎁` Recompensas possíveis: 0, 25, 50 ou 100 SC.\n"
                "> `📜` A primeira carta do dia também conclui o contrato de **60 SC**.\n\n"
                "**Probabilidades por tentativa**\n"
                "> `40%` — 0 SC\n> `35%` — 25 SC\n> `20%` — 50 SC\n> `5%` — 100 SC\n\n"
                "*As três cartas têm as mesmas probabilidades. Uma tentativa por dia (UTC).*",
                COR_SEPIA,
            )
            await interaction.followup.send(embed=embed, view=CartasView(self), ephemeral=True)
        except Exception:
            LOG.exception("Falha ao abrir cartas")
            await interaction.followup.send("❌ Não foi possível abrir as cartas agora.", ephemeral=True)

    async def coletar_visita(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            ganho, saldo = await extras.coletar_visita(interaction.user.id)
            msg = (f"📜 Contrato concluído! **+40 SC**. Saldo: **{fmt(saldo)}**."
                   if ganho else "⌛ Você já concluiu o contrato de visita hoje.")
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            LOG.exception("Falha ao coletar visita")
            await interaction.followup.send("❌ Não foi possível concluir o contrato. Tente mais tarde.", ephemeral=True)

    async def revelar_carta(self, interaction: discord.Interaction, carta: int):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            r = await extras.revelar_carta(interaction.user.id, carta)
            if not r["novo"]:
                return await interaction.followup.send("🃏 Você já revelou uma carta hoje. Volte amanhã (UTC).", ephemeral=True)
            await interaction.followup.send(
                f"🃏 **Carta {carta} revelada!**\n"
                f"> Prêmio da carta: **{fmt(r['premio'])}**\n"
                f"> Contrato concluído: **+60 SC**\n"
                f"> Saldo atual: **{fmt(r['saldo'])}**",
                ephemeral=True,
            )
        except Exception:
            LOG.exception("Falha ao revelar carta")
            await interaction.followup.send("❌ Não foi possível confirmar sua carta. Consulte seu extrato antes de tentar novamente.", ephemeral=True)

    # ── Animações ───────────────────────────────────────────────
    def _quadros(self, jogo: str, r: Resultado) -> list[discord.Embed]:
        nome = NOMES_JOGOS[jogo]
        c = r.cena
        if jogo == "cara":
            return [embed_cena(f"🪙 {nome}", ["A moeda sobe, gira, gira...", "", "# 🪙 💫 🪙"]),
                    embed_cena(f"🪙 {nome}", ["Ela está caindo...", "", "# ✨ 🪙 ✨"])]
        if jogo == "dados":
            return [embed_cena(f"🎲 {nome}", ["O Rei sacode os dados...", "", f"# 🎲 {RNG.randint(1, 6)} 🎲"]),
                    embed_cena(f"🎲 {nome}", ["Rolando pela mesa...", "", f"# 🎲 {RNG.randint(1, 6)} 🎲"])]
        if jogo == "roleta":
            def giro():
                n = RNG.randint(0, 36)
                return f"# 🎡 {n} {cor_roleta(n)}"
            return [embed_cena(f"🎡 {nome}", ["Faça suas apostas... a bola foi lançada!", "", giro()]),
                    embed_cena(f"🎡 {nome}", ["A bola salta entre os números...", "", giro()]),
                    embed_cena(f"🎡 {nome}", ["Quase parando...", "", giro()])]
        if jogo == "slots":
            rolos = c["rolos"]
            fig = [s[0] for s in SIMBOLOS]
            def spin():
                return RNG.choice(fig)
            return [
                embed_cena(f"🎰 {nome}", ["Puxando a alavanca...", "", f"# [ {spin()} | {spin()} | {spin()} ]"]),
                embed_cena(f"🎰 {nome}", ["Os rolos giram...", "", f"# [ {rolos[0]} | {spin()} | {spin()} ]"]),
                embed_cena(f"🎰 {nome}", ["Quase lá...", "", f"# [ {rolos[0]} | {rolos[1]} | {spin()} ]"]),
            ]
        if jogo == "corrida":
            vencedor = c["vencedor"]
            quadros = []
            for passo in (3, 6, 8):
                linhas = ["Eles largaram! 🏁", ""]
                for i, (nome_c, emoji, _) in enumerate(CORREDORES):
                    pos = min(passo + (1 if i == vencedor else 0) + RNG.randint(-2, 0), 9) if i != vencedor else min(passo + 1, 9)
                    pos = max(pos, 0)
                    linhas.append(f"`{'·' * pos}`{emoji}`{'·' * (10 - pos)}` 🏁 {nome_c}")
                quadros.append(embed_cena(f"🏇 {nome}", linhas))
            return quadros
        # kingdice
        quadros = []
        passou = c["passou"]
        for i, ok in enumerate(passou):
            boss = KD_BOSSES[i] if c["andares"] <= 7 else "King Dice"
            trilha = " ".join(("✅" if j < i else "⚔️" if j == i else "▫️") for j in range(c["andares"]))
            quadros.append(embed_cena(f"👑 {nome}", [f"**Andar {i + 1}:** enfrentando **{boss}**...", "", f"# {trilha}"]))
            trilha2 = " ".join(("✅" if j < i or (j == i and ok) else "💀" if j == i else "▫️") for j in range(c["andares"]))
            quadros.append(embed_cena(f"👑 {nome}", [f"**{boss}** — " + ("derrotado! ✅" if ok else "você caiu! 💀"), "", f"# {trilha2}"]))
        return quadros[:6] if len(quadros) > 6 else quadros

    # ── Jogar ───────────────────────────────────────────────────
    def _parse_aposta(self, texto: str, saldo: int, limite: int) -> int | None:
        t = texto.strip().lower().replace(" ", "")
        if t in ("max", "tudo", "all"):
            return min(saldo, limite)
        mult = 1
        if t.endswith("k"):
            mult, t = 1_000, t[:-1]
        try:
            v = int(round(float(t.replace(",", ".")) * mult)) if mult > 1 else int(t.replace(".", "").replace(",", ""))
        except ValueError:
            return None
        return v

    async def jogar(self, interaction: discord.Interaction, jogo: str, aposta_txt: str, escolha: str, editar: bool = False):
        if editar:
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)

        async def erro(texto: str):
            await interaction.followup.send(texto, ephemeral=True)

        if interaction.guild is None:
            return await erro("❌ Jogue dentro do servidor.")
        if jogo not in NOMES_JOGOS or not escolha_valida(jogo, escolha):
            return await erro("❌ Escolha inválida.")

        uid = interaction.user.id
        perfil = await self.perfil(uid)
        nivel_antes = nivel_de(perfil["apostado"])
        limite = limite_de(perfil["apostado"])
        saldo_atual = await db.obter_saldo(uid)
        aposta = self._parse_aposta(aposta_txt, saldo_atual, limite)
        if aposta is None:
            return await erro("❌ Digite um valor numérico (ex.: 100, 1k ou max).")
        if not MIN_APOSTA <= aposta <= limite:
            dica = "" if limite >= 30_000 else " Jogue mais para subir de nível e aumentar o limite!"
            return await erro(f"❌ Aposte entre {fmt(MIN_APOSTA)} e {fmt(limite)}.{dica}")

        lock = self.locks.setdefault(uid, asyncio.Lock())
        if lock.locked():
            return await erro("⏳ Sua partida anterior ainda está sendo processada.")
        async with lock:
            if time.monotonic() - self.ultimo.get(uid, 0) < INTERVALO_SEG:
                return await erro(f"⏳ Aguarde {INTERVALO_SEG} segundos entre partidas.")
            self.ultimo[uid] = time.monotonic()

            numero = str(uuid.uuid4())
            bonus = evento_ativo()
            guarda_pote = self.lock_pote if jogo == "slots" else None
            if guarda_pote:
                await guarda_pote.acquire()
            try:
                pote = await self.pote_atual() if jogo == "slots" else 0
                r = resolver(jogo, escolha, pote)
                premio = int(aposta * r.mult) + r.extra
                if premio > 0 and bonus:
                    premio = int(premio * (1 + bonus["bonus"]))
                try:
                    saldo = await self._finalizar(uid, interaction.guild.id, numero, jogo, nome_escolha(jogo, escolha), r.sorteio, aposta, premio)
                except partidas.SaldoInsuficiente:
                    return await erro("❌ Saldo insuficiente para essa aposta.")
                except Exception:
                    LOG.exception("Falha ao registrar partida %s", numero)
                    return await erro("❌ Não foi possível confirmar a partida. Confira seu extrato antes de tentar novamente.")

                # Pote: jackpot zera o pote; senão cada aposta contribui
                try:
                    if r.jackpot:
                        await self.pool.execute(
                            "UPDATE cassino_pote SET valor=$1, ultimo_vencedor=$2, ultimo_valor=$3, ultimo_ts=$4 WHERE id=1",
                            POTE_INICIAL, uid, premio, int(time.time()),
                        )
                        pote_depois = POTE_INICIAL
                    else:
                        contribuicao = max(1, int(aposta * POTE_PERCENTUAL))
                        pote_depois = int(await self.pool.fetchval(
                            "UPDATE cassino_pote SET valor = valor + $1 WHERE id=1 RETURNING valor", contribuicao))
                except Exception:
                    LOG.exception("Falha ao atualizar o pote")
                    pote_depois = pote
            finally:
                if guarda_pote:
                    guarda_pote.release()

            # Progressão (melhor esforço: nunca atrapalha o pagamento)
            ctx = {"jogo": jogo, "escolha": escolha, "aposta": aposta, "premio": premio,
                   "mult": (premio / aposta) if aposta else 0, "jackpot": r.jackpot}
            try:
                perfil_novo, novas = await self._registrar_perfil(uid, ctx)
            except Exception:
                LOG.exception("Falha ao registrar perfil")
                perfil_novo, novas = {**perfil, "sequencia": 0}, []

            # Animação (o resultado já está gravado: abandonar a tela não muda nada)
            primeira = True

            async def mostrar(embed, view=None):
                nonlocal primeira
                if primeira and not editar:
                    kw = {"view": view} if view is not None else {}
                    await interaction.followup.send(embed=embed, ephemeral=True, **kw)
                else:
                    await interaction.edit_original_response(embed=embed, view=view)
                primeira = False

            try:
                for quadro in self._quadros(jogo, r):
                    await mostrar(quadro)
                    await asyncio.sleep(PAUSA_ANIMACAO)
            except discord.HTTPException:
                pass

            final = embed_resultado(
                NOMES_JOGOS[jogo], nome_escolha(jogo, escolha), r.sorteio, aposta, premio, saldo, numero,
                ctx["mult"], bonus, r.jackpot, perfil_novo, nivel_antes, novas, pote_depois,
            )
            limite_novo = limite_de(perfil_novo["apostado"])
            await mostrar(final, ResultadoView(self, uid, jogo, escolha, aposta, limite_novo))

            await self._anunciar(interaction, jogo, escolha, aposta, premio, ctx["mult"], r.jackpot, nome_escolha(jogo, escolha))

    async def _anunciar(self, interaction, jogo, escolha, aposta, premio, mult, jackpot, escolha_txt):
        if not CANAL_ANUNCIOS_ID or premio <= aposta:
            return
        if not (jackpot or premio >= LIMITE_ANUNCIO or mult >= LIMITE_ANUNCIO_MULT):
            return
        canal = interaction.guild.get_channel(CANAL_ANUNCIOS_ID)
        if canal is None:
            return
        titulo = "😈 JACKPOT DO DIABO!!!" if jackpot else "🏆 GRANDE VITÓRIA NO CASSINO!"
        texto = (
            f"# {titulo}\n"
            f"{interaction.user.mention} acabou de arrancar **{fmt(premio)}** do Diabo!\n\n"
            f"> `🎲` Mesa: **{NOMES_JOGOS[jogo]}**\n"
            f"> `🎯` Aposta: **{fmt(aposta)}** em **{escolha_txt}**\n"
            f"> `🔥` Multiplicador: **{fmt_mult(mult)}**\n\n"
            "*Quer tentar a sorte também? Vá até o painel do cassino!*"
        )
        embed = base(texto, COR_JACKPOT if jackpot else COR_OURO)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        try:
            await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ── Comandos ────────────────────────────────────────────────
    @commands.command(name="painelcassino")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def painel_cassino(self, ctx):
        await ctx.send(embed=painel_embed(), view=CassinoView(self), allowed_mentions=discord.AllowedMentions.none())
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name="pote")
    @commands.guild_only()
    async def pote_cmd(self, ctx):
        pote = await self.pote_atual()
        await ctx.reply(embed=base(f"# 😈 **Pote do Diabo**\n> `💰` Acumulado: **{fmt(pote)}**\n> `🎰` Ganhe com **😈😈😈** no Caça-Níquel!", COR_JACKPOT),
                        mention_author=False)

    @commands.command(name="cassino", aliases=["cara", "coroa", "dados", "roleta", "slots", "corrida"])
    @commands.guild_only()
    async def cassino_ajuda(self, ctx, *args):
        await ctx.reply("🎰 Utilize o **painel do cassino** para jogar com segurança e receber seu resultado privado.", mention_author=False)


async def setup(bot):
    await bot.add_cog(Cassino(bot))