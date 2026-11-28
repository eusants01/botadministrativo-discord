from __future__ import annotations

import asyncio
import json
import importlib
import logging
import secrets
import re
import unicodedata
from bisect import bisect_right
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord.ext import commands

LOG = logging.getLogger("sants.bot.lucky_block")

CANAL_PAINEL = 1572639152737091654
CANAL_REGISTROS = 1572355776377266176
CANAL_ESTOQUE = 1573584140719357972  
ID_DONO_DISCORD = 925863471902503033  # Proprietário; catálogo e entregas manuais
CARGOS_VALIDADORES = (1561231585993293864,)  
# ================== PERMISSÕES E NOTIFICAÇÕES ==================
# O proprietário sempre pode administrar. Cargos/usuários abaixo podem
# consultar e AUMENTAR o estoque; apenas o proprietário pode reduzi-lo.
CARGOS_ABASTECER_ESTOQUE = (1561231585993293864,)  # Ex.: (123456789012345678,)
USUARIOS_ABASTECER_ESTOQUE = ()

# Destinatários padrão (mantidos da versão anterior).
CARGOS_ALERTA_ESTOQUE = CARGOS_VALIDADORES
USUARIOS_ALERTA_ESTOQUE = (1371486864791572555,1243928690795221123,1455061586082533410)
# Personalize separadamente os dois tipos de alerta, se desejar.
CARGOS_ALERTA_ESTOQUE_BAIXO = CARGOS_ALERTA_ESTOQUE
USUARIOS_ALERTA_ESTOQUE_BAIXO = USUARIOS_ALERTA_ESTOQUE
CARGOS_ALERTA_ESTOQUE_ESGOTADO = CARGOS_ALERTA_ESTOQUE
USUARIOS_ALERTA_ESTOQUE_ESGOTADO = USUARIOS_ALERTA_ESTOQUE
AVISAR_DONO_ESTOQUE_BAIXO = True
AVISAR_DONO_ESTOQUE_ESGOTADO = True
# ===============================================================
ABERTURAS_POR_CICLO = 10
HORAS_APOS_ULTIMA_ABERTURA = 4
BANNER_PAINEL = "assets/lucky_block/painel.png"
BANNER_CAIXA_VAZIA = "caixa_vazia"
BANNER_REPOSICAO = "reposicao_estoque"  # assets/lucky_block/reposicao_estoque.png
BANNER_PREMIO_SECRETO = "recompensa_secreta"  # assets/lucky_block/recompensa_secreta.png
BANNER_ABERTURA = "abertura_misteriosa"
BANNER_REVELACAO = "abertura_revelacao"
BANNER_ANUNCIO_PREMIO = "recompensa_encontrada"
BANNERS_RARIDADE = {"rare": "revelacao_rara", "epic": "revelacao_epica",
                     "legendary": "revelacao_lendaria", "secret": "revelacao_secreta"}
ATIVAR_ABERTURA_CINEMATOGRAFICA = False
SEGUNDOS_SUSPENSE = 0.8
# Progressão exclusivamente cosmética; sem compras, trocas ou chances extras.
FRAGMENTOS_POR_CAIXA_VAZIA = 1
SELOS_FRAGMENTOS = ((25, "Centelha Royal"), (100, "Guardião Royal"), (300, "Legado Royal"))
# Para trocar as artes de uma temporada, informe os nomes alternativos aqui.
# Chaves são os nomes base dos banners. Vazio = usa as artes existentes.
BANNERS_TEMPORADA = {}  # Ex.: {"painel": "arcana/painel", "colecao": "arcana/colecao"}
# Desafio gratuito opcional: não interfere nas chances nem concede prêmio de valor.
DESAFIO_ATIVO = True
DESAFIO_ID = "natal_2026"
DESAFIO_TITULO = "Enigma da Estrela Royal"
DESAFIO_PERGUNTA = "Qual enfeite tradicional fica no topo da árvore de Natal?"
DESAFIO_OPCOES = ("Estrela", "Sino", "Guirlanda")
DESAFIO_RESPOSTA = 0  # Índice da alternativa correta, iniciando em 0.
TEMA_TEMPORADA = "Natalina"  # Alterável sem apagar histórico.
# Marcos coletivos desbloqueiam selos comemorativos exibidos no perfil mensal.
BANNER_COLECAO = "colecao"                        # colecao.png
BANNER_RANKING = "ranking"                        # ranking.png
BANNER_META = "meta_comunitaria"                 # meta_comunitaria.png
BANNER_RESGATES = "central_resgates"             # central_resgates.png
INTERVALO_REENVIO_AVISOS = 60  # segundos; não afeta a abertura
LOTE_REENVIO_AVISOS = 20
META_COMUNITARIA_MENSAL = 300  # Meta apenas comemorativa: não dá prêmios automaticamente.
MARCOS_COMUNIDADE = ((50, "Primeira centelha"), (150, "Energia da Família"), (300, "Legado ROYAL"))
LIMIAR_ALERTA_ESTOQUE = 1  # Alertar a equipe ao chegar a 1 unidade e ao zerar.
EXIGIR_APROVACAO_ENTREGA_MANUAL = True  # Para prêmios de entrega manual.
AVISAR_EVERYONE_SECRETOS = True
CONCEDER_CARGOS_AUTOMATICAMENTE = True
PREMIACOES = {

    # --------------------------------------------------------
    # 01 - CANDIDATO EM UMA DIVISAO
    # RARIDADE: EPICA | CHANCE: 0.013%
    # --------------------------------------------------------

    "candidato_divisao": dict(
        nome="Candidato em uma divisão",
        raridade="epic",
        chance="0.013",
        estoque=2,
        cargo_id=0,
        banner="candidato_divisao",
        ativo=True,
        descricao="Candidatura em divisão do E.B; requisitos sujeitos à validação da equipe.",
    ),

    # --------------------------------------------------------
    # 02 - FRUTA PERMANENTE
    # RARIDADE: LENDARIA | CHANCE: 0.010%
    # --------------------------------------------------------

    "fruta_permanente": dict(
        nome="Fruta Permanente",
        raridade="legendary",
        chance="0.010",
        estoque=1,
        cargo_id=0,
        banner="fruta_permanente",
        ativo=True,
        descricao="Fruta Permanente aleatória no Blox Fruit.",
    ),

    # --------------------------------------------------------
    # 03 - CANDIDATO CIGS
    # RARIDADE: LENDARIA | CHANCE: 0.030%
    # --------------------------------------------------------

    "Candidato_CIGS": dict(
        nome="Candidato CIGS",
        raridade="legendary",
        chance="0.030",
        estoque=1,
        cargo_id=0,
        banner="Candidato_CIGS",
        ativo=True,
        descricao="Candidato CIGS no E.B.",
    ),

    # --------------------------------------------------------
    # 04 - MINERIO ALEATORIO
    # RARIDADE: LENDARIA | CHANCE: 0.040%
    # --------------------------------------------------------

    "Minerio_aleatório": dict(
        nome="Minério Aleatório",
        raridade="legendary",
        chance="0.040",
        estoque=1,
        cargo_id=0,
        banner="Minerio_aleatório",
        ativo=True,
        descricao="Minério aleatório no servidor do E.B",
    ),

    # --------------------------------------------------------
    # 05 - DISCORD NITRO BASICO
    # RARIDADE: SECRETA | CHANCE: 0.008%
    # --------------------------------------------------------

    "nitro_basico": dict(
        nome="Discord Nitro Básico",
        raridade="secret",
        chance="0.008",
        estoque=1,
        cargo_id=0,
        banner="nitro_basico",
        ativo=True,
        descricao="Nitro Básico; resgate sujeito à elegibilidade e disponibilidade.",
    ),

    # --------------------------------------------------------
    # 06 - DISCORD NITRO NORMAL
    # RARIDADE: SECRETA | CHANCE: 0.003%
    # --------------------------------------------------------

    "nitro_normal": dict(
        nome="Discord Nitro Normal",
        raridade="secret",
        chance="0.003",
        estoque=1,
        cargo_id=0,
        banner="nitro_normal",
        ativo=True,
        descricao="Nitro Normal; resgate sujeito à elegibilidade e disponibilidade.",
    ),

    # --------------------------------------------------------
    # 07 - 500 ROBUX
    # RARIDADE: SECRETA | CHANCE: 0.001%
    # --------------------------------------------------------

    "500_robux": dict(
        nome="500 Robux",
        raridade="secret",
        chance="0.001",
        estoque=1,
        cargo_id=0,
        banner="500_robux",
        ativo=True,
        descricao="500 Robux; a forma de entrega será acertada no ticket.",
    ),

    # --------------------------------------------------------
    # 08 - CLOVER
    # RARIDADE: RARA | CHANCE: 5.00%
    # --------------------------------------------------------

    "clover": dict(
        nome="Clover",
        raridade="rare",
        chance="5.00",
        estoque=1,
        cargo_id=1572848152548085871,
        banner="clover",
        ativo=True,
        descricao="Cargo exclusivo Clover da Família ROYAL.",
    ),

    # --------------------------------------------------------
        # 09 - Salve da Kananda
        # RARIDADE: RARA | CHANCE: 10.00%
        # --------------------------------------------------------
    
        "salve_kananda": dict(
            nome="Salve da Kananda",
            raridade="rare",
            chance="10.00",
            estoque=1,
            cargo_id=0,
            banner="salve_kananda",
            ativo=True,
            descricao="Um presente especial da Kananda.",
        ),

    # --------------------------------------------------------
    # 10 - DEMON NIGHT
    # RARIDADE: EPICA | CHANCE: 1.00%
    # --------------------------------------------------------

    "demon_night": dict(
        nome="Demon Night",
        raridade="epic",
        chance="1.00",
        estoque=1,
        cargo_id=1569948996573597726,
        banner="demon_night",
        ativo=True,
        descricao="Cargo exclusivo Demon Night da Família ROYAL.",
    ),

    # --------------------------------------------------------
        # 11 - 10x Keys Aleatórias Steam
        # RARIDADE: SECRETA | CHANCE: 0.005%
        # --------------------------------------------------------
    
        "keys_aleatorias_steam": dict(
            nome="10x Keys Aleatórias Steam",
            raridade="secret",
            chance="0.005",
            estoque=1,
            cargo_id=0,
            banner="keys_aleatorias_steam",
            ativo=True,
            descricao="10 keys aleatórias Steam; a forma de entrega será acertada no ticket.",
        ),

        # --------------------------------------------------------
            # 12 - Vaga na Família
            # RARIDADE: SECRETA | CHANCE: 0.001%
            # --------------------------------------------------------
        
            "Vaga na Família": dict(
                nome="Vaga na Família",
                raridade="secret",
                chance="0.001",
                estoque=1,
                cargo_id=0,
                banner="vaga_na_familia",
                ativo=True,
                descricao="Vaga na Família ROYAL: A forma de entrega será acertada no ticket."
            ),

    # --------------------------------------------------------
    # 13 - DECORACAO DE PERFIL
    # RARIDADE: LENDARIA | CHANCE: 0.040%
    # --------------------------------------------------------

    "decoracao_perfil": dict(
        nome="Decoração de Perfil Aleatória (Discord)",
        raridade="legendary",
        chance="0.040",
        estoque=1,
        cargo_id=0,
        banner="decoracao_perfil",
        ativo=True,
        descricao="Decoração de perfil aleatória.",
    ),

}

# Alias para comandos sem aspas; preserva a chave original no PostgreSQL.
_ALIASES_PREMIACOES = {"vaga_na_familia": "Vaga na Família"}
_TABELA_SORTEIO: tuple[tuple[int, ...], tuple[str, ...]] | None = None

TOTAL_SORTEIO = 10_000_000  # 0.00001% por bilhete
CORES = discord.Colour.from_rgb(91, 79, 187)
RARIDADES = {"empty": ("Caixa vazia", 0), "epic": ("Épica", 100),
             "legendary": ("Lendária", 1000), "secret": ("Secreta", 10000),
             "rare": ("Rara", 10)}
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
EXTENSOES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_BANNERS_AUSENTES_AVISADOS: set[str] = set()  # Evita repetir aviso em cada abertura.

for codigo, premio in PREMIACOES.items():
    premio["banner"] = premio.get("banner") or codigo


def cruzou_limiar(anterior: int, atual: int) -> bool:
    return anterior > atual and (atual == 0 or (0 < atual <= LIMIAR_ALERTA_ESTOQUE < anterior))


def agora() -> datetime:
    return datetime.now(timezone.utc)


def tickets_da_chance(valor: str, codigo: str) -> int:
    try:
        v = Decimal(str(valor)) * Decimal(100_000)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(f"Chance inválida em {codigo}") from exc
    if not v.is_finite() or v < 0 or v != v.to_integral_value() or v > TOTAL_SORTEIO:
        raise ValueError(f"Chance inválida em {codigo}; use múltiplos de 0.00001% entre 0 e 100%.")
    return int(v)


def validar_configuracao(catalogo=None):
    global _TABELA_SORTEIO
    origem = PREMIACOES if catalogo is None else catalogo
    for ids in (CARGOS_VALIDADORES, CARGOS_ABASTECER_ESTOQUE, USUARIOS_ABASTECER_ESTOQUE,
                CARGOS_ALERTA_ESTOQUE_BAIXO, USUARIOS_ALERTA_ESTOQUE_BAIXO,
                CARGOS_ALERTA_ESTOQUE_ESGOTADO, USUARIOS_ALERTA_ESTOQUE_ESGOTADO):
        if not isinstance(ids, (tuple, list, set, frozenset)) or any(not isinstance(i, int) or i <= 0 for i in ids):
            raise ValueError("IDs de cargos/usuários devem ser uma coleção de inteiros; use (ID,) para um único ID.")
    if not isinstance(LIMIAR_ALERTA_ESTOQUE,int) or LIMIAR_ALERTA_ESTOQUE < 0:
        raise ValueError("Limiar de estoque inválido")
    if not isinstance(FRAGMENTOS_POR_CAIXA_VAZIA,int) or FRAGMENTOS_POR_CAIXA_VAZIA < 0:
        raise ValueError("Fragmentos inválidos")
    if DESAFIO_ATIVO and (not 2 <= len(DESAFIO_OPCOES) <= 5 or not 0 <= DESAFIO_RESPOSTA < len(DESAFIO_OPCOES)):
        raise ValueError("Configuração de desafio inválida")
    total = 0
    if len({c.casefold() for c in origem}) != len(origem):
        raise ValueError("Códigos de prêmio duplicados")
    limites, codigos = [], []
    for codigo, premio in origem.items():
        # A chave histórica com espaços é aceita apenas por seu alias explícito.
        identificador = next((a for a, c in _ALIASES_PREMIACOES.items() if c == codigo), codigo)
        if not identificador.replace("_", "").isalnum() or len(codigo) > 60:
            raise ValueError(f"Código de premiação inválido: {codigo}")
        if not isinstance(premio.get('nome'), str) or not 1 <= len(premio['nome']) <= 100:
            raise ValueError(f"Nome inválido: {codigo}")
        if not isinstance(premio.get('descricao'), str) or len(premio['descricao']) > 500:
            raise ValueError(f"Descrição inválida: {codigo}")
        if not isinstance(premio.get('banner'), str) or len(premio['banner']) > 250:
            raise ValueError(f"Banner inválido: {codigo}")
        if premio["raridade"] not in RARIDADES or premio["raridade"] == "empty":
            raise ValueError(f"Raridade inválida: {codigo}")
        if not isinstance(premio["estoque"], int) or premio["estoque"] < 0:
            raise ValueError(f"Estoque inicial inválido: {codigo}")
        if not isinstance(premio["cargo_id"], int) or premio["cargo_id"] < 0:
            raise ValueError(f"Cargo inválido: {codigo}")
        if not isinstance(premio["ativo"], bool):
            raise ValueError(f"Campo ativo inválido: {codigo}")
        bilhetes = tickets_da_chance(premio["chance"], codigo)
        if premio["ativo"]:
            total += bilhetes
            limites.append(total)
            codigos.append(codigo)
    if total > TOTAL_SORTEIO:
        raise ValueError("As chances somadas excedem 100%")
    tabela = (tuple(limites), tuple(codigos))
    if catalogo is None:
        _TABELA_SORTEIO = tabela
    return tabela


def sortear_codigo() -> str | None:
    # As probabilidades são validadas e acumuladas uma vez por carregamento.
    if _TABELA_SORTEIO is None:
        validar_configuracao()
    limites, codigos = _TABELA_SORTEIO
    indice = bisect_right(limites, secrets.randbelow(TOTAL_SORTEIO))
    return codigos[indice] if indice < len(codigos) else None


def raridade_nome(raridade: str) -> str:
    return RARIDADES.get(raridade, ("Desconhecida", 0))[0]


def codigo_premiacao(valor: str) -> str:
    """Resolve letras maiúsculas/minúsculas sem alterar as chaves reais do catálogo."""
    entrada = valor.strip().casefold()
    if entrada in _ALIASES_PREMIACOES:
        return _ALIASES_PREMIACOES[entrada]
    return next((codigo for codigo in PREMIACOES if codigo.casefold() == entrada), valor.strip())


@lru_cache(maxsize=512)
def normalizar_nome_banner(nome: str) -> str:
    texto = unicodedata.normalize("NFKD", nome.casefold())
    return re.sub(r"[\W_]+", "", "".join(c for c in texto if not unicodedata.combining(c)))


def banner_arquivo(referencia: str) -> Path | str | None:
    if referencia:
        tema = BANNERS_TEMPORADA.get(Path(referencia).stem)
        if tema and tema != referencia:
            caminho = _banner_arquivo_original(tema)
            if caminho:
                return caminho
    return _banner_arquivo_original(referencia)


def _banner_arquivo_original(referencia: str) -> Path | str | None:
    if not referencia:
        return None
    if referencia.startswith("https://"):
        url = urlparse(referencia)
        return referencia if url.netloc else None
    rel = Path(referencia.replace("\\", "/").strip())
    if rel.is_absolute() or ".." in rel.parts or ":" in referencia:
        return None
    if rel.parts and rel.parts[0].lower() == "assets":
        rel = Path(*rel.parts[1:])
    if not rel.parts:
        return None
    bases = [PASTA_ASSETS / rel]
    if rel.parts[0].lower() != "lucky_block":
        bases.insert(0, PASTA_ASSETS / "lucky_block" / rel)
    else:
        bases.append(PASTA_ASSETS / rel.name)
    for base in bases:
        caminhos = [base] if base.suffix else [base.with_suffix(s) for s in EXTENSOES]
        for caminho in caminhos:
            if caminho.is_file() and caminho.resolve().is_relative_to(PASTA_ASSETS.resolve()):
                return caminho
        if base.parent.is_dir():
            alvo_normalizado = normalizar_nome_banner(base.stem)
            for arquivo in base.parent.iterdir():
                if (arquivo.is_file() and arquivo.suffix.casefold() in EXTENSOES
                    and normalizar_nome_banner(arquivo.stem) == alvo_normalizado
                    and (not base.suffix or arquivo.suffix.casefold() == base.suffix.casefold())
                    and arquivo.resolve().is_relative_to(PASTA_ASSETS.resolve())):
                    return arquivo
    if referencia not in _BANNERS_AUSENTES_AVISADOS:
        _BANNERS_AUSENTES_AVISADOS.add(referencia)
        LOG.warning("Banner não localizado em assets: %s", referencia)
    return None


def nome_anexo(caminho: Path) -> str:
    # Nome ASCII estável, idêntico no upload e na referência attachment://.
    return "lucky-banner" + caminho.suffix.lower()


