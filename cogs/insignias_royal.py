from __future__ import annotations

"""Insígnias da Família Royal | edição de Natal.

Requer discord.py >= 2.6 (Components V2) e bot.pool (asyncpg).
Coloque este arquivo na pasta de cogs, mantendo a pasta assets no nível acima.
"""

import logging
import math
from pathlib import Path

import discord
from discord.ext import commands

LOG = logging.getLogger("royal.insignias")
COR_ROYAL = discord.Colour.from_rgb(139, 32, 45)
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
BANNERS = {
    "catalogo": "insignias_royal.png",
    "solicitacao": "insignias_solicitacao_royal.png",
    "decisao": "insignias_decisao_royal.png",
}

# Os dados, IDs e emojis originais foram preservados.
INSIGNIAS = [
    {'nome': 'Noel', 'cargo_id': 1568866728237211668, 'emoji': '🎅', 'titular_id': 0, 'descricao_curta': 'Edição natalina · Permissões especiais.', 'descricao_completa': 'Insígnia especial de Natal da Família Royal. Concede permissões especiais no servidor e sua concessão depende da aprovação do titular escolhido pela administração.'},
    {'nome': 'Natalina', 'cargo_id': 1568866716723839038, 'emoji': '🎄', 'titular_id': 1399464764760920145, 'descricao_curta': 'Edição natalina · Permissões especiais.', 'descricao_completa': 'Insígnia especial de Natal da Família Royal. Concede permissões especiais no servidor e sua concessão depende da aprovação do titular escolhido pela administração.'},
    {'nome': 'Candy', 'cargo_id': 1568866728031559742, 'emoji': '🍬', 'titular_id': 0, 'descricao_curta': 'Edição natalina · Permissões especiais.', 'descricao_completa': 'Insígnia especial de Natal da Família Royal. Concede permissões especiais no servidor e sua concessão depende da aprovação do titular escolhido pela administração.'},
    {'nome': 'Bruna', 'cargo_id': 1554376484637122591, 'emoji': '🌹', 'titular_id': 697068974323793921, 'descricao_curta': 'Fundadora · Lealdade e acolhimento.', 'descricao_completa': "Fundadora da Família Royal, integrante mais antiga e esposa de Sant's. Sua insígnia simboliza acolhimento, confiança e lealdade."},
    {'nome': 'Pietra', 'cargo_id': 1556147238852628562, 'emoji': '💐', 'titular_id': 1295645409082867732, 'descricao_curta': 'Apreço e reconhecimento.', 'descricao_completa': 'Simboliza apreço, reconhecimento e consideração pessoal.'},
    {'nome': 'Kananda', 'cargo_id': 1556147239179518022, 'emoji': '🪽', 'titular_id': 1430221798389059584, 'descricao_curta': 'Companheirismo e proteção.', 'descricao_completa': 'Reconhece laços de companheirismo, cuidado e proteção.'},
    {'nome': 'Tatah', 'cargo_id': 1555370356343312486, 'emoji': '🌙', 'titular_id': 1032084016196763688, 'descricao_curta': 'Confiança e proximidade.', 'descricao_completa': 'Distinção de confiança e proximidade, concedida a critério de Tatah.'},
    {'nome': 'Lívia', 'cargo_id': 1565443617651294278, 'emoji': '🎀', 'titular_id': 1399464764760920145, 'descricao_curta': 'Lealdade e consideração.', 'descricao_completa': 'Expressa lealdade, consideração e vínculos pessoais.'},
    {'nome': 'Nathy', 'cargo_id': 1565443626002026526, 'emoji': '🌵', 'titular_id': 775086637386301524, 'descricao_curta': 'Tengo lengo tengo', 'descricao_completa': 'Simboliza amizade, proximidade e lealdade.'},
    {'nome': 'Soso', 'cargo_id': 1565942565767745699, 'emoji': '🌺', 'titular_id': 1525265476425355337, 'descricao_curta': 'Lealdade e consideração.', 'descricao_completa': 'Representa lealdade e consideração pessoal de um corregedor.'},
    {'nome': "Sant's", 'cargo_id': 1554376496196493342, 'emoji': '👑', 'titular_id': 925863471902503033, 'descricao_curta': 'Criador da Família Royal.', 'descricao_completa': "Distinção pessoal de Sant's, criador da Família Royal. Sua concessão depende de sua autorização."},
    {'nome': 'Ruan', 'cargo_id': 1554376496548941894, 'emoji': '🛡️', 'titular_id': 1348504492345397358, 'descricao_curta': 'Lealdade e consideração.', 'descricao_completa': 'Símbolo de lealdade e consideração pessoal.'},
    {'nome': 'Pato', 'cargo_id': 1556147238986711070, 'emoji': '🦆', 'titular_id': 1459320617852731635, 'descricao_curta': 'quack quack.', 'descricao_completa': 'Expressa amizade e estima pessoal, concedida a critério de Pato.'},
    {'nome': 'Violets', 'cargo_id': 1562498973787230339, 'emoji': '🪐', 'titular_id': 969628191268421672, 'descricao_curta': 'Vínculo e reconhecimento.', 'descricao_completa': 'Representa vínculo especial e reconhecimento.'},
    {'nome': 'Diniz', 'cargo_id': 1563986618207965246, 'emoji': '🌟', 'titular_id': 1546524499430604891, 'descricao_curta': 'Proximidade e apreço.', 'descricao_completa': 'Símbolo de proximidade e apreço pessoal.'},
    {'nome': 'Mateus', 'cargo_id': 1564494650327437363, 'emoji': '🔍', 'titular_id': 1481369480482394223, 'descricao_curta': 'Confiança e consideração.', 'descricao_completa': 'Representa confiança e consideração pessoal.'},
    {'nome': 'Hanz', 'cargo_id': 1564041775000064060, 'emoji': '🔥', 'titular_id': 1004088774810144859, 'descricao_curta': 'Lealdade e consideração.', 'descricao_completa': 'Representa lealdade e consideração pessoal.'},
    {'nome': 'Gostosãodanaty', 'cargo_id': 1565441465243541625, 'emoji': '⚖️', 'titular_id': 529781932976898058, 'descricao_curta': 'Justiça e integridade.', 'descricao_completa': 'Insígnia pessoal de Teteu, juiz do Poder Judiciário, símbolo de justiça, integridade e respeito.'},
    {'nome': 'Golgos', 'cargo_id': 1565443033787277394, 'emoji': '🎥', 'titular_id': 525837977545605132, 'descricao_curta': 'Criatividade e influência.', 'descricao_completa': 'Distinção pessoal de Golgos, editor de vídeo e influenciador, associada à criatividade e à comunicação.'},
    {'nome': 'Dark', 'cargo_id': 1565443625523880137, 'emoji': '🐦\u200d⬛', 'titular_id': 1089646065084534854, 'descricao_curta': 'Lealdade e consideração.', 'descricao_completa': 'Representa lealdade e consideração pessoal de um corregedor.'},
    {'nome': 'PH', 'cargo_id': 1565942574676705330, 'emoji': '❄️', 'titular_id': 896496513251962992, 'descricao_curta': 'Esperança e perseverança', 'descricao_completa': 'Representa lealdade e consideração pessoal de um corregedor.'},
]

