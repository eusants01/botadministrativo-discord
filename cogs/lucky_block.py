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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord.ext import commands

LOG = logging.getLogger("sants.bot.lucky_block")

# ========================= CONFIGURAÇÃO PRIVADA =========================
CANAL_PAINEL = 1572785659108917439
CANAL_REGISTROS = 1572355776377266176
CANAL_ESTOQUE = 1573584140719357972  # Avisos públicos de reposição
ID_DONO_DISCORD = 925863471902503033  # Única conta autorizada a consultar/alterar estoque
ABERTURAS_POR_CICLO = 5
HORAS_APOS_ULTIMA_ABERTURA = 8  # a espera começa SOMENTE após a 5ª abertura
BANNER_PAINEL = "assets/lucky_block/painel.png"
BANNER_CAIXA_VAZIA = "caixa_vazia"
BANNER_PREMIO_SECRETO = "recompensa_secreta"  # assets/lucky_block/recompensa_secreta.png
# O banner secreto aparece no anúncio público. A DM preserva a imagem individual do prêmio.
AVISAR_EVERYONE_SECRETOS = True
CONCEDER_CARGOS_AUTOMATICAMENTE = True
# Todas as chances são percentuais ABSOLUTAS por abertura; não são pesos relativos.
# Os valores abaixo conservam as chances da última versão fornecida pelo usuário.
# "estoque" é inicial SOMENTE para prêmios ainda não existentes no banco.
# O estoque atual passa a ser administrado pelo painel privado e nunca é reabastecido no reinício.
PREMIACOES = {
    "candidato_divisao": dict(nome="Candidato em uma divisão", raridade="epic", chance="0.0050", estoque=2, cargo_id=0, banner="", ativo=True,
                               descricao="Candidatura em divisão do E.B; requisitos sujeitos à validação da equipe."),
    "sub_civil": dict(nome="Sub Civil", raridade="legendary", chance="0.030", estoque=1, cargo_id=0, banner="", ativo=True,
                      descricao="Sub Civil no E.B. A equipe confirmará as condições no ticket."),
    "nitro_basico": dict(nome="Discord Nitro Básico", raridade="secret", chance="0.00015", estoque=1, cargo_id=0, banner="", ativo=True,
                         descricao="Nitro Básico; resgate sujeito à elegibilidade e disponibilidade."),
    "nitro_normal": dict(nome="Discord Nitro Normal", raridade="secret", chance="0.00018", estoque=1, cargo_id=0, banner="", ativo=True,
                         descricao="Nitro Normal; resgate sujeito à elegibilidade e disponibilidade."),
    "500_robux": dict(nome="500 Robux", raridade="secret", chance="0.00015", estoque=1, cargo_id=0, banner="", ativo=True,
                      descricao="500 Robux; a forma de entrega será acertada no ticket."),
    "clover": dict(nome="Clover", raridade="legendary", chance="0.2", estoque=1,
                   cargo_id=1572848152548085871, banner="", ativo=True,
                   descricao="Cargo exclusivo Clover da Família ROYAL."),
    "demon_night": dict(nome="Demon Night", raridade="legendary", chance="0.001", estoque=1,
                        cargo_id=1569948996573597726, banner="", ativo=True,
                        descricao="Cargo exclusivo Demon Night da Família ROYAL."),
    "decoracao_perfil": dict(nome="Decoração de Perfil Aleatória (Discord)", raridade="legendary", chance="0.00035", estoque=1,
                             cargo_id=0, banner="", ativo=True,
                             descricao="Decoração de perfil aleatória; entrega sujeita à disponibilidade."),
}
# ========================================================================

TOTAL_SORTEIO = 10_000_000  # 0.00001% por bilhete
CORES = discord.Colour.from_rgb(91, 79, 187)
RARIDADES = {"empty": ("Caixa vazia", 0), "epic": ("Épica", 100),
             "legendary": ("Lendária", 1000), "secret": ("Secreta", 10000),
             "rare": ("Rara", 10)}
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"
EXTENSOES = (".png", ".jpg", ".jpeg", ".webp", ".gif")

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
                    and arquivo.stem.casefold() == base.stem.casefold()
                    and (not base.suffix or arquivo.suffix.casefold() == base.suffix.casefold())
                    and arquivo.resolve().is_relative_to(PASTA_ASSETS.resolve())):
                    return arquivo
    LOG.warning("Banner não localizado em assets: %s", referencia)
    return None


