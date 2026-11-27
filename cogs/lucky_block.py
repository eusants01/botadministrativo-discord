"""Lucky Block ROYAL — discord.py 2.6+, asyncpg, Components V2.

Instale APENAS este arquivo em cogs/lucky_block.py; exige bot.pool e cogs.tickets.
Banco e prêmios são persistentes. Apenas o dono vê estoque e detalhes de testes.
Não insira tokens ou credenciais no repositório.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import secrets
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord.ext import commands

LOG = logging.getLogger("sants.bot.lucky_block")

CANAL_PAINEL = 1572785659108917439
CANAL_REGISTROS = 1572355776377266176
CANAL_ESTOQUE = 1573584140719357972  
ID_DONO_DISCORD = 925863471902503033  
CARGOS_VALIDADORES = (1561231585993293864,)  
CARGOS_ALERTA_ESTOQUE = CARGOS_VALIDADORES  
USUARIOS_ALERTA_ESTOQUE = (1371486864791572555,1243928690795221123,1455061586082533410)  
ABERTURAS_POR_CICLO = 10
HORAS_APOS_ULTIMA_ABERTURA = 2 
BANNER_PAINEL = "assets/lucky_block/painel.png"
BANNER_CAIXA_VAZIA = "caixa_vazia"
BANNER_REPOSICAO = "reposicao_estoque"  # assets/lucky_block/reposicao_estoque.png
BANNER_PREMIO_SECRETO = "recompensa_secreta"  # assets/lucky_block/recompensa_secreta.png
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
        # RARIDADE: RARA | CHANCE: 5.00%
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
            nome="Keys Aleatórias Steam",
            raridade="Secreta",
            chance="0,005",
            estoque=1,
            cargo_id=0,
            banner="keys_aleatorias_steam",
            ativo=True,
            descricao="Keys Aleatórias Steam: A forma de entrega será acertada no ticket.",
        ),

        # --------------------------------------------------------
            # 12 - Vaga na Família
            # RARIDADE: SECRETA | CHANCE: 0.001%
            # --------------------------------------------------------
        
            "Vaga na Família": dict(
                nome="Vaga na Família",
                raridade="Secreta",
                chance="0,001",
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


def validar_configuracao() -> None:
    for ids in (CARGOS_VALIDADORES, CARGOS_ALERTA_ESTOQUE, USUARIOS_ALERTA_ESTOQUE):
        if not isinstance(ids, (tuple, list, set, frozenset)) or any(not isinstance(i, int) or i <= 0 for i in ids):
            raise ValueError("IDs de cargos/usuários devem ser uma coleção de inteiros; use (ID,) para um único ID.")
    total = 0
    for codigo, premio in PREMIACOES.items():
        if not codigo.replace("_", "").isalnum() or len(codigo) > 60:
            raise ValueError(f"Código de premiação inválido: {codigo}")
        if premio["raridade"] not in RARIDADES or premio["raridade"] == "empty":
            raise ValueError(f"Raridade inválida: {codigo}")
        if not isinstance(premio["estoque"], int) or premio["estoque"] < 0:
            raise ValueError(f"Estoque inicial inválido: {codigo}")
        if not isinstance(premio["cargo_id"], int) or premio["cargo_id"] < 0:
            raise ValueError(f"Cargo inválido: {codigo}")
        if not isinstance(premio["ativo"], bool):
            raise ValueError(f"Campo ativo inválido: {codigo}")
        if premio["ativo"]:
            total += tickets_da_chance(premio["chance"], codigo)
    if total > TOTAL_SORTEIO:
        raise ValueError("As chances somadas excedem 100%")


def sortear_codigo() -> str | None:
    sorteio = secrets.randbelow(TOTAL_SORTEIO)
    limite = 0
    for codigo, premio in PREMIACOES.items():
        if premio["ativo"]:
            limite += tickets_da_chance(premio["chance"], codigo)
            if sorteio < limite:
                return codigo
    return None


def raridade_nome(raridade: str) -> str:
    return RARIDADES.get(raridade, ("Desconhecida", 0))[0]


def codigo_premiacao(valor: str) -> str:
    """Resolve letras maiúsculas/minúsculas sem alterar as chaves reais do catálogo."""
    entrada = valor.strip().casefold()
    return next((codigo for codigo in PREMIACOES if codigo.casefold() == entrada), valor.strip())


def normalizar_nome_banner(nome: str) -> str:
    texto = unicodedata.normalize("NFKD", nome.casefold())
    return re.sub(r"[\W_]+", "", "".join(c for c in texto if not unicodedata.combining(c)))


def banner_arquivo(referencia: str) -> Path | str | None:
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
            for arquivo in base.parent.iterdir():
                if (arquivo.is_file() and arquivo.suffix.casefold() in EXTENSOES
                    and normalizar_nome_banner(arquivo.stem) == normalizar_nome_banner(base.stem)
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
                             banner_individual, BANNER_PAINEL)


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


def cartao(titulo: str, conteudo: str, banner: str = "", *, teste=False) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=180)
    cont = discord.ui.Container(accent_colour=CORES)
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
            "Teste sua sorte nas Lucky Blocks e concorra a prêmios exclusivos. "
            f"Você possui **{ABERTURAS_POR_CICLO} aberturas**; ao terminar todas, novas tentativas "
            f"ficam disponíveis **{HORAS_APOS_ULTIMA_ABERTURA} horas depois da última abertura**.\n\n"
            "### Premiações\n"
            "> ☰ `💜` Discord Nitro\n"
            "> ☰ `🍊` Fruta Permanente Aleatória\n"
            "> ☰ `🎨` Decoração de Perfil\n"
            "> ☰ `🐆` Candidato do CIGS\n"
            "> ☰ `💖` Salve da Kananda\n"
            "> ☰ `🔑` 10x Keys Aleatórias Steam\n"
            "> ☰ `💎` Minério aleatório no EB.\n"
            "> ☰ `💸` 500 Robux\n\n"
            "### Observações\n"
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
        if teste:
            for botao in linha.children:
                botao.disabled = True
        cont.add_item(linha)
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
        if cog is None or not await cog.usuario_dono(interaction.user):
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
        except Exception:
            LOG.exception("Falha ao ajustar estoque %s", self.codigo)
            await interaction.followup.send("❌ Erro ao salvar estoque no PostgreSQL.", ephemeral=True)


class SeletorEstoque(discord.ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        opcoes = [discord.SelectOption(label=p["nome"][:95], value=c,
                    description=f"{raridade_nome(p['raridade'])} • {c}"[:100])
                  for c, p in PREMIACOES.items()]
        super().__init__(placeholder="Selecione uma recompensa para editar o estoque",
                         min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("LuckyBlockRoyal")
        if cog is None or not await cog.usuario_dono(interaction.user):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        await interaction.response.send_modal(ModalEstoque(self.guild_id, self.values[0]))


class PainelEstoque(discord.ui.LayoutView):
    def __init__(self, guild_id: int, texto: str):
        super().__init__(timeout=900)
        cont = discord.ui.Container(accent_colour=CORES)
        cont.add_item(discord.ui.TextDisplay("## <:luckblock:1572868783725609083> ESTOQUE PRIVADO — LUCKY BLOCK\n" + texto +
                    "\nSelecione uma premiação para definir a quantidade de unidades **disponíveis**. "
                    "O banco preserva a quantidade após reiniciar o bot."))
        linha = discord.ui.ActionRow()
        linha.add_item(SeletorEstoque(guild_id))
        cont.add_item(linha)
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
            + texto + '\n\n-# Validação não equivale à entrega. Estoque continua exclusivo do proprietário.'))
        if rows:
            linha = discord.ui.ActionRow()
            linha.add_item(SeletorResgates(guild_id, rows))
            cont.add_item(linha)
        self.add_item(cont)


class LuckyBlockRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ticket_locks: dict[int, asyncio.Lock] = {}
        self._avisos_task: asyncio.Task | None = None

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
        self.bot.add_view(PainelLucky())
        self.bot.add_dynamic_items(BotaoTicket)
        self._avisos_task = asyncio.create_task(self.reenviar_avisos())
        LOG.info("Lucky Block ROYAL carregado; %d recompensas", len(PREMIACOES))

    async def cog_unload(self):
        if self._avisos_task is not None:
            self._avisos_task.cancel()
            try:
                await self._avisos_task
            except asyncio.CancelledError:
                pass
        self.bot.remove_dynamic_items(BotaoTicket)

    async def garantir_guild(self, guild_id: int):
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                await con.execute("INSERT INTO lucky_settings(guild_id) VALUES($1) ON CONFLICT DO NOTHING", guild_id)
                for codigo, premio in PREMIACOES.items():
                    await con.execute("""INSERT INTO lucky_reward_stock(guild_id,code,stock_total,stock_available)
                        VALUES($1,$2,$3,$3) ON CONFLICT DO NOTHING""",
                        guild_id, codigo, premio["estoque"])

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
                await ctx.author.send(texto, allowed_mentions=discord.AllowedMentions.none())
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

    async def abrir(self, guild_id: int, usuario_id: int) -> dict:
        # Bloqueio por usuário + decremento condicional do estoque dentro da mesma transação.
        instante = agora()
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                await con.execute("""INSERT INTO lucky_users(guild_id,user_id,next_open_at,window_started_at,opens_used)
                    VALUES($1,$2,$3,NULL,0) ON CONFLICT DO NOTHING""", guild_id, usuario_id, instante)
                membro = await con.fetchrow("""SELECT opens_used,next_open_at,window_started_at
                    FROM lucky_users WHERE guild_id=$1 AND user_id=$2 FOR UPDATE""", guild_id, usuario_id)
                usadas = membro["opens_used"]
                if usadas >= ABERTURAS_POR_CICLO and membro["next_open_at"] > instante:
                    return {"limite": membro["next_open_at"]}
                if usadas >= ABERTURAS_POR_CICLO:
                    usadas = 0
                codigo = sortear_codigo()
                premio = PREMIACOES.get(codigo) if codigo else None
                sem_estoque = False
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
                        (guild_id,reward_code,actor_id,before_stock,after_stock,change_reason,opening_id)
                        VALUES($1,$2,$3,$4,$5,'premiacao',$6)""",
                        guild_id, codigo, usuario_id, disponivel+1, disponivel, abertura_id)
                    await con.execute("""INSERT INTO lucky_wins(opening_id,guild_id,user_id,reward_code,
                        reward_name,reward_rarity,reward_banner_url,role_id,public_pending)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8,TRUE)""",
                        abertura_id, guild_id, usuario_id, codigo, premio["nome"], raridade,
                        premio["banner"], premio["cargo_id"] or None)
                return {"id": abertura_id, "premio": premio, "codigo": codigo,
                        "raridade": raridade, "restantes": ABERTURAS_POR_CICLO-usadas,
                        "renovacao": espera if usadas == ABERTURAS_POR_CICLO else None,
                        "sem_estoque": sem_estoque, "estoque_restante": disponivel if premio else None,
                        "created_at": instante}

    async def ajustar_cargo(self, guild: discord.Guild, membro: discord.Member, abertura: dict):
        premio = abertura["premio"]
        if not CONCEDER_CARGOS_AUTOMATICAMENTE or not premio["cargo_id"]:
            return
        cargo = guild.get_role(premio["cargo_id"])
        if not cargo:
            LOG.warning("Cargo %s não localizado", premio["cargo_id"])
            return
        try:
            if cargo not in membro.roles:
                await membro.add_roles(cargo, reason=f"Lucky Block #{abertura['id']}")
            await self.bot.pool.execute("""UPDATE lucky_wins SET status='delivered',delivered_at=NOW(),
                delivered_by=$2 WHERE opening_id=$1 AND status='pending'""", abertura["id"], self.bot.user.id)
        except discord.HTTPException:
            LOG.exception("Falha na entrega automática do cargo Lucky Block")

    async def avisar_dono_sem_estoque(self, guild: discord.Guild, codigo: str, abertura_id: int,
                                      disponivel: int = 0):
        """Avisa dono/equipe por DM quando o estoque cruza o limiar ou fica zerado."""
        destinatarios = {ID_DONO_DISCORD, *USUARIOS_ALERTA_ESTOQUE}
        ids_cargos = set(CARGOS_ALERTA_ESTOQUE)
        if ids_cargos:
            # O cache pode ser parcial. Quando permitido, consulta os membros via API.
            for membro in guild.members:
                if not membro.bot and any(cargo.id in ids_cargos for cargo in membro.roles):
                    destinatarios.add(membro.id)
            if self.bot.intents.members and not getattr(guild, "chunked", False):
                try:
                    async for membro in guild.fetch_members(limit=None):
                        if not membro.bot and any(cargo.id in ids_cargos for cargo in membro.roles):
                            destinatarios.add(membro.id)
                except (discord.HTTPException, discord.ClientException):
                    LOG.exception("Não foi possível completar a lista de membros dos cargos de alerta")
            else:
                LOG.warning("Aviso de estoque por cargos depende de Server Members Intent para cobertura completa; "
                            "use USUARIOS_ALERTA_ESTOQUE como alternativa")
        premio = PREMIACOES.get(codigo, {})
        esgotado = disponivel == 0
        texto = (("## 📦 ESTOQUE ESGOTADO — LUCKY BLOCK\n\n" if esgotado else
                  "## ⚠️ ESTOQUE BAIXO — LUCKY BLOCK\n\n")
                 + f"> `🎁` **Premiação:** {premio.get('nome', codigo)}\n"
                 + f"> `💎` **Raridade:** {raridade_nome(premio.get('raridade', 'empty'))}\n"
                 + f"> `📉` **Disponível:** {disponivel} unidade(s)\n"
                 + f"> `📜` **Última premiação:** `LB-{abertura_id:06d}`\n\n"
                 + ("> `⚠️` O prêmio ficará indisponível até a próxima reposição.\n" if esgotado else
                    "> `🛎️` Prepare a reposição antes de zerar o estoque.\n")
                 + "-# 👑 Família ROYAL • Alerta privado da equipe")

        async def enviar(destinatario_id: int) -> None:
            try:
                usuario = self.bot.get_user(destinatario_id) or await self.bot.fetch_user(destinatario_id)
                await usuario.send(view=cartao("📦 AVISO DE ESTOQUE", texto),
                                   allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                LOG.warning("Falha na DM de estoque esgotado para usuário %s", destinatario_id)

        await asyncio.gather(*(enviar(uid) for uid in sorted(destinatarios) if uid > 0))

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
            banner = banner_anuncio_premio(raridade, row["reward_banner_url"] or premio.get("banner", ""))
            view = cartao("<a:luck:1575023399833567272> PRÊMIO ESPECIAL ENCONTRADO!", mensagem, banner)
            canal = await self.buscar_canal(guild, CANAL_REGISTROS)
            msg = await enviar_layout(canal.send, view, allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute("""UPDATE lucky_wins SET public_message_id=$2,
                public_claimed_at=NULL,public_pending=FALSE WHERE opening_id=$1""", abertura_id, msg.id)
            if raridade == "secret" and AVISAR_EVERYONE_SECRETOS:
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
        if getattr(msg.flags, "is_components_v2", False):
            await msg.edit(view=view, **anexo_edicao(view))
        else:
            await msg.edit(content=None, embeds=[], view=view, **anexo_edicao(view))

    async def verificar_e_publicar_comprovante(self, ticket: discord.TextChannel, abertura_id: int, usuario_id: int) -> bool:
        # Não publica novamente no mesmo ticket; serve como prova recuperável pela staff.
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                row = await con.fetchrow("""SELECT * FROM lucky_wins
                    WHERE opening_id=$1 AND guild_id=$2 AND user_id=$3 FOR UPDATE""",
                    abertura_id, ticket.guild.id, usuario_id)
                if not row:
                    return False
                if row["ticket_channel_id"] is not None:
                    if int(row["ticket_channel_id"]) == ticket.id:
                        return True
                    # Ticket antigo não existe mais: permite registrar comprovante no novo ticket.
                    if ticket.guild.get_channel(int(row["ticket_channel_id"])) is not None:
                        return False
                # Usa o nome e a raridade salvos no momento do ganho: uma edição
                # futura no catálogo não pode mudar um comprovante antigo.
                atual = PREMIACOES.get(row["reward_code"], {})
                premio = dict(atual,
                    nome=row["reward_name"] or atual.get("nome", row["reward_code"]),
                    raridade=row["reward_rarity"] or atual.get("raridade", "legendary"),
                    banner=row["reward_banner_url"] or atual.get("banner", ""))
                entrada = {"id": abertura_id, "premio": premio,
                           "created_at": row["created_at"], "status": row["status"]}
                view = cartao("🧾 COMPROVANTE OFICIAL DE PREMIAÇÃO",
                              recibo(entrada, usuario_id),
                              banner_individual_premio(row["reward_banner_url"] or premio["banner"], premio["raridade"]))
                # Uma tentativa de mensagem é feita enquanto a linha está bloqueada para evitar duplicatas.
                await enviar_layout(ticket.send, view, allowed_mentions=discord.AllowedMentions.none())
                await con.execute("""UPDATE lucky_wins SET ticket_channel_id=$2,
                    ticket_claimed_at=NOW() WHERE opening_id=$1""", abertura_id, ticket.id)
                return True

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
                for cargo_id in set(tickets.CARGOS_STAFF + tickets.CARGOS_NOTIFICAR):
                    cargo = guild.get_role(cargo_id)
                    if cargo is not None:
                        overwrites[cargo] = discord.PermissionOverwrite(view_channel=True,
                            send_messages=True, read_message_history=True, attach_files=True,
                            embed_links=True, manage_messages=True)
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
                    await self.verificar_e_publicar_comprovante(canal, abertura_id, membro.id)
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
                resultado = await self.abrir(guild_id, interaction.user.id)
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
                        texto += f"\n⏳ Renovação: <t:{int(resultado['renovacao'].timestamp())}:R>"
                    async def resultado_imediato():
                        view = cartao("🎁 PREMIAÇÃO ENCONTRADA", texto,
                                      banner_individual_premio(premio["banner"], premio["raridade"]))
                        linha = discord.ui.ActionRow()
                        linha.add_item(BotaoTicket(guild_id, resultado['id']))
                        view.children[0].add_item(linha)
                        await enviar_layout(interaction.followup.send, view, ephemeral=True)

                    async def etapa(nome, tarefa):
                        try:
                            await tarefa
                        except Exception:
                            LOG.exception("Falha na etapa %s do ganho #%s", nome, resultado['id'])

                    # O resultado e o anúncio não dependem de DM, de cargo ou de alertas privados.
                    await asyncio.gather(
                        etapa("resultado", resultado_imediato()),
                        etapa("anúncio público", self.anuncio(interaction.guild, resultado['id'])),
                        etapa("DM", self.mandar_dm_vencedor(interaction.user, resultado)),
                    )
                    if premio['cargo_id'] and isinstance(interaction.user, discord.Member):
                        await etapa("cargo", self.ajustar_cargo(interaction.guild, interaction.user, resultado))
                    restante = resultado['estoque_restante']
                    if restante == 0 or (LIMIAR_ALERTA_ESTOQUE > 0 and restante == LIMIAR_ALERTA_ESTOQUE):
                        await etapa("estoque baixo", self.avisar_dono_sem_estoque(interaction.guild, resultado['codigo'], resultado['id'], restante))
                    await etapa("comprovante", self.comprovante_em_ticket_existente(interaction.guild, interaction.user.id, resultado['id']))

                else:
                    texto = "A caixa veio vazia, boa sorte na próxima!"
                    if resultado["sem_estoque"]:
                        texto = ("⚠️ Uma recompensa sorteada está sem estoque no momento. "
                                 "Nenhuma premiação foi reservada nesta abertura.")
                    texto += f"\n`🎟️` Restantes: **{resultado['restantes']}/{ABERTURAS_POR_CICLO}**"
                    if resultado["renovacao"]:
                        texto += f"\n⏳ Renovação: <t:{int(resultado['renovacao'].timestamp())}:R>"
                    await self.exibir_revelacao(interaction, "📦 CAIXA VAZIA", texto,
                                               BANNER_CAIXA_VAZIA)
                return
            if acao == "historico":
                saldo, renovacao = await self.obter_saldo(guild_id, interaction.user.id)
                rows = await self.bot.pool.fetch("""SELECT id,reward_code,reward_name,rarity,created_at
                    FROM lucky_openings WHERE guild_id=$1 AND user_id=$2 ORDER BY id DESC LIMIT 10""",
                    guild_id, interaction.user.id)
                linhas = [f"`LB-{r['id']:06d}` · {r['reward_name'] or 'Caixa vazia'} · "
                          f"{raridade_nome(r['rarity'])} · <t:{int(r['created_at'].timestamp())}:R>" for r in rows]
                texto = ("\n".join(linhas) if linhas else "Você ainda não abriu nenhuma caixa.")
                texto += f"\n\n`🎟️` Aberturas disponíveis: **{saldo}/{ABERTURAS_POR_CICLO}**"
                if renovacao:
                    texto += f"\n⏳ Renovação: <t:{int(renovacao.timestamp())}:R>"
                return await interaction.followup.send(view=cartao("📜 MEU HISTÓRICO", texto), ephemeral=True)
            if acao == "ranking":
                view = cartao("🏆 RANKING DA TEMPORADA", await self.texto_ranking(guild_id), BANNER_RANKING)
                return await interaction.followup.send(view=view, ephemeral=True, **anexo_envio(view))
            if acao == "colecao":
                view = cartao("🏅 MINHA COLEÇÃO", await self.texto_colecao(guild_id, interaction.user.id), BANNER_COLECAO)
                return await interaction.followup.send(view=view, ephemeral=True, **anexo_envio(view))
            if acao == "meta":
                view = cartao("🌟 DESAFIO DA FAMÍLIA", await self.texto_meta(guild_id), BANNER_META)
                return await interaction.followup.send(view=view, ephemeral=True, **anexo_envio(view))
            await interaction.followup.send("❌ Ação inválida.", ephemeral=True)
        except Exception:
            LOG.exception("Erro em interação Lucky Block (%s)", acao)
            await interaction.followup.send("❌ Erro interno do Lucky Block. Consulte o log do bot.", ephemeral=True)

    async def resumo_estoques(self, guild_id: int) -> str:
        await self.garantir_guild(guild_id)
        rows = await self.bot.pool.fetch("""SELECT code,stock_total,stock_available
            FROM lucky_reward_stock WHERE guild_id=$1""", guild_id)
        mapa = {row["code"]: row for row in rows}
        return "\n".join(f"`{codigo}` — **{mapa[codigo]['stock_available']} disponíveis** "
              f"(total histórico: {mapa[codigo]['stock_total']})" for codigo in PREMIACOES if codigo in mapa)

    async def alterar_estoque(self, guild_id: int, codigo: str, quantidade: int,
                              actor_id: int = ID_DONO_DISCORD) -> str:
        if actor_id != ID_DONO_DISCORD:
            raise ValueError("Somente o proprietário pode alterar o estoque")
        if codigo not in PREMIACOES or not 0 <= quantidade <= 100_000:
            raise ValueError("Código ou quantidade inválida")
        await self.garantir_guild(guild_id)
        audit_id = None
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                anterior = await con.fetchval("""SELECT stock_available FROM lucky_reward_stock
                    WHERE guild_id=$1 AND code=$2 FOR UPDATE""", guild_id, codigo)
                await con.execute("""UPDATE lucky_reward_stock
                    SET stock_total=GREATEST(0,stock_total-stock_available)+$3,
                        stock_available=$3 WHERE guild_id=$1 AND code=$2""", guild_id, codigo, quantidade)
                if anterior is not None and anterior != quantidade:
                    audit_id = await con.fetchval("""INSERT INTO lucky_stock_audit
                        (guild_id,reward_code,actor_id,before_stock,after_stock,change_reason,notice_pending)
                        VALUES($1,$2,$3,$4,$5,'reposicao_manual',$6) RETURNING id""",
                        guild_id, codigo, actor_id, anterior, quantidade, quantidade > anterior)
        if audit_id is not None and quantidade > anterior:
            try:
                ok = await self.avisar_reposicao(guild_id, audit_id)
            except Exception:
                LOG.exception("Estoque salvo; falha ao iniciar envio da reposição #%s", audit_id)
                ok = False
            return ("📢 Reposição anunciada no canal de estoque." if ok else
                    "⚠️ Estoque salvo; anúncio pendente de envio automático. Verifique o canal e as permissões.")
        return "ℹ️ Sem aumento de estoque; nenhum anúncio público foi gerado."

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
                "\n\n-# Os selos são comemorativos e não concedem recompensas reais.")

    async def texto_ranking(self, guild_id: int, *, mensal: bool = True) -> str:
        restricao = "AND created_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'" if mensal else ""
        rows = await self.bot.pool.fetch(f"""SELECT user_id, COUNT(*) AS total,
            COALESCE(SUM(CASE rarity WHEN 'rare' THEN 10 WHEN 'epic' THEN 100 WHEN 'legendary' THEN 1000
                WHEN 'secret' THEN 10000 ELSE 0 END),0) AS pontos
            FROM lucky_openings WHERE guild_id=$1 {restricao}
            GROUP BY user_id ORDER BY pontos DESC,total DESC,user_id LIMIT 10""", guild_id)
        linhas = '\n'.join(f"**{i}.** <@{r['user_id']}> — **{int(r['pontos'])}** pts ({r['total']} caixas)"
            for i,r in enumerate(rows,1))
        return (f"**☰ {'TEMPORADA ATUAL' if mensal else 'RANKING GERAL'}**\n" +
                (linhas or 'Ainda não houve aberturas neste período.') +
                "\n\n-# Pontos: rara 10 · épica 100 · lendária 1.000 · secreta 10.000. "
                + ('A temporada vira no primeiro dia do mês (UTC).' if mensal else 'Período histórico completo.'))

    async def texto_meta(self, guild_id: int) -> str:
        feitas = await self.bot.pool.fetchval("""SELECT COUNT(*) FROM lucky_openings
            WHERE guild_id=$1 AND created_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""", guild_id)
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
        """Resultado direto, sem suspense, animações intermediárias ou edição de mensagem."""
        view = cartao(titulo, descricao, banner)
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
                  AND status='pending' AND validated_at IS NULL
                RETURNING user_id,ticket_channel_id,reward_name,reward_code,validated_at""",
                guild_id, abertura_id, interaction.user.id)
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
                SET status='delivered',delivered_at=NOW(),delivered_by=$3
                WHERE guild_id=$1 AND opening_id=$2 AND status='pending'
                  AND validated_at IS NOT NULL AND review_reason IS NULL
                RETURNING opening_id,ticket_channel_id""",
                guild_id, abertura_id, interaction.user.id)
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
                      descricao=atual.get('descricao', 'Recompensa histórica.'),
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
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        guild = ctx.guild or await self.guild_oficial()
        texto = await self.resumo_estoques(guild.id)
        await self.dm(ctx, view=PainelEstoque(guild.id, texto))

    @commands.command(name="luckyestoques")
    async def luckyestoques(self, ctx: commands.Context):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        guild = ctx.guild or await self.guild_oficial()
        await self.dm(ctx, texto="📦 **Estoques atuais:**\n" + await self.resumo_estoques(guild.id))

    @commands.command(name="luckyestoque")
    async def luckyestoque(self, ctx: commands.Context, codigo: str, quantidade: int):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        guild = ctx.guild or await self.guild_oficial()
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
            delivered_at=NOW(),delivered_by=$3 WHERE opening_id=$1 AND guild_id=$2
            AND status='pending' AND ($4::bool = FALSE OR (validated_at IS NOT NULL AND review_reason IS NULL))
            RETURNING user_id,reward_code""",
            abertura_id, ctx.guild.id, ctx.author.id, EXIGIR_APROVACAO_ENTREGA_MANUAL)
        if not row:
            return await self.dm(ctx, texto="❌ Registro inexistente, já entregue ou ainda sem aprovação formal.")
        try:
            await self.atualizar_anuncio(ctx.guild, abertura_id)
        except discord.HTTPException:
            LOG.exception("Falha ao atualizar o anúncio entregue")
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
              AND status='pending' AND validated_at IS NULL
            RETURNING opening_id,user_id,reward_name,reward_code,ticket_channel_id,validated_at""",
            guild.id, abertura_id, ctx.author.id)
        if row is None:
            existente = await self.bot.pool.fetchrow("""SELECT validated_at,validated_by,ticket_channel_id
                FROM lucky_wins WHERE guild_id=$1 AND opening_id=$2""", guild.id, abertura_id)
            if existente is None:
                texto = "❌ Protocolo inexistente no banco."
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

    @commands.command(name="luckycolecao")
    @commands.guild_only()
    async def luckycolecao(self, ctx: commands.Context):
        view = cartao('🏅 MINHA COLEÇÃO', await self.texto_colecao(ctx.guild.id, ctx.author.id), BANNER_COLECAO)
        await ctx.send(view=view, **anexo_envio(view), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="luckyranking")
    @commands.guild_only()
    async def luckyranking(self, ctx: commands.Context, periodo: str = 'mensal'):
        mensal = periodo.lower() not in ('geral', 'all', 'total')
        view = cartao('🏆 RANKING ROYAL', await self.texto_ranking(ctx.guild.id, mensal=mensal), BANNER_RANKING)
        await ctx.send(view=view, **anexo_envio(view), allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="luckymeta")
    @commands.guild_only()
    async def luckymeta(self, ctx: commands.Context):
        view = cartao('🌟 META DA FAMÍLIA', await self.texto_meta(ctx.guild.id), BANNER_META)
        await ctx.send(view=view, **anexo_envio(view), allowed_mentions=discord.AllowedMentions.none())

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
                          ("Reposição", BANNER_REPOSICAO), ("Secreto", BANNER_PREMIO_SECRETO)] + [
                              (p['nome'], p['banner']) for p in PREMIACOES.values()]:
            caminho = banner_arquivo(ref)
            linhas.append(f"{'✅' if caminho else '❌'} {nome}: `{caminho.name if isinstance(caminho, Path) else 'URL configurada' if caminho else ref}`")
        wins = await self.bot.pool.fetchval("SELECT COUNT(*) FROM lucky_wins WHERE guild_id=$1 AND public_pending AND public_message_id IS NULL", guild.id)
        stocks = await self.bot.pool.fetchval("SELECT COUNT(*) FROM lucky_stock_audit WHERE guild_id=$1 AND notice_pending AND notice_message_id IS NULL", guild.id)
        linhas.append(f"Fila: {wins} vitórias / {stocks} reposições. Tenta novamente após falhas (reserva de 5 min).")
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
            "reposicao", "sem_estoque", "comprovante", "fluxo", "todos", "vazia"} else codigo
        if codigo == "lista":
            texto = "🧪 **Comandos de teste — privados**\n" + "\n".join(
                f"`!testarlucky {c}` — {p['nome']} [{raridade_nome(p['raridade'])}]" for c,p in PREMIACOES.items())
            texto += ("\n`!testarlucky painel` · `!testarlucky vazia` · `!testarlucky todos`"
                      "\n`!testarlucky sorteio` · `!testarlucky fluxo` · `!testarlucky estoque` · `!testarlucky comprovante` · `!testarlucky sem_estoque` · `!testarlucky reposicao`"
                      "\n`!testarlucky clover registros` (prévia pública sem marcações)"
                      "\n`!testarlucky reposicao estoque` · `!luckydiagnostico`"
                      "\n`!simularlucky nitro_basico` (DM + anúncio idênticos ao real, temporários)"
                      "\n`!luckyvalidar ID` (confere autenticidade) · `!luckyaprovar ID` (aprova, para equipe autorizada)"
                      "\n`!painelresgateslucky` · `!luckypendentes` · `!luckyauditoria` (dono)"
                      "\n`!luckycolecao` · `!luckyranking` · `!luckymeta`")
            return await self.dm(ctx, texto=texto)
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
                "O estoque deve ser atualizado pelo painel privado.", BANNER_CAIXA_VAZIA, teste=True))
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
        """!simularlucky clover — prévias visuais reais, sem sorteio, estoque nem @everyone.

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
        # DM com a mesma apresentação real, sem rótulo; ticket desativado.
        view_dm = mensagem_premio(guild.id, demonstracao, teste=True, visual_real=True)
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