INSIGNIAS_NATAL = {
    "noel": 1568866728237211668,
    "natalina": 1568866716723839038,
    "candy": 1568866728031559742,
}

# Mantém as três indicações originais como padrão até um administrador substituir
# o titular com !titularnatal. A configuração do PostgreSQL prevalece.
TITULARES_NATAL_PADRAO = {
    1568866728237211668: 697068974323793921,
    1568866716723839038: 1399464764760920145,
    1568866728031559742: 1430221798389059584,
}

INSIGNIAS_POR_CARGO = {item["cargo_id"]: item for item in INSIGNIAS}
ITENS_POR_CATEGORIA = {
    "natal": [item for item in INSIGNIAS if item["cargo_id"] in INSIGNIAS_NATAL.values()],
    "membros": [item for item in INSIGNIAS if item["cargo_id"] not in INSIGNIAS_NATAL.values()],
}
PAGINA_TAMANHO = 8
TAMANHO_MENSAGEM = 500
SEM_MENCOES = discord.AllowedMentions.none()

# Emojis personalizados já utilizados pelo painel original (não alterados).
EMOJI_NEVE = "<:snowglobe:1570680338101960764>"
EMOJI_ARVORE = "<:tree:1568871853970165820>"
EMOJI_PRESENTE = "<:gift:1570666397745549322>"
EMOJI_COROA = "<a:coroa:1564000189167960177>"


def eh_insignia_natal(cargo_id: int) -> bool:
    return cargo_id in TITULARES_NATAL_PADRAO


def catalogo() -> dict[int, dict]:
    return INSIGNIAS_POR_CARGO


def caminho_banner(tipo: str) -> Path | None:
    preferido = PASTA_ASSETS / BANNERS[tipo]
    if preferido.is_file():
        return preferido
    reserva = PASTA_ASSETS / BANNERS["catalogo"]
    return reserva if reserva.is_file() else None


def painel_com_banner(painel: discord.ui.Container, tipo: str) -> Path | None:
    arquivo = caminho_banner(tipo)
    if arquivo:
        painel.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem(media=f"attachment://{arquivo.name}")
        ))
    return arquivo


async def enviar_layout(destino, view: discord.ui.LayoutView, banner: Path | None):
    """Uma mensagem em Components V2, com banner quando o arquivo existe."""
    if banner:
        with banner.open("rb") as arquivo:
            return await destino.send(
                view=view,
                file=discord.File(arquivo, filename=banner.name),
                allowed_mentions=SEM_MENCOES,
            )
    return await destino.send(view=view, allowed_mentions=SEM_MENCOES)


def texto_seguro(valor: str) -> str:
    """Impede menções involuntárias e formatação injetada pelo solicitante."""
    return discord.utils.escape_markdown(discord.utils.escape_mentions(valor))


def texto_citado(valor: str) -> str:
    if not valor:
        return "> *Nenhuma mensagem adicional.*"
    return "\n".join("> " + linha for linha in texto_seguro(valor).splitlines())