def adicionar_banner(container: discord.ui.Container, ref: str) -> Path | None:
    caminho = banner_arquivo(ref)
    if caminho:
        galeria = discord.ui.MediaGallery()
        galeria.add_item(media=f"attachment://{nome_anexo(caminho)}" if isinstance(caminho, Path) else caminho,
                         description="Família ROYAL • Lucky Block")
        container.add_item(galeria)
    return caminho if isinstance(caminho, Path) else None


def anexo_envio(view: discord.ui.LayoutView) -> dict:
    caminho = getattr(view, "_lucky_banner", None)
    return {"file": discord.File(str(caminho), filename=nome_anexo(caminho))} if caminho else {}


def anexo_edicao(view: discord.ui.LayoutView) -> dict:
    caminho = getattr(view, "_lucky_banner", None)
    return {"attachments": [discord.File(str(caminho), filename=nome_anexo(caminho))]} if caminho else {"attachments": []}


def banner_disponivel(*referencias: str) -> str:
    return next((ref for ref in referencias if ref and banner_arquivo(ref)), "")


def banner_individual_premio(referencia: str, raridade: str) -> str:
    return banner_disponivel(referencia, BANNER_PREMIO_SECRETO if raridade == "secret" else "", BANNER_PAINEL)


def banner_anuncio_premio(raridade: str, banner_individual: str) -> str:
    """Prioriza a arte de secretos; usa arte individual ou painel se faltar."""
    return banner_disponivel(BANNER_PREMIO_SECRETO if raridade == "secret" else "",
                             BANNER_ANUNCIO_PREMIO, banner_individual, BANNER_PAINEL)


def remover_midia(view: discord.ui.LayoutView) -> None:
    for container in view.children:
        if isinstance(container, discord.ui.Container):
            for item in list(container.children):
                if isinstance(item, discord.ui.MediaGallery):
                    container.remove_item(item)
    view._lucky_banner = None


async def enviar_layout(enviar, view: discord.ui.LayoutView, **kwargs):
    """Uma falha definitiva de upload não deve impedir a entrega do texto/botão."""
    tem_midia = any(isinstance(item, discord.ui.MediaGallery)
                    for c in view.children if isinstance(c, discord.ui.Container) for item in c.children)
    anexo = {}
    try:
        anexo = anexo_envio(view)
        return await enviar(view=view, **kwargs, **anexo)
    except (OSError, discord.HTTPException) as exc:
        if not tem_midia or (isinstance(exc, discord.HTTPException) and exc.status not in (400, 403, 413)):
            raise
        LOG.warning("Falha definitiva ao enviar mídia Lucky Block; tentando sem banner: %s", exc)
        remover_midia(view)
    finally:
        if anexo.get("file"):
            anexo["file"].close()
    return await enviar(view=view, **kwargs)

def texto_anuncio_premio(usuario_id: int, nome: str, raridade: str, protocolo: str) -> str:
    """Conteúdo idêntico para anúncio verdadeiro e prévia visual."""
    return (f"`🏆` **Vencedor:** <@{usuario_id}>\n"
            f"`🎁` **Premiação:** {nome}\n"
            f"`💎` **Raridade:** {raridade_nome(raridade)}\n"
            f"`📜` **Registro:** `{protocolo}`\n"
            f"`🎟️` **Resgate:** comprovante disponível ao abrir o ticket do vencedor")