def adicionar_banner(container: discord.ui.Container, ref: str) -> Path | None:
    caminho = banner_arquivo(ref)
    if caminho:
        galeria = discord.ui.MediaGallery()
        galeria.add_item(media=f"attachment://{caminho.name}" if isinstance(caminho, Path) else caminho,
                         description="Família ROYAL • Lucky Block")
        container.add_item(galeria)
    return caminho if isinstance(caminho, Path) else None


def anexo_envio(view: discord.ui.LayoutView) -> dict:
    caminho = getattr(view, "_lucky_banner", None)
    return {"file": discord.File(str(caminho), filename=caminho.name)} if caminho else {}


def anexo_edicao(view: discord.ui.LayoutView) -> dict:
    caminho = getattr(view, "_lucky_banner", None)
    return {"attachments": [discord.File(str(caminho), filename=caminho.name)]} if caminho else {"attachments": []}


def banner_anuncio_premio(raridade: str, banner_individual: str) -> str:
    """Exibe a arte especial em ganhos secretos sem alterar a DM individual."""
    return BANNER_PREMIO_SECRETO if raridade == "secret" else banner_individual


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
    return (
        "**☰ IDENTIFICAÇÃO DO GANHADOR**\n"
        f"> `👤` **Beneficiário:** <@{membro_id}>\n"
        f"> `🆔` **ID do Discord:** `{membro_id}`\n"
        f"> `📜` **Protocolo único:** `{registro}`\n"
        f"> `📅` **Data do sorteio:** <t:{int(data.timestamp())}:F>\n\n"
        "**☰ INFORMAÇÕES DA PREMIAÇÃO**\n"
        f"> `🎁` **Recompensa:** {premio['nome']}\n"
        f"> `💎` **Raridade:** {raridade_nome(premio['raridade'])}\n"
        f"> `📋` **Situação:** {status}\n\n"
        "**☰ AUTENTICIDADE E RESGATE**\n"
        "> `🔐` Este comprovante é **individual e intransferível**.\n"
        "> `🎟️` A entrega é conferida pela equipe neste ticket.\n"
        "> `✅` A administração valida o protocolo no banco com `!luckyvalidar ID`.\n"
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
            aviso + "## <:luckblock:1572868783725609083> LUCKY BLOCK - FAMÍLIA ROYAL\n\n"
            "Teste sua sorte nas Lucky Blocks e concorra a prêmios exclusivos. "
            "Você possui **5 aberturas**; ao terminar as cinco, novas tentativas "
            "ficam disponíveis **8 horas depois da última abertura**.\n\n"
            "### Premiações\n"
            "> ☰ `👹` Cargos exclusivos da Família ROYAL\n"
            "> ☰ `💜` Discord Nitro (Básico ou Normal)\n"
            "> ☰ `🎨` Decoração de perfil\n"
            "> ☰ `🤓` Sub Civil no E.B ou candidato de divisão\n"
            "> ☰ `💸` 500 Robux\n\n"
            "### Observações\n"
            "> ☰ `🛎️` As chances são extremamente baixas; depende da sua sorte.\n"
            "> ☰ `🛎️` Premiações têm estoque limitado, sujeito a reposição.\n"
            "> ☰ `🛎️` Os prêmios não podem ser transferidos para outro usuário.\n"
            "> ☰ `🎟️` Ganhos exigem resgate via ticket e comprovante individual."
        ))
        cont.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        linha = discord.ui.ActionRow()
        linha.add_item(AcaoPainel("abrir", "Abrir", "<:luckblock:1572868783725609083>", discord.ButtonStyle.success))
        linha.add_item(AcaoPainel("historico", "Histórico", "📜", discord.ButtonStyle.secondary))
        linha.add_item(AcaoPainel("ranking", "Ranking", "<:versustrophy:1564669597440016485>", discord.ButtonStyle.secondary))
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
        "> `1.` Clique no botão **Abrir ticket para resgatar** abaixo.\n"
        "> `2.` Seu comprovante exclusivo será enviado ao ticket.\n"
        "> `3.` Aguarde a validação ou confirmação da equipe.\n\n"
        "**☰ OBSERVAÇÕES**\n"
        f"> `🏆` {premio['descricao']}\n"
        "> `🗃️` A recompensa é **individual e intransferível**.\n"
        "> `🧾` Guarde o protocolo para acompanhamento."
    )
    view = discord.ui.LayoutView(timeout=180 if teste else None)
    cont = discord.ui.Container(accent_colour=CORES)
    view._lucky_banner = adicionar_banner(cont, premio["banner"])
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