def montar_catalogo(cog: "InsigniasRoyal", com_banner: bool = False) -> discord.ui.LayoutView:
    """Painel público fixo; cada pessoa navega em páginas privadas."""
    view = discord.ui.LayoutView(timeout=None)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    if com_banner:
        painel_com_banner(bloco, "catalogo")

    bloco.add_item(discord.ui.TextDisplay(
        f"## {EMOJI_NEVE}  INSÍGNIAS DA FAMÍLIA ROYAL\n"
        "### EDIÇÃO ESPECIAL DE NATAL\n"
        "╭・✧  **Uma distinção, um vínculo, uma história.**\n"
        "┊  Cada insígnia representa reconhecimento e confiança.\n"
        "╰・✧  Explore os presentes e os símbolos de nossa Família."
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        f"**{EMOJI_ARVORE}  ✦ COLEÇÃO NATALINA ・ EXCLUSIVAS**\n"
        "🎅 <@&1568866728237211668>  ┊  *Espírito de Natal*\n"
        "🎄 <@&1568866716723839038>  ┊  *Celebração Real*\n"
        "🍬 <@&1568866728031559742>  ┊  *Doçura e União*\n"
        "-# Insígnias especiais, com permissões próprias e autorização do titular."
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        f"**{EMOJI_PRESENTE} INSÍGNIAS DOS MEMBROS**\n"
        "Distinções pessoais de integrantes da Família, concedidas mediante aprovação.\n\n"
        "**❄️ COMO PARTICIPAR**\n"
        "`01`  Abra uma das duas coleções abaixo.\n"
        "`02`  Escolha a insígnia e escreva uma mensagem *opcional*.\n"
        "`03`  O titular recebe o pedido na DM e decide aprovar ou recusar.\n"
        "-# ✧ Cada solicitação é individual. Respeite a decisão de seu titular."
    ))
    bloco.add_item(discord.ui.ActionRow(
        AbrirCategoria(cog, "natal"),
        AbrirCategoria(cog, "membros"),
    ))
    bloco.add_item(discord.ui.ActionRow(AbrirMeusPedidos(cog)))
    view.add_item(bloco)
    return view


def montar_pagina(cog: "InsigniasRoyal", categoria: str, pagina: int = 0) -> discord.ui.LayoutView:
    """Navegação privada: não altera o catálogo público para os demais."""
    itens = ITENS_POR_CATEGORIA[categoria]
    total = max(1, math.ceil(len(itens) / PAGINA_TAMANHO))
    pagina = max(0, min(pagina, total - 1))
    exibidos = itens[pagina * PAGINA_TAMANHO:(pagina + 1) * PAGINA_TAMANHO]
    titulo = (f"{EMOJI_ARVORE}  INSÍGNIAS ESPECIAIS / EXCLUSIVAS"
              if categoria == "natal" else f"{EMOJI_COROA}  INSÍGNIAS DOS MEMBROS")
    resumo = ("Distinções sazonais de Natal, autorizadas por seus titulares."
              if categoria == "natal" else "Símbolos pessoais da Família, concedidos por seus titulares.")

    view = discord.ui.LayoutView(timeout=600)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    bloco.add_item(discord.ui.TextDisplay(
        f"## ❄️ {titulo}\n"
        f"> {resumo}\n"
        f"-# 〔 Página {pagina + 1:02d} de {total:02d} 〕 ・ {len(itens)} insígnias no catálogo"
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    linhas = [
        f"{item['emoji']}  <@&{item['cargo_id']}>\n"
        f"　　└・*{texto_seguro(item['descricao_curta'])}*"
        for item in exibidos
    ]
    bloco.add_item(discord.ui.TextDisplay("\n".join(linhas)))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        "**🎄 SOLICITAR INSÍGNIA**\n"
        "Selecione no menu para abrir a ficha com a mensagem opcional.\n"
        "-# A análise será feita pelo titular em mensagem privada."
    ))
    bloco.add_item(discord.ui.ActionRow(InsigniaSelect(cog, exibidos, categoria, pagina)))
    botoes = []
    if pagina > 0:
        botoes.append(NavegarPagina(cog, categoria, pagina - 1, anterior=True))
    if pagina + 1 < total:
        botoes.append(NavegarPagina(cog, categoria, pagina + 1, anterior=False))
    botoes.append(TrocarCategoria(cog, "membros" if categoria == "natal" else "natal"))
    bloco.add_item(discord.ui.ActionRow(*botoes))
    view.add_item(bloco)
    return view


class AbrirCategoria(discord.ui.Button):
    def __init__(self, cog: "InsigniasRoyal", categoria: str):
        titulo = "Especiais / exclusivas" if categoria == "natal" else "Insígnias dos membros"
        emoji = "🎄" if categoria == "natal" else "🎁"
        super().__init__(
            label=titulo, emoji=emoji, style=discord.ButtonStyle.primary,
            custom_id=f"royal:insignias:categoria:{categoria}:v2",
        )
        self.cog = cog
        self.categoria = categoria

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=montar_pagina(self.cog, self.categoria),
            ephemeral=True, allowed_mentions=SEM_MENCOES,
        )


class NavegarPagina(discord.ui.Button):
    def __init__(self, cog: "InsigniasRoyal", categoria: str, pagina: int, *, anterior: bool):
        super().__init__(
            label="Anterior" if anterior else "Próxima",
            emoji="⬅️" if anterior else "➡️",
            style=discord.ButtonStyle.secondary,
        )
        self.cog, self.categoria, self.pagina = cog, categoria, pagina

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            view=montar_pagina(self.cog, self.categoria, self.pagina)
        )


class TrocarCategoria(discord.ui.Button):
    def __init__(self, cog: "InsigniasRoyal", categoria: str):
        super().__init__(
            label="Ver natalinas" if categoria == "natal" else "Ver membros",
            emoji="🎄" if categoria == "natal" else "🎀",
            style=discord.ButtonStyle.secondary,
        )
        self.cog, self.categoria = cog, categoria

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=montar_pagina(self.cog, self.categoria))