def cartao(titulo: str, conteudo: str, banner: str = "", *, teste=False, raridade=None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    paleta = {"rare": 0x36A56A, "epic": 0x9B59B6, "legendary": 0xE8AE35, "secret": 0xC0395B}
    cont = discord.ui.Container(accent_colour=paleta.get(raridade, CORES))
    view._lucky_banner = adicionar_banner(cont, banner)
    prefixo = "🧪 **SIMULAÇÃO — SEM VALIDADE PARA RESGATE**\n\n" if teste else ""
    cont.add_item(discord.ui.TextDisplay(f"{prefixo}## {titulo}\n{conteudo}"))
    view.add_item(cont)
    return view


def recibo(abertura: dict, membro_id: int, *, teste=False) -> str:
    """Comprovante vinculado ao vencedor; só o PostgreSQL confirma sua autenticidade."""
    id_ = abertura["id"]
    premio = abertura["premio"]
    data = abertura.get("created_at") or agora()
    registro = "TESTE-SEM-VALIDADE" if teste else f"LB-{id_:06d}"
    status_raw = str(abertura.get("status") or "pending")
    status = {
        "pending": "⏳ Aguardando validação/entrega",
        "delivered": "✅ Entregue",
        "TESTE": "🧪 Simulação, sem premiação real",
    }.get(status_raw, status_raw)
    data_validacao = abertura.get("validated_at")
    validador = abertura.get("validated_by")
    validacao = (f"> `✅` **Validação:** confirmada por <@{validador}> "
                f"em <t:{int(data_validacao.timestamp())}:f>\n"
                if data_validacao and validador else
                "> `⏳` **Validação:** ainda não realizada\n")
    return (
        "**☰ IDENTIFICAÇÃO DO GANHADOR**\n"
        f"> `👤` **Beneficiário:** <@{membro_id}>\n"
        f"> `🆔` **ID do Discord:** `{membro_id}`\n"
        f"> `📜` **Protocolo único:** `{registro}`\n"
        f"> `📅` **Data do sorteio:** <t:{int(data.timestamp())}:F>\n\n"
        "**☰ INFORMAÇÕES DA PREMIAÇÃO**\n"
        f"> `🎁` **Recompensa:** {premio['nome']}\n"
        f"> `💎` **Raridade:** {raridade_nome(premio['raridade'])}\n"
        f"> `📋` **Situação:** {status}\n"
        + validacao + (f"> `🔎` **Revisão pendente:** {discord.utils.escape_markdown(abertura['review_reason'][:180])}\n"
                      if abertura.get('review_reason') else '') + "\n"
        "**☰ AUTENTICIDADE E RESGATE**\n"
        "> `🛒` Este comprovante é **individual e intransferível**.\n"
        "> `🎟️` A entrega é conferida pela equipe neste ticket.\n"
        "> `✅` A equipe confere com `!luckyvalidar ID` e aprova com `!luckyaprovar ID`.\n"
        + ("\n-# 🧪 Documento demonstrativo; não gera direito a prêmio."
           if teste else "\n-# 👑 Família ROYAL • Registro oficial do Lucky Block")
    )


class AcaoPainel(discord.ui.Button):
    def __init__(self, acao: str, label: str, emoji: str, estilo: discord.ButtonStyle):
        super().__init__(label=label, emoji=emoji, style=estilo, custom_id=f"royal_lucky:v1:{acao}")
        self.acao = acao

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("LuckyBlockRoyal")
        if cog is None:
            return await interaction.response.send_message("Sistema indisponível no momento.", ephemeral=True)
        await cog.interagir(interaction, self.acao)


class PainelLucky(discord.ui.LayoutView):
    def __init__(self, *, teste=False):
        super().__init__(timeout=180 if teste else None)
        cont = discord.ui.Container(accent_colour=CORES)
        self._lucky_banner = adicionar_banner(cont, BANNER_PAINEL)
        aviso = "🧪 **PRÉVIA, SEM ABERTURAS REAIS**\n" if teste else ""
        cont.add_item(discord.ui.TextDisplay(
            aviso + "## <:luckblock:1572868783725609083> LUCKY BLOCKS - FAMÍLIA ROYAL\n\n"
            f"**☰ TEMPORADA {TEMA_TEMPORADA.upper()}**\n"
            "Descubra recompensas, reúna selos e acompanhe sua coleção. "
            f"Você possui **{ABERTURAS_POR_CICLO} aberturas** ao terminar todas, novas tentativas "
            f"ficam disponíveis **{HORAS_APOS_ULTIMA_ABERTURA} horas depois da última abertura**.\n\n"
            "### Exemplos de premiações (sujeitas à disponibilidade)\n"
            "> ☰ `💜` Discord Nitro\n"
            "> ☰ `🍊` Fruta Permanente Aleatória\n"
            "> ☰ `🎨` Decoração de Perfil\n"
            "> ☰ `🐆` Candidato do CIGS\n"
            "> ☰ `💖` Salve da Kananda\n"
            "> ☰ `🔑` 10x Keys Aleatórias Steam\n"
            "> ☰ `💎` Minério aleatório no EB.\n"
            "> ☰ `💸` 500 Robux\n"
            "### Observações\n"
            "> ☰ `💎` Caixas sem prêmio concedem fragmentos cosméticos.\n"
            "> ☰ `📦` Estoque indisponível não aumenta as chances dos demais prêmios.\n"
            "> ☰ `🛎️` Algumas chances são extremamente baixas.\n"
            "> ☰ `🛎️` Premiações têm estoque limitado, sujeito a reposição.\n"
            "> ☰ `🛎️` Os prêmios não podem ser transferidos para outro usuário.\n"
            "> ☰ `🛒` Ganhos exigem resgate via ticket e comprovante individual."
        ))
        cont.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        linha = discord.ui.ActionRow()
        linha.add_item(AcaoPainel("abrir", "Abrir", "<:luckblock:1572868783725609083>", discord.ButtonStyle.success))
        linha.add_item(AcaoPainel("historico", "Histórico", "📜", discord.ButtonStyle.secondary))
        linha.add_item(AcaoPainel("ranking", "Ranking", "<:versustrophy:1564669597440016485>", discord.ButtonStyle.secondary))
        linha.add_item(AcaoPainel("colecao", "Coleção", "<a:Presenteghost:1553872045492797550>", discord.ButtonStyle.secondary))
        linha.add_item(AcaoPainel("meta", "Meta", "<a:luck:1575023399833567272>", discord.ButtonStyle.secondary))
        linha2 = discord.ui.ActionRow()
        linha2.add_item(AcaoPainel("perfil", "Meu progresso", "<a:Sg21_Tree:1576120735192318213>", discord.ButtonStyle.secondary))
        linha2.add_item(AcaoPainel("album", "Álbum", "<:wreath:1570688836776755200>", discord.ButtonStyle.secondary))
        linha2.add_item(AcaoPainel("participacao", "Participação", "<a:Sg21_Sparkles:1576120732419891251>", discord.ButtonStyle.secondary))
        linha2.add_item(AcaoPainel("marcos", "Meus marcos", "🎯", discord.ButtonStyle.secondary))
        if DESAFIO_ATIVO:
            linha2.add_item(AcaoPainel("desafio", "Desafio", "<a:trofeu_topdesigner:1576120729546526841>", discord.ButtonStyle.secondary))
        if teste:
            for botao in (*linha.children, *linha2.children):
                botao.disabled = True
        cont.add_item(linha)
        cont.add_item(linha2)
        self.add_item(cont)


class BotaoTicket(discord.ui.DynamicItem[discord.ui.Button],
                  template=r"royal_lucky:resgate:(?P<guild>[0-9]+):(?P<id>[0-9]+)"):
    def __init__(self, guild_id: int, premio_id: int):
        self.guild_id = guild_id
        self.premio_id = premio_id
        super().__init__(discord.ui.Button(label="Solicitar", emoji="<:christmascard:1570666450161639464>",
            style=discord.ButtonStyle.success,
            custom_id=f"royal_lucky:resgate:{guild_id}:{premio_id}"))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(int(match["guild"]), int(match["id"]))

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("LuckyBlockRoyal")
        if cog is None:
            return await interaction.response.send_message("❌ Resgate indisponível.", ephemeral=True)
        await cog.abrir_ticket_premio(interaction, self.guild_id, self.premio_id)


def mensagem_premio(guild_id: int, abertura: dict, *, teste=False,
                   visual_real=False) -> discord.ui.LayoutView:
    """DM de prêmio com etapas de resgate e botão individual de ticket."""
    premio = abertura["premio"]
    registro = "TESTE" if teste and not visual_real else f"LB-{abertura['id']:06d}"
    data = abertura.get("created_at") or agora()
    texto = (
        "Sua Lucky Block revelou uma recompensa especial! "
        "O prêmio foi registrado em seu nome.\n\n"
        "**☰ SUA CONQUISTA**\n"
        f"> `🎁` **Premiação:** {premio['nome']}\n"
        f"> `💎` **Raridade:** {raridade_nome(premio['raridade'])}\n"
        f"> `📜` **Protocolo:** `{registro}`\n"
        f"> `📅` **Conquista:** <t:{int(data.timestamp())}:F>\n\n"
        "**☰ COMO RESGATAR**\n"
        "> `1.` Clique no botão **Solicitar** abaixo.\n"
        "> `2.` Seu comprovante exclusivo será enviado ao ticket.\n"
        "> `3.` Aguarde a validação ou confirmação da equipe.\n\n"
        "**☰ OBSERVAÇÕES**\n"
        f"> `🏆` {premio['descricao']}\n"
        "> `🗃️` A recompensa é **individual e intransferível**.\n"
        "> `🧾` Guarde o protocolo para acompanhamento."
    )
    view = discord.ui.LayoutView(timeout=180 if teste else None)
    cont = discord.ui.Container(accent_colour=CORES)
    view._lucky_banner = adicionar_banner(cont, banner_individual_premio(premio["banner"], premio["raridade"]))
    cont.add_item(discord.ui.TextDisplay(
        ("🧪 **TESTE — SEM PRÊMIO REAL OU DIREITO A RESGATE**\n\n" if teste and not visual_real else "")
        + "## <a:Presenteghost:1553872045492797550> VOCÊ GANHOU NO LUCKY BLOCK!\n\n" + texto
    ))
    cont.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    linha = discord.ui.ActionRow()
    if teste:
        linha.add_item(discord.ui.Button(label=("Solicitar" if visual_real
                                             else "Abrir ticket (simulação)"), emoji="<:christmascard:1570666450161639464>",
                                         style=discord.ButtonStyle.secondary, disabled=True))
    else:
        linha.add_item(BotaoTicket(guild_id, abertura["id"]))
    cont.add_item(linha)
    view.add_item(cont)
    return view


def cartao_reposicao(codigo: str, anterior: int, atual: int, *, teste=False) -> discord.ui.LayoutView:
    """Anuncia o prêmio efetivamente reabastecido e suas quantidades."""
    premio = PREMIACOES[codigo]
    adicionadas = atual - anterior
    conteudo = (
        "As Lucky Blocks da Família ROYAL receberam **novas unidades de premiações**!\n\n"
        "**☰ INFORMAÇÕES DA REPOSIÇÃO**\n"
        f"> `🎁` **Recompensa:** {premio['nome']}\n"
        f"> `💎` **Raridade:** {raridade_nome(premio['raridade'])}\n"
        f"> `📦` **Unidades adicionadas:** +{adicionadas}\n"
        f"> `📊` **Estoque disponível:** {anterior} → **{atual}**\n"
        f"> `🎯` **Onde participar:** <#{CANAL_PAINEL}>\n"
        f"> `🎟️` **Tentativas:** {ABERTURAS_POR_CICLO} aberturas; após a última, renovação em {HORAS_APOS_ULTIMA_ABERTURA} horas.\n"
        "**☰ BOA SORTE!**\n"
        f"> `🍀` Sua próxima abertura pode guardar uma surpresa.\n"
        f"> `🎉` Participe e concorra a prêmios exclusivos da Família ROYAL."
    )
    return cartao("<:luckblock:1572868783725609083> NOVO ESTOQUE NO LUCKY BLOCK",
                  conteudo, banner_disponivel(BANNER_REPOSICAO, BANNER_PAINEL), teste=teste)


class ModalEstoque(discord.ui.Modal, title="Estoque • Lucky Block"):
    def __init__(self, guild_id: int, codigo: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.codigo = codigo
        self.quantidade = discord.ui.TextInput(
            label="Unidades disponíveis", placeholder="Exemplo: 2 (0 para esgotar)",
            min_length=1, max_length=6, required=True)
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("LuckyBlockRoyal")
        if cog is None or not await cog.pode_abastecer(interaction.user, self.guild_id):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        try:
            quantidade = int(str(self.quantidade.value).strip())
            if not 0 <= quantidade <= 100_000:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Informe um número de 0 a 100000.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            aviso = await cog.alterar_estoque(self.guild_id, self.codigo, quantidade, interaction.user.id)
            await interaction.followup.send(
                f"✅ `{self.codigo}`: **{quantidade}** unidade(s) disponíveis. "
                "O sorteio e as probabilidades não foram alterados. " + aviso, ephemeral=True)
        except ValueError as exc:
            await interaction.followup.send(f"❌ {exc}",ephemeral=True)
        except Exception:
            LOG.exception("Falha ao ajustar estoque %s", self.codigo)
            await interaction.followup.send("❌ Erro ao salvar estoque no PostgreSQL.", ephemeral=True)


class SeletorEstoque(discord.ui.Select):
    def __init__(self, guild_id: int, pagina=0):
        self.guild_id = guild_id
        opcoes = [discord.SelectOption(label=p["nome"][:95], value=c,
                    description=f"{raridade_nome(p['raridade'])} • {c}"[:100])
                  for c, p in list(PREMIACOES.items())[pagina*20:(pagina+1)*20]]
        super().__init__(placeholder="Selecione uma recompensa para editar o estoque",
                         min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("LuckyBlockRoyal")
        if cog is None or not await cog.pode_abastecer(interaction.user, self.guild_id):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        await interaction.response.send_modal(ModalEstoque(self.guild_id, self.values[0]))


class EstoquePagina(discord.ui.Button):
    def __init__(self,guild_id,pagina,label,disabled):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled)
        self.guild_id,self.pagina=guild_id,pagina

    async def callback(self, interaction):
        cog=interaction.client.get_cog('LuckyBlockRoyal')
        if not cog or not await cog.pode_abastecer(interaction.user,self.guild_id):
            return await interaction.response.send_message('❌ Sem permissão.',ephemeral=True)
        await interaction.response.defer(ephemeral=True,thinking=True)
        texto=await cog.resumo_estoques(self.guild_id,pagina=self.pagina)
        await enviar_layout(interaction.followup.send,PainelEstoque(self.guild_id,texto,self.pagina),ephemeral=True)


class PainelEstoque(discord.ui.LayoutView):
    def __init__(self, guild_id: int, texto: str, pagina=0):
        super().__init__(timeout=900)
        cont = discord.ui.Container(accent_colour=CORES)
        cont.add_item(discord.ui.TextDisplay("## <:luckblock:1572868783725609083> ESTOQUE PRIVADO — LUCKY BLOCK\n" + texto +
                    "\nSelecione uma premiação para definir a quantidade de unidades **disponíveis**. "
                    "O banco preserva a quantidade após reiniciar o bot. A equipe pode aumentar; apenas o dono pode reduzir."))
        linha = discord.ui.ActionRow()
        linha.add_item(SeletorEstoque(guild_id, pagina))
        cont.add_item(linha)
        navegacao = discord.ui.ActionRow()
        navegacao.add_item(EstoquePagina(guild_id, max(0,pagina-1), 'Anterior', pagina == 0))
        navegacao.add_item(EstoquePagina(guild_id, pagina+1, 'Próxima', (pagina+1)*20 >= len(PREMIACOES)))
        cont.add_item(navegacao)
        self.add_item(cont)


class BotaoDetalheResgate(discord.ui.Button):
    def __init__(self, guild_id: int, abertura_id: int, acao: str):
        self.guild_id = guild_id
        self.abertura_id = abertura_id
        self.acao = acao
        if acao == 'aprovar':
            super().__init__(label='Aprovar comprovante', emoji='✅', style=discord.ButtonStyle.success)
        else:
            super().__init__(label='Confirmar entrega', emoji='📦', style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog('LuckyBlockRoyal')
        if cog is None:
            return await interaction.response.send_message('❌ Sistema indisponível.', ephemeral=True)
        await cog.acao_resgate_painel(interaction, self.guild_id, self.abertura_id, self.acao)


class DetalheResgate(discord.ui.LayoutView):
    def __init__(self, guild_id: int, abertura_id: int, texto: str, dono: bool):
        super().__init__(timeout=600)
        cont = discord.ui.Container(accent_colour=CORES)
        self._lucky_banner = adicionar_banner(cont, BANNER_RESGATES)
        cont.add_item(discord.ui.TextDisplay('## 🎟️ ACOMPANHAMENTO DO RESGATE\n' + texto))
        linha = discord.ui.ActionRow()
        linha.add_item(BotaoDetalheResgate(guild_id, abertura_id, 'aprovar'))
        if dono:
            linha.add_item(BotaoDetalheResgate(guild_id, abertura_id, 'entregar'))
        cont.add_item(linha)
        self.add_item(cont)


class SeletorResgates(discord.ui.Select):
    def __init__(self, guild_id: int, rows):
        self.guild_id = guild_id
        opcoes = [discord.SelectOption(label=f"LB-{r['opening_id']:06d} • {(r['reward_name'] or r['reward_code'])[:70]}",
                     value=str(r['opening_id']), description=f"Ganhador: {r['user_id']}"[:95])
                  for r in rows]
        super().__init__(placeholder='Selecione um comprovante para consultar', options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog('LuckyBlockRoyal')
        if cog is None:
            return await interaction.response.send_message('❌ Sistema indisponível.', ephemeral=True)
        guild = cog.bot.get_guild(self.guild_id)
        if not guild or not await cog.pode_validar(interaction.user, guild):
            return await interaction.response.send_message('❌ Acesso restrito aos validadores.', ephemeral=True)
        abertura_id = int(self.values[0])
        row = await cog.bot.pool.fetchrow('SELECT * FROM lucky_wins WHERE guild_id=$1 AND opening_id=$2',
                                          self.guild_id, abertura_id)
        if not row:
            return await interaction.response.send_message('❌ Registro não encontrado.', ephemeral=True)
        estado = ('✅ Entregue' if row['status']=='delivered' else
                  ('🔎 Em revisão' if row['review_reason'] else
                   ('✅ Validado' if row['validated_at'] else '⏳ Aguardando validação')))
        texto = (f"> `📜` **Protocolo:** `LB-{abertura_id:06d}`\n"
                 f"> `👤` **Ganhador:** <@{row['user_id']}>\n"
                 f"> `🎁` **Recompensa:** {row['reward_name'] or row['reward_code']}\n"
                 f"> `📋` **Situação:** {estado}\n"
                 f"> `🎟️` **Ticket:** {f'<#{row["ticket_channel_id"]}>' if row['ticket_channel_id'] else 'Pendente'}\n\n"
                 f'`!luckyvalidar {abertura_id}` — Conferir autenticidade\n'
                 f'`!luckyaprovar {abertura_id}` — Aprovar formalmente\n'
                 f'`!luckyrevisar {abertura_id} motivo` — Anotar pendência\n'
                 + (f'`!luckyentregar {abertura_id}` — Confirmar entrega (dono)' if interaction.user.id==ID_DONO_DISCORD else
                    'A confirmação final de entrega é exclusiva do dono.'))
        view = DetalheResgate(self.guild_id, abertura_id, texto, interaction.user.id == ID_DONO_DISCORD)
        await interaction.response.send_message(view=view, ephemeral=True, **anexo_envio(view))


class PainelResgates(discord.ui.LayoutView):
    def __init__(self, guild_id: int, texto: str, rows):
        super().__init__(timeout=900)
        cont = discord.ui.Container(accent_colour=CORES)
        self._lucky_banner = adicionar_banner(cont, BANNER_RESGATES)
        cont.add_item(discord.ui.TextDisplay(
            '## 🛡️ CENTRAL DE RESGATES — ROYAL\n'
            + texto + '\n\n-# Validação não equivale à entrega. Estoque: proprietário e abastecedores autorizados.'))
        if rows:
            linha = discord.ui.ActionRow()
            linha.add_item(SeletorResgates(guild_id, rows))
            cont.add_item(linha)
        self.add_item(cont)


class AlbumSelect(discord.ui.Select):
    def __init__(self, guild_id, user_id, rows):
        self.guild_id, self.user_id = guild_id, user_id
        self.rows = {str(i): r for i,r in enumerate(rows)}
        super().__init__(placeholder="Selecione uma conquista descoberta", options=[
            discord.SelectOption(label=(r['nome'] or r['reward_code'])[:100], value=str(i),
                description=f"{raridade_nome(r['raridade'])} • {r['total']} conquista(s)"[:100])
            for i,r in enumerate(rows)])

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Álbum individual.", ephemeral=True)
        r = self.rows[self.values[0]]
        view = cartao("🏅 CONQUISTA DESCOBERTA", f"> `🎁` **{r['nome'] or r['reward_code']}**\n"
                      f"> `💎` **Raridade:** {raridade_nome(r['raridade'])}\n> `📜` **Registros:** {r['total']}",
                      banner_individual_premio(r['banner'] or '', r['raridade'] or 'legendary'), raridade=r['raridade'])
        await enviar_layout(interaction.response.send_message, view, ephemeral=True)


class AlbumPagina(discord.ui.Button):
    def __init__(self, guild_id, user_id, pagina, label, disabled=False):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled)
        self.guild_id, self.user_id, self.pagina = guild_id, user_id, pagina

    async def callback(self, interaction):
        cog = interaction.client.get_cog('LuckyBlockRoyal')
        if not cog or interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Álbum individual.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        await enviar_layout(interaction.followup.send, await cog.album(self.guild_id,self.user_id,self.pagina), ephemeral=True)


class AlbumRoyal(discord.ui.LayoutView):
    def __init__(self, guild_id, user_id, rows, pagina):
        super().__init__(timeout=180)
        c = discord.ui.Container(accent_colour=CORES)
        self._lucky_banner = adicionar_banner(c, BANNER_COLECAO)
        texto = '\n'.join(f"> `🎁` **{r['nome'] or r['reward_code']}** · {raridade_nome(r['raridade'])} · {r['total']}x" for r in rows)
        c.add_item(discord.ui.TextDisplay(f"## <:wreath:1570688836776755200> ÁLBUM ROYAL • Página {pagina+1}\n" + (texto or "Nenhuma conquista nesta página.") + "\n-# Somente recompensas que você encontrou são exibidas."))
        if rows:
            linha = discord.ui.ActionRow()
            linha.add_item(AlbumSelect(guild_id,user_id,rows))
            c.add_item(linha)
        linha = discord.ui.ActionRow()
        linha.add_item(AlbumPagina(guild_id,user_id,max(0,pagina-1),'Anterior',pagina==0))
        linha.add_item(AlbumPagina(guild_id,user_id,pagina+1,'Próxima',len(rows)<10))
        c.add_item(linha)
        self.add_item(c)


class CatalogoConfirmar(discord.ui.Button):
    def __init__(self, codigo, dados, anterior):
        super().__init__(label="Salvar alteração", emoji="✅", style=discord.ButtonStyle.success)
        self.codigo,self.dados,self.anterior=codigo,dados,anterior

    async def callback(self, interaction):
        cog=interaction.client.get_cog('LuckyBlockRoyal')
        if not cog or interaction.user.id != ID_DONO_DISCORD:
            return await interaction.response.send_message('❌ Exclusivo do proprietário.',ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await cog.salvar_catalogo(self.codigo,self.dados,self.anterior,interaction.user.id)
        except ValueError as exc:
            return await interaction.followup.send(f'❌ {exc}',ephemeral=True)
        except Exception:
            LOG.exception('Erro ao salvar catálogo')
            return await interaction.followup.send('❌ Não foi possível confirmar a alteração; consulte o diagnóstico.',ephemeral=True)
        self.disabled=True
        await interaction.followup.send('✅ Catálogo salvo no PostgreSQL. Estoques existentes não foram alterados.',ephemeral=True)


class CatalogoModal(discord.ui.Modal):
    def __init__(self, codigo=None, detalhes=False):
        super().__init__(title='Premiação • '+('Detalhes' if detalhes else 'Cadastro'),timeout=300)
        self.codigo,self.detalhes=codigo,detalhes
        self.anterior=dict(PREMIACOES[codigo]) if codigo else None
        dados=self.anterior or {}
        campos = ([('descricao','Descrição',dados.get('descricao',''),500),
                   ('cargo_id','ID do cargo (0 = manual)',str(dados.get('cargo_id',0)),20),
                   ('estoque','Estoque inicial (não repõe existente)',str(dados.get('estoque',0)),6),
                   ('ativo','Ativo? sim / não','sim' if dados.get('ativo') else 'não',5)] if detalhes else
                  [('nome','Nome',dados.get('nome',''),100),('raridade','rare / epic / legendary / secret',dados.get('raridade','rare'),20),
                   ('chance','Chance percentual (ex.: 0.01)',dados.get('chance','0'),20),
                   ('banner','Banner (nome ou URL HTTPS)',dados.get('banner',''),250)])
        if codigo is None:
            campos.insert(0,('codigo','Código único (ex.: premio_novo)','',60))
        self.campos={}
        for chave,label,valor,limite in campos:
            item=discord.ui.TextInput(label=label,default=str(valor),max_length=limite,
                required=chave not in ('banner','descricao'),style=discord.TextStyle.paragraph if chave=='descricao' else discord.TextStyle.short)
            self.campos[chave]=item
            self.add_item(item)

    async def on_submit(self, interaction):
        cog=interaction.client.get_cog('LuckyBlockRoyal')
        if not cog or interaction.user.id != ID_DONO_DISCORD:
            return await interaction.response.send_message('❌ Exclusivo do proprietário.',ephemeral=True)
        valores={k:str(v.value).strip() for k,v in self.campos.items()}
        codigo=self.codigo or valores.pop('codigo','').lower()
        dados=dict(self.anterior or dict(nome='',raridade='rare',chance='0',estoque=0,cargo_id=0,banner='',ativo=False,descricao='Nova recompensa.'))
        try:
            if self.codigo is None and (not re.fullmatch(r'[a-z0-9_]{1,60}',codigo) or codigo_premiacao(codigo) in PREMIACOES):
                raise ValueError('Código já existe ou é inválido. Use letras, números e sublinhado.')
            if self.detalhes:
                if valores['ativo'].casefold() not in ('sim','não','nao'):
                    raise ValueError('Informe sim ou não.')
                valores['ativo']=valores['ativo'].casefold()=='sim'
                for k in ('estoque','cargo_id'):
                    valores[k]=int(valores[k])
                if not 0 <= valores['estoque'] <= 100000 or not 0 <= valores['cargo_id'] < 2**63:
                    raise ValueError('Estoque ou ID inválido.')
            else:
                valores['raridade']=valores['raridade'].lower()
                valores['chance']=valores['chance'].replace(',','.')
                valores['banner']=valores['banner'] or codigo
            dados.update(valores)
            candidato=dict(PREMIACOES);candidato[codigo]=dados
            tabela=validar_configuracao(candidato)
            total=Decimal(tabela[0][-1] if tabela[0] else 0)/100000
        except (ValueError,TypeError) as exc:
            return await interaction.response.send_message(f'❌ {exc}',ephemeral=True)
        texto=(f"> `🎁` **{dados['nome']}** (`{codigo}`)\n> `💎` {raridade_nome(dados['raridade'])} • {dados['chance']}%\n"
               f"> `📦` Inicial: {dados['estoque']} • {'Ativo' if dados['ativo'] else 'Inativo'}\n"
               f"> `📊` **Soma ativa após salvar:** {total}%\n> `🖼️` Banner: `{dados['banner']}`\n"
               "-# Novos prêmios começam inativos; configure detalhes e estoque antes de ativar.")
        view=cartao('🛡️ CONFIRMAR ALTERAÇÃO',texto, banner_individual_premio(dados['banner'],dados['raridade']))
        linha=discord.ui.ActionRow();linha.add_item(CatalogoConfirmar(codigo,dados,self.anterior));view.children[0].add_item(linha)
        await enviar_layout(interaction.response.send_message,view,ephemeral=True)


class CatalogoAcao(discord.ui.Button):
    def __init__(self,codigo=None,detalhes=False):
        super().__init__(label='Adicionar prêmio' if codigo is None else ('Detalhes / ativação' if detalhes else 'Editar prêmio'),style=discord.ButtonStyle.primary)
        self.codigo,self.detalhes=codigo,detalhes

    async def callback(self,interaction):
        if interaction.user.id != ID_DONO_DISCORD:
            return await interaction.response.send_message('❌ Exclusivo do proprietário.',ephemeral=True)
        if self.codigo and self.codigo not in PREMIACOES:
            return await interaction.response.send_message('❌ Cadastro não encontrado.',ephemeral=True)
        await interaction.response.send_modal(CatalogoModal(self.codigo,self.detalhes))


class CatalogoSeletor(discord.ui.Select):
    def __init__(self,pagina):
        super().__init__(placeholder='Selecione uma premiação',options=[discord.SelectOption(
            label=p['nome'][:95],value=c,description=f"{raridade_nome(p['raridade'])} • {p['chance']}% • {'ativo' if p['ativo'] else 'inativo'}"[:100])
            for c,p in list(PREMIACOES.items())[pagina*20:(pagina+1)*20]])

    async def callback(self,interaction):
        if interaction.user.id != ID_DONO_DISCORD:
            return await interaction.response.send_message('❌ Exclusivo do proprietário.',ephemeral=True)
        codigo=self.values[0]
        if codigo not in PREMIACOES:
            return await interaction.response.send_message('❌ Cadastro não encontrado.',ephemeral=True)
        await enviar_layout(interaction.response.send_message,detalhe_catalogo(codigo),ephemeral=True)


def detalhe_catalogo(codigo):
    p=PREMIACOES[codigo]
    view=cartao('🎁 CONFIGURAR PREMIAÇÃO',f"> `🎁` **{p['nome']}** (`{codigo}`)\n> `💎` {raridade_nome(p['raridade'])} • {p['chance']}%\n"
        f"> `📦` Inicial: {p['estoque']} • {'Ativo' if p['ativo'] else 'Inativo'}\n> `🖼️` `{p['banner']}`\n"
        f"> `📜` {p['descricao']}\n-# Use o painel de estoque para ajustar unidades existentes.",p['banner'])
    linha=discord.ui.ActionRow();linha.add_item(CatalogoAcao(codigo));linha.add_item(CatalogoAcao(codigo,True));view.children[0].add_item(linha)
    return view


class CatalogoPagina(discord.ui.Button):
    def __init__(self,pagina,label,disabled):
        super().__init__(label=label,style=discord.ButtonStyle.secondary,disabled=disabled);self.pagina=pagina

    async def callback(self,interaction):
        if interaction.user.id != ID_DONO_DISCORD:
            return await interaction.response.send_message('❌ Exclusivo do proprietário.',ephemeral=True)
        await interaction.response.send_message(view=PainelCatalogo(self.pagina),ephemeral=True)


class PainelCatalogo(discord.ui.LayoutView):
    def __init__(self,pagina=0):
        super().__init__(timeout=900)
        c=discord.ui.Container(accent_colour=CORES)
        total=sum(Decimal(p['chance']) for p in PREMIACOES.values() if p['ativo'])
        c.add_item(discord.ui.TextDisplay(f'## 🛡️ CATÁLOGO PRIVADO — ROYAL\n> `📊` **Total ativo:** {total}%\n> `🎁` {len(PREMIACOES)} recompensas • Página {pagina+1}\n-# Alterações salvas pelo painel prevalecem sobre o Python.'))
        linha=discord.ui.ActionRow();linha.add_item(CatalogoSeletor(pagina));c.add_item(linha)
        linha=discord.ui.ActionRow();linha.add_item(CatalogoAcao());linha.add_item(CatalogoPagina(max(0,pagina-1),'Anterior',pagina==0));linha.add_item(CatalogoPagina(pagina+1,'Próxima',(pagina+1)*20>=len(PREMIACOES)));c.add_item(linha)
        self.add_item(c)


class RespostaDesafio(discord.ui.Button):
    def __init__(self,guild_id,user_id,indice):
        super().__init__(label=DESAFIO_OPCOES[indice][:80],style=discord.ButtonStyle.secondary)
        self.guild_id,self.user_id,self.indice,self.evento=guild_id,user_id,indice,DESAFIO_ID

    async def callback(self,interaction):
        cog=interaction.client.get_cog('LuckyBlockRoyal')
        if not cog or interaction.user.id != self.user_id or self.evento != DESAFIO_ID or not DESAFIO_ATIVO:
            return await interaction.response.send_message('❌ Desafio indisponível.',ephemeral=True)
        if self.indice != DESAFIO_RESPOSTA:
            return await interaction.response.send_message('Essa não é a resposta. Você pode tentar novamente, sem perder nada.',ephemeral=True)
        await interaction.response.defer(ephemeral=True,thinking=True)
        gravado=await cog.bot.pool.fetchval("""INSERT INTO lucky_challenges(guild_id,user_id,event_id,title)
            VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING event_id""",self.guild_id,self.user_id,self.evento,DESAFIO_TITULO)
        await interaction.followup.send('✅ Selo comemorativo desbloqueado no seu perfil!' if gravado else 'ℹ️ Você já concluiu este desafio.',ephemeral=True)


def painel_desafio(guild_id,user_id):
    view=cartao('🧩 '+DESAFIO_TITULO,DESAFIO_PERGUNTA+'\n-# Atividade opcional, gratuita e sem efeito nas probabilidades.',BANNER_META)
    linha=discord.ui.ActionRow()
    for i in range(len(DESAFIO_OPCOES)):
        linha.add_item(RespostaDesafio(guild_id,user_id,i))
    view.children[0].add_item(linha)
    return view


class LuckyBlockRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ticket_locks: dict[int, asyncio.Lock] = {}
        self._avisos_task: asyncio.Task | None = None
        self._guilds_inicializadas: set[int] = set()
        self._guild_init_locks: dict[int, asyncio.Lock] = {}
        self._catalog_lock = asyncio.Lock()

    async def cog_load(self):
        validar_configuracao()
        if getattr(self.bot, "pool", None) is None:
            raise RuntimeError("Lucky Block exige bot.pool (PostgreSQL)")
        pool = self.bot.pool
        async with pool.acquire() as con:
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_settings (
                guild_id BIGINT PRIMARY KEY, panel_message_id BIGINT,
                panel_banner_url TEXT, empty_banner_url TEXT)""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_reward_stock (
                guild_id BIGINT NOT NULL, code TEXT NOT NULL,
                stock_total INTEGER NOT NULL CHECK (stock_total >= 0),
                stock_available INTEGER NOT NULL CHECK (stock_available >= 0),
                PRIMARY KEY (guild_id, code))""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_users (
                guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
                next_open_at TIMESTAMPTZ NOT NULL, window_started_at TIMESTAMPTZ,
                opens_used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (guild_id, user_id))""")
            await con.execute("ALTER TABLE lucky_users ADD COLUMN IF NOT EXISTS window_started_at TIMESTAMPTZ")
            await con.execute("ALTER TABLE lucky_users ADD COLUMN IF NOT EXISTS opens_used INTEGER NOT NULL DEFAULT 0")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_openings (
                id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
                reward_code TEXT, rarity TEXT NOT NULL, reward_name TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            await con.execute("ALTER TABLE lucky_openings ADD COLUMN IF NOT EXISTS reward_name TEXT")
            await con.execute("""CREATE INDEX IF NOT EXISTS lucky_openings_user_idx
                ON lucky_openings(guild_id,user_id,created_at DESC)""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_wins (
                opening_id BIGINT PRIMARY KEY REFERENCES lucky_openings(id),
                guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
                reward_code TEXT NOT NULL, reward_name TEXT, reward_rarity TEXT,
                reward_banner_url TEXT, role_id BIGINT,
                status TEXT NOT NULL DEFAULT 'pending', public_message_id BIGINT,
                public_claimed_at TIMESTAMPTZ, delivered_by BIGINT,
                delivered_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            for coluna, tipo in (("reward_name", "TEXT"), ("reward_rarity", "TEXT"),
                ("reward_banner_url", "TEXT"), ("role_id", "BIGINT"),
                ("public_claimed_at", "TIMESTAMPTZ"), ("ticket_channel_id", "BIGINT"),
                ("dm_sent_at", "TIMESTAMPTZ"), ("ticket_claimed_at", "TIMESTAMPTZ")):
                await con.execute(f"ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
            # Aprovação formal não altera o status de entrega original.
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS validated_by BIGINT")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS review_reason TEXT")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS review_at TIMESTAMPTZ")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS review_by BIGINT")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_stock_audit (
                id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL,
                reward_code TEXT NOT NULL, actor_id BIGINT NOT NULL,
                before_stock INTEGER NOT NULL, after_stock INTEGER NOT NULL,
                change_reason TEXT NOT NULL, opening_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            await con.execute("""CREATE INDEX IF NOT EXISTS lucky_stock_audit_guild_idx
                ON lucky_stock_audit(guild_id, created_at DESC)""")
            # Apenas novos eventos entram automaticamente na fila; sem disparos históricos em massa.
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS public_pending BOOLEAN NOT NULL DEFAULT FALSE")
            await con.execute("ALTER TABLE lucky_stock_audit ADD COLUMN IF NOT EXISTS notice_pending BOOLEAN NOT NULL DEFAULT FALSE")
            await con.execute("ALTER TABLE lucky_stock_audit ADD COLUMN IF NOT EXISTS notice_claimed_at TIMESTAMPTZ")
            await con.execute("ALTER TABLE lucky_stock_audit ADD COLUMN IF NOT EXISTS notice_message_id BIGINT")
            # Índice para recuperação de resgates e histórico.
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_wins_guild_user_idx ON lucky_wins(guild_id,user_id)")
            # Índices para consultas frequentes de histórico, ranking e fila de avisos.
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_openings_user_id_idx ON lucky_openings(guild_id,user_id,id DESC)")
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_openings_guild_month_idx ON lucky_openings(guild_id,created_at)")
            await con.execute("""CREATE INDEX IF NOT EXISTS lucky_wins_pending_notice_idx
                ON lucky_wins(public_claimed_at NULLS FIRST,opening_id)
                WHERE public_pending AND public_message_id IS NULL""")
            await con.execute("""CREATE INDEX IF NOT EXISTS lucky_stock_pending_notice_idx
                ON lucky_stock_audit(notice_claimed_at NULLS FIRST,id)
                WHERE notice_pending AND notice_message_id IS NULL""")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS role_pending BOOLEAN NOT NULL DEFAULT FALSE")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS role_claimed_at TIMESTAMPTZ")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS public_refresh_pending BOOLEAN NOT NULL DEFAULT FALSE")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS reward_description TEXT")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS receipt_message_id BIGINT")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS receipt_claimed_at TIMESTAMPTZ")
            await con.execute("ALTER TABLE lucky_wins ADD COLUMN IF NOT EXISTS receipt_claim_channel BIGINT")
            await con.execute("ALTER TABLE lucky_stock_audit ADD COLUMN IF NOT EXISTS dm_pending BOOLEAN NOT NULL DEFAULT FALSE")
            await con.execute("ALTER TABLE lucky_stock_audit ADD COLUMN IF NOT EXISTS dm_claimed_at TIMESTAMPTZ")
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_stock_dm_pending_idx ON lucky_stock_audit(id) WHERE dm_pending")
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_role_pending_idx ON lucky_wins(opening_id) WHERE role_pending AND status='pending'")
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_refresh_pending_idx ON lucky_wins(opening_id) WHERE public_refresh_pending")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_stock_dm (
                audit_id BIGINT NOT NULL REFERENCES lucky_stock_audit(id), user_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY(audit_id,user_id))""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_fragments (
                guild_id BIGINT NOT NULL, user_id BIGINT NOT NULL, total BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY(guild_id,user_id))""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_challenges (
                guild_id BIGINT NOT NULL,user_id BIGINT NOT NULL,event_id TEXT NOT NULL,title TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(guild_id,user_id,event_id))""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_catalog_overrides (
                code TEXT PRIMARY KEY, data JSONB NOT NULL)""")
            await con.execute("""CREATE TABLE IF NOT EXISTS lucky_catalog_audit (
                id BIGSERIAL PRIMARY KEY, code TEXT NOT NULL, actor_id BIGINT NOT NULL,
                before_data JSONB, after_data JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            overrides = await con.fetch("SELECT code,data FROM lucky_catalog_overrides")
            candidato = dict(PREMIACOES)
            for item in overrides:
                candidato[item['code']] = json.loads(item['data']) if isinstance(item['data'], str) else dict(item['data'])
            validar_configuracao(candidato)
            PREMIACOES.clear()
            PREMIACOES.update(candidato)
            validar_configuracao()
        self.bot.add_view(PainelLucky())
        self.bot.add_dynamic_items(BotaoTicket)
        self._avisos_task = asyncio.create_task(self.reenviar_avisos())
        LOG.info("Lucky Block ROYAL carregado; %d recompensas e %d comandos por prefixo",
                 len(PREMIACOES), len(self.get_commands()))
        if not self.bot.intents.message_content:
            LOG.warning("Message Content Intent desativada no bot; comandos por prefixo em canais podem não funcionar.")

    async def cog_unload(self):
        if self._avisos_task is not None:
            self._avisos_task.cancel()
            try:
                await self._avisos_task
            except asyncio.CancelledError:
                pass
        self.bot.remove_dynamic_items(BotaoTicket)

    async def garantir_guild(self, guild_id: int):
        # Inicializa uma vez por servidor e por carregamento do cog, sem alterar estoques existentes.
        if guild_id in self._guilds_inicializadas:
            return
        lock = self._guild_init_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            if guild_id in self._guilds_inicializadas:
                return
            async with self._catalog_lock:
                codigos = list(PREMIACOES)
                quantidades = [PREMIACOES[c]["estoque"] for c in codigos]
                async with self.bot.pool.acquire() as con:
                    async with con.transaction():
                        await con.execute("INSERT INTO lucky_settings(guild_id) VALUES($1) ON CONFLICT DO NOTHING", guild_id)
                        await con.execute("""INSERT INTO lucky_reward_stock(guild_id,code,stock_total,stock_available)
                            SELECT $1, dados.code, dados.stock, dados.stock
                            FROM unnest($2::text[], $3::integer[]) AS dados(code, stock)
                            ON CONFLICT DO NOTHING""", guild_id, codigos, quantidades)
                # Marca como inicializado somente após o commit bem-sucedido.
                self._guilds_inicializadas.add(guild_id)

    async def salvar_catalogo(self,codigo,dados,anterior,actor_id):
        if actor_id != ID_DONO_DISCORD:
            raise ValueError('Exclusivo do proprietário.')
        async with self._catalog_lock:
            if PREMIACOES.get(codigo) != anterior:
                raise ValueError('O cadastro mudou desde a prévia. Abra o painel novamente.')
            candidato=dict(PREMIACOES);candidato[codigo]=dict(dados)
            tabela=validar_configuracao(candidato)
            async with self.bot.pool.acquire() as con:
                async with con.transaction():
                    await con.execute("""INSERT INTO lucky_catalog_overrides(code,data) VALUES($1,$2::jsonb)
                        ON CONFLICT(code) DO UPDATE SET data=EXCLUDED.data""",codigo,json.dumps(dados,ensure_ascii=False))
                    await con.execute("""INSERT INTO lucky_catalog_audit(code,actor_id,before_data,after_data)
                        VALUES($1,$2,$3::jsonb,$4::jsonb)""",codigo,actor_id,
                        json.dumps(anterior,ensure_ascii=False) if anterior else None,json.dumps(dados,ensure_ascii=False))
                    await con.execute("""INSERT INTO lucky_reward_stock(guild_id,code,stock_total,stock_available)
                        SELECT guild_id,$1,$2,$2 FROM lucky_settings ON CONFLICT DO NOTHING""",codigo,dados['estoque'])
            global _TABELA_SORTEIO
            PREMIACOES[codigo]=dict(dados)
            _TABELA_SORTEIO=tabela

    async def buscar_canal(self, guild: discord.Guild, canal_id: int) -> discord.TextChannel:
        canal = guild.get_channel(canal_id) or await self.bot.fetch_channel(canal_id)
        if not isinstance(canal, discord.TextChannel) or canal.guild.id != guild.id:
            raise ValueError(f"Canal {canal_id} não pertence a este servidor")
        return canal

    async def guild_oficial(self) -> discord.Guild:
        canal = self.bot.get_channel(CANAL_PAINEL)
        if canal is None:
            canal = await self.bot.fetch_channel(CANAL_PAINEL)
        if not isinstance(canal, discord.TextChannel):
            raise RuntimeError("Canal do painel não foi encontrado")
        guild = self.bot.get_guild(canal.guild.id)
        if guild is None:
            raise RuntimeError("Servidor da Família ROYAL não está acessível")
        return guild

    async def usuario_dono(self, usuario: discord.abc.User) -> bool:
        # Autorização estrita: nem administradores nem outros donos da aplicação têm acesso.
        return usuario.id == ID_DONO_DISCORD

    async def exigir_dono(self, ctx: commands.Context) -> bool:
        if await self.usuario_dono(ctx.author):
            return True
        await ctx.send("❌ Comando exclusivo do proprietário.", delete_after=8)
        return False

    async def pode_abastecer(self, usuario, guild_id: int) -> bool:
        if usuario.id == ID_DONO_DISCORD:
            return True
        guild = self.bot.get_guild(guild_id)
        if guild is None or guild.get_channel(CANAL_PAINEL) is None:
            return False
        membro = guild.get_member(usuario.id)
        if membro is None:
            try:
                membro = await guild.fetch_member(usuario.id)
            except discord.HTTPException:
                return False
        return (not membro.bot and (membro.id in USUARIOS_ABASTECER_ESTOQUE or
                any(c.id in CARGOS_ABASTECER_ESTOQUE for c in membro.roles)))

    async def exigir_abastecedor(self, ctx, guild) -> bool:
        if await self.pode_abastecer(ctx.author, guild.id):
            return True
        await ctx.send("❌ Sem autorização para abastecer estoque.", delete_after=8)
        return False

    async def pode_validar(self, usuario: discord.abc.User, guild: discord.Guild) -> bool:
        if usuario.id == ID_DONO_DISCORD:
            return True
        membro = guild.get_member(usuario.id)
        if membro is None:
            try:
                membro = await guild.fetch_member(usuario.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                membro = None
        return bool(membro and any(cargo.id in CARGOS_VALIDADORES for cargo in membro.roles))

    async def exigir_validador(self, ctx: commands.Context, guild: discord.Guild) -> bool:
        """Restringe conferência/aprovação ao dono ou a cargos configurados no servidor."""
        if await self.pode_validar(ctx.author, guild):
            return True
        await ctx.send("❌ Somente os cargos autorizados podem validar comprovantes.", delete_after=10)
        return False

    @staticmethod
    async def apagar_comando(ctx: commands.Context):
        if ctx.guild:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

    async def dm(self, ctx: commands.Context, *, texto="", view=None) -> bool:
        try:
            if view:
                await enviar_layout(ctx.author.send, view, allowed_mentions=discord.AllowedMentions.none())
            else:
                restante = texto
                while restante:
                    corte = len(restante) if len(restante) <= 1900 else restante.rfind('\n',0,1900)
                    if corte <= 0:
                        corte = 1900
                    await ctx.author.send(restante[:corte], allowed_mentions=discord.AllowedMentions.none())
                    restante = restante[corte:].lstrip('\n')
            return True
        except discord.HTTPException:
            LOG.exception("Não foi possível enviar DM ao dono")
            if ctx.guild:
                await ctx.send("❌ Habilite suas DMs ou verifique os arquivos de assets.", delete_after=10)
            return False

    async def obter_saldo(self, guild_id: int, usuario_id: int) -> tuple[int, datetime | None]:
        item = await self.bot.pool.fetchrow("""SELECT opens_used,next_open_at FROM lucky_users
            WHERE guild_id=$1 AND user_id=$2""", guild_id, usuario_id)
        if not item:
            return ABERTURAS_POR_CICLO, None
        usadas = item["opens_used"]
        if usadas >= ABERTURAS_POR_CICLO:
            if item["next_open_at"] > agora():
                return 0, item["next_open_at"]
            return ABERTURAS_POR_CICLO, None
        return max(0, ABERTURAS_POR_CICLO - usadas), None

    async def abrir(self, guild_id: int, usuario_id: int, cargos_usuario=()) -> dict:
        # Bloqueio por usuário + decremento condicional do estoque dentro da mesma transação.
        instante = agora()
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                await con.execute("""INSERT INTO lucky_users(guild_id,user_id,next_open_at,window_started_at,opens_used)
                    VALUES($1,$2,$3,NULL,0) ON CONFLICT DO NOTHING""", guild_id, usuario_id, instante)
                membro = await con.fetchrow("""SELECT opens_used,next_open_at,window_started_at
                    FROM lucky_users WHERE guild_id=$1 AND user_id=$2 FOR UPDATE""", guild_id, usuario_id)
                instante = agora()
                usadas = membro["opens_used"]
                if usadas >= ABERTURAS_POR_CICLO and membro["next_open_at"] > instante:
                    return {"limite": membro["next_open_at"]}
                if usadas >= ABERTURAS_POR_CICLO:
                    usadas = 0
                codigo = sortear_codigo()
                premio = PREMIACOES.get(codigo) if codigo else None
                sem_estoque = False
                cargo_repetido = bool(premio and premio['cargo_id'] and premio['cargo_id'] in cargos_usuario)
                if premio and premio['cargo_id'] and not cargo_repetido:
                    cargo_repetido = bool(await con.fetchval("""SELECT EXISTS(SELECT 1 FROM lucky_wins
                        WHERE guild_id=$1 AND user_id=$2 AND role_id=$3 AND status IN ('pending','delivered'))""",
                        guild_id, usuario_id, premio['cargo_id']))
                if cargo_repetido:
                    premio = None
                    codigo = None
                if premio is not None:
                    disponivel = await con.fetchval("""UPDATE lucky_reward_stock
                        SET stock_available=stock_available-1
                        WHERE guild_id=$1 AND code=$2 AND stock_available>0
                        RETURNING stock_available""", guild_id, codigo)
                    if disponivel is None:
                        sem_estoque = True
                        premio = None
                        codigo = None
                usadas += 1
                espera = instante + timedelta(hours=HORAS_APOS_ULTIMA_ABERTURA) if usadas == ABERTURAS_POR_CICLO else instante
                await con.execute("""UPDATE lucky_users SET opens_used=$3,next_open_at=$4,
                    window_started_at=$5 WHERE guild_id=$1 AND user_id=$2""",
                    guild_id, usuario_id, usadas, espera, instante if usadas == 1 else membro["window_started_at"])
                raridade = premio["raridade"] if premio else "empty"
                abertura_id = await con.fetchval("""INSERT INTO lucky_openings(guild_id,user_id,reward_code,rarity,reward_name)
                    VALUES($1,$2,$3,$4,$5) RETURNING id""",
                    guild_id, usuario_id, codigo, raridade, premio["nome"] if premio else None)
                if premio:
                    await con.execute("""INSERT INTO lucky_stock_audit
                        (guild_id,reward_code,actor_id,before_stock,after_stock,change_reason,opening_id,dm_pending)
                        VALUES($1,$2,$3,$4,$5,'premiacao',$6,$7)""",
                        guild_id, codigo, usuario_id, disponivel+1, disponivel, abertura_id,
                        cruzou_limiar(disponivel+1, disponivel))
                    await con.execute("""INSERT INTO lucky_wins(opening_id,guild_id,user_id,reward_code,
                        reward_name,reward_rarity,reward_banner_url,role_id,public_pending,reward_description,role_pending)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,TRUE,$9,$10)""",
                        abertura_id, guild_id, usuario_id, codigo, premio["nome"], raridade,
                        premio["banner"], premio["cargo_id"] or None, premio['descricao'],bool(CONCEDER_CARGOS_AUTOMATICAMENTE and premio['cargo_id']))
                else:
                    await con.execute("""INSERT INTO lucky_fragments(guild_id,user_id,total) VALUES($1,$2,$3)
                        ON CONFLICT(guild_id,user_id) DO UPDATE SET total=lucky_fragments.total+EXCLUDED.total""",
                        guild_id, usuario_id, FRAGMENTOS_POR_CAIXA_VAZIA)
                return {"id": abertura_id, "premio": premio, "codigo": codigo,
                        "raridade": raridade, "restantes": ABERTURAS_POR_CICLO-usadas,
                        "renovacao": espera if usadas == ABERTURAS_POR_CICLO else None,
                        "sem_estoque": sem_estoque, "cargo_repetido": cargo_repetido, "estoque_restante": disponivel if premio else None,
                        "created_at": instante}

    async def ajustar_cargo(self, guild: discord.Guild, membro: discord.Member, abertura: dict):
        if not CONCEDER_CARGOS_AUTOMATICAMENTE:
            return
        row=await self.bot.pool.fetchrow("""UPDATE lucky_wins SET role_claimed_at=NOW()
            WHERE guild_id=$1 AND opening_id=$2 AND user_id=$3 AND role_pending AND status='pending'
              AND review_reason IS NULL AND (role_claimed_at IS NULL OR role_claimed_at<NOW()-INTERVAL '5 minutes')
            RETURNING role_id""",guild.id,abertura['id'],membro.id)
        if not row:
            return
        cargo=guild.get_role(row['role_id'])
        if not cargo:
            LOG.warning('Cargo %s não localizado; entrega permanece pendente.',row['role_id'])
            return
        try:
            if cargo not in membro.roles:
                await membro.add_roles(cargo,reason=f"Lucky Block #{abertura['id']}")
            await self.bot.pool.execute("""UPDATE lucky_wins SET status='delivered',delivered_at=NOW(),delivered_by=$2,
                role_pending=FALSE,role_claimed_at=NULL,public_refresh_pending=TRUE
                WHERE opening_id=$1 AND status='pending'""",abertura['id'],self.bot.user.id)
        except discord.HTTPException:
            LOG.exception('Falha na entrega automática de cargo; nova tentativa futura.')

    async def avisar_dono_sem_estoque(self, guild, audit_id: int):
        row = await self.bot.pool.fetchrow("""UPDATE lucky_stock_audit SET dm_claimed_at=NOW()
            WHERE guild_id=$1 AND id=$2 AND dm_pending
              AND (dm_claimed_at IS NULL OR dm_claimed_at<NOW()-INTERVAL '5 minutes') RETURNING *""",
            guild.id, audit_id)
        if not row:
            return
        esgotado = row['after_stock'] == 0
        cargos = set(CARGOS_ALERTA_ESTOQUE_ESGOTADO if esgotado else CARGOS_ALERTA_ESTOQUE_BAIXO)
        usuarios = set(USUARIOS_ALERTA_ESTOQUE_ESGOTADO if esgotado else USUARIOS_ALERTA_ESTOQUE_BAIXO)
        if AVISAR_DONO_ESTOQUE_ESGOTADO if esgotado else AVISAR_DONO_ESTOQUE_BAIXO:
            usuarios.add(ID_DONO_DISCORD)
        if cargos:
            membros = guild.members
            usuarios.update(m.id for m in membros if not m.bot and any(c.id in cargos for c in m.roles))
            if self.bot.intents.members and not guild.chunked:
                try:
                    async for m in guild.fetch_members(limit=None):
                        if not m.bot and any(c.id in cargos for c in m.roles):
                            usuarios.add(m.id)
                except (discord.HTTPException,discord.ClientException):
                    LOG.warning('Não foi possível completar os membros por cargo; usando cache e IDs explícitos.',exc_info=True)
            elif not self.bot.intents.members:
                LOG.warning('Ative Server Members Intent para alertas completos por cargo.')
        async with self.bot.pool.acquire() as con:
            await con.executemany("""INSERT INTO lucky_stock_dm(audit_id,user_id) VALUES($1,$2)
                ON CONFLICT DO NOTHING""", [(audit_id, u) for u in usuarios])
        pendentes = await self.bot.pool.fetch("SELECT user_id FROM lucky_stock_dm WHERE audit_id=$1 AND status='pending'", audit_id)
        premio = PREMIACOES.get(row['reward_code'], {})
        texto = (f"> `🎁` **Premiação:** {premio.get('nome', row['reward_code'])}\n"
                 f"> `💎` **Raridade:** {raridade_nome(premio.get('raridade','empty'))}\n"
                 f"> `📉` **Estoque no evento:** {row['before_stock']} → {row['after_stock']}\n"
                 f"> `📜` **Movimento:** `EST-{audit_id}`\n"
                 f"> `📅` **Data:** <t:{int(row['created_at'].timestamp())}:F>\n"
                 "-# 👑 Família ROYAL • Alerta privado da equipe")
        for item in pendentes:
            uid = item['user_id']
            if uid not in usuarios:
                status = 'revoked'
            else:
                try:
                    usuario = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                    await usuario.send(view=cartao("📦 ESTOQUE ESGOTADO" if esgotado else "⚠️ ESTOQUE BAIXO", texto),
                                       allowed_mentions=discord.AllowedMentions.none())
                    status = 'sent'
                except (discord.Forbidden, discord.NotFound):
                    status = 'unavailable'
                    LOG.warning("DM indisponível para alerta %s / %s", audit_id, uid)
                except discord.HTTPException:
                    continue
            await self.bot.pool.execute("UPDATE lucky_stock_dm SET status=$3 WHERE audit_id=$1 AND user_id=$2", audit_id, uid, status)
            await self.bot.pool.execute("UPDATE lucky_stock_audit SET dm_claimed_at=NOW() WHERE id=$1",audit_id)
        await self.bot.pool.execute("""UPDATE lucky_stock_audit SET dm_pending=FALSE,dm_claimed_at=NULL
            WHERE id=$1 AND NOT EXISTS(SELECT 1 FROM lucky_stock_dm WHERE audit_id=$1 AND status='pending')""", audit_id)

    async def buscar_mensagem_registro(self, canal, protocolo, titulo, desde):
        # Reconciliação limitada ao histórico recente. Não confunde simulações nem mensagens de usuários.
        try:
            async for msg in canal.history(limit=150, after=desde-timedelta(seconds=2), oldest_first=False):
                if msg.author.id != self.bot.user.id:
                    continue
                textos=[]
                def coletar(item):
                    if getattr(item,'content',None):
                        textos.append(str(item.content))
                    for filho in getattr(item,'children',[]):
                        coletar(filho)
                    for filho in getattr(item,'components',[]):
                        coletar(filho)
                for item in msg.components:
                    coletar(item)
                corpo='\n'.join(textos)
                if titulo in corpo and f'`{protocolo}`' in corpo and 'SIMULAÇÃO' not in corpo:
                    return msg
        except discord.HTTPException:
            LOG.warning('Histórico indisponível para reconciliação: %s',protocolo)
        return None

    async def avisar_reposicao(self, guild_id: int, audit_id: int) -> bool:
        """Reserva uma notificação de estoque persistida junto da alteração real."""
        row = await self.bot.pool.fetchrow("""UPDATE lucky_stock_audit SET notice_claimed_at=NOW()
            WHERE id=$1 AND guild_id=$2 AND notice_pending AND notice_message_id IS NULL
              AND (notice_claimed_at IS NULL OR notice_claimed_at<NOW()-INTERVAL '5 minutes')
            RETURNING *""", audit_id, guild_id)
        if not row:
            return False
        try:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                raise RuntimeError(f"Servidor {guild_id} indisponível")
            canal = await self.buscar_canal(guild, CANAL_ESTOQUE)
            view = cartao_reposicao(row['reward_code'], row['before_stock'], row['after_stock'])
            view.children[0].add_item(discord.ui.TextDisplay(f"-# Movimento: `EST-{audit_id}`"))
            msg = None
            if (agora()-row['created_at']).total_seconds()>30:
                msg = await self.buscar_mensagem_registro(canal,f'EST-{audit_id}','NOVO ESTOQUE',row['created_at'])
            if msg is None:
                msg = await enviar_layout(canal.send, view, allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute("""UPDATE lucky_stock_audit SET notice_message_id=$2,
                notice_pending=FALSE,notice_claimed_at=NULL WHERE id=$1""", audit_id, msg.id)
            return True
        except Exception:
            # Mantém a reserva por 5 minutos, evitando rajadas em falhas de permissão/API.
            LOG.exception("Falha ao anunciar reposição #%s no canal %s; aguardando reenvio", audit_id, CANAL_ESTOQUE)
            return False

    async def reenviar_avisos(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                wins = await self.bot.pool.fetch("""SELECT guild_id,opening_id FROM lucky_wins
                    WHERE public_pending AND public_message_id IS NULL
                      AND (public_claimed_at IS NULL OR public_claimed_at<NOW()-INTERVAL '5 minutes')
                    ORDER BY public_claimed_at NULLS FIRST, opening_id LIMIT $1""", LOTE_REENVIO_AVISOS)
                for row in wins:
                    guild = self.bot.get_guild(row['guild_id'])
                    if guild is not None:
                        try:
                            await self.anuncio(guild, row['opening_id'])
                        except Exception:
                            LOG.exception("Falha no reenvio da vitória #%s", row['opening_id'])
                estoques = await self.bot.pool.fetch("""SELECT guild_id,id FROM lucky_stock_audit
                    WHERE notice_pending AND notice_message_id IS NULL
                      AND (notice_claimed_at IS NULL OR notice_claimed_at<NOW()-INTERVAL '5 minutes')
                    ORDER BY notice_claimed_at NULLS FIRST,id LIMIT $1""", LOTE_REENVIO_AVISOS)
                for row in estoques:
                    try:
                        await self.avisar_reposicao(row['guild_id'], row['id'])
                    except Exception:
                        LOG.exception("Falha no reenvio do estoque #%s", row['id'])
                alertas = await self.bot.pool.fetch("""SELECT guild_id,id FROM lucky_stock_audit
                    WHERE dm_pending AND (dm_claimed_at IS NULL OR dm_claimed_at<NOW()-INTERVAL '5 minutes')
                    ORDER BY id LIMIT $1""", LOTE_REENVIO_AVISOS)
                for row in alertas:
                    guild = self.bot.get_guild(row['guild_id'])
                    if guild:
                        try:
                            await self.avisar_dono_sem_estoque(guild, row['id'])
                        except Exception:
                            LOG.exception("Alerta privado pendente %s", row['id'])
                if CONCEDER_CARGOS_AUTOMATICAMENTE:
                    cargos = await self.bot.pool.fetch("""SELECT guild_id,user_id,opening_id FROM lucky_wins
                        WHERE role_pending AND status='pending' AND review_reason IS NULL
                        AND (role_claimed_at IS NULL OR role_claimed_at<NOW()-INTERVAL '5 minutes')
                        ORDER BY opening_id LIMIT $1""",LOTE_REENVIO_AVISOS)
                    for r in cargos:
                        g=self.bot.get_guild(r['guild_id'])
                        if g:
                            try:
                                m=g.get_member(r['user_id']) or await g.fetch_member(r['user_id'])
                                await self.ajustar_cargo(g,m,{'id':r['opening_id']})
                            except discord.HTTPException:
                                await self.bot.pool.execute('UPDATE lucky_wins SET role_claimed_at=NOW() WHERE opening_id=$1 AND role_pending',r['opening_id'])
                atualizacoes=await self.bot.pool.fetch("""SELECT guild_id,opening_id FROM lucky_wins
                    WHERE public_refresh_pending AND public_message_id IS NOT NULL ORDER BY opening_id LIMIT $1""",LOTE_REENVIO_AVISOS)
                for r in atualizacoes:
                    g=self.bot.get_guild(r['guild_id'])
                    if g:
                        try:
                            await self.atualizar_anuncio(g,r['opening_id'])
                        except Exception:
                            LOG.exception('Atualização do anúncio pendente %s',r['opening_id'])
            except Exception:
                LOG.exception("Falha temporária na fila de avisos Lucky Block")
            await asyncio.sleep(INTERVALO_REENVIO_AVISOS)

    async def mandar_dm_vencedor(self, membro: discord.Member, abertura: dict) -> bool:
        try:
            view = mensagem_premio(membro.guild.id, abertura)
            await enviar_layout(membro.send, view, allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute("UPDATE lucky_wins SET dm_sent_at=NOW() WHERE opening_id=$1", abertura["id"])
            return True
        except Exception:
            LOG.exception("Falha na DM do vencedor %s; registro #%d", membro.id, abertura["id"])
            return False

    async def anuncio(self, guild: discord.Guild, abertura_id: int) -> bool:
        row = await self.bot.pool.fetchrow("""UPDATE lucky_wins SET public_claimed_at=NOW(),public_pending=TRUE
            WHERE opening_id=$1 AND guild_id=$2 AND public_message_id IS NULL
              AND (public_claimed_at IS NULL OR public_claimed_at<NOW()-INTERVAL '5 minutes')
            RETURNING *""", abertura_id, guild.id)
        if not row:
            return False
        try:
            premio = PREMIACOES.get(row["reward_code"], {})
            raridade = row["reward_rarity"] or premio.get("raridade", "empty")
            # Todas as vitórias registradas, inclusive raras e recompensas históricas.
            nome = row["reward_name"] or premio.get("nome", row["reward_code"])
            mensagem = texto_anuncio_premio(row["user_id"], nome, raridade, f"LB-{abertura_id:06d}")
            mensagem += "\n`📋` **Situação:** " + ("Entregue" if row["status"] == "delivered" else "Aguardando entrega")
            banner = banner_anuncio_premio(raridade, row["reward_banner_url"] or premio.get("banner", ""))
            view = cartao("<a:luck:1575023399833567272> PRÊMIO ESPECIAL ENCONTRADO!", mensagem, banner)
            canal = await self.buscar_canal(guild, CANAL_REGISTROS)
            msg = None
            if (agora()-row['created_at']).total_seconds()>30:
                msg = await self.buscar_mensagem_registro(canal,f'LB-{abertura_id:06d}','PRÊMIO ESPECIAL ENCONTRADO',row['created_at'])
            reconciliado = msg is not None
            if msg is None:
                msg = await enviar_layout(canal.send, view, allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute("""UPDATE lucky_wins SET public_message_id=$2,
                public_claimed_at=NULL,public_pending=FALSE WHERE opening_id=$1""", abertura_id, msg.id)
            if raridade == "secret" and AVISAR_EVERYONE_SECRETOS and not reconciliado:
                try:
                    await canal.send("@everyone 🎉 Uma premiação **SECRETA** acaba de ser encontrada! "
                                     "Confira o anúncio acima.",
                        allowed_mentions=discord.AllowedMentions(everyone=True, users=False, roles=False))
                except discord.HTTPException:
                    LOG.exception("Anúncio secreto salvo, mas não foi possível mencionar @everyone")
            return True
        except Exception:
            LOG.exception("Falha ao anunciar Lucky Block #%d no canal %s; aguardando reenvio", abertura_id, CANAL_REGISTROS)
            return False

    async def atualizar_anuncio(self, guild: discord.Guild, abertura_id: int):
        row = await self.bot.pool.fetchrow("SELECT * FROM lucky_wins WHERE guild_id=$1 AND opening_id=$2",
                                           guild.id, abertura_id)
        if not row or not row["public_message_id"]:
            return
        premio = PREMIACOES.get(row["reward_code"])
        nome = row["reward_name"] or (premio["nome"] if premio else row["reward_code"])
        txt = (f"🏆 **Vencedor:** <@{row['user_id']}>\n"
               f"🎁 **Premiação:** {nome}\n"
               f"💎 **Raridade:** {raridade_nome(row['reward_rarity'])}\n"
               f"📜 **Registro:** `LB-{abertura_id:06d}`\n"
               f"✅ **Situação:** {'Entregue' if row['status'] == 'delivered' else 'Aguardando entrega'}")
        canal = await self.buscar_canal(guild, CANAL_REGISTROS)
        msg = await canal.fetch_message(row["public_message_id"])
        banner = banner_anuncio_premio(
            row["reward_rarity"] or (premio["raridade"] if premio else "empty"),
            row["reward_banner_url"] or (premio["banner"] if premio else ""))
        view = cartao("<a:luck:1575023399833567272> PRÊMIO ESPECIAL ENCONTRADO!", txt, banner)
        extras = {} if getattr(msg.flags, "is_components_v2", False) else {"content": None, "embeds": []}
        anexos = {}
        try:
            anexos = anexo_edicao(view)
            await msg.edit(view=view, **extras, **anexos)
        except (OSError, discord.HTTPException) as exc:
            if isinstance(exc, discord.HTTPException) and exc.status not in (400, 403, 413):
                raise
            remover_midia(view)
            await msg.edit(view=view, **extras, attachments=[])
        finally:
            for arquivo in anexos.get('attachments', []):
                arquivo.close()
        await self.bot.pool.execute("UPDATE lucky_wins SET public_refresh_pending=FALSE WHERE opening_id=$1 AND status=$2",abertura_id,row['status'])

    async def verificar_e_publicar_comprovante(self, ticket: discord.TextChannel, abertura_id: int, usuario_id: int) -> bool:
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                row = await con.fetchrow("""SELECT * FROM lucky_wins
                    WHERE opening_id=$1 AND guild_id=$2 AND user_id=$3 FOR UPDATE""",abertura_id,ticket.guild.id,usuario_id)
                if not row:
                    return False
                if row['ticket_channel_id'] == ticket.id:
                    return True
                if row['ticket_channel_id'] and ticket.guild.get_channel(row['ticket_channel_id']):
                    return False
                if row['receipt_claimed_at'] and row['receipt_claimed_at'] > agora()-timedelta(minutes=5):
                    return False
                reserva=await con.fetchval("""UPDATE lucky_wins SET receipt_claimed_at=NOW(),receipt_claim_channel=$2
                    WHERE opening_id=$1 RETURNING receipt_claimed_at""",abertura_id,ticket.id)
        # Discord I/O fora do bloqueio de linha. Reutiliza comprovante se a confirmação anterior falhou.
        atual=PREMIACOES.get(row['reward_code'],{})
        premio=dict(atual,nome=row['reward_name'] or atual.get('nome',row['reward_code']),
            raridade=row['reward_rarity'] or atual.get('raridade','legendary'),
            banner=row['reward_banner_url'] or atual.get('banner',''))
        entrada=dict(id=abertura_id,premio=premio,created_at=row['created_at'],status=row['status'],
                     validated_at=row['validated_at'],validated_by=row['validated_by'],review_reason=row['review_reason'])
        # Concede acesso de leitura/atendimento aos validadores também em ticket pré-existente.
        for cid in CARGOS_VALIDADORES:
            cargo=ticket.guild.get_role(cid)
            if cargo and not ticket.permissions_for(cargo).view_channel:
                permissoes=ticket.overwrites_for(cargo)
                permissoes.view_channel=True;permissoes.send_messages=True;permissoes.read_message_history=True
                try:
                    await ticket.set_permissions(cargo,overwrite=permissoes,reason='Validação Lucky Block')
                except discord.HTTPException:
                    LOG.warning('Sem permissão para conceder acesso ao validador %s no ticket %s',cid,ticket.id)
        msg=None
        if row['receipt_claimed_at']:
            msg=await self.buscar_mensagem_registro(ticket,f'LB-{abertura_id:06d}','COMPROVANTE OFICIAL',row['created_at'])
        if msg is None:
            view=cartao('🧾 COMPROVANTE OFICIAL DE PREMIAÇÃO',recibo(entrada,usuario_id),
                        banner_individual_premio(premio['banner'],premio['raridade']))
            msg=await enviar_layout(ticket.send,view,allowed_mentions=discord.AllowedMentions.none())
        atualizado=await self.bot.pool.fetchval("""UPDATE lucky_wins SET ticket_channel_id=$2,ticket_claimed_at=NOW(),
            receipt_message_id=$3,receipt_claimed_at=NULL,receipt_claim_channel=NULL WHERE opening_id=$1
            AND receipt_claimed_at=$4 AND receipt_claim_channel=$2 RETURNING opening_id""",abertura_id,ticket.id,msg.id,reserva)
        return atualizado is not None

    async def comprovante_em_ticket_existente(self, guild: discord.Guild, usuario_id: int, abertura_id: int):
        """Se o usuário já tem ticket, anexa o comprovante imediatamente ao ganhar."""
        try:
            tickets = importlib.import_module("cogs.tickets")
            if self.bot.get_cog("TicketsCog") is None:
                return
            for canal, estado in tickets.listar_tickets(guild):
                if estado.get("owner") == usuario_id:
                    await self.verificar_e_publicar_comprovante(canal, abertura_id, usuario_id)
                    break
        except Exception:
            LOG.exception("Falha ao anexar comprovante no ticket existente para #%d", abertura_id)

    async def abrir_ticket_premio(self, interaction: discord.Interaction, guild_id: int, abertura_id: int):
        if interaction.user.id <= 0:
            return await interaction.response.send_message("❌ Usuário inválido.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        row = await self.bot.pool.fetchrow("SELECT * FROM lucky_wins WHERE opening_id=$1 AND guild_id=$2",
                                           abertura_id, guild_id)
        if row is None or row["user_id"] != interaction.user.id:
            return await interaction.followup.send("❌ Esse comprovante pertence a outro usuário ou não existe.", ephemeral=True)
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return await interaction.followup.send("❌ Servidor indisponível.", ephemeral=True)
        try:
            tickets = importlib.import_module("cogs.tickets")
            if self.bot.get_cog("TicketsCog") is None:
                raise RuntimeError("cogs.tickets não está carregado")
            membro = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
            lock = self._ticket_locks.setdefault(interaction.user.id, asyncio.Lock())
            async with lock:
                existentes = [(canal, st) for canal, st in tickets.listar_tickets(guild)
                              if st.get("owner") == interaction.user.id]
                if existentes:
                    canal = existentes[0][0]
                    ok = await self.verificar_e_publicar_comprovante(canal, abertura_id, membro.id)
                    return await interaction.followup.send(
                        (f"✅ Seu comprovante foi vinculado ao ticket {canal.mention}." if ok else
                         "⚠️ O registro já está associado a outro ticket ainda ativo. Consulte a equipe."),
                        ephemeral=True)
                erro = tickets.checar_pode_abrir(guild, membro)
                if erro:
                    return await interaction.followup.send(erro, ephemeral=True)
                cat = tickets.CATEGORIAS["outros"]
                painel = await self.buscar_canal(guild, CANAL_PAINEL)
                categoria = tickets.resolver_categoria(guild, cat, painel.category)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    membro: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                         read_message_history=True, attach_files=True, embed_links=True),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                         manage_channels=True, manage_permissions=True, manage_messages=True,
                         attach_files=True, embed_links=True),
                }
                for cargo_id in set(tickets.CARGOS_STAFF) | set(tickets.CARGOS_NOTIFICAR) | set(CARGOS_VALIDADORES):
                    cargo = guild.get_role(cargo_id)
                    if cargo is not None:
                        overwrites[cargo] = discord.PermissionOverwrite(view_channel=True,
                            send_messages=True, read_message_history=True, attach_files=True,
                            embed_links=True, manage_messages=cargo_id in set(tickets.CARGOS_STAFF) | set(tickets.CARGOS_NOTIFICAR))
                numero = tickets.proximo_numero()
                canal = await guild.create_text_channel(
                    name=f"resgate-lucky-{numero:04d}", category=categoria,
                    topic=f"owner={membro.id};cat=outros;num={numero}",
                    overwrites=overwrites, reason=f"Resgate Lucky Block #{abertura_id} / {membro.id}")
                try:
                    tickets.salvar_estado(canal.id, owner=membro.id, cat="outros", num=numero,
                        prio="normal", claim=None, claim_ts=None, locked=False, decisao=None,
                        respostas=[["Assunto", f"Resgate Lucky Block LB-{abertura_id:06d}"],
                                  ["Solicitação", "Validação de premiação do Lucky Block"]],
                        notas=[], card_id=None)
                    # O comprovante é registrado no banco e publicado imediatamente no ticket.
                    if not await self.verificar_e_publicar_comprovante(canal, abertura_id, membro.id):
                        raise RuntimeError('Comprovante ainda não vinculado')
                    try:
                        await tickets.atualizar_card(canal)
                    except Exception:
                        LOG.exception("Ticket Lucky criado, mas card de ticket falhou")
                    await canal.send(membro.mention + " " + " ".join(
                        f"<@&{id_}>" for id_ in tickets.cargos_para_notificar("outros")),
                        allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False))
                except Exception:
                    LOG.exception("Ticket criado, porém não foi possível concluir o comprovante")
                    return await interaction.followup.send(
                        f"⚠️ Ticket {canal.mention} criado, mas o comprovante não foi anexado. "
                        "Avise a equipe e informe o número do registro.", ephemeral=True)
                await interaction.followup.send(f"✅ Ticket de resgate criado: {canal.mention}. "
                    "Seu comprovante já está disponível para a equipe.", ephemeral=True)
        except (discord.HTTPException, RuntimeError, KeyError, ValueError) as exc:
            LOG.exception("Falha ao abrir ticket de prêmio")
            await interaction.followup.send("❌ Não consegui abrir o ticket. "
                "Verifique se a Central de Tickets está ativa e se o bot pode criar canais.", ephemeral=True)

    async def interagir(self, interaction: discord.Interaction, acao: str):
        if interaction.guild is None or interaction.channel_id != CANAL_PAINEL:
            return await interaction.response.send_message("❌ Use o painel oficial do Lucky Block.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            guild_id = interaction.guild.id
            if acao == "abrir":
                await self.garantir_guild(guild_id)
                resultado = await self.abrir(guild_id, interaction.user.id,
                    {r.id for r in getattr(interaction.user, "roles", [])})
                if "limite" in resultado:
                    return await interaction.followup.send(
                        f"⏳ Você usou suas {ABERTURAS_POR_CICLO} aberturas. "
                        f"Novas tentativas <t:{int(resultado['limite'].timestamp())}:R>.", ephemeral=True)
                premio = resultado["premio"]
                if premio:
                    texto = (f"🎉 Você ganhou **{premio['nome']}**!\n"
                             f"📜 Protocolo: `LB-{resultado['id']:06d}`\n"
                             f"🎟️ Restantes: **{resultado['restantes']}/{ABERTURAS_POR_CICLO}**\n"
                             "Você pode resgatar pelo botão abaixo ou pela DM.")
                    if resultado['renovacao']:
                        texto += f"\n`⏳` Renovação: <t:{int(resultado['renovacao'].timestamp())}:R>"
                    async def resultado_imediato():
                        view = cartao("🎁 PREMIAÇÃO ENCONTRADA", texto,
                                      banner_individual_premio(premio["banner"], premio["raridade"]))
                        linha = discord.ui.ActionRow()
                        linha.add_item(BotaoTicket(guild_id, resultado['id']))
                        view.children[0].add_item(linha)
                        await self.resultado_visual(interaction, view)

                    async def etapa(nome, tarefa):
                        try:
                            await tarefa
                        except Exception:
                            LOG.exception("Falha na etapa %s do ganho #%s", nome, resultado['id'])

                    # A reserva já foi confirmada; efeitos não alteram o sorteio.
                    await self.suspense(interaction, resultado['raridade'])
                    await asyncio.gather(
                        etapa("resultado", resultado_imediato()),
                        etapa("anúncio público", self.anuncio(interaction.guild, resultado['id'])),
                        etapa("DM", self.mandar_dm_vencedor(interaction.user, resultado)),
                    )
                    if premio['cargo_id'] and isinstance(interaction.user, discord.Member):
                        await etapa("cargo", self.ajustar_cargo(interaction.guild, interaction.user, resultado))
                        await etapa("atualizar anúncio", self.atualizar_anuncio(interaction.guild, resultado['id']))
                    await etapa("comprovante", self.comprovante_em_ticket_existente(interaction.guild, interaction.user.id, resultado['id']))

                else:
                    texto = "A caixa veio vazia, boa sorte na próxima!"
                    if resultado["sem_estoque"]:
                        texto = ("⚠️ Uma recompensa sorteada está sem estoque no momento. "
                                 "Nenhuma premiação foi reservada nesta abertura.")
                    if resultado.get('cargo_repetido'):
                        texto = "Você já possui ou recebeu esse cargo, ou tem uma entrega pendente. Nenhuma unidade foi consumida."
                    texto += f"\n`💎` **+{FRAGMENTOS_POR_CAIXA_VAZIA} fragmento(s) Royal** (cosméticos)."
                    texto += f"\n`🎟️` Restantes: **{resultado['restantes']}/{ABERTURAS_POR_CICLO}**"
                    if resultado["renovacao"]:
                        texto += f"\n`⏳` Renovação: <t:{int(resultado['renovacao'].timestamp())}:R>"
                    await self.suspense(interaction, "empty")
                    await self.exibir_revelacao(interaction, "📦 CAIXA VAZIA", texto,
                                               BANNER_CAIXA_VAZIA)
                return
            if acao == "desafio" and DESAFIO_ATIVO:
                return await enviar_layout(interaction.followup.send,painel_desafio(guild_id,interaction.user.id),ephemeral=True)
            if acao == "perfil":
                return await enviar_layout(interaction.followup.send, cartao("💎 MEU PROGRESSO",
                    await self.texto_perfil(guild_id, interaction.user.id), BANNER_COLECAO), ephemeral=True)
            if acao == "album":
                return await enviar_layout(interaction.followup.send, await self.album(guild_id, interaction.user.id), ephemeral=True)
            if acao == "participacao":
                return await enviar_layout(interaction.followup.send, cartao("🏅 RANKING DE PARTICIPAÇÃO",
                    await self.texto_ranking(guild_id, participacao=True), BANNER_RANKING), ephemeral=True)
            if acao == "marcos":
                return await enviar_layout(interaction.followup.send, cartao("🎯 MEUS MARCOS",
                    await self.meus_marcos(guild_id, interaction.user.id), BANNER_META), ephemeral=True)
            if acao == "historico":
                (saldo, renovacao), rows = await asyncio.gather(
                    self.obter_saldo(guild_id, interaction.user.id),
                    self.bot.pool.fetch("""SELECT id,reward_code,reward_name,rarity,created_at
                        FROM lucky_openings WHERE guild_id=$1 AND user_id=$2 ORDER BY id DESC LIMIT 10""",
                        guild_id, interaction.user.id),
                )
                linhas = [f"`LB-{r['id']:06d}` · {r['reward_name'] or 'Caixa vazia'} · "
                          f"{raridade_nome(r['rarity'])} · <t:{int(r['created_at'].timestamp())}:R>" for r in rows]
                texto = ("\n".join(linhas) if linhas else "Você ainda não abriu nenhuma caixa.")
                texto += f"\n\n`🎟️` Aberturas disponíveis: **{saldo}/{ABERTURAS_POR_CICLO}**"
                if renovacao:
                    texto += f"\n`⏳` Renovação: <t:{int(renovacao.timestamp())}:R>"
                return await interaction.followup.send(view=cartao("📜 MEU HISTÓRICO", texto), ephemeral=True)
            if acao == "ranking":
                view = cartao("🏆 RANKING DA TEMPORADA", await self.texto_ranking(guild_id), BANNER_RANKING)
                return await enviar_layout(interaction.followup.send, view, ephemeral=True)
            if acao == "colecao":
                view = cartao("🏅 MINHA COLEÇÃO", await self.texto_colecao(guild_id, interaction.user.id), BANNER_COLECAO)
                return await enviar_layout(interaction.followup.send, view, ephemeral=True)
            if acao == "meta":
                view = cartao("🌟 DESAFIO DA FAMÍLIA", await self.texto_meta(guild_id), BANNER_META)
                return await enviar_layout(interaction.followup.send, view, ephemeral=True)
            await interaction.followup.send("❌ Ação inválida.", ephemeral=True)
        except Exception:
            LOG.exception("Erro em interação Lucky Block (%s)", acao)
            await interaction.followup.send("❌ Erro interno do Lucky Block. Consulte o log do bot.", ephemeral=True)

    async def resumo_estoques(self, guild_id: int, pagina=None) -> str:
        await self.garantir_guild(guild_id)
        rows = await self.bot.pool.fetch("""SELECT code,stock_total,stock_available
            FROM lucky_reward_stock WHERE guild_id=$1""", guild_id)
        mapa = {row["code"]: row for row in rows}
        codigos = list(PREMIACOES)
        if pagina is not None:
            codigos = codigos[pagina*20:(pagina+1)*20]
        return "\n".join(f"`{codigo}` — **{mapa[codigo]['stock_available']} disponíveis** "
              f"(total histórico: {mapa[codigo]['stock_total']})" for codigo in codigos if codigo in mapa)

    async def alterar_estoque(self, guild_id: int, codigo: str, quantidade: int,
                              actor_id: int) -> str:
        if actor_id != ID_DONO_DISCORD:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                raise ValueError("Servidor indisponível")
            membro = guild.get_member(actor_id)
            if membro is None:
                try:
                    membro = await guild.fetch_member(actor_id)
                except discord.HTTPException as exc:
                    raise ValueError("Membro não localizado") from exc
            if not await self.pode_abastecer(membro, guild_id):
                raise ValueError("Sem autorização para abastecer estoque")
        if codigo not in PREMIACOES or not 0 <= quantidade <= 100_000:
            raise ValueError("Código ou quantidade inválida")
        await self.garantir_guild(guild_id)
        audit_id = None
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                anterior = await con.fetchval("""SELECT stock_available FROM lucky_reward_stock
                    WHERE guild_id=$1 AND code=$2 FOR UPDATE""", guild_id, codigo)
                if actor_id != ID_DONO_DISCORD and quantidade < anterior:
                    raise ValueError("Somente o proprietário pode reduzir estoque")
                await con.execute("""UPDATE lucky_reward_stock
                    SET stock_total=GREATEST(0,stock_total-stock_available)+$3,
                        stock_available=$3 WHERE guild_id=$1 AND code=$2""", guild_id, codigo, quantidade)
                if anterior is not None and anterior != quantidade:
                    audit_id = await con.fetchval("""INSERT INTO lucky_stock_audit
                        (guild_id,reward_code,actor_id,before_stock,after_stock,change_reason,notice_pending,dm_pending)
                        VALUES($1,$2,$3,$4,$5,'reposicao_manual',$6,$7) RETURNING id""",
                        guild_id, codigo, actor_id, anterior, quantidade, quantidade > anterior,
                        cruzou_limiar(anterior, quantidade))
        if audit_id is not None and quantidade > anterior:
            try:
                ok = await self.avisar_reposicao(guild_id, audit_id)
            except Exception:
                LOG.exception("Estoque salvo; falha ao iniciar envio da reposição #%s", audit_id)
                ok = False
            return ("📢 Reposição anunciada no canal de estoque." if ok else
                    "⚠️ Estoque salvo; anúncio pendente de envio automático. Verifique o canal e as permissões.")
        return "ℹ️ Sem aumento de estoque; nenhum anúncio público foi gerado."

    async def texto_perfil(self, guild_id, user_id):
        saldo, recarga = await self.obter_saldo(guild_id, user_id)
        total = await self.bot.pool.fetchval("SELECT total FROM lucky_fragments WHERE guild_id=$1 AND user_id=$2", guild_id, user_id) or 0
        selos = '\n'.join(f"{'✅' if total >= n else '🔒'} {titulo} — {n} fragmentos" for n,titulo in SELOS_FRAGMENTOS)
        desafios = await self.bot.pool.fetch("SELECT title FROM lucky_challenges WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 10",guild_id,user_id)
        if desafios:
            selos += '\n\n**☰ EVENTOS CONCLUÍDOS**\n' + '\n'.join('✅ '+r['title'] for r in desafios)
        return (f"**☰ TEMPORADA {TEMA_TEMPORADA.upper()}**\n> `🎟️` **Aberturas:** {saldo}/{ABERTURAS_POR_CICLO}\n"
                + (f"> `⏳` **Recarga:** <t:{int(recarga.timestamp())}:R>\n" if recarga else "")
                + f"> `💎` **Fragmentos Royal:** {total}\n\n**☰ SELOS COSMÉTICOS**\n{selos}\n"
                + "-# Fragmentos não podem ser comprados, trocados ou convertidos em prêmios ou chances.")

    async def album(self, guild_id, user_id, pagina=0):
        rows = await self.bot.pool.fetch("""SELECT DISTINCT ON (reward_code) reward_code,reward_name AS nome,reward_rarity AS raridade,
            reward_banner_url AS banner, COUNT(*) OVER (PARTITION BY reward_code) AS total
            FROM lucky_wins WHERE guild_id=$1 AND user_id=$2
            ORDER BY reward_code,opening_id DESC LIMIT 10 OFFSET $3""", guild_id, user_id, pagina*10)
        return AlbumRoyal(guild_id, user_id, rows, pagina)

    async def meus_marcos(self, guild_id, user_id, periodo=None):
        if periodo is not None:
            try:
                periodo=datetime.strptime(periodo,'%Y-%m').date().replace(day=1)
            except ValueError as exc:
                raise ValueError('Use ano-mês, exemplo: 2026-11.') from exc
        row = await self.bot.pool.fetchrow("""WITH mes AS (SELECT COALESCE($3::date,date_trunc('month',NOW() AT TIME ZONE 'America/Sao_Paulo')::date) AS inicio)
            SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE user_id=$2) AS pessoal
            FROM lucky_openings,mes WHERE guild_id=$1 AND created_at>=inicio::timestamp AT TIME ZONE 'America/Sao_Paulo'
            AND created_at<(inicio+INTERVAL '1 month') AT TIME ZONE 'America/Sao_Paulo'""", guild_id, user_id, periodo)
        texto = (f"> `📅` **Período:** {periodo.strftime('%m/%Y') if periodo else 'Mês atual'}\n"
                 f"> `📦` **Contribuições:** {row['pessoal']}\n> `🎯` **Total coletivo:** {row['total']}\n\n")
        for n, nome in MARCOS_COMUNIDADE:
            atingido = row['total'] >= n and row['pessoal'] > 0
            texto += f"{'✅' if atingido else '🔒'} **{nome}** — {n} caixas\n"
        return texto + "\n-# Selos comemorativos do mês para quem participou; nenhum prêmio pago é concedido."

    async def texto_colecao(self, guild_id: int, usuario_id: int) -> str:
        """Conquistas sem vazar o catálogo privado das recompensas."""
        row = await self.bot.pool.fetchrow("""SELECT COUNT(*) AS abertas,
            COUNT(*) FILTER (WHERE rarity='rare') AS raras,
            COUNT(*) FILTER (WHERE rarity='epic') AS epicas,
            COUNT(*) FILTER (WHERE rarity='legendary') AS lendarias,
            COUNT(*) FILTER (WHERE rarity='secret') AS secretas,
            COUNT(DISTINCT reward_code) FILTER (WHERE reward_code IS NOT NULL) AS diferentes
            FROM lucky_openings WHERE guild_id=$1 AND user_id=$2""", guild_id, usuario_id)
        abertas = int(row['abertas'] or 0)
        raras = int(row['raras'] or 0)
        epicas = int(row['epicas'] or 0)
        lendarias = int(row['lendarias'] or 0)
        secretas = int(row['secretas'] or 0)
        diferentes = int(row['diferentes'] or 0)
        conquistas = [
            (abertas >= 1, '`🍀` Primeira Lucky Block'),
            (abertas >= 25, '`📦` Explorador de caixas'),
            (abertas >= 100, '`🏛️` Veterano ROYAL'),
            (epicas > 0, '`⚡` Descobridor épico'),
            (lendarias > 0, '`💎` Lenda da Família'),
            (secretas > 0, '`👑` Segredo revelado'),
            (diferentes >= 3, '`🏅` Colecionador'),
        ]
        selos = '\n'.join(f"{'✅' if ganhou else '🔒'} {titulo}" for ganhou,titulo in conquistas)
        return ("**☰ MEU ÁLBUM**\n"
                f"> `🎟️` **Caixas abertas:** {abertas}\n"
                f"> `🍀` **Raras:** {raras}\n"
                f"> `⚡` **Épicas:** {epicas}\n"
                f"> `💎` **Lendárias:** {lendarias}\n"
                f"> `👑` **Secretas:** {secretas}\n"
                f"> `🎁` **Prêmios diferentes encontrados:** {diferentes}\n\n"
                "**☰ CONQUISTAS**\n" + selos +
                "\n\n-# Os selos são comemorativos e não concedem recompensas reais.\n" + await self.texto_perfil(guild_id, usuario_id))

    async def texto_ranking(self, guild_id: int, *, mensal: bool = True, participacao=False) -> str:
        restricao = "AND created_at >= date_trunc('month', NOW() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'America/Sao_Paulo'" if mensal else ""
        ordem = 'total DESC,pontos DESC,user_id' if participacao else 'pontos DESC,total DESC,user_id'
        rows = await self.bot.pool.fetch(f"""SELECT user_id, COUNT(*) AS total,
            COALESCE(SUM(CASE rarity WHEN 'rare' THEN 10 WHEN 'epic' THEN 100 WHEN 'legendary' THEN 1000
                WHEN 'secret' THEN 10000 ELSE 0 END),0) AS pontos
            FROM lucky_openings WHERE guild_id=$1 {restricao}
            GROUP BY user_id ORDER BY {ordem} LIMIT 10""", guild_id)
        linhas = '\n'.join(f"**{i}.** <@{r['user_id']}> — **{int(r['pontos'])}** pts ({r['total']} caixas)"
            for i,r in enumerate(rows,1))
        return (f"**☰ {'PARTICIPAÇÃO' if participacao else 'SORTE'} • {'TEMPORADA ATUAL' if mensal else 'RANKING GERAL'}**\n" +
                (linhas or 'Ainda não houve aberturas neste período.') +
                "\n\n-# Pontos: rara 10 · épica 100 · lendária 1.000 · secreta 10.000. "
                + ('A temporada vira no primeiro dia do mês (horário de São Paulo).' if mensal else 'Período histórico completo.'))

    async def texto_meta(self, guild_id: int) -> str:
        feitas = await self.bot.pool.fetchval("""SELECT COUNT(*) FROM lucky_openings
            WHERE guild_id=$1 AND created_at >= date_trunc('month', NOW() AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'America/Sao_Paulo'""", guild_id)
        feitas = int(feitas or 0)
        meta = META_COMUNITARIA_MENSAL
        preenchidos = min(12, (feitas*12)//max(1,meta))
        barra = '🟪'*preenchidos + '⬜'*(12-preenchidos)
        marcos = '\n'.join(f"{'✅' if feitas >= quantidade else '🔒'} **{quantidade} caixas** — {nome}"
                           for quantidade,nome in MARCOS_COMUNIDADE)
        return ("**☰ DESAFIO COLETIVO — TEMPORADA ATUAL**\n"
                f"> `📦` **Aberturas da Família:** {feitas}/{meta}\n"
                f"> `🎯` **Progresso:** {min(100, feitas*100//max(1,meta))}%\n"
                f"{barra}\n\n**☰ MARCOS COMUNITÁRIOS**\n{marcos}\n\n")

    async def exibir_revelacao(self, interaction: discord.Interaction, titulo: str,
                              descricao: str, banner: str) -> None:
        view = cartao(titulo, descricao, banner)
        await self.resultado_visual(interaction, view)

    async def editar_visual(self, interaction, view):
        anexos = {}
        try:
            anexos = anexo_edicao(view)
            return await interaction.edit_original_response(view=view, **anexos)
        finally:
            for arquivo in anexos.get('attachments', []):
                arquivo.close()

    async def suspense(self, interaction, raridade):
        if not ATIVAR_ABERTURA_CINEMATOGRAFICA:
            return
        try:
            await self.editar_visual(interaction, cartao(
                "<a:luck:1575023399833567272> ABERTURA MISTERIOSA",
                "`🎁` A caixa está sendo revelada...", banner_disponivel(BANNER_ABERTURA, BANNER_PAINEL)))
            await asyncio.sleep(max(0, min(2, SEGUNDOS_SUSPENSE)))
            await self.editar_visual(interaction, cartao(
                "✨ REVELAÇÃO", "`💎` Resultado registrado.",
                banner_disponivel(BANNERS_RARIDADE.get(raridade, ''), BANNER_REVELACAO, BANNER_PAINEL),
                raridade=raridade))
            await asyncio.sleep(max(0, min(2, SEGUNDOS_SUSPENSE)))
        except Exception:
            LOG.warning("Falha visual; exibindo resultado sem suspense", exc_info=True)

    async def resultado_visual(self, interaction, view):
        try:
            await self.editar_visual(interaction, view)
        except (OSError, discord.HTTPException):
            await enviar_layout(interaction.followup.send, view, ephemeral=True)

    async def texto_pendentes(self, guild_id: int, *, limite: int = 10):
        rows = await self.bot.pool.fetch("""SELECT opening_id,user_id,reward_name,reward_code,
            status,validated_at,review_reason,ticket_channel_id,created_at
            FROM lucky_wins WHERE guild_id=$1 AND status='pending'
            ORDER BY created_at ASC LIMIT $2""", guild_id, limite)
        texto = '\n'.join(
            f"`LB-{r['opening_id']:06d}` · {r['reward_name'] or r['reward_code']} · "
            f"<@{r['user_id']}> · "
            f"{'🔎 Revisão' if r['review_reason'] else ('✅ Aprovado' if r['validated_at'] else '⏳ Pendente')}"
            for r in rows) or 'Nenhum prêmio pendente de entrega.'
        return rows, texto

    async def acao_resgate_painel(self, interaction: discord.Interaction, guild_id: int,
                                  abertura_id: int, acao: str) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None or not await self.pode_validar(interaction.user, guild):
            return await interaction.response.send_message('❌ Acesso restrito.', ephemeral=True)
        if acao == 'entregar' and interaction.user.id != ID_DONO_DISCORD:
            return await interaction.response.send_message('❌ Entrega exclusiva do proprietário.', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        if acao == 'aprovar':
            row = await self.bot.pool.fetchrow("""UPDATE lucky_wins
                SET validated_at=NOW(),validated_by=$3,
                    review_reason=NULL,review_at=NULL,review_by=NULL
                WHERE guild_id=$1 AND opening_id=$2 AND ticket_channel_id IS NOT NULL
                  AND status='pending' AND validated_at IS NULL AND (user_id<>$3 OR $3=$4)
                RETURNING user_id,ticket_channel_id,reward_name,reward_code,validated_at""",
                guild_id, abertura_id, interaction.user.id, ID_DONO_DISCORD)
            if row is None:
                return await interaction.followup.send(
                    'ℹ️ Nada alterado: confirme se o ticket existe, se está pendente e se já não foi aprovado.', ephemeral=True)
            ticket = guild.get_channel(row['ticket_channel_id'])
            if isinstance(ticket, discord.TextChannel):
                try:
                    await ticket.send(view=cartao('✅ RESGATE APROVADO',
                        f"> `📜` **Protocolo:** `LB-{abertura_id:06d}`\n"
                        f"> `👤` **Beneficiário:** <@{row['user_id']}>\n"
                        f"> `🎁` **Prêmio:** {row['reward_name'] or row['reward_code']}\n"
                        f"> `🛡️` **Validador:** <@{interaction.user.id}>\n"
                        '> `📦` A validação não confirma a entrega do prêmio.'),
                        allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    LOG.exception('Aprovação salva mas falhou notificação no ticket')
            return await interaction.followup.send(
                f'✅ `LB-{abertura_id:06d}` aprovado. Ainda aguarda entrega.', ephemeral=True)
        if acao == 'entregar':
            row = await self.bot.pool.fetchrow("""UPDATE lucky_wins
                SET status='delivered',delivered_at=NOW(),delivered_by=$3,role_pending=FALSE,public_refresh_pending=TRUE
                WHERE guild_id=$1 AND opening_id=$2 AND status='pending'
                  AND ($4::bool = FALSE OR (validated_at IS NOT NULL AND review_reason IS NULL))
                RETURNING opening_id,ticket_channel_id""",
                guild_id, abertura_id, interaction.user.id, EXIGIR_APROVACAO_ENTREGA_MANUAL)
            if row is None:
                return await interaction.followup.send(
                    '❌ Não foi possível confirmar: protocolo inexistente, já entregue ou não aprovado.', ephemeral=True)
            try:
                await self.atualizar_anuncio(guild, abertura_id)
            except discord.HTTPException:
                LOG.exception('Entrega salva, mas falhou atualização do anúncio')
            return await interaction.followup.send(f'✅ Entrega `LB-{abertura_id:06d}` confirmada.', ephemeral=True)
        return await interaction.followup.send('❌ Ação inválida.', ephemeral=True)

    async def resumo_auditoria(self, guild_id: int) -> str:
        rows = await self.bot.pool.fetch("""SELECT actor_id,reward_code,before_stock,after_stock,
            change_reason,created_at FROM lucky_stock_audit WHERE guild_id=$1
            ORDER BY id DESC LIMIT 15""", guild_id)
        return '\n'.join(
            f"<t:{int(r['created_at'].timestamp())}:d> · `{r['reward_code']}` "
            f"**{r['before_stock']} → {r['after_stock']}** · "
            f"{'Sorteio' if r['change_reason']=='premiacao' else 'Manual'} · <@{r['actor_id']}>"
            for r in rows) or 'Sem mudanças registradas desde a atualização.'

    @commands.command(name="luckyresgatar")
    @commands.guild_only()
    async def luckyresgatar(self, ctx: commands.Context, abertura_id: int):
        """!luckyresgatar ID — reenvia uma DM com o botão de ticket ao verdadeiro vencedor."""
        row = await self.bot.pool.fetchrow("""SELECT * FROM lucky_wins
            WHERE guild_id=$1 AND opening_id=$2 AND user_id=$3""",
            ctx.guild.id, abertura_id, ctx.author.id)
        if not row:
            return await ctx.send("❌ Registro não encontrado para sua conta.", delete_after=15)
        atual = PREMIACOES.get(row['reward_code'], {})
        premio = dict(atual, nome=row['reward_name'] or atual.get('nome', row['reward_code']),
                      raridade=row['reward_rarity'] or atual.get('raridade', 'legendary'),
                      banner=row['reward_banner_url'] or atual.get('banner', ''),
                      descricao=row['reward_description'] or atual.get('descricao', 'Recompensa histórica.'),
                      cargo_id=row['role_id'] or 0)
        entrada = {"id": abertura_id, "premio": premio, "created_at": row['created_at']}

        if await self.mandar_dm_vencedor(ctx.author, entrada):
            await ctx.send("✅ Enviei uma nova DM com seu botão de resgate.", delete_after=15)
        else:
            await ctx.send("❌ Abra suas mensagens privadas e tente novamente.", delete_after=15)

    @commands.command(name="painellucky")
    @commands.guild_only()
    async def painellucky(self, ctx: commands.Context):
        if not await self.exigir_dono(ctx):
            return
        await self.garantir_guild(ctx.guild.id)
        canal = await self.buscar_canal(ctx.guild, CANAL_PAINEL)
        antigo = await self.bot.pool.fetchval("SELECT panel_message_id FROM lucky_settings WHERE guild_id=$1", ctx.guild.id)
        if antigo:
            try:
                mensagem = await canal.fetch_message(antigo)
                view = PainelLucky()
                if getattr(mensagem.flags, "is_components_v2", False):
                    await mensagem.edit(view=view, **anexo_edicao(view))
                else:
                    await mensagem.edit(content=None, embeds=[], view=view, **anexo_edicao(view))
                return await ctx.send(f"✅ Painel atualizado em {canal.mention}.")
            except (discord.NotFound, discord.HTTPException):
                LOG.warning("Painel anterior inacessível; criando outro")
        view = PainelLucky()
        msg = await enviar_layout(canal.send, view, allowed_mentions=discord.AllowedMentions.none())
        await self.bot.pool.execute("UPDATE lucky_settings SET panel_message_id=$2 WHERE guild_id=$1", ctx.guild.id, msg.id)
        await ctx.send(f"✅ Painel publicado em {canal.mention}.")

    @commands.command(name="painelestoquelucky", aliases=["estoqueluckypainel"])
    async def painelestoquelucky(self, ctx: commands.Context):
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_abastecedor(ctx, guild):
            return
        await self.apagar_comando(ctx)
        texto = await self.resumo_estoques(guild.id, pagina=0)
        await self.dm(ctx, view=PainelEstoque(guild.id, texto))

    @commands.command(name="luckyestoques")
    async def luckyestoques(self, ctx: commands.Context):
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_abastecedor(ctx, guild):
            return
        await self.apagar_comando(ctx)
        await self.dm(ctx, texto="📦 **Estoques atuais:**\n" + await self.resumo_estoques(guild.id))

    @commands.command(name="luckyestoque")
    async def luckyestoque(self, ctx: commands.Context, codigo: str, quantidade: int):
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_abastecedor(ctx, guild):
            return
        await self.apagar_comando(ctx)
        try:
            aviso = await self.alterar_estoque(guild.id, codigo_premiacao(codigo), quantidade, ctx.author.id)
            await self.dm(ctx, texto=f"✅ `{codigo}`: estoque disponível atualizado para {quantidade}.\n{aviso}")
        except ValueError as exc:
            await self.dm(ctx, texto=f"❌ {exc}")

    @commands.command(name="luckysaldo")
    @commands.guild_only()
    async def luckysaldo(self, ctx: commands.Context):
        saldo, renovacao = await self.obter_saldo(ctx.guild.id, ctx.author.id)
        texto = f"🎟️ Você tem **{saldo}/{ABERTURAS_POR_CICLO}** aberturas disponíveis."
        if renovacao:
            texto += f" Renovação <t:{int(renovacao.timestamp())}:R>."
        await ctx.send(texto)

    @commands.command(name="luckyentregar")
    @commands.guild_only()
    async def luckyentregar(self, ctx: commands.Context, abertura_id: int):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        row = await self.bot.pool.fetchrow("""UPDATE lucky_wins SET status='delivered',
            delivered_at=NOW(),delivered_by=$3,role_pending=FALSE,public_refresh_pending=TRUE WHERE opening_id=$1 AND guild_id=$2
            AND status='pending' AND ($4::bool = FALSE OR (validated_at IS NOT NULL AND review_reason IS NULL))
            RETURNING user_id,reward_code""",
            abertura_id, ctx.guild.id, ctx.author.id, EXIGIR_APROVACAO_ENTREGA_MANUAL)
        if not row:
            return await self.dm(ctx, texto="❌ Registro inexistente, já entregue ou ainda sem aprovação formal.")
        try:
            await self.atualizar_anuncio(ctx.guild, abertura_id)
        except Exception:
            LOG.exception("Falha ao atualizar o anúncio entregue; permanece pendente")
        await self.dm(ctx, texto=f"✅ Registro `LB-{abertura_id:06d}` marcado como entregue.")

    @commands.command(name="luckypublicar")
    @commands.guild_only()
    async def luckypublicar(self, ctx: commands.Context, abertura_id: int):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        enviado = await self.anuncio(ctx.guild, abertura_id)
        await self.dm(ctx, texto="✅ Anúncio publicado." if enviado else "ℹ️ Registro inexistente, já anunciado ou temporariamente pendente. Consulte os logs/diagnóstico.")

    @commands.command(name="luckyvalidar")
    async def luckyvalidar(self, ctx: commands.Context, abertura_id: int):
        """Consulta a autenticidade do comprovante, sem mudar a situação da entrega."""
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_validador(ctx, guild):
            return
        await self.apagar_comando(ctx)
        row = await self.bot.pool.fetchrow("SELECT * FROM lucky_wins WHERE guild_id=$1 AND opening_id=$2",
                                           guild.id, abertura_id)
        if not row:
            return await self.dm(ctx, texto="❌ Comprovante não encontrado no banco.")
        atual = PREMIACOES.get(row["reward_code"], {})
        premio = dict(atual,
            nome=row["reward_name"] or atual.get("nome", row["reward_code"]),
            raridade=row["reward_rarity"] or atual.get("raridade", "legendary"),
            banner=row["reward_banner_url"] or atual.get("banner", ""))
        entrada = {"id": abertura_id, "premio": premio,
                   "created_at": row["created_at"], "status": row["status"],
                   "validated_at": row["validated_at"], "validated_by": row["validated_by"],
                   "review_reason": row["review_reason"]}
        ticket = f"<#{row['ticket_channel_id']}>" if row["ticket_channel_id"] else "Aguardando abertura"
        view = cartao("✅ COMPROVANTE CONFERIDO NO BANCO",
                      recibo(entrada, row["user_id"]) + f"\n\n> `🎟️` **Ticket:** {ticket}",
                      banner_individual_premio(row["reward_banner_url"] or premio["banner"], premio["raridade"]))
        await self.dm(ctx, view=view)

    @commands.command(name="luckyaprovar")
    async def luckyaprovar(self, ctx: commands.Context, abertura_id: int):
        """Registra aprovação do comprovante por um validador; não entrega a premiação."""
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_validador(ctx, guild):
            return
        await self.apagar_comando(ctx)
        row = await self.bot.pool.fetchrow("""UPDATE lucky_wins
            SET validated_at=NOW(), validated_by=$3,
                review_reason=NULL,review_at=NULL,review_by=NULL
            WHERE guild_id=$1 AND opening_id=$2 AND ticket_channel_id IS NOT NULL
              AND status='pending' AND validated_at IS NULL AND (user_id<>$3 OR $3=$4)
            RETURNING opening_id,user_id,reward_name,reward_code,ticket_channel_id,validated_at""",
            guild.id, abertura_id, ctx.author.id, ID_DONO_DISCORD)
        if row is None:
            existente = await self.bot.pool.fetchrow("""SELECT validated_at,validated_by,ticket_channel_id,user_id,status
                FROM lucky_wins WHERE guild_id=$1 AND opening_id=$2""", guild.id, abertura_id)
            if existente is None:
                texto = "❌ Protocolo inexistente no banco."
            elif existente['user_id']==ctx.author.id and ctx.author.id!=ID_DONO_DISCORD:
                texto = '❌ Validadores não podem aprovar o próprio comprovante.'
            elif existente['status']=='delivered':
                texto = 'ℹ️ Esta recompensa já foi entregue.'
            elif existente["validated_at"] is not None:
                texto = f"ℹ️ O protocolo `LB-{abertura_id:06d}` já foi aprovado por <@{existente['validated_by']}>."
            else:
                texto = "⚠️ O ganhador precisa abrir o ticket e receber seu comprovante antes da aprovação."
            return await self.dm(ctx, texto=texto)

        # O banco confirma a aprovação. A notificação no ticket é informativa.
        canal = guild.get_channel(row["ticket_channel_id"])
        if isinstance(canal, discord.TextChannel):
            try:
                await canal.send(view=cartao("✅ COMPROVANTE VALIDADO",
                    f"> `📜` **Protocolo:** `LB-{abertura_id:06d}`\n"
                    f"> `👤` **Beneficiário:** <@{row['user_id']}>\n"
                    f"> `🎁` **Premiação:** {row['reward_name'] or row['reward_code']}\n"
                    f"> `🛡️` **Validador:** <@{ctx.author.id}>\n"
                    f"> `📅` **Data:** <t:{int(row['validated_at'].timestamp())}:F>\n\n"
                    "> `📦` **Entrega:** continua sujeita à confirmação pelo responsável."),
                    allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                LOG.exception("Comprovante aprovado, mas falhou o aviso no ticket #%s", abertura_id)
        await self.dm(ctx, texto=f"✅ Comprovante `LB-{abertura_id:06d}` aprovado e registrado no PostgreSQL. "
                                "A aprovação não marca a premiação como entregue.")

    @commands.command(name="luckycatalogolog")
    async def luckycatalogolog(self,ctx):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        rows=await self.bot.pool.fetch("SELECT code,actor_id,created_at FROM lucky_catalog_audit ORDER BY id DESC LIMIT 20")
        texto='\n'.join(f"`{r['code']}` • <@{r['actor_id']}> • <t:{int(r['created_at'].timestamp())}:F>" for r in rows)
        await self.dm(ctx,texto='📜 **Auditoria do catálogo**\n'+(texto or 'Nenhuma edição pelo painel.'))

    @commands.command(name="luckypremiacoes")
    async def luckypremiacoes(self,ctx,*,codigo: str = ''):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        if codigo:
            codigo=codigo_premiacao(codigo)
            if codigo not in PREMIACOES:
                return await self.dm(ctx,texto='❌ Código não encontrado.')
            return await self.dm(ctx,view=detalhe_catalogo(codigo))
        await self.dm(ctx,view=PainelCatalogo())

    @commands.command(name="luckydesafio")
    @commands.guild_only()
    async def luckydesafio(self,ctx):
        if not DESAFIO_ATIVO:
            return await ctx.send('Nenhum desafio ativo.',delete_after=10)
        await self.dm(ctx,view=painel_desafio(ctx.guild.id,ctx.author.id))

    @commands.command(name="luckycatalogo")
    @commands.guild_only()
    async def luckycatalogo(self,ctx):
        await self.garantir_guild(ctx.guild.id)
        rows=await self.bot.pool.fetch('SELECT code,stock_available FROM lucky_reward_stock WHERE guild_id=$1',ctx.guild.id)
        estoque={r['code']:r['stock_available'] for r in rows}
        linhas=[];secretos=0;chance_secreta=Decimal(0)
        for c,p in PREMIACOES.items():
            if not p['ativo']:
                continue
            if p['raridade']=='secret':
                if estoque.get(c,0)>0:
                    secretos+=1;chance_secreta+=Decimal(p['chance'])
                continue
            linhas.append(f"`💎` {p['nome']} • {raridade_nome(p['raridade'])} • {p['chance']}% • {'Disponível' if estoque.get(c,0)>0 else 'Esgotado'}")
        texto='**☰ CATÁLOGO DISPONÍVEL**\n'+'\n'.join(linhas)+f'\n\n`👑` Secretos disponíveis: {secretos} • chance total {chance_secreta}%\n-# Chances por caixa, não garantias; cargos já recebidos não são concedidos novamente.'
        await self.dm(ctx,texto=texto)

    @commands.command(name="luckyperfil")
    @commands.guild_only()
    async def luckyperfil(self, ctx):
        await self.dm(ctx, view=cartao("💎 MEU PROGRESSO", await self.texto_perfil(ctx.guild.id, ctx.author.id), BANNER_COLECAO))

    @commands.command(name="luckyalbum")
    @commands.guild_only()
    async def luckyalbum(self, ctx):
        await self.dm(ctx, view=await self.album(ctx.guild.id,ctx.author.id))

    @commands.command(name="luckymarcos")
    @commands.guild_only()
    async def luckymarcos(self, ctx, periodo: str = ''):
        try:
            texto=await self.meus_marcos(ctx.guild.id,ctx.author.id,periodo or None)
        except ValueError as exc:
            return await ctx.send(f'❌ {exc}',delete_after=15)
        await self.dm(ctx, view=cartao("🎯 MEUS MARCOS",texto,BANNER_META))

    @commands.command(name="luckycolecao")
    @commands.guild_only()
    async def luckycolecao(self, ctx: commands.Context):
        view = cartao('🏅 MINHA COLEÇÃO', await self.texto_colecao(ctx.guild.id, ctx.author.id), BANNER_COLECAO)
        await enviar_layout(ctx.send, view, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="luckyranking")
    @commands.guild_only()
    async def luckyranking(self, ctx: commands.Context, periodo: str = 'mensal'):
        mensal = periodo.lower() not in ('geral', 'all', 'total', 'participacao_geral')
        participacao = periodo.lower() in ('participacao', 'participação', 'participacao_geral')
        view = cartao('🏆 RANKING ROYAL', await self.texto_ranking(ctx.guild.id, mensal=mensal, participacao=participacao), BANNER_RANKING)
        await enviar_layout(ctx.send, view, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="luckymeta")
    @commands.guild_only()
    async def luckymeta(self, ctx: commands.Context):
        view = cartao('🌟 META DA FAMÍLIA', await self.texto_meta(ctx.guild.id), BANNER_META)
        await enviar_layout(ctx.send, view, allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="luckypendentes")
    async def luckypendentes(self, ctx: commands.Context):
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_validador(ctx, guild):
            return
        await self.apagar_comando(ctx)
        _, texto = await self.texto_pendentes(guild.id)
        await self.dm(ctx, texto='📋 **Premiações aguardando entrega**\n' + texto)

    @commands.command(name="painelresgateslucky", aliases=['centralresgateslucky'])
    async def painelresgateslucky(self, ctx: commands.Context):
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_validador(ctx, guild):
            return
        await self.apagar_comando(ctx)
        rows, texto = await self.texto_pendentes(guild.id)
        view = PainelResgates(guild.id, texto, rows)
        await self.dm(ctx, view=view)

    @commands.command(name="luckyrevisar")
    async def luckyrevisar(self, ctx: commands.Context, abertura_id: int, *, motivo: str):
        """Anota pendência sem cancelar prêmio, liberar estoque ou bloquear outras ações."""
        guild = ctx.guild or await self.guild_oficial()
        if not await self.exigir_validador(ctx, guild):
            return
        await self.apagar_comando(ctx)
        motivo = motivo.strip()
        if len(motivo) < 4 or len(motivo) > 350:
            return await self.dm(ctx, texto='❌ Informe de 4 a 350 caracteres no motivo.')
        row = await self.bot.pool.fetchrow("""UPDATE lucky_wins SET
            review_reason=$4,review_by=$3,review_at=NOW(),
            validated_at=NULL,validated_by=NULL
            WHERE guild_id=$1 AND opening_id=$2 AND status='pending'
            RETURNING opening_id,user_id,ticket_channel_id,reward_name,reward_code""",
            guild.id, abertura_id, ctx.author.id, motivo)
        if not row:
            return await self.dm(ctx, texto='❌ Protocolo inexistente ou não está pendente.')
        canal = guild.get_channel(row['ticket_channel_id']) if row['ticket_channel_id'] else None
        if isinstance(canal, discord.TextChannel):
            try:
                await canal.send(view=cartao('🔎 RESGATE EM ANÁLISE',
                    f"> `📜` **Protocolo:** `LB-{abertura_id:06d}`\n"
                    f"> `🛡️` **Responsável:** <@{ctx.author.id}>\n"
                    f"> `📋` **Motivo:** {discord.utils.escape_markdown(motivo)}\n"
                    '> `📦` **Premiação:** continua reservada; nenhuma unidade foi devolvida.'),
                    allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                LOG.warning('Revisão salva; falha ao publicar no ticket #%d', abertura_id)
        await self.dm(ctx, texto=f'✅ Motivo registrado para `LB-{abertura_id:06d}`. A premiação continua reservada.')

    @commands.command(name="luckyauditoria")
    async def luckyauditoria(self, ctx: commands.Context):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        guild = ctx.guild or await self.guild_oficial()
        texto = await self.resumo_auditoria(guild.id)
        await self.dm(ctx, texto='📊 **Auditoria dos 15 últimos movimentos de estoque**\n' + texto)

    @commands.command(name="luckydiagnostico")
    async def luckydiagnostico(self, ctx: commands.Context):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        guild = ctx.guild or await self.guild_oficial()
        linhas = ["**Diagnóstico Lucky Block — privado**"]
        for nome, id_ in (("Painel", CANAL_PAINEL), ("Registros", CANAL_REGISTROS), ("Estoque", CANAL_ESTOQUE)):
            try:
                canal = await self.buscar_canal(guild, id_)
                bot_membro = guild.me or await guild.fetch_member(self.bot.user.id)
                perms = canal.permissions_for(bot_membro)
                faltam = [p for p in ("view_channel", "send_messages", "attach_files", "read_message_history") if not getattr(perms, p)]
                linhas.append(f"{nome}: <#{id_}> — " + ("⚠️ " + ', '.join(faltam) if faltam else "✅ OK"))
                if nome == "Registros" and AVISAR_EVERYONE_SECRETOS and not perms.mention_everyone:
                    linhas.append("⚠️ Sem permissão mention_everyone para secretos.")
            except Exception as exc:
                linhas.append(f"❌ {nome} ({id_}): {type(exc).__name__}")
        for nome, ref in [("Painel", BANNER_PAINEL), ("Caixa vazia", BANNER_CAIXA_VAZIA),
                          ("Reposição", BANNER_REPOSICAO), ("Secreto", BANNER_PREMIO_SECRETO),
                          ("Abertura", BANNER_ABERTURA), ("Revelação", BANNER_REVELACAO),
                          ("Anúncio", BANNER_ANUNCIO_PREMIO)] + [
                              (p['nome'], p['banner']) for p in PREMIACOES.values()]:
            caminho = banner_arquivo(ref)
            linhas.append(f"{'✅' if caminho else '❌'} {nome}: `{caminho.name if isinstance(caminho, Path) else 'URL configurada' if caminho else ref}`")
        wins, stocks = await asyncio.gather(
            self.bot.pool.fetchval("SELECT COUNT(*) FROM lucky_wins WHERE guild_id=$1 AND public_pending AND public_message_id IS NULL", guild.id),
            self.bot.pool.fetchval("SELECT COUNT(*) FROM lucky_stock_audit WHERE guild_id=$1 AND notice_pending AND notice_message_id IS NULL", guild.id),
        )
        linhas.append(f"Fila: {wins} vitórias / {stocks} reposições. Tenta novamente após falhas (reserva de 5 min).")
        dm_pendentes = await self.bot.pool.fetchval("SELECT COUNT(*) FROM lucky_stock_audit WHERE guild_id=$1 AND dm_pending",guild.id)
        dm_indisponiveis = await self.bot.pool.fetchval("""SELECT COUNT(*) FROM lucky_stock_dm d JOIN lucky_stock_audit a ON a.id=d.audit_id
            WHERE a.guild_id=$1 AND d.status='unavailable'""",guild.id)
        linhas.append(f"Alertas privados: {dm_pendentes} evento(s) pendentes; {dm_indisponiveis} DM(s) indisponíveis registradas.")
        linhas.append(f"Abastecedores: {len(CARGOS_ABASTECER_ESTOQUE)} cargo(s), {len(USUARIOS_ABASTECER_ESTOQUE)} usuário(s).")
        await self.dm(ctx, texto='\n'.join(linhas))

    @commands.command(name="testarlucky", aliases=["testelucky"])
    async def testarlucky(self, ctx: commands.Context, codigo: str="lista", destino: str="dm"):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        codigo, destino = codigo.strip(), destino.lower().strip()
        if codigo.lower() == "clove":
            codigo = "clover"
        codigo = codigo_premiacao(codigo) if codigo not in {"lista", "painel", "estoque", "sorteio",
            "reposicao", "sem_estoque", "comprovante", "fluxo", "todos", "vazia", "abertura", "revelacao"} else codigo
        if codigo == "lista":
            texto = "🧪 **Comandos de teste — privados**\n" + "\n".join(
                f"`!testarlucky {next((a for a, original in _ALIASES_PREMIACOES.items() if original == c), c)}` — {p['nome']} [{raridade_nome(p['raridade'])}]" for c,p in PREMIACOES.items())
            texto += ("\n`!testarlucky painel` · `!testarlucky vazia` · `!testarlucky todos`"
                      "\n`!testarlucky sorteio` · `!testarlucky fluxo` · `!testarlucky estoque` · `!testarlucky comprovante` · `!testarlucky sem_estoque` · `!testarlucky reposicao`"
                      "\n`!testarlucky clover registros` (prévia pública sem marcações)"
                      "\n`!testarlucky reposicao estoque` · `!luckydiagnostico`"
                      "\n`!simularlucky nitro_basico` (DM + anúncio identificados como teste, temporários)"
                      "\n`!luckyvalidar ID` (confere autenticidade) · `!luckyaprovar ID` (aprova, para equipe autorizada)"
                      "\n`!painelresgateslucky` · `!luckypendentes` · `!luckyauditoria` (dono)"
                      "\n`!luckycolecao` · `!luckyranking` · `!luckymeta`"
                      "\n`!luckyperfil` · `!luckyalbum` · `!luckymarcos` · `!luckydesafio` · `!luckycatalogo`"
                      "\n`!luckypremiacoes` · `!luckycatalogolog`")
            return await self.dm(ctx, texto=texto)
        if codigo in ('abertura','revelacao'):
            return await self.dm(ctx,view=cartao('🧪 '+codigo.upper(),'Prévia visual, sem consumo.',
                BANNER_ABERTURA if codigo=='abertura' else BANNER_REVELACAO,teste=True))
        if codigo == "painel":
            return await self.dm(ctx, view=PainelLucky(teste=True))
        if codigo == "estoque":
            guild = ctx.guild or await self.guild_oficial()
            return await self.dm(ctx, texto="🧪 **Estoques atuais**\n" + await self.resumo_estoques(guild.id))
        if codigo == "sorteio":
            sorteado = sortear_codigo()
            nome = PREMIACOES[sorteado]["nome"] if sorteado else "Caixa vazia"
            return await self.dm(ctx, texto=f"🧪 Sorteio simulado: **{nome}**. Nenhuma tentativa ou estoque consumido.")
        if codigo == "reposicao":
            view = cartao_reposicao("clover", 0, 2, teste=True)
            if destino == "estoque":
                try:
                    guild = ctx.guild or await self.guild_oficial()
                    canal = await self.buscar_canal(guild, CANAL_ESTOQUE)
                    await enviar_layout(canal.send, view, delete_after=180,
                                        allowed_mentions=discord.AllowedMentions.none())
                    return await self.dm(ctx, texto=f"✅ Prévia enviada a {canal.mention}; sem alteração de estoque.")
                except Exception:
                    LOG.exception("Falha no teste do canal de estoque")
                    return await self.dm(ctx, texto="❌ Falha no canal de estoque. Use !luckydiagnostico.")
            return await self.dm(ctx, view=view)
        if codigo == "sem_estoque":
            return await self.dm(ctx, view=cartao("📦 RECOMPENSA SEM ESTOQUE — TESTE",
                "Uma recompensa sorteada está sem estoque. Nenhum prêmio foi reservado. "
                "A caixa concederia fragmentos cosméticos. O estoque pode ser abastecido pelo painel privado.", BANNER_CAIXA_VAZIA, teste=True))
        if codigo == "comprovante":
            premio = PREMIACOES["clover"]
            entrada = {"id": 0, "premio": premio, "created_at": agora(), "status": "TESTE"}
            return await self.dm(ctx, view=cartao("🧾 COMPROVANTE — TESTE",
                recibo(entrada, ctx.author.id, teste=True), premio["banner"], teste=True))
        if codigo == "fluxo":
            return await self.dm(ctx, texto=("🧪 **Teste do fluxo:**\n"
                "1. Resultado no painel, com banner específico.\n"
                "2. DM privada com botão persistente de resgate.\n"
                "3. Ticket em `cogs.tickets` usando categoria Outros.\n"
                "4. Comprovante de protocolo único publicado no ticket.\n"
                "5. Anúncio público em `Registros` (secretos com @everyone em ganhos reais).\n"
                "6. Painel do dono altera estoque. **Este teste não abre ticket.**"))
        if codigo == "todos":
            if destino != "dm":
                return await self.dm(ctx, texto="❌ Teste `todos` é exclusivo de DM.")
            codigos = list(PREMIACOES) + ["vazia"]
        else:
            codigos = [codigo]
        if destino not in ("dm", "registros"):
            return await self.dm(ctx, texto="❌ Destino: `dm` ou `registros`.")
        if destino == "registros" and ctx.guild is None:
            return await self.dm(ctx, texto="❌ Testes públicos devem ser invocados dentro do servidor.")
        if destino == "registros":
            canal = await self.buscar_canal(ctx.guild, CANAL_REGISTROS)
        for cod in codigos:
            if cod == "vazia":
                view = cartao("📦 CAIXA VAZIA — TESTE", "Simulação sem premiação.", BANNER_CAIXA_VAZIA, teste=True)
            else:
                premio = PREMIACOES.get(cod)
                if not premio:
                    from difflib import get_close_matches
                    sugestoes = get_close_matches(cod, PREMIACOES, n=1, cutoff=0.4)
                    dica = f" Você quis dizer `{sugestoes[0]}`?" if sugestoes else " Use `!testarlucky lista`."
                    return await self.dm(ctx, texto=f"❌ Código `{cod}` inexistente.{dica}")
                teste_abertura = {"id": 0, "premio": premio, "created_at": agora()}
                if destino == "registros":
                    # Prévia identificada como simulação. Não cria vitória no banco.
                    conteudo = texto_anuncio_premio(
                        ctx.author.id, premio["nome"], premio["raridade"], "LB-000000")
                    view = cartao("<a:luck:1575023399833567272> PRÊMIO ESPECIAL ENCONTRADO!", conteudo,
                        banner_anuncio_premio(premio["raridade"], premio["banner"]), teste=True)
                else:
                    view = mensagem_premio(ctx.guild.id if ctx.guild else 0,
                                           teste_abertura, teste=True)
            if destino == "registros":
                # Sem @everyone, mesmo que a premiação simulada seja secreta.
                await enviar_layout(canal.send, view, allowed_mentions=discord.AllowedMentions.none(), delete_after=180)
            else:
                if not await self.dm(ctx, view=view):
                    return
        await self.dm(ctx, texto=f"✅ Teste concluído: **{len(codigos)}** prévia(s). Sem consumo, sem tickets reais, sem menções.")


    @commands.command(name="simularlucky", aliases=["simulalucky"])
    @commands.guild_only()
    async def simularlucky(self, ctx: commands.Context, codigo: str):
        """!simularlucky clover — prévias identificadas, sem sorteio, estoque nem @everyone.

        Mostra ao dono a DM (botão desativado) e publica temporariamente o
        anúncio no canal de registros. Publicações são apagadas em 3 minutos
        para que não permaneçam como falsas conquistas da comunidade.
        """
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        codigo = codigo.strip()
        if codigo.lower() == "clove":
            codigo = "clover"
        codigo = codigo_premiacao(codigo)
        premio = PREMIACOES.get(codigo)
        if premio is None:
            from difflib import get_close_matches
            sugestoes = get_close_matches(codigo, PREMIACOES.keys(), n=1, cutoff=0.45)
            dica = f" Você quis dizer `!simularlucky {sugestoes[0]}`?" if sugestoes else ""
            return await self.dm(ctx, texto=f"❌ Recompensa `{codigo}` inexistente.{dica}")

        guild = ctx.guild
        demonstracao = {"id": 0, "premio": premio, "created_at": agora()}
        # DM identificada como teste; ticket desativado.
        view_dm = mensagem_premio(guild.id, demonstracao, teste=True, visual_real=False)
        if not await self.dm(ctx, view=view_dm):
            return

        # Anúncio usa o mesmo layout e banner que um ganho efetivo.
        titulo = "<a:luck:1575023399833567272> PRÊMIO ESPECIAL ENCONTRADO!"
        texto = texto_anuncio_premio(ctx.author.id, premio["nome"],
                                     premio["raridade"], "LB-000000")
        banner = banner_anuncio_premio(premio["raridade"], premio["banner"])
        view_publica = cartao(titulo, texto, banner, teste=True)
        try:
            canal = await self.buscar_canal(guild, CANAL_REGISTROS)
            # Sem @everyone ou outras menções reais. Nunca cria comprovante.
            await enviar_layout(canal.send, view_publica, allowed_mentions=discord.AllowedMentions.none(), delete_after=180)
        except (discord.Forbidden, discord.HTTPException, ValueError):
            LOG.exception("Não foi possível enviar a simulação pública: %s", codigo)
            return await self.dm(ctx, texto="❌ DM enviada, mas não foi possível publicar nos registros.")
        await self.dm(ctx, texto=(
            f"✅ Prévia de `{codigo}` enviada à DM e a {canal.mention}. "
            "A mensagem pública será apagada em 3 minutos. "
            "Nenhum sorteio, estoque, cargo, ticket ou @everyone foi acionado."))



async def setup(bot: commands.Bot) -> None:
    if not all(hasattr(discord.ui, nome) for nome in
               ("LayoutView", "Container", "TextDisplay", "MediaGallery", "ActionRow", "DynamicItem")):
        raise RuntimeError("Lucky Block exige discord.py 2.6+ com Components V2")
    await bot.add_cog(LuckyBlockRoyal(bot))