def cartao_reposicao(*, teste=False) -> discord.ui.LayoutView:
    """Anúncio sem revelar recompensas ou estoques internos."""
    conteudo = (
        "As Lucky Blocks da Família ROYAL receberam **novas unidades de premiações**!\n\n"
        "**☰ INFORMAÇÕES DA REPOSIÇÃO**\n"
        "> `📦` **Situação:** estoque atualizado e disponível.\n"
        f"> `🎁` **Onde participar:** <#{CANAL_PAINEL}>\n"
        "> `🎟️` **Tentativas:** 5 aberturas; após a quinta, renovação em 8 horas.\n"
        "> `🔒` O catálogo completo e as quantidades continuam reservados à administração.\n\n"
        "**☰ BOA SORTE!**\n"
        "> `🍀` Sua próxima abertura pode guardar uma surpresa.\n"
        "-# 👑 Família ROYAL • Notificação de reposição"
    )
    return cartao("<:luckblock:1572868783725609083> NOVO ESTOQUE NO LUCKY BLOCK", conteudo, teste=teste)


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
            await cog.alterar_estoque(self.guild_id, self.codigo, quantidade)
            await interaction.followup.send(
                f"✅ `{self.codigo}`: **{quantidade}** unidade(s) disponíveis. "
                "O sorteio e as probabilidades não foram alterados.", ephemeral=True)
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