class InsigniaSelect(discord.ui.Select):
    """Seleção que abre um modal (inclusive nos painéis antigos v1)."""
    def __init__(self, cog: "InsigniasRoyal", itens: list[dict],
                 categoria: str = "membros", pagina: int = 0, *, legado: bool = False):
        self.cog = cog
        self.categoria = categoria
        self.pagina = pagina
        kwargs_id = {"custom_id": "royal:insignias:selecionar:v1"} if legado else {}
        super().__init__(
            placeholder="🎄 Escolha a insígnia para solicitar…",
            min_values=1, max_values=1,
            **kwargs_id,
            options=[discord.SelectOption(
                label=f"Insígnia {item['nome']}"[:100],
                value=str(item["cargo_id"]),
                description=item["descricao_curta"][:100],
                # O emoji do item continua intocado nos dados e textos.
                # O seletor mantém o fallback Unicode já usado para Dark.
                emoji="🐦" if item["nome"] == "Dark" else item["emoji"],
            ) for item in itens],
        )

    async def callback(self, interaction: discord.Interaction):
        cargo_id = int(self.values[0])
        item = INSIGNIAS_POR_CARGO.get(cargo_id)
        if item is None:
            return await interaction.response.send_message(
                "❌ Esta insígnia não está mais disponível.", ephemeral=True
            )
        await interaction.response.send_modal(SolicitarInsigniaModal(self.cog, item))


class SolicitarInsigniaModal(discord.ui.Modal):
    def __init__(self, cog: "InsigniasRoyal", item: dict):
        super().__init__(title=f"Solicitar insígnia {item['nome']}"[:45], timeout=300)
        self.cog = cog
        self.cargo_id = item["cargo_id"]
        self.mensagem = discord.ui.TextInput(
            label="Mensagem ao titular (opcional)",
            placeholder="Por que você gostaria de receber esta insígnia?",
            style=discord.TextStyle.paragraph,
            required=False, max_length=TAMANHO_MENSAGEM,
        )
        self.add_item(self.mensagem)

    async def on_submit(self, interaction: discord.Interaction):
        mensagem = (self.mensagem.value or "").strip()
        await self.cog.solicitar(interaction, self.cargo_id, mensagem)