class LuckyBlockRoyal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ticket_locks: dict[int, asyncio.Lock] = {}

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
            # Índice para recuperação de resgates e histórico.
            await con.execute("CREATE INDEX IF NOT EXISTS lucky_wins_guild_user_idx ON lucky_wins(guild_id,user_id)")
        self.bot.add_view(PainelLucky())
        self.bot.add_dynamic_items(BotaoTicket)
        LOG.info("Lucky Block ROYAL carregado; %d recompensas", len(PREMIACOES))

    async def cog_unload(self):
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
        canal = guild.get_channel(canal_id) or await guild.fetch_channel(canal_id)
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
                await ctx.author.send(view=view, **anexo_envio(view))
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
                    await con.execute("""INSERT INTO lucky_wins(opening_id,guild_id,user_id,reward_code,
                        reward_name,reward_rarity,reward_banner_url,role_id)
                        VALUES($1,$2,$3,$4,$5,$6,$7,$8)""",
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

    async def avisar_dono_sem_estoque(self, codigo: str, abertura_id: int):
        """Notifica o proprietário, sem divulgar o catálogo nem as quantidades."""
        try:
            if ID_DONO_DISCORD:
                owner_id = ID_DONO_DISCORD
            else:
                app = await self.bot.application_info()
                dono = app.owner
                owner_id = dono.id if isinstance(dono, discord.User) else None
            if owner_id:
                dono = await self.bot.fetch_user(owner_id)
                await dono.send(f"⚠️ **Lucky Block: estoque esgotado**\n"
                    f"Premiação: `{codigo}`\nÚltimo registro: `LB-{abertura_id:06d}`.\n"
                    "Use `!painelestoquelucky` para configurar o estoque.")
        except (discord.HTTPException, AttributeError):
            LOG.warning("Não foi possível avisar o dono sobre estoque esgotado: %s", codigo)

    async def avisar_reposicao(self, guild: discord.Guild):
        """Anúncio de reposição só no canal específico, sem expor a premiação/quantidade."""
        try:
            canal = await self.buscar_canal(guild, CANAL_ESTOQUE)
            await canal.send(view=cartao_reposicao(),
                allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, ValueError):
            LOG.exception("Falha ao anunciar reposição no canal de estoque %s", CANAL_ESTOQUE)

    async def mandar_dm_vencedor(self, membro: discord.Member, abertura: dict) -> bool:
        try:
            view = mensagem_premio(membro.guild.id, abertura)
            await membro.send(view=view, **anexo_envio(view))
            await self.bot.pool.execute("UPDATE lucky_wins SET dm_sent_at=NOW() WHERE opening_id=$1", abertura["id"])
            return True
        except discord.HTTPException:
            LOG.warning("Vencedor %s com DMs fechadas; registro #%d", membro.id, abertura["id"])
            return False

    async def anuncio(self, guild: discord.Guild, abertura_id: int) -> bool:
        row = await self.bot.pool.fetchrow("""UPDATE lucky_wins SET public_claimed_at=NOW()
            WHERE opening_id=$1 AND guild_id=$2 AND public_message_id IS NULL
              AND (public_claimed_at IS NULL OR public_claimed_at<NOW()-INTERVAL '5 minutes')
            RETURNING *""", abertura_id, guild.id)
        if not row:
            return False
        premio = PREMIACOES.get(row["reward_code"])
        raridade = row["reward_rarity"] or (premio["raridade"] if premio else "empty")
        if raridade not in ("epic", "legendary", "secret"):
            await self.bot.pool.execute("UPDATE lucky_wins SET public_claimed_at=NULL WHERE opening_id=$1", abertura_id)
            return False
        nome = row["reward_name"] or (premio["nome"] if premio else row["reward_code"])
        mensagem = texto_anuncio_premio(
            row["user_id"], nome, raridade, f"LB-{abertura_id:06d}")
        banner = banner_anuncio_premio(
            raridade, row["reward_banner_url"] or (premio["banner"] if premio else ""))
        view = cartao("🎉 PRÊMIO ESPECIAL ENCONTRADO!", mensagem, banner)
        # A marcação de todos deve ser um content real: menções em componentes não geram ping.
        everyone = raridade == "secret" and AVISAR_EVERYONE_SECRETOS
        try:
            canal = await self.buscar_canal(guild, CANAL_REGISTROS)
            # Components V2 não permite `content` na mesma mensagem do LayoutView.
            # Por isso, o @everyone é enviado em aviso separado, somente após salvar o anúncio.
            msg = await canal.send(view=view, **anexo_envio(view),
                allowed_mentions=discord.AllowedMentions.none())
            await self.bot.pool.execute("""UPDATE lucky_wins SET public_message_id=$2,
                public_claimed_at=NULL WHERE opening_id=$1""", abertura_id, msg.id)
            if everyone:
                try:
                    await canal.send("@everyone 🎉 Uma premiação **SECRETA** acaba de ser encontrada! "
                                     "Confira o anúncio acima.",
                        allowed_mentions=discord.AllowedMentions(everyone=True, users=False, roles=False))
                except discord.HTTPException:
                    LOG.exception("Anúncio secreto salvo, mas não foi possível mencionar @everyone")
            return True
        except Exception:
            await self.bot.pool.execute("UPDATE lucky_wins SET public_claimed_at=NULL WHERE opening_id=$1", abertura_id)
            LOG.exception("Falha ao anunciar Lucky Block #%d", abertura_id)
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
        view = cartao("🎉 PRÊMIO ESPECIAL ENCONTRADO!", txt, banner)
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
                              row["reward_banner_url"] or premio["banner"])
                # Uma tentativa de mensagem é feita enquanto a linha está bloqueada para evitar duplicatas.
                await ticket.send(view=view, **anexo_envio(view),
                    allowed_mentions=discord.AllowedMentions.none())
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
                    if premio["cargo_id"] and isinstance(interaction.user, discord.Member):
                        await self.ajustar_cargo(interaction.guild, interaction.user, resultado)
                    dm_ok = await self.mandar_dm_vencedor(interaction.user, resultado)
                    texto = (f"🎉 Você ganhou **{premio['nome']}**!\n"
                             f"📜 Protocolo: `LB-{resultado['id']:06d}`\n"
                             f"{'📨 Enviamos uma DM com o botão para abrir o ticket.' if dm_ok else '⚠️ Suas DMs estão fechadas. Abra-as para resgatar, ou avise a equipe com seu protocolo.'}")
                    view = cartao("🎁 PREMIAÇÃO ENCONTRADA", texto, premio["banner"])
                    await interaction.followup.send(view=view, ephemeral=True, **anexo_envio(view))
                    # Ao terminar a última unidade, o dono é alertado sem revelar o catálogo publicamente.
                    if resultado["estoque_restante"] == 0:
                        LOG.warning("Premiação %s esgotou no registro #%d", resultado["codigo"], resultado["id"])
                        await self.avisar_dono_sem_estoque(resultado["codigo"], resultado["id"])
                    await self.anuncio(interaction.guild, resultado["id"])
                    await self.comprovante_em_ticket_existente(interaction.guild, interaction.user.id, resultado["id"])
                else:
                    texto = "A caixa veio vazia, boa sorte na próxima!"
                    if resultado["sem_estoque"]:
                        texto = ("⚠️ Uma recompensa sorteada está sem estoque no momento. "
                                 "Nenhuma premiação foi reservada nesta abertura.")
                    texto += f"\n🎟️ Restantes: **{resultado['restantes']}/{ABERTURAS_POR_CICLO}**"
                    if resultado["renovacao"]:
                        texto += f"\n⏳ Renovação: <t:{int(resultado['renovacao'].timestamp())}:R>"
                    view = cartao("📦 CAIXA VAZIA", texto, BANNER_CAIXA_VAZIA)
                    await interaction.followup.send(view=view, ephemeral=True, **anexo_envio(view))
                return
            if acao == "historico":
                saldo, renovacao = await self.obter_saldo(guild_id, interaction.user.id)
                rows = await self.bot.pool.fetch("""SELECT id,reward_code,reward_name,rarity,created_at
                    FROM lucky_openings WHERE guild_id=$1 AND user_id=$2 ORDER BY id DESC LIMIT 10""",
                    guild_id, interaction.user.id)
                linhas = [f"`LB-{r['id']:06d}` · {r['reward_name'] or 'Caixa vazia'} · "
                          f"{raridade_nome(r['rarity'])} · <t:{int(r['created_at'].timestamp())}:R>" for r in rows]
                texto = ("\n".join(linhas) if linhas else "Você ainda não abriu nenhuma caixa.")
                texto += f"\n\n🎟️ Aberturas disponíveis: **{saldo}/{ABERTURAS_POR_CICLO}**"
                if renovacao:
                    texto += f"\n⏳ Renovação: <t:{int(renovacao.timestamp())}:R>"
                return await interaction.followup.send(view=cartao("📜 MEU HISTÓRICO", texto), ephemeral=True)
            if acao == "ranking":
                rows = await self.bot.pool.fetch("""SELECT user_id,COUNT(*) AS total,
                    SUM(CASE rarity WHEN 'epic' THEN 100 WHEN 'legendary' THEN 1000
                    WHEN 'secret' THEN 10000 ELSE 0 END) AS pontos
                    FROM lucky_openings WHERE guild_id=$1 GROUP BY user_id
                    ORDER BY pontos DESC,total DESC LIMIT 10""", guild_id)
                texto = "\n".join(f"**{i}.** <@{r['user_id']}> — {r['pontos']} pontos ({r['total']} caixas)"
                                  for i, r in enumerate(rows, 1)) or "Ainda não houve aberturas."
                return await interaction.followup.send(view=cartao("🏆 RANKING", texto), ephemeral=True)
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

    async def alterar_estoque(self, guild_id: int, codigo: str, quantidade: int) -> None:
        if codigo not in PREMIACOES or not 0 <= quantidade <= 100_000:
            raise ValueError("Código ou quantidade inválida")
        await self.garantir_guild(guild_id)
        async with self.bot.pool.acquire() as con:
            async with con.transaction():
                anterior = await con.fetchval("""SELECT stock_available FROM lucky_reward_stock
                    WHERE guild_id=$1 AND code=$2 FOR UPDATE""", guild_id, codigo)
                await con.execute("""UPDATE lucky_reward_stock
                    SET stock_total=GREATEST(0,stock_total-stock_available)+$3,
                        stock_available=$3 WHERE guild_id=$1 AND code=$2""", guild_id, codigo, quantidade)
        if anterior is not None and quantidade > anterior:
            guild = self.bot.get_guild(guild_id)
            if guild:
                await self.avisar_reposicao(guild)

    @commands.command(name="luckyresgatar")
    @commands.guild_only()
    async def luckyresgatar(self, ctx: commands.Context, abertura_id: int):
        """!luckyresgatar ID — reenvia uma DM com o botão de ticket ao verdadeiro vencedor."""
        row = await self.bot.pool.fetchrow("""SELECT * FROM lucky_wins
            WHERE guild_id=$1 AND opening_id=$2 AND user_id=$3""",
            ctx.guild.id, abertura_id, ctx.author.id)
        if not row:
            return await ctx.send("❌ Registro não encontrado para sua conta.", delete_after=15)
        premio = PREMIACOES.get(row["reward_code"])
        if premio is None:
            premio = dict(nome=row["reward_name"] or row["reward_code"],
                          raridade=row["reward_rarity"] or "legendary",
                          banner=row["reward_banner_url"] or "", descricao="Recompensa histórica.",
                          cargo_id=row["role_id"] or 0)
        entrada = {"id": abertura_id, "premio": premio}
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
                await mensagem.edit(content=None, embeds=[], view=view, **anexo_edicao(view))
                return await ctx.send(f"✅ Painel atualizado em {canal.mention}.")
            except (discord.NotFound, discord.HTTPException):
                LOG.warning("Painel anterior inacessível; criando outro")
        view = PainelLucky()
        msg = await canal.send(view=view, **anexo_envio(view))
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
            await self.alterar_estoque(guild.id, codigo.lower(), quantidade)
            await self.dm(ctx, texto=f"✅ `{codigo}`: estoque disponível atualizado para {quantidade}.")
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
            AND status='pending' RETURNING user_id,reward_code""",
            abertura_id, ctx.guild.id, ctx.author.id)
        if not row:
            return await self.dm(ctx, texto="❌ Registro inexistente ou já entregue.")
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
        await self.dm(ctx, texto="✅ Anúncio publicado." if enviado else "ℹ️ Registro inexistente ou já anunciado.")

    @commands.command(name="luckyvalidar")
    async def luckyvalidar(self, ctx: commands.Context, abertura_id: int):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        guild = ctx.guild or await self.guild_oficial()
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
                   "created_at": row["created_at"], "status": row["status"]}
        ticket = f"<#{row['ticket_channel_id']}>" if row["ticket_channel_id"] else "Aguardando abertura"
        view = cartao("✅ COMPROVANTE CONFERIDO NO BANCO",
                      recibo(entrada, row["user_id"]) + f"\n\n> `🎟️` **Ticket:** {ticket}",
                      row["reward_banner_url"] or premio["banner"])
        await self.dm(ctx, view=view)

    @commands.command(name="testarlucky", aliases=["testelucky"])
    async def testarlucky(self, ctx: commands.Context, codigo: str="lista", destino: str="dm"):
        if not await self.exigir_dono(ctx):
            return
        await self.apagar_comando(ctx)
        codigo, destino = codigo.lower().strip(), destino.lower().strip()
        if codigo == "clove":
            codigo = "clover"
        if codigo == "lista":
            texto = "🧪 **Comandos de teste — privados**\n" + "\n".join(
                f"`!testarlucky {c}` — {p['nome']} [{raridade_nome(p['raridade'])}]" for c,p in PREMIACOES.items())
            texto += ("\n`!testarlucky painel` · `!testarlucky vazia` · `!testarlucky todos`"
                      "\n`!testarlucky sorteio` · `!testarlucky fluxo` · `!testarlucky estoque` · `!testarlucky comprovante` · `!testarlucky sem_estoque` · `!testarlucky reposicao`"
                      "\n`!testarlucky clover registros` (prévia pública sem marcações)"
                      "\n`!simularlucky nitro_basico` (DM + anúncio idênticos ao real, temporários)"
                      "\n`!luckyvalidar ID` (valida comprovante real)")
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
            return await self.dm(ctx, view=cartao_reposicao(teste=True))
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
                    # Prévia da apresentação real, sem texto de teste. Não cria vitória no banco.
                    conteudo = texto_anuncio_premio(
                        ctx.author.id, premio["nome"], premio["raridade"], "LB-000000")
                    view = cartao("🎉 PRÊMIO ESPECIAL ENCONTRADO!", conteudo,
                        banner_anuncio_premio(premio["raridade"], premio["banner"]))
                else:
                    view = mensagem_premio(ctx.guild.id if ctx.guild else 0,
                                           teste_abertura, teste=True)
            if destino == "registros":
                # Sem @everyone, mesmo que a premiação simulada seja secreta.
                await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none(),
                                 delete_after=180, **anexo_envio(view))
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
        codigo = codigo.strip().lower()
        if codigo == "clove":
            codigo = "clover"
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
        titulo = "🎉 PRÊMIO ESPECIAL ENCONTRADO!"
        texto = texto_anuncio_premio(ctx.author.id, premio["nome"],
                                     premio["raridade"], "LB-000000")
        banner = banner_anuncio_premio(premio["raridade"], premio["banner"])
        view_publica = cartao(titulo, texto, banner)
        try:
            canal = await self.buscar_canal(guild, CANAL_REGISTROS)
            # Sem @everyone ou outras menções reais. Nunca cria comprovante.
            await canal.send(view=view_publica,
                             allowed_mentions=discord.AllowedMentions.none(),
                             delete_after=180, **anexo_envio(view_publica))
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