class AbrirMeusPedidos(discord.ui.Button):
    def __init__(self, cog: "InsigniasRoyal"):
        super().__init__(
            label="Meus pedidos pendentes", emoji="📜",
            style=discord.ButtonStyle.secondary,
            custom_id="royal:insignias:meus-pedidos:v2",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.mostrar_meus_pedidos(interaction)


class CancelarPedidoSelect(discord.ui.Select):
    def __init__(self, cog: "InsigniasRoyal", registros):
        super().__init__(
            placeholder="❌ Selecione um pedido para cancelar",
            min_values=1, max_values=1,
            options=[discord.SelectOption(
                label=f"Insígnia {r['insignia_name']}"[:100],
                value=str(r["id"]),
                description=f"Pedido #{r['id']}"[:100],
                emoji="❄️",
            ) for r in registros[:25]],
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.cancelar_pedido(interaction, int(self.values[0]))


def montar_meus_pedidos(cog: "InsigniasRoyal", registros) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=300)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    bloco.add_item(discord.ui.TextDisplay(
        f"## {EMOJI_PRESENTE} MEUS PEDIDOS DE INSÍGNIAS\n"
        "**❄️ 〔 ACOMPANHAMENTO 〕**\n"
        "Confira suas solicitações ainda aguardando resposta do titular."
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    if registros:
        bloco.add_item(discord.ui.TextDisplay("\n".join(
            f"✦ **{texto_seguro(r['insignia_name'])}** · pedido `#{r['id']}` "
            f"· <t:{int(r['created_at'].timestamp())}:R>"
            for r in registros[:25]
        )))
        bloco.add_item(discord.ui.TextDisplay(
            "-# Se cancelar, o titular não poderá mais aprovar este pedido."
        ))
        bloco.add_item(discord.ui.ActionRow(CancelarPedidoSelect(cog, registros)))
    else:
        bloco.add_item(discord.ui.TextDisplay(
            "🎄 Você não possui solicitações pendentes.\n"
            "-# Abra uma das coleções no painel para solicitar uma insígnia."
        ))
    view.add_item(bloco)
    return view


def montar_pedido(cog: "InsigniasRoyal", pedido_id: int, item: dict,
                   solicitante: int, servidor: str, mensagem: str = "",
                   com_banner: bool = False) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    if com_banner:
        painel_com_banner(bloco, "solicitacao")
    bloco.add_item(discord.ui.TextDisplay(
        f"## {EMOJI_COROA} PEDIDO DE INSÍGNIA · NATAL\n"
        "**❄️ 〔 NOVA SOLICITAÇÃO 〕**\n"
        f"> {item['emoji']} **Insígnia {texto_seguro(item['nome'])}**\n"
        f"> 👤 Solicitante: <@{solicitante}>\n"
        f"> 🏰 Comunidade: **{texto_seguro(servidor or 'Família Royal')}**\n"
        f"> 📜 Registro: `#{pedido_id}`"
    ))
    bloco.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    bloco.add_item(discord.ui.TextDisplay(
        f"**🎄 ✦ SIGNIFICADO DA DISTINÇÃO**\n{item['descricao_completa']}\n\n"
        f"**💌 ✦ MENSAGEM DO SOLICITANTE**\n{texto_citado(mensagem)}\n\n"
        "-# ✧ A decisão de conceder a insígnia é exclusiva do titular."
    ))
    aprovar = discord.ui.Button(
        label="Aprovar", emoji="✅", style=discord.ButtonStyle.success,
        custom_id=f"royal:insig:aprovar:{pedido_id}",
    )
    recusar = discord.ui.Button(
        label="Recusar", emoji="✖️", style=discord.ButtonStyle.danger,
        custom_id=f"royal:insig:recusar:{pedido_id}",
    )

    async def aprovar_cb(interaction: discord.Interaction):
        await cog.decidir(interaction, pedido_id, aprovar=True)

    async def recusar_cb(interaction: discord.Interaction):
        await cog.decidir(interaction, pedido_id, aprovar=False)

    aprovar.callback = aprovar_cb
    recusar.callback = recusar_cb
    bloco.add_item(discord.ui.ActionRow(aprovar, recusar))
    view.add_item(bloco)
    return view


def montar_resultado(pedido, estado: str, *,
                     com_banner: bool = False) -> discord.ui.LayoutView:
    configuracoes = {
        "approved": ("✅ APROVADA", "🎁 A insígnia foi concedida com autorização do titular."),
        "rejected": ("📜 NÃO APROVADA", "❄️ Solicitação encerrada por decisão do titular."),
        "cancelled": ("🚫 CANCELADA", "📜 Solicitação cancelada por quem a enviou."),
    }
    titulo, explicacao = configuracoes[estado]
    view = discord.ui.LayoutView(timeout=None)
    bloco = discord.ui.Container(accent_colour=COR_ROYAL)
    if com_banner:
        painel_com_banner(bloco, "decisao")
    bloco.add_item(discord.ui.TextDisplay(
        f"## {EMOJI_NEVE} {titulo}\n"
        "**🎄 〔 REGISTRO DA FAMÍLIA ROYAL 〕**\n"
        f"> ✦ Insígnia: **{texto_seguro(pedido['insignia_name'])}**\n"
        f"> 👤 Solicitante: <@{pedido['requester_id']}>\n"
        f"> 📜 Pedido: `#{pedido['id']}`\n\n"
        f"{explicacao}\n"
        "-# ✧ Honra · União · Lealdade"
    ))
    view.add_item(bloco)
    return view


def montar_legado(cog: "InsigniasRoyal") -> discord.ui.LayoutView:
    """Preserva os menus publicados antes desta atualização (ID v1)."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.ActionRow(
        InsigniaSelect(cog, INSIGNIAS[:25], legado=True)
    ))
    return view


class InsigniasRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def pool(self):
        pool = getattr(self.bot, "pool", None)
        if pool is None:
            raise RuntimeError("PostgreSQL indisponível: confira DATABASE_URL e bot.pool.")
        return pool

    async def cog_load(self):
        pool = self.pool()
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_insignia_requests (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                requester_id BIGINT NOT NULL,
                owner_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                insignia_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                dm_message_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                decided_at TIMESTAMPTZ
            )
        """)
        # Migração compatível com pedidos anteriores; não perde registros existentes.
        await pool.execute("""
            ALTER TABLE royal_insignia_requests
            ADD COLUMN IF NOT EXISTS message_text TEXT NOT NULL DEFAULT ''
        """)
        await pool.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS royal_insignia_pending_unique
            ON royal_insignia_requests(guild_id, requester_id, role_id)
            WHERE status IN ('pending', 'processing')
        """)
        await pool.execute("""
            CREATE TABLE IF NOT EXISTS royal_christmas_insignia_owners (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                owner_id BIGINT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (guild_id, role_id),
                UNIQUE (guild_id, owner_id)
            )
        """)

        # Se o bot caiu entre adicionar o cargo e atualizar o banco, o novo
        # clique verifica o cargo primeiro: não o concede em duplicidade.
        await pool.execute("""
            UPDATE royal_insignia_requests
            SET status='pending', decided_at=NULL
            WHERE status='processing'
        """)

        self.bot.add_view(montar_catalogo(self, com_banner=False))
        self.bot.add_view(montar_legado(self))

        pendentes = await pool.fetch("""
            SELECT id, guild_id, insignia_name, requester_id, role_id,
                   message_text, dm_message_id
            FROM royal_insignia_requests
            WHERE status='pending' AND dm_message_id IS NOT NULL
        """)
        for pedido in pendentes:
            item = INSIGNIAS_POR_CARGO.get(pedido["role_id"])
            if item is None:
                item = {
                    "nome": pedido["insignia_name"], "emoji": "👑",
                    "descricao_completa": "Distinção pessoal da Família Royal.",
                }
            self.bot.add_view(
                montar_pedido(
                    self, pedido["id"], item, pedido["requester_id"],
                    "Família Royal", pedido["message_text"], com_banner=False,
                ),
                message_id=pedido["dm_message_id"],
            )
        LOG.info("Insígnias Royal iniciadas (%d pedidos aguardando).", len(pendentes))

    async def obter_titular(self, guild_id: int, cargo_id: int, item: dict) -> int:
        if not eh_insignia_natal(cargo_id):
            return item["titular_id"]
        configurado = await self.pool().fetchval("""
            SELECT owner_id FROM royal_christmas_insignia_owners
            WHERE guild_id=$1 AND role_id=$2
        """, guild_id, cargo_id)
        return configurado or TITULARES_NATAL_PADRAO.get(cargo_id, 0)

    async def solicitar(self, interaction: discord.Interaction,
                        cargo_id: int, mensagem: str = ""):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Use o painel dentro do servidor da Família Royal.", ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)

        item = INSIGNIAS_POR_CARGO.get(cargo_id)
        if item is None:
            return await interaction.followup.send("❌ Insígnia indisponível.", ephemeral=True)

        guild = interaction.guild
        membro = interaction.user if isinstance(interaction.user, discord.Member) else None
        if membro is None:
            membro = guild.get_member(interaction.user.id)
        if membro is None:
            try:
                membro = await guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                return await interaction.followup.send("❌ Você precisa estar no servidor.", ephemeral=True)
        if membro.bot:
            return await interaction.followup.send("❌ Bots não podem solicitar insígnias.", ephemeral=True)

        cargo = guild.get_role(cargo_id)
        if cargo is None:
            return await interaction.followup.send("❌ Cargo não encontrado no servidor.", ephemeral=True)
        if cargo in membro.roles:
            return await interaction.followup.send("✅ Você já possui esta insígnia.", ephemeral=True)

        titular_id = await self.obter_titular(guild.id, cargo_id, item)
        if not titular_id:
            return await interaction.followup.send(
                "⚠️ O titular desta insígnia ainda não foi definido.", ephemeral=True,
            )
        if titular_id == membro.id:
            return await interaction.followup.send(
                "🎄 Você já é o titular desta insígnia.", ephemeral=True,
            )

        mensagem = (mensagem or "").strip()[:TAMANHO_MENSAGEM]
        pool = self.pool()
        pedido = await pool.fetchrow("""
            INSERT INTO royal_insignia_requests
                (guild_id, requester_id, owner_id, role_id, insignia_name, message_text)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT DO NOTHING RETURNING id
        """, guild.id, membro.id, titular_id, cargo_id, item["nome"], mensagem)
        if pedido is None:
            return await interaction.followup.send(
                "⏳ Já existe um pedido pendente para esta insígnia. "
                "Use **Meus pedidos pendentes** para acompanhar ou cancelar.", ephemeral=True,
            )

        pedido_id = pedido["id"]
        banner = caminho_banner("solicitacao")
        try:
            titular = await self.bot.fetch_user(titular_id)
            dm = await enviar_layout(
                titular,
                montar_pedido(
                    self, pedido_id, item, membro.id, guild.name, mensagem,
                    com_banner=bool(banner),
                ),
                banner,
            )
        except (discord.HTTPException, OSError) as exc:
            await pool.execute("""
                DELETE FROM royal_insignia_requests
                WHERE id=$1 AND status='pending'
            """, pedido_id)
            LOG.warning("Falha ao enviar pedido #%s para %s: %s", pedido_id, titular_id, exc)
            return await interaction.followup.send(
                "❌ Não consegui entregar a solicitação na DM do titular. "
                "Ele pode estar com mensagens privadas desativadas.", ephemeral=True,
            )

        try:
            await pool.execute("""
                UPDATE royal_insignia_requests
                SET dm_message_id=$1 WHERE id=$2
            """, dm.id, pedido_id)
        except Exception:
            LOG.exception("Falha ao atualizar o envio do pedido #%s no PostgreSQL.", pedido_id)
            try:
                await dm.delete()
            except discord.HTTPException:
                LOG.warning("Não foi possível apagar a DM do pedido #%s.", pedido_id)
            try:
                await pool.execute("""
                    DELETE FROM royal_insignia_requests
                    WHERE id=$1 AND status='pending'
                """, pedido_id)
            except Exception:
                LOG.exception("Não foi possível liberar o pedido #%s após a falha.", pedido_id)
            return await interaction.followup.send(
                "❌ A solicitação não pôde ser registrada no banco de dados. "
                "Tente novamente mais tarde.", ephemeral=True,
            )

        self.bot.add_view(
            montar_pedido(self, pedido_id, item, membro.id, guild.name, mensagem),
            message_id=dm.id,
        )
        await interaction.followup.send(
            f"🎄 **Solicitação enviada!**\n"
            f"{item['emoji']} **Insígnia {item['nome']}** · pedido `#{pedido_id}`\n"
            f"💌 {'Sua mensagem foi enviada junto ao pedido.' if mensagem else 'Nenhuma mensagem adicional foi incluída.'}\n"
            "-# O titular recebeu a solicitação e poderá aprovar ou recusar.",
            ephemeral=True, allowed_mentions=SEM_MENCOES,
        )

    async def decidir(self, interaction: discord.Interaction, pedido_id: int,
                      *, aprovar: bool):
        await interaction.response.defer(ephemeral=True, thinking=True)
        pool = self.pool()
        pedido = await pool.fetchrow(
            "SELECT * FROM royal_insignia_requests WHERE id=$1", pedido_id
        )
        if pedido is None:
            return await interaction.followup.send("❌ Pedido não encontrado.", ephemeral=True)
        if interaction.user.id != pedido["owner_id"]:
            return await interaction.followup.send(
                "⛔ Apenas o titular pode decidir sobre esta insígnia.", ephemeral=True,
            )
        if pedido["status"] != "pending":
            return await interaction.followup.send(
                "📜 Este pedido já foi processado ou cancelado.", ephemeral=True,
            )

        novo_status = "processing" if aprovar else "rejected"
        alterado = await pool.fetchrow("""
            UPDATE royal_insignia_requests
            SET status=$2, decided_at=now()
            WHERE id=$1 AND status='pending' RETURNING id
        """, pedido_id, novo_status)
        if alterado is None:
            return await interaction.followup.send(
                "⏳ O pedido foi decidido em outra interação.", ephemeral=True,
            )

        if aprovar:
            try:
                guild = self.bot.get_guild(pedido["guild_id"])
                if guild is None:
                    raise RuntimeError("O servidor não está disponível para o bot.")
                cargo = guild.get_role(pedido["role_id"])
                if cargo is None:
                    raise RuntimeError("O cargo da insígnia não foi encontrado.")
                me = guild.me
                if me is None and self.bot.user is not None:
                    me = await guild.fetch_member(self.bot.user.id)
                if me is None or not me.guild_permissions.manage_roles:
                    raise RuntimeError("O bot não possui a permissão Gerenciar Cargos.")
                if cargo >= me.top_role:
                    raise RuntimeError("Coloque o cargo do bot acima da insígnia no Discord.")

                membro = guild.get_member(pedido["requester_id"])
                if membro is None:
                    membro = await guild.fetch_member(pedido["requester_id"])
                # Idempotente se o processo caiu após a entrega do cargo.
                if cargo not in membro.roles:
                    await membro.add_roles(
                        cargo,
                        reason=f"Insígnia {pedido['insignia_name']} aprovada pelo titular {interaction.user.id}",
                    )
                await pool.execute("""
                    UPDATE royal_insignia_requests
                    SET status='approved' WHERE id=$1 AND status='processing'
                """, pedido_id)
            except (discord.HTTPException, RuntimeError) as exc:
                await pool.execute("""
                    UPDATE royal_insignia_requests
                    SET status='pending', decided_at=NULL
                    WHERE id=$1 AND status='processing'
                """, pedido_id)
                LOG.warning("Não foi possível aprovar o pedido #%s: %s", pedido_id, exc)
                return await interaction.followup.send(
                    f"❌ Não foi possível entregar a insígnia: {texto_seguro(str(exc))[:180]}",
                    ephemeral=True,
                )

        estado = "approved" if aprovar else "rejected"
        await interaction.followup.send(
            f"{'✅ Insígnia concedida!' if aprovar else '📜 Solicitação recusada.'} "
            f"Pedido `#{pedido_id}` registrado.", ephemeral=True,
        )
        try:
            solicitante = await self.bot.fetch_user(pedido["requester_id"])
            banner = caminho_banner("decisao")
            await enviar_layout(
                solicitante, montar_resultado(pedido, estado, com_banner=bool(banner)), banner,
            )
        except (discord.HTTPException, OSError) as exc:
            LOG.info("Não foi possível notificar o solicitante %s: %s", pedido["requester_id"], exc)
        if interaction.message is not None:
            try:
                await interaction.message.edit(
                    view=montar_resultado(pedido, estado),
                    attachments=[], allowed_mentions=SEM_MENCOES,
                )
            except discord.HTTPException:
                LOG.warning("Não foi possível atualizar a DM de decisão #%s", pedido_id)

    async def mostrar_meus_pedidos(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Abra este painel dentro do servidor da Família.", ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        registros = await self.pool().fetch("""
            SELECT id, insignia_name, created_at
            FROM royal_insignia_requests
            WHERE guild_id=$1 AND requester_id=$2 AND status='pending'
            ORDER BY created_at DESC LIMIT 25
        """, interaction.guild.id, interaction.user.id)
        await interaction.followup.send(
            view=montar_meus_pedidos(self, registros),
            ephemeral=True, allowed_mentions=SEM_MENCOES,
        )

    async def cancelar_pedido(self, interaction: discord.Interaction, pedido_id: int):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Solicitação inválida fora do servidor.", ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True, thinking=True)
        pedido = await self.pool().fetchrow("""
            UPDATE royal_insignia_requests
            SET status='cancelled', decided_at=now()
            WHERE id=$1 AND guild_id=$2 AND requester_id=$3 AND status='pending'
            RETURNING *
        """, pedido_id, interaction.guild.id, interaction.user.id)
        if pedido is None:
            return await interaction.followup.send(
                "⚠️ Este pedido não está mais pendente.", ephemeral=True,
            )
        await interaction.followup.send(
            f"🚫 Solicitação da **Insígnia {texto_seguro(pedido['insignia_name'])}** "
            "cancelada. O titular não poderá mais aprová-la.",
            ephemeral=True, allowed_mentions=SEM_MENCOES,
        )
        # Remove botões da DM original sempre que possível.
        if pedido["dm_message_id"]:
            try:
                titular = await self.bot.fetch_user(pedido["owner_id"])
                canal_dm = await titular.create_dm()
                mensagem = await canal_dm.fetch_message(pedido["dm_message_id"])
                await mensagem.edit(
                    view=montar_resultado(pedido, "cancelled"),
                    attachments=[], allowed_mentions=SEM_MENCOES,
                )
            except discord.HTTPException:
                LOG.info("Não foi possível remover os botões do pedido #%s cancelado.", pedido_id)

    async def publicar(self, ctx: commands.Context, canal: discord.TextChannel):
        me = canal.guild.me
        if me is None and self.bot.user is not None:
            me = await canal.guild.fetch_member(self.bot.user.id)
        if me is None:
            return await ctx.reply("❌ Bot não encontrado no servidor.", mention_author=False)
        perms = canal.permissions_for(me)
        if not (perms.view_channel and perms.send_messages):
            return await ctx.reply(
                "❌ Preciso das permissões Ver Canal e Enviar Mensagens.",
                mention_author=False,
            )
        banner = caminho_banner("catalogo")
        if banner and not perms.attach_files:
            return await ctx.reply("❌ Preciso da permissão Anexar Arquivos.", mention_author=False)
        try:
            await enviar_layout(canal, montar_catalogo(self, bool(banner)), banner)
        except (discord.HTTPException, OSError):
            LOG.exception("Não foi possível publicar as insígnias.")
            return await ctx.reply(
                "❌ Falha ao publicar o painel. Confira os logs.", mention_author=False,
            )
        await ctx.reply(
            f"✅ Painel natalino de insígnias publicado em {canal.mention}.",
            mention_author=False,
        )

    @commands.command(name="titularnatal")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def titularnatal(self, ctx: commands.Context, nome: str | None = None,
                           titular: discord.Member | None = None):
        """!titularnatal Noel @membro | sem argumentos: mostra os titulares."""
        if nome is None:
            linhas = ["🎄 **〔 TITULARES DAS INSÍGNIAS NATALINAS 〕**"]
            for chave, role_id in INSIGNIAS_NATAL.items():
                dono_id = await self.obter_titular(ctx.guild.id, role_id, INSIGNIAS_POR_CARGO[role_id])
                linhas.append(
                    f"✦ **{chave.capitalize()}** · <@&{role_id}> ┊ "
                    + (f"<@{dono_id}>" if dono_id else "Ainda não definido")
                )
            linhas.append("\n-# Para alterar: `!titularnatal Noel @membro`")
            return await ctx.reply(
                "\n".join(linhas), mention_author=False, allowed_mentions=SEM_MENCOES,
            )

        cargo_id = INSIGNIAS_NATAL.get(nome.casefold())
        if cargo_id is None:
            return await ctx.reply(
                "❌ Escolha `Noel`, `Natalina` ou `Candy`.", mention_author=False,
            )
        if titular is None or titular.bot:
            return await ctx.reply(
                f"❌ Utilize `!titularnatal {nome.capitalize()} @membro` com um membro válido.",
                mention_author=False,
            )
        if ctx.guild.get_role(cargo_id) is None:
            return await ctx.reply(
                "❌ O cargo desta insígnia não existe no servidor.", mention_author=False,
            )

        atual = await self.obter_titular(ctx.guild.id, cargo_id, INSIGNIAS_POR_CARGO[cargo_id])
        if atual != titular.id:
            existe = await self.pool().fetchval("""
                SELECT COUNT(*) FROM royal_insignia_requests
                WHERE guild_id=$1 AND role_id=$2 AND status IN ('pending', 'processing')
            """, ctx.guild.id, cargo_id)
            if existe:
                return await ctx.reply(
                    "⚠️ Finalize os pedidos pendentes antes de trocar o titular.",
                    mention_author=False,
                )
        for outro_cargo in INSIGNIAS_NATAL.values():
            if outro_cargo == cargo_id:
                continue
            outro_dono = await self.obter_titular(
                ctx.guild.id, outro_cargo, INSIGNIAS_POR_CARGO[outro_cargo]
            )
            if outro_dono == titular.id:
                return await ctx.reply(
                    "❌ Essa pessoa já é titular de outra insígnia natalina.",
                    mention_author=False,
                )

        await self.pool().execute("""
            INSERT INTO royal_christmas_insignia_owners (guild_id, role_id, owner_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, role_id)
            DO UPDATE SET owner_id=EXCLUDED.owner_id, updated_at=now()
        """, ctx.guild.id, cargo_id, titular.id)
        await ctx.reply(
            f"🎄 O titular da **Insígnia {nome.capitalize()}** agora é {titular.mention}.",
            mention_author=False, allowed_mentions=SEM_MENCOES,
        )

    @commands.command(name="atualizarinsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def atualizarinsignias(self, ctx: commands.Context):
        """Responda ao painel antigo com !atualizarinsignias, sem criar cópia."""
        referencia = ctx.message.reference
        if referencia is None or referencia.message_id is None:
            return await ctx.reply(
                "❌ Responda à mensagem do painel com `!atualizarinsignias`.",
                mention_author=False,
            )
        try:
            mensagem = await ctx.channel.fetch_message(referencia.message_id)
            if self.bot.user is None or mensagem.author.id != self.bot.user.id:
                raise RuntimeError("O painel precisa ter sido publicado por este bot.")
            if not getattr(mensagem.flags, "components_v2", False):
                raise RuntimeError("A mensagem escolhida não utiliza Components V2.")
            conteudo_antigo = discord.ui.LayoutView.from_message(mensagem, timeout=None)
            trechos = [
                item.content for item in conteudo_antigo.walk_children()
                if isinstance(item, discord.ui.TextDisplay)
            ]
            if not any("INSÍGNIAS DA FAMÍLIA ROYAL" in trecho for trecho in trechos):
                raise RuntimeError("Essa mensagem não parece ser o painel de insígnias.")
            banner = caminho_banner("catalogo")
            if banner is None:
                await mensagem.edit(
                    view=montar_catalogo(self), attachments=[],
                    allowed_mentions=SEM_MENCOES,
                )
            else:
                me = ctx.guild.me or await ctx.guild.fetch_member(self.bot.user.id)
                if not ctx.channel.permissions_for(me).attach_files:
                    raise RuntimeError("Preciso da permissão Anexar Arquivos.")
                with banner.open("rb") as arquivo:
                    await mensagem.edit(
                        view=montar_catalogo(self, com_banner=True),
                        attachments=[discord.File(arquivo, filename=banner.name)],
                        allowed_mentions=SEM_MENCOES,
                    )
        except (discord.DiscordException, RuntimeError, OSError, ValueError) as exc:
            LOG.exception("Falha ao atualizar o painel de insígnias")
            return await ctx.reply(
                f"❌ Não foi possível atualizar: {texto_seguro(str(exc))[:200]}",
                mention_author=False,
            )
        await ctx.reply(
            f"✅ Painel atualizado sem duplicação: {mensagem.jump_url}",
            mention_author=False,
        )

    @commands.command(name="painelinsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def painelinsignias(self, ctx: commands.Context, canal: discord.TextChannel):
        await self.publicar(ctx, canal)

    @commands.command(name="previainsignias")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def previainsignias(self, ctx: commands.Context):
        if isinstance(ctx.channel, discord.TextChannel):
            await self.publicar(ctx, ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(InsigniasRoyal(bot))
